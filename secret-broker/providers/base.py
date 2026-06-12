from __future__ import annotations
from abc import ABC, abstractmethod

class SecretProvider(ABC):
    @abstractmethod
    def can_resolve(self, secret_ref: str) -> bool: ...

    @abstractmethod
    def resolve(self, secret_ref: str) -> str: ...
