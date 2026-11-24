import type { ServerLoadEvent } from '@sveltejs/kit';
import { apiServerGetData } from '$lib/server/api-server';

export type FivesOffReason = 'license' | 'switched_off' | 'unreachable' | 'unknown';
type Feature = { key: string; enabled: boolean; licensed?: boolean; switched_on?: boolean; installed?: boolean };

/**
 * Why the 5S module is not usable, for the screens of the module (null when it is). Administrators read the detail
 * (license, switch, container); the others only learn that it is off.
 */
export async function fivesOff(
  event: ServerLoadEvent,
  context: { features?: string[]; isAdmin?: boolean }
): Promise<{ reason: FivesOffReason } | null> {
  if ((context.features ?? []).includes('fives')) return null;
  let reason: FivesOffReason = 'unknown';
  if (context.isAdmin) {
    const state = await apiServerGetData<{ features?: Feature[] }>('/features', event).catch(() => null);
    const fives = state?.features?.find((feature) => feature.key === 'fives');
    if (fives) reason = !fives.licensed ? 'license' : !fives.switched_on ? 'switched_off' : !fives.installed ? 'unreachable' : 'unknown';
  }
  return { reason };
}
