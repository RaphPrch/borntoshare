type JsonObject = Record<string, unknown>;

export type DataEnvelope<T> = {
  data: T;
  meta?: Record<string, unknown>;
};

export function unwrapDataStrict<T>(payload: unknown, context = 'API response'): T {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new Error(`${context} must be an object envelope with a "data" field`);
  }

  const envelope = payload as JsonObject;
  if (!('data' in envelope)) {
    throw new Error(`${context} is missing required "data" field`);
  }

  return envelope.data as T;
}

export function unwrapListStrict<T>(payload: unknown, context = 'API list response'): T[] {
  const data = unwrapDataStrict<unknown>(payload, context);
  if (!Array.isArray(data)) {
    throw new Error(`${context} "data" field must be an array`);
  }
  return data as T[];
}

export function unwrapObjectStrict<T extends Record<string, unknown>>(
  payload: unknown,
  context = 'API object response'
): T {
  const data = unwrapDataStrict<unknown>(payload, context);
  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    throw new Error(`${context} "data" field must be an object`);
  }
  return data as T;
}
