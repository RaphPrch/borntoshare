/**
 * Tag colours follow the family: each family gets one hue and its tags are shades of it, so a family reads at a
 * glance. Tags without a family are grey. The hue of a family comes from its name (stable, no setting to keep).
 */
const HUES: string[][] = [
  ['#dc2626', '#ea580c', '#b45309', '#be123c'],
  ['#2563eb', '#1d4ed8', '#0891b2', '#4f46e5'],
  ['#16a34a', '#65a30d', '#0d9488', '#15803d'],
  ['#9333ea', '#7c3aed', '#c026d3', '#a21caf'],
  ['#0f766e', '#0e7490', '#047857', '#155e75'],
  ['#ca8a04', '#a16207', '#d97706', '#854d0e']
];
const GREY = ['#6b7280', '#475569', '#78716c', '#64748b'];

export const fold = (value: unknown): string =>
  String(value ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();

export function familyShades(family: string | null | undefined): string[] {
  const key = fold(family);
  if (!key) return GREY;
  let hash = 0;
  for (const char of key) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return HUES[hash % HUES.length];
}

/** Same name (accents and case aside), or one letter apart / a plural away: « Finance » and « Finances ». */
export function nameClash(name: string, existing: string[]): { kind: 'same' | 'near'; name: string } | null {
  const wanted = fold(name);
  if (!wanted) return null;
  const same = existing.find((other) => fold(other) === wanted);
  if (same) return { kind: 'same', name: same };
  const near = existing.find((other) => {
    const known = fold(other);
    if (known.length < 3 || wanted.length < 3) return false;
    if (known.startsWith(wanted) || wanted.startsWith(known)) return Math.abs(known.length - wanted.length) <= 2;
    if (known.length !== wanted.length) return false;
    let differences = 0;
    for (let index = 0; index < known.length; index += 1) if (known[index] !== wanted[index]) differences += 1;
    return differences <= 1;
  });
  return near ? { kind: 'near', name: near } : null;
}
