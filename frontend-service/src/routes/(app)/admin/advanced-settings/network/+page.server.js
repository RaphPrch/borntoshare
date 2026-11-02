import { apiServerGetData } from '$lib/server/api-server';

export async function load(event) {
  const dns = await apiServerGetData('/admin/network/dns', event).catch(() => null);
  return { configured: dns?.configured ?? [], proposed: dns?.proposed ?? [], failed: dns === null };
}
