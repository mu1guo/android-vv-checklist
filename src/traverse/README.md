# 阶段 ④ 真机边遍历

`adb_traverse.py` 提供**可复用原语**（dump / nodes / find / tapn / back / capture / save_index），
不是开箱即跑的遍历器——每个 app 的屏、入口、弹窗都不同，遍历路径必须按该 app 的 fact-tree 写。

## 写一个 app 特定的遍历脚本

```python
# traverse_<app>.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # 指向 src/traverse
from adb_traverse import Traverse

t = Traverse(device="emulator-5554", pkg="com.example.app.debug",
             activity="com.example.app.MainActivity", out="android_traverse_screenshots")

t.cold_start()
ns = t.capture("page_0001_Home", "Home", host_id="HomeScreen")

# 按 fact-tree 的 inbound edge 找入口控件，逐屏走
settings = t.find(ns, "Settings", click=True)
if settings:
    t.tapn(settings)
    t.capture("page_0002_Settings", "Settings", host_id="SettingsScreen")
    t.back()
    ns = t.dump_nodes()

t.save_index()
```

## 关键点

1. **`host_id` 是「屏 → fact-tree 页」的桥梁**。给 `capture(..., host_id="HomeScreen")` 显式传
   fact-tree 里的 page id，`gen_func_list.py` 就能自动把遍历账本关联回页面，**无需再写 `config.device_map`**。
2. **条件自动弹窗**（通知权限 / 完成 N 次后弹）：遍历未触发是正常的，`gen_func_list.py` 会把这类行标
   「设备未到达（条件自动弹窗，遍历未触发）」，属已知口径，不是失败。
3. **no-op stub**：`find` 到控件但点击无反应的，记一屏、留给 gen_func_list 标「no-op（范围外）」。
4. **Compose 单 Activity 判屏**：`uiautomator dump` 的 Activity 名对所有屏相同，靠文案/`content_desc`
   （`find` 的 needle）判屏；控件锚点用 `text`/`content_desc`，不用 resource-id（Compose 没有）。
5. **settle 时长**：`tapn`/`back` 默认 1.5–2s，慢屏可调大；截图前确保动画稳定。

## 输出契约

`index.json` 每屏一个 unit（字段见 `../../docs/schema.md` §5）：`page_id` / `label` / `host_id`(可选) /
`screenshot` / `view_xml` / `clickable_count` / `timestamp`。逐屏 `screenshot.png` + `view.xml` 落
`<page_id>/` 子目录。
