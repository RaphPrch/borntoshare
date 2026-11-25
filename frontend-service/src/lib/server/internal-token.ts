declare const process: {
  env: Record<string, string | undefined>;
};

/**
 * Added by the BFF to each upstream call:
 * - X-Service-Token: the token of the web interface (B2S_SERVICE_TOKEN), by which core-service knows it is the BFF;
 * - X-Internal-Token: the token shared by the services (INTERNAL_TOKEN), still checked by auth-service and the
 *   5S module, and by core-service before make deploy gave each service its token.
 */
export async function buildInternalHeaders(): Promise<HeadersInit> {
  const headers: Record<string, string> = {};
  const shared = (process.env.INTERNAL_TOKEN ?? '').trim();
  const own = (process.env.B2S_SERVICE_TOKEN ?? '').trim();
  if (shared) headers['X-Internal-Token'] = shared;
  if (own) headers['X-Service-Token'] = own;
  return headers;
}
