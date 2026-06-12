
import type { UUID, ISODate } from './common';

export type AccessRequestStatus =
  | 'pending'
  | 'approved'
  | 'enforced'
  | 'revoked'
  | 'rejected';

export interface AccessRequest {
  id: UUID;
  requester_id: UUID;
  storage_root_id: UUID;
  access_profile_id: UUID;
  status: AccessRequestStatus;
  justification?: string;
  expires_at?: ISODate | null;
  created_at: ISODate;
  updated_at: ISODate;
}
