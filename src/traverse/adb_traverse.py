#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""adb_traverse.py — 阶段 ④ 的通用 adb 边遍历原语（供 app 特定遍历脚本 import）。

真机边遍历：冷启动 → 逐屏 dump UI 树 + 截图 → 记录「page_id / label / screenshot / view.xml /
clickable_count」到 index.json。这不是一个开箱即跑的遍历器——每个 app 的屏/入口/弹窗都不同，
遍历路径必须由人（或 LLM）按该 app 的 fact-tree 写。这里提供的是**可复用原语**：

  dump / nodes / find / find_back / tapn / tap_xy / back / capture / save_index

用法定式（写一个 app 特定的 traverse_<app>.py）：

    from adb_traverse import Traverse
    t = Traverse(device="emulator-5554", pkg="com.example.app", activity="com.example.app.MainActivity", out="android_traverse_screenshots")
    t.cold_start()
    ns = t.capture("page_0001_Home", "Home")
    btn = t.find(ns, "Settings", click=True)
    if btn:
        t.tapn(btn); t.capture("page_0002_Settings", "Settings"); t.back()
    t.save_index()

capture 的 unit 会带 `host_id=None`；若你按 fact-tree page id 命名 page_id（或显式传 host_id=），
gen_func_list.py 就能自动把「屏」关联回「页面」，无需再写 device_map。见本目录 README。
"""
from __future__ import annotations

import datetime
import html
import json
import os
import re
import subprocess
import time


class Traverse:
    def __init__(self, *, device: str, pkg: str, activity: str, out: str):
        self.device = device
        self.pkg = pkg
        self.activity = activity
        self.out = out
        self.xml_tmp = "//sdcard/ui.xml"
        self.units: list[dict] = []
        os.makedirs(out, exist_ok=True)

    def sh(self, cmd: str) -> str:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return (r.stdout + r.stderr).strip()

    def adb(self, *a: str) -> str:
        return self.sh("adb -s " + self.device + " " + " ".join(a))

    # ---- 底层 ----
    def dump(self) -> str:
        self.adb("shell uiautomator dump " + self.xml_tmp)
        self.adb("pull " + self.xml_tmp + ' "' + os.path.join(self.out, "_cur.xml") + '"')
        with open(os.path.join(self.out, "_cur.xml"), encoding="utf-8") as fh:
            return fh.read()

    def nodes(self, xml: str) -> list[dict]:
        out = []
        for n in re.split(r"<node ", xml)[1:]:
            if "text=" not in n:
                continue
            txt = re.search(r'text="([^"]*)"', n).group(1)
            cd = re.search(r'content-desc="([^"]*)"', n)
            cd = cd.group(1) if cd else ""
            clk = 'clickable="true"' in n
            b = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', n)
            if not b:
                continue
            x1, y1, x2, y2 = map(int, b.groups())
            out.append({"text": html.unescape(txt), "desc": html.unescape(cd),
                        "click": clk, "cx": (x1 + x2) // 2, "cy": (y1 + y2) // 2,
                        "bounds": [x1, y1, x2, y2]})
        return out

    def find(self, ns: list[dict], needle: str, click: bool | None = None) -> dict | None:
        low = needle.lower()
        for n in ns:
            if low in n["text"].lower() or low in n["desc"].lower():
                if click is None or n["click"] == click:
                    return n
        return None

    def find_back(self, ns: list[dict]) -> dict | None:
        cand = [n for n in ns if n["click"] and n["bounds"][0] < 250 and 40 < n["cy"] < 260]
        return cand[0] if cand else None

    def tapn(self, n: dict, settle: float = 2.0) -> None:
        self.adb("shell", "input", "tap", str(n["cx"]), str(n["cy"]))
        time.sleep(settle)

    def tap_xy(self, x: int, y: int, settle: float = 2.0) -> None:
        self.adb("shell", "input", "tap", str(x), str(y))
        time.sleep(settle)

    def back(self, settle: float = 1.5) -> None:
        self.adb("shell", "input", "keyevent", "4")
        time.sleep(settle)

    def text(self, s: str) -> None:
        self.adb("shell", "input", "text", s)

    # ---- 冷启动 ----
    def cold_start(self, settle: float = 4.0) -> None:
        self.adb("shell", "am", "force-stop", self.pkg)
        time.sleep(1)
        self.adb("shell", "am", "start", "-n", self.pkg + "/" + self.activity)
        time.sleep(settle)

    # ---- 采集一屏 ----
    def capture(self, page_id: str, label: str, *, host_id: str | None = None, extra: dict | None = None) -> list[dict]:
        os.makedirs(os.path.join(self.out, page_id), exist_ok=True)
        xml = self.dump()
        with open(os.path.join(self.out, page_id, "view.xml"), "w", encoding="utf-8") as fh:
            fh.write(xml)
        self.adb("shell screencap -p //sdcard/" + page_id + ".png")
        self.adb("pull //sdcard/" + page_id + '.png "' + os.path.join(self.out, page_id, "screenshot.png") + '"')
        self.adb("shell rm //sdcard/" + page_id + ".png")
        ns = self.nodes(xml)
        unit = {
            "page_id": page_id,
            "label": label,
            "host_id": host_id,
            "timestamp": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
            "device": "adb",
            "clickable_count": sum(1 for n in ns if n["click"]),
            "screenshot": page_id + "/screenshot.png",
            "view_xml": page_id + "/view.xml",
            "manual_traverse": True,
        }
        if extra:
            unit.update(extra)
        self.units.append(unit)
        print("  [cap] %-28s %-24s clickable=%d" % (page_id, label, unit["clickable_count"]))
        return ns

    def save_index(self) -> None:
        with open(os.path.join(self.out, "index.json"), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(self.units, fh, ensure_ascii=False, indent=2)
        print("  [idx] %d units -> index.json" % len(self.units))
