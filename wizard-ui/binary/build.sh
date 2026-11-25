#!/bin/bash
# Builds the wizard as a single executable, dist/b2s-wizard (Linux x86_64): no Python, no Podman needed to run it.
# Built in an AlmaLinux 9 container, so that it runs on RHEL 9 and every later system (glibc 2.34 or newer).
#   make wizard-binary            (then: WIZARD=binary make wizard, or make wizard on a host without Podman)
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p dist
podman run --rm -v "$PWD/wizard-ui:/src:ro,z" -v "$PWD/dist:/out:z" docker.io/library/almalinux:9 bash -ec '
  dnf -y -q install python3.12 python3.12-pip binutils >/dev/null
  python3.12 -m pip install -q --disable-pip-version-check -r /src/requirements.txt pyinstaller==6.11.1
  cp -r /src /tmp/w && cd /tmp/w
  python3.12 -m PyInstaller --onefile --name b2s-wizard --log-level WARN \
    --add-data backend/app/static:backend/app/static --add-data backend/app/sql:backend/app/sql \
    --collect-submodules uvicorn --collect-all mysql.connector binary/entry.py
  install -m 0755 dist/b2s-wizard /out/b2s-wizard'
echo "dist/b2s-wizard : $(du -h dist/b2s-wizard | cut -f1)"
