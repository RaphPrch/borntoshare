from __future__ import annotations
from abc import ABC, abstractmethod
from app.schemas.auth import UserInfo

class AuthProvider(ABC):
    name: str

    @abstractmethod
    async def authenticate(self, username: str, password: str) -> UserInfo:
        raise NotImplementedError

    async def change_password(self, username: str, current_password: str, new_password: str) -> None:
        raise NotImplementedError("change_password not supported")
