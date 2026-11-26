# vv 方法论：source-first 功能清单

## 1. 为什么 source-first

两条产「安卓功能清单」的路：

| | source-first（本仓库） | device-first（HiTest 等） |
|---|---|---|
| 功能点来源 | 读源码：交互组件 + 导航边 + 数据驱动列表 | 真机盲遍历 + 运行时 UI dump 猜 |
| 覆盖边界 | 源码里有的都能列，含**不可达 / 条件弹窗 / no-op stub** | 只能列**恰好走到**的屏 |
| 对「数据驱动」 | 同构家族压缩为 1 条，一条不漏 | 依赖枚举值恰好被触发，易漏 |
| 对「条件自动弹窗」 | 源码可见，标注「遍历未触发」 | 根本看不到 |
| 成本 | 一次 LLM 源码分析 + 一次真机遍历 | 遍历要覆盖到才能发现，常需反复 |

Jetsnack 实测：vv source-first 清单 + `.kt` 补锚 喂 ECAT，优于 HiTest device-first——多修 1 个真 bug、省 37% token、0 幻影（见 `docs/` 外的迁移评测报告）。**结论：功能点的完备性由源码保证，设备只负责回填「可达性 / 实测结果 / 截图」。**

## 2. 为什么纯 Compose 只有阶段 ① 是 LLM

- 阶段 ① `compose-fact-tree` 是语义推理：哪些 `@Composable` 是 page/dialog、导航边从哪个 clickable 发起、`stringResource` 解析到真文案——**必须 LLM 读源码**。
- 阶段 ② `compose_registry_from_tree` 是投影：fact-tree 已经把交互组件抽进 `pages[].components[]`（含 text / navigation / source_anchor），宿主页天然已知。**把交互组件逐条抄成 registry / host_map / intents 是确定性操作**，没有新推理。
- 阶段 ③ merge 是把 host_map 精确挂回 fact-tree，同样是确定性映射（`feature_path → host_id`）。
- 阶段 ⑤ gen_func_list 是纯组装。

> 对比 XML/View 架构：XML 阶段 ② 的 registry 需要 LLM 读源码补 dialog/context_menu/代码级交互（无 XML 布局、无 resource-id 时）。**纯 Compose 没有 XML 布局、没有 resource-id，所以 registry 塌缩成确定性旁路。**本仓库面向纯 Compose（Cofi / Jetsnack 均为纯 Compose），故只保留这条旁路。

## 3. 关键坑（真实踩过）

1. **导航是图不是树**：同一页可被多页跳入（Feed/Search/Cart 都 → Detail）。每个真实触发点都建一条边，不因「目的地出现过」就少建。
2. **边归 UI 触发页，不归 wiring 注册点**：回调常被层层透传（`onSnackClick → onSnackSelected → ::navigateToDetail`）。边的 `from` = 真正有 `clickable/onClick` 的页，不是注册/透传点。用回调 fixpoint 追到发起页。
3. **解不出的运行时路由「记录」不「丢弃」**：`navigate(someVar)` 写进 `unresolved_hints` 或展开成 dynamic 边，绝不静默丢。
4. **页内 `when(stateVar)` 状态切换也是页**：引导/wizard/页内 tab/多步表单，每个全屏分支各拆一个 page。最易漏。
5. **`is_dynamic` 语义**：指「目标*页面*运行时才定」，不是「参数运行时才定」。`navigate("player/$id")` 目标页确定 → `is_dynamic:false`；`navigate(runtimeRouteVar)` → `true`。
6. **文案真值**：`stringResource(R.string.x)` 必须解析到 `strings.xml` 实际值，**跨所有模块**搜 `**/src/**/res/values*/strings.xml`（资源常在 `data`/`common`/`lib_*` 模块，不在 UI 模块）。严禁用 key 名 / CamelCase 反推。取 app 默认 locale（国产 app 通常中文）。
7. **no-op stub**：`onClick = { }` / `onClick = { /* todo */ }` → `is_interactive:true` 但 `navigation:null`，notes 标 `no-op stub`。设备遍历不应期待它跳转。
8. **空实现 vs 真跳转**：expected 判定（「点击后跳转到 X」vs「click 后触发对应行为」）必须从源码 handler 下钻，不按函数名字面猜。
9. **数据驱动列表内的同名泛化字段**：列表项卡片里同名字段（如「Name」「Save」）在 LLM 端会被追加 `(component_id)` 消歧为 `Name (step_name)`；这是 compose-fact-tree 阶段的语义判断（`enclosing_fn` 落在子 composable 里）。`compose_registry_from_tree.py` 的确定性投影只取 `text`/`content_desc` 裸文案，不追 `(id)` 后缀——因此 registry 名是裸「Name」。**影响仅限显示名，feature_path 与宿主映射仍唯一正确**（`Edit recipe>Name` 与 `Add recipe>Name` 靠层级路径区分）。已验证真实 Cofi：114/114 条结构与宿主映射一致，仅 4 条列表字段名差 `(id)` 后缀。

## 4. 口径

- **功能点 = 交互组件**（`is_interactive=true`），逐条进 registry。
- **数据驱动列表**（列表项 / 枚举 / 设置项 / 图标网格）按同构家族压缩为 1 条（如 `RecipeItem#recipe_item` 一条代表整列食谱卡），不逐项膨胀。
- **账号态**：无账号体系（本地 mock）→ 写死；有账号 → 按 login/VIP 门控分 trip，见 `prompts/compose-fact-tree.md` 的 precondition 扫描。
- **英文评测**：清单文案与真机基线跑同一 locale；不做 app 内翻译。
