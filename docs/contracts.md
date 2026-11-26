# 真实 vv 中间产物契约

真实方法在 `spec/` 与 `android_traverse_screenshots/` 下流转 4 份关键 JSON + 1 份账本。本文只记**真实方法特有的字段**；`main`/`v2` 的 `docs/schema.md` 记的是简化版契约（缺双 oracle）。

---

## 1. `spec/toolkit-fact-tree.json`（UI 树，三态同构）

`android-fact-tree` 的产出，三条架构路（纯 XML / 纯 Compose / 混合）产出的树**字段同构**，`arkts-visual-verify` 零改消费。

- `pages[]` / `dialogs[]`（真实版还有 `fragments[]`）：每条 record 有 `id` / `type` / `label` / `purpose` / `inbound_triggers[]` / `navigation_contract` / `reach_path(s)` / `components[]` / `flow_graph`。
- `components[]`：交互组件（`is_interactive=true`），含 `text` / `content_desc` /（View）`resource_id` / `navigation` / `behaviors[file:line]`。
- `features[]`：一级模块聚类。
- hybrid 额外：节点带 `arch:"xml"|"compose"`，跨架构边已缝进 `flow_graph`。

> 三态锚点策略：Compose 用文案（text/contentDesc），View 用 `resource-id`；`name` 永远取人话文案。

---

## 2. `spec/a2h/functional_registry.json`（功能点枚举）

`a2h-functional-registry` 的产出。`entries[]` 每条功能点：

```jsonc
{
  "name": "售后中心",                 // 功能点名（人话文案）
  "depth": 3,
  "feature_path": "我的>设置>售后中心", // 层级路径（叶名 = merge 主键）
  "source_file": "app/.../activity_mine_setting.xml",  // 声明处
  "source_section": "context_menu",   // 控件类型 → fixer 选修复模式
  "raw_identifier": "com.pkg:id/btn_xxx",  // XML：真 resource-id；代码交互：代码锚点
  "action": "...",
  "expected": "...",                  // 预期结果
  "expected_source": "spec_acceptance|spec_nav|inferred",
  "group": "independent|setup|dependent|blocked",
  "precondition": "...",
  "domain": "我的"
}
```

三条 join / 定位命门（脚本强保证）：
1. `registry.name` == `intent.feature_path` 叶名（merge 主键）
2. `intent.steps` 含「预期结果：」（merge `split_expected` 切 `expected_llm`）
3. XML 控件 `raw_identifier` = 真 resource-id（grounding `uiautomator dump` 定位）

纯 Compose 走 `compose_registry_from_tree.py` 投影时，`raw_identifier` 塌缩为文案/`code_anchor`，另产 `compose_host_map.json`（`feature_path → {host_id, component_id, tap_text, expected}`）供 merge 精确映射。

---

## 3. `spec/a2h/test_intents.json`（测试意图 + 预期判据）

`build_intents.py` 从同一 `functional_points.json` 投影（与 registry 同源 → join 天然对齐）。`groups[].steps[]` 内嵌「预期结果：…」，merge 据此切 `expected_llm`。

---

## 4. `functional_checks[]`（注入进 fact-tree 的双 oracle，**核心**）

`a2h-functional-merge` 注入到 page record 顶层。完整结构：

```jsonc
"functional_checks": [{
  "fp_id": "FP_售后中心",
  "name": "售后中心",
  "feature_path": "我的>设置>售后中心",        // join 溯源

  // —— 双 oracle：LLM 种子（保底）+ 安卓实测（主）——
  "expected_llm": "跳转至售后中心页面",         // ← test_intents 切出（LLM 静态分析种子）
  "expected_llm_missing": false,               // 没 join 到则 true
  "expected_android": null,                    // ← grounding 安卓实测填（主 oracle）；未跑为 null
  "android_trusted": null,                     // ← grounding 用独立结构指纹判 expected_android 可信度

  "android_anchor": {
    "decl_file": "app/.../activity_mine_setting.xml", // ← registry.source_file（声明处）
    "impl_file": null,                         // ← Phase 3 枚举精修补的入口宿主页（非枚举为 null）
    "raw_identifier": "..."                    // ← 精确符号锚 / type 判别
  },
  "type_discriminator": null,    // 通用宿主页（承载多工具）时填枚举值
  "confidence": "high",          // 映射置信（high/medium/low）
  "mapping_method": "layout字段",
  "source": "a2h_functional_merge",

  // —— Q2 透传（源码侧额外信息，上游缺则 null）——
  "source_section": "context_menu",        // → grounding 选 tap/longtap/drag；fixer 选修复模式
  "precondition_required": "队列非空且未锁定", // → grounding step0 据此造态
  "expected_source": "spec_acceptance"     // 判据溯源 → trust 信号（acceptance > nav > inferred）
}]
```

### 双 oracle 的语义（别搞错）

`expected_android`（安卓实测）和 `expected_llm`（LLM 猜）是**「修正者 vs 被修正者」**，不是「两个投票者」：

- **不用「两者一致」当置信**（那是范畴错误，会把 grounding 成功纠错误降级）。
- 用**独立结构指纹**判 `expected_android` 自身可信度 → 写 `android_trusted`。

| `android_trusted` | 下游判定 |
|---|---|
| `true` | 鸿蒙 H 匹配 `expected_android` → PASS；不匹配 → FAIL |
| `false` | 退回 `expected_llm` 弱判 + `low_confidence` |

### 顶层兜底

- `unmapped_functional_points[]`：挂不上页面的功能点（带 `unmapped_reason`），绝不静默丢弃。
- `stats.a2h_functional_merge`：功能点总数 / mapped（按置信分档）/ unmapped 及原因 / 挂上但缺预期数 / 承接页面数 / 枚举精修数。

---

## 5. `android_traverse_screenshots/index.json`（安卓边遍历账本）

`arkts-visual-verify` 安卓趟的产出，逐屏：

```jsonc
[{ "page_id": "page_0001_RecipeList", "label": "...", "screenshot": "..." }]
```

`gen_func_list.py` 用它回填「可达性 / 安卓实测结果 / 实测可信 / 实测来源 / 页面截图」。
