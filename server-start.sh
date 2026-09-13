#!/usr/bin/env bash
set -Eeuo pipefail

# 服务器一键更新并部署。
#
# 常规更新：
#   ./server-start.sh
# 首次部署：
#   ./server-start.sh --init
# 指定远端和分支：
#   ./server-start.sh --remote gitlab --branch main

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REMOTE="${DEPLOY_GIT_REMOTE:-origin}"
BRANCH="${DEPLOY_GIT_BRANCH:-}"
INIT_MODE=false

usage() {
    cat <<'EOF'
用法：./server-start.sh [--init] [--remote <远端>] [--branch <分支>]

  --init            首次部署：初始化数据库并写入种子数据
  --remote <远端>   Git 远端名，默认 origin，也可用环境变量 DEPLOY_GIT_REMOTE
  --branch <分支>   部署分支，默认当前分支，也可用环境变量 DEPLOY_GIT_BRANCH
  -h, --help        显示帮助
EOF
}

while (($#)); do
    case "$1" in
        --init)
            INIT_MODE=true
            shift
            ;;
        --remote)
            [ "$#" -ge 2 ] || { echo "错误：--remote 缺少参数" >&2; exit 2; }
            REMOTE="$2"
            shift 2
            ;;
        --branch)
            [ "$#" -ge 2 ] || { echo "错误：--branch 缺少参数" >&2; exit 2; }
            BRANCH="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "错误：未知参数 $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

cd "$PROJECT_DIR"

command -v git >/dev/null || { echo "错误：服务器未安装 git" >&2; exit 1; }
command -v docker >/dev/null || { echo "错误：服务器未安装 docker" >&2; exit 1; }
docker compose version >/dev/null 2>&1 || {
    echo "错误：Docker Compose v2 不可用（需要 docker compose 命令）" >&2
    exit 1
}
[ -d .git ] || { echo "错误：${PROJECT_DIR} 不是 Git 仓库" >&2; exit 1; }
[ -f .env ] || {
    echo "错误：缺少 .env，请先执行 cp .env.example .env 并修改生产配置" >&2
    exit 1
}

if [ -z "$BRANCH" ]; then
    # git branch --show-current 需要 Git 2.22+；symbolic-ref 兼容旧版 Git。
    BRANCH="$(git symbolic-ref --quiet --short HEAD || true)"
fi
[ -n "$BRANCH" ] || { echo "错误：当前处于 detached HEAD，请用 --branch 指定部署分支" >&2; exit 1; }

git remote get-url "$REMOTE" >/dev/null 2>&1 || {
    echo "错误：Git 远端 '$REMOTE' 不存在" >&2
    exit 1
}

# 不覆盖服务器上的人工修改，避免代码和配置在部署时悄悄丢失。
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "错误：仓库存在未提交的已跟踪文件修改，请先提交或处理后再部署：" >&2
    git status --short >&2
    exit 1
fi

echo "[1/3] 同步代码：${REMOTE}/${BRANCH} ..."
git fetch --prune "$REMOTE" "$BRANCH"

REMOTE_REF="refs/remotes/${REMOTE}/${BRANCH}"
git show-ref --verify --quiet "$REMOTE_REF" || {
    echo "错误：远端分支 ${REMOTE}/${BRANCH} 不存在" >&2
    exit 1
}

if ! git merge-base --is-ancestor HEAD "$REMOTE_REF"; then
    echo "错误：本地提交与 ${REMOTE}/${BRANCH} 不一致，已停止部署以避免覆盖代码" >&2
    echo "请先人工检查：git log --oneline --graph --decorate --all -20" >&2
    exit 1
fi

git merge --ff-only "$REMOTE_REF"
echo "当前版本：$(git rev-parse --short HEAD) ($(git log -1 --format=%s))"

echo "[2/3] 检查部署脚本 ..."
[ -x ./deploy.sh ] || chmod +x ./deploy.sh

echo "[3/3] 构建并启动服务 ..."
if [ "$INIT_MODE" = true ]; then
    exec ./deploy.sh --init
else
    exec ./deploy.sh
fi
