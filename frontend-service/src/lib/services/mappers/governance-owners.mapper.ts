export type GovernanceOwnerLike = Record<string, unknown>;

export type GovernanceOwnerCardVM = {
  title: string;
  subtitle: string | null;
  tertiary: string | null;
  typeLabel: 'User' | 'Group';
  iconKind: 'user' | 'group';
  iconClass: string;
};

const toText = (value: unknown): string => String(value ?? '').trim();

const normalizeType = (row: GovernanceOwnerLike, fallbackType?: string): 'user' | 'group' => {
  const raw = toText(row?.identity_type ?? row?.type ?? fallbackType).toLowerCase();
  return raw.includes('group') ? 'group' : 'user';
};

const resolveTitle = (row: GovernanceOwnerLike, fallbackDisplayName?: string): string => {
  const fromFallback = toText(fallbackDisplayName);
  if (fromFallback) return fromFallback;

  return (
    toText(row?.display_name) ||
    toText(row?.name) ||
    toText(row?.username) ||
    toText(row?.email) ||
    'Unknown user'
  );
};

const resolveSubtitle = (row: GovernanceOwnerLike): string | null => {
  const value =
    toText(row?.email) ||
    toText(row?.mail) ||
    toText(row?.upn) ||
    toText(row?.username) ||
    toText(row?.sam_account_name);

  return value || null;
};

const resolveTertiary = (row: GovernanceOwnerLike, subtitle: string | null): string | null => {
  const normalizedSubtitle = toText(subtitle).toLowerCase();
  const candidates = [row?.username, row?.upn, row?.sam_account_name, row?.external_id]
    .map((value) => toText(value))
    .filter(Boolean);

  const distinct = candidates.find((value) => value.toLowerCase() !== normalizedSubtitle);
  return distinct || null;
};

export const mapGovernanceOwnerToCardVM = (
  owner: GovernanceOwnerLike,
  options?: { displayName?: string; typeLabel?: string }
): GovernanceOwnerCardVM => {
  const iconKind = normalizeType(owner, options?.typeLabel);
  const subtitle = resolveSubtitle(owner);

  return {
    title: resolveTitle(owner, options?.displayName),
    subtitle,
    tertiary: resolveTertiary(owner, subtitle),
    typeLabel: iconKind === 'group' ? 'Group' : 'User',
    iconKind,
    iconClass: iconKind === 'group' ? 'bi-people' : 'bi-person'
  };
};

