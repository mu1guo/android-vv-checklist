# 中间产物字段契约

本仓库的确定性脚本只依赖 5 份 JSON（+ 1 份可选 config）。字段契约如下（`schemas/*.schema.json` 是机器可读版本）。

## 1. `spec/toolkit-fact-tree.json`（阶段 ① 产物，阶段 ② 输入）

顶层：`$schema_version`(int, 权威键 =1)、`source`、`app`、`features[]`、`pages[]`、`fragments[]`、`dialogs[]`、`flow_graph`、`stats`。

**page / dialog record**（`pages[]` + `fragments[]` + `dialogs[]`，字段形状相同）：

```jsonc
{
  "id": "RecipeList",                 // 唯一；type-safe 用 Route 子类型名
  "type": "Composable",               // Compose 用 "Composable"；View 用 "Activity"/"Fragment"/"Dialog"
  "screen_kind": "page",              // page | dialog | fragment | activity | activity_shell | nav_shell
  "framework": "compose",             // compose | view | hybrid（app/page/component 三级，缺省 compose）
  "label": "Recipe list",             // 人类可读（LLM 兜底可填，否则 null）
  "purpose": null,                    // 留给下游
  "android_file": "app/src/.../RecipeList.kt",
  "logical_feature_id": "compose.ui.details",   // 回填自 features[]
  "route": "recipe_list",             // Compose 扩展字段
  "is_start_destination": true,
  "contains": [], "shows_dialogs": ["RatioBottomSheet"],
  "components": [ /* 见下 */ ],
  "navigation": {"inbound": [], "outbound": [], "unresolved_hints": []},
  "reach_paths": [], "notes": null
}
```

**component**（`pages[].components[]`，阶段 ② 消费 `is_interactive` / `framework` / `text` / `content_desc` / `resource_id` / `type` / `id` / `navigation` / `source_anchor`）：

```jsonc
{
  "id": "recipe_settings_button",
  "type": "IconButton",
  "parent_id": null,
  "framework": "compose",             // compose | view（view 组件用 resource-id 锚点）
  "text": null,                       // 文案真值（compose: stringResource 解析 / view: android:text 或 @string 解析）
  "content_desc": "Settings",         // contentDescription 或 android:contentDescription
  "resource_id": null,                // View 控件 android:id 全名（如 com.example:id/btn_x）；Compose 为 null
  "click_handler": null,              // View 监听器方法名（如 onSettingsClick）；Compose 为 null
  "is_interactive": true,
  "triggers": ["click"],
  "navigation": {"to_page": "AppSettings", "trigger": "click", "params": null, "is_dynamic": false},
  "source_anchor": {"file": "app/src/.../RecipeList.kt", "line": 88},
  "notes": null
}
```

> View 方言下 `source_anchor.file` 优先指向挂监听器的 `.kt/.java`（无监听器时用 layout `.xml`）；`resource_id` = `{applicationId}:id/{x}`。

**navigation edge**（`navigation.outbound[]` / `flow_graph.edges[]`）：`{to, via_component, trigger, params, is_dynamic, source}`；`inbound[]` 是其反转 `{from, via_component, ...}`。

## 2. `spec/a2h/functional_registry.json`（阶段 ② 产物）

```jsonc
{"entries": [
  {"name": "Settings",                       // 交互组件文案（显示名，永远取人话文案）
   "depth": 2,
   "feature_path": "Recipe list>Settings",   // "页面label>name"，join 主键
   "source_file": "app/src/.../RecipeList.kt",
   "source_section": "compose_iconbutton",   // "compose_"/"view_" + type.lower()
   "raw_identifier": "Settings",             // 锚点：compose=文案；view=resource_id（如 com.example:id/btn_x）
   "anchor_type": "text",                    // "text" | "resource_id"
   "resource_id": null}                      // view 控件的 android:id 全名，compose 为 null
]}
```

## 3. `spec/a2h/compose_host_map.json`（阶段 ② 产物，阶段 ③ 输入）

`feature_path → 宿主映射`：

```jsonc
{"Recipe list>Settings": {
  "host_id": "RecipeList",                   // fact-tree page id
  "component_id": "recipe_settings_button",
  "tap_text": "Settings",                    // 真机点击锚点文案（view 无文案时兜底 resource_id 短名）
  "tap_by": "text",                          // "text"（compose）| "resource_id"（view 且有 resource_id）
  "anchor_type": "text",                     // 同 tap_by
  "resource_id": null,                       // view 控件的 android:id 全名，compose 为 null
  "code_anchor": "app/src/.../RecipeList.kt:88",
  "expected": "点击后跳转到 AppSettings 页面",  // 由 navigation.to_page 派生
  "to_page": "AppSettings",
  "precondition": null}}
```

## 4. `spec/a2h/test_intents.json`（阶段 ② 产物）

```jsonc
{"app_package_name": "com.omelan.cofi",
 "groups": {
   "independent": [{
     "feature_path": "Recipe list>Settings",
     "steps": ["在 Recipe list 页面点击「Settings」，预期结果：点击后跳转到 AppSettings 页面"],
     "expected_source": "inferred",
     "precondition_required": null}]}}
```

> `steps[]` 内嵌「预期结果：」是阶段 ⑤ 切 expected 判据的来源。

## 5. `android_traverse_screenshots/index.json`（阶段 ④ 产物，阶段 ⑤ 输入）

每屏一个 unit：

```jsonc
[{"page_id": "page_0001_RecipeList",   // 设备侧屏 id（可含 host_id 字段供自动映射）
  "host_id": "RecipeList",             // 可选：直接关联 fact-tree page，缺省走 config.device_map / label 匹配
  "label": "Recipe list",
  "timestamp": "2026-11-26T09:49:00+08:00",
  "screenshot": "page_0001_RecipeList/screenshot.png",
  "view_xml": "page_0001_RecipeList/view.xml",
  "clickable_count": 8}]
```

阶段 ⑤ 判断「可达」的规则（优先级）：① unit 带 `host_id` == 页面 id；② `config.device_map[host_id]` 命中某 unit 的 `page_id`；③ unit `label` 匹配 page `label`（大小写不敏感）。

## 6. `config.json`（可选，阶段 ⑤ 输入，app 特定信息）

```jsonc
{
  "app_name": "Cofi",
  "app_package": "com.omelan.cofi",
  "architecture": "纯 Compose（无 XML/resource-id）；控件锚点用文案，源码位置用 .kt 相对路径",
  "account_state": "无账号体系（本地 mock；预置 6 款默认食谱）",
  "traverse_notes": "20/23 屏实走；NotificationPermissionDialog 与 SupportCofiDialog 为条件自动弹窗，遍历未触发",
  "output_prefix": "Cofi_安卓功能清单",
  "device_map": {"MainActivity": "page_0001_RecipeList", "RecipeList": "page_0001_RecipeList", "RecipeDetails": "page_0002_RecipeDetails"}
}
```

缺省时：`app_name` 取 `fact-tree.app.label`；`device_map` 空（靠 `host_id` / label 匹配）；`output_prefix` = `<app_name>_安卓功能清单`。

## 7. xlsx 输出（34 列，阶段 ⑤ 产物）

三个 sheet：
- **功能清单**：序号 / 功能ID / 树内FP名 / 一级模块 / 功能路径 / 功能点 / 所在页面 / 页面用途 / 控件ID / 控件类型 / 账号状态 / 前置条件 / 操作 / 预期结果(源码推断) / 安卓实测结果 / 实测可信 / 实测来源 / 可达性 / 备注 / reach_path(树) / 点击路径 / 步数 / 路径验证 / 页面截图 / 步骤1…步骤10。
- **页面路径**：每 page/dialog 一行，可达性 + 点击路径 + 截图。
- **说明**：数据来源 / 生成方式 / 架构 / 口径 / 账号态 / 遍历。

ECAT 4 列 markdown（ID | 功能名 | 层级路径 | 源码位置）是这 34 列的瘦身投影，由 `gen_func_list.py --ecat` 直接产。
