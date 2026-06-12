import type { PageServerLoad } from './$types';
import { requireAuth } from '$lib/utils/requireAuth.server';
import { apiServerGetData } from '$lib/server/api-server';

type IdentityOverviewItem = Record<string, unknown>;

const toItemsFromObject = (payload: Record<string, unknown>): IdentityOverviewItem[] => {
  const users = Array.isArray(payload?.users) ? (payload.users as IdentityOverviewItem[]) : [];
  const groups = Array.isArray(payload?.groups) ? (payload.groups as IdentityOverviewItem[]) : [];
  const items = Array.isArray(payload?.items) ? (payload.items as IdentityOverviewItem[]) : [];
  if (items.length > 0) return items;
  return [...users, ...groups];
};

const splitByType = (items: IdentityOverviewItem[]) => ({
  users: items.filter((item) => String(item?.type ?? 'user').toLowerCase() !== 'group'),
  groups: items.filter((item) => String(item?.type ?? '').toLowerCase() === 'group')
});

export const load: PageServerLoad = async (event) => {
  await requireAuth(event);

  const payload = await apiServerGetData<unknown>('/identity', event);

  if (Array.isArray(payload)) {
    const items = payload as IdentityOverviewItem[];
    const { users, groups } = splitByType(items);
    return { users, groups, items };
  }

  const normalizedPayload = payload && typeof payload === 'object' ? (payload as Record<string, unknown>) : {};
  const items = toItemsFromObject(normalizedPayload);
  const grouped = splitByType(items);

  return {
    users: grouped.users,
    groups: grouped.groups,
    items
  };
};
