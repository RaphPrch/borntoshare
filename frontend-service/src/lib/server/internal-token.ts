declare const process: {
  env: Record<string, string | undefined>;
};

/** X-Internal-Token: the token shared by every service (INTERNAL_TOKEN), added by the BFF to each upstream call. */
export async function buildInternalHeaders(): Promise<HeadersInit> {
  const token = (process.env.INTERNAL_TOKEN ?? '').trim();
  return token ? { 'X-Internal-Token': token } : {};
}
