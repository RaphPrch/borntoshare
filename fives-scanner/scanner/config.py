"""Settings of the scanner, from its environment."""
from __future__ import annotations

import os
import socket

CORE_URL = os.getenv("CORE_URL", "http://core-service:8000").rstrip("/")
INTERNAL_TOKEN = os.getenv("INTERNAL_TOKEN", "")
DB_HOST = os.getenv("FIVES_DB_HOST", "localhost")
DB_PORT = int(os.getenv("FIVES_DB_PORT", "3306"))
DB_USER = os.getenv("FIVES_DB_USER", "b2s_fives")
DB_PASSWORD = os.getenv("FIVES_DB_PASSWORD", "")
DB_NAME = os.getenv("FIVES_DB_NAME", "b2s_fives")
INVENTORY_DB_NAME = os.getenv("FIVES_INVENTORY_DB_NAME", "b2s_fives_inventory")
# Each instance has its own name (one per site): it is seen in the 5S › Scanner page
SCANNER_ID = os.getenv("SCANNER_ID", "") or socket.gethostname()
POLL_SECONDS = int(os.getenv("SCANNER_POLL_SECONDS", "10"))
# Walks at a time in this instance (the limit per server still applies)
THREADS = int(os.getenv("SCANNER_THREADS", "2"))
