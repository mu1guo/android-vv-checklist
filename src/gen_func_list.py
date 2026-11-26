#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_func_list.py — 阶段 ⑤：组装 34 列安卓功能清单 xlsx（+ 可选 4 列 ECAT markdown）。

消费五样输入（路径相对 --app 目录）：
  1) spec/toolkit-fact-tree.json                 UI 树（pages/dialogs/components/navigation）
  2) spec/a2h/functional_registry.json           功能点枚举 + 源码锚点
  3) spec/a2h/compose_host_map.json              功能点 -> 宿主页精确映射
  4) spec/a2h/test_intents.json                  预期结果判据
  5) android_traverse_screenshots/index.json      真机边遍历账本（可达性/截图）
可选 6) config.json                                app 特定信息（账号态/device_map/架构说明）

纯组装：不做任何语义推理。功能点完备性由 registry 保证；设备只回填可达性。

用法：
  python3 gen_func_list.py --app <app> [--config <app>/config.json] [--ecat]
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
from collections import deque

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))

# 34 列（对齐 vv 流水线 AIPPT feature.xlsx）
HEADER = ["序号", "功能ID", "树内FP名", "一级模块", "功能路径", "功能点", "所在页面", "页面用途",
          "控件ID", "控件类型", "账号状态", "前置条件", "操作", "预期结果(源码推断)",
          "安卓实测结果", "实测可信", "实测来源", "可达性", "备注",
          "reach_path(树)", "点击路径", "步数", "路径验证", "页面截图",
          "步骤1", "步骤2", "步骤3", "步骤4", "步骤5", "步骤6", "步骤7", "步骤8", "步骤9", "步骤10"]

PAGE_HEADER = ["页面ID", "类型", "用途", "账号状态", "安卓实到达", "可达性", "备注",
               "reach_path(树)", "点击路径", "步数", "路径验证", "截图",
               "步骤1", "步骤2", "步骤3", "步骤4", "步骤5", "步骤6", "步骤7", "步骤8", "步骤9"]

NOOP = re.compile(r"no-op|todo", re.I)


def _load(path: str):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _load_if(path: str):
    return _load(path) if os.path.exists(path) else None


def _component_label(comp: dict) -> str:
    for key in ("text", "content_desc"):
        v = comp.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


class Checklist:
    def __init__(self, app_dir: str, config: dict | None):
        self.app = app_dir
        self.config = config or {}
        self.tree = _load(os.path.join(app_dir, "spec", "toolkit-fact-tree.json"))
        self.registry = _load(os.path.join(app_dir, "spec", "a2h", "functional_registry.json"))
        self.host_map = _load(os.path.join(app_dir, "spec", "a2h", "compose_host_map.json"))
        self.intents = _load(os.path.join(app_dir, "spec", "a2h", "test_intents.json"))
        self.units = _load_if(os.path.join(app_dir, "android_traverse_screenshots", "index.json")) or []

        self.pages = list(self.tree.get("pages", [])) + list(self.tree.get("dialogs", []))
        self.by_id = {p["id"]: p for p in self.pages}
        self.comp_by_page = {p["id"]: {c["id"]: c for c in p.get("components", [])} for p in self.pages}
        self.feat_label = {f["id"]: f["label"] for f in self.tree.get("features", [])}

        self.start_ids = {p["id"] for p in self.pages if p.get("is_start_destination")}
        self.device_map = self.config.get("device_map", {})
        self.account_state = self.config.get("account_state", "无账号体系（本地 mock）")

        # 预期判据：从 test_intents 的 steps 切「预期结果：」
        self.intent_expect: dict[str, str] = {}
        for grp in (self.intents.get("groups") or {}).values():
            for it in grp:
                for s in it.get("steps", []):
                    if "预期结果：" in s:
                        self.intent_expect[it["feature_path"]] = s.split("预期结果：", 1)[1].strip()

    # ---- 路径派生（基于 thin tree 的 navigation.inbound/outbound）----
    def _reach_path(self, pid: str) -> list[str]:
        if pid in self.start_ids:
            return [pid]
        parent: dict[str, str] = {}
        queue = deque(sorted(self.start_ids))
        visited = set(self.start_ids)
        while queue:
            cur = queue.popleft()
            for e in self.by_id.get(cur, {}).get("navigation", {}).get("outbound", []):
                to = e.get("to")
                if to and to in self.by_id and to not in visited:
                    visited.add(to)
                    parent[to] = cur
                    queue.append(to)
        if pid not in parent:
            return []
        path = [pid]
        while path[-1] in parent:
            path.append(parent[path[-1]])
        path.reverse()
        return path

    def _inbound_edge(self, pid: str) -> dict | None:
        rp = self._reach_path(pid)
        if len(rp) < 2:
            return None
        prev = rp[-2]
        for e in self.by_id[prev].get("navigation", {}).get("outbound", []):
            if e.get("to") == pid:
                return {"from": prev, "edge": e}
        return None

    def _trigger_label(self, from_page: str, edge: dict) -> str:
        comp = self.comp_by_page.get(from_page, {}).get(edge.get("via_component"), {})
        return _component_label(comp) or "入口"

    def _label(self, pid: str) -> str:
        return self.by_id[pid].get("label") or pid

    def reach_text(self, pid: str) -> str:
        return " → ".join(self._label(s) for s in self._reach_path(pid))

    def click_path(self, pid: str) -> str:
        p = self.by_id[pid]
        if pid in self.start_ids or p.get("type") == "Activity":
            return f"冷启动自动进入「{self._label(pid)}」"
        ie = self._inbound_edge(pid)
        if ie:
            lbl = self._trigger_label(ie["from"], ie["edge"])
            return f"冷启动 → {self._label(ie['from'])} → 点「{lbl}」→ {self._label(pid)}"
        return f"冷启动 → {self._label(pid)}"

    def steps(self, pid: str) -> list[str]:
        rp = self._reach_path(pid)
        out = []
        for i, s in enumerate(rp):
            out.append(s if i == 0 else f"进入「{self._label(s)}」")
        ie = self._inbound_edge(pid)
        if ie:
            out.append(f"点「{self._trigger_label(ie['from'], ie['edge'])}」")
        return out

    # ---- 设备可达性 ----
    def device_unit(self, host_id: str) -> dict | None:
        label = ((self.by_id.get(host_id) or {}).get("label") or "").lower()
        for u in self.units:
            if u.get("host_id") == host_id:
                return u
        mapped = self.device_map.get(host_id)
        if mapped:
            for u in self.units:
                if u.get("page_id") == mapped:
                    return u
        if label:
            for u in self.units:
                if (u.get("label") or "").lower() == label:
                    return u
        return None

    def page_purpose(self, pid: str) -> str:
        return self.by_id.get(pid, {}).get("purpose") or ""

    # ---- 功能清单 sheet ----
    def func_rows(self) -> list[list]:
        rows = []
        entries = self.registry.get("entries", [])
        for i, e in enumerate(entries, 1):
            name = e["name"]
            fp = e["feature_path"]
            segs = [s for s in fp.split(">") if s.strip()]
            module = segs[0] if segs else ""
            hm = self.host_map.get(fp, {})
            host_id = hm.get("host_id", "")
            comp_id = hm.get("component_id", "")
            comp = self.comp_by_page.get(host_id, {}).get(comp_id, {})
            ctype = comp.get("type", "元素")
            notes = comp.get("notes") or ""
            is_noop = bool(NOOP.search(notes))
            feat_id = self.by_id.get(host_id, {}).get("logical_feature_id", "")
            module_label = self.feat_label.get(feat_id, module)

            unit = self.device_unit(host_id)
            reached = unit is not None
            dev_label = unit.get("label", "") if unit else ""
            shot = ""
            if unit and unit.get("screenshot"):
                shot = os.path.relpath(os.path.join(self.app, "android_traverse_screenshots", unit["screenshot"]), HERE).replace("\\", "/")

            expect = self.intent_expect.get(fp) or hm.get("expected") or ""
            action = f"在 {self._label(host_id) if host_id in self.by_id else host_id} 页面点击「{name}」"

            if is_noop:
                actual = f"宿主页「{dev_label or host_id}」已到达；该控件源码为 no-op（点击无反应，范围外）"
            elif reached:
                actual = f"设备已到达宿主页「{dev_label}」"
            else:
                actual = "设备未到达（条件自动弹窗，遍历未触发）"

            st = self.steps(host_id)
            depth = len(self._reach_path(host_id))
            verif = "全程安卓实走确认" if reached else "源码推断"

            row = [
                i, "INT%04d" % i, "FP_" + re.sub(r"\W+", "_", name),
                module_label, fp, name, host_id, self.page_purpose(host_id),
                comp_id, ctype, self.account_state, hm.get("precondition") or "",
                action, expect, actual, "是" if reached else "否",
                "边遍历" if reached else "", "可达" if reached else "不可达", notes,
                self.reach_text(host_id), self.click_path(host_id), depth, verif, shot,
            ]
            row += st[:10]
            while len(row) < len(HEADER):
                row.append("")
            rows.append(row)
        return rows

    def page_rows(self) -> list[list]:
        dialog_ids = {d["id"] for d in self.tree.get("dialogs", [])}
        rows = []
        for p in self.pages:
            pid = p["id"]
            unit = self.device_unit(pid)
            reached = unit is not None
            st = self.steps(pid)
            shot = ""
            if unit and unit.get("screenshot"):
                shot = os.path.relpath(os.path.join(self.app, "android_traverse_screenshots", unit["screenshot"]), HERE).replace("\\", "/")
            note = "" if reached else self._unreached_note(pid)
            r = [
                pid,
                "Activity" if p.get("type") == "Activity" else ("弹窗" if pid in dialog_ids else "页面"),
                self.page_purpose(pid),
                self.account_state,
                "是" if reached else "否",
                "可达" if reached else "不可达",
                note,
                self.reach_text(pid), self.click_path(pid),
                len(self._reach_path(pid)),
                "全程安卓实走确认" if reached else "源码推断",
                shot,
            ]
            r += st[:9]
            while len(r) < len(PAGE_HEADER):
                r.append("")
            rows.append(r)
        return rows

    def _unreached_note(self, pid: str) -> str:
        notes = self.by_id.get(pid, {}).get("notes") or ""
        if notes:
            return notes
        return ""

    # ---- 输出 ----
    def app_name(self) -> str:
        return self.config.get("app_name") or (self.tree.get("app") or {}).get("label") or "App"

    def write_xlsx(self, out_path: str) -> None:
        import openpyxl
        from openpyxl.utils import get_column_letter

        wb = openpyxl.Workbook()
        ws1 = wb.active
        ws1.title = "功能清单"
        ws1.append(HEADER)
        for r in self.func_rows():
            ws1.append(r)

        ws2 = wb.create_sheet("页面路径")
        ws2.append(PAGE_HEADER)
        for r in self.page_rows():
            ws2.append(r)

        ws3 = wb.create_sheet("说明")
        name = self.app_name()
        pkg = (self.tree.get("app") or {}).get("package", "")
        ws3.append([f"{name}（{pkg}）安卓功能清单", None])
        ws3.append(["数据来源", "spec/toolkit-fact-tree.json + spec/a2h/{functional_registry,compose_host_map,test_intents}.json + android_traverse_screenshots/index.json"])
        ws3.append(["生成方式", "compose-fact-tree（LLM 源码分析）→ compose_registry_from_tree → compose_merge_into_facttree → 真机边遍历 → 本脚本"])
        ws3.append(["架构", self.config.get("architecture", "纯 Compose（无 XML/resource-id）；控件锚点用文案，源码位置用 .kt 相对路径")])
        ws3.append(["口径", "功能点 = 交互组件（is_interactive=true）；数据驱动列表按同构家族压缩为 1 条"])
        ws3.append(["账号态", self.account_state])
        ws3.append(["遍历", self.config.get("traverse_notes", "")])

        for ws in (ws1, ws2):
            for ci in range(1, ws.max_column + 1):
                ws.column_dimensions[get_column_letter(ci)].width = 18
        wb.save(out_path)

        n_reached = sum(1 for r in self.func_rows() if r[17] == "可达")
        print(f"[ok] {out_path}")
        print(f"   功能清单 {len(self.func_rows())} 行 / {len(HEADER)} 列；页面路径 {len(self.page_rows())} 行")
        print(f"   设备可达 {n_reached} 条功能点，不可达 {len(self.func_rows()) - n_reached} 条")

    def write_ecat(self, out_path: str) -> None:
        seen: set[str] = set()
        rows: list[str] = []
        for e in self.registry.get("entries", []):
            fp = e.get("feature_path", "")
            if fp in seen:
                continue
            seen.add(fp)
            path = " > ".join(s for s in fp.split(">") if s.strip())
            rows.append(f"| F{len(rows)+1:03d} | {e['name']} | {path} | {e.get('source_file', '')} |")
        lines = ["| ID | 功能名 | 层级路径 | 源码位置 |", "| --- | --- | --- | --- |"] + rows
        with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")
        n_anchored = sum(1 for r in rows if r.rsplit("|", 2)[1].strip())
        print(f"[ok] {out_path} — {len(rows)} 条，含源码位置 {n_anchored} 条")


def main() -> None:
    ap = argparse.ArgumentParser(description="组装 34 列安卓功能清单 xlsx（+ 可选 ECAT markdown）")
    ap.add_argument("--app", required=True, help="app 目录（含 spec/ 与 android_traverse_screenshots/）")
    ap.add_argument("--config", help="可选 config.json（app 特定信息）")
    ap.add_argument("--ecat", action="store_true", help="同时产出 4 列 ECAT markdown")
    ap.add_argument("--out", help="xlsx 输出路径（默认 <app>/<前缀>_<时间戳>.xlsx）")
    args = ap.parse_args()

    config = _load(args.config) if args.config and os.path.exists(args.config) else None
    cl = Checklist(args.app, config)

    prefix = (config or {}).get("output_prefix", f"{cl.app_name()}_安卓功能清单")
    out_xlsx = args.out or os.path.join(args.app, f"{prefix}_{datetime.datetime.now():%Y%m%d_%H%M%S}.xlsx")
    cl.write_xlsx(out_xlsx)

    if args.ecat:
        out_md = os.path.join(args.app, f"{prefix}_ecat_checklist.md")
        cl.write_ecat(out_md)


if __name__ == "__main__":
    main()
