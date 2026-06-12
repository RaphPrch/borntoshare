import { clientRequest } from '../http/client-request';
import { ApiError } from '../http/errors';
import {
  type DataEnvelope,
  unwrapDataStrict,
  unwrapListStrict,
  unwrapObjectStrict
} from '../http/envelopes';
import type { FetchLike } from '../http/contract';

export type { FetchLike, DataEnvelope };
export { ApiError, unwrapDataStrict, unwrapListStrict, unwrapObjectStrict };

type TimeoutOptions = { timeoutMs?: number };

type QueryParams = Record<string, unknown>;

export const apiGet = <T>(
  fetchFn: FetchLike,
  path: string,
  params?: QueryParams
) =>
  clientRequest<T>(fetchFn, {
    method: 'GET',
    path,
    params
  });

export const apiPost = <T>(
  fetchFn: FetchLike,
  path: string,
  body?: unknown,
  options?: TimeoutOptions
) =>
  clientRequest<T>(fetchFn, {
    method: 'POST',
    path,
    body,
    timeoutMs: options?.timeoutMs
  });

export const apiPut = <T>(
  fetchFn: FetchLike,
  path: string,
  body?: unknown
) =>
  clientRequest<T>(fetchFn, {
    method: 'PUT',
    path,
    body
  });

export const apiPatch = <T>(
  fetchFn: FetchLike,
  path: string,
  body?: unknown
) =>
  clientRequest<T>(fetchFn, {
    method: 'PATCH',
    path,
    body
  });

export const apiDelete = <T>(
  fetchFn: FetchLike,
  path: string
) =>
  clientRequest<T>(fetchFn, {
    method: 'DELETE',
    path
  });

export const apiGetData = async <T>(
  fetchFn: FetchLike,
  path: string,
  params?: QueryParams
): Promise<T> => unwrapDataStrict<T>(await apiGet<unknown>(fetchFn, path, params), `GET ${path}`);

export const apiGetList = async <T>(
  fetchFn: FetchLike,
  path: string,
  params?: QueryParams
): Promise<T[]> => unwrapListStrict<T>(await apiGet<unknown>(fetchFn, path, params), `GET ${path}`);

export const apiPostData = async <T>(
  fetchFn: FetchLike,
  path: string,
  body?: unknown,
  options?: TimeoutOptions
): Promise<T> => unwrapDataStrict<T>(await apiPost<unknown>(fetchFn, path, body, options), `POST ${path}`);

export const apiPutData = async <T>(
  fetchFn: FetchLike,
  path: string,
  body?: unknown
): Promise<T> => unwrapDataStrict<T>(await apiPut<unknown>(fetchFn, path, body), `PUT ${path}`);

export const apiPatchData = async <T>(
  fetchFn: FetchLike,
  path: string,
  body?: unknown
): Promise<T> => unwrapDataStrict<T>(await apiPatch<unknown>(fetchFn, path, body), `PATCH ${path}`);

export const apiDeleteData = async <T>(
  fetchFn: FetchLike,
  path: string
): Promise<T> => unwrapDataStrict<T>(await apiDelete<unknown>(fetchFn, path), `DELETE ${path}`);
