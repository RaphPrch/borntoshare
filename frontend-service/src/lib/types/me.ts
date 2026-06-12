import type { Role } from './identity';

export type Me = {
  id: number;
  username: string;
  display_name?: string | null;
  email?: string | null;
  roles: string[];
  is_admin: boolean;
};

function toNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

export function normalizeMe(raw: unknown): Me {
  const obj = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>;

  const id =
    toNumber(obj.identity_id) ??
    0;

  const username = String(
    obj.username ?? obj.display_name ?? obj.email ?? (id > 0 ? `user-${id}` : 'anonymous')
  ).trim();

  const roles = Array.isArray(obj.roles)
    ? obj.roles.map((r) => String(r).trim()).filter(Boolean)
    : [];

  const isAdminRole = roles.some((role) => {
    const normalized = role.toLowerCase();
    return normalized === 'platform_admin' || normalized === 'admin';
  });

  return {
    id,
    username,
    display_name: obj.display_name == null ? null : String(obj.display_name),
    email: obj.email == null ? null : String(obj.email),
    roles,
    is_admin: isAdminRole
  };
}

export function isAdmin(me: Me | null | undefined): boolean {
  return me?.is_admin === true;
}

export function hasRole(me: Me | null | undefined, role: Role | string): boolean {
  if (!me) return false;
  return me.roles.some((r) => r.toLowerCase() === String(role).toLowerCase());
}
