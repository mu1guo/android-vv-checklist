#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_func_list.py — 真实 vv 功能清单组装脚本（参考实例：Cofi，com.omelan.cofi，纯 Jetpack Compose）。

这是真实生产方法阶段⑤ 的确定性组装器（从 `E:\huawei_0930_project_cc\Cofi_visualverify_and_feature_checklist\gen_func_list.py`
忠实复制，仅加本注释头）。它演示「根据 UI 树 + 功能树 + 遍历账本生成 Excel 功能清单」这一真实动作：

消费三样输入 → 34 列 xlsx（功能清单 / 页面路径 / 说明 三 sheet），列 schema 对齐 AIPPT feature.xlsx：
  1) spec/toolkit-fact-tree.json           UI 树（pages/dialogs/components/reach_path/functional_checks）
  2) spec/a2h/functional_registry.json     功能树（feature_path/name/source_file）
     spec/a2h/compose_host_map.json        精确映射（host_id/component_id/tap_text/expected）
     spec/a2h/test_intents.json            预期结果
  3) android_traverse_screenshots/index.json  安卓边遍历账本（真实到达/截图）

★ 本实例是纯 Compose 分支：无 resource-id → 控件ID 用树内 component_id；账号状态写死「无账号体系（本地 mock）」。
  XML/混合 app 的差异：控件ID 用真 resource-id、控件类型来自 toolkit-fact-indexer、账号态按 login/VIP 门控分 trip。
  ★ app 特定硬编码：DEVICE_MAP（host 页 → 设备 page_id）每个 app 都要改写——真实设备账本的 page_id 与树内 host_id 的对应关系 app 之间不同。
"""
import json, os, re, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
TREE = os.path.join(HERE, "spec", "toolkit-fact-tree.json")
REG = os.path.join(HERE, "spec", "a2h", "functional_registry.json")
HMAP = os.path.join(HERE, "spec", "a2h", "compose_host_map.json")
INTENTS = os.path.join(HERE, "spec", "a2h", "test_intents.json")
IDX = os.path.join(HERE, "android_traverse_screenshots", "index.json")

def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)

tree = load(TREE)
reg = load(REG)["entries"]
hmap = load(HMAP)
intents = load(INTENTS)

# ---------- 页面元数据 ----------
pages = tree["pages"] + tree["dialogs"]
by_id = {p["id"]: p for p in pages}
# 一级模块（features 聚类）
FEAT_LABEL = {f["id"]: f["label"] for f in tree["features"]}

# ---------- 组件索引（page_id -> component_id -> component）----------
comp_by_page = {}
for p in pages:
    comp_by_page[p["id"]] = {c["id"]: c for c in p.get("components", [])}

# ---------- 设备账本 ----------
units = load(IDX) if os.path.exists(IDX) else []
units_by_pid = {u["page_id"]: u for u in units}
# host 页/弹窗 -> 设备 page_id（单 Activity Compose，多 host 共用同屏）
DEVICE_MAP = {
    "MainActivity": "page_0001_RecipeList",
    "RecipeList": "page_0001_RecipeList",
    "RecipeDetails": "page_0002_RecipeDetails",
    "RecipeEdit": "page_0003_RecipeEdit",
    "AddRecipe": "page_0004_AddRecipe",
    "AppSettings": "page_0005_AppSettings",
    "TimerSettings": "page_0006_TimerSettings",
    "BackupRestoreSettings": "page_0007_BackupRestoreSettings",
    "AppSettingsAbout": "page_0008_AppSettingsAbout",
    "LicensesList": "page_0009_LicensesList",
    "AppearanceSettings": "page_0010_AppearanceSettings",
    "CombineWeightDialog": "page_0011_CombineWeightDialog",
    "BackupDialog": "page_0012_BackupDialog",
    "DefaultRecipesDialog": "page_0013_DefaultRecipesDialog",
    # NotificationPermissionDialog —— 条件自动弹窗，遍历未触发（已授权/已关闭）
    "DirectLinkDialog": "page_0015_DirectLinkDialog",
    "RatioBottomSheet": "page_0016_RatioBottomSheet",
    "IconPickerBottomSheet": "page_0017_IconPickerBottomSheet",
    "CloneDialog": "page_0018_CloneDialog",
    "DeleteDialog": "page_0019_DeleteDialog",
    "SaveDialog": "page_0020_SaveDialog",
    "DurationExplainerDialog": "page_0021_DurationExplainerDialog",
    # SupportCofiDialog —— 条件自动弹窗（完成食谱 3 次后），遍历未触发
}

NOOP = re.compile(r"no-op|todo", re.I)

def page_purpose(pid):
    return by_id.get(pid, {}).get("purpose") or ""

def device_unit_for(host_id, comp_id):
    pid = DEVICE_MAP.get(host_id)
    return units_by_pid.get(pid) if pid else None

def click_path_for(pid):
    p = by_id[pid]
    it = p.get("inbound_triggers") or []
    if p.get("is_start_destination") or pid == "MainActivity":
        return f"冷启动自动进入「{p.get('label') or pid}」"
    if it and it[0].get("trigger") != "boot":
        e = it[0]
        lbl = e.get("trigger_label") or e.get("trigger_method") or "入口"
        return f"冷启动 → {e.get('from_page') or '?'} → 点「{lbl}」→ {p.get('label') or pid}"
    return f"冷启动 → {p.get('label') or pid}"

def reach_path_text(pid):
    p = by_id[pid]
    rp = p.get("reach_path_clean") or p.get("reach_path") or []
    return " → ".join(rp) if rp else ""

def steps_for(pid):
    p = by_id[pid]
    rp = p.get("reach_path_clean") or []
    steps = []
    for i, s in enumerate(rp):
        steps.append(s if i == 0 else f"进入「{s}」")
    if pid not in ("MainActivity",) and not p.get("is_start_destination"):
        it = p.get("inbound_triggers") or []
        if it and it[0].get("trigger") != "boot":
            steps.append(f"点「{it[0].get('trigger_label') or '入口'}」")
    return steps

# ---------- 构建 功能清单 sheet 行 ----------
HEADER = ["序号", "功能ID", "树内FP名", "一级模块", "功能路径", "功能点", "所在页面", "页面用途",
          "控件ID", "控件类型", "账号状态", "前置条件", "操作", "预期结果(源码推断)",
          "安卓实测结果", "实测可信", "实测来源", "可达性", "备注",
          "reach_path(树)", "点击路径", "步数", "路径验证", "页面截图",
          "步骤1", "步骤2", "步骤3", "步骤4", "步骤5", "步骤6", "步骤7", "步骤8", "步骤9", "步骤10"]

INTENT_EXPECT = {}
for grp in intents.get("groups", {}).values():
    for it in grp:
        for s in it.get("steps", []):
            if "预期结果：" in s:
                INTENT_EXPECT[it["feature_path"]] = s.split("预期结果：", 1)[1].strip()

rows = []
for i, e in enumerate(reg, 1):
    name = e["name"]
    fp = e["feature_path"]
    segs = [s for s in fp.split(">") if s.strip()]
    module = segs[0] if segs else ""
    hm = hmap.get(fp, {})
    host_id = hm.get("host_id", "")
    comp_id = hm.get("component_id", "")
    comp = comp_by_page.get(host_id, {}).get(comp_id, {})
    ctype = comp.get("type", "元素")
    notes = comp.get("notes") or ""
    is_noop = bool(NOOP.search(notes))
    feat_id = by_id[host_id].get("logical_feature_id") if host_id in by_id else ""
    module_label = FEAT_LABEL.get(feat_id, module)

    unit = device_unit_for(host_id, comp_id)
    reached = unit is not None
    dev_label = unit.get("label", "") if unit else ""
    shot = os.path.relpath(unit["screenshot"], HERE).replace("\\", "/") if unit and unit.get("screenshot") else ""

    expect = INTENT_EXPECT.get(fp) or hm.get("expected") or ""
    action = f"在 {by_id.get(host_id, {}).get('label', host_id)} 页面点击「{name}」"

    if is_noop:
        actual = f"宿主页「{dev_label or host_id}」已到达；该控件源码为 no-op（点击无反应，范围外）"
    elif reached:
        actual = f"设备已到达宿主页「{dev_label}」"
    else:
        actual = "设备未到达（条件自动弹窗，遍历未触发）"

    steps = steps_for(host_id)
    depth = e.get("depth") or len(segs)
    verif = "全程安卓实走确认" if reached else "源码推断"

    row = [
        i,                                   # 序号
        f"INT{i:04d}",                       # 功能ID
        "FP_" + re.sub(r"\W+", "_", name),   # 树内FP名
        module_label,                        # 一级模块
        fp,                                  # 功能路径
        name,                                # 功能点
        host_id,                             # 所在页面
        page_purpose(host_id),               # 页面用途
        comp_id,                             # 控件ID
        ctype,                               # 控件类型
        "无账号体系（本地 mock）",            # 账号状态
        hm.get("precondition") or "",        # 前置条件
        action,                              # 操作
        expect,                              # 预期结果(源码推断)
        actual,                              # 安卓实测结果
        "是" if reached else "否",           # 实测可信
        ("边遍历" if reached else ""),       # 实测来源
        "可达" if reached else "不可达",      # 可达性
        notes,                               # 备注
        reach_path_text(host_id),            # reach_path(树)
        click_path_for(host_id),             # 点击路径
        depth,                               # 步数
        verif,                               # 路径验证
        shot,                                # 页面截图
    ]
    for s in steps[:10]:
        row.append(s)
    while len(row) < len(HEADER):
        row.append("")
    rows.append(row)

# ---------- 构建 页面路径 sheet ----------
PAGE_HEADER = ["页面ID", "类型", "用途", "账号状态", "安卓实到达", "可达性", "备注",
               "reach_path(树)", "点击路径", "步数", "路径验证", "截图",
               "步骤1", "步骤2", "步骤3", "步骤4", "步骤5", "步骤6", "步骤7", "步骤8", "步骤9"]
dialog_ids = {d["id"] for d in tree["dialogs"]}
page_rows = []
for p in pages:
    pid = p["id"]
    unit = device_unit_for(pid, None)
    reached = unit is not None
    steps = steps_for(pid)
    r = [
        pid,
        "Activity" if pid == "MainActivity" else ("弹窗" if pid in dialog_ids else "页面"),
        page_purpose(pid),
        "无账号体系（本地 mock）",
        "是" if reached else "否",
        "可达" if reached else "不可达",
        "" if reached else ("条件自动弹窗（NotificationPermissionDialog/SupportCofiDialog）" if pid in ("NotificationPermissionDialog", "SupportCofiDialog") else ""),
        reach_path_text(pid),
        click_path_for(pid),
        len(p.get("reach_path_clean") or []),
        "全程安卓实走确认" if reached else "源码推断",
        (os.path.relpath(unit["screenshot"], HERE).replace("\\", "/") if unit and unit.get("screenshot") else ""),
    ]
    for s in steps[:9]:
        r.append(s)
    while len(r) < len(PAGE_HEADER):
        r.append("")
    page_rows.append(r)

# ---------- 写 xlsx ----------
import openpyxl
from openpyxl.utils import get_column_letter
wb = openpyxl.Workbook()
ws1 = wb.active
ws1.title = "功能清单"
ws1.append(HEADER)
for r in rows:
    ws1.append(r)
ws2 = wb.create_sheet("页面路径")
ws2.append(PAGE_HEADER)
for r in page_rows:
    ws2.append(r)
ws3 = wb.create_sheet("说明")
ws3.append(["Cofi（com.omelan.cofi，纯 Jetpack Compose 手冲咖啡计时器）安卓功能清单", None])
ws3.append(["数据来源", "UI 树 spec/toolkit-fact-tree.json；功能树 spec/a2h/functional_registry.json + compose_host_map.json + test_intents.json；安卓边遍历账本 android_traverse_screenshots/index.json"])
ws3.append(["生成方式", "compose-fact-tree（LLM 源码分析产树）→ compose_registry_from_tree → compose_merge_into_facttree → 手动 adb 设备遍历（aft 工具不可用）→ 本脚本"])
ws3.append(["架构", "纯 Compose（无 XML/resource-id）；控件锚点用文案(text/contentDesc)，源码位置用 .kt 相对路径"])
ws3.append(["口径", "功能点 = 交互组件（is_interactive=true）；数据驱动列表（食谱卡/步骤项/设置项/图标网格）按同构家族压缩为 1 条"])
ws3.append(["账号态", "无账号体系（本地 Room mock；预置 6 款 James Hoffmann 默认食谱）"])
ws3.append(["遍历", "20/23 屏实走（含 9 弹窗）；NotificationPermissionDialog 与 SupportCofiDialog 为条件自动弹窗，遍历未触发"])

for ws in (ws1, ws2):
    for ci in range(1, ws.max_column + 1):
        ws.column_dimensions[get_column_letter(ci)].width = 18

out = os.path.join(HERE, f"Cofi_安卓功能清单_{datetime.datetime.now():%Y%m%d_%H%M%S}.xlsx")
wb.save(out)
print(f"[ok] 写入 {out}")
print(f"   功能清单 {len(rows)} 行 / 34 列；页面路径 {len(page_rows)} 行")
print(f"   设备可达 {sum(1 for r in rows if r[17]=='可达')} 条功能点，不可达 {sum(1 for r in rows if r[17]=='不可达')}")
