import { principalLabel, principalSubtitle } from '../../utils/principal-search';

export type PrincipalLike = Record<string, unknown>;

export type PrincipalDisplayVM = {
  title: string;
  subtitle: string;
  typeLabel: string;
  iconKind: 'user' | 'group' | 'neutral';
  iconClass: string;
};

const toText = (value: unknown): string => String(value ?? '').trim();

const normalizeType = (value: unknown): 'user' | 'group' | 'ou' | 'other' => {
  const raw = toText(value).toLowerCase();
  if (raw === 'user') return 'user';
  if (raw === 'group') return 'group';
  if (raw === 'ou') return 'ou';
  return 'other';
};

export const mapPrincipalToDisplayVM = (principal: PrincipalLike): PrincipalDisplayVM => {
  const normalizedType = normalizeType(principal?.type);
  const iconKind = normalizedType === 'group' ? 'group' : normalizedType === 'user' ? 'user' : 'neutral';

  return {
    title: principalLabel(principal),
    subtitle: principalSubtitle(principal),
    typeLabel:
      normalizedType === 'group'
        ? 'Group'
        : normalizedType === 'ou'
          ? 'OU'
          : normalizedType === 'user'
            ? 'User'
            : toText(principal?.type) || 'Identity',
    iconKind,
    iconClass:
      normalizedType === 'group'
        ? 'bi-people'
        : normalizedType === 'ou'
          ? 'bi-folder2-open'
          : normalizedType === 'user'
            ? 'bi-person'
            : 'bi-person-badge'
  };
};
