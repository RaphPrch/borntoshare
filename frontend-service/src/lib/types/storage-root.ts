
import type { UUID, ISODate } from './common';

export interface StorageRoot {
  id: UUID;
  name: string;
  path: string;
  description?: string;
  created_at: ISODate;
  updated_at: ISODate;
}
