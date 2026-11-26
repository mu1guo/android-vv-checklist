#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""detect_framework.py — 确定性探测 Android app 的 UI 框架（阶段 ① 预扫）。

扫 app 源码，按信号把 app 归到三态之一：`compose` / `view` / `hybrid` / `unknown`：

  - compose 证据：`.kt`/`.java` 出现 `@Composable` / `setContent` / `androidx.compose`。
  - view 证据：`**/res/layout/**/*.xml` 存在；或 `.kt`/`.java` 出现 `setContentView(` / `R.layout.`。

二者并存 → hybrid。产出 `{framework, evidence:{compose:[...], view:[...]}}`。

用途：
  1. 给阶段① 的 LLM prompt（prompts/android-fact-tree.md）做 Phase 0 预扫提示。
  2. 给阶段⑤「说明」sheet 的架构行提供事实。
  3. 守卫：检测到 view 却喂了纯 compose 树 → 告警。

用法：
  python3 detect_framework.py --app <app> [--src <app>/app/src/main] [--out <app>/spec/framework.json]
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

SKIP_DIRS = {
    ".git", ".gradle", ".idea", "build", "node_modules", "__pycache__",
    ".venv", "venv", ".claude", "spec", "android_traverse_screenshots",
}

COMPOSE_MARKERS = ("@composable", "androidx.compose")
VIEW_MARKERS = ("setcontentview(", "r.layout.")


def _scan(root: str) -> tuple[list[str], list[str]]:
    compose_ev: list[str] = []
    view_ev: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, root).replace("\\", "/")
            if fn.endswith((".kt", ".java")):
                try:
                    with open(path, encoding="utf-8", errors="ignore") as fh:
                        low = fh.read().lower()
                except OSError:
                    continue
                if any(m in low for m in COMPOSE_MARKERS):
                    compose_ev.append(rel)
                if any(m in low for m in VIEW_MARKERS):
                    view_ev.append(rel)
            elif fn.endswith(".xml") and "/res/layout/" in "/" + rel:
                view_ev.append(rel)
    return compose_ev, view_ev


def classify(compose_ev: list[str], view_ev: list[str]) -> str:
    has_compose = bool(compose_ev)
    has_view = bool(view_ev)
    if has_compose and has_view:
        return "hybrid"
    if has_compose:
        return "compose"
    if has_view:
        return "view"
    return "unknown"


def main() -> None:
    ap = argparse.ArgumentParser(description="探测 Android app 的 UI 框架（compose/view/hybrid）")
    ap.add_argument("--app", required=True, help="app 根目录（含源码）")
    ap.add_argument("--src", help="源码子目录（默认扫整个 --app，跳过 build/.git 等）")
    ap.add_argument("--out", help="可选：写 spec/framework.json")
    args = ap.parse_args()

    root = args.src or args.app
    if not os.path.isdir(root):
        print(f"[err] 目录不存在：{root}", file=sys.stderr)
        sys.exit(1)

    compose_ev, view_ev = _scan(root)
    framework = classify(compose_ev, view_ev)
    doc = {"framework": framework, "evidence": {"compose": compose_ev, "view": view_ev}}

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print(f"[ok] {framework} -> {args.out}")

    print(f"[ok] framework={framework}  (compose 证据 {len(compose_ev)} 处 / view 证据 {len(view_ev)} 处)")


if __name__ == "__main__":
    main()
