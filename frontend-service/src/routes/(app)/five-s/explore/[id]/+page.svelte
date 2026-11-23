<script lang="ts">

  import TagPill from '$lib/components/tags/TagPill.svelte';
  import FolderHeader from '../../FolderHeader.svelte';
  import AccessPanel from '../../AccessPanel.svelte';
  import FileSearch from '../../FileSearch.svelte';
  import { copyText } from '$lib/utils/clipboard';
  import { onDestroy, onMount, untrack } from 'svelte';
  import { page } from '$app/stores';
  import { t } from '$lib/i18n';
  import { apiGetData, apiGetList, apiPostData } from '$lib/api/client';
  import { toast } from '$lib/stores/toast';
  import { reportUiError } from '$lib/errors';
  import ConfirmActionModal from '$lib/components/ui/ConfirmActionModal.svelte';
  import ContextMenu, { menuPositionFor, type ContextMenuItem } from '$lib/components/ui/ContextMenu.svelte';
  import { goto } from '$app/navigation';
  import { formatBytes, formatDate, formatDateTime, timeAgo } from '$lib/utils/format';
  import { csvFilename, downloadCsv } from '$lib/utils/csv';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import MeasureCompleteness, { type Completeness } from '$lib/components/storage-roots/MeasureCompleteness.svelte';
  import { inside } from '../explore-state.svelte';

  /**
   * 5S of a scanned folder in one screen: the scanner banner and the figures, then either the explorer (tree and
   * list, down to the deepest folder) or the 5S workshop (a score per pillar and the decisions to take), and on the
   * right the sheet of the folder chosen: its dates, its rights and inheritance, its duplicates with the copy to keep.
   */
  type Ace = { who: string; level: string; inherited: boolean; orphan?: boolean };
  type Folder = { path: string; parent: string | null; name: string; depth: number; bytes: number; files: number; folders: number;
    direct_bytes: number; direct_files: number; cold1_bytes: number; cold3_bytes: number; last_modified: string | null;
    last_access?: string | null; created_at?: string | null; acl?: Ace[] | null; inheritance_broken?: boolean | null;
    acl_total?: number | null; acl_orphans?: number | null; partial?: boolean };
  type FileRow = { path: string; name: string; size: number; modified: string | null; created?: string | null; accessed?: string | null;
    extension?: string | null; owner?: string | null };
  type Level = { node: Folder | null; children: Folder[]; files: FileRow[]; files_source?: 'inventory' | 'fingerprints'; files_total?: number; files_at?: string | null;
    completeness?: Completeness | null };
  type Copy = { path: string; modified: string | null };
  type Group = { fingerprint: string; size: number; wasted: number; copies: Copy[]; decision: { keep_path: string | null } | null };
  type ScorePoint = { measured_at: string; score: number; seiri: number | null; seiton: number | null; seiso: number | null; seiketsu: number | null; shitsuke: number | null };
  // The 5S score of the folder: the one of the 5S page (fives-service), now and at each measure; never computed here
  type Scores = { current: { score: number | null; pillars: Record<string, number | null>; actions: Array<{ pillar: string; text: string }> };
    history: ScorePoint[]; former_model_points: number };
  let scores = $state<Scores | null>(null);
  let history = $derived(scores?.history ?? []);
  type Scanner = { last: any; running: any; pieces: number; journal: boolean; last_full_at: string | null; window: any };

  let rootName = $state('');
  let rootPath = $state('');
  let junk: { bytes: number; files: number } = $state({ bytes: 0, files: 0 });
  let scanner = $state<Scanner | null>(null);
  let groups = $state<Group[]>([]);
  let level = $state<Level | null>(null);
  let trail = $state<Folder[]>([]);
  let selected = $state<Folder | null>(null);
  let loading = $state(true);
  let busy = $state(false);
  let error = $state<string | null>(null);
  // The tab of the sheet: content (explorer) or the 5S workshop, from the address so that the header links it
  let view = $derived<'explorer' | 'workshop'>($page.url.searchParams.get('view') === 'workshop' ? 'workshop' : 'explorer');
  let filter = $state<'all' | 'dormant' | 'dups' | 'broken'>('all');

  let rootId = $derived(Number($page.params.id));
  const NOW = Date.now();
  const YEAR = 365 * 86400000;
  const load = (path: string | null) =>
    apiGetData<Level>(fetch, `/modules/fives/storage-roots/${rootId}/folders`, path == null ? undefined : { path });

  // ---- tags of the sub-folders (policies « also on the sub-folders »), by lower-case path from the share ----
  let folderTags = $state(new Map<string, Array<{ id: number; name: string; color: string | null; policy?: string | null; automatic?: boolean }>>());
  $effect.pre(() => {
    if (rootId) void apiGetList<{ path: string; tags: Array<{ id: number; name: string; color: string | null; policy?: string | null; automatic?: boolean }> }>(fetch, `/storage-roots/${rootId}/folder-tags`)
      .then((rows) => (folderTags = new Map(rows.map((row) => [row.path.toLowerCase(), row.tags]))))
      .catch(() => null);
  });

  // ---- sensitive files: the findings of the sensitivity scan of the core (never a detection of this page) ----
  type Finding = { path: string; category: string; rule: string };
  let sensitive = $state<Finding[]>([]);
  $effect.pre(() => {
    if (rootId) void apiGetData<{ findings?: Finding[] }>(fetch, `/storage-roots/${rootId}/sensitivity`)
      .then((data) => (sensitive = (data?.findings ?? []).filter((item: any) => !item.ignored)))
      .catch(() => null);
  });
  const sensitiveOf = (path: string) => {
    const lower = path.toLowerCase();
    return sensitive.find((item) => lower === item.path.toLowerCase() || lower.endsWith(`\\${item.path.toLowerCase()}`));
  };

  // ---- the files of the open folder, as they are now on the file server (read by a worker) ----
  // The inventory of the module only knows the files fingerprinted for the duplicates: it stays as the fallback.
  type LiveListing = { folders: string[]; files: Array<{ n: string; s: number; t: string | null }>; files_total: number };
  let liveFor = $state<string | null>(null);
  let liveFiles = $state<FileRow[] | null>(null);
  let liveTotal = $state(0);
  let liveState = $state<'idle' | 'loading' | 'ok' | 'failed'>('idle');
  let liveError = $state('');
  let liveSeq = 0;
  async function loadLive(path: string) {
    const seq = ++liveSeq;
    liveFor = path;
    liveFiles = null;
    liveState = 'loading';
    try {
      const data = await apiGetData<LiveListing>(fetch, `/storage-roots/${rootId}/files`, path ? { path } : undefined);
      if (seq !== liveSeq) return;
      const prefix = path ? `${path}\\` : '';
      // The worker reads names, sizes and dates now; creation, last access and owner come from the last measure
      const known = new Map((level?.files ?? []).map((file) => [file.name.toLowerCase(), file]));
      liveFiles = (data?.files ?? []).map((file) => {
        const measured = known.get(String(file.n).toLowerCase());
        return { ...measured, path: prefix + file.n, name: file.n, size: Number(file.s) || 0, modified: file.t ? `${file.t}Z` : null };
      });
      liveTotal = Number(data?.files_total ?? liveFiles.length);
      liveState = 'ok';
    } catch (error) {
      if (seq !== liveSeq) return;
      liveState = 'failed';
      liveError = error instanceof Error ? error.message : '';
    }
  }
  $effect.pre(() => {
    if (level?.node && level.node.path !== liveFor) {
      const path = level.node.path;
      untrack(() => void loadLive(path));
    }
  });

  onMount(async () => {
    try {
      const overview = await apiGetData<Record<string, any>>(fetch, `/storage-roots/${rootId}/overview`);
      rootName = String(overview?.storage_root_name ?? `#${rootId}`);
      rootPath = String(overview?.root_path ?? '');
      junk = { bytes: Number(overview?.content?.junk?.bytes ?? 0), files: Number(overview?.content?.junk?.files ?? 0) };
      void apiGetData<Scores>(fetch, `/modules/fives/storage-roots/${rootId}/scores`).then((data) => (scores = data)).catch(() => null);
      const [first, scan, dups] = await Promise.all([
        load(null),
        apiGetData<Scanner>(fetch, `/modules/fives/storage-roots/${rootId}/scanner`).catch(() => null),
        apiGetData<{ groups: Group[] }>(fetch, `/modules/fives/storage-roots/${rootId}/duplicate-groups`).catch(() => null)
      ]);
      level = first;
      scanner = scan;
      groups = dups?.groups ?? [];
      if (first?.node) {
        trail = [first.node];
        selected = first.node;
      }
      // Opened on a folder found by the file search of the explorer entry page
      const wanted = $page.url.searchParams.get('open');
      wantedFile = $page.url.searchParams.get('file');
      if (wanted && first?.node) void openFolder(wanted);
      // No tree yet (first measure) or a measure walking: follow the scanner until the tree is there
      if (!first?.node || scan?.running) watchScanner();
    } catch {
      error = t('Unable to load the scanned tree of this folder.');
    } finally {
      loading = false;
    }
  });

  // ---- follow a measure: the tree, the figures and the duplicates come when the scanner has walked the folder ----
  let watchTimer: ReturnType<typeof setInterval> | null = null;
  // A measure just asked waits in the queue before it walks: the page keeps watching (at most 10 minutes) until it ended
  let awaitingRuns = 0;
  async function refreshTree() {
    const [first, dups] = await Promise.all([
      load(null).catch(() => null),
      apiGetData<{ groups: Group[] }>(fetch, `/modules/fives/storage-roots/${rootId}/duplicate-groups`).catch(() => null)
    ]);
    if (!first) return;
    groups = dups?.groups ?? groups;
    // The person may have gone down the tree meanwhile: the root level is replaced only when they stand on it
    if (trail.length <= 1 || !level?.node) {
      level = first;
      if (first.node) {
        trail = [first.node];
        selected = first.node;
      }
    }
  }
  function watchScanner() {
    if (watchTimer) return;
    watchTimer = setInterval(async () => {
      const wasRunning = Boolean(scanner?.running);
      const scan = await apiGetData<Scanner>(fetch, `/modules/fives/storage-roots/${rootId}/scanner`).catch(() => null);
      if (scan) scanner = scan;
      const running = Boolean(scan?.running);
      const ended = wasRunning && !running;
      if (!level?.node || ended) await refreshTree();
      if (ended || awaitingRuns > 0) awaitingRuns = ended ? 0 : awaitingRuns - 1;
      if (level?.node && !running && awaitingRuns === 0 && watchTimer) {
        clearInterval(watchTimer);
        watchTimer = null;
      }
    }, 6000);
  }
  onDestroy(() => watchTimer && clearInterval(watchTimer));

  async function enter(folder: Folder) {
    if (busy || folder.folders === 0) return;
    busy = true;
    try {
      const next = await load(folder.path);
      if (next?.node) {
        level = next;
        trail = [...trail, next.node];
        selected = next.node;
        pickedFile = null;
        filter = 'all';
      }
    } finally {
      busy = false;
    }
  }
  /** Opens a folder anywhere under the root (a file found by the search): each level from the root, as a person would. */
  async function openFolder(path: string) {
    const top = trail[0];
    if (!top || busy) return;
    const base = (top.path ?? '').replace(/\\+$/, '');
    const inside = base && path.toLowerCase().startsWith(`${base.toLowerCase()}\\`) ? path.slice(base.length + 1) : base ? '' : path;
    busy = true;
    try {
      const steps = [top];
      let cursor = base;
      let last: Level | null = null;
      for (const part of inside.split('\\').filter(Boolean)) {
        cursor = cursor ? `${cursor}\\${part}` : part;
        const next = await load(cursor);
        if (!next?.node) break;
        steps.push(next.node);
        last = next;
      }
      if (last?.node) {
        level = last;
        trail = steps;
        selected = last.node;
        pickedFile = null;
        filter = 'all';
      }
    } finally {
      busy = false;
    }
  }
  async function up(index: number) {
    if (busy || index === trail.length - 1) return;
    busy = true;
    try {
      const next = await load(index === 0 ? null : trail[index].path);
      if (next?.node) {
        level = next;
        trail = trail.slice(0, index + 1);
        selected = next.node;
        pickedFile = null;
      }
    } finally {
      busy = false;
    }
  }

  // ---- figures ------------------------------------------------------------------------------------------------
  const SYSTEM = /^(AUTORITE NT|NT AUTHORITY|BUILTIN|CREATOR|CREATEUR|Tout le monde|Everyone)/i;
  let root = $derived(trail[0] ?? null);
  let current = $derived(level?.node ?? null);
  const under = (path: string, folder: string) => !folder || path.toLowerCase().startsWith(folder.toLowerCase() + '\\');
  const share = (part: number, whole: number) => (whole > 0 ? part / whole : 0);
  const pct = (part: number, whole: number) => Math.round(share(part, whole) * 100);
  const dormant = (folder: Folder) => Boolean(folder.last_access) && NOW - new Date(String(folder.last_access)).getTime() > 2 * YEAR;
  const groupsUnder = (path: string) => groups.filter((group) => group.copies.some((copy) => under(copy.path, path)));
  let wasted = $derived(groups.reduce((sum, group) => sum + group.wasted, 0));
  let decided = $derived(groups.filter((group) => group.decision?.keep_path).length);
  let children = $derived(level?.children ?? []);
  let brokenHere = $derived(children.filter((folder) => folder.inheritance_broken));
  let explicitHere = $derived(children.filter((folder) => (folder.acl ?? []).some((ace) => !ace.inherited && !SYSTEM.test(ace.who))));
  let dormantBytes = $derived(children.filter(dormant).reduce((sum, folder) => sum + folder.bytes, 0));

  // ---- 5S scores (each one is explained on hover): the same computation as the 5S page, from fives-service ----------
  let latest = $derived(history.length ? history[history.length - 1] : null);
  let previousScore = $derived(history.length > 1 ? history[history.length - 2].score : null);
  let pillars = $derived([
    { key: 'sort', jp: 'Seiri', fr: t('Sort'), how: t('Data untouched for 1 to 3 years counts half, over 3 years fully; duplicates in the folder fully, shared with other folders half') },
    { key: 'order', jp: 'Seiton', fr: t('Set in order'), how: t('Two guardians or more, a tag and a quota') },
    { key: 'shine', jp: 'Seiso', fr: t('Shine'), how: t('No password, key or token in the files, few clutter files') },
    { key: 'standard', jp: 'Seiketsu', fr: t('Standardise'), how: t('Inheritance as expected, no error alert, the folder reachable') },
    { key: 'sustain', jp: 'Shitsuke', fr: t('Sustain'), how: t('Measured within 30 days, sensitivity scanned within 90 days, corrections and requests handled') }
  ].map((pillar) => ({ ...pillar, score: scores?.current.pillars[pillar.key] ?? null })));
  let score = $derived(scores?.current.score ?? null);
  const tone = (value: number | null) => (value == null ? '#5b6b80' : value >= 70 ? '#0b7a4b' : value >= 45 ? '#a85a00' : '#b3364b');
  // ---- workshop: the decisions, from what was measured -----------------------------------------------------
  type Card = { tag: string; tone: string; gain: string; title: string; detail: string; cta: string; href?: string; folder?: Folder; act?: 'archive' | 'inherit' };

  // ---- real actions: restore the inheritance (worker, administrators), archive a folder (scanner, reversible) ----
  let isAdmin = $derived(Boolean(($page.data as any)?.me?.is_admin));
  let acting = $state(false);
  let archiving = $state<Folder | null>(null);
  async function restoreInheritance(folder: Folder) {
    if (acting || !folder.path) return;
    acting = true;
    try {
      await apiPostData(fetch, `/storage-roots/${rootId}/folders/inheritance`, { path: folder.path, mode: 'restore' });
      folder.inheritance_broken = false;
      if (folder.acl) folder.acl = folder.acl.map((ace) => ({ ...ace }));
      level = level;
      selected = selected;
      toast.success(t('Inheritance restored on « {name} »: its rights now come from its parent.', { name: folder.name }));
    } catch (e: unknown) {
      reportUiError(e, t('Unable to restore the inheritance.'), 'fives.inheritance');
    } finally {
      acting = false;
    }
  }
  async function confirmArchive() {
    const folder = archiving;
    archiving = null;
    if (!folder) return;
    acting = true;
    try {
      await apiPostData(fetch, `/modules/fives/storage-roots/${rootId}/folders/archive`, { path: folder.path, size: folder.bytes });
      toast.success(t('« {name} » goes to the archives: the scanner moves it in a moment (restorable).', { name: folder.name }));
    } catch (e: unknown) {
      reportUiError(e, t('Unable to archive the folder.'), 'fives.archive');
    } finally {
      acting = false;
    }
  }
  // ---- right click on a folder: what the sheet offers, without opening it ----
  let menu: { folder: Folder; at: { x: number; y: number } } | null = $state(null);
  const fullPath = (folder: Folder) => (folder.path ? `${rootPath.replace(/\\$/, '')}\\${folder.path}` : rootPath);
  function openMenu(folder: Folder, event: MouseEvent) {
    event.preventDefault();
    selected = folder;
    menu = { folder, at: menuPositionFor(event) };
  }
  function menuItems(folder: Folder): ContextMenuItem[] {
    const dups = groupsUnder(folder.path).length;
    return [
      { key: 'open', label: t('Open'), icon: 'bi-folder2-open', disabled: folder.folders <= 0, hint: folder.folders <= 0 ? t('No sub-folder') : undefined },
      { key: 'dups', label: dups ? t('See its {count} duplicate group(s)', { count: dups }) : t('No duplicate here'), icon: 'bi-files', disabled: !dups },
      { key: 'copy', label: t('Copy the path'), icon: 'bi-clipboard' },
      { key: 'measure', label: t('Measure the governed folder again'), icon: 'bi-arrow-clockwise', disabled: measuring, hint: measuring ? t('A measure is already asked') : undefined },
      { key: 'inherit', label: t('Restore the inheritance'), icon: 'bi-arrow-repeat', separated: true,
        disabled: !(folder.inheritance_broken && isAdmin && folder.path), hint: !folder.inheritance_broken ? t('The inheritance is not broken') : !isAdmin ? t('Administrators only') : undefined },
      { key: 'archive', label: t('Archive this folder'), icon: 'bi-archive', danger: true, disabled: !folder.path, hint: !folder.path ? t('The governed folder itself cannot be archived') : undefined }
    ];
  }
  function pickMenu(key: string) {
    const folder = menu?.folder;
    if (!folder) return;
    if (key === 'open') void enter(folder);
    else if (key === 'dups') void goto(`/five-s/duplicates/${rootId}?path=${encodeURIComponent(folder.path)}`);
    else if (key === 'copy') void copyText(fullPath(folder)).then((ok) => ok && toast.success(t('Path copied.')));
    else if (key === 'measure') void measureAgain();
    else if (key === 'inherit') void restoreInheritance(folder);
    else if (key === 'archive') archiving = folder;
  }

  // A new measure of the whole governed folder (the scanner walks it again; the page follows the module's figures)
  let measuring = false;
  async function measureAgain() {
    measuring = true;
    try {
      await apiPostData(fetch, `/storage-roots/${rootId}/measure`, {});
      toast.success(t('Measure asked: the figures follow when the scanner has walked the folder.'));
      awaitingRuns = 100;
      watchScanner();
    } catch (e) {
      measuring = false;
      reportUiError(e, t('Unable to measure the folder.'), 'fives.measure');
    }
  }

  // ---- keyboard: ↑ ↓ choose, Enter open, Backspace / Alt+↑ parent folder ----
  function onKeys(event: KeyboardEvent) {
    const el = event.target as HTMLElement | null;
    if (menu || archiving || event.ctrlKey || event.metaKey || (el && (/^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName) || el.isContentEditable || el.closest('[role="dialog"]')))) return;
    const index = selected ? rows.indexOf(selected) : -1;
    if (event.key === 'Backspace' || (event.altKey && event.key === 'ArrowUp')) {
      if (trail.length > 1) { event.preventDefault(); void up(trail.length - 2); }
    } else if (event.altKey) {
      return;
    } else if (event.key === 'ArrowDown' && rows.length) {
      event.preventDefault();
      selected = rows[Math.min(rows.length - 1, index + 1)];
    } else if (event.key === 'ArrowUp' && rows.length) {
      event.preventDefault();
      selected = rows[Math.max(0, index - 1)];
    } else if (event.key === 'Enter' && selected && index >= 0) {
      event.preventDefault();
      void enter(selected);
    }
  }

  function runCard(card: Card) {
    if (card.act === 'archive' && card.folder) archiving = card.folder;
    else if (card.act === 'inherit' && card.folder) void restoreInheritance(card.folder);
    else if (card.folder) { selected = card.folder; void goto(`/five-s/explore/${rootId}`, { keepFocus: true, noScroll: true }); }
  }
  let columns = $derived([
    { key: 'seiri', title: t('Sort (Seiri)'), cards: [
      ...groups.filter((group) => !group.decision?.keep_path).slice(0, 3).map((group): Card => ({
        tag: t('Duplicate'), tone: 'dup', gain: `−${formatBytes(group.wasted)}`,
        title: group.copies[0]?.path.split('\\').pop() ?? '', detail: t('{count} identical copies', { count: group.copies.length }),
        cta: t('Choose the copies'), href: `/five-s/duplicates/${rootId}` })),
      ...children.filter((folder) => share(folder.cold3_bytes, folder.bytes) > 0.8 && folder.bytes > 0).slice(0, 2).map((folder): Card => ({
        tag: t('Old'), tone: 'old', gain: formatBytes(folder.cold3_bytes), title: t('« {name} »: nothing changed for 3 years', { name: folder.name }),
        detail: t('Candidate for archiving.'), cta: t('Archive'), folder, act: 'archive' }))
    ] },
    { key: 'seiton', title: t('Set in order (Seiton)'), cards: [
      ...(current && current.direct_files > 50 && current.folders > 0 ? [{ tag: t('Loose files'), tone: 'old', gain: t('{count} files', { count: current.direct_files }),
        title: t('Files loose at the root of « {name} »', { name: current.name || rootName }), detail: t('File them in the sub-folders.'), cta: t('See the folder'), folder: current } as Card] : [])
    ] },
    { key: 'seiso', title: t('Shine (Seiso)'), cards: [
      ...(junk.files ? [{ tag: t('Clutter'), tone: 'junk', gain: `−${formatBytes(junk.bytes)}`, title: t('{count} clutter files', { count: junk.files }),
        detail: t('Copies, temporary and system files.'), cta: t('See the report'), href: `/five-s/report/${rootId}` } as Card] : [])
    ] },
    { key: 'seiketsu', title: t('Standardise (Seiketsu)'), cards: [
      ...brokenHere.slice(0, 3).map((folder): Card => ({ tag: t('Inheritance'), tone: 'inh', gain: t('broken'), title: t('« {name} » has its own rights', { name: folder.name }),
        detail: t('Its inheritance is broken: check why.'), cta: isAdmin ? t('Restore the inheritance') : t('See the rights'), folder, act: isAdmin ? 'inherit' : undefined })),
      ...explicitHere.filter((folder) => !folder.inheritance_broken).slice(0, 2).map((folder): Card => ({ tag: t('Rights'), tone: 'acl', gain: t('explicit'),
        title: t('Accounts added by hand on « {name} »', { name: folder.name }), detail: t('Prefer the groups of the folder.'), cta: t('See the rights'), folder }))
    ] }
  ]);
  let decisions = $derived(columns.reduce((sum, column) => sum + column.cards.length, 0));

  // ---- tree on the left: the path walked from the root, then the sub-folders of the current folder ----------
  let treeItems = $derived([
    ...trail.map((folder, index) => ({ key: `t${index}`, name: index === 0 ? rootName : folder.name, depth: index, bytes: folder.bytes,
      open: true, current: index === trail.length - 1, folder, index })),
    ...children.map((folder) => ({ key: `c${folder.path}`, name: folder.name, depth: trail.length, bytes: folder.bytes,
      open: false, current: false, folder, index: -1 }))
  ]);
  function pickTree(item: { folder: Folder; index: number }) {
    pickedFile = null;
    if (item.index >= 0) void up(item.index);
    else if (item.folder.folders > 0) void enter(item.folder);
    else selected = item.folder;
  }
  // The tree is drawn by the explorer layout, under this folder: its items and what a click does
  $effect(() => {
    const items = treeItems;
    inside.rootId = rootId;
    inside.items = items.map((item) => ({ key: item.key, name: item.name, depth: item.depth, bytes: item.bytes, current: item.current }));
    inside.pick = (key: string) => {
      const item = items.find((entry) => entry.key === key);
      if (item) pickTree(item);
    };
  });
  onDestroy(() => {
    inside.rootId = null;
    inside.items = [];
    inside.pick = null;
  });

  // ---- a file chosen in the list (or found by the search): its sheet on the right ----
  let pickedFile = $state<FileRow | null>(null);
  let wantedFile = $state<string | null>(null);
  $effect(() => {
    if (!wantedFile) return;
    const hit = files.find((file) => file.path.toLowerCase() === wantedFile?.toLowerCase());
    if (hit) {
      pickedFile = hit;
      wantedFile = null;
    }
  });
  let fileSensitive = $derived(pickedFile ? sensitiveOf(pickedFile.path) : null);
  let fileGroup = $derived(pickedFile ? groups.find((group) => group.copies.some((copy) => copy.path === pickedFile?.path)) ?? null : null);
  const fileFullPath = (file: FileRow) => `${rootPath.replace(/\\$/, '')}\\${file.path}`;

  // ---- list --------------------------------------------------------------------------------------------------
  let rows = $derived(children.filter((folder) =>
    filter === 'all' || (filter === 'dormant' && dormant(folder)) || (filter === 'dups' && groupsUnder(folder.path).length > 0) || (filter === 'broken' && folder.inheritance_broken)));
  let files = $derived(filter === 'all' ? (liveState === 'ok' && liveFiles ? liveFiles : level?.files ?? []) : []);
  const rights = (folder: Folder) =>
    folder.acl == null ? { label: t('not read yet'), tone: 'none' }
      : folder.inheritance_broken ? { label: t('Broken'), tone: 'warn' }
        : (folder.acl ?? []).some((ace) => !ace.inherited && !SYSTEM.test(ace.who)) ? { label: t('Explicit'), tone: 'warn' } : { label: t('Inherited'), tone: 'ok' };
  const FILTERS = (): Array<[typeof filter, string]> => [['all', t('All')], ['dormant', t('Not opened for 2 years')], ['dups', t('With duplicates')], ['broken', t('Broken inheritance')]];

  // ---- sheet of the folder chosen -----------------------------------------------------------------------------
  let sheetGroups = $derived(selected ? groupsUnder(selected.path).slice(0, 3) : []);
  /** The copy to keep: not a « copy », not in a download or backup folder, then the most recently changed */
  function suggestion(group: Group): string {
    const weak = /(copie|copy|\(\d+\)|download|t[ée]l[ée]chargement|backup|tmp|temp)/i;
    const ranked = [...group.copies].sort((a, b) =>
      Number(weak.test(a.path)) - Number(weak.test(b.path)) || String(b.modified ?? '').localeCompare(String(a.modified ?? '')) || a.path.length - b.path.length);
    return group.decision?.keep_path ?? ranked[0]?.path ?? '';
  }
  let chain = $derived(trail.map((folder) => ({ name: folder.name || rootName, broken: folder.inheritance_broken === true })));
  const LEVEL = (): Record<string, string> => ({ F: t('Full control'), W: t('Modify'), R: t('Read') });
  const levelLabel = (value: string) => (value.startsWith('!') ? `${t('Denied')} · ` : '') + (LEVEL()[value.replace('!', '')] ?? value);

  const exportLevel = () =>
    downloadCsv(csvFilename(`5s-${rootName}`), [
      { header: t('Path'), value: (row: any) => row.path },
      { header: t('Size'), value: (row: any) => row.bytes },
      { header: t('Files'), value: (row: any) => row.files },
      { header: t('Created'), value: (row: any) => row.created_at ?? '' },
      { header: t('Last change'), value: (row: any) => row.last_modified ?? '' },
      { header: t('Last access'), value: (row: any) => row.last_access ?? '' },
      { header: t('Not modified for 1 year'), value: (row: any) => row.cold1_bytes },
      { header: t('Inheritance'), value: (row: any) => (row.inheritance_broken == null ? '' : row.inheritance_broken ? 'cassé' : 'hérité') }
    ], children);
  const duration = (ms: number | null | undefined) =>
    ms ? (ms < 60000 ? `${Math.round(ms / 1000)} s` : `${Math.floor(ms / 60000)} min ${String(Math.round((ms % 60000) / 1000)).padStart(2, '0')} s`) : '—';
</script>

<div class="fx">
  <FolderHeader {rootId} name={rootName} path={rootPath} current={view === 'workshop' ? 'workshop' : 'content'}
    counts={{ workshop: decisions, duplicates: groups.length - decided }}>
    {#snippet actions()}
      <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" onclick={exportLevel} disabled={!children.length}><i class="bi bi-download" aria-hidden="true"></i>{t('Export CSV')}</button>
    {/snippet}
  </FolderHeader>

  {#if loading}
    <LoadingState skeleton="page" rows={6} />
  {:else if error}
    <InlineAlert tone="error">{error}</InlineAlert>
  {:else if !current || !root}
    <InlineAlert tone="info">{t('The detailed tree appears after the next measure of this folder with the 5S module (Measure on its page).')}</InlineAlert>
  {:else}
    {#if trail.length > 1}
    <header class="fx__head">
      <div>
        <nav class="fx__crumbs" aria-label={t('Path')}>
          <button type="button" class="fx__up" disabled={busy || trail.length < 2} onclick={() => up(trail.length - 2)}
            title={t('Parent folder (Backspace)')} aria-label={t('Parent folder')}><i class="bi bi-arrow-up" aria-hidden="true"></i></button>
          {#each trail as step, index (step.path + index)}
            {#if index}<i class="bi bi-chevron-right" aria-hidden="true"></i>{/if}
            <button type="button" class:is-current={index === trail.length - 1} disabled={busy} onclick={() => up(index)}>{index === 0 ? rootName : step.name}</button>
          {/each}
          {#if busy}<span class="b2s-spinner b2s-spinner--sm" aria-hidden="true"></span>{/if}
        </nav>
      </div>
    </header>
    {/if}

    <!-- The scanner itself is not shown: only a measure in progress, or the error of the last one -->
    {#if scanner?.running}
      <p class="fx__note"><span class="fx__dot is-busy" aria-hidden="true"></span>{t('Measure in progress')}{scanner.running.progress?.chunks_total ? ` · ${scanner.running.progress.chunks_done}/${scanner.running.progress.chunks_total}` : ''}</p>
    {/if}
    {#if scanner?.last?.status === 'failed'}<p class="fx__note is-bad"><i class="bi bi-exclamation-triangle" aria-hidden="true"></i>{scanner.last.error}</p>{/if}
    <MeasureCompleteness value={level?.completeness ?? scanner?.last?.completeness} />

    <section class="fx__kpis" aria-label={t('Figures')}>
      <div><span>{t('Volume')}</span><b>{formatBytes(current.bytes)}</b><small>{t('{count} files', { count: current.files.toLocaleString('fr-FR') })}</small></div>
      <div><span>{t('Not modified for 1 year')}</span><b class={share(current.cold1_bytes, current.bytes) > 0.6 ? 'is-warn' : ''}>{pct(current.cold1_bytes, current.bytes)} %</b><small>{formatBytes(current.cold1_bytes)}</small></div>
      <div><span>{t('Not opened for 2 years')}</span><b class={share(dormantBytes, current.bytes) > 0.4 ? 'is-warn' : ''}>{pct(dormantBytes, current.bytes)} %</b><small>{t('of the sub-folders')}</small></div>
      <div><span>{t('Duplicates')}</span><b class={wasted ? 'is-bad' : ''}>{formatBytes(wasted)}</b><small>{t('{count} group(s), {done} decided', { count: groups.length, done: decided })}</small></div>
      <div><span>{t('Rights off the rule')}</span><b class={brokenHere.length || explicitHere.length ? 'is-bad' : ''}>{brokenHere.length + explicitHere.length}</b><small>{t('{count} broken inheritance(s) here', { count: brokenHere.length })}</small></div>
      <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
      <div class="fx__score" tabindex="0" role="group" aria-describedby="fx-score-card"><span>{t('5S score')}</span><b style={`color:${tone(score)}`}>{score ?? '—'} / 100</b><small>{t('same score as the 5S page')}</small>
        <div class="fx__score-card" id="fx-score-card" role="tooltip">
          <strong>{t('5S score of {name}', { name: rootName })}{#if previousScore != null}<em>{previousScore} → {score}</em>{/if}</strong>
          {#each pillars as pillar (pillar.jp)}
            <span class="fx__score-row"><span>{pillar.fr}</span><i aria-hidden="true"><i style={`width:${Math.max(2, pillar.score ?? 0)}%;background:${tone(pillar.score)}`}></i></i><b>{pillar.score ?? '—'}</b></span>
          {/each}
        </div>
      </div>
    </section>

    <div class="fx__body">
      <main class="fx__main">
        {#if view === 'explorer'}
          <FileSearch {rootId} onOpen={(hit) => { wantedFile = hit.path; void openFolder(hit.path.split('\\').slice(0, -1).join('\\')); }} />
          <div class="fx__filters" role="radiogroup" aria-label={t('Filter')}>
            {#each FILTERS() as [key, label] (key)}
              <button type="button" class:is-on={filter === key} onclick={() => (filter = key)}>{label}</button>
            {/each}
          </div>
          <div class="fx__table">
            <table class="b2s-table">
              <thead><tr>
                <th>{t('Name')}</th><th class="fx__num">{t('Size')}</th><th>{t('Created')}</th><th>{t('Last change')}</th><th>{t('Last access')}</th>
                <th>{t('Age')}</th><th>{t('Rights')}</th><th class="fx__num">{t('Duplicates')}</th>
              </tr></thead>
              <tbody>
                {#each rows as folder (folder.path)}
                  {@const right = rights(folder)}
                  {@const dups = groupsUnder(folder.path).length}
                  <tr class:is-sel={selected === folder && !pickedFile} onclick={() => { selected = folder; pickedFile = null; }} ondblclick={() => enter(folder)} oncontextmenu={(event) => openMenu(folder, event)}>
                    <td class="fx__name"><i class="bi bi-folder-fill" aria-hidden="true"></i>
                      {#if folder.folders > 0}<button type="button" class="b2s-link-btn" onclick={(event) => { event.stopPropagation(); enter(folder); }}>{folder.name}</button>{:else}<span>{folder.name}</span>{/if}
                      {#each folderTags.get(folder.path.toLowerCase()) ?? [] as tag (tag.id)}<TagPill small label={tag.name} color={tag.color ?? null} policy={tag.policy ?? null} automatic={Boolean(tag.automatic)} />{/each}</td>
                    <td class="fx__num">{formatBytes(folder.bytes)}</td>
                    <td>{folder.created_at ? formatDate(folder.created_at) : '—'}</td>
                    <td>{folder.last_modified ? formatDate(folder.last_modified) : '—'}</td>
                    <td class:is-warn={dormant(folder)}>{folder.last_access ? formatDate(folder.last_access) : '—'}</td>
                    <td><span class="fx__age" title={t('{fresh} % recent, {mid} % > 1 year, {old} % > 3 years', { fresh: 100 - pct(folder.cold1_bytes, folder.bytes), mid: pct(folder.cold1_bytes - folder.cold3_bytes, folder.bytes), old: pct(folder.cold3_bytes, folder.bytes) })}
                      style={`--a:${100 - pct(folder.cold1_bytes, folder.bytes)}%;--b:${100 - pct(folder.cold3_bytes, folder.bytes)}%`}></span></td>
                    <td><span class={`fx__pill is-${right.tone}`}>{right.label}</span></td>
                    <td class="fx__num" class:is-bad={dups > 0}>{dups || '—'}</td>
                  </tr>
                {/each}
                {#each files as file (file.path)}
                  {@const flag = sensitiveOf(file.path)}
                  <tr class="is-file" class:is-sel={pickedFile?.path === file.path} onclick={() => (pickedFile = file)}>
                    <td class="fx__name"><i class="bi bi-file-earmark" aria-hidden="true"></i><code title={file.path} data-copy={file.path}>{file.name}</code>
                      {#if flag}<span class="fx__pill is-bad" title={flag.rule}><i class="bi bi-shield-exclamation" aria-hidden="true"></i> {t('Sensitive')}</span>{/if}</td>
                    <td class="fx__num">{formatBytes(file.size)}</td><td>{file.created ? formatDate(file.created) : '—'}</td><td>{file.modified ? formatDate(file.modified) : '—'}</td>
                    <td title={t('Indicative: Windows updates it late, or not at all when it is turned off')}>{file.accessed ? formatDate(file.accessed) : '—'}</td><td></td>
                    <td class="fx__owner">{#if file.owner}<span title={t('NTFS owner')}>{file.owner}</span>{/if}</td>
                    <td class="fx__num">{groups.some((group) => group.copies.some((copy) => copy.path === file.path)) ? '•' : '—'}</td>
                  </tr>
                {/each}
                {#if filter === 'all' && liveState === 'loading'}
                  <tr class="fx__live"><td colspan="8"><span class="b2s-spinner b2s-spinner--sm" aria-hidden="true"></span>{t('Reading the files of this folder on the server…')}</td></tr>
                {:else if filter === 'all' && liveState === 'failed' && level?.files_source === 'inventory'}
                  <tr class="fx__live is-info"><td colspan="8"><i class="bi bi-clock-history" aria-hidden="true"></i>{t('State of the measure of {date}: the server cannot be read now ({error}).', { date: level.files_at ? formatDateTime(level.files_at) : '—', error: liveError || '—' })}
                    {#if (level.files_total ?? 0) > files.length} {t('The {shown} biggest files of {total} are listed.', { shown: files.length.toLocaleString('fr-FR'), total: (level.files_total ?? 0).toLocaleString('fr-FR') })}{/if}
                    <button type="button" class="b2s-link-btn" onclick={() => level?.node && loadLive(level.node.path)}>{t('Try again')}</button></td></tr>
                {:else if filter === 'all' && liveState === 'failed'}
                  <tr class="fx__live is-warn"><td colspan="8"><i class="bi bi-exclamation-triangle" aria-hidden="true"></i>{t('Partial list: only the files followed for the duplicates are shown (the server could not be read: {error}).', { error: liveError || '—' })}
                    <button type="button" class="b2s-link-btn" onclick={() => level?.node && loadLive(level.node.path)}>{t('Try again')}</button></td></tr>
                {:else if filter === 'all' && liveState === 'ok' && liveTotal > files.length}
                  <tr class="fx__live"><td colspan="8">{t('The {shown} biggest files of {total} are listed.', { shown: files.length.toLocaleString('fr-FR'), total: liveTotal.toLocaleString('fr-FR') })}</td></tr>
                {/if}
                {#if !rows.length && !files.length && liveState !== 'loading'}<tr><td colspan="8" class="fx__empty">{t('Nothing here for this filter.')}</td></tr>{/if}
              </tbody>
            </table>
          </div>
        {:else}
          {#if history.length}
            <section class="fx__trend" aria-label={t('Trend')}>
              <span><b style={`color:${tone(latest?.score ?? null)}`}>{latest?.score}</b> / 100
                {#if previousScore != null && latest}<em class={latest.score >= previousScore ? 'is-up' : 'is-down'}>{latest.score >= previousScore ? '+' : ''}{latest.score - previousScore} {t('since the previous measure')}</em>{/if}</span>
              <span class="fx__spark" aria-hidden="true">
                {#each history as point (point.measured_at)}<i style={`height:${Math.max(6, point.score)}%;background:${tone(point.score)}`} title={`${formatDate(point.measured_at)} · ${point.score}`}></i>{/each}
              </span>
              <small>{t('{count} measure(s)', { count: history.length })}</small>
            </section>
          {:else}
            <p class="fx__hint">{t('The trend starts with the next measure: each measure keeps the score of the 5S page.')}{#if scores?.former_model_points} {t('{count} older point(s) of a former computation are not shown.', { count: scores.former_model_points })}{/if}</p>
          {/if}
          <section class="fx__pillars" aria-label={t('Pillars')}>
            {#each pillars as pillar (pillar.jp)}
              <div title={pillar.how}>
                <span class="fx__pill-head"><b>{pillar.jp}</b><strong style={`color:${tone(pillar.score)}`}>{pillar.score ?? '—'}</strong></span>
                <small>{pillar.score == null ? t('not judged: no measure or scan yet') : pillar.fr}</small>
                <span class="fx__bar"><span style={`width:${pillar.score ?? 0}%;background:${tone(pillar.score)}`}></span></span>
              </div>
            {/each}
          </section>
          <section class="fx__board" aria-label={t('Decisions')}>
            {#each columns as column (column.key)}
              <div class="fx__col">
                <header><b>{column.title}</b><small>{column.cards.length}</small></header>
                {#each column.cards as card, index (column.key + index)}
                  <article>
                    <span class="fx__tags"><span class={`fx__tag is-${card.tone}`}>{card.tag}</span><span class="fx__gain">{card.gain}</span></span>
                    <b>{card.title}</b>
                    <small>{card.detail}</small>
                    {#if card.href}<a class="b2s-btn b2s-btn-sm b2s-btn-primary" href={card.href}>{card.cta}</a>
                    {:else if card.folder}<button type="button" class={`b2s-btn b2s-btn-sm ${card.act ? 'b2s-btn-primary' : 'b2s-btn-secondary'}`} disabled={acting} onclick={() => runCard(card)}>{card.cta}</button>{/if}
                  </article>
                {:else}
                  <p class="fx__none">{t('Nothing to decide.')}</p>
                {/each}
              </div>
            {/each}
          </section>
        {/if}
      </main>

      <aside class="fx__sheet" aria-label={pickedFile ? t('Sheet of the file') : t('Sheet of the folder')}>
        {#if pickedFile}
          <section class="fx__card">
            <header class="fx__card-head">
              <h2 class="fx__file-name"><i class="bi bi-file-earmark" aria-hidden="true"></i>{pickedFile.name}</h2>
              <button type="button" class="fx__close" onclick={() => (pickedFile = null)} aria-label={t('Close the sheet of the file')}><i class="bi bi-x-lg" aria-hidden="true"></i></button>
            </header>
            {#if fileSensitive}
              <p class="fx__note is-bad"><b>{t('Sensitive file')}</b>{fileSensitive.rule}</p>
            {/if}
            {#if fileGroup}
              <p class="fx__note is-warn"><b>{t('Duplicate')}</b>{t('{count} identical copies, {size} each.', { count: fileGroup.copies.length, size: formatBytes(fileGroup.size) })}</p>
            {/if}
            <dl>
              <dt>{t('Size')}</dt><dd>{formatBytes(pickedFile.size)}</dd>
              <dt>{t('Owner')}</dt><dd>{pickedFile.owner || '—'}</dd>
              <dt>{t('Created')}</dt><dd>{pickedFile.created ? formatDate(pickedFile.created) : '—'}</dd>
              <dt>{t('Last change')}</dt><dd>{pickedFile.modified ? formatDate(pickedFile.modified) : '—'}</dd>
              <dt>{t('Last access (indicative)')}</dt><dd>{pickedFile.accessed ? formatDate(pickedFile.accessed) : '—'}</dd>
            </dl>
            <p class="fx__path"><code data-copy={fileFullPath(pickedFile)}>{fileFullPath(pickedFile)}</code></p>
            <div class="fx__file-acts">
              <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" onclick={() => pickedFile && void copyText(fileFullPath(pickedFile)).then(() => toast.success(t('Path copied.')))}>
                <i class="bi bi-clipboard" aria-hidden="true"></i>{t('Copy the path')}</button>
              {#if fileGroup}<a class="b2s-btn b2s-btn-sm b2s-btn-primary" href={`/five-s/duplicates/${rootId}${current?.path ? `?path=${encodeURIComponent(current.path)}` : ''}`}><i class="bi bi-files" aria-hidden="true"></i>{t('Choose the copy to keep')}</a>{/if}
            </div>
            {#if fileGroup}
              <div class="fx__dup">
                {#each fileGroup.copies as copy (copy.path)}<div class:is-keep={copy.path === pickedFile.path}><code title={copy.path}>{copy.path}</code><b>{copy.path === pickedFile.path ? t('This one') : t('Copy')}</b></div>{/each}
              </div>
            {/if}
          </section>
          <section class="fx__card">
            <h3>{t('Who can open it')}</h3>
            <p class="fx__hint">{t('A file follows the rights of its folder.')}</p>
            <AccessPanel {rootId} path={current?.path ?? ''} />
          </section>
        {:else if selected}
          <section class="fx__card">
            <header class="fx__card-head">
              <h2>{selected.name || rootName}</h2>
              {#if selected.inheritance_broken}<span class="fx__pill is-warn">{t('Broken inheritance')}</span>{/if}
              {#if selected.partial}<span class="fx__pill is-warn" title={t('A part of this folder could not be read or listed in full by the last measure: its figures may be below reality.')}>{t('Seen in part')}</span>{/if}
            </header>
            {#if selected !== current && selected.folders > 0}
              <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-primary" onclick={() => selected && enter(selected)}><i class="bi bi-box-arrow-in-down-right" aria-hidden="true"></i>{t('Open ({count} sub-folders)', { count: selected.folders })}</button>
            {/if}
            <ol class="fx__time">
              <li><span class="is-c"></span><b>{t('Created')}</b><small>{selected.created_at ? formatDate(selected.created_at) : '—'}</small></li>
              <li><span class="is-m"></span><b>{t('Last change')}</b><small>{selected.last_modified ? formatDate(selected.last_modified) : '—'}</small></li>
              <li title={t('Windows updates the last access late (up to an hour) or not at all when it is turned off on the server: an indication only.')}><span class="is-a"></span><b>{t('Last access (indicative)')}</b><small>{selected.last_access ? formatDate(selected.last_access) : '—'}</small></li>
            </ol>
            <dl>
              <dt>{t('Volume')}</dt><dd>{formatBytes(selected.bytes)} · {pct(selected.bytes, root.bytes)} %</dd>
              <dt>{t('Files')}</dt><dd>{selected.files.toLocaleString('fr-FR')} · {t('{count} right in it', { count: selected.direct_files })}</dd>
              <dt>{t('Not modified for 3 years')}</dt><dd>{formatBytes(selected.cold3_bytes)}</dd>
            </dl>
            <p class="fx__path"><code data-copy={fullPath(selected)}>{selected.path || rootPath}</code></p>
            {#if selected !== root && selected.path}
              <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" disabled={acting} onclick={() => (archiving = selected)}><i class="bi bi-archive" aria-hidden="true"></i>{t('Archive this folder')}</button>
            {/if}
          </section>

          <section class="fx__card">
            <h3>{t('Rights')}</h3>
            {#if selected.acl == null}
              <p class="fx__hint">{t('Read at the next full measure of the folder.')}</p>
            {:else}
              <ul class="fx__acl">
                {#each selected.acl as ace (ace.who + ace.level)}
                  <li class:is-own={!ace.inherited} class:is-orphan={ace.orphan}>
                    <span><b>{ace.who}</b><small>{ace.orphan ? `${t('account deleted from the directory (orphan SID)')} · ` : ''}{ace.inherited ? t('inherited') : t('set on this folder')}</small></span>
                    <em class={`is-${ace.level.replace('!', 'deny-')}`}>{levelLabel(ace.level)}</em>
                  </li>
                {/each}
              </ul>
              {#if (selected.acl_total ?? 0) > selected.acl.length}<p class="fx__hint">{t('and {count} more right(s) not kept by the measure (64 kept at most)', { count: (selected.acl_total ?? 0) - selected.acl.length })}</p>{/if}
              {#if selected.inheritance_broken && isAdmin && selected.path}
                <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-primary" disabled={acting} onclick={() => selected && restoreInheritance(selected)}><i class="bi bi-arrow-repeat" aria-hidden="true"></i>{t('Restore the inheritance')}</button>
              {/if}
              <div class="fx__chain"><span>{t('Inheritance')}</span>
                {#each chain as link, index (index)}<span class:is-broken={link.broken}>{link.broken ? '✕ ' : ''}{link.name}</span>{/each}
              </div>
            {/if}
          </section>

          <section class="fx__card">
            <h3>{t('Who has access and why')}</h3>
            <AccessPanel {rootId} path={selected.path} />
          </section>

          <section class="fx__card">
            <h3>{t('Duplicates here')}</h3>
            {#each sheetGroups as group (group.fingerprint + group.size)}
              {@const keep = suggestion(group)}
              <div class="fx__dup">
                <small>{group.copies[0]?.path.split('\\').pop()} · {formatBytes(group.size)} · {group.fingerprint.slice(0, 10)}…</small>
                {#each group.copies as copy (copy.path)}
                  <div class:is-keep={copy.path === keep}><code title={copy.path} data-copy={copy.path}>{copy.path}</code><b>{copy.path === keep ? (group.decision?.keep_path ? t('Kept') : t('Suggested')) : t('Copy')}</b></div>
                {/each}
              </div>
            {:else}
              <p class="fx__hint">{t('No duplicate known here.')}</p>
            {/each}
            {#if sheetGroups.length}<a class="b2s-btn b2s-btn-sm b2s-btn-primary" href={`/five-s/duplicates/${rootId}${selected.path ? `?path=${encodeURIComponent(selected.path)}` : ''}`}>{t('See the duplicates of this folder ({count})', { count: groupsUnder(selected.path).length })}</a>{/if}
          </section>
        {/if}
      </aside>
    </div>
  {/if}
</div>

<ConfirmActionModal
  open={Boolean(archiving)}
  title={t('Archive « {name} »', { name: archiving?.name ?? '' })}
  subtitle={t('The folder ({size}) moves whole to « _B2S_Archives » at the root of the same share: its users no longer find it at its place. Nothing is deleted, it can be restored at any time from Duplicates › Quarantine, and the move is written to the audit log.', { size: formatBytes(archiving?.bytes ?? 0) })}
  confirmLabel={t('Archive')}
  onConfirm={confirmArchive}
  onClose={() => (archiving = null)}
/>

<svelte:window onkeydown={onKeys} />

<ContextMenu open={Boolean(menu)} title={menu?.folder.name || rootName} subtitle={menu ? fullPath(menu.folder) : ''}
  items={menu ? menuItems(menu.folder) : []} at={menu?.at ?? { x: 0, y: 0 }} onClose={() => (menu = null)} onPick={pickMenu} />

<style>
  .fx__file-name { display: flex; gap: 8px; align-items: flex-start; word-break: break-word; }
  .fx__close { margin-left: auto; width: 30px; height: 30px; border: 0; border-radius: 8px; background: none; color: var(--b2s-color-text-muted); cursor: pointer; }
  .fx__close:hover { background: var(--b2s-color-surface-soft); }
  .fx__note { display: grid; gap: 2px; margin: 0; padding: 10px 12px; border-radius: 10px; font-size: var(--b2s-fs-sm); }
  .fx__note.is-bad { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger-strong); }
  .fx__note.is-warn { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .fx__file-acts { display: flex; flex-wrap: wrap; gap: 8px; }
  tr.is-file { cursor: pointer; }
  .fx { display: grid; grid-template-columns: minmax(0, 1fr); gap: 14px; min-width: 0; padding: 26px 28px 80px; }
  .fx__head { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; justify-content: space-between; }
  .fx__crumbs { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; font-size: 13px; }
  .fx__crumbs button { border: 0; background: none; padding: 2px 4px; color: var(--b2s-color-primary); cursor: pointer; font: inherit; }
  .fx__crumbs button.is-current { color: inherit; font-weight: 600; cursor: default; }
  .fx__crumbs i { font-size: 11px; color: var(--b2s-color-text-muted); }
  .fx__dot { width: 8px; height: 8px; border-radius: 50%; background: var(--b2s-brand); }
  .fx__dot.is-busy { background: var(--b2s-accent-vivid); }
  .fx__kpis { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 10px; }
  .fx__kpis > div { display: grid; gap: 2px; padding: 12px 14px; border: 1px solid var(--b2s-color-border); border-radius: 12px; background: var(--b2s-color-surface, #fff); }
  .fx__kpis span, .fx__kpis small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .fx__kpis b { font-size: 20px; }
  .fx__kpis b.is-warn { color: var(--b2s-color-warning-strong); }
  .fx__kpis b.is-bad { color: var(--b2s-color-danger-strong); }
  .fx__body { display: grid; grid-template-columns: minmax(0, 1fr) 360px; gap: 14px; align-items: start; }
  .fx__main { display: grid; gap: 12px; min-width: 0; }
  .fx__filters { display: flex; flex-wrap: wrap; gap: 6px; }
  .fx__filters button { height: 30px; padding: 0 12px; border: 1px solid var(--b2s-color-border); border-radius: 999px; background: var(--b2s-color-surface, #fff); font: inherit; font-size: var(--b2s-fs-sm); cursor: pointer; }
  .fx__filters button.is-on { background: var(--b2s-accent); border-color: var(--b2s-accent); color: #fff; }
  .fx__table { overflow-x: auto; border: 1px solid var(--b2s-color-border); border-radius: 12px; background: var(--b2s-color-surface, #fff); }
  .fx__table tr { cursor: default; }
  .fx__table tbody tr:hover td { background: var(--b2s-color-surface-soft); }
  .fx__table tr.is-sel td { background: var(--b2s-accent-soft); }
  .fx__name { display: flex; gap: 8px; align-items: center; min-width: 0; }
  .fx__name i.bi-folder-fill { color: var(--b2s-color-warning); }
  .fx__name code { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: var(--b2s-fs-xs); max-width: 360px; }
  .fx__num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
  td.is-warn { color: var(--b2s-color-warning-strong); }
  td.is-bad { color: var(--b2s-color-danger-strong); font-weight: 600; }
  .fx__age { display: block; width: 44px; height: 8px; border-radius: 4px; background: linear-gradient(90deg, var(--b2s-accent) 0 var(--a), var(--b2s-color-warning) var(--a) var(--b), var(--b2s-color-danger-strong) var(--b) 100%); }
  .fx__pill { padding: 2px 9px; border-radius: 999px; font-size: var(--b2s-fs-xs); font-weight: 600; white-space: nowrap; }
  .fx__pill.is-ok { background: var(--b2s-color-success-soft); color: var(--b2s-color-success-strong); }
  .fx__pill.is-warn { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .fx__pill.is-none { background: var(--b2s-color-surface-muted); color: var(--b2s-color-text-muted); font-weight: 500; }
  .fx__empty { padding: 20px; text-align: center; color: var(--b2s-color-text-muted); }
  .fx__trend { display: flex; flex-wrap: wrap; gap: 14px; align-items: center; padding: 12px 14px; border: 1px solid var(--b2s-color-border); border-radius: 12px; background: var(--b2s-color-surface, #fff); }
  .fx__trend b { font-size: 24px; }
  .fx__trend em { margin-left: 8px; font-style: normal; font-size: var(--b2s-fs-sm); font-weight: 600; }
  .fx__trend em.is-up { color: var(--b2s-color-success-strong); }
  .fx__trend em.is-down { color: var(--b2s-color-danger-strong); }
  .fx__trend small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .fx__spark { display: flex; align-items: flex-end; gap: 3px; height: 36px; flex: 1 1 200px; }
  .fx__spark i { flex: 0 0 8px; border-radius: 2px; }
  .fx__pillars { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; }
  .fx__pillars > div { display: grid; gap: 4px; padding: 12px; border: 1px solid var(--b2s-color-border); border-radius: 12px; background: var(--b2s-color-surface, #fff); cursor: help; }
  .fx__pill-head { display: flex; justify-content: space-between; align-items: baseline; }
  .fx__pill-head strong { font-size: 20px; }
  .fx__pillars small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .fx__bar { height: 6px; border-radius: 3px; background: var(--b2s-color-surface-muted); overflow: hidden; }
  .fx__bar span { display: block; height: 100%; }
  .fx__board { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; align-items: start; }
  .fx__col { display: grid; gap: 8px; padding: 10px; border-radius: 12px; background: var(--b2s-color-neutral-soft); }
  .fx__col header { display: flex; justify-content: space-between; font-size: var(--b2s-fs-sm); }
  .fx__col article { display: grid; gap: 6px; justify-items: start; padding: 10px; border-radius: 10px; background: #fff; }
  .fx__col article b { font-size: var(--b2s-fs-sm); line-height: 1.35; overflow-wrap: anywhere; }
  .fx__col article small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .fx__tags { display: flex; gap: 6px; flex-wrap: wrap; }
  .fx__tag { padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; }
  .fx__tag.is-dup { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger-strong); }
  .fx__tag.is-old { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .fx__tag.is-junk { background: var(--b2s-color-neutral-soft); color: var(--b2s-color-text-strong); }
  .fx__tag.is-inh { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .fx__tag.is-acl { background: var(--b2s-accent-soft); color: var(--b2s-accent-strong); }
  .fx__gain { padding: 2px 8px; border-radius: 999px; background: var(--b2s-color-surface-muted); font-size: 11px; }
  .fx__none { margin: 4px; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .fx__sheet { position: sticky; top: calc(var(--b2s-shell-top) + 12px); display: grid; grid-template-columns: minmax(0, 1fr); gap: 10px; min-width: 0; }
  .fx__card { display: grid; gap: 10px; min-width: 0; padding: 14px; border: 1px solid var(--b2s-color-border); border-radius: 12px; background: var(--b2s-color-surface, #fff); }
  .fx__card h2 { margin: 0; font-size: 16px; overflow-wrap: anywhere; }
  .fx__card h3 { margin: 0; font-size: var(--b2s-fs-sm); }
  .fx__card-head { display: flex; justify-content: space-between; gap: 8px; align-items: center; }
  .fx__card dl { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 4px 10px; margin: 0; font-size: var(--b2s-fs-sm); }
  .fx__card dt { color: var(--b2s-color-text-muted); }
  .fx__card dd { margin: 0; text-align: right; }
  .fx__time { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px; margin: 0; padding: 0; list-style: none; }
  .fx__time li { display: grid; gap: 2px; justify-items: center; text-align: center; font-size: var(--b2s-fs-xs); }
  .fx__time li span { width: 12px; height: 12px; border-radius: 50%; }
  .fx__time .is-c { background: var(--b2s-color-text-faint); }
  .fx__time .is-m { background: var(--b2s-color-warning); }
  .fx__time .is-a { background: var(--b2s-accent); }
  .fx__time small { color: var(--b2s-color-text-muted); }
  .fx__path code { font-size: var(--b2s-fs-xs); overflow-wrap: anywhere; }
  .fx__hint { margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .fx__acl { display: grid; gap: 6px; margin: 0; padding: 0; list-style: none; font-size: var(--b2s-fs-sm); }
  .fx__acl li { display: flex; justify-content: space-between; gap: 8px; align-items: center; }
  .fx__acl li span { display: grid; min-width: 0; }
  .fx__acl li b { font-weight: 500; overflow-wrap: anywhere; }
  .fx__acl li small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .fx__acl li.is-own b { color: var(--b2s-color-warning-strong); }
  .fx__acl li.is-orphan b { color: var(--b2s-color-text-muted); text-decoration: line-through dotted; }
  .fx__partial { color: var(--b2s-color-warning-strong); font-size: 12px; }
  .fx__pill.is-bad { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger-strong); }
  .fx__owner { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .fx__acl em { font-style: normal; font-size: var(--b2s-fs-xs); font-weight: 600; white-space: nowrap; }
  .fx__acl em.is-F { color: var(--b2s-color-danger-strong); }
  .fx__acl em.is-W { color: var(--b2s-accent); }
  .fx__acl em.is-R { color: var(--b2s-color-success-strong); }
  .fx__acl em[class*='is-deny'] { color: var(--b2s-color-warning-strong); }
  .fx__chain { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; font-size: var(--b2s-fs-xs); }
  .fx__chain span:first-child { color: var(--b2s-color-text-muted); margin-right: 2px; }
  .fx__chain span + span { padding: 2px 8px; border-radius: 999px; background: var(--b2s-color-success-soft); color: var(--b2s-color-success-strong); }
  .fx__chain span.is-broken { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .fx__dup { display: grid; gap: 4px; }
  .fx__dup small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .fx__dup div { display: flex; justify-content: space-between; gap: 8px; padding: 5px 8px; border: 1px solid var(--b2s-color-border); border-radius: 8px; font-size: var(--b2s-fs-xs); }
  .fx__dup div code { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .fx__dup div b { white-space: nowrap; color: var(--b2s-color-danger-strong); }
  .fx__dup div.is-keep { border-color: var(--b2s-color-success-border); background: var(--b2s-color-success-soft); }
  .fx__dup div.is-keep b { color: var(--b2s-color-success-strong); }
  .fx__score { position: relative; outline: none; }
  .fx__score-card { position: absolute; right: 0; top: calc(100% + 8px); z-index: 30; width: 300px; display: grid; gap: 8px; padding: 14px; border-radius: 14px;
    background: var(--b2s-topbar-bg); color: var(--b2s-color-surface-muted); box-shadow: 0 18px 40px rgba(18, 59, 73, 0.3); opacity: 0; visibility: hidden; transform: translateY(-4px);
    transition: opacity 140ms ease, transform 140ms ease, visibility 140ms; pointer-events: none; }
  .fx__score:hover .fx__score-card, .fx__score:focus-within .fx__score-card, .fx__score:focus .fx__score-card { opacity: 1; visibility: visible; transform: none; }
  .fx__score-card strong { display: flex; justify-content: space-between; font-size: var(--b2s-fs-sm); }
  .fx__score-card em { font-style: normal; font-weight: 500; color: var(--b2s-color-border); }
  .fx__score-row { display: grid; grid-template-columns: 96px minmax(0, 1fr) 28px; gap: 8px; align-items: center; font-size: 12px; color: var(--b2s-color-border); }
  .fx__score-row > i { height: 6px; border-radius: 999px; background: var(--b2s-color-text-strong); overflow: hidden; }
  .fx__score-row > i > i { display: block; height: 100%; border-radius: 999px; }
  .fx__score-row b { text-align: right; color: #FFFFFF; }
  .fx__crumbs button.fx__up { width: 26px; height: 26px; display: inline-flex; align-items: center; justify-content: center; margin-right: 4px; border: 1px solid var(--b2s-color-border); border-radius: 8px; color: var(--b2s-color-text); }
  .fx__crumbs button.fx__up:disabled { opacity: 0.4; cursor: default; }
  .fx__live td { padding: 10px 14px; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .fx__live td { display: table-cell; }
  .fx__live .b2s-spinner, .fx__live i { margin-right: 8px; }
  .fx__live.is-warn td { color: var(--b2s-color-warning-strong); background: var(--b2s-color-warning-soft); }
  .fx__live .b2s-link-btn { margin-left: 8px; }
  .fx__live.is-info td { color: var(--b2s-color-info-strong); background: var(--b2s-color-info-soft); }
  .fx__note { display: flex; align-items: center; gap: 8px; margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .fx__note.is-bad { color: var(--b2s-color-danger-strong); }
</style>
