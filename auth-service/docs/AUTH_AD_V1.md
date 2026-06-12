# Auth AD V1 (VMware-like)

## Principles
- Active Directory is the authority.
- User passwords are never stored.
- A service account is used for search/bind.
- The service account password is resolved via Secret Broker.

## Flow
UI -> Frontend BFF -> Auth-service -> AD
                   |
                   -> Secret Broker (resolve env:// or file://)

## Why no capsule here?
Authentication must remain synchronous and local to Auth-service.
