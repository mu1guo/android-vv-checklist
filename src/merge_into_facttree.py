#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""merge_into_facttree.py — 把功能点注入 fact-tree（阶段 ③）。

读 compose_host_map.json（由 registry_from_tree.py 产）做精确映射，把每条功能点
挂到其宿主 page 的 functional_checks[]。只新增字段（functional_checks[] /
unmapped_functional_points[] / stats.a2h_functional_merge），不改导航与结构。

框架无关：host_map 里的 tap_by/tap_text/anchor_type/resource_id 已由阶段②按
framework 判别填好，这里原样透传，无需关心 compose/view。

注入的 check schema（对齐 visual-verify 的双 oracle 契约）：
  fp_id / name / feature_path / expected_llm / expected_llm_missing /
  expected_android(null) / android_trusted(null) / android_anchor{decl_file, impl_file, raw_identifier} /
  type_discriminator(null) / confidence / mapping_method / source /
  source_section / precondition_required / expected_source /
  tap_by / tap_text / anchor_type / resource_id / code_anchor

用法：
  python3 merge_into_facttree.py \
      --facttree <app>/spec/toolkit-fact-tree.json \
      --registry <app>/spec/a2h/functional_registry.json \
      --host-map <app>/spec/a2h/compose_host_map.json \
      [--in-place]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _fp_id(name: str) -> str:
    keep = "".join(ch if ch.isalnum() else "_" for ch in name)
    return f"FP_{keep}"


def merge(facttree: dict, registry: dict, host_map: dict) -> dict:
    pages = list(facttree.get("pages", [])) + list(facttree.get("fragments", [])) + list(facttree.get("dialogs", []))
    by_id = {p["id"]: p for p in pages}
    for p in pages:
        p.setdefault("functional_checks", [])

    by_feature_path = {e["feature_path"]: e for e in registry.get("entries", [])}

    mapped = 0
    unmapped: list[dict] = []
    for feature_path, hm in host_map.items():
        host_id = hm.get("host_id")
        page = by_id.get(host_id) if host_id else None
        entry = by_feature_path.get(feature_path, {})
        if page is None:
            unmapped.append({"feature_path": feature_path, "unmapped_reason": f"host_id {host_id!r} 不在 fact-tree"})
            continue
        page["functional_checks"].append({
            "fp_id": _fp_id(entry.get("name", feature_path)),
            "name": entry.get("name", hm.get("tap_text")),
            "feature_path": feature_path,
            "expected_llm": hm.get("expected"),
            "expected_llm_missing": not bool(hm.get("expected")),
            "expected_android": None,
            "android_trusted": None,
            "android_anchor": {
                "decl_file": entry.get("source_file"),
                "impl_file": None,
                "raw_identifier": entry.get("raw_identifier"),
            },
            "type_discriminator": None,
            "confidence": "high",
            "mapping_method": "compose_host_map",
            "source": "a2h_functional_merge",
            "source_section": entry.get("source_section"),
            "precondition_required": hm.get("precondition"),
            "expected_source": "inferred",
            "tap_by": hm.get("tap_by", "text"),
            "tap_text": hm.get("tap_text"),
            "anchor_type": hm.get("anchor_type", "text"),
            "resource_id": hm.get("resource_id"),
            "code_anchor": hm.get("code_anchor"),
        })
        mapped += 1

    facttree["unmapped_functional_points"] = unmapped
    stats = facttree.setdefault("stats", {})
    stats["a2h_functional_merge"] = {
        "total": len(host_map),
        "mapped": mapped,
        "unmapped": len(unmapped),
    }
    return facttree


def main() -> None:
    ap = argparse.ArgumentParser(description="把功能点注入 fact-tree（框架无关）")
    ap.add_argument("--facttree", required=True)
    ap.add_argument("--registry", required=True)
    ap.add_argument("--host-map", required=True)
    ap.add_argument("--in-place", action="store_true", help="原地改写 fact-tree")
    ap.add_argument("--out", help="另存输出路径（默认覆盖原路径）")
    args = ap.parse_args()

    facttree = _load(args.facttree)
    registry = _load(args.registry)
    host_map = _load(args.host_map)

    merged = merge(facttree, registry, host_map)
    out_path = args.out or args.facttree
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(merged, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    bill = merged["stats"]["a2h_functional_merge"]
    print(f"[ok] 注入 {bill['mapped']} 条 functional_checks；unmapped {bill['unmapped']} -> {out_path}")


if __name__ == "__main__":
    main()
