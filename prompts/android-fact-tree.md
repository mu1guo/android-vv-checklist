# android-fact-tree — Android 源码 → fact-tree（LLM 提示词模板，多方言）

> 这是 vv 流水线**唯一需要 LLM** 的阶段。把这段提示词交给一个能读文件、能 grep、能写文件的 agent（如 Claude Code），让它从**任意原生 Android app** 源码逆向产出 `spec/toolkit-fact-tree.json`。
>
> 覆盖原生三态：**Compose** / **经典 View(XML)** / **混合（Compose↔View 互嵌）**。纯 Compose app 仍可用 `compose-fact-tree.md`（本模板的子集）。
>
> 产物 schema 契约见 `../docs/schema.md` §1 与 `../schemas/toolkit-fact-tree.schema.json`。

---

你是 **Android 源码事实树推导专家**。任务：阅读一个原生 Android app 的源码（Kotlin/Java + XML），产出结构事实层 fact-tree（`spec/toolkit-fact-tree.json`）。核心字段 `framework` 贯穿 `app` / `page` / `component` 三级，取值 `compose` | `view` | `hybrid`。

## 输入
- 源码根目录 `$SRC`（含 `settings.gradle(.kts)` / `build.gradle` / `AndroidManifest.xml` / Kotlin/Java 源码 / `res/`）
- 输出目录 `$OUT`（产物写 `$OUT/spec/toolkit-fact-tree.json`）

## 硬性边界
- **源码目录只读**：禁止在 `$SRC` 内写任何文件；所有产出写到 `$OUT/`。
- 只产**结构事实**：`purpose` / `label`（兜底）/ `dependency_graph` / `reach_paths` 语义补全保持 `null` / `[]`。

## 执行：分 Phase 推进

### Phase 0 — framework 检测（决定后续走哪套规则）
1. 机械预扫（可先跑 `src/detect_framework.py --app $SRC` 拿提示，但以你自己 grep 为准）：
   - **compose 信号**：`grep -rl '@Composable' --include='*.kt'`、`setContent`、`androidx.compose`。
   - **view 信号**：`res/layout/*.xml` 存在、`setContentView(`、`R.layout.`、`Activity`/`Fragment` 子类。
   - 二者并存 → **hybrid**；只有 compose → **compose**；只有 view → **view**。
2. 把结论写到 `app.framework`（compose/view/hybrid），并在 `source.resolution_notes` 记录命中信号与计数。
3. 建 `$OUT/spec/.cache/android-fact/source-index.json`（机械预扫，供后续定向读）：compose 侧记 `composables`/`route_consts`/`nav_registrations`/`interactive_sites`；view 侧记 `activities`/`fragments`/`layouts`/`view_ids`/`listener_sites`/`nav_graph`。

### Phase 1 — 页面发现（按 framework 分流）

**判据：page = 导航目的地（无论哪种 UI），或页内全屏状态分支。**

- **compose 方言**（沿用 compose-fact-tree）：
  1. 遍历导航注册，解析路由（D1 string-route / D2 type-safe nav / D3 state-object / D4 Nav3 / D5 fragment-hosted ComposeView / D6 custom `when(stateVar)`）。
  2. screen composable = 注册 lambda 内首个 @Composable 调用。
  3. Dialog → `dialogs[]`：`AlertDialog`/`Dialog`/`ModalBottomSheet`/`Popup`/条件 overlay（scrim + 居中卡片 + 开关控制显隐）。
  4. host Activity：单 LAUNCHER Activity 记 `type:"Activity"` 的 page，`contains` 指向 setContent 的根 @Composable。
  5. 页内 `when(stateVar)` 状态页：每个全屏分支拆一个 page；`when(uiState){Loading/Success/Error}` 不是页。

- **view 方言**：
  1. **Activity 页**：`AndroidManifest.xml` 里带 `MAIN`/`LAUNCHER` intent-filter 的是 start Activity；其余被 `startActivity(Intent(...))` 触达的 Activity 也各记一页。`type:"Activity"`、`framework:"view"`、`android_file` 指向 `.kt/.java`、`screen_kind:"activity"`。
  2. **Fragment 页**：`class XFragment : Fragment`（或 extends）且被 `FragmentTransaction`/`nav_graph.xml` 挂载的全屏 Fragment，各记一页。`type:"Fragment"`、`screen_kind:"fragment"`、`android_file` 指向 fragment 源文件，layout 记在 `layout_file`（若 schema 允许，否则放 notes）。
  3. **Dialog 页** → `dialogs[]`：`Dialog`/`AlertDialog` 子类、`DialogFragment`、XML 里 `<dialog>` 布局；`type:"Dialog"`、`framework:"view"`。
  4. 单 Activity 多 Fragment 的 app：Activity 是壳页（`contains` 指向其默认 Fragment），各 Fragment 是独立页。

### Phase 2 — 导航图（三条铁律 + view 导航）

- **铁律 A（图不是树，抓 fan-in）**：同一页可被多页跳入，每个真实触发点都建一条 inbound/outbound。
- **铁律 B（边归 UI 触发点，反虚边）**：边的 `from` = 真正有点击/监听的页，不是注册/透传点。compose 侧从 `interactive_sites` 反向追回调 fixpoint；view 侧从 `listener_sites` 追 `findViewById(...).setOnClickListener` 所在的方法。
- **铁律 C（记录不丢弃，反丢边）**：解不出的运行时跳转 → 展开 `is_dynamic:true` 边或写 `navigation.unresolved_hints[]`；`finish()`/`onBackPressed`/`navigateUp()`/`popBackStack()` → `trigger:"back"` 边。
- **双写**：page 级 `navigation.outbound[]` + 组件级 `component.navigation{to_page,...}`，两处都填。
- **view 导航识别**：
  - `startActivity(Intent(this, XActivity::class.java))` / `Intent(context, X::class.java)` → 边 to X，`source:"view_nav"`。
  - `Navigation.findNavController(v).navigate(R.id.action_a_to_b)` → 查 `res/navigation/nav_graph.xml` 的 `<action>`/`<fragment android:id>` 解析目的 Fragment。
  - `supportFragmentManager.beginTransaction().replace(R.id.container, XFragment())` → 边 to X。
- **`is_dynamic` 语义**：目标**页面**运行时才定 = true；仅参数 runtime（`navigate("player/$id")`、`startActivity(intent with runtime class)`）= false + `params:{id:"runtime"}`。
- **flow_graph**：聚合所有 outbound 成 `flow_graph.{nodes,edges}`，`edges` 数 == 所有 outbound 之和。

### Phase 3 — 组件抽取

对每个 page/dialog，收集**可交互元素 + 必要布局容器**（用于 `parent_id` 邻接）。

- **compose 方言**（沿用）：
  - 收集：`Button/IconButton/TextButton/FilledTonalButton/FloatingActionButton/TextField/OutlinedTextField/Checkbox/Switch/Slider/FilterChip/RadioButton`，`Modifier.clickable/combinedClickable/toggleable/selectable`、`SwipeToDismissBox`；容器 `Column/Row/Box/LazyColumn/LazyRow/Scaffold`。
  - 空实现 stub：`onClick = { }` / `{ /* todo */ }` → `is_interactive:true` 但 `navigation:null`，`notes:"no-op stub"`。
  - **🔑 文案真值铁律**：`stringResource(R.string.X)` / `getString(R.string.X)` 必须解析到 `strings.xml` 实际值，**跨所有模块**搜 `**/src/**/res/values[-<locale>]/strings.xml`，locale 取 app 默认。严禁用 key 名 / CamelCase 反推。解析不到 → 保留 `R.string.X` ref + `uncertain:true`。

- **view 方言**（关键差异：锚点 = resource-id）：
  1. 对每个 layout（`res/layout/*.xml`），扫带 `android:id="@+id/x"` 的控件：`Button/TextView/EditText/CheckBox/Switch/RadioButton/ImageView/ImageButton/Spinner/SeekBar`，以及 `android:clickable="true"` 的容器。
  2. **`is_interactive=true` 判据**：该 id 在 Activity/Fragment 里被 `findViewById(R.id.x).setOnClickListener/setOnItemClickListener/setOnCheckedChangeListener/setOnClickListener` 挂监听，**或** XML `android:onClick="method"`，**或** `android:clickable="true"`。
  3. **字段**：
     - `resource_id` = `{applicationId}:id/{x}`（applicationId 从 `build.gradle` / Manifest 取）。
     - `text` = `android:text` 字面量，或 `@string/x` **解析后的真值**（同铁律）；EditText 用 `android:hint`；ImageView 用 `android:contentDescription`。
     - `click_handler` = 监听器方法名（如 `onSubmitClick`）。
     - `framework:"view"`；`type` = 控件名（Button/EditText/CheckBox…）。
     - `source_anchor.file` = 挂监听的 `.kt/.java` 文件（无监听器时用 layout `.xml`），`line` = `findViewById` 行或 XML 该控件行。
     - `navigation`：从 handler 下钻 `startActivity`/`navigate`/`FragmentTransaction`，同 Phase 2。
  4. **列表/Adapter**：`RecyclerView`/`ListView` + Adapter 按同构家族压缩：`itemView` 里带 `setOnClickListener` 的整行记 1 条（`type:"RecyclerViewItem"`/`ListViewItem`），notes 标「数据驱动列表，同构家族压缩」。
  5. **no-op**：`findViewById` 后无监听、无 `android:onClick`、无 `clickable` → 不列（或 `is_interactive:false`）。

- **hybrid 方言**：
  - `ComposeView`（XML 内嵌）：宿主页 framework 记 view；ComposeView 内部的 composable 组件各自 `framework:"compose"`，仍挂在该宿主页下。
  - `AndroidView`/`AndroidViewBinding`（Compose 内嵌）：宿主页 framework 记 compose；内嵌 View 组件各自 `framework:"view"`，带 `resource_id`（若有）。
  - 两侧都按各自规则建边；边界控件本身（ComposeView/AndroidView）也记一条组件，`framework` 匹配**内层**内容、宿主页匹配**外层**。

### Phase 4 — features 聚类 + 装配
- `features[]` 按**包/目录**聚类 pages（compose：`ui/home/*`；view：`ui/home/` 或按 feature 包），`logical_feature_id` 回填。
- `app`：`package`（applicationId）、`framework`、`launcher_activity`/`launcher_short`（Manifest），其余缺则 null。
- `source` 段：`toolkit:"android-fact-tree"`、`android_root`、`resolution_notes`（各类计数 + framework 信号 + nav 方言命中）。
- `stats`：逐字段算（total_pages/fragments/dialogs/components/navigation_edges/features/dynamic_targets/components_with_parent），必须与实际一致。

### Phase 5 — 自检（不可放宽）
- **8 结构闸**：`$schema_version==1`；顶层字段齐；id 唯一；`component.navigation.to_page` 可达或 `is_dynamic`；`parent_id` 闭合；`flow_graph.edges`==outbound 之和；stats 一致；`reach_paths` 是 list。
- **compose 闸**：无孤儿页；无丢边（`navigate_sites` 解不出的都在 unresolved_hints 或展开 dynamic）；无虚边（每条边 from 在某 component 有对应 navigation）；page/组件级双写一致。
- **view 闸**：每个 `resource_id` 在页内唯一（重复则 notes 说明，如 Adapter 复用行）；`text` 都解析过 `@string`（无 `@string/` 字面残留）；每条 outbound 边能对应一个 handler；非 start Activity/Fragment 有 ≥1 inbound 或 notes 说明（如 deep-link/后台广播唤起）。
- **hybrid 闸**：ComposeView/AndroidView 边界两侧组件 framework 标记正确，无「view 组件当 compose」或反之。
- 任一不满足 → 修正重跑直到全绿。

## 交付
- `$OUT/spec/toolkit-fact-tree.json`（主产物）。
- 终端汇报：`framework=X pages=N fragments=F dialogs=K components=C edges=E features=F` + 命中信号/方言 + unresolved_hints / uncertain 清单。
