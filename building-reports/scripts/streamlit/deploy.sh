#!/usr/bin/env bash
# 部署 Streamlit 报告 app 到 GitHub (Garcing/streamlit-reports) → 触发 Streamlit Community Cloud 自动重新部署。
#
# 原理：用 git subtree 把 building-reports/scripts/streamlit 子目录
# 原样作为 streamlit-reports 仓库的根推上去（不复制文件、不维护两份代码）。
# Cloud 监听 main 分支，push 后约 1-2 分钟重新部署。
#
# 用法（在仓库根目录或 building-reports/ 下执行均可，脚本会自动 cd 到 repo 根）：
#   bash scripts/streamlit/deploy.sh
#
# 前提：
#   - 已把新报告 commit 到本仓库（skill repo）的 main 分支
#   - 远程 streamlit-reports 已配好（git remote -v 可见）
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

PREFIX="building-reports/scripts/streamlit"
REMOTE="streamlit-reports"
URL="https://super-data-analysis.streamlit.app/"
TMP="_streamlit_deploy"

# 清理可能残留的临时分支
git branch -D "$TMP" >/dev/null 2>&1 || true

# 把子目录切出成独立历史的临时分支（其根 = 子目录内容）
git subtree split --prefix="$PREFIX" -b "$TMP"

# 推到 streamlit-reports 的 main。
# 注意：本仓库 1.0 重置后 git 历史与 streamlit-reports 无共同祖先，subtree split
# 切出的 commit 无法 fast-forward，必须 --force 覆盖（deploy 专用仓库，可接受）。
git push --force "$REMOTE" "$TMP:main"

# 清理临时分支
git branch -D "$TMP"

# 清理 GCM（.NET System.CommandLine 库）可能在工作目录残留的 dotnet-suggest sentinel 文件。
# 根因见 https://github.com/git-ecosystem/git-credential-manager/issues/505：
# git push 触发的 git-credential-manager 偶尔会在 cwd 留下 <某目录>/system-commandline-sentinel-files/...
# 精准匹配该子目录并删除，顺手清掉空壳父目录，保证 skill 跑完工作区干净。
find . -maxdepth 3 -name "system-commandline-sentinel-files" -type d 2>/dev/null | while IFS= read -r d; do
  rm -rf "$d"
  rmdir "$(dirname "$d")" 2>/dev/null || true
done

echo ""
echo "✓ 已推送 $PREFIX → $REMOTE:main"
echo "✓ Streamlit Cloud 正在重新部署（约 1-2 分钟）"
echo "  线上地址：$URL"
