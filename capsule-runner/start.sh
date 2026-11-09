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

# Interactive jobs (tests, ACL, groups) and the long walks of folders in separate processes: a scan of millions of
# files never delays a test. SCAN_THREADS: walks at the same time (each one reads its file server).
dramatiq app.jobs.tasks --queues capsule_identity capsule_provisioning capsule_acl capsule_probes &
dramatiq app.jobs.tasks --queues capsule_scans --processes 1 --threads "${SCAN_THREADS:-2}" &

# Exit as soon as one of them exits
wait -n
exit $?
