#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""registry_from_tree.py — 框架感知：fact-tree → 功能点契约（阶段 ②）。

从 fact-tree 产物 spec/toolkit-fact-tree.json 中，把每个 page/dialog 的交互组件
（is_interactive=true）投影为三份契约产物 + 精确宿主映射：

  - functional_registry.json    {entries: [{name, depth, feature_path, source_file,
                                             source_section, raw_identifier,
                                             anchor_type, resource_id}]}
  - compose_host_map.json       {feature_path: {host_id, component_id, tap_text,
                                                tap_by, anchor_type, resource_id,
                                                code_anchor, expected, to_page,
                                                precondition}}
  - test_intents.json           {app_package_name, groups: {...}}

**框架感知**：原生三态 `compose` / `view` / `hybrid`（见 fact-tree 的 `framework`
字段，app/page/component 三级，缺省 compose）。锚点策略按框架切换：

  - view 且有 resource_id → tap_by="resource_id"，raw_identifier=resource_id，
    tap_text=文案（text/content_desc，兜底 resource_id 短名）。
  - 否则（compose / view 无 id）→ tap_by="text"，raw_identifier=文案。

`name`（显示名）永远取人话文案；`raw_identifier`/`tap_by` 才区分锚点。纯确定性、
无 LLM：交互组件已经是 fact-tree 的提取产物，宿主页天然已知。

用法：
  python3 registry_from_tree.py --tree <app>/spec/toolkit-fact-tree.json --out <app>/spec/a2h
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# Windows GBK 控制台：让 stdout 输出 UTF-8，避免中文 mojibake（文件本身始终 UTF-8）
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _resource_short(resource_id: str | None) -> str:
    """com.example:id/btn_x（或 @+id/btn_x）→ btn_x。"""
    if not isinstance(resource_id, str) or not resource_id.strip():
        return ""
    return resource_id.strip().split("/")[-1]


def _component_label(comp: dict) -> str:
    """控件可见文案：text 优先，其次 content_desc，再 resource_id 短名，兜底 TypeName#id。"""
    for key in ("text", "content_desc"):
        value = comp.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    short = _resource_short(comp.get("resource_id"))
    if short:
        return short
    comp_id = comp.get("id") or "component"
    return f"{comp.get('type', 'Component')}#{comp_id}"


def _framework_of(comp: dict, page: dict, app_fw: str) -> str:
    """组件级 framework 优先，其次页级，再 app 级，缺省 compose。"""
    fw = comp.get("framework") or page.get("framework") or app_fw or "compose"
    return "view" if fw == "view" else "compose"


def _anchor_for(comp: dict, name: str, fw: str) -> tuple[str, str, str, str | None, str]:
    """返回 (tap_by, raw_identifier, tap_text, resource_id, anchor_type)。"""
    rid = comp.get("resource_id")
    if fw == "view" and isinstance(rid, str) and rid.strip():
        return "resource_id", rid, name, rid, "resource_id"
    return "text", name, name, (rid if isinstance(rid, str) and rid.strip() else None), "text"


def _source_section(comp: dict, fw: str) -> str:
    prefix = "view" if fw == "view" else "compose"
    return f"{prefix}_{str(comp.get('type', 'component')).lower()}"


def _expected_for(comp: dict, page: dict, pages_by_id: dict[str, dict]) -> tuple[str, str | None]:
    nav = comp.get("navigation") or {}
    to_page = nav.get("to_page")
    if isinstance(to_page, str) and to_page:
        return f"点击后跳转到 {to_page} 页面", to_page
    return "click 后触发对应行为，页面无异常", None


def build(tree: dict) -> tuple[dict, dict, dict]:
    pages = list(tree.get("pages", [])) + list(tree.get("fragments", [])) + list(tree.get("dialogs", []))
    pages_by_id = {p["id"]: p for p in pages}
    app_fw = (tree.get("app") or {}).get("framework") or "compose"

    entries: list[dict] = []
    host_map: dict[str, dict] = {}
    intents: dict[str, list[dict]] = {"independent": [], "setup": [], "dependent": [], "blocked": []}

    for page in pages:
        page_label = page.get("label") or page["id"]
        for comp in page.get("components", []):
            if not comp.get("is_interactive", False):
                continue

            name = _component_label(comp)
            fw = _framework_of(comp, page, app_fw)
            feature_path = f"{page_label}>{name}"
            anchor = comp.get("source_anchor") or {}
            source_file = anchor.get("file") or page.get("android_file")
            line = anchor.get("line")
            code_anchor = f"{source_file}:{line}" if (source_file and line is not None) else (source_file or "")

            tap_by, raw_identifier, tap_text, resource_id, anchor_type = _anchor_for(comp, name, fw)

            entries.append({
                "name": name,
                "depth": 2,
                "feature_path": feature_path,
                "source_file": source_file,
                "source_section": _source_section(comp, fw),
                "raw_identifier": raw_identifier,
                "anchor_type": anchor_type,
                "resource_id": resource_id,
            })

            expected, to_page = _expected_for(comp, page, pages_by_id)
            host_map[feature_path] = {
                "host_id": page["id"],
                "component_id": comp.get("id"),
                "tap_text": tap_text,
                "tap_by": tap_by,
                "anchor_type": anchor_type,
                "resource_id": resource_id,
                "code_anchor": code_anchor,
                "expected": expected,
                "to_page": to_page,
                "precondition": None,
            }

            intents["independent"].append({
                "feature_path": feature_path,
                "steps": [f"在 {page_label} 页面点击「{name}」，预期结果：{expected}"],
                "expected_source": "inferred",
                "precondition_required": None,
            })

    registry = {"entries": entries}
    intents_doc = {"app_package_name": (tree.get("app") or {}).get("package"), "groups": intents}
    return registry, host_map, intents_doc


def main() -> None:
    ap = argparse.ArgumentParser(description="fact-tree → functional_registry + host_map + test_intents（框架感知）")
    ap.add_argument("--tree", required=True, help="spec/toolkit-fact-tree.json")
    ap.add_argument("--out", required=True, help="输出目录（spec/a2h）")
    args = ap.parse_args()

    tree = _load(args.tree)
    registry, host_map, intents = build(tree)
    os.makedirs(args.out, exist_ok=True)

    outputs = {
        "functional_registry.json": registry,
        "compose_host_map.json": host_map,
        "test_intents.json": intents,
    }
    for filename, doc in outputs.items():
        with open(os.path.join(args.out, filename), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print(f"[ok] {filename}")

    n_resid = sum(1 for e in registry["entries"] if e.get("anchor_type") == "resource_id")
    print(f"[ok] {len(registry['entries'])} 功能点 -> {args.out}（resource_id 锚点 {n_resid} 条）")


if __name__ == "__main__":
    main()
