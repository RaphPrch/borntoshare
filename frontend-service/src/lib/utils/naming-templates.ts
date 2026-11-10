import { t } from '$lib/i18n';

/**
 * Naming of the AD groups: the tokens core-service accepts (app/services/naming_policy.py) and ready-made models.
 * A template names the folder ({ROOTCODE} or {RAND}) and the permission ({PERM}): one group per folder and access.
 */
export const NAMING_TOKENS = ['{PREFIX}', '{ZONE}', '{ROOTCODE}', '{RAND}', '{PERM}'] as const;
const ALLOWED = new Set(['PREFIX', 'ZONE', 'ROOTCODE', 'RAND', 'PERM']);

export const namingTokenHelp = (): { token: string; label: string }[] => [
  { token: '{PREFIX}', label: t('prefix') },
  { token: '{ZONE}', label: t('code of the zone') },
  { token: '{ROOTCODE}', label: t('storage root path') },
  { token: '{RAND}', label: t('random number, always the same for a folder') },
  { token: '{PERM}', label: t('RX (read) or RW (write)') }
];

export type NamingModel = { key: string; label: () => string; template: string };

export const NAMING_MODELS: NamingModel[] = [
  { key: 'path', label: () => t('Prefix, folder, permission'), template: '{PREFIX}_{ROOTCODE}_{PERM}' },
  { key: 'zone-path', label: () => t('Prefix, zone, folder, permission'), template: '{PREFIX}_{ZONE}_{ROOTCODE}_{PERM}' },
  { key: 'random', label: () => t('Prefix, random number, permission'), template: '{PREFIX}_{RAND}_{PERM}' },
  { key: 'zone-random', label: () => t('Prefix, zone, random number, permission'), template: '{PREFIX}_{ZONE}_{RAND}_{PERM}' },
  { key: 'perm-first', label: () => t('Prefix, permission, folder'), template: '{PREFIX}_{PERM}_{ROOTCODE}' }
];

/** Tokens unknown to core-service, and whether the template keeps one group per folder and per permission */
export function checkNamingTemplate(template: string): { unknown: string[]; unique: boolean } {
  const tokens = [...String(template ?? '').matchAll(/\{([A-Z_]+)\}/g)].map((match) => match[1]);
  return {
    unknown: [...new Set(tokens.filter((token) => !ALLOWED.has(token)))],
    unique: tokens.includes('PERM') && (tokens.includes('ROOTCODE') || tokens.includes('RAND'))
  };
}

/** A name shown as an example (the real one is computed by core-service for each folder) */
export function exampleGroupName(template: string, values: { prefix?: string; zone?: string; rootcode?: string } = {}): string {
  return String(template ?? '')
    .replaceAll('{PREFIX}', values.prefix || 'B2S')
    .replaceAll('{ZONE}', values.zone || 'CORP')
    .replaceAll('{ROOTCODE}', values.rootcode || 'ACHATS')
    .replaceAll('{RAND}', '482913')
    .replaceAll('{PERM}', 'RX')
    .toUpperCase();
}
