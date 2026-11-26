# android-vv-checklist

**通用 vv 功能清单生成器**：从一个 Jetpack Compose App 的源码，端到端产出「安卓功能清单」xlsx（34 列，功能清单 / 页面路径 / 说明 三 sheet），并可同时产出喂给迁移评测（ECAT）用的 4 列 markdown。

> **vv = source-first（源码优先）**。先静态分析源码建「事实树 + 功能点契约」，再上真机边遍历回填「可达性 / 截图 / 实测结果」。对比 device-first（先盲遍历再猜功能），source-first 的功能点不依赖设备能走到哪、不依赖运行时枚举值是否恰好触发，因此**召回更全、能产出「不可达 / 条件弹窗」等 device-first 根本看不到的行**。

---

## 流水线（5 阶段）

```
Android Compose 源码 (.kt)
        │  ① compose-fact-tree          ← 唯一 LLM 阶段
        ▼
spec/toolkit-fact-tree.json             （薄树：pages / dialogs / components / flow_graph / features）
        │  ② compose_registry_from_tree.py    ← 确定性
        ▼
spec/a2h/functional_registry.json       （功能点枚举 + 源码锚点）
spec/a2h/compose_host_map.json          （功能点 → 宿主页精确映射）
spec/a2h/test_intents.json              （测试意图 + 预期结果判据）
        │  ③ compose_merge_into_facttree.py   ← 确定性（可选，喂 visual-verify）
        ▼
spec/toolkit-fact-tree.json + functional_checks[]
        │  ④ 真机边遍历（adb / aft）           ← 设备侧
        ▼
android_traverse_screenshots/index.json  （逐屏到达账本 + 截图）
        │  ⑤ gen_func_list.py                 ← 确定性
        ▼
<app>_安卓功能清单_YYYYMMDD_HHMMSS.xlsx  （34 列）+ 可选 4 列 markdown（ECAT）
```

| 阶段 | 输入 | 输出 | 主体 |
|---|---|---|---|
| ① compose-fact-tree | Compose 源码 | `toolkit-fact-tree.json` | **LLM**（`prompts/compose-fact-tree.md`） |
| ② compose_registry_from_tree | fact-tree | `functional_registry.json` + `compose_host_map.json` + `test_intents.json` | 确定性脚本 |
| ③ compose_merge_into_facttree | registry + host_map + fact-tree | fact-tree 加 `functional_checks[]` | 确定性脚本 |
| ④ 设备遍历 | fact-tree + 真机 | `index.json`（逐屏截图/可达） | 设备（adb 辅助脚本） |
| ⑤ gen_func_list | ②③ 的 JSON + index.json | 34 列 xlsx / 4 列 md | 确定性脚本 |

> 关键设计：**纯 Compose 只有阶段 ① 需要 LLM**。阶段 ② ③ 是确定性投影（交互组件已经由 compose-fact-tree 提取，宿主页天然已知，无需再猜）；阶段 ④ 是设备实走；阶段 ⑤ 是纯组装。这是从真实 vv 流水线（Cofi / Jetsnack 两套实测）中提炼的结论——详见 `docs/method.md`。

---

## 快速上手

依赖：`python3` + `openpyxl`（仅阶段 ⑤ 需要）。

```bash
pip install openpyxl
```

对一个已有 fact-tree 的 Compose 项目（`<app>` 目录）：

```bash
# ② 功能点契约（确定性）
python3 src/compose_registry_from_tree.py \
    --tree <app>/spec/toolkit-fact-tree.json \
    --out  <app>/spec/a2h

# ③ 注入 functional_checks（可选，喂 visual-verify 用）
python3 src/compose_merge_into_facttree.py \
    --facttree <app>/spec/toolkit-fact-tree.json \
    --registry <app>/spec/a2h/functional_registry.json \
    --host-map <app>/spec/a2h/compose_host_map.json \
    --in-place

# ④ 真机遍历（写 app 特定的遍历脚本，用 src/traverse/adb_traverse.py 的原语）

# ⑤ 生成 xlsx
python3 src/gen_func_list.py --app <app> [--config <app>/config.json]
```

`--app` 指向一个包含 `spec/` 与 `android_traverse_screenshots/` 的目录；`--config` 可选，承载 app 特定信息（设备页映射 `device_map`、账号态、架构说明等），缺省走自动推导。完整字段见 `docs/schema.md`。

跑通端到端示例（无需真机）：

```bash
examples/demo/run.sh
```

---

## 目录结构

```
docs/
  method.md         vv 方法论：source-first 为什么成立、关键坑
  schema.md         5 份 JSON 的字段契约（含 config.json）
prompts/
  compose-fact-tree.md   阶段 ① 的 LLM 提示词模板（唯一 LLM 阶段）
schemas/
  *.schema.json     5 份中间产物的 JSON Schema
src/
  compose_registry_from_tree.py    阶段 ②
  compose_merge_into_facttree.py   阶段 ③
  gen_func_list.py                 阶段 ⑤
  traverse/adb_traverse.py         阶段 ④ 的 adb 遍历原语（通用）
examples/demo/      最小示例，端到端可跑（无需真机）
```

## 关键约束

- **不改 Android 源码**：源码是只读 oracle，所有产出写到 `<app>/spec/` 与 `<app>/android_traverse_screenshots/`。
- **源码优先、真值 = 源码**：spec / 设备账本 / 任何派生物与实际源码冲突时，回源码为准。
- **功能点 = 交互组件**（`is_interactive=true`）。数据驱动列表（列表项 / 枚举 / 设置项）按同构家族压缩为 1 条，不逐项膨胀。
- **文案真值铁律**：控件文案必须解析 `stringResource(R.string.x)` 到 `strings.xml` 实际值（跨所有模块），严禁用资源 key 名 / 路由名 / CamelCase 反推。文案错 = 真机上点错 / 判错页。
