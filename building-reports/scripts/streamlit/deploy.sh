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

# Windows 上 git push 会调 git-credential-manager（.NET 程序），其 dotnet-suggest
# 会在 cwd 留下一个名为 $TMP 的 sentinel 文件夹。把 DOTNET_SUGGEST_SCRIPTS 指到临时目录，
# 让 sentinel 写那里而非仓库根；push 后再 rm -rf 兜底，确保仓库干净。
export DOTNET_SUGGEST_SCRIPTS="${TMPDIR:-/tmp}/dotnet-suggest"

git branch -D "$TMP" >/dev/null 2>&1 || true   # 清掉上次残留的临时分支
git subtree split --prefix="$PREFIX" -b "$TMP" # 子目录切出独立历史
git push "$REMOTE" "$TMP:main"                 # fast-forward 推到远程 main
git branch -D "$TMP"                           # 清理临时分支
rm -rf "$TMP"                                  # 兜底：清掉 GCM 可能留下的 sentinel 文件夹

echo ""
echo "✓ 已推送 $PREFIX → $REMOTE:main"
echo "✓ Streamlit Cloud 正在重新部署（约 1-2 分钟）"
echo "  线上地址：$URL"
