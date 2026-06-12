import type { FetchLike, HttpRequestOptions } from './contract';
import { httpRequest } from './request';

const API_BASE = (import.meta as any).env?.VITE_API_BASE ?? '/api';

function resolveClientBasePath(): string {
  if (!API_BASE.startsWith('/')) {
    throw new Error('Invalid API_BASE configuration');
  }
  return API_BASE;
}

export async function clientRequest<T>(
  fetchFn: FetchLike,
  options: Omit<HttpRequestOptions, 'basePath' | 'credentials'>
): Promise<T> {
  return httpRequest<T>(fetchFn, {
    ...options,
    basePath: resolveClientBasePath(),
    credentials: 'include'
  });
}

