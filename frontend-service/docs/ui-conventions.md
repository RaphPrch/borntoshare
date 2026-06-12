# UI conventions

- `Create` uses a modal.
- `Edit` uses a drawer for richer objects.
- `Delete` uses a short centered confirm modal.
- `Delete` and `Remove` always use the danger style.
- Standard button variants reuse `EntityActionButton`: `primary`, `secondary`, `ghost`, `danger`.
- Toast error messages stay short and map common API statuses:
  `400` invalid request, `401` session expired, `403` action not allowed, `404` item not found, `409` item still used, `500` unexpected error.
- Prefer existing CSS tokens for primary, danger, surface, border, text, muted, radius and shadows.
