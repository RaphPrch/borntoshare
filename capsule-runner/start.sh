#!/bin/bash
# Worker entrypoint: the Dramatiq worker (jobs) and the agent API (checked by core-service).
# The agent is HTTPS on 8443 when capsule-runner/certs (mounted on /etc/b2s/certs) holds agent.crt and agent.key,
# HTTP on 8080 otherwise (internal network only). The container stops when either process stops.
set -eu

CERTS=/etc/b2s/certs
if [ -f "$CERTS/agent.crt" ] && [ -f "$CERTS/agent.key" ]; then
  uvicorn app.main:app --host 0.0.0.0 --port 8443 --no-access-log \
    --ssl-certfile "$CERTS/agent.crt" --ssl-keyfile "$CERTS/agent.key" &
else
  echo "WARNING: agent in HTTP on 8080 (no agent.crt / agent.key in $CERTS): internal network only" >&2
  uvicorn app.main:app --host 0.0.0.0 --port 8080 --no-access-log &
fi

dramatiq app.jobs.tasks &

# Exit as soon as one of them exits
wait -n
exit $?
