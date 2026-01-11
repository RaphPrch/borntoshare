# Auth ↔ DAL Contract (V2)

Date: 2025-12-31

This document defines the **internal** API contract between **auth-service** and **dal-service** for **local authentication**.
It is designed to be **V1-compatible** (no breaking change) while improving security.

## Goals

- DAL verifies credentials and returns a **verdict**, not secrets.
- **No password hashes** (or other sensitive secrets) are returned to auth-service.
- Auth-service remains responsible for **sessions/JWT**, **cookies**, **OIDC/Keycloak**, and user-facing auth flows.

---

## Endpoints

### V2 (preferred): Verify local credentials

**POST** `/internal/auth/local/verify`

Request:
```json
{
  "username": "admin",
  "password": "secret"
}
```

Success (200):
```json
{
  "identity_id": "123",
  "provider": "local",
  "is_active": true,
  "username": "admin",
  "display_name": "Admin",
  "email": "admin@example.org",
  "roles": ["platform_admin"]
}
```

Failure:
- `401` invalid credentials / disabled account

Notes:
- `roles` can be empty.
- `display_name` / `email` can be null.

---

### V1 legacy (kept for compatibility)

**POST** `/internal/auth/local-login`

Request (same as V2):
```json
{
  "username": "admin",
  "password": "secret"
}
```

Success (200) legacy shape:
```json
{
  "id": "123",
  "username": "admin",
  "display_name": "Admin",
  "email": "admin@example.org",
  "is_active": true,
  "roles": ["platform_admin"]
}
```

Failure:
- `401` invalid credentials / disabled account

---

## Migration plan

1. DAL exposes one endpoint:
   - `/internal/auth/local/verify` (V2)

2. Auth-service uses V2 by default via `DAL_VALIDATE_CREDENTIALS_PATH`.

3. Once all deployments are migrated and stable, V1 legacy can be removed.

---

## Security considerations

- DAL **must not** return `password_hash`.
- Auth-service should treat DAL as a trusted internal dependency but still handle:
  - retries / timeouts
  - normalized error messages
  - request-id propagation for traceability

