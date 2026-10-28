#!/bin/bash
# Worker entrypoint: the Dramatiq worker (jobs) and, when enabled, the agent API (checked by core-service).
# The container stops when either process stops, so the orchestrator restarts it.
set -eu

if [ "${AGENT_ENABLED:-true}" = "true" ]; then
  if [ -n "${AGENT_TLS_CERT:-}" ] && [ -n "${AGENT_TLS_KEY:-}" ]; then
    uvicorn app.main:app --host 0.0.0.0 --port "${AGENT_PORT:-8443}" --no-access-log \
      --ssl-certfile "$AGENT_TLS_CERT" --ssl-keyfile "$AGENT_TLS_KEY" &
  else
    echo "WARNING: agent without TLS (AGENT_TLS_CERT / AGENT_TLS_KEY unset): use it on an internal network only" >&2
    uvicorn app.main:app --host 0.0.0.0 --port "${AGENT_PORT:-8443}" --no-access-log &
  fi
fi

dramatiq app.jobs.tasks &

# Exit as soon as one of them exits
wait -n
exit $?
