import { apiGetData } from '$lib/api/client';

/**
 * What the pages of the explorer share: the measured folders of the person (loaded once by the layout, read by
 * the tree and the table), and the sub-folders of the folder open on the folder page (shown inside the tree).
 * Filled in the browser only (onMount): nothing is kept between two people on the server.
 */
export type ParkFolder = {
  id: number;
  name: string;
  path: string;
  server: string | null;
  zone: string | null;
  size_bytes: number | null;
  score: number | null;
  dup_bytes?: number | null;
  sensitive_files?: number;
  measured_at?: string | null;
  tags?: string[];
};
export type SubItem = { key: string; name: string; depth: number; bytes: number; current: boolean };

export const park = $state<{ folders: ParkFolder[]; loading: boolean; error: string }>({ folders: [], loading: true, error: '' });
export const inside = $state<{ rootId: number | null; items: SubItem[]; pick: ((key: string) => void) | null }>({ rootId: null, items: [], pick: null });

export async function loadPark(fetchFn: typeof fetch, failure: string): Promise<void> {
  park.loading = true;
  park.error = '';
  try {
    const data = await apiGetData<{ folders: ParkFolder[] }>(fetchFn, '/modules/fives/five-s');
    park.folders = data?.folders ?? [];
  } catch (error) {
    park.error = error instanceof Error ? error.message : failure;
  } finally {
    park.loading = false;
  }
}

/** Zone or server of a folder as the tree and the address name it (« — » when the folder has none). */
export const placeOf = (value: string | null | undefined) => value || '—';
export const toneOf = (score: number | null | undefined) => (score == null ? 'mut' : score >= 80 ? 'ok' : score >= 60 ? 'warn' : 'bad');
