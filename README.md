# android-vv-checklist — `real_vv_tianyou_version`

**本分支**忠实记录**真实生产环境**的 vv 功能清单生成方法（「天佑版」）。它和 `main` / `v2` 里我手写的「source-first 确定性脚本流水线」是两回事——真实方法**不是**「一套『只有阶段①是 LLM』的确定性脚本」，而是**一组 Claude Code skill 编排**：

```
android-fact-tree         判架构 → 分发到三态生成器（统一入口 + 确定性闸）
        ↓  spec/toolkit-fact-tree.json（三态字段同构的 UI 树）
a2h-functional-registry   功能点契约（functional_registry.json + test_intents.json）
a2h-functional-merge      注入 functional_checks[]（双 oracle 种子）
        ↓  spec/toolkit-fact-tree.json + functional_checks[]
arkts-visual-verify       安卓真机边遍历 + Phase 0.5 grounding（回填 expected_android/android_trusted）
        ↓  android_traverse_screenshots/index.json（逐屏到达账本 + 截图）
gen_func_list.py          按「UI 树 + 功能树」组装 34 列 xlsx 功能清单
```

## 读哪份

| 文件 | 内容 |
|---|---|
| `docs/real-pipeline.md` | 完整流水线：每个 skill 干什么、怎么接、为什么这么分 |
| `docs/contracts.md` | 中间产物的字段契约（尤其 `functional_checks[]` 的**双 oracle** 结构） |
| `docs/diff-from-v1v2.md` | 与 `main`/`v2` 的两处关键差异（我此前理解错在哪） |
| `prompts/functional-checklist.md` | 真实调用 prompt（遍历安卓 → 生成 Excel 功能清单） |
| `reference/gen_func_list.py` | 真实 Excel 组装脚本（Cofi 纯 Compose 实例，含 34 列 schema） |

## 三处关键事实（与 v1/v2 的纠偏）

1. **「只有阶段①是 LLM」只对纯 Compose 成立**。XML / 混合的 `functional_registry.json` 由 `a2h-functional-registry` 用 **LLM 读全源码 + census** 生成（锚点 = 真 resource-id）；只有纯 Compose 才走 `compose_registry_from_tree.py` 的**确定性投影**（因为 compose-fact-tree 已把交互组件抽进树、join 天然完成）。所以真实方法的 LLM 阶段是 **2 个**（fact-tree 产树 + XML 功能注册表），不是 1 个。

2. **设备遍历不止回填「可达性 / 截图」**，还有 **Phase 0.5 grounding**：安卓趟遍历时逐功能点在**真机实操** + 用独立结构指纹自验落点，回填 `expected_android`（主 oracle，真值）+ `android_trusted`（该真值是否可信）。下游判定按 `android_trusted` 分流：`true` 比 `expected_android`，`false` 退回 `expected_llm`。v1/v2 把这些字段留成 `null`，等于把「双 oracle」退化成了「单 oracle（LLM 猜）」。

3. **「功能点 → 页面」的映射不是纯确定性**。XML/混合靠 `resource-id` grep + 模糊 join（确定性覆盖 ~82%）+ **对低置信枚举功能点派 LLM 精修**（定位分发中枢 `when(type){…}` 背后的真正入口宿主页）；纯 Compose 才是 `compose_host_map.json` 精确映射。

详见 `docs/diff-from-v1v2.md`。

## 分支关系

| 分支 | 是什么 |
|---|---|
| `main` | v1：纯 Jetpack Compose 的 source-first 确定性脚本流水线 |
| `v2` | 推广到原生三态（Compose/View/hybrid）的 source-first 确定性脚本流水线 |
| `real_vv_tianyou_version` | **本分支**：真实生产方法（skill 编排 + 双 oracle grounding）的忠实记录 |

> 本分支里的 `src/`、`schemas/`、`examples/`、`docs/method.md`、`docs/schema.md`、`prompts/compose-fact-tree.md` 等仍是从 `main` 继承的「简化版确定性流水线」——它们是 `docs/diff-from-v1v2.md` 里被纠偏的对照物，**不是**真实方法。真实方法以本 README + `docs/` + `prompts/functional-checklist.md` + `reference/` 为准。

## 关键约束（沿用）

- **不改 Android 源码**：源码是只读 oracle，一切产出写 `<app>/spec/` 与 `<app>/android_traverse_screenshots/`。
- **真值 = 源码**，但**安卓实测（grounding 后的 `expected_android`）是功能判定的主 oracle**——LLM 的 `expected_llm` 只是保底种子。
- **功能点 = 交互组件**（`is_interactive=true`）；数据驱动列表按同构家族压缩为 1 条。
- **文案真值铁律**：控件文案必须解析到 `strings.xml` 实际值（跨所有模块），严禁用资源 key / CamelCase 反推。
