from __future__ import annotations

import argparse
import json

from app.core.db import SessionLocal
from app.services.directory_effective_memberships_service import DirectoryEffectiveMembershipsService


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild directory_effective_memberships from active snapshot(s)")
    parser.add_argument("--snapshot-id", type=int, default=None)
    parser.add_argument("--identity-source-id", type=int, default=None)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        svc = DirectoryEffectiveMembershipsService(db)
        if args.snapshot_id:
            result = svc.rebuild_for_snapshot(snapshot_id=int(args.snapshot_id))
        elif args.identity_source_id:
            result = svc.rebuild_for_identity_source(identity_source_id=int(args.identity_source_id))
        else:
            result = {"results": svc.rebuild_all_active()}

        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    finally:
        db.close()


if __name__ == "__main__":
    main()

