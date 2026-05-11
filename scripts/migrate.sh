#!/usr/bin/env bash
# migrate.sh — Run Alembic migrations in a one-shot Docker container.
#
# Builds the backend image (if not already built), then runs a throwaway
# container with only `alembic <cmd>` as the entrypoint — no local Python,
# asyncpg, or alembic install required.
#
# Usage:
#   ./scripts/migrate.sh                  # upgrade to head (default)
#   ./scripts/migrate.sh current          # show current revision
#   ./scripts/migrate.sh history          # show full history
#   ./scripts/migrate.sh downgrade -1     # roll back one revision
#
# DATABASE_URL is read from (in order):
#   1. DATABASE_URL already exported in the shell
#   2. backend/.env

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
IMAGE="border-cloud-migrate"

ALEMBIC_ARGS=("upgrade" "head")   # default
if [[ $# -gt 0 ]]; then
  ALEMBIC_ARGS=("$@")
fi

# ── Resolve DATABASE_URL ─────────────────────────────────────────────────────
if [[ -z "${DATABASE_URL:-}" ]] && [[ -f "$BACKEND_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source <(grep -E '^DATABASE_URL=' "$BACKEND_DIR/.env")
  set +a
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "ERROR: DATABASE_URL is not set. Add it to backend/.env or export it first." >&2
  exit 1
fi

echo "DATABASE_URL: ${DATABASE_URL//:*@/:***@}"

# ── Build image ──────────────────────────────────────────────────────────────
echo "Building migration image…"
docker build -q -t "$IMAGE" "$BACKEND_DIR"

# ── Run migration ─────────────────────────────────────────────────────────────
echo "Running: alembic ${ALEMBIC_ARGS[*]}"
docker run --rm \
  -e "DATABASE_URL=$DATABASE_URL" \
  -e "SECRET_KEY=migration-dummy-key-not-used-for-auth-000000000000" \
  --entrypoint alembic \
  "$IMAGE" \
  "${ALEMBIC_ARGS[@]}"
