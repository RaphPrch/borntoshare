/**
 * Express entry of the new request page: one sentence such as
 * « lecture sur Achats et Compta pour 30 jours : clôture de novembre » fills the request.
 * Keywords and dates only, nothing is guessed: what is not found stays to fill in the steps.
 */
export type SentenceRoot = { id: number; name: string; path: string; dfsPath: string };
export type SentenceDuration = { days: number } | { date: string } | { permanent: true };
export type ParsedSentence = {
  level: 'READ' | 'WRITE' | null;
  rootIds: number[];
  /** A name shared by several folders: the user picks one in the list. */
  ambiguous: Array<{ term: string; ids: number[] }>;
  duration: SentenceDuration | null;
  reason: string;
};

const fold = (value: string) => value.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
const escapeRe = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const iso = (date: Date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;

function parseLevel(text: string): ParsedSentence['level'] {
  if (/\b(modif\w*|ecri\w*|ecrit\w*|write|rw)\b/.test(text)) return 'WRITE';
  if (/\b(lect\w*|lire|read|ro|consult\w*)\b/.test(text)) return 'READ';
  return null;
}

function parseDuration(text: string, now: Date): SentenceDuration | null {
  if (/\b(permanent\w*|sans fin|definiti\w*)\b/.test(text)) return { permanent: true };
  const until = text.match(/\b(?:jusqu'?\s*au|jusqu'?\s*a|until|au)\s+(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?/);
  if (until) {
    const day = Number(until[1]);
    const month = Number(until[2]);
    let year = until[3] ? Number(until[3]) : now.getFullYear();
    if (year < 100) year += 2000;
    let date = new Date(year, month - 1, day);
    if (!until[3] && date < now) date = new Date(year + 1, month - 1, day);
    if (date.getMonth() === month - 1 && date > now) return { date: iso(date) };
  }
  const amount = text.match(/\b(\d{1,3})\s*(j|jours?|days?|sem\w*|weeks?|mois|months?)\b/);
  if (amount) {
    const count = Number(amount[1]);
    const unit = amount[2];
    const days = /^(sem|week)/.test(unit) ? count * 7 : /^(mois|month)/.test(unit) ? count * 30 : count;
    if (days > 0) return { days };
  }
  return null;
}

function parseRoots(text: string, roots: SentenceRoot[]) {
  const ids = new Set<number>();
  const ambiguous: ParsedSentence['ambiguous'] = [];
  // A pasted UNC path (server or DFS) names exactly one folder
  for (const match of text.matchAll(/\\\\[^\s,;]+/g)) {
    const path = match[0].replace(/\\+$/, '');
    const root = roots.find((r) => fold(r.path) === path || fold(r.dfsPath) === path);
    if (root) ids.add(root.id);
  }
  const rest = text.replace(/\\\\[^\s,;]+/g, ' ');
  const byName = new Map<string, number[]>();
  for (const root of roots) {
    const name = fold(root.name);
    if (name.length < 3) continue;
    byName.set(name, [...(byName.get(name) ?? []), root.id]);
  }
  for (const [name, list] of byName) {
    if (!new RegExp(`(^|[^\\p{L}\\p{N}_])${escapeRe(name)}($|[^\\p{L}\\p{N}_])`, 'u').test(rest)) continue;
    if (list.some((id) => ids.has(id))) continue;
    if (list.length === 1) ids.add(list[0]);
    else ambiguous.push({ term: name, ids: list });
  }
  return { rootIds: [...ids], ambiguous };
}

export function parseRequestSentence(sentence: string, roots: SentenceRoot[], now = new Date()): ParsedSentence {
  const raw = String(sentence ?? '');
  // The reason comes after the first colon (a UNC path has none)
  const colon = raw.indexOf(':');
  const head = fold(colon >= 0 ? raw.slice(0, colon) : raw);
  const reason = colon >= 0 ? raw.slice(colon + 1).trim() : '';
  return { level: parseLevel(head), ...parseRoots(head, roots), duration: parseDuration(head, now), reason };
}
