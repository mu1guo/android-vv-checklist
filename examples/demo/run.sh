#!/usr/bin/env bash
# 端到端跑通 vv 功能清单（无需真机）：② 功能点契约 → ③ 注入 → ⑤ xlsx + ECAT md
set -euo pipefail
cd "$(dirname "$0")"

ROOT="$(cd ../.. && pwd)"

echo "== ② compose_registry_from_tree =="
python3 "$ROOT/src/compose_registry_from_tree.py" --tree spec/toolkit-fact-tree.json --out spec/a2h

echo "== ③ compose_merge_into_facttree（注入 functional_checks，写到 merged 文件，不动输入）=="
python3 "$ROOT/src/compose_merge_into_facttree.py" \
    --facttree spec/toolkit-fact-tree.json \
    --registry spec/a2h/functional_registry.json \
    --host-map spec/a2h/compose_host_map.json \
    --out spec/toolkit-fact-tree.merged.json

echo "== ⑤ gen_func_list（xlsx + ECAT markdown）=="
python3 "$ROOT/src/gen_func_list.py" --app . --config config.json --ecat

echo ""
echo "产物："
echo "  spec/a2h/functional_registry.json"
echo "  spec/a2h/compose_host_map.json"
echo "  spec/a2h/test_intents.json"
echo "  spec/toolkit-fact-tree.merged.json"
echo "  Demo_安卓功能清单_*.xlsx"
echo "  Demo_安卓功能清单_ecat_checklist.md"
