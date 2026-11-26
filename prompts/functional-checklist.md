# 真实 vv 功能清单生成 prompt

## 核心用法（用户实际使用的方式）

> 用 arkts-visual-verify 遍历安卓应用：`<安卓应用路径>`，**不跑鸿蒙**。遍历完后根据 UI 树和功能树生成 Excel 功能清单。功能清单格式可参考：`<过往功能清单>`。

拆解：

1. **`用 arkts-visual-verify 遍历安卓应用：<安卓应用路径>`** —— 触发 `arkts-visual-verify` 的**安卓趟**（edge-walk 边遍历 + UI 树 dump + 截图 + Phase 0.5 grounding 回填 `expected_android`/`android_trusted`），产 `android_traverse_screenshots/index.json`。
2. **`不跑鸿蒙`** —— 只做安卓趟 + grounding，跳过鸿蒙趟（鸿蒙趟是 A2H 迁移一致性别验证用的，功能清单生成用不到）。
3. **`遍历完后根据 UI 树和功能树生成 Excel 功能清单`** —— 用 `gen_func_list.py` 消费「UI 树（fact-tree）+ 功能树（functional_registry / test_intents）+ 遍历账本（index.json）」，产 34 列 xlsx。
4. **`功能清单格式可参考：<过往功能清单>`** —— 34 列 schema 对齐既有 AIPPT feature.xlsx / Cofi 清单。

### skill 版本

`arkts-visual-verify` skill 版本：<https://github.com/fuxi-ailabs/ArkTs-Core/tree/version_1030/arkts-skills/skills/arkts-visual-verify>

---

## 前置（不在上面的 prompt 里，但真实流程需要）

上面的 prompt 假设「UI 树 + 功能树」已经存在。完整前置链：

```bash
# ① 产 UI 树（判架构分发到三态生成器 + 确定性闸）
#    android-fact-tree: dispatch.py plan <src> → 三态生成器 → dispatch.py gate

# ② 产功能点契约（XML/混合 = LLM 读全源码；纯 Compose = 确定性投影）
#    a2h-functional-registry → spec/a2h/{functional_registry,test_intents}.json

# ③ 注入 functional_checks[]（双 oracle 种子）
#    a2h-functional-merge → spec/toolkit-fact-tree.json + functional_checks[]

# ④ 安卓趟 + grounding（上面 prompt 的核心）
#    arkts-visual-verify（不跑鸿蒙）

# ⑤ 组装 Excel
#    gen_func_list.py
```

即真实方法是 `① → ② → ③ → ④ → ⑤` 的编排（详见 `docs/real-pipeline.md`），用户那句 prompt 是把最外层的「遍历 + 出清单」两个动作合并了，其余由 `android-fact-tree` 的 §3.5 自动接续。

---

## 34 列 schema（对齐过往功能清单）

`gen_func_list.py` 的「功能清单」sheet 表头：

| # | 列 | 来源 |
|---|---|---|
| 1 | 序号 | 枚举 |
| 2 | 功能ID | `INT0001…` |
| 3 | 树内FP名 | `FP_<name>` |
| 4 | 一级模块 | feature 聚类 label |
| 5 | 功能路径 | `feature_path` |
| 6 | 功能点 | `name` |
| 7 | 所在页面 | `host_id` |
| 8 | 页面用途 | fact-tree `purpose` |
| 9 | 控件ID | `component_id` |
| 10 | 控件类型 | `type` |
| 11 | 账号状态 | app 特定（无账号体系则写死） |
| 12 | 前置条件 | `precondition` / `precondition_required` |
| 13 | 操作 | 「在 X 页面点击「name」」 |
| 14 | 预期结果(源码推断) | intents `预期结果：` 切出 / `expected_llm` |
| 15 | 安卓实测结果 | grounding `expected_android` 回填 |
| 16 | 实测可信 | `android_trusted` |
| 17 | 实测来源 | 边遍历 / 空 |
| 18 | 可达性 | 遍历账本到达与否 |
| 19 | 备注 | 组件 `notes`（含 no-op stub） |
| 20 | reach_path(树) | fact-tree `reach_path` |
| 21 | 点击路径 | 冷启动 → … → 点击路径 |
| 22 | 步数 | `depth` |
| 23 | 路径验证 | 全程安卓实走确认 / 源码推断 |
| 24 | 页面截图 | 遍历账本 screenshot 相对路径 |
| 25–34 | 步骤1..10 | 分步操作 |

另两个 sheet：**页面路径**（页面级账本）、**说明**（数据来源 / 生成方式 / 架构 / 口径 / 账号态 / 遍历统计）。
