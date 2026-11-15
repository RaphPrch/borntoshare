/**
 * Pilot: questions in plain French on the folders, answered from what BornToShare already knows (the context list
 * of the storage roots, the permissions of a folder: ACL read × directory × requests). No model, no guess: a few
 * intents read from the words of the question; the answer says how the question was understood.
 */
import { apiGetList, type FetchLike } from '$lib/api/client';
import { getStorageRootPermissions, type PermissionPerson } from '$lib/api/storage-root-permissions';
import { formatBytes, formatDate } from '$lib/utils/format';

export type PilotTone = 'ok' | 'warn' | 'bad' | 'mut' | 'info';
export type PilotCell = { text: string; tone?: PilotTone; mono?: boolean };
export type PilotAnswer = {
  question: string;
  /** How the question was understood, shown to the person (« dossier:TEST → personnes ») */
  intent: string;
  text: string;
  source: string;
  columns: string[];
  rows: PilotCell[][];
  /** File name of the CSV export (none: nothing to export) */
  file: string | null;
  /** Folders the answer is about, to open them */
  links: Array<{ label: string; href: string }>;
  ok: boolean;
};

type Root = Record<string, any>;

const num = (value: unknown) => (Number.isFinite(Number(value)) ? Number(value) : 0);
const fold = (value: unknown) => String(value ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
const name = (row: Root) => String(row.storage_root_name ?? row.storage_root_code ?? `#${row.storage_root_id}`);
const slug = (value: string) => fold(value).replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '') || 'export';
const size = (row: Root) => num(row.content_size_bytes ?? row.estimated_size_bytes);
const rootLink = (row: Root) => ({ label: name(row), href: `/storage-roots?selected=${row.storage_root_id}` });

export const PILOT_EXAMPLES = [
  'Exporte-moi tous les utilisateurs du dossier Finance',
  'Quels groupes donnent accès au dossier RH ?',
  'Quels dossiers contiennent des mots de passe ?',
  'Quotas au-delà de 85 %',
  'Dossiers jamais mesurés',
  'Dossiers sans gardien',
  'Les 10 plus gros dossiers',
  'Doublons à libérer',
  'Dossiers du serveur FILER01',
  'Données froides depuis plus d’un an'
];

/** The folder named in the question: after « dossier », else any folder whose name is in the question (longest first). */
function findFolder(question: string, roots: Root[]): { root: Root | null; asked: string | null; others: Root[] } {
  const quoted = question.match(/dossiers?\s+(?:«\s*|"|')?([^»"'?]+?)(?:\s*»|"|')?\s*(?:\?|$)/i);
  const asked = quoted ? quoted[1].trim() : null;
  const wanted = fold(asked);
  const byName = (row: Root) => fold(name(row));
  if (wanted) {
    const exact = roots.filter((row) => byName(row) === wanted || fold(row.storage_root_code) === wanted);
    if (exact.length) return { root: exact[0], asked, others: exact.slice(1) };
    const partial = roots.filter((row) => byName(row).includes(wanted) || fold(row.root_path).split(/[\\/]/).includes(wanted));
    if (partial.length) return { root: partial[0], asked, others: partial.slice(1) };
  }
  const q = fold(question);
  const named = roots.filter((row) => byName(row).length > 2 && q.includes(byName(row))).sort((a, b) => byName(b).length - byName(a).length);
  return { root: named[0] ?? null, asked, others: named.slice(1) };
}

const levelLabel = (level: string | null) => (level === 'write' ? 'Modification' : level === 'read' ? 'Lecture' : '—');
function viaLabel(person: PermissionPerson): string {
  return person.via
    .map((via) => (via.kind === 'request' ? `demande ${via.code}` : via.kind === 'outside' ? `hors BornToShare (${via.group})` : via.group))
    .filter((value, index, all) => all.indexOf(value) === index)
    .join(', ') || '—';
}

export async function askPilot(fetchFn: FetchLike, question: string): Promise<PilotAnswer> {
  const q = fold(question);
  const roots = await apiGetList<Root>(fetchFn, '/storage-roots/context').catch(() => [] as Root[]);
  const base = { question, ok: true, links: [] as PilotAnswer['links'] };
  const table = (rows: Root[]) => rows.slice(0, 200);

  // ---- people of a folder ----
  const wantsPeople = /utilisateur|personne|membre|qui (a|accede)|acces|droit/.test(q) && !/groupe/.test(q);
  const wantsGroups = /groupe/.test(q) && /dossier/.test(q);
  if (wantsPeople || wantsGroups) {
    const { root, asked, others } = findFolder(question, roots);
    if (!root) {
      return { ...base, ok: false, intent: `dossier:${asked ?? '?'}`, source: '', columns: [], rows: [], file: null,
        text: asked ? `Aucun dossier « ${asked} » parmi les ${roots.length} dossiers que vous voyez. Vérifiez son nom dans Storage Roots.` : 'Quel dossier ? Écrivez par exemple « utilisateurs du dossier Finance ».' };
    }
    const data = await getStorageRootPermissions(fetchFn, Number(root.storage_root_id));
    const scanned = data.acl_scanned_at ? `ACL lue le ${formatDate(data.acl_scanned_at)}` : 'ACL jamais lue';
    const synced = data.snapshot_at ? `annuaire du ${formatDate(data.snapshot_at)}` : 'annuaire non synchronisé';
    const more = others.length ? ` (${others.length} autre(s) dossier(s) portent un nom proche)` : '';
    if (wantsGroups) {
      return { ...base, intent: `dossier:${name(root)} → groupes`, source: `${scanned} · ${synced}`, links: [rootLink(root)],
        text: `${data.groups.length} groupe(s) donnent accès à ${name(root)}${more} ; ${data.gaps.length} entrée(s) hors règle dans son ACL.`,
        columns: ['Groupe', 'Droit', 'Membres', 'Dans l’ACL'],
        rows: data.groups.map((group) => [{ text: group.name, mono: true }, { text: levelLabel(group.level) }, { text: String(group.members_count) },
          { text: group.ace === 'ok' ? 'Présent' : group.ace === 'missing' ? 'Manquant' : group.ace === 'mismatch' ? 'Droit différent' : 'Inconnu', tone: group.ace === 'ok' ? 'ok' : group.ace === 'unknown' ? 'mut' : 'bad' }]),
        file: `${slug(name(root))}_groupes.csv` };
    }
    const people = data.people;
    const write = people.filter((person) => person.level === 'write').length;
    return { ...base, intent: `dossier:${name(root)} → personnes`, source: `${scanned} · ${synced}`, links: [rootLink(root)],
      text: `${people.length} personne(s) accèdent à ${name(root)}${more} : ${write} en modification, ${people.length - write} en lecture.${data.summary.expiring_30d ? ` ${data.summary.expiring_30d} accès se terminent dans les 30 jours.` : ''}`,
      columns: ['Personne', 'Login', 'Droit', 'Par', 'Jusqu’au'],
      rows: people.map((person) => [{ text: person.name }, { text: person.username ?? '—', mono: true }, { text: levelLabel(person.level), tone: person.level === 'write' ? 'warn' : 'info' },
        { text: viaLabel(person), tone: person.via.some((via) => via.kind === 'outside') ? 'warn' : undefined }, { text: person.expires_at ? formatDate(person.expires_at) : 'Sans fin' }]),
      file: `${slug(name(root))}_utilisateurs.csv` };
  }

  // ---- lists of folders ----
  const folderRows = (list: Root[], extra: Array<[string, (row: Root) => PilotCell]>) =>
    table(list).map((row) => [{ text: name(row) }, { text: String(row.storage_endpoint_name ?? '—'), mono: true }, ...extra.map(([, value]) => value(row))]);
  const folderAnswer = (intent: string, text: string, source: string, list: Root[], extra: Array<[string, (row: Root) => PilotCell]>, file: string): PilotAnswer => ({
    ...base, intent, text, source, columns: ['Dossier', 'Serveur', ...extra.map(([header]) => header)], rows: folderRows(list, extra), file: list.length ? file : null, links: list.slice(0, 5).map(rootLink) });

  const server = question.match(/serveur\s+([\w.-]+)/i);
  if (server) {
    const wanted = fold(server[1]);
    const list = roots.filter((row) => fold(row.storage_endpoint_name).includes(wanted));
    return folderAnswer(`serveur:${server[1]}`, `${list.length} dossier(s) sur un serveur nommé « ${server[1]} ».`, 'Storage Roots', list,
      [['Volume', (row) => ({ text: size(row) ? formatBytes(size(row)) : '—' })], ['Gardiens', (row) => ({ text: String(num(row.guardians_count)), tone: num(row.guardians_count) ? undefined : 'warn' })]], `serveur_${slug(server[1])}.csv`);
  }
  if (/passe|secret|cle|jeton|sensib|personnel/.test(q)) {
    const list = roots.filter((row) => num(row.password_files) + num(row.key_files) + (/personnel|sensib/.test(q) ? num(row.personal_files) : 0) > 0)
      .sort((a, b) => num(b.password_files) + num(b.key_files) - num(a.password_files) - num(a.key_files));
    return folderAnswer('sensibilité:mot-de-passe OU clé', `${list.length} dossier(s) contiennent des fichiers sensibles d’après la dernière analyse.`, 'analyse de sensibilité', list,
      [['Mots de passe', (row) => ({ text: String(num(row.password_files)), tone: num(row.password_files) ? 'bad' : undefined })], ['Clés / jetons', (row) => ({ text: String(num(row.key_files)), tone: num(row.key_files) ? 'bad' : undefined })],
        ['Données perso', (row) => ({ text: String(num(row.personal_files)), tone: num(row.personal_files) ? 'warn' : undefined })]], 'fichiers_sensibles.csv');
  }
  if (/quota/.test(q)) {
    const threshold = Number((question.match(/(\d{2,3})\s*%/) ?? [])[1] ?? 85);
    const list = roots.filter((row) => row.quota_used_percent != null && num(row.quota_used_percent) >= threshold).sort((a, b) => num(b.quota_used_percent) - num(a.quota_used_percent));
    return folderAnswer(`quota ≥ ${threshold} %`, `${list.length} dossier(s) à ${threshold} % de leur quota ou plus.`, 'quotas FSRM relus', list,
      [['Utilisé', (row) => ({ text: formatBytes(num(row.quota_used_bytes)) })], ['Limite', (row) => ({ text: formatBytes(num(row.quota_limit_bytes)) })],
        ['Remplissage', (row) => ({ text: `${num(row.quota_used_percent)} %`, tone: num(row.quota_used_percent) >= 100 ? 'bad' : 'warn' })], ['Demandes', (row) => ({ text: String(num(row.quota_pending_requests)) })]], 'quotas.csv');
  }
  if (/jamais|non mesur|pas mesur/.test(q)) {
    const list = roots.filter((row) => row.content_size_bytes == null && !['done', 'running'].includes(String(row.measure_status ?? '')));
    return folderAnswer('est:non-mesure', `${list.length} dossier(s) n’ont jamais été mesurés : ni volume détaillé, ni 5S, ni doublons.`, 'inventaire', list,
      [['Zone', (row) => ({ text: String(row.zone_name ?? '—') })], ['État', () => ({ text: 'Jamais mesuré', tone: 'warn' })]], 'jamais_mesures.csv');
  }
  if (/gardien/.test(q)) {
    const list = roots.filter((row) => num(row.guardians_count) === 0);
    return folderAnswer('est:sans-gardien', `${list.length} dossier(s) sans gardien : leurs demandes reviennent aux administrateurs.`, 'Storage Roots', list,
      [['Zone', (row) => ({ text: String(row.zone_name ?? '—') })], ['Volume', (row) => ({ text: size(row) ? formatBytes(size(row)) : '—' })]], 'sans_gardien.csv');
  }
  if (/doublon/.test(q)) {
    const dups = (row: Root) => num(row.dup_wasted_bytes) + num(row.shared_dup_bytes);
    const list = roots.filter((row) => dups(row) > 0).sort((a, b) => dups(b) - dups(a));
    const total = list.reduce((sum, row) => sum + dups(row), 0);
    return folderAnswer('doublons > 0', `${formatBytes(total)} de doublons vérifiés dans ${list.length} dossier(s).`, 'empreintes des mesures 5S', list,
      [['Doublons', (row) => ({ text: formatBytes(dups(row)), tone: 'warn' })], ['Volume', (row) => ({ text: size(row) ? formatBytes(size(row)) : '—' })]], 'doublons.csv');
  }
  if (/froid|archiv|ancien|vieux/.test(q)) {
    const list = roots.filter((row) => size(row) > 0 && num(row.cold_1y_bytes) > 0.5 * size(row)).sort((a, b) => num(b.cold_1y_bytes) - num(a.cold_1y_bytes));
    return folderAnswer('données froides > 50 %', `${list.length} dossier(s) dont plus de la moitié n’a pas bougé depuis un an.`, 'mesures 5S', list,
      [['Froid (1 an)', (row) => ({ text: formatBytes(num(row.cold_1y_bytes)) })], ['Part', (row) => ({ text: `${Math.round((num(row.cold_1y_bytes) / size(row)) * 100)} %`, tone: 'warn' })]], 'donnees_froides.csv');
  }
  if (/gros|volumineux|taille|plus grand/.test(q)) {
    const count = Number((question.match(/\b(\d{1,3})\b/) ?? [])[1] ?? 10);
    const list = roots.filter((row) => size(row) > 0).sort((a, b) => size(b) - size(a)).slice(0, count);
    return folderAnswer(`top ${count} par volume`, `Les ${list.length} plus gros dossiers mesurés.`, 'mesures', list,
      [['Volume', (row) => ({ text: formatBytes(size(row)) })], ['Fichiers', (row) => ({ text: num(row.content_files).toLocaleString('fr-FR') })]], `top_${count}_volume.csv`);
  }
  return { ...base, ok: false, intent: 'non compris', source: '', columns: [], rows: [], file: null,
    text: 'Je n’ai pas compris. Essayez une des questions proposées : les utilisateurs ou les groupes d’un dossier, les mots de passe, les quotas, les dossiers jamais mesurés, sans gardien, les doublons, les plus gros dossiers…' };
}
