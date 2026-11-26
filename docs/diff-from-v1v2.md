# 与 `main` / `v2` 的差异：真实方法纠正了我此前的两处理解

`main`（v1，纯 Compose）和 `v2`（原生三态）是我手写的一版 **source-first 确定性脚本流水线**，核心卖点是「只有阶段①是 LLM，其余全确定性」。真实生产方法（skill 编排）在两条关键点上推翻了这个卖点。

---

## 纠正 ①：「只有阶段①是 LLM」只对纯 Compose 成立

### 我此前的说法（错在哪）

> v1/v2：`android-fact-tree` 是唯一 LLM 阶段；阶段② `registry_from_tree` 是「把交互组件逐条抄成 registry 的确定性投影」。

### 真实情况

功能点注册表（阶段②）按架构分流，**XML/混合这条链本身也是 LLM**：

| 架构 | 功能注册表怎么产 | LLM? |
|---|---|---|
| 纯 Compose | `compose_registry_from_tree.py` 确定性投影（compose-fact-tree 已抽组件、join 天然完成） | ❌ 否 |
| 纯 XML | `a2h-functional-registry` S0–S6：**LLM 读全源码 + census/确定性地板**，锚点 = 真 resource-id | ✅ **是** |
| 混合 | 同上（XML 半边 LLM，Compose 半边投影） | ✅ **是** |

所以真实方法的 LLM 阶段是 **2 个**：① fact-tree 产树（三态生成器）+ ② XML/混合的功能注册表（`a2h-functional-registry` 的 LLM 主提取）。「只有阶段①是 LLM」这个结论是我从**纯 Compose 的 Cofi 实例**上归纳出来的，不能推广到 XML/混合。

### 为什么 XML 的注册表必须 LLM

`a2h-functional-registry` 的流程铁律写得很清楚：

> **LLM 读完整源码（.java/.kt + xml）= 主提取器**——决定有哪些功能点。**control_census（XML+代码扫描）= 确定性地板 + 省 token 素材，不是上限**。早期把 census 当主干、LLM 当贴标签的 → 系统性漏掉 ~26% 代码级交互。

- 确定性地板（`det_floor.json`：menu + preference + ListPreference + Java 枚举）召回 ~79%；
- LLM 深读补代码级交互（dialog / custom_view 手势 / setOnClickListener / BottomSheet / WebView 桥接点）召回 ~75%；
- **并集 ~90%**。地板救 LLM 的随机漏，LLM 救地板的代码盲区——两者是互补，不是「LLM 只管贴标签」。

而我的 `v2` 的 `registry_from_tree.py` 是**纯确定性投影**，它假设「fact-tree 已经把所有交互组件抽进 `components[]`、宿主页静态已知」。这对纯 Compose 成立（compose-fact-tree 就是干这个的），但对 XML/混合**不成立**：XML 的 `resource-id`、`setOnClickListener`、代码级交互（dialog/context_menu）需要 LLM 读源码才能凑齐，确定性脚本投影会漏掉这 ~26%。

---

## 纠正 ②：设备遍历被低估了——真实方法有「grounding」，把安卓实测当主 oracle

### 我此前的做法（缺了什么）

> v1/v2：阶段④ 设备遍历只回填「可达性 / 截图 / 实测来源」；`functional_checks[]` 里的 `expected_android` / `android_trusted` 字段**留成 `null`**，判定只靠 `expected_llm`。

### 真实情况

`arkts-visual-verify` 有 **Phase 0.5 grounding**：安卓趟遍历到页后，**逐 functional_check 在真机实操 + 观察 + 独立结构指纹自验**，回填：

- `expected_android` = 安卓实测真值（**主判据**）
- `android_trusted` = 指纹判「安卓落点是否可信」（独立于 `expected_llm`，对照 fact-tree 该功能点该去的 record 结构；没真到达就标 `false`，不瞎写）
- `precondition` = 测试登录态

下游（鸿蒙趟 / 功能判定）按 `android_trusted` 分流：

| `android_trusted` | 判定 |
|---|---|
| `true` | 实测 H 匹配 `expected_android` → PASS；不匹配 → FAIL |
| `false` | 退回 `expected_llm` 弱判 + `low_confidence` |

### 为什么这是「双 oracle」而不是「单 oracle」

`expected_android`（安卓实测）和 `expected_llm`（LLM 猜）是**「修正者 vs 被修正者」**，不是「两个投票者」：

- **不用「两者一致」当置信**——那是范畴错误，会把 grounding 成功纠错误降级；
- 用**独立结构指纹**判 `expected_android` 自身可信度（`android_trusted`）。

实测：真退化 4/4 抓 FAIL、untrusted 3/3 落 low_confidence 不误报、grounding 同时提 precision（少误报）和 recall（抓到单 oracle 漏的门禁退化）。

我的 v1/v2 把 `expected_android`/`android_trusted` 留 `null`，等于退化回「单 oracle（LLM 猜）」——功能清单的「安卓实测结果 / 实测可信」两列从此没有真值可回填。

---

## 完整对照表

| 维度 | main（v1）/ v2 | 真实方法（本分支） |
|---|---|---|
| 形态 | 一套确定性 Python 脚本 | 一组 Claude Code skill 编排 |
| fact-tree 产树 | 一个 prompt + `framework` 字段 | 调度器 + 三态生成器（XML→toolkit+ART / Compose→compose-fact-tree / hybrid 缝合） |
| 功能注册表（XML/混合） | 确定性投影 `registry_from_tree.py` | **LLM 读全源码** `a2h-functional-registry`（+ census/地板） |
| 功能注册表（纯 Compose） | 确定性投影 | 确定性投影（`compose_registry_from_tree.py`） |
| 功能点 → 页面映射 | 确定性（宿主页天然已知） | 确定性 ~82% + **枚举 LLM 精修**（Phase 3） |
| 设备遍历角色 | 回填可达性 / 截图 | 回填可达性 / 截图 **+ Phase 0.5 grounding 回填双 oracle 真值** |
| `expected_android` / `android_trusted` | 留 `null` | grounding 填真值（主 oracle） |
| 判定 oracle | 单（`expected_llm`） | 双（`expected_android` 主 + `expected_llm` 保底） |
| 校验 | （无对等） | `dispatch.py gate`（产出契约 / 连通 / 功能维度三道确定性闸） |

## 结论

真实方法不是我的 v1/v2 的「加几行代码」，而是**把「功能点完备性由 LLM 读源码保证」和「功能判定真值由安卓实测保证」两条线并起来**的编排系统。v1/v2 的确定性脚本只在**纯 Compose** 这个窄场景里成立；推广到 XML/混合时，「功能注册表也要 LLM」这条是绕不过去的。

本分支的 `docs/real-pipeline.md` + `docs/contracts.md` + `prompts/functional-checklist.md` 就是这条真实编排系统的忠实记录。
