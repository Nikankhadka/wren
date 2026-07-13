#!/usr/bin/env bash
# One-command demo bootstrap for Wren.
#
# Starts a local GoTrue (Supabase Auth) + the dev DB, fixes env files, runs
# migrations + the demo-world seed, and brings up the backend + frontend dev
# servers. Ctrl-C cleanly stops both dev servers (the DB + auth stay up for a
# quick rerun; `docker compose down` tears them out fully).
#
# See docs/DEMO.md for the scripted walkthrough and troubleshooting.
set -euo pipefail

# All paths resolve from the repo root, no matter where the script is invoked.
cd "$(dirname "$0")/.."
ROOT="$PWD"

# --- pretty printing -----------------------------------------------------------
c_reset=$'\033[0m'; c_bold=$'\033[1m'; c_dim=$'\033[2m'; c_green=$'\033[32m'; c_red=$'\033[31m'; c_yellow=$'\033[33m'
say()  { printf '%s\n' "${c_bold}$*${c_reset}"; }
ok()   { printf '%s%s%s\n' "$c_green" "  ✓ $*" "$c_reset"; }
warn() { printf '%s%s%s\n' "$c_yellow" "  ! $*" "$c_reset" >&2; }
die()  { printf '%s%s%s\n' "$c_red" "  ✗ $*" "$c_reset" >&2; exit 1; }

# --- 1. preflight --------------------------------------------------------------
say "preflight"
command -v docker >/dev/null || die "docker is not installed. Install Docker Desktop and re-run."
command -v uv >/dev/null     || die "uv is not installed. Install from https://docs.astral.sh/uv/ and re-run."
command -v npm >/dev/null    || die "npm is not installed. Install Node 22+ and re-run."
docker info >/dev/null 2>&1  || die "docker daemon is not running. Start Docker Desktop and re-run."

port_busy() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }
for p in 3000 8000 54321; do
  if port_busy "$p"; then
    die "port $p is already in use (free it, or stop the process on it). Note: 54321 conflicts with a running supabase CLI stack - stop it first."
  fi
done
# 5432 is only a problem if it is NOT our wren-db container.
if port_busy 5432; then
  if ! docker ps --format '{{.Names}}' | grep -qx wren-db-1; then
    die "port 5432 is in use by something other than wren-db-1. Stop it or change DATABASE_URL."
  fi
fi
ok "tools present, demo ports free"

# --- 2. backend/.env -----------------------------------------------------------
say "backend env"
BACKEND_ENV="$ROOT/backend/.env"
if [[ ! -f "$BACKEND_ENV" ]]; then
  cp "$ROOT/.env.example" "$BACKEND_ENV"
  # The migrate runner fails closed on the 'change-me' password placeholder
  # (and on empty/unsafe values); replace it immediately with a generated one.
  generated_pw="wren$(openssl rand -hex 12)"
  # Portable in-place edit (no sed -i portability concerns).
  awk -v pw="$generated_pw" 'BEGIN{FS=OFS="="} $1=="WREN_APP_DB_PASSWORD"{$2=pw} {print}' \
    "$BACKEND_ENV" > "$BACKEND_ENV.tmp" && mv "$BACKEND_ENV.tmp" "$BACKEND_ENV"
  ok "created backend/.env from .env.example (generated WREN_APP_DB_PASSWORD)"
else
  ok "backend/.env exists (left untouched)"
fi

# Append-only: ensure SUPABASE_JWT_SECRET and SUPABASE_URL exist. Never overwrite
# a value the developer already set.
ensure_env_key() {  # ensure_env_key <file> <key> <value>
  local file="$1" key="$2" val="$3"
  if grep -qE "^${key}=" "$file"; then
    cur="$(grep -E "^${key}=" "$file" | head -1 | cut -d= -f2-)"
    if [[ -z "$cur" ]]; then
      awk -v k="$key" -v v="$val" 'BEGIN{FS=OFS="="} $1==k{$2=v} {print}' "$file" > "$file.tmp" \
        && mv "$file.tmp" "$file"
      ok "set empty $key in $(basename "$file")"
    fi
  else
    printf '%s=%s\n' "$key" "$val" >> "$file"
    ok "added missing $key to $(basename "$file")"
  fi
}

# Read a value out of an env file (empty if absent/unset).
env_val() { grep -E "^$1=" "$2" 2>/dev/null | head -1 | cut -d= -f2- || true; }

jwt_secret="$(env_val SUPABASE_JWT_SECRET "$BACKEND_ENV")"
if [[ -z "$jwt_secret" ]]; then
  jwt_secret="$(openssl rand -hex 32)"
  ensure_env_key "$BACKEND_ENV" SUPABASE_JWT_SECRET "$jwt_secret"
else
  ok "SUPABASE_JWT_SECRET already set in backend/.env"
fi
ensure_env_key "$BACKEND_ENV" SUPABASE_URL "http://localhost:54321"

# Warn (do not edit) on known-bad states.
if [[ "$(env_val WREN_APP_DB_PASSWORD "$BACKEND_ENV")" == "change-me" ]]; then
  warn "WREN_APP_DB_PASSWORD is still 'change-me' in backend/.env - the migrate runner will fail. Set a real value (min 8 chars, no quotes/backslashes/\$)."
fi
if [[ -z "$(env_val LLM_API_KEY "$BACKEND_ENV")" ]]; then
  warn "LLM_API_KEY is empty - live chat will fall back to errors, but seeded transcripts keep the demo working. See .env.example for free-tier options."
fi

# --- 3. start containers (db + auth + auth-proxy) ------------------------------
say "containers"
export SUPABASE_JWT_SECRET="$jwt_secret"  # compose interpolates this into GoTrue

# db first: GoTrue's first migration assumes the `auth` schema already exists
# (it creates tables as auth.* but does not create the schema), so the schema
# must be present before auth starts. Creating it here is idempotent.
docker compose up -d db
for _ in $(seq 1 30); do
  if docker compose exec -T db pg_isready -U postgres -d wren >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
docker compose exec -T db pg_isready -U postgres -d wren >/dev/null 2>&1 \
  || die "postgres did not become ready. Try 'docker compose logs db'."
docker compose exec -T db psql -U postgres -d wren -c "create schema if not exists auth;" >/dev/null \
  || die "could not create the auth schema (GoTrue needs it before its first migration)."

docker compose up -d auth auth-proxy

# Wait for the GoTrue health endpoint (through the auth-proxy on 54321).
auth_ready=false
for _ in $(seq 1 40); do
  if curl -fsS http://localhost:54321/health >/dev/null 2>&1; then
    auth_ready=true
    break
  fi
  sleep 1
done
[[ "$auth_ready" == true ]] \
  || die "GoTrue did not become healthy on http://localhost:54321/health. Try 'docker compose logs auth'. (A JWT-secret change against an old volume is harmless - GoTrue signs at request time; if migrations are corrupted, 'docker compose exec db psql -U postgres -d wren -c \"drop schema if exists auth cascade; create schema auth;\"' then rerun.)"
ok "db + GoTrue (auth) + auth-proxy up"

# --- 4. backend: deps + migrate + seed -----------------------------------------
say "backend"
( cd backend && uv sync )
( cd backend && uv run python -m app.core.migrate )
ok "migrations applied"
say "seeding demo world (first run downloads the embedder model - this can take a minute)"
( cd backend && uv run python -m seeds.seed_demo )
ok "demo world seeded"

# --- 5. frontend/.env.local (targeted fix of exactly three keys) ---------------
say "frontend env"
FE_ENV="$ROOT/frontend/.env.local"
need_backup=false
if [[ -f "$FE_ENV" ]]; then need_backup=true; fi

set_fe_key() {  # set_fe_key <key> <value>
  local key="$1" val="$2" old=""
  if grep -qE "^${key}=" "$FE_ENV"; then
    old="$(grep -E "^${key}=" "$FE_ENV" | head -1 | cut -d= -f2-)"
    if [[ "$old" != "$val" ]]; then
      awk -v k="$key" -v v="$val" 'BEGIN{FS=OFS="="} $1==k{$2=v} {print}' "$FE_ENV" > "$FE_ENV.tmp" \
        && mv "$FE_ENV.tmp" "$FE_ENV"
      warn "$key: $old -> $val"
    fi
  else
    printf '%s=%s\n' "$key" "$val" >> "$FE_ENV"
  fi
}

anon_key="$(cd backend && uv run python -m seeds.supabase_keys anon)"
api_url="http://localhost:8000"
supabase_url="http://localhost:54321"

if [[ "$need_backup" == true ]]; then
  cp "$FE_ENV" "$FE_ENV.bak"
  ok "backed up existing frontend/.env.local to frontend/.env.local.bak"
fi
set_fe_key NEXT_PUBLIC_API_URL "$api_url"
set_fe_key NEXT_PUBLIC_SUPABASE_URL "$supabase_url"
set_fe_key NEXT_PUBLIC_SUPABASE_ANON_KEY "$anon_key"
ok "frontend/.env.local ready (API=$api_url, SUPABASE_URL=$supabase_url, anon key minted)"

# --- 6. frontend deps ----------------------------------------------------------
say "frontend deps"
if [[ ! -d frontend/node_modules ]]; then
  ( cd frontend && npm install )
  ok "frontend deps installed"
else
  ok "frontend deps already installed"
fi

# --- 7. run (backend + frontend dev servers) -----------------------------------
say "starting dev servers"
( cd backend && uv run uvicorn app.main:app --port 8000 ) &
BACKEND_PID=$!
( cd frontend && npm run dev ) &
FRONTEND_PID=$!

cleanup() {
  echo
  say "shutting down"
  kill "$BACKEND_PID" 2>/dev/null || true
  kill "$FRONTEND_PID" 2>/dev/null || true
  docker compose stop auth auth-proxy >/dev/null 2>&1 || true
  # db stays up for a quick rerun; use `docker compose down` to tear it out.
  wait "$BACKEND_PID" 2>/dev/null || true
  wait "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Give the servers a moment, then print the banner.
sleep 3
cat <<EOF

${c_green}${c_bold}Wren demo is up.${c_reset}

  ${c_bold}Customer chat${c_reset}   http://bytefix.localhost:3000    (no login)
                http://lumident.localhost:3000
  ${c_bold}Tenant console${c_reset}  http://app.localhost:3000/login   owner@bytefix.dev  / wren-demo
                http://app.localhost:3000/login   owner@lumident.dev / wren-demo
  ${c_bold}Platform${c_reset}        http://admin.localhost:3000      founder@wren.dev   / wren-demo

  ${c_dim}Guide: docs/DEMO.md${c_reset}
  ${c_dim}Ctrl-C stops both dev servers; db + auth stay up for a quick rerun.${c_reset}
  ${c_dim}Free-tier LLM may rate-limit live chat; seeded transcripts do not depend on it.${c_reset}

EOF

wait
