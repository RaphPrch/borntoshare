# Actor Context V1 — Foundation (Zero Trust Prep)

## Purpose

This note documents the V1 foundation for future ephemeral identity handling.

The current authentication model remains cookie-session based (`b2s_session`) with
an additional short-lived principal snapshot cookie (`b2s_principal`).

The actor context is introduced as a non-breaking placeholder for V2+.

## Model

`app/core/actor_context.py` defines:

- `ActorContext`
- `build_actor_context_placeholder(user, ...)`

Shape:

```json
{
  "actor_id": "actor:123:1710000000",
  "subject_id": 123,
  "scope": ["ui:ssr"],
  "elevation": "standard",
  "issued_at": "2026-03-11T11:00:00+00:00",
  "expires_at": "2026-03-11T11:05:00+00:00"
}
```

## Current usage in V1

- Exposed via placeholder endpoint:
  - `GET /auth/actor-context/placeholder`
- Endpoint requires authenticated session (`get_current_user`)
- No enforcement yet in RBAC-sensitive actions

## Future integration targets

Planned progressive adoption for:

- admin critical operations
- secret resolution workflows
- AD-sensitive operations
- capsule executions
- sensitive approval flows

## Compatibility

This foundation is additive and does not change existing frontend/auth contracts.
