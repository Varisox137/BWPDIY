#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_DIR="${BWPDIY_REPO_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
REMOTE="${BWPDIY_REMOTE:-}"
BRANCH="${BWPDIY_BRANCH:-main}"
PORT="${BWPDIY_PORT:-8640}"
PYTHON="${BWPDIY_PYTHON:-python}"
EXPECTED_REMOTE="https://github.com/Varisox137/BWPDIY.git"

fail() {
    printf '错误：%s\n' "$*" >&2
    exit 1
}

command -v git >/dev/null 2>&1 || fail "未找到 git；请执行 pkg install git"
command -v "$PYTHON" >/dev/null 2>&1 || fail "未找到 $PYTHON；请执行 pkg install python"
command -v tee >/dev/null 2>&1 || fail "未找到 tee；请执行 pkg install coreutils"
[[ "$PORT" =~ ^[0-9]+$ ]] && ((PORT >= 1 && PORT <= 65535)) \
    || fail "BWPDIY_PORT 必须是 1-65535"
"$PYTHON" -c 'import sys; raise SystemExit(sys.version_info < (3, 12))' \
    || fail "Python 版本必须不低于 3.12"

cd -- "$REPO_DIR" || fail "无法进入仓库：$REPO_DIR"
[[ "$(git rev-parse --is-inside-work-tree 2>/dev/null)" == "true" ]] \
    || fail "$REPO_DIR 不是 Git 工作区"
[[ "$(git branch --show-current)" == "$BRANCH" ]] \
    || fail "当前分支不是 $BRANCH"
if [[ -z "$REMOTE" ]]; then
    if git remote get-url origin >/dev/null 2>&1; then
        REMOTE=origin
    else
        fail "远端 origin 不存在；可用 BWPDIY_REMOTE 指定远端"
    fi
fi
REMOTE_URL=$(git remote get-url "$REMOTE" 2>/dev/null) \
    || fail "远端不存在：$REMOTE"
REMOTE_URL=${REMOTE_URL%/}
case "$REMOTE_URL" in
    "$EXPECTED_REMOTE"|"https://github.com/Varisox137/BWPDIY"|"git@github.com:Varisox137/BWPDIY.git"|"ssh://git@github.com/Varisox137/BWPDIY.git")
        ;;
    *)
        fail "远端地址不符合预期：$REMOTE_URL"
        ;;
esac

if [[ -n "$(git status --porcelain --untracked-files=all)" ]]; then
    git status --short
    fail "存在未提交或未跟踪改动；不会自动 stash/reset/clean，请使用干净部署副本"
fi

mkdir -p logs
chmod 700 logs || printf '警告：无法设置日志目录权限，将继续启动\n' >&2
LOG_FILE="logs/bwpdiy-launcher-$(date +%Y%m%d-%H%M%S)-$$.log"
touch "$LOG_FILE"
chmod 600 "$LOG_FILE" || printf '警告：无法设置 launcher 日志权限，将继续启动\n' >&2
exec > >(tee -a "$LOG_FILE") 2>&1

printf '更新 %s/%s，日志：%s\n' "$REMOTE" "$BRANCH" "$LOG_FILE"
git pull --ff-only "$REMOTE" "$BRANCH"
printf '启动在线本地版原型：http://127.0.0.1:%s/\n' "$PORT"
printf '首次打开需要联网下载浏览器运行时；作品与卡图不会上传到服务器。\n'
exec "$PYTHON" "$REPO_DIR/prototype/pyodide/server.py" --port "$PORT" "$@"
