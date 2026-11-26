# 真实 vv 功能清单流水线（天佑版）

本文忠实记录真实生产环境的 vv 功能清单生成方法。核心是一个 **skill 编排**：`android-fact-tree`（统一入口 + 判架构分发）→ `a2h-functional-registry`（功能点契约）→ `a2h-functional-merge`（双 oracle 注入）→ `arkts-visual-verify`（设备遍历 + grounding）→ `gen_func_list.py`（组装 Excel）。

与 `main`/`v2` 的「source-first 确定性脚本流水线」差异见 `docs/diff-from-v1v2.md`。

---

## 0. 全景

```
Android 源码（纯 XML / 纯 Compose / 混合）
        │  ① android-fact-tree（编排器，不是生成器）
        │     dispatch.py plan 判架构 → 分发到三态生成器 → dispatch.py gate 校验
        ▼
spec/toolkit-fact-tree.json              （三态字段同构的 UI 树：pages/dialogs/components/flow_graph）
        │  ② a2h-functional-registry（功能点契约）
        │     ├─ XML/混合：LLM 读全源码 + census/确定性地板 → functional_registry.json + test_intents.json
        │     └─ 纯 Compose：compose_registry_from_tree.py（确定性投影，锚点=文案）
        ▼
spec/a2h/functional_registry.json        （功能点枚举 + 源码锚点）
spec/a2h/test_intents.json               （测试意图 + 「预期结果」判据）
        │  ③ a2h-functional-merge（注入 functional_checks[]）
        │     ├─ XML/混合：map_registry_to_facttree.py + merge_functional_into_facttree.py（+ 枚举 LLM 精修）
        │     └─ 纯 Compose：compose_merge_into_facttree.py（compose_host_map 精确映射）
        ▼
spec/toolkit-fact-tree.json + functional_checks[]（双 oracle 种子：expected_llm + expected_android 占位）
        │  ④ arkts-visual-verify（设备遍历 + grounding，核心差异）
        │     安卓趟：边遍历真实点击 → UI 树 dump + 截图 → index.json
        │     Phase 0.5 grounding：逐 check 安卓实操 → 填 expected_android / android_trusted / precondition
        │     （可选）鸿蒙趟：逐 check 鸿蒙实测 → 按 android_trusted 判 PASS/FAIL → 写 fix 单
        ▼
android_traverse_screenshots/index.json  （逐屏到达账本 + 截图）
        │  ⑤ gen_func_list.py（确定性组装）
        ▼
<app>_安卓功能清单_YYYYMMDD_HHMMSS.xlsx  （34 列：功能清单 / 页面路径 / 说明 三 sheet）
```

---

## ① android-fact-tree —— 统一入口 + 判架构分发

**它自己不解源码成节点**，只做四件事：判架构、分发、校验、接续功能注入。

### 判架构（确定性，永远先跑）

```bash
python3 scripts/dispatch.py plan <android_source_root>
```

内部 `detect_arch.py` 确定性扫：`@Composable` 密度 / `setContentView(R.layout.*)` 宿主数 / Activity 数 / navigation-compose 依赖 / `ComposeView` / xml layout 数 + manifest 的 launcher 宿主 → 输出**三态判定 + 走哪条路**。

> 判据核心：真·XML 屏 = `setContentView(R.layout.*)` 的 Activity；孤立 `ComposeView` / appwidget 等非屏 layout **不**使纯 Compose 误判为 hybrid。

### 三态分发

| 架构 | 生成器 |
|---|---|
| pure_traditional（纯 XML） | `toolkit-fact-indexer`（确定性结构树）+ `app-relationship-tree`（LLM 富化：purpose / inbound_triggers / navigation_contract / reach_paths） |
| pure_compose（纯 Compose） | `compose-fact-tree`（Phase 0–7，Phase 7 `enrich_parity.py` 产出与传统树同构的富化字段） |
| hybrid（混合） | **XML 先**（2A 产基础树，节点打 `arch:"xml"`）→ **Compose 补充式叠加**（supplement 模式，新节点打 `arch:"compose"`，按 `fq_class` 去重）→ **缝合跨架构边**（`startActivity(XmlActivity)` / `ComposeView.setContent{XScreen()}` 补边） |

> hybrid 顺序不可换：XML 先于 Compose，正因 XML 节点先存在，Compose→XML 边才解析得出；反过来退化成两座孤岛。

### 确定性校验（三条路都跑，任一红不得交付）

```bash
python3 scripts/dispatch.py gate <spec/toolkit-fact-tree.json> <android_source_root>
```

1. **产出契约闸** = 复用 `arkts-visual-verify/scripts/check_prereq_freshness.py`（visual-verify 自己认的那把尺）：navigation_contract≥80% / reach≥50% / uncertain≤30%。不达标直接输出 `NEED:<对应生成器>` 告诉你该补跑谁。
2. **连通闸**（仅 hybrid）：从 launcher BFS 走全图，跨架构断裂 = 接缝边没缝上。
3. **功能维度闸**（A2H 项目）：`REG>0 且 N==0` → FAIL（registry 有功能点但树里 0 个 functional_check = merge 没注进去）。

### 接续 a2h-functional-merge（§3.5）

树就绪后，检测 `spec/a2h/functional_registry.json` 是否存在 → 存在则按架构自动接续功能注入；缺失则**先自产**（②），再 merge（③）。

---

## ② a2h-functional-registry —— 功能点契约

产出 `functional_registry.json`（控件级功能点枚举 + 锚点）与 `test_intents.json`（含「预期结果」判据），落契约路径 `<hmos_project>/spec/a2h/`。

### 核心定位（纠偏点 ①）

> **LLM 读完整源码 = 主提取器**（决定有哪些功能点）；**control_census（XML + 代码扫描）= 确定性地板 + 省 token 素材，不是上限**。早期把 census 当主干、LLM 当贴标签的 → 系统性漏掉 ~26% 代码级交互。

- 纯 XML/混合：`S0–S6` 主流程（LLM 为主）。锚点 = **真 resource-id**（XML 控件抄 census 真 id；代码交互用 census 代码锚点）。
- 纯 Compose：**旁路脚本** `compose_registry_from_tree.py`（确定性投影，锚点 = 文案 text + code_anchor），因 compose-fact-tree 已把交互组件抽进树的 `components`、宿主页天然已知（join 已完成）。

### XML/混合的 S0–S6（LLM 为主）

```
S0 🤖 确认输入（$SRC/$HM/$PKG/$BASE）
S1 ⚙️ source_index + strings_catalog + arrays_catalog + control_census + ★deterministic_floor（无遗漏叶子地板）
S2 ⚙️ spec_oracle（expected 升级源，可选）
S3 🤖 ★地板喂 LLM 深读（补语义 + 补代码层 + 枚举收口）→ 唯一手写文件 functional_points.json
S3b ⚙️ reconcile（地板 ⊕ LLM 双向对账）→ 🤖 核 floor_only / llm_only
S4 ⚙️ project_registry + build_intents（确定性投影）
S5a ⚙️ validate_contract（契约 + 完备性 + join 自检）→ 🤖 修
S5b ⚙️ spec_crosscheck（源码 × spec 双向交叉校验）→ 🤖 逐条裁决
S6 🤖 完成 → 交下游
```

**关键机制**：
- **确定性地板**（`det_floor.json`：menu + preference + ListPreference 枚举 + Java 枚举类）召回 ~79%；**LLM 深读**召回 ~75%；**并集 ~90%**。互补：地板救 LLM 的随机漏（资源项），LLM 救地板的代码盲区（dialog / custom / 手势 / WebView 桥接点）。
- **WebView 桥接点必入册**：grep `@JavascriptInterface` / `onShowFileChooser` / `setDownloadListener` / `shouldOverrideUrlLoading`，每个桥方法一条功能点（anchor = 桥方法，expected = 原生侧反应）。
- **expected 优先级**：`spec_acceptance`（命中 features 验收标准）> `spec_nav`（命中 page 导航关系）> `inferred`（读源码 handler 推断）。inferred 时**必须下钻 handler 函数体**，不按函数名字面猜。
- **改产物的唯一合法路径**：改 `functional_points.json` → 重跑 S4 投影 → 重跑 S5 校验。`functional_registry.json` / `test_intents.json` 永远由脚本投影，禁止 LLM 手改。

---

## ③ a2h-functional-merge —— 注入双 oracle 种子

**只新增字段，不改** toolkit/art 已填的导航与结构。把功能维度注入 fact-tree：

| A2H 独特产物 | fact-tree 为何缺 |
|---|---|
| ① 功能点枚举（`name`） | enum 驱动工具运行时拼出，不在任何 layout |
| ② 预期结果判据（`test_intents.steps` 切「预期」） | fact-tree 只有 `purpose`，没有「什么算对」的 oracle |
| ③ 功能点 → 源码锚点（`source_file`/`raw_identifier`） | fact-tree 页面级文件路径稀疏 |

### 注入 schema（见 `docs/contracts.md` 完整契约）

每条 `functional_check` 带**双 oracle 种子**：

```jsonc
{
  "fp_id": "FP_售后中心",
  "name": "售后中心",
  "feature_path": "我的>设置>售后中心",
  "expected_llm": "跳转至售后中心页面",   // ← LLM 静态分析种子（保底）
  "expected_llm_missing": false,
  "expected_android": null,               // ← grounding 安卓实测填（主 oracle）；未跑为 null
  "android_trusted": null,                // ← grounding 用独立结构指纹判 expected_android 可信度
  "android_anchor": { "decl_file": "...", "impl_file": null, "raw_identifier": "..." }
}
```

### 映射策略

- **XML/混合**：`map_registry_to_facttree.py`（三路确定性：类名直命中 / layout 文件名 / 枚举分发 / kt 文件名，覆盖 ~82%）→ `merge_functional_into_facttree.py`（join 预期 + 注入 + 自检）→ **Phase 3 枚举 LLM 精修**（只对低置信枚举功能点派 sub-agent，定位分发中枢 `when(type){…}` 背后的真入口宿主页）。
- **纯 Compose**：`compose_merge_into_facttree.py` 读 `compose_host_map.json` 做**精确映射**（无 grep / 无模糊 join），注入的 check 带 `tap_by=text` / `tap_text` / `code_anchor`。
- **镜像功能点默认跳过**（`is_mirror=true`，跨引用副本，同一 raw_identifier 在主页面已有 check）。
- **挂不上的**（参数原子 / 无对应 record）→ 进顶层 `unmapped_functional_points[]`，带 `unmapped_reason`，绝不静默丢弃。
- **归属以 `android_anchor.decl_file` 为准**（源码真值），不是名字匹配；裸名兜底是「6 个弹窗都有『关闭』全倒进同一节点」串台之源。

---

## ④ arkts-visual-verify —— 设备遍历 + grounding（核心差异）

真实方法的功能清单生成**依赖真机边遍历**（不是 `am start` 盲起），且**把「安卓实测」做成主 oracle**。

### 安卓趟：边遍历 + 账本

- 从 fact-tree 的 launcher 出发做 **BFS 边遍历**（edge-walk），逐页真实点击；每页 dump UI 树 + 截图，写 `android_traverse_screenshots/index.json`（逐屏到达账本）。
- 这一步就是「真实 vv 功能清单」的**可达性 / 截图 / 实测来源**来源。

### Phase 0.5 grounding：填双 oracle 的真值

导航到页后，**逐 functional_check 在安卓实操功能 + 观察 + 结构指纹自验**，回填：

- `expected_android` = 安卓实测真值（**主判据**）
- `android_trusted` = 指纹判「安卓落点是否可信」（independent 于 expected_llm，对照 fact-tree 该功能点该去的 record 结构；没真到达就标 `false`，不瞎写）
- `precondition` = 测试登录态

> 指纹独立于 `expected_llm`：挡误触 / 没点中。这是「修正者 vs 被修正者」，不是「两个投票者」——所以**不用「两者一致」当置信**，而是用独立结构指纹判 `expected_android` 自身可信度。

### 下游判定（鸿蒙趟，A2H 迁移项目用）

| `android_trusted` | 判定 |
|---|---|
| **true** | 鸿蒙实测 H 匹配 `expected_android` → PASS；不匹配 → **FAIL**（安卓可信真值，鸿蒙不符 = 真退化） |
| **false** | 退回 `expected_llm` 弱判 + 标 `low_confidence` |

> **纯功能清单生成场景**（用户的实际用法）：「用 arkts-visual-verify 遍历安卓应用，**不跑鸿蒙**」——即只跑安卓趟 + grounding，产出账本 + 回填实测结果，然后交给 ⑤ 组装 Excel。鸿蒙趟只在 A2H 迁移一致性别验证时才跑。

---

## ⑤ gen_func_list.py —— 组装 Excel

确定性脚本，消费三样输入：

1. `spec/toolkit-fact-tree.json`（UI 树，含 `functional_checks[]`）
2. `spec/a2h/functional_registry.json` + `compose_host_map.json` + `test_intents.json`（功能树）
3. `android_traverse_screenshots/index.json`（安卓边遍历账本）

产 **34 列 xlsx**（功能清单 / 页面路径 / 说明 三 sheet），关键列：

| 列 | 来源 |
|---|---|
| 功能ID / 树内FP名 / 一级模块 / 功能路径 / 功能点 | 功能树（registry） |
| 所在页面 / 页面用途 / 控件ID / 控件类型 | UI 树（fact-tree）+ 功能树映射 |
| 前置条件 / 操作 / 预期结果(源码推断) | intents（`预期结果：` 切出） |
| **安卓实测结果 / 实测可信 / 实测来源 / 可达性** | **grounding 回填的 `expected_android` + 遍历账本** |
| reach_path(树) / 点击路径 / 步数 / 路径验证 / 页面截图 / 步骤1..10 | 树 + 账本 |

真实实例（Cofi 纯 Compose）见 `reference/gen_func_list.py`。该脚本的 `DEVICE_MAP`（host 页 → 设备 page_id）是 app 特定硬编码，不同 app 需改写；`INTENT_EXPECT` 从 `test_intents.json` 的 `预期结果：` 切出 `expected` 列，是「预期结果(源码推断)」列的判据来源。
