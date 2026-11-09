#!/usr/bin/env python3
"""Issue BornToShare license keys (Ed25519), OUTSIDE the application.

    python issue_license.py init  --key ~/.b2s-license/issuer_ed25519.pem         # once: the key pair
    python issue_license.py issue --key ~/.b2s-license/issuer_ed25519.pem \\
        --customer "CORP" --features fives --expires 2027-12-31 [--limit max_tb=40]

The private key never goes into the repository nor the application: only its public key is embedded
(core-service/app/core/license_keys.py). A key is: B2S- + base32(version, payload length, JSON payload, signature),
in groups of 5 characters. The application checks it offline.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import struct
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

VERSION = 1


def encode(payload: dict, private: Ed25519PrivateKey) -> str:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    head = struct.pack(">BH", VERSION, len(body))
    blob = head + body + private.sign(head + body)
    text = base64.b32encode(blob).decode().rstrip("=")
    return "B2S-" + "-".join(text[i:i + 5] for i in range(0, len(text), 5))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["init", "issue", "public"])
    parser.add_argument("--key", required=True, type=Path)
    parser.add_argument("--customer", default="")
    parser.add_argument("--features", default="")
    parser.add_argument("--expires", default="")
    parser.add_argument("--limit", action="append", default=[])
    args = parser.parse_args()
    key_path = args.key.expanduser()
    if args.command == "init":
        if key_path.exists():
            print(f"{key_path} already exists", file=sys.stderr)
            return 1
        key_path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(key_path.parent, 0o700)
        private = Ed25519PrivateKey.generate()
        pem = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(pem)
    private = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    if args.command in {"init", "public"}:
        print(private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode())
        return 0
    features = sorted({item.strip() for item in args.features.split(",") if item.strip()})
    if not features or not args.customer:
        print("--customer and --features are required", file=sys.stderr)
        return 1
    limits = {}
    for item in args.limit:
        name, _, value = item.partition("=")
        limits[name.strip()] = int(value) if value.strip().isdigit() else value.strip()
    payload = {"lic": secrets.token_hex(6), "cust": args.customer, "feat": features, "iat": datetime.now(timezone.utc).date().isoformat(),
               "exp": date.fromisoformat(args.expires).isoformat() if args.expires else None, "lim": limits}
    print(encode(payload, private))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
