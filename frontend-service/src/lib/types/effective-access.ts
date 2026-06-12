export type EffectiveAccess = {
  storage_root_id: number;
  actor_id: number;
  access_level: string;
  source: 'request' | 'inherited' | 'manual' | 'unknown' | string;
  granted_at: string | null; // ISO date
  expires_at: string | null; // ISO date | null
};
