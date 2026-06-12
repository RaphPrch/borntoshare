from __future__ import annotations

from typing import List, Dict, Any
from sqlalchemy.orm import Session

from app.repositories.sql_view_repo import SQLViewRepo


class DirectoryGroupsViewsRepo(SQLViewRepo):
    """
    READ-ONLY repository
    --------------------
    Backed by SQL view: v_directory_groups

    - No writes
    - No business logic
    - No ORM models
    - View = source of truth
    """

    def __init__(self, db: Session):
        super().__init__(db)

    def list_all(self) -> List[Dict[str, Any]]:
        """
        Return all directory groups from v_directory_groups (read-only)
        """
        return self._all("SELECT * FROM v_directory_groups")

    # Standard name
    def list(self) -> List[Dict[str, Any]]:
        return self.list_all()
