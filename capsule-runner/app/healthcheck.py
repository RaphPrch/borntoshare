"""Container healthcheck: the agent's /health, in HTTPS (8443, with certificates) or HTTP (8080), as start.sh chose."""
from __future__ import annotations

import ssl
import sys
import urllib.request
from pathlib import Path


def main() -> int:
    certs = Path("/etc/b2s/certs")
    https = (certs / "agent.crt").is_file() and (certs / "agent.key").is_file()
    url = "https://localhost:8443/health" if https else "http://localhost:8080/health"
    # The certificate is issued for the worker's name, not localhost: only the answer matters here
    context = ssl._create_unverified_context() if https else None
    try:
        urllib.request.urlopen(url, timeout=4, context=context)
        return 0
    except Exception as exc:
        print(f"{url}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
