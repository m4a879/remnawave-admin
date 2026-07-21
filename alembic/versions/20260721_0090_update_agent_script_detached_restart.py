"""update_agent: перекат агента переживает смерть самого агента.

Revision ID: 0090
Revises: 0089
Create Date: 2026-07-21

Боевой кейс: скрипт «Обновление агента» выполняется процессом САМОГО агента
(exec_script). Когда он делает `docker compose up -d` / `docker restart` /
`systemctl restart` для агента, docker/systemd убивает весь cgroup — включая
скрипт — между «остановить старое» и «запустить новое». Агент оставался
лежать, приходилось заходить на сервер руками.

Теперь тяжёлая и безопасная часть (pull образа, git/tarball, зависимости)
выполняется в скрипте как раньше, а сам перезапуск уходит в transient
systemd-unit хоста (systemd-run --collect) — он живёт вне cgroup агента и
довершает перекат после смерти скрипта. Фолбэк без systemd-run: setsid+nohup.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0090"
down_revision: Union[str, None] = "0089"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_SCRIPT_CONTENT = r"""#!/bin/sh
set -e

CONTAINER_NAME="${CONTAINER_NAME:-remnawave-node-agent}"
SERVICE_NAME="${SERVICE_NAME:-remnawave-node-agent}"
REPO_TARBALL="https://github.com/Case211/remnawave-admin/archive/refs/heads/main.tar.gz"

echo "=== Updating Remnawave Node Agent ==="

# Скрипт выполняется процессом САМОГО агента: перезапуск агента убивает и
# скрипт (cgroup). Всё, что перезапускает агента, уводим в фон вне cgroup —
# transient systemd-unit (или setsid+nohup), который довершит перекат.
detached_run() {
    # sleep 3 — скрипт успевает завершиться и отдать результат в панель
    # ДО того, как фоновый юнит убьёт агента перезапуском
    if command -v systemd-run >/dev/null 2>&1; then
        systemd-run --unit="remnawave-agent-update-$(date +%s)" --collect \
            /bin/sh -c "sleep 3; $1" >/dev/null 2>&1
    else
        setsid nohup sh -c "sleep 3; $1" >/var/tmp/remnawave-agent-update.log 2>&1 &
    fi
}

# --- Detect environment ---
if [ -f "/.dockerenv" ] || grep -qsE '(docker|containerd)' /proc/1/cgroup 2>/dev/null; then
    echo "Running inside Docker container."
    echo ""
    echo "Self-update from inside a container is not supported."
    echo "To update the agent, run on the HOST machine:"
    echo ""
    echo "  cd <agent-compose-directory>"
    echo "  docker compose pull"
    echo "  docker compose up -d"
    exit 0
fi

# --- Docker deployment on host ---
if command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${CONTAINER_NAME}$"; then
    echo "Docker deployment detected (container: $CONTAINER_NAME)"

    OLD_IMAGE=$(docker inspect --format='{{.Config.Image}}' "$CONTAINER_NAME" 2>/dev/null || echo "unknown")
    echo "Current image: $OLD_IMAGE"

    COMPOSE_DIR=$(docker inspect --format='{{index .Config.Labels "com.docker.compose.project.working_dir"}}' "$CONTAINER_NAME" 2>/dev/null || echo "")
    COMPOSE_SERVICE=$(docker inspect --format='{{index .Config.Labels "com.docker.compose.service"}}' "$CONTAINER_NAME" 2>/dev/null || echo "")

    if [ -n "$COMPOSE_DIR" ] && [ -n "$COMPOSE_SERVICE" ]; then
        echo "Pulling latest image..."
        cd "$COMPOSE_DIR"
        docker compose pull "$COMPOSE_SERVICE" 2>&1 | tail -5
        echo "Recreating container in background (survives agent restart)..."
        detached_run "cd '$COMPOSE_DIR' && docker compose up -d --no-deps '$COMPOSE_SERVICE'"
    else
        echo "Pulling latest image..."
        docker pull "$OLD_IMAGE" 2>&1 | tail -5
        echo "Restarting container in background (survives agent restart)..."
        detached_run "docker restart '$CONTAINER_NAME'"
        echo "NOTE: For full image update use 'docker compose pull && docker compose up -d'"
    fi
    echo "Agent will reconnect with the new version shortly (~30s)."
    exit 0
fi

# --- Bare metal / systemd deployment ---
echo "Bare metal deployment detected"

# Auto-detect agent directory: git-repo OR plain sources (src/main.py)
if [ -z "$AGENT_DIR" ]; then
    for candidate in \
        /opt/node-agent \
        /opt/remnawave-node-agent \
        /opt/remnawave-node \
        /opt/remnawave-agent \
        /root/node-agent \
        /root/remnawave-node \
        /home/*/node-agent \
        /home/*/remnawave-node
    do
        if [ -d "$candidate/.git" ] || [ -f "$candidate/src/main.py" ]; then
            AGENT_DIR="$candidate"
            echo "Auto-detected agent at: $AGENT_DIR"
            break
        fi
    done
fi

AGENT_DIR="${AGENT_DIR:-/opt/node-agent}"

if [ ! -d "$AGENT_DIR" ]; then
    echo "ERROR: Agent directory not found: $AGENT_DIR"
    echo "Specify AGENT_DIR parameter when running this script."
    exit 1
fi

cd "$AGENT_DIR"

agent_ver() {
    grep -oE 'AGENT_VERSION *= *"[^"]+"' src/version.py 2>/dev/null | cut -d'"' -f2 || true
}

restart_service() {
    echo "Restarting $SERVICE_NAME in background (survives self-restart)..."
    detached_run "systemctl restart '$SERVICE_NAME'"
    echo "Agent will reconnect with the new version shortly (~30s)."
}

install_deps() {
    if [ -f "requirements.txt" ]; then
        echo "Updating pip dependencies..."
        pip3 install -r requirements.txt --quiet 2>&1 || pip install -r requirements.txt --quiet 2>&1 || true
    fi
}

if [ -d ".git" ]; then
    # Git installation — original flow
    OLD_VERSION=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    echo "Current version: $OLD_VERSION"
    echo "Pulling latest changes..."
    git fetch --all --quiet
    git reset --hard origin/main
    NEW_VERSION=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    echo "New version: $NEW_VERSION"
    if [ "$OLD_VERSION" = "$NEW_VERSION" ]; then
        echo "Already up to date."
        exit 0
    fi
    install_deps
    restart_service
    echo "Agent updated: $OLD_VERSION -> $NEW_VERSION"
    exit 0
fi

# Plain sources without git — refresh from GitHub tarball, keep .env intact
if [ ! -f "src/main.py" ]; then
    echo "ERROR: $AGENT_DIR is neither a git repo nor an agent source tree"
    echo "Reinstall the agent from the node dialog in the panel (install.sh)."
    exit 1
fi

echo "Plain-source installation (no git) — updating from GitHub tarball..."
OLD_VER=$(agent_ver)
[ -n "$OLD_VER" ] && echo "Current agent version: $OLD_VER"

TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

if command -v curl >/dev/null 2>&1; then
    curl -sSL "$REPO_TARBALL" -o "$TMP_DIR/repo.tar.gz"
elif command -v wget >/dev/null 2>&1; then
    wget -q "$REPO_TARBALL" -O "$TMP_DIR/repo.tar.gz"
else
    echo "ERROR: neither curl nor wget found"
    exit 1
fi

tar -xzf "$TMP_DIR/repo.tar.gz" -C "$TMP_DIR" --strip-components=2 "remnawave-admin-main/node-agent" 2>/dev/null \
    || tar -xzf "$TMP_DIR/repo.tar.gz" -C "$TMP_DIR" --strip-components=2 --wildcards "*/node-agent"

if [ ! -f "$TMP_DIR/src/main.py" ]; then
    echo "ERROR: downloaded tarball does not contain node-agent sources"
    exit 1
fi

# Overwrite code, never the local config
rm -rf src
cp -r "$TMP_DIR/src" src
[ -f "$TMP_DIR/requirements.txt" ] && cp "$TMP_DIR/requirements.txt" requirements.txt

NEW_VER=$(agent_ver)
[ -n "$NEW_VER" ] && echo "New agent version: $NEW_VER"

install_deps
restart_service
echo "Agent updated${OLD_VER:+: $OLD_VER}${NEW_VER:+ -> $NEW_VER}"
"""


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE node_scripts SET script_content = :content, updated_at = NOW() "
            "WHERE name = 'update_agent'"
        ),
        {"content": NEW_SCRIPT_CONTENT},
    )


def downgrade() -> None:
    # Скрипт правится и из UI; откат содержимого не критичен.
    pass
