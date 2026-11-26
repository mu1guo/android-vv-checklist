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

## 2. 为什么只有阶段 ① 是 LLM（原生三态都成立）

- 阶段 ① `android-fact-tree`（纯 Compose 时用 `compose-fact-tree` 子集）是语义推理：哪些 `@Composable`/Activity/Fragment 是 page/dialog、导航边从哪个 clickable/listener 发起、`stringResource`/`@string` 解析到真文案、View 控件带哪个 `android:id` + 监听器——**必须 LLM 读源码**。
- 阶段 ② `registry_from_tree` 是投影：fact-tree 已经把交互组件抽进 `pages[].components[]`（含 text / resource_id / navigation / source_anchor），宿主页天然已知。**把交互组件逐条抄成 registry / host_map / intents 是确定性操作**，没有新推理；唯一区别是按 `framework` 切换锚点（view 用 `resource_id`，compose 用文案）。
- 阶段 ③ merge 是把 host_map 精确挂回 fact-tree，同样是确定性映射（`feature_path → host_id`），框架无关。
- 阶段 ⑤ gen_func_list 是纯组装。

> 关键：**语义推理（哪些是页、锚点是什么、跳转到哪）全部压进阶段 ①**，无论 Compose 还是 View。View 的 resource-id / listener / `startActivity` / `nav_graph.xml` 解析同样由 LLM 在阶段 ① 完成并写进 fact-tree，阶段 ② 只需读 `resource_id` 字段做确定性投影。因此「只有阶段 ① 是 LLM」对三态都成立——v1 之所以只写了 Compose，是因为纯 Compose 没有 XML/resource-id，锚点塌缩成单一「文案」；v2 补上 `framework` + `resource_id` 后，同样的确定性旁路原样覆盖 View/hybrid。

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

## 4. View / hybrid 专属坑

1. **锚点 vs 显示名分离**：View 控件真机定位首选 `resource-id`（稳定、唯一），文案次之（多语言下会变）。但**功能点名 / 显示名永远用文案**——`resource_id` 是给自动化定位用的，`name` 是给人看的。阶段② 用 `raw_identifier`/`tap_by` 记锚点，`name` 记文案，两者不混。
2. **Adapter / ViewHolder 列表行**：`RecyclerView`/`ListView` 的 `itemView.setOnClickListener` 在 Adapter 里，`resource_id` 是行布局的 `@+id`，运行时逐行重复 N 次——按同构家族压缩为 1 条，`type:"RecyclerViewItem"/"ListViewItem"`，notes 标「数据驱动列表」。
3. **Fragment 是页不是组件**：`FragmentTransaction.replace(R.id.container, XFragment())` 里的 `R.id.container` 是容器，不是页；`to` = Fragment id，边的 `from` 在触发 Fragment 替换的 UI 处。单 Activity 多 Fragment 的 app，Activity 是壳页（`contains` 指向默认 Fragment），各 Fragment 独立成页。
4. **nav_graph.xml 导航**：Navigation Component 的 `navigate(R.id.action_a_to_b)` 必须回查 `res/navigation/*.xml` 的 `<action>`/`<fragment android:id>` 解析目的 Fragment，不能只记 `R.id.action_*` 字面量。
5. **@string 文案真值（View 版）**：`android:text="@string/x"` / `getString(R.string.x)` 同 Compose 一样要解析到 `strings.xml` 实际值（跨 `res/values*` 所有模块）；EditText 取 `android:hint`、ImageView 取 `android:contentDescription`。严禁用资源 key 名反推。
6. **hybrid 边界**：`ComposeView`（XML 内嵌）内部是 compose 组件、`AndroidView`/`AndroidViewBinding`（Compose 内嵌）内部是 view 组件。边界控件 framework 标**内层**、宿主页标**外层**——标反了会导致 view 组件的 `resource_id` 被漏掉。

## 5. 口径

- **功能点 = 交互组件**（`is_interactive=true`），逐条进 registry。
- **数据驱动列表**（列表项 / 枚举 / 设置项 / 图标网格）按同构家族压缩为 1 条（如 `RecipeItem#recipe_item` 一条代表整列食谱卡），不逐项膨胀。
- **账号态**：无账号体系（本地 mock）→ 写死；有账号 → 按 login/VIP 门控分 trip，见 `prompts/compose-fact-tree.md` 的 precondition 扫描。
- **英文评测**：清单文案与真机基线跑同一 locale；不做 app 内翻译。
