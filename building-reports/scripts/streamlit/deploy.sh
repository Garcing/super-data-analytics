#!/usr/bin/env bash
# 部署 Streamlit 报告到 GitHub (Garcing/streamlit-reports)，触发 Streamlit Cloud 自动重新部署。
# 原理：git subtree 把 building-reports/scripts/streamlit 子目录原样作为 streamlit-reports 的根推上去。
# 用法：bash scripts/streamlit/deploy.sh （脚本会自动 cd 到仓库根）
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

PREFIX="building-reports/scripts/streamlit"
REMOTE="streamlit-reports"
URL="https://super-data-analytics.streamlit.app/"
TMP="_streamlit_deploy"

git branch -D "$TMP" >/dev/null 2>&1 || true   # 清掉上次残留的临时分支
git subtree split --prefix="$PREFIX" -b "$TMP" # 子目录切出独立历史
git push "$REMOTE" "$TMP:main"                 # fast-forward 推到远程 main
git branch -D "$TMP"                           # 清理临时分支

# 备注：git push 触发的 git-credential-manager 偶尔会在工作目录留下
# <某目录>/system-commandline-sentinel-files/... 残留（GCM 已知问题 #505，无害）。
# 如需清理：find . -maxdepth 3 -name system-commandline-sentinel-files -type d -exec rm -rf {} +

echo ""
echo "✓ 已推送 $PREFIX → $REMOTE:main"
echo "✓ Streamlit Cloud 正在重新部署（约 1-2 分钟）"
echo "  线上地址：$URL"
