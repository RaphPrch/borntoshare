export interface AccessProfileConsoleOverview {
  access_profile_id: number;
  code: string | null;
  name: string | null;
  description: string | null;
  permission: string | null;
  access_level_code: string | null;
  is_active: boolean | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface AccessProfileConsoleBinding {
  resource_type: string;
  resource_id: number;
  resource_name?: string | null;
  zone_id?: number | null;
  zone_name?: string | null;
  created_at?: string | null;
}

export interface AccessProfileConsole {
  overview: AccessProfileConsoleOverview;
  bindings: AccessProfileConsoleBinding[];
  kpis: {
    bindings_count: number;
    used_in_roots_count: number;
    zones_count: number;
  };
}
