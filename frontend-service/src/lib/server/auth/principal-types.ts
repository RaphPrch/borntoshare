export type PrincipalSnapshot = {
  id: number;
  username: string;
  display_name?: string | null;
  email?: string | null;
  roles: string[];
  is_admin: boolean;
  must_change_password?: boolean;
  ver: number;
  exp: number;
};

