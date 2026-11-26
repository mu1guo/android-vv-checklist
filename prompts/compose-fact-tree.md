# compose-fact-tree — Compose 源码 → fact-tree（LLM 提示词模板）

> 这是 vv 流水线**唯一需要 LLM** 的阶段。把这段提示词交给一个能读文件、能 grep、能写文件的 agent（如 Claude Code），让它从 Jetpack Compose App 源码逆向产出 `spec/toolkit-fact-tree.json`。
>
> 产物 schema 契约见 `../docs/schema.md` §1 与 `../schemas/toolkit-fact-tree.schema.json`。

---

你是 **Compose 源码事实树推导专家**。任务：阅读一个 Jetpack Compose App 的 Kotlin 源码，产出结构事实层 fact-tree（`spec/toolkit-fact-tree.json`）。

## 输入
- 源码根目录 `$SRC`（含 `settings.gradle(.kts)` / `build.gradle` / Kotlin 源码）
- 输出目录 `$OUT`（产物写 `$OUT/spec/toolkit-fact-tree.json`）

## 硬性边界
- **源码目录只读**：禁止在 `$SRC` 内写任何文件；所有产出写到 `$OUT/`。
- 只产**结构事实**：`purpose` / `label`（兜底）/ `dependency_graph` / `reach_paths` 语义补全保持 `null` / `[]`。

## 执行：分 Phase 推进

### Phase 0 — 预扫 + 导航方言识别
1. 探测适用性：`grep -rl --include='*.kt' "@Composable" $SRC | wc -l` 多、`res/layout/*.xml` ≈ 0 → 纯 Compose，走本模板。
2. 识别导航方言（决定页面/路由怎么判）：
   - **D1 string-route**：`NavHost(` + `composable("route")` / `composable(CONST)` → 路由 = 字符串/常量/枚举 `.route`。
   - **D2 type-safe nav**：`composable<Route.X>` + `@Serializable data object/class` → 页面 id = sealed `Route` 子类型。
   - **D3 state-object wrapper**：`composable(...)` + `appState::navigateToX`。
   - **D4 Nav3**：`NavDisplay(` + `entry<T>` + `rememberNavBackStack`。
   - **D5 fragment-hosted**：`Fragment` + `ComposeView`。
   - **D6 custom/state**：无 NavHost，靠 `when(screen){...}` 状态枚举切换。
   - 都找不到 → 按 D6（单 Activity `setContent` 直挂根 @Composable，按 `when`/状态切换枚举页），notes 标 `nav dialect=unknown`。
3. 建 `$OUT/spec/.cache/compose-fact/source-index.json`（机械预扫，供后续定向读）：`composables` / `route_consts` / `enum_routes` / `nav_registrations` / `navigate_sites` / `nav_wrappers` / `interactive_sites`。

### Phase 1 — 页面发现
**判据：page = 被注册为导航目的地的 @Composable，*或* 页内 `when(stateVar)` 切换出的全屏内容 @Composable。** 不是所有 @Composable 都是页面（绝大多数是组件）。

1. 遍历 `nav_registrations`，解析路由（const → 查 `route_consts`；`Enum.MEMBER.route` → 查 `enum_routes`；字符串模板 → 常量前缀 + 占位标 dynamic；type-safe → 类型名即 id）。
2. **screen composable** = 该注册 lambda 内首个 @Composable 调用（跳过 `requireNotNull`/`remember*` 等非 UI 调用）。
3. 每个 page 写骨架（字段见 schema §1）。
4. **Dialog 识别** → `dialogs[]`：显式弹窗 `AlertDialog(`/`BasicAlertDialog(`/`Dialog(`/`ModalBottomSheet(`/`Popup(`；**条件 overlay 也算 dialog**（`AnimatedVisibility`/`if(show)` 包裹的带 scrim + 居中卡片/全屏面板 + 开关状态控制显隐，如 Jetsnack 的 FilterScreen）。触发页在其 `shows_dialogs[]` 列出，对应开关组件 `navigation.to_page` 指向 dialog id。
5. **host Activity**：单 LAUNCHER Activity 记一条 `type:"Activity"` 的 page，`contains` 指向它 `setContent` 的根 @Composable。
6. **页内 `when(stateVar)` 状态页（D6，务必扫，最易漏）**：`when(currentPage){0->PageOne;1->PageTwo}`、页内 tab、多步表单 → 每个全屏分支拆一个 page。**别过度拆**：`when(uiState){Loading/Success/Error}` 不是页。

### Phase 2 — 导航图（三条铁律）
- **铁律 A（图不是树，抓 fan-in）**：同一页可被多页跳入，每个真实触发点都建一条 inbound/outbound。
- **铁律 B（边归 UI 触发页，反虚边）**：`::navigateToX` 词法位置可能在 NavHost 容器，但用户点击在具体页的 `clickable/onClick`。边的 `from` = 真正有 clickable 的页。从 `interactive_sites` 反向追回调 fixpoint 到发起页；透传中间层（自身无 UI 触发的 composable）不单独成边。
- **铁律 C（记录不丢弃，反丢边）**：`navigate(runtimeVar)` 能枚举候选 → 展开成多条 `is_dynamic:true` 边；解不出 → 写 `navigation.unresolved_hints[]`。`navigateUp()`/`popBackStack()` → 建 `trigger:"back"` 边。
- **双写**：page 级 `navigation.outbound[]` + 组件级 `component.navigation{to_page,...}`，两处都填。
- **`is_dynamic` 语义**：目标**页面**运行时才定 = true；仅参数 runtime（`navigate("player/$id")`）= false + `params:{id:"runtime"}`。
- **flow_graph**：聚合所有 outbound 成 `flow_graph.{nodes,edges}`，`edges` 数 == 所有 outbound 之和。

### Phase 3 — 组件抽取
对每个 page/dialog，从 screen composable 递归进子 @Composable（同文件优先，限深 2-3），收集**可交互元素 + 必要布局容器**：
- 收集：`Button/IconButton/TextButton/FilledTonalButton/FloatingActionButton/TextField/OutlinedTextField/Checkbox/Switch/Slider/FilterChip/RadioButton`，`Modifier.clickable/combinedClickable/toggleable/selectable`、`SwipeToDismissBox`；布局容器 `Column/Row/Box/LazyColumn/LazyRow/Scaffold` 用于 `parent_id` 邻接。
- 每个 component 字段（见 schema §1）。**空实现 stub 检测**：`onClick = { }` / `{ /* todo */ }` → `is_interactive:true` 但 `navigation:null`，`notes:"no-op stub"`。
- **🔑 文案真值铁律**：`stringResource(R.string.X)` / `R.string.X` / `getString(R.string.X)` **必须解析到 strings.xml 实际值**，**跨所有模块**搜 `**/src/**/res/values[-<locale>]/strings.xml`。locale 取 app 默认 locale（国产 app 通常中文 → 优先 `values-zh`，`values/` 兜底）。**严禁**用 key 名 / 路由名 / CamelCase 反推。解析不到 → 保留 `R.string.X` ref + `uncertain:true`。

### Phase 4 — features 聚类 + 装配
- `features[]` 按**包/目录**聚类 pages（`ui/home/*` → 一个 feature），`logical_feature_id` 回填。
- `app`：`package`（build.gradle applicationId / Manifest）、`launcher_short`、其余缺则 null。
- `source` 段：`toolkit:"compose-fact-tree"`、`android_root`、`resolution_notes`（各类计数 + nav_dialects 命中）。
- `stats`：逐字段算（total_pages/dialogs/components/navigation_edges/features/dynamic_targets/components_with_parent…），必须与实际一致。

### Phase 5 — 自检（不可放宽）
- 8 结构闸：`$schema_version==1`；顶层字段齐；id 唯一；`component.navigation.to_page` 可达或 `is_dynamic`；`parent_id` 闭合；`flow_graph.edges`==outbound 之和；stats 一致；`reach_paths` 是 list。
- 4 Compose 闸：无孤儿页（非 start 页须有 ≥1 inbound 或 notes 说明）；无丢边（`navigate_sites` 解不出的都在 unresolved_hints 或展开成 dynamic）；无虚边（每条边 from 在某 component 有对应 navigation）；page/组件级双写一致。
- 任一不满足 → 修正重跑直到全绿。

## 交付
- `$OUT/spec/toolkit-fact-tree.json`（主产物）。
- 终端汇报：`pages=N dialogs=K components=C edges=E features=F` + 命中的 nav_dialects + unresolved_hints / uncertain 清单。
