export type FetchLike = (
  input: RequestInfo | URL,
  init?: RequestInit
) => Promise<Response>;

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | 'HEAD';

export type HttpRequestOptions = {
  method: HttpMethod;
  path: string;
  body?: unknown;
  params?: Record<string, unknown>;
  headers?: HeadersInit;
  timeoutMs?: number;
  credentials?: RequestCredentials;
  basePath?: string;
};

