#!/usr/bin/env bash
# Hugging Face Space entrypoint: local Postgres + Redis (unless DATABASE_URL / REDIS_URL point to managed
# services), then every GigBid service via scripts/run_stack.py on $PORT (7860).
set -euo pipefail
PGDATA="${PGDATA:-$HOME/pgdata}"
PGBIN="$(ls -d /usr/lib/postgresql/*/bin | head -1)"

if [[ -z "${DATABASE_URL:-}" ]]; then
  if [[ ! -d "$PGDATA" ]]; then
    "$PGBIN/initdb" -D "$PGDATA" -U gigbid --auth=trust >/dev/null
  fi
  "$PGBIN/pg_ctl" -D "$PGDATA" -o "-k /tmp -p 5432 -c listen_addresses=127.0.0.1" -l "$HOME/pg.log" start
  for i in $(seq 1 30); do "$PGBIN/pg_isready" -h 127.0.0.1 -p 5432 >/dev/null && break; sleep 1; done
  "$PGBIN/createdb" -h 127.0.0.1 -U gigbid gigbid 2>/dev/null || true
  export DATABASE_URL="postgresql://gigbid@127.0.0.1:5432/gigbid"
fi
if [[ -z "${REDIS_URL:-}" ]]; then
  redis-server --daemonize yes --bind 127.0.0.1 --port 6379 --save "" --appendonly no
  export REDIS_URL="redis://127.0.0.1:6379/0"
fi
exec python -m scripts.run_stack
