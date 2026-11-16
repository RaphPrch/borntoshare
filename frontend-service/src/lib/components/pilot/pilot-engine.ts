/**
 * Pilot: questions in plain French on the folders, answered from what BornToShare already knows (the context list
 * of the storage roots, the permissions of a folder: ACL read × directory × requests). No model, no guess: a few
 * intents read from the words of the question; the answer says how the question was understood.
 */
import { apiGetData, apiGetList, type FetchLike } from '$lib/api/client';
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
  'Données froides depuis plus d’un an',
  'Fichiers sensibles ouverts à tous',
  'Dossiers avec des droits à revoir',
  'Fichiers du propriétaire CORP\\jane',
  'Fichiers pdf de plus de 100 Mo'
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

  // ---- 5S module: files of the inventory, sensitive files open to all, rights to review ----
  const fives = await askFives(fetchFn, question, q, roots, base);
  if (fives) return fives;

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


type FileHit = { storage_root_id: number; folder_name: string | null; path: string; size: number; modified: string | null; owner: string | null };

/** The questions answered by the 5S module (inventory of the files, rights of the sub-folders); null: not one of them. */
async function askFives(fetchFn: FetchLike, question: string, q: string, roots: Root[], base: { question: string; ok: boolean; links: PilotAnswer['links'] }): Promise<PilotAnswer | null> {
  const unavailable = (intent: string): PilotAnswer => ({ ...base, ok: false, intent, source: '', columns: [], rows: [], file: null,
    text: 'Le module 5S ne répond pas : il n’est pas actif sur cette installation, ou aucun dossier n’a encore été mesuré par son scanner.' });

  // Sensitive files that the whole company can open (sensitivity scan of the core)
  if (/sensib|mot(s)? de passe|secret/.test(q) && /ouvert|tous|tout le monde|everyone/.test(q)) {
    const candidates = roots.filter((row) => num(row.sensitive_files) + num(row.password_files) + num(row.key_files) > 0).slice(0, 60);
    const rows: Array<{ root: Root; path: string; category: string; by: string }> = [];
    for (const root of candidates) {
      const data = await apiGetData<{ findings?: Array<{ path: string; category: string; ignored?: boolean; acl?: { broad?: boolean; by?: string[] } }> }>(
        fetchFn, `/storage-roots/${root.storage_root_id}/sensitivity`).catch(() => null);
      for (const item of data?.findings ?? []) {
        if (!item.ignored && item.acl?.broad) rows.push({ root, path: item.path, category: item.category, by: (item.acl.by ?? []).join(', ') });
      }
    }
    return { ...base, intent: 'fichiers sensibles → ouverts à tous', source: 'Analyse de sensibilité', links: [...new Set(rows.map((row) => row.root))].slice(0, 5).map(rootLink),
      text: rows.length ? `${rows.length} fichier(s) sensible(s) lisible(s) par toute l’entreprise, dans ${new Set(rows.map((row) => row.root)).size} dossier(s).` : 'Aucun fichier sensible ouvert à toute l’entreprise.',
      columns: ['Dossier', 'Fichier', 'Catégorie', 'Ouvert par'],
      rows: rows.slice(0, 200).map((row) => [{ text: name(row.root) }, { text: row.path, mono: true }, { text: row.category, tone: 'bad' }, { text: row.by || '—', mono: true }]),
      file: rows.length ? 'fichiers_sensibles_ouverts.csv' : null };
  }

  // Rights to review in the sub-folders (orphan SIDs, whole company writing, full control, rights set by hand, broken inheritance)
  if (/droits? a revoir|orphelin|sid|droits? excessi|controle total|ecriture pour tous/.test(q)) {
    const wantOrphans = /orphelin|sid/.test(q);
    const measured = roots.filter((row) => row.content_size_bytes != null).slice(0, 60);
    const rows: Array<{ root: Root; path: string; codes: string[] }> = [];
    let answered = 0;
    for (const root of measured) {
      const data = await apiGetData<{ folders: Array<{ path: string; codes: string[] }> }>(fetchFn, `/modules/fives/storage-roots/${root.storage_root_id}/rights-review`).catch(() => null);
      if (!data) continue;
      answered += 1;
      for (const folder of data.folders) if (!wantOrphans || folder.codes.includes('ORPHAN_SID')) rows.push({ root, path: folder.path, codes: folder.codes });
    }
    if (!answered) return unavailable('droits à revoir');
    const LABEL: Record<string, string> = { ORPHAN_SID: 'SID orphelin', BROAD_WRITE: 'Écriture pour tous', FULL_CONTROL: 'Contrôle total', EXPLICIT_ENTRY: 'Droits posés à la main', INHERITANCE_BROKEN: 'Héritage rompu' };
    return { ...base, intent: wantOrphans ? 'dossiers → SID orphelins' : 'dossiers → droits à revoir', source: 'Droits de la dernière mesure 5S',
      links: [...new Set(rows.map((row) => row.root))].slice(0, 5).map((root) => ({ label: name(root), href: `/five-s/access/${root.storage_root_id}` })),
      text: rows.length ? `${rows.length} sous-dossier(s) à revoir dans ${new Set(rows.map((row) => row.root)).size} dossier(s) gouverné(s).` : 'Rien à revoir dans les droits des dossiers mesurés.',
      columns: ['Dossier', 'Sous-dossier', 'À revoir'],
      rows: rows.slice(0, 200).map((row) => [{ text: name(row.root) }, { text: row.path, mono: true },
        { text: row.codes.map((code) => LABEL[code] ?? code).join(', '), tone: row.codes.some((code) => code === 'ORPHAN_SID' || code === 'BROAD_WRITE') ? 'bad' : 'warn' }]),
      file: rows.length ? (wantOrphans ? 'sid_orphelins.csv' : 'droits_a_revoir.csv') : null };
  }

  // Files of the inventory: by owner, extension, size, age
  if (/fichiers?/.test(q) && /proprietaire|appartenant|\.\w{2,5}\b|\b(pdf|docx?|xlsx?|pptx?|zip|iso|mp4|mkv|pst|msi|exe|jpe?g|png)\b|plus de \d|\d+\s*(mo|go|ko)/.test(q)) {
    const params: Record<string, string> = { limit: '200' };
    const owner = question.match(/(?:propri[ée]taire|appartenant [àa]|de l['’]utilisateur)\s+([\w.\\@-]+)/i);
    if (owner) params.owner = owner[1];
    const ext = q.match(/\.(\w{2,5})\b/) ?? q.match(/\b(pdf|docx?|xlsx?|pptx?|zip|iso|mp4|mkv|pst|msi|exe|jpe?g|png)\b/);
    if (ext) params.ext = ext[1];
    const big = q.match(/plus de (\d+(?:[.,]\d+)?)\s*(ko|mo|go)/);
    if (big) params.min_bytes = String(Math.round(Number(big[1].replace(',', '.')) * { ko: 1024, mo: 1024 ** 2, go: 1024 ** 3 }[big[2] as 'ko' | 'mo' | 'go']));
    const old = q.match(/depuis (?:plus de )?(\d+) ans?/);
    if (old) params.older_days = String(Number(old[1]) * 365);
    if (Object.keys(params).length === 1) return null;
    const data = await apiGetData<{ files: FileHit[]; total: number; bytes: number }>(fetchFn, '/modules/fives/files/search', params).catch(() => null);
    if (!data) return unavailable('fichiers');
    const said = [params.ext && `.${params.ext}`, params.owner && `de ${params.owner}`, params.min_bytes && `de plus de ${formatBytes(Number(params.min_bytes))}`,
      params.older_days && `non modifiés depuis ${Math.round(Number(params.older_days) / 365)} an(s)`].filter(Boolean).join(' ');
    return { ...base, intent: `fichiers ${said}`, source: 'Inventaire de la dernière mesure 5S',
      links: [...new Set(data.files.map((file) => file.storage_root_id))].slice(0, 5).map((id) => ({ label: data.files.find((file) => file.storage_root_id === id)?.folder_name ?? `#${id}`, href: `/five-s/explore/${id}` })),
      text: data.total ? `${data.total} fichier(s) ${said}, ${formatBytes(data.bytes)} au total${data.total > data.files.length ? ` (les ${data.files.length} plus gros listés)` : ''}.` : `Aucun fichier ${said} dans l’inventaire.`,
      columns: ['Dossier', 'Fichier', 'Taille', 'Modifié', 'Propriétaire'],
      rows: data.files.map((file) => [{ text: file.folder_name ?? `#${file.storage_root_id}` }, { text: file.path, mono: true }, { text: formatBytes(file.size) },
        { text: file.modified ? formatDate(file.modified) : '—' }, { text: file.owner ?? '—', mono: true }]),
      file: data.files.length ? 'fichiers.csv' : null };
  }
  return null;
}
