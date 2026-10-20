import { t } from '$lib/i18n';
import { asRecord } from '../utils/values';

type ProbeErrorType =
  | 'VALIDATION'
  | 'NETWORK'
  | 'SECRET'
  | 'CAPSULE'
  | 'TIMEOUT'
  | 'UNKNOWN';

export type NormalizedProbeError = {
  type: ProbeErrorType;
  message: string;
  technical?: string;
};

const contains = (msg: string, needle: string) =>
  msg.toLowerCase().includes(needle.toLowerCase());

function pickString(record: Record<string, unknown> | null, key: string): string | null {
  if (!record) return null;
  const value = record[key];
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

export function normalizeProbeError(e: unknown): NormalizedProbeError {
  const rec = asRecord(e);
  const raw =
    pickString(rec, 'message') ??
    pickString(rec, 'errorMessage') ??
    pickString(rec, 'error') ??
    'Unknown error';
  const technical = pickString(rec, 'technical') ?? raw;

  if (contains(raw, 'missing required') || contains(raw, 'required field') || contains(raw, 'invalid')) {
    return { type: 'VALIDATION', message: t('Please check the required fields.'), technical };
  }
  if (contains(raw, 'timeout')) {
    return { type: 'TIMEOUT', message: t('Probe timed out. Please try again.'), technical };
  }
  if (contains(raw, 'network') || contains(raw, 'failed to fetch') || contains(raw, 'fetch')) {
    return { type: 'NETWORK', message: t('Network connection failed.'), technical };
  }
  if (contains(raw, 'secret') || contains(raw, 'vault') || contains(raw, 'broker')) {
    return { type: 'SECRET', message: t('Secret resolution failed.'), technical };
  }
  if (contains(raw, 'capsule') || contains(raw, 'probe') || contains(raw, 'execution')) {
    return { type: 'CAPSULE', message: t('Probe execution failed.'), technical };
  }
  return { type: 'UNKNOWN', message: t('Unexpected error.'), technical };
}
