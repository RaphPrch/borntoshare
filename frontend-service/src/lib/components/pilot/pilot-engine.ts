/**
 * Assistant (formerly Pilot): questions in plain French on the folders, answered from what BornToShare already knows
 * (the context list of the storage roots, their guardians, the permissions of a folder: ACL read × directory ×
 * requests). No model, no guess: a few intents read from the words of the question; the answer says how the question
 * was understood. The questions of the 5S module (files, duplicates, cold data, rights to review) are answered only
 * when the module is active.
 */
import { apiGetData, apiGetList, apiPostData, type FetchLike } from '$lib/api/client';
import { getStorageRootPermissions, type PermissionPerson } from '$lib/api/storage-root-permissions';
import { accessRequestId, accessRequestRequesterName, accessRequestTargetLabel } from '$lib/mappers/access-requests.mapper';
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
  /** A change asked for (« ajoute le tag … »): shown first, applied only on a click on « Appliquer » */
  action?: PilotAction;
};

export type PilotAction = { kind: 'tag-add' | 'tag-remove'; tagId: number; tagName: string; rootIds: number[] };

type Root = Record<string, any>;

const num = (value: unknown) => (Number.isFinite(Number(value)) ? Number(value) : 0);
const fold = (value: unknown) => String(value ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
const name = (row: Root) => String(row.storage_root_name ?? row.storage_root_code ?? `#${row.storage_root_id}`);
const slug = (value: string) => fold(value).replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '') || 'export';
const size = (row: Root) => num(row.content_size_bytes ?? row.estimated_size_bytes);
const rootLink = (row: Root) => ({ label: name(row), href: `/storage-roots?selected=${row.storage_root_id}` });

const EXAMPLES: Array<{ text: string; fives?: true }> = [
  { text: 'Exporte-moi tous les utilisateurs du dossier Finance' },
  { text: 'Exporte-moi les utilisateurs avec le nombre de dossiers dont ils sont responsables' },
  { text: 'Exporte-moi les gardiens dont les données sont sensibles' },
  { text: 'Exporte-moi les utilisateurs qui accèdent à des données sensibles' },
  { text: 'Quels groupes donnent accès au dossier RH ?' },
  { text: 'Quels dossiers contiennent des mots de passe ?' },
  { text: 'Fichiers sensibles ouverts à tous' },
  { text: 'Quotas au-delà de 85 %' },
  { text: 'Dossiers jamais mesurés' },
  { text: 'Dossiers sans gardien' },
  { text: 'Dossiers sans suppléant' },
  { text: 'Les 10 plus gros dossiers' },
  { text: 'Dossiers du serveur FILER01' },
  { text: 'Demandes en retard' },
  { text: 'Accès qui expirent cette semaine' },
  { text: 'Revues d’accès à traiter' },
  { text: 'Doublons à libérer', fives: true },
  { text: 'Données froides depuis plus d’un an', fives: true },
  { text: 'Dossiers avec des droits à revoir', fives: true },
  { text: 'Fichiers du propriétaire CORP\\jane', fives: true },
  { text: 'Fichiers pdf de plus de 100 Mo', fives: true },
  { text: 'Ajoute le tag Confidentiel au dossier Finance' },
  { text: 'Retire le tag Archive des dossiers du serveur FILER01' }
];

/** The examples offered: those of the 5S module only when it is active. */
export function pilotExamples(fives: boolean): string[] {
  return EXAMPLES.filter((example) => fives || !example.fives).map((example) => example.text);
}

// The questions only the 5S module answers: its file inventory, its fingerprints (duplicates), the age of the data,
// the rights of the sub-folders. Same words as the intents below.
const FIVES_FILES = /\b(fichiers?)\b/;
const FIVES_FILE_FILTER = /proprietaire|appartenant|\.\w{2,5}\b|\b(pdf|docx?|xlsx?|pptx?|zip|iso|mp4|mkv|pst|msi|exe|jpe?g|png)\b|plus de \d|\d+\s*(mo|go|ko)/;
const FIVES_RIGHTS = /droits? a revoir|orphelin|\bsid\b|droits? excessi|controle total|ecriture pour tous/;
const FIVES_DATA = /doublon|froid|\b5s\b/;
export function isFivesQuestion(q: string): boolean {
  if (/sensib|mot(s)? de passe|secret/.test(q) && /ouvert|tous|tout le monde|everyone/.test(q)) return false; // sensitivity scan of the core
  return FIVES_DATA.test(q) || FIVES_RIGHTS.test(q) || (FIVES_FILES.test(q) && FIVES_FILE_FILTER.test(q)) || (/archiv|ancien|vieux/.test(q) && !/\btags?\b/.test(q));
}

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

export async function askPilot(fetchFn: FetchLike, question: string, options: { fives?: boolean } = {}): Promise<PilotAnswer> {
  const q = fold(question);
  const base = { question, ok: true, links: [] as PilotAnswer['links'] };
  const fivesOn = options.fives !== false;

  // ---- the 5S module is off: its questions are not answered ----
  if (!fivesOn && !(ACTION_VERB.test(q) && /\btags?\b/.test(q)) && isFivesQuestion(q)) {
    return { ...base, ok: false, intent: 'module 5S', source: '', columns: [], rows: [], file: null,
      text: 'Cette question porte sur le contenu des dossiers (fichiers, doublons, données froides, droits des sous-dossiers) : elle relève du module 5S, qui n’est pas actif sur cette installation.' };
  }

  const roots = await apiGetList<Root>(fetchFn, '/storage-roots/context').catch(() => [] as Root[]);
  const table = (rows: Root[]) => rows.slice(0, 200);

  // ---- actions: put a tag on folders or take it off (nothing changes before « Appliquer ») ----
  if (ACTION_VERB.test(q) && /\btags?\b/.test(q)) return planTagAction(fetchFn, q, roots, base);

  // ---- people × folders: who is responsible for what, who guards or reaches sensitive data ----
  const people = await askPeopleAndFolders(fetchFn, q, roots, base);
  if (people) return people;

  // ---- 5S module: files of the inventory, sensitive files open to all, rights to review ----
  const fives = await askFives(fetchFn, question, q, roots, base);
  if (fives) return fives;

  // ---- access governance: requests past their deadline, accesses ending soon, reviews to handle ----
  const governance = await askGovernance(fetchFn, q, base);
  if (governance) return governance;

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
  // One guardian and nobody to take over: the most exposed first (sensitive files, requests waiting, volume)
  if (/sans (suppleant|releve|remplacant)|pas de (suppleant|remplacant)|couverture/.test(q)) {
    const risk = (row: Root) => (num(row.password_files) + num(row.key_files) + num(row.sensitive_files) > 0 ? 1000 : 0) + num(row.pending_validation_count) * 10 + (size(row) > 0 ? 1 : 0);
    const list = roots.filter((row) => num(row.guardians_count) > 0 && row.backup_covered === false)
      .sort((a, b) => risk(b) - risk(a) || size(b) - size(a));
    return folderAnswer('est:sans-suppleant', `${list.length} dossier(s) gardés par une seule personne, sans suppléant : en son absence, personne ne décide. Les plus sensibles d’abord.`, 'Storage Roots', list,
      [['Gardien', (row) => ({ text: (row.guardians ?? []).map((guardian: Record<string, any>) => guardian.name).join(', ') || '—' })],
       ['Sensibles', (row) => { const count = num(row.password_files) + num(row.key_files) + num(row.sensitive_files); return { text: count ? String(count) : '—', tone: count ? 'bad' : undefined }; }],
       ['Demandes', (row) => ({ text: String(num(row.pending_validation_count) || '—') })],
       ['Volume', (row) => ({ text: size(row) ? formatBytes(size(row)) : '—' })]], 'sans_suppleant.csv');
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


const ACTION_VERB = /\b(ajoute|ajouter|pose|poser|mets|mettre|applique|appliquer|tague|taguer|retire|retirer|enleve|enlever|supprime|supprimer|ote|oter)\b/;
const REMOVE_VERB = /\b(retire|retirer|enleve|enlever|supprime|supprimer|ote|oter)\b/;
const hasTag = (row: Root, tagId: number) => Array.isArray(row.tags) && row.tags.some((tag: Root) => Number(tag?.id) === tagId);

/** The folders named after the tag: « du serveur X », « sans gardien », « jamais mesurés », « sensibles », or names (« dossiers A, B et C »). */
export function pilotTargets(rest: string, roots: Root[]): { list: Root[]; label: string; missing: string[] } {
  const server = rest.match(/serveur\s+([\w.-]+)/);
  if (server) return { list: roots.filter((row) => fold(row.storage_endpoint_name).includes(server[1])), label: `dossiers du serveur ${server[1]}`, missing: [] };
  if (/sans gardien/.test(rest)) return { list: roots.filter((row) => num(row.guardians_count) === 0), label: 'dossiers sans gardien', missing: [] };
  if (/jamais mesur|non mesur|pas mesur/.test(rest)) return { list: roots.filter((row) => row.content_size_bytes == null && !['done', 'running'].includes(String(row.measure_status ?? ''))), label: 'dossiers jamais mesurés', missing: [] };
  if (/sensib|mots? de passe|secret/.test(rest)) return { list: roots.filter((row) => num(row.password_files) + num(row.key_files) + num(row.sensitive_files) > 0), label: 'dossiers sensibles', missing: [] };
  const names = rest.replace(/^(?:(?:le|les|la|l')\s*)?dossiers?\s+/, '').split(/\s*,\s*|\s+et\s+/).map((item) => item.replace(/^[«"'\s]+|[»"'\s]+$/g, '')).filter(Boolean);
  const list: Root[] = [];
  const missing: string[] = [];
  for (const wanted of names) {
    const exact = roots.find((row) => fold(name(row)) === wanted || fold(row.storage_root_code) === wanted);
    const partial = exact ? [] : roots.filter((row) => fold(name(row)).includes(wanted));
    const hit = exact ?? (partial.length === 1 ? partial[0] : null);
    if (hit && !list.includes(hit)) list.push(hit);
    else if (!hit) missing.push(partial.length > 1 ? `${wanted} (${partial.length} dossiers possibles)` : wanted);
  }
  return { list, label: list.map(name).join(', ') || 'aucun dossier', missing };
}

// ---- sensitivity of a folder: what the sensitivity scan found in its files, and its sensitivity tags ----
const SCAN_GROUPS: Array<[string, string]> = [
  ['password_files', 'Mots de passe'], ['key_files', 'Clés et jetons'], ['personal_files', 'Données personnelles'],
  ['bank_files', 'Données bancaires'], ['risky_files', 'Fichiers à risque']
];
// Tags of these families mark a sensitive folder, except the levels that say it is not (« Public », « Interne »)
const SENSITIVE_TAG_FAMILIES = ['confidentialite', 'conformite'];
const NOT_SENSITIVE_TAGS = ['public', 'interne'];

export function sensitiveTagNames(tags: Root[]): Set<string> {
  return new Set(tags.filter((tag) => SENSITIVE_TAG_FAMILIES.includes(fold(tag.family)) && !NOT_SENSITIVE_TAGS.includes(fold(tag.name))).map((tag) => fold(tag.name)));
}

/** What makes the folder sensitive (empty: nothing found, or never scanned and no sensitivity tag). */
export function sensitivityOf(row: Root, sensitiveTags: Set<string>): string[] {
  const found = SCAN_GROUPS.filter(([field]) => num(row[field]) > 0).map(([, label]) => label);
  if (!found.length && num(row.sensitive_files) > 0) found.push('Fichiers sensibles');
  const tags = (Array.isArray(row.tags) ? row.tags : []).map((tag: Root) => String(tag.name ?? tag.label ?? '')).filter((tag: string) => sensitiveTags.has(fold(tag)));
  return [...found, ...tags.filter((tag: string) => !found.some((label) => fold(label) === fold(tag)))];
}

type Guardian = { identity_id: number; login: string | null; name: string | null };
const guardiansOf = (row: Root): Guardian[] => (Array.isArray(row.guardians) ? row.guardians : []);

/** Reads the permissions of many folders, a few at a time (the list of a folder costs a tenth of a second). */
async function permissionsOf(fetchFn: FetchLike, list: Root[], parallel = 8) {
  const out: Array<{ root: Root; people: PermissionPerson[] }> = [];
  let next = 0;
  const worker = async () => {
    while (next < list.length) {
      const root = list[next++];
      const data = await getStorageRootPermissions(fetchFn, Number(root.storage_root_id)).catch(() => null);
      if (data) out.push({ root, people: data.people });
    }
  };
  await Promise.all(Array.from({ length: Math.min(parallel, list.length) }, worker));
  return out.sort((a, b) => name(a.root).localeCompare(name(b.root), 'fr'));
}

/** Lists across people and folders: the guardians and their folders, who reaches sensitive data. null: not one of them. */
async function askPeopleAndFolders(fetchFn: FetchLike, q: string, roots: Root[], base: { question: string; ok: boolean; links: PilotAnswer['links'] }): Promise<PilotAnswer | null> {
  const sensitiveWord = /sensib|confidenti|rgpd|reglementaire/.test(q);
  const guardianWord = /gardien|responsab/.test(q) && !/sans gardien/.test(q);
  const accessWord = /(utilisateur|personne|qui|login)/.test(q) && /(acce|acced|ouvr|lis|droit)/.test(q);
  const summary = /responsab/.test(q) || (/gardien/.test(q) && /nombre|combien|chacun|chaque|liste|tous les|par gardien/.test(q));
  if (!(guardianWord && (sensitiveWord || summary)) && !(sensitiveWord && accessWord)) return null;

  const tags = await apiGetList<Root>(fetchFn, '/tags').catch(() => [] as Root[]);
  const sensitiveTags = sensitiveTagNames(tags);
  const sensitive = roots.map((root) => ({ root, labels: sensitivityOf(root, sensitiveTags) })).filter((item) => item.labels.length);
  const source = 'analyse de sensibilité · tags de confidentialité et de conformité';

  // Guardians of sensitive data: one line per guardian and folder
  if (guardianWord && sensitiveWord) {
    const rows = sensitive.flatMap(({ root, labels }) => guardiansOf(root).map((guardian) => ({ guardian, root, labels })))
      .sort((a, b) => String(a.guardian.login ?? '').localeCompare(String(b.guardian.login ?? ''), 'fr') || name(a.root).localeCompare(name(b.root), 'fr'));
    const people = new Set(rows.map((row) => row.guardian.identity_id)).size;
    const orphan = sensitive.filter(({ root }) => !guardiansOf(root).length).length;
    return { ...base, intent: 'gardiens × dossiers sensibles', source, links: [],
      text: `${people} gardien(s) veillent sur ${sensitive.length - orphan} dossier(s) sensible(s)${orphan ? ` ; ${orphan} dossier(s) sensible(s) n’ont aucun gardien` : ''}.`,
      columns: ['Login', 'Nom', 'Dossier', 'Sensibilité'],
      rows: rows.map(({ guardian, root, labels }) => [{ text: guardian.login ?? '—', mono: true }, { text: guardian.name ?? '—' }, { text: name(root) }, { text: labels.join(', '), tone: 'bad' }]),
      file: rows.length ? 'gardiens_donnees_sensibles.csv' : null };
  }

  // Each guardian and what they are responsible for
  if (guardianWord) {
    const byGuardian = new Map<number, { guardian: Guardian; folders: number; bytes: number; sensitive: number }>();
    for (const root of roots) {
      for (const guardian of guardiansOf(root)) {
        const entry = byGuardian.get(guardian.identity_id) ?? { guardian, folders: 0, bytes: 0, sensitive: 0 };
        entry.folders += 1;
        entry.bytes += size(root);
        if (sensitivityOf(root, sensitiveTags).length) entry.sensitive += 1;
        byGuardian.set(guardian.identity_id, entry);
      }
    }
    const list = [...byGuardian.values()].sort((a, b) => b.folders - a.folders || b.bytes - a.bytes);
    const without = roots.filter((root) => !guardiansOf(root).length).length;
    return { ...base, intent: 'gardiens → dossiers, volume', source: 'gardiens des dossiers · dernières mesures', links: [],
      text: `${list.length} personne(s) sont responsables d’au moins un dossier${without ? ` ; ${without} dossier(s) n’ont aucun gardien` : ''}.`,
      columns: ['Login', 'Nom', 'Dossiers', 'Volume', 'Dossiers sensibles'],
      rows: list.map((entry) => [{ text: entry.guardian.login ?? '—', mono: true }, { text: entry.guardian.name ?? '—' }, { text: String(entry.folders) },
        { text: entry.bytes ? formatBytes(entry.bytes) : '—' }, { text: String(entry.sensitive), tone: entry.sensitive ? 'warn' : undefined }]),
      file: list.length ? 'gardiens_dossiers.csv' : null };
  }

  // People who reach sensitive data: one line per person and folder
  const reached = await permissionsOf(fetchFn, sensitive.map((item) => item.root));
  const labelsOf = new Map(sensitive.map((item) => [Number(item.root.storage_root_id), item.labels]));
  const rows = reached.flatMap(({ root, people }) => people.map((person) => ({ person, root, labels: labelsOf.get(Number(root.storage_root_id)) ?? [] })));
  const persons = new Set(rows.map((row) => row.person.username ?? row.person.name)).size;
  return { ...base, intent: 'personnes × dossiers sensibles', source: `droits lus (ACL × annuaire × demandes) · ${source}`, links: [],
    text: `${persons} personne(s) accèdent à ${reached.length} dossier(s) sensible(s), ${rows.length} accès au total.${reached.length < sensitive.length ? ` Les droits de ${sensitive.length - reached.length} dossier(s) n’ont pas pu être lus.` : ''}`,
    columns: ['Login', 'Nom', 'Droit', 'Dossier', 'Sensibilité'],
    rows: rows.map(({ person, root, labels }) => [{ text: person.username ?? '—', mono: true }, { text: person.name }, { text: levelLabel(person.level), tone: person.level === 'write' ? 'warn' : 'info' },
      { text: name(root) }, { text: labels.join(', '), tone: 'bad' }]),
    file: rows.length ? 'acces_donnees_sensibles.csv' : null };
}

async function planTagAction(fetchFn: FetchLike, q: string, roots: Root[], base: { question: string; ok: boolean; links: PilotAnswer['links'] }): Promise<PilotAnswer> {
  const remove = REMOVE_VERB.test(q);
  const refuse = (intent: string, text: string): PilotAnswer => ({ ...base, ok: false, intent, text, source: '', columns: [], rows: [], file: null });
  const tags = await apiGetList<Root>(fetchFn, '/tags').catch(() => [] as Root[]);
  const after = q.slice(q.search(/\btags?\b/)).replace(/^tags?\s*/, '').replace(/^[«"'\s]+/, '').replace(/[?.!\s]+$/, '');
  // The tag is the longest known name right after « tag » (a name may hold « de », « à »…)
  const hit = tags
    .flatMap((tag) => [tag.name, tag.label, tag.code].map(fold).filter(Boolean).map((key) => ({ tag, key })))
    .filter(({ key }) => after.startsWith(key) && (after.length === key.length || /[\s»"',]/.test(after[key.length])))
    .sort((a, b) => b.key.length - a.key.length)[0];
  if (!hit) {
    const typed = after.split(/\s+(?:a|au|aux|sur|du|des|de|dans)\s+/)[0] || '?';
    const known = tags.map((tag) => String(tag.name ?? tag.label ?? '')).filter(Boolean).slice(0, 12).join(', ');
    return refuse(`tag:${typed} ?`, `Aucun tag « ${typed} ». Créez-le d’abord dans Administration › Tags.${known ? ` Tags existants : ${known}${tags.length > 12 ? '…' : ''}.` : ''}`);
  }
  const tagId = Number(hit.tag.id);
  const tagName = String(hit.tag.name ?? hit.tag.label ?? hit.key);
  const rest = after.slice(hit.key.length).replace(/^[»"'\s]+/, '').replace(/^(?:a la|de la|a|au|aux|sur|du|des|de|dans|pour)\s+/, '');
  if (!rest) return refuse(`tag:${tagName} → ?`, `Sur quels dossiers ? Écrivez par exemple « ${remove ? 'retire' : 'ajoute'} le tag ${tagName} ${remove ? 'du' : 'au'} dossier Finance ».`);
  const { list, label, missing } = pilotTargets(rest, roots);
  const todo = list.filter((row) => hasTag(row, tagId) === remove);
  const skipped = list.length - todo.length;
  const intent = `tag:${tagName} → ${remove ? 'retirer de' : 'poser sur'} ${label.length > 60 ? `${list.length} dossiers` : label}`;
  const missed = missing.length ? ` Introuvable : ${missing.join(', ')}.` : '';
  if (!todo.length) {
    return refuse(intent, list.length ? `Rien à faire : ${remove ? 'aucun de ces dossiers ne porte' : 'ces dossiers portent déjà'} le tag « ${tagName} ».${missed}` : `Aucun dossier trouvé.${missed}`);
  }
  const verb = remove ? 'perdront' : 'recevront';
  return { ...base, intent, source: 'Storage Roots · tags', action: { kind: remove ? 'tag-remove' : 'tag-add', tagId, tagName, rootIds: todo.map((row) => Number(row.storage_root_id)) },
    text: `${todo.length} dossier(s) ${verb} le tag « ${tagName} »${skipped ? ` (${skipped} ${remove ? 'ne le portent pas' : 'l’ont déjà'})` : ''}.${missed} Rien n’est changé avant votre clic sur « Appliquer ».`,
    columns: ['Dossier', 'Serveur', 'Zone', 'Tags actuels'],
    rows: table200(todo).map((row) => [{ text: name(row) }, { text: String(row.storage_endpoint_name ?? '—'), mono: true }, { text: String(row.zone_name ?? '—') },
      { text: (Array.isArray(row.tags) ? row.tags.map((tag: Root) => String(tag?.name ?? '')).filter(Boolean).join(', ') : '') || '—', tone: 'mut' }]),
    file: null, links: todo.slice(0, 5).map(rootLink) };
}
const table200 = (rows: Root[]) => rows.slice(0, 200);

type Request = Record<string, any>;
const day = (value: unknown) => {
  const time = new Date(String(value ?? '')).getTime();
  return Number.isFinite(time) && time > 0 ? new Date(time).toLocaleDateString('fr-FR') : '—';
};
const requestRoot = (row: Request) => ({ label: accessRequestTargetLabel(row), href: `/access-requests?focus=${accessRequestId(row)}` });
const requestCode = (row: Request) => String(row.request_code ?? row.code ?? `REQ-${accessRequestId(row)}`);
const requestLevel = (row: Request) => (/write|contribution|modif/.test(String(row.access_profile_name ?? row.permission ?? '').toLowerCase()) ? 'write' : 'read');

/** Requests past their decision deadline, accesses that end soon, access reviews still open (as the API lets the person see them). */
async function askGovernance(fetchFn: FetchLike, q: string, base: { question: string; ok: boolean; links: PilotAnswer['links'] }): Promise<PilotAnswer | null> {
  const lateAsked = /demandes?/.test(q) && /retard|en attente depuis|delai|echeance|pas (encore )?decid/.test(q);
  const endingAsked = /acces/.test(q) && /expir|se termin|fin d|prennent fin|arrivent a echeance/.test(q);
  const reviewsAsked = /revues?/.test(q);
  if (!lateAsked && !endingAsked && !reviewsAsked) return null;
  const unavailable = (what: string): PilotAnswer => ({ ...base, ok: false, intent: what, source: '', columns: [], rows: [], file: null, links: [],
    text: `Les ${what} ne sont pas lisibles : la gouvernance des accès n’est pas active sur cette installation, ou vous n’y avez pas accès.` });
  if (reviewsAsked) {
    const reviews = await apiGetData<Array<Record<string, any>>>(fetchFn, '/access-reviews').catch(() => null);
    if (!reviews) return unavailable('revues d’accès');
    const open = reviews.filter((review) => review.status === 'open');
    return { ...base, intent: 'revues → ouvertes', source: 'Access Management › Revues',
      text: open.length ? `${open.length} revue(s) d’accès ouverte(s), ${open.reduce((sum, review) => sum + Math.max(0, review.total - review.decided), 0)} accès encore à décider.` : 'Aucune revue d’accès ouverte.',
      columns: ['Revue', 'À décider', 'Décidés', 'Dossiers', 'Échéance'],
      rows: open.map((review) => [{ text: String(review.name) }, { text: String(Math.max(0, review.total - review.decided)), tone: review.total > review.decided ? 'warn' : 'ok' },
        { text: `${review.decided} / ${review.total}` }, { text: String(review.folders) }, { text: day(review.due_at), tone: review.due_at && Date.parse(review.due_at) < Date.now() ? 'bad' : undefined }]),
      file: open.length ? 'revues_ouvertes.csv' : null,
      links: open.slice(0, 6).map((review) => ({ label: String(review.name), href: `/access-reviews/${review.id}` })) };
  }
  const requests = await apiGetList<Request>(fetchFn, '/access-requests').catch(() => null);
  if (!requests) return unavailable('demandes d’accès');
  if (lateAsked) {
    const late = requests.filter((row) => String(row.status ?? '').toLowerCase() === 'pending' && row.overdue === true)
      .sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)));
    return { ...base, intent: 'demandes → en retard', source: 'Access Management › Demandes',
      text: late.length ? `${late.length} demande(s) attendent une décision au-delà du délai : relancez leurs gardiens ou décidez.` : 'Aucune demande en retard : toutes ont été décidées dans le délai.',
      columns: ['Demande', 'Dossier', 'Pour', 'Faite le', 'Échéance'],
      rows: late.slice(0, 200).map((row) => [{ text: requestCode(row), mono: true }, { text: accessRequestTargetLabel(row) },
        { text: accessRequestRequesterName(row) }, { text: day(row.created_at) }, { text: day(row.due_at), tone: 'bad' }]),
      file: late.length ? 'demandes_en_retard.csv' : null, links: late.slice(0, 6).map(requestRoot) };
  }
  const horizon = /mois|30 jours/.test(q) ? 30 : 7;
  const now = Date.now();
  const ending = requests.filter((row) => {
    const end = Date.parse(String(row.expires_at ?? ''));
    return ['approved', 'applied', 'active'].includes(String(row.status ?? '').toLowerCase()) && end > now && end - now <= horizon * 86_400_000;
  }).sort((a, b) => String(a.expires_at).localeCompare(String(b.expires_at)));
  return { ...base, intent: `accès → fin sous ${horizon} jours`, source: 'Access Management › Demandes',
    text: ending.length ? `${ending.length} accès se terminent dans les ${horizon} prochains jours. Le titulaire peut demander un renouvellement depuis sa demande.` : `Aucun accès ne se termine dans les ${horizon} prochains jours.`,
    columns: ['Pour', 'Dossier', 'Niveau', 'Fin le'],
    rows: ending.slice(0, 200).map((row) => [{ text: accessRequestRequesterName(row) }, { text: accessRequestTargetLabel(row) },
      { text: levelLabel(requestLevel(row)) }, { text: day(row.expires_at), tone: 'warn' }]),
    file: ending.length ? `acces_fin_${horizon}_jours.csv` : null, links: ending.slice(0, 6).map(requestRoot) };
}

/** Applies a planned action; each folder is answered for (the API refuses non-administrators). */
export async function applyPilotAction(fetchFn: FetchLike, action: PilotAction): Promise<{ done: number; failed: string[] }> {
  let done = 0;
  const failed: string[] = [];
  if (action.kind === 'tag-add') {
    for (let start = 0; start < action.rootIds.length; start += 100) {
      const ids = action.rootIds.slice(start, start + 100);
      try {
        const data = await apiPostData<{ updated?: number[]; failed?: Array<{ message?: string }> }>(fetchFn, '/storage-roots/bulk-tags', { root_ids: ids, tag_ids: [action.tagId] });
        done += data?.updated?.length ?? 0;
        failed.push(...(data?.failed ?? []).map((item) => String(item.message ?? 'refusé')));
      } catch (error) {
        failed.push(...ids.map(() => (error instanceof Error ? error.message : 'refusé')));
      }
    }
    return { done, failed };
  }
  for (const id of action.rootIds) {
    try {
      await apiPostData(fetchFn, '/tags/detach', { tag_id: action.tagId, resource_type: 'storage_root', resource_id: id });
      done += 1;
    } catch (error) {
      failed.push(error instanceof Error ? error.message : 'refusé');
    }
  }
  return { done, failed };
}
