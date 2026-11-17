import { serverSecret } from './secret-files';

/** X-Internal-Token: the token shared by every service (INTERNAL_TOKEN, a secret file), added by the BFF to each upstream call. */
export async function buildInternalHeaders(): Promise<HeadersInit> {
  const token = serverSecret('INTERNAL_TOKEN');
  return token ? { 'X-Internal-Token': token } : {};
}
