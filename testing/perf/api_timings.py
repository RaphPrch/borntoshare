"""Response times of the main screens' API routes, through the web interface (BFF), as a signed-in administrator.

    B2S_URL=http://127.0.0.1:3000 B2S_USER=admin B2S_PASSWORD_FILE=<file> python3 testing/perf/api_timings.py [N]

Each route is called N times (10 by default) after one warm-up call; prints the number of rows of the answer and the
median, 95th percentile and maximum in milliseconds. Read-only: nothing is created or changed.
"""
from __future__ import annotations

import http.cookiejar
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request

ROUTES = [
    "/storage-roots/context", "/identity", "/identity-sources", "/storage-endpoints", "/zones",
    "/access-requests", "/admin/jobs?limit=200", "/infrastructure/overview", "/dashboard/platform-overview",
]


def main() -> int:
    base = os.environ.get("B2S_URL", "http://127.0.0.1:3000").rstrip("/")
    origin = os.environ.get("B2S_ORIGIN", base)
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(method: str, path: str, body: dict | None = None) -> tuple[int, object]:
        request = urllib.request.Request(base + "/api" + path, method=method, data=json.dumps(body).encode() if body else None,
                                         headers={"Content-Type": "application/json", "Origin": origin})
        try:
            return 200, json.loads(opener.open(request, timeout=120).read() or b"{}")
        except urllib.error.HTTPError as exc:
            return exc.code, {}

    password = open(os.environ["B2S_PASSWORD_FILE"]).read().strip()
    status, _ = call("POST", "/auth/login", {"username": os.environ.get("B2S_USER", "admin"), "password": password, "provider": "local"})
    if status != 200:
        print(f"connexion refusée : HTTP {status}")
        return 1
    print(f"{'route':32} {'HTTP':>4} {'lignes':>7} {'médiane':>8} {'p95':>8} {'max':>8}  (ms, {runs} appels)")
    for path in ROUTES:
        status, payload = call("GET", path)
        data = payload.get("data", payload) if isinstance(payload, dict) else payload
        if isinstance(data, dict):
            data = data.get("items", data)
        count = len(data) if isinstance(data, list) else "-"
        times = []
        for _ in range(runs):
            started = time.perf_counter()
            call("GET", path)
            times.append((time.perf_counter() - started) * 1000)
        times.sort()
        p95 = times[max(0, int(round(0.95 * len(times))) - 1)]
        print(f"{path:32} {status:>4} {count!s:>7} {statistics.median(times):8.0f} {p95:8.0f} {times[-1]:8.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
