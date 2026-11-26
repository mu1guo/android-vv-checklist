#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""compose_registry_from_tree.py — 纯 Compose 旁路：fact-tree → 功能点契约（阶段 ②）。

从 compose-fact-tree 产出的 spec/toolkit-fact-tree.json 中，把每个 page/dialog 的
交互组件（is_interactive=true）投影为 A2H Stage1 的两份契约产物 + 精确宿主映射：

  - functional_registry.json    {entries: [{name, depth, feature_path, source_file,
                                             source_section, raw_identifier}]}
  - compose_host_map.json       {feature_path: {host_id, component_id, tap_text,
                                                tap_by, code_anchor, expected,
                                                to_page, precondition}}
  - test_intents.json           {app_package_name, groups: {...}}

纯确定性、无 LLM：交互组件已经是 compose-fact-tree 的提取产物，宿主页天然已知
（join 已完成）。锚点 = 文案（text/content_desc），tap_by = "text"（Compose 无 resource-id）。

用法：
  python3 compose_registry_from_tree.py --tree <app>/spec/toolkit-fact-tree.json --out <app>/spec/a2h
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


def _component_label(comp: dict) -> str:
    """控件可见文案：text 优先，其次 content_desc，兜底 TypeName#id。"""
    for key in ("text", "content_desc"):
        value = comp.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    comp_id = comp.get("id") or "component"
    return f"{comp.get('type', 'Component')}#{comp_id}"


def _source_section(comp: dict) -> str:
    return "compose_" + str(comp.get("type", "component")).lower()


def _expected_for(comp: dict, page: dict, pages_by_id: dict[str, dict]) -> tuple[str, str | None]:
    nav = comp.get("navigation") or {}
    to_page = nav.get("to_page")
    if isinstance(to_page, str) and to_page:
        return f"点击后跳转到 {to_page} 页面", to_page
    return "click 后触发对应行为，页面无异常", None


def build(tree: dict) -> tuple[dict, dict, dict]:
    pages = list(tree.get("pages", [])) + list(tree.get("dialogs", []))
    pages_by_id = {p["id"]: p for p in pages}

    entries: list[dict] = []
    host_map: dict[str, dict] = {}
    intents: dict[str, list[dict]] = {"independent": [], "setup": [], "dependent": [], "blocked": []}

    for page in pages:
        page_label = page.get("label") or page["id"]
        for comp in page.get("components", []):
            if not comp.get("is_interactive", False):
                continue

            name = _component_label(comp)
            feature_path = f"{page_label}>{name}"
            anchor = comp.get("source_anchor") or {}
            source_file = anchor.get("file") or page.get("android_file")
            line = anchor.get("line")
            code_anchor = f"{source_file}:{line}" if (source_file and line is not None) else (source_file or "")

            entries.append({
                "name": name,
                "depth": 2,
                "feature_path": feature_path,
                "source_file": source_file,
                "source_section": _source_section(comp),
                "raw_identifier": name,
            })

            expected, to_page = _expected_for(comp, page, pages_by_id)
            host_map[feature_path] = {
                "host_id": page["id"],
                "component_id": comp.get("id"),
                "tap_text": name,
                "tap_by": "text",
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
    ap = argparse.ArgumentParser(description="fact-tree → functional_registry + compose_host_map + test_intents")
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

    print(f"[ok] {len(registry['entries'])} 功能点 -> {args.out}")


if __name__ == "__main__":
    main()
