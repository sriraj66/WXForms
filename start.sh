#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# WX Form — first-time bootstrap & run script.
#
# Usage:
#   ./start.sh                # interactive: sets up + runs dev server
#   ./start.sh --no-run       # only set things up, don't start the server
#   ./start.sh --reset        # wipe venv and start fresh
#   PORT=8080 ./start.sh      # custom port (default 8000)
# ---------------------------------------------------------------------------
set -euo pipefail

# --- Pretty output --------------------------------------------------------
BOLD="$(printf '\033[1m')"; DIM="$(printf '\033[2m')"; RESET="$(printf '\033[0m')"
GREEN="$(printf '\033[32m')"; YELLOW="$(printf '\033[33m')"; RED="$(printf '\033[31m')"; BLUE="$(printf '\033[34m')"

step()  { echo "${BLUE}${BOLD}==>${RESET} ${BOLD}$*${RESET}"; }
ok()    { echo "  ${GREEN}✓${RESET} $*"; }
warn()  { echo "  ${YELLOW}!${RESET} $*"; }
die()   { echo "${RED}✗ $*${RESET}" >&2; exit 1; }

# --- Resolve paths --------------------------------------------------------
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/.venv"
BACKEND="$ROOT/backend"
PORT="${PORT:-8000}"
RUN_SERVER=1
RESET=0

for arg in "$@"; do
    case "$arg" in
        --no-run) RUN_SERVER=0 ;;
        --reset)  RESET=1 ;;
        -h|--help)
            grep -E '^# ' "$0" | sed -E 's/^# ?//'
            exit 0
            ;;
        *) warn "Unknown argument: $arg" ;;
    esac
done

cd "$ROOT"

# --- 1. Python check ------------------------------------------------------
step "Checking Python"
PYTHON_BIN="$(command -v python3 || true)"
[[ -n "$PYTHON_BIN" ]] || die "python3 not found. Install Python 3.10+ first."
PY_VERSION="$($PYTHON_BIN -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
ok "Found Python $PY_VERSION at $PYTHON_BIN"

# --- 2. Virtualenv --------------------------------------------------------
if [[ "$RESET" -eq 1 && -d "$VENV" ]]; then
    step "Removing existing virtualenv (--reset)"
    rm -rf "$VENV"
    ok "Removed $VENV"
fi

if [[ ! -d "$VENV" ]]; then
    step "Creating virtualenv at .venv"
    "$PYTHON_BIN" -m venv "$VENV"
    ok "Created $VENV"
else
    ok "Virtualenv already exists"
fi

# shellcheck source=/dev/null
source "$VENV/bin/activate"

# --- 3. Dependencies ------------------------------------------------------
step "Installing dependencies"
pip install --quiet --upgrade pip
pip install --quiet -r "$ROOT/requirements.txt"
ok "Dependencies installed"

# --- 4. Environment defaults ---------------------------------------------
ENV_FILE="$BACKEND/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    step "Creating default .env"
    SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(50))')"
    cat > "$ENV_FILE" <<EOF
# WX Form — local development environment.
DJANGO_SECRET_KEY=$SECRET_KEY
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
EOF
    ok "Wrote $ENV_FILE"
else
    ok ".env already exists, leaving as-is"
fi

# --- 5. Database migration ------------------------------------------------
step "Running database migrations"
cd "$BACKEND"
python manage.py migrate --noinput
ok "Database is up to date"

# --- 6. Static files ------------------------------------------------------
step "Collecting static files"
python manage.py collectstatic --noinput >/dev/null
ok "Static files collected"

# --- 7. Default app settings ---------------------------------------------
step "Loading default app settings"
python manage.py shell -c "from misc.services import load_default_app_settings; created = load_default_app_settings(); print('  new:', created or 'none (already loaded)')"

# --- 8. Superuser (optional) ---------------------------------------------
if ! python manage.py shell -c "from django.contrib.auth import get_user_model; import sys; sys.exit(0 if get_user_model().objects.filter(is_superuser=True).exists() else 1)" >/dev/null 2>&1; then
    step "Creating superuser (interactive)"
    echo "  ${DIM}Skip with Ctrl+C if you want to do it later via 'python manage.py createsuperuser'${RESET}"
    if ! python manage.py createsuperuser; then
        warn "Superuser creation skipped"
    fi
else
    ok "Superuser already exists"
fi

# --- 9. Run server --------------------------------------------------------
if [[ "$RUN_SERVER" -eq 1 ]]; then
    step "Starting dev server on http://127.0.0.1:$PORT"
    echo "  ${DIM}Press Ctrl+C to stop.${RESET}"
    exec python manage.py runserver "$PORT"
else
    ok "Setup complete. Run the server with:"
    echo "    source .venv/bin/activate && cd backend && python manage.py runserver $PORT"
fi
