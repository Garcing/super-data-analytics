#!/usr/bin/env bash
# 部署 Streamlit 报告 app 到 GitHub (Garcing/streamlit-reports) → 触发 Streamlit Community Cloud 自动重新部署。
#
# 原理：用 git subtree 把 generating-insights-report/scripts/streamlit 子目录
# 原样作为 streamlit-reports 仓库的根推上去（不复制文件、不维护两份代码）。
# Cloud 监听 main 分支，push 后约 1-2 分钟重新部署。
#
# 用法（在 generating-insights-report/ 目录下执行）：
#   bash scripts/streamlit/deploy.sh
#
# 前提：
#   - 已把新报告 commit 到本仓库（skill repo）的 main 分支
#   - 远程 streamlit-reports 已配好（git remote -v 可见）
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

PREFIX="generating-insights-report/scripts/streamlit"
REMOTE="streamlit-reports"
URL="https://super-data-analysis.streamlit.app/"
TMP="_streamlit_deploy"

# 清理可能残留的临时分支
git branch -D "$TMP" >/dev/null 2>&1 || true

# 把子目录切出成独立历史的临时分支（其根 = 子目录内容）
git subtree split --prefix="$PREFIX" -b "$TMP"

# 推到 streamlit-reports 的 main（fast-forward；deploy 专用仓库，不应有分叉）
git push "$REMOTE" "$TMP:main"

# 清理临时分支
git branch -D "$TMP"

echo ""
echo "✓ 已推送 $PREFIX → $REMOTE:main"
echo "✓ Streamlit Cloud 正在重新部署（约 1-2 分钟）"
echo "  线上地址：$URL"
