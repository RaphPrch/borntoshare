#!/bin/sh
cd /opt/wizard/backend
exec uvicorn app.main:app --host 0.0.0.0 --port 8080