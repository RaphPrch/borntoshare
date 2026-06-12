type RoleLike = string | null | undefined;

function normalizeRole(role: RoleLike): string {
  return String(role ?? '').trim().toLowerCase();
}

export function hasRole(roles: RoleLike[] | null | undefined, role: string): boolean {
  const expected = normalizeRole(role);
  return Array.isArray(roles) && roles.some((current) => normalizeRole(current) === expected);
}

export function isPlatformAdmin(roles: RoleLike[] | null | undefined): boolean {
  return hasRole(roles, 'platform_admin');
}

export function canDeleteManagedObject(roles: RoleLike[] | null | undefined): boolean {
  return isPlatformAdmin(roles) || hasRole(roles, 'admin');
}
