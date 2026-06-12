from __future__ import annotations

from datetime import datetime

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.models.access_request import AccessRequest
from app.models.access_request_item import AccessRequestItem


class AccessRequestsRepo:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, request_id: int) -> AccessRequest | None:
        return self.db.get(AccessRequest, int(request_id))

    def create_with_items(
        self,
        *,
        request_data: dict,
        items: list[dict],
    ) -> AccessRequest:
        payload = dict(request_data)
        payload["status"] = str(payload.get("status") or "pending").lower()
        obj = AccessRequest(**payload)
        self.db.add(obj)
        self.db.flush()

        for item in items:
            self.db.add(
                AccessRequestItem(
                    access_request_id=int(obj.id),
                    target_type=str(item["target_type"]),
                    target_id=int(item["target_id"]),
                    permission=str(item["permission"]),
                    expires_at=item.get("expires_at"),
                )
            )

        self.db.commit()
        self.db.refresh(obj)
        return obj

    def bulk_decision(self, *, ids: list[int], decision: str, decision_comment: str | None = None) -> int:
        if not ids:
            return 0
        new_status = {"approve": "approved", "reject": "rejected", "revoke": "revoked"}.get(decision, decision)
        comment = str(decision_comment or "").strip() or None
        stmt = text(
            """
            UPDATE access_requests
            SET status = :status,
                decision_comment = CASE
                    WHEN :decision_comment IS NOT NULL THEN :decision_comment
                    ELSE decision_comment
                END,
                decided_at = CASE WHEN :status IN ('approved','rejected') THEN COALESCE(decided_at, :now) ELSE decided_at END,
                revoked_at = CASE WHEN :status = 'revoked' THEN COALESCE(revoked_at, :now) ELSE revoked_at END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id IN :ids
            """
        ).bindparams(bindparam("ids", expanding=True))
        res = self.db.execute(
            stmt,
            {
                "status": new_status,
                "ids": [int(i) for i in ids],
                "now": datetime.utcnow(),
                "decision_comment": comment,
            },
        )
        self.db.commit()
        return int(res.rowcount or 0)
