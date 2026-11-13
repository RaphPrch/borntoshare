<script lang="ts">
  import TagPill from '$lib/components/tags/TagPill.svelte';
  import { copyText } from '$lib/utils/clipboard';
  import { onMount } from 'svelte';
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

  /**
   * 5S of a scanned folder in one screen: the scanner banner and the figures, then either the explorer (tree and
   * list, down to the deepest folder) or the 5S workshop (a score per pillar and the decisions to take), and on the
   * right the sheet of the folder chosen: its dates, its rights and inheritance, its duplicates with the copy to keep.
   */
  type Ace = { who: string; level: string; inherited: boolean };
  type Folder = { path: string; parent: string | null; name: string; depth: number; bytes: number; files: number; folders: number;
    direct_bytes: number; direct_files: number; cold1_bytes: number; cold3_bytes: number; last_modified: string | null;
    last_access?: string | null; created_at?: string | null; acl?: Ace[] | null; inheritance_broken?: boolean | null };
  type FileRow = { path: string; name: string; size: number; modified: string | null };
  type Level = { node: Folder | null; children: Folder[]; files: FileRow[]; files_source?: 'inventory' | 'fingerprints'; files_total?: number; files_at?: string | null };
  type Copy = { path: string; modified: string | null };
  type Group = { fingerprint: string; size: number; wasted: number; copies: Copy[]; decision: { keep_path: string | null } | null };
  type ScorePoint = { measured_at: string; score: number; seiri: number; seiton: number; seiso: number; seiketsu: number; shitsuke: number };
  let history: ScorePoint[] = [];
  type Scanner = { last: any; running: any; pieces: number; journal: boolean; last_full_at: string | null; window: any };

  let rootName = '';
  let rootPath = '';
  let junk: { bytes: number; files: number } = { bytes: 0, files: 0 };
  let scanner: Scanner | null = null;
  let groups: Group[] = [];
  let level: Level | null = null;
  let trail: Folder[] = [];
  let selected: Folder | null = null;
  let loading = true;
  let busy = false;
  let error: string | null = null;
  let view: 'explorer' | 'workshop' = 'explorer';
  let filter: 'all' | 'dormant' | 'dups' | 'broken' = 'all';

  $: rootId = Number($page.params.id);
  const NOW = Date.now();
  const YEAR = 365 * 86400000;
  const load = (path: string | null) =>
    apiGetData<Level>(fetch, `/modules/fives/storage-roots/${rootId}/folders`, path == null ? undefined : { path });

  // ---- tags of the sub-folders (policies « also on the sub-folders »), by lower-case path from the share ----
  let folderTags = new Map<string, Array<{ id: number; name: string; color: string | null }>>();
  $: if (rootId) void apiGetList<{ path: string; tags: Array<{ id: number; name: string; color: string | null }> }>(fetch, `/storage-roots/${rootId}/folder-tags`)
    .then((rows) => (folderTags = new Map(rows.map((row) => [row.path.toLowerCase(), row.tags]))))
    .catch(() => null);

  // ---- the files of the open folder, as they are now on the file server (read by a worker) ----
  // The inventory of the module only knows the files fingerprinted for the duplicates: it stays as the fallback.
  type LiveListing = { folders: string[]; files: Array<{ n: string; s: number; t: string | null }>; files_total: number };
  let liveFor: string | null = null;
  let liveFiles: FileRow[] | null = null;
  let liveTotal = 0;
  let liveState: 'idle' | 'loading' | 'ok' | 'failed' = 'idle';
  let liveError = '';
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
      liveFiles = (data?.files ?? []).map((file) => ({ path: prefix + file.n, name: file.n, size: Number(file.s) || 0, modified: file.t ? `${file.t}Z` : null }));
      liveTotal = Number(data?.files_total ?? liveFiles.length);
      liveState = 'ok';
    } catch (error) {
      if (seq !== liveSeq) return;
      liveState = 'failed';
      liveError = error instanceof Error ? error.message : '';
    }
  }
  $: if (level?.node && level.node.path !== liveFor) void loadLive(level.node.path);

  onMount(async () => {
    try {
      const overview = await apiGetData<Record<string, any>>(fetch, `/storage-roots/${rootId}/overview`);
      rootName = String(overview?.storage_root_name ?? `#${rootId}`);
      rootPath = String(overview?.root_path ?? '');
      junk = { bytes: Number(overview?.content?.junk?.bytes ?? 0), files: Number(overview?.content?.junk?.files ?? 0) };
      void apiGetData<{ history: ScorePoint[] }>(fetch, `/modules/fives/storage-roots/${rootId}/scores`).then((data) => (history = data?.history ?? [])).catch(() => null);
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
    } catch {
      error = t('Unable to load the scanned tree of this folder.');
    } finally {
      loading = false;
    }
  });

  async function enter(folder: Folder) {
    if (busy || folder.folders === 0) return;
    busy = true;
    try {
      const next = await load(folder.path);
      if (next?.node) {
        level = next;
        trail = [...trail, next.node];
        selected = next.node;
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
      }
    } finally {
      busy = false;
    }
  }

  // ---- figures ------------------------------------------------------------------------------------------------
  const SYSTEM = /^(AUTORITE NT|NT AUTHORITY|BUILTIN|CREATOR|CREATEUR|Tout le monde|Everyone)/i;
  $: root = trail[0] ?? null;
  $: current = level?.node ?? null;
  const under = (path: string, folder: string) => !folder || path.toLowerCase().startsWith(folder.toLowerCase() + '\\');
  const share = (part: number, whole: number) => (whole > 0 ? part / whole : 0);
  const pct = (part: number, whole: number) => Math.round(share(part, whole) * 100);
  const dormant = (folder: Folder) => Boolean(folder.last_access) && NOW - new Date(String(folder.last_access)).getTime() > 2 * YEAR;
  const groupsUnder = (path: string) => groups.filter((group) => group.copies.some((copy) => under(copy.path, path)));
  $: wasted = groups.reduce((sum, group) => sum + group.wasted, 0);
  $: decided = groups.filter((group) => group.decision?.keep_path).length;
  $: children = level?.children ?? [];
  $: brokenHere = children.filter((folder) => folder.inheritance_broken);
  $: explicitHere = children.filter((folder) => (folder.acl ?? []).some((ace) => !ace.inherited && !SYSTEM.test(ace.who)));
  $: dormantBytes = children.filter(dormant).reduce((sum, folder) => sum + folder.bytes, 0);

  // ---- 5S scores (each one is explained on hover) --------------------------------------------------------------
  $: seiri = root ? Math.round(100 * (1 - Math.min(1, 0.6 * share(root.cold1_bytes, root.bytes) + 4 * share(wasted, root.bytes)))) : 0;
  $: seiton = root ? Math.round(100 * (1 - Math.min(1, 2 * share(root.direct_files, root.files)))) : 0;
  $: seiso = root ? Math.round(100 * (1 - Math.min(1, 50 * share(junk.bytes, root.bytes)))) : 0;
  $: seiketsu = children.length ? Math.round(100 * (1 - Math.min(1, share(brokenHere.length, children.length) + 0.5 * share(explicitHere.length, children.length)))) : 100;
  $: lastDone = scanner?.last?.finished_at ? new Date(scanner.last.finished_at).getTime() : 0;
  $: shitsuke = Math.round((lastDone && NOW - lastDone < 30 * 86400000 ? 50 : lastDone ? 25 : 0) + 50 * share(decided, groups.length || 1));
  // The scores computed by the scanner at each measure (for the whole folder); the browser's own as long as there is none
  $: latest = history.length ? history[history.length - 1] : null;
  $: previousScore = history.length > 1 ? history[history.length - 2].score : null;
  $: pillars = [
    { jp: 'Seiri', fr: t('Sort'), score: latest?.seiri ?? seiri, how: t('Less old data and fewer duplicates: 100 − 60 % × share > 1 year − 4 × share lost to duplicates') },
    { jp: 'Seiton', fr: t('Set in order'), score: latest?.seiton ?? seiton, how: t('Files filed in sub-folders rather than loose at the root') },
    { jp: 'Seiso', fr: t('Shine'), score: latest?.seiso ?? seiso, how: t('Few clutter files (copies, temporary and system files)') },
    { jp: 'Seiketsu', fr: t('Standardise'), score: latest?.seiketsu ?? seiketsu, how: t('Sub-folders that inherit their rights, without accounts added by hand') },
    { jp: 'Shitsuke', fr: t('Sustain'), score: latest?.shitsuke ?? shitsuke, how: t('A recent measure (less than 30 days) and the duplicates decided') }
  ];
  $: score = latest?.score ?? Math.round(pillars.reduce((sum, pillar) => sum + pillar.score, 0) / pillars.length);
  const tone = (value: number) => (value >= 70 ? '#047857' : value >= 45 ? '#B45309' : '#B91C1C');

  // ---- workshop: the decisions, from what was measured -----------------------------------------------------
  type Card = { tag: string; tone: string; gain: string; title: string; detail: string; cta: string; href?: string; folder?: Folder; act?: 'archive' | 'inherit' };

  // ---- real actions: restore the inheritance (worker, administrators), archive a folder (scanner, reversible) ----
  $: isAdmin = Boolean(($page.data as any)?.me?.is_admin);
  let acting = false;
  let archiving: Folder | null = null;
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
  let menu: { folder: Folder; at: { x: number; y: number } } | null = null;
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
    else if (card.folder) { selected = card.folder; view = 'explorer'; }
  }
  $: columns = [
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
  ];
  $: decisions = columns.reduce((sum, column) => sum + column.cards.length, 0);

  // ---- tree on the left: the path walked from the root, then the sub-folders of the current folder ----------
  $: treeItems = [
    ...trail.map((folder, index) => ({ key: `t${index}`, name: index === 0 ? rootName : folder.name, depth: index, bytes: folder.bytes,
      open: true, current: index === trail.length - 1, folder, index })),
    ...children.map((folder) => ({ key: `c${folder.path}`, name: folder.name, depth: trail.length, bytes: folder.bytes,
      open: false, current: false, folder, index: -1 }))
  ];
  function pickTree(item: { folder: Folder; index: number }) {
    if (item.index >= 0) void up(item.index);
    else if (item.folder.folders > 0) void enter(item.folder);
    else selected = item.folder;
  }

  // ---- list --------------------------------------------------------------------------------------------------
  $: rows = children.filter((folder) =>
    filter === 'all' || (filter === 'dormant' && dormant(folder)) || (filter === 'dups' && groupsUnder(folder.path).length > 0) || (filter === 'broken' && folder.inheritance_broken));
  $: files = filter === 'all' ? (liveState === 'ok' && liveFiles ? liveFiles : level?.files ?? []) : [];
  const rights = (folder: Folder) =>
    folder.acl == null ? { label: t('not read yet'), tone: 'none' }
      : folder.inheritance_broken ? { label: t('Broken'), tone: 'warn' }
        : (folder.acl ?? []).some((ace) => !ace.inherited && !SYSTEM.test(ace.who)) ? { label: t('Explicit'), tone: 'warn' } : { label: t('Inherited'), tone: 'ok' };
  const FILTERS = (): Array<[typeof filter, string]> => [['all', t('All')], ['dormant', t('Not opened for 2 years')], ['dups', t('With duplicates')], ['broken', t('Broken inheritance')]];

  // ---- sheet of the folder chosen -----------------------------------------------------------------------------
  $: sheetGroups = selected ? groupsUnder(selected.path).slice(0, 3) : [];
  /** The copy to keep: not a « copy », not in a download or backup folder, then the most recently changed */
  function suggestion(group: Group): string {
    const weak = /(copie|copy|\(\d+\)|download|t[ée]l[ée]chargement|backup|tmp|temp)/i;
    const ranked = [...group.copies].sort((a, b) =>
      Number(weak.test(a.path)) - Number(weak.test(b.path)) || String(b.modified ?? '').localeCompare(String(a.modified ?? '')) || a.path.length - b.path.length);
    return group.decision?.keep_path ?? ranked[0]?.path ?? '';
  }
  $: chain = trail.map((folder) => ({ name: folder.name || rootName, broken: folder.inheritance_broken === true }));
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
  <div class="fx__top">
    <a class="b2s-btn b2s-btn-sm b2s-btn-secondary" href="/five-s"><i class="bi bi-arrow-left" aria-hidden="true"></i>{t('All the folders')}</a>
    <span class="fx__links">
      <a class="b2s-btn b2s-btn-sm b2s-btn-secondary" href={`/five-s/duplicates/${rootId}`}><i class="bi bi-files" aria-hidden="true"></i>{t('Duplicates')}</a>
      <a class="b2s-btn b2s-btn-sm b2s-btn-secondary" href={`/five-s/report/${rootId}`}><i class="bi bi-file-earmark-text" aria-hidden="true"></i>{t('Report')}</a>
      <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" on:click={exportLevel} disabled={!children.length}><i class="bi bi-download" aria-hidden="true"></i>{t('Export CSV')}</button>
    </span>
  </div>

  {#if loading}
    <LoadingState skeleton="page" rows={6} />
  {:else if error}
    <InlineAlert tone="error">{error}</InlineAlert>
  {:else if !current || !root}
    <InlineAlert tone="info">{t('The detailed tree appears after the next measure of this folder with the 5S module (Measure on its page).')}</InlineAlert>
  {:else}
    <header class="fx__head">
      <div>
        <nav class="fx__crumbs" aria-label={t('Path')}>
          <button type="button" class="fx__up" disabled={busy || trail.length < 2} on:click={() => up(trail.length - 2)}
            title={t('Parent folder (Backspace)')} aria-label={t('Parent folder')}><i class="bi bi-arrow-up" aria-hidden="true"></i></button>
          {#each trail as step, index (step.path + index)}
            {#if index}<i class="bi bi-chevron-right" aria-hidden="true"></i>{/if}
            <button type="button" class:is-current={index === trail.length - 1} disabled={busy} on:click={() => up(index)}>{index === 0 ? rootName : step.name}</button>
          {/each}
          {#if busy}<span class="b2s-spinner b2s-spinner--sm" aria-hidden="true"></span>{/if}
        </nav>
        <h1>{current.name || rootName}</h1>
      </div>
      <div class="fx__tabs" role="tablist" aria-label={t('View')}>
        <button type="button" role="tab" aria-selected={view === 'explorer'} class:is-on={view === 'explorer'} on:click={() => (view = 'explorer')}>{t('Explorer')}</button>
        <button type="button" role="tab" aria-selected={view === 'workshop'} class:is-on={view === 'workshop'} on:click={() => (view = 'workshop')}>{t('5S workshop')}{#if decisions}<span>{decisions}</span>{/if}</button>
      </div>
    </header>

    <section class="fx__scan" aria-label={t('Scanner')}>
      <span class="fx__scan-name"><span class="fx__dot" class:is-busy={Boolean(scanner?.running)} aria-hidden="true"></span>{t('5S scanner')}{scanner?.last?.scanner ? ` · ${scanner.last.scanner}` : ''}</span>
      {#if scanner?.running}
        <span>{t('Measure in progress')}{scanner.running.progress?.chunks_total ? ` · ${scanner.running.progress.chunks_done}/${scanner.running.progress.chunks_total}` : ''}</span>
      {/if}
      <span>{t('Last measure')} <b>{scanner?.last?.finished_at ? `${formatDate(scanner.last.finished_at)} (${timeAgo(scanner.last.finished_at)})` : '—'}</b></span>
      <span>{t('Mode')} <b>{scanner?.last?.mode === 'incremental' ? t('incremental') : scanner?.last?.mode === 'full' ? t('full') : '—'}</b> · {duration(scanner?.last?.elapsed_ms)}</span>
      <span>{t('Pieces')} <b>{scanner?.pieces ?? 0}</b>{scanner?.last?.pieces_kept ? ` · ${t('{count} kept', { count: scanner.last.pieces_kept })}` : ''}</span>
      <span>{t('Change journal')} <b class:is-warn={!scanner?.journal}>{scanner?.journal ? t('available: incremental scans') : t('unavailable: full scans only')}</b></span>
      {#if scanner?.window}<span>{t('Window')} <b>{scanner.window.window_start}–{scanner.window.window_end}</b>{scanner.window.full_every_days ? ` · ${t('full every {days} d', { days: scanner.window.full_every_days })}` : ''}</span>{/if}
      {#if scanner?.last?.status === 'failed'}<span class="fx__scan-err">{scanner.last.error}</span>{/if}
    </section>

    <section class="fx__kpis" aria-label={t('Figures')}>
      <div><span>{t('Volume')}</span><b>{formatBytes(current.bytes)}</b><small>{t('{count} files', { count: current.files.toLocaleString('fr-FR') })}</small></div>
      <div><span>{t('Not modified for 1 year')}</span><b class={share(current.cold1_bytes, current.bytes) > 0.6 ? 'is-warn' : ''}>{pct(current.cold1_bytes, current.bytes)} %</b><small>{formatBytes(current.cold1_bytes)}</small></div>
      <div><span>{t('Not opened for 2 years')}</span><b class={share(dormantBytes, current.bytes) > 0.4 ? 'is-warn' : ''}>{pct(dormantBytes, current.bytes)} %</b><small>{t('of the sub-folders')}</small></div>
      <div><span>{t('Duplicates')}</span><b class={wasted ? 'is-bad' : ''}>{formatBytes(wasted)}</b><small>{t('{count} group(s), {done} decided', { count: groups.length, done: decided })}</small></div>
      <div><span>{t('Rights off the rule')}</span><b class={brokenHere.length || explicitHere.length ? 'is-bad' : ''}>{brokenHere.length + explicitHere.length}</b><small>{t('{count} broken inheritance(s) here', { count: brokenHere.length })}</small></div>
      <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
      <div class="fx__score" tabindex="0" role="group" aria-describedby="fx-score-card"><span>{t('5S score')}</span><b style={`color:${tone(score)}`}>{score} / 100</b><small>{t('average of the 5 pillars')}</small>
        <div class="fx__score-card" id="fx-score-card" role="tooltip">
          <strong>{t('5S score of {name}', { name: rootName })}{#if previousScore != null}<em>{previousScore} → {score}</em>{/if}</strong>
          {#each pillars as pillar (pillar.jp)}
            <span class="fx__score-row"><span>{pillar.fr}</span><i aria-hidden="true"><i style={`width:${Math.max(2, pillar.score)}%;background:${tone(pillar.score)}`}></i></i><b>{pillar.score}</b></span>
          {/each}
        </div>
      </div>
    </section>

    <div class="fx__body">
      <main class="fx__main">
        {#if view === 'explorer'}
          <div class="fx__filters" role="radiogroup" aria-label={t('Filter')}>
            {#each FILTERS() as [key, label] (key)}
              <button type="button" class:is-on={filter === key} on:click={() => (filter = key)}>{label}</button>
            {/each}
          </div>
          <div class="fx__split">
          <nav class="fx__tree" aria-label={t('Tree')}>
            {#each treeItems as item (item.key)}
              <button type="button" class:is-current={item.current} class:is-sel={selected === item.folder} style={`padding-left:${10 + item.depth * 14}px`}
                on:click={() => pickTree(item)} on:contextmenu={(event) => openMenu(item.folder, event)} title={item.folder.path || rootPath}>
                <i class={`bi ${item.open ? 'bi-folder2-open' : item.folder.folders > 0 ? 'bi-folder-fill' : 'bi-folder'}`} aria-hidden="true"></i>
                <span>{item.name}</span>
                <small>{formatBytes(item.bytes)}</small>
              </button>
            {/each}
          </nav>
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
                  <tr class:is-sel={selected === folder} on:click={() => (selected = folder)} on:dblclick={() => enter(folder)} on:contextmenu={(event) => openMenu(folder, event)}>
                    <td class="fx__name"><i class="bi bi-folder-fill" aria-hidden="true"></i>
                      {#if folder.folders > 0}<button type="button" class="b2s-link-btn" on:click|stopPropagation={() => enter(folder)}>{folder.name}</button>{:else}<span>{folder.name}</span>{/if}
                      {#each folderTags.get(folder.path.toLowerCase()) ?? [] as tag (tag.id)}<TagPill small label={tag.name} color={tag.color ?? null} />{/each}</td>
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
                  <tr class="is-file">
                    <td class="fx__name"><i class="bi bi-file-earmark" aria-hidden="true"></i><code title={file.path} data-copy={file.path}>{file.name}</code></td>
                    <td class="fx__num">{formatBytes(file.size)}</td><td>—</td><td>{file.modified ? formatDate(file.modified) : '—'}</td><td>—</td><td></td><td></td>
                    <td class="fx__num">{groups.some((group) => group.copies.some((copy) => copy.path === file.path)) ? '•' : '—'}</td>
                  </tr>
                {/each}
                {#if filter === 'all' && liveState === 'loading'}
                  <tr class="fx__live"><td colspan="8"><span class="b2s-spinner b2s-spinner--sm" aria-hidden="true"></span>{t('Reading the files of this folder on the server…')}</td></tr>
                {:else if filter === 'all' && liveState === 'failed' && level?.files_source === 'inventory'}
                  <tr class="fx__live is-info"><td colspan="8"><i class="bi bi-clock-history" aria-hidden="true"></i>{t('State of the measure of {date}: the server cannot be read now ({error}).', { date: level.files_at ? formatDateTime(level.files_at) : '—', error: liveError || '—' })}
                    {#if (level.files_total ?? 0) > files.length} {t('The {shown} biggest files of {total} are listed.', { shown: files.length.toLocaleString('fr-FR'), total: (level.files_total ?? 0).toLocaleString('fr-FR') })}{/if}
                    <button type="button" class="b2s-link-btn" on:click={() => level?.node && loadLive(level.node.path)}>{t('Try again')}</button></td></tr>
                {:else if filter === 'all' && liveState === 'failed'}
                  <tr class="fx__live is-warn"><td colspan="8"><i class="bi bi-exclamation-triangle" aria-hidden="true"></i>{t('Partial list: only the files followed for the duplicates are shown (the server could not be read: {error}).', { error: liveError || '—' })}
                    <button type="button" class="b2s-link-btn" on:click={() => level?.node && loadLive(level.node.path)}>{t('Try again')}</button></td></tr>
                {:else if filter === 'all' && liveState === 'ok' && liveTotal > files.length}
                  <tr class="fx__live"><td colspan="8">{t('The {shown} biggest files of {total} are listed.', { shown: files.length.toLocaleString('fr-FR'), total: liveTotal.toLocaleString('fr-FR') })}</td></tr>
                {/if}
                {#if !rows.length && !files.length && liveState !== 'loading'}<tr><td colspan="8" class="fx__empty">{t('Nothing here for this filter.')}</td></tr>{/if}
              </tbody>
            </table>
          </div>
          </div>
        {:else}
          {#if history.length}
            <section class="fx__trend" aria-label={t('Trend')}>
              <span><b style={`color:${tone(score)}`}>{score}</b> / 100
                {#if previousScore != null}<em class={score >= previousScore ? 'is-up' : 'is-down'}>{score >= previousScore ? '+' : ''}{score - previousScore} {t('since the previous measure')}</em>{/if}</span>
              <span class="fx__spark" aria-hidden="true">
                {#each history as point (point.measured_at)}<i style={`height:${Math.max(6, point.score)}%;background:${tone(point.score)}`} title={`${formatDate(point.measured_at)} · ${point.score}`}></i>{/each}
              </span>
              <small>{t('{count} measure(s)', { count: history.length })}</small>
            </section>
          {/if}
          <section class="fx__pillars" aria-label={t('Pillars')}>
            {#each pillars as pillar (pillar.jp)}
              <div title={pillar.how}>
                <span class="fx__pill-head"><b>{pillar.jp}</b><strong style={`color:${tone(pillar.score)}`}>{pillar.score}</strong></span>
                <small>{pillar.fr}</small>
                <span class="fx__bar"><span style={`width:${pillar.score}%;background:${tone(pillar.score)}`}></span></span>
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
                    {:else if card.folder}<button type="button" class={`b2s-btn b2s-btn-sm ${card.act ? 'b2s-btn-primary' : 'b2s-btn-secondary'}`} disabled={acting} on:click={() => runCard(card)}>{card.cta}</button>{/if}
                  </article>
                {:else}
                  <p class="fx__none">{t('Nothing to decide.')}</p>
                {/each}
              </div>
            {/each}
          </section>
        {/if}
      </main>

      <aside class="fx__sheet" aria-label={t('Sheet of the folder')}>
        {#if selected}
          <section class="fx__card">
            <header class="fx__card-head">
              <h2>{selected.name || rootName}</h2>
              {#if selected.inheritance_broken}<span class="fx__pill is-warn">{t('Broken inheritance')}</span>{/if}
            </header>
            {#if selected !== current && selected.folders > 0}
              <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-primary" on:click={() => selected && enter(selected)}><i class="bi bi-box-arrow-in-down-right" aria-hidden="true"></i>{t('Open ({count} sub-folders)', { count: selected.folders })}</button>
            {/if}
            <ol class="fx__time">
              <li><span class="is-c"></span><b>{t('Created')}</b><small>{selected.created_at ? formatDate(selected.created_at) : '—'}</small></li>
              <li><span class="is-m"></span><b>{t('Last change')}</b><small>{selected.last_modified ? formatDate(selected.last_modified) : '—'}</small></li>
              <li><span class="is-a"></span><b>{t('Last access')}</b><small>{selected.last_access ? formatDate(selected.last_access) : '—'}</small></li>
            </ol>
            <dl>
              <dt>{t('Volume')}</dt><dd>{formatBytes(selected.bytes)} · {pct(selected.bytes, root.bytes)} %</dd>
              <dt>{t('Files')}</dt><dd>{selected.files.toLocaleString('fr-FR')} · {t('{count} right in it', { count: selected.direct_files })}</dd>
              <dt>{t('Not modified for 3 years')}</dt><dd>{formatBytes(selected.cold3_bytes)}</dd>
            </dl>
            <p class="fx__path"><code data-copy={fullPath(selected)}>{selected.path || rootPath}</code></p>
            {#if selected !== root && selected.path}
              <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" disabled={acting} on:click={() => (archiving = selected)}><i class="bi bi-archive" aria-hidden="true"></i>{t('Archive this folder')}</button>
            {/if}
          </section>

          <section class="fx__card">
            <h3>{t('Rights')}</h3>
            {#if selected.acl == null}
              <p class="fx__hint">{t('Read at the next full measure of the folder.')}</p>
            {:else}
              <ul class="fx__acl">
                {#each selected.acl as ace (ace.who + ace.level)}
                  <li class:is-own={!ace.inherited}>
                    <span><b>{ace.who}</b><small>{ace.inherited ? t('inherited') : t('set on this folder')}</small></span>
                    <em class={`is-${ace.level.replace('!', 'deny-')}`}>{levelLabel(ace.level)}</em>
                  </li>
                {/each}
              </ul>
              {#if selected.inheritance_broken && isAdmin && selected.path}
                <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-primary" disabled={acting} on:click={() => selected && restoreInheritance(selected)}><i class="bi bi-arrow-repeat" aria-hidden="true"></i>{t('Restore the inheritance')}</button>
              {/if}
              <div class="fx__chain"><span>{t('Inheritance')}</span>
                {#each chain as link, index (index)}<span class:is-broken={link.broken}>{link.broken ? '✕ ' : ''}{link.name}</span>{/each}
              </div>
            {/if}
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
  subtitle={t('The folder ({size}) moves whole to « _B2S_Archives » at the root of the same share: its users no longer find it at its place. It can be restored at any time from the duplicates page (Quarantine).', { size: formatBytes(archiving?.bytes ?? 0) })}
  confirmLabel={t('Archive')}
  onConfirm={confirmArchive}
  onClose={() => (archiving = null)}
/>

<svelte:window on:keydown={onKeys} />

<ContextMenu open={Boolean(menu)} title={menu?.folder.name || rootName} subtitle={menu ? fullPath(menu.folder) : ''}
  items={menu ? menuItems(menu.folder) : []} at={menu?.at ?? { x: 0, y: 0 }} onClose={() => (menu = null)} onPick={pickMenu} />

<style>
  .fx { display: grid; grid-template-columns: minmax(0, 1fr); gap: 14px; min-width: 0; padding: var(--b2s-page-padding); }
  .fx__top { display: flex; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
  .fx__links { display: inline-flex; gap: 8px; flex-wrap: wrap; }
  .fx__head { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; justify-content: space-between; }
  .fx__head h1 { margin: 2px 0 0; font-size: 26px; }
  .fx__crumbs { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; font-size: 13px; }
  .fx__crumbs button { border: 0; background: none; padding: 2px 4px; color: var(--b2s-color-primary, #2563eb); cursor: pointer; font: inherit; }
  .fx__crumbs button.is-current { color: inherit; font-weight: 600; cursor: default; }
  .fx__crumbs i { font-size: 11px; color: var(--b2s-color-text-muted); }
  .fx__tabs { display: inline-flex; padding: 3px; border-radius: 999px; background: #E5E7EB; }
  .fx__tabs button { display: inline-flex; gap: 6px; align-items: center; height: 34px; padding: 0 16px; border: 0; border-radius: 999px; background: none; font: inherit; font-weight: 600; cursor: pointer; color: #374151; }
  .fx__tabs button.is-on { background: #0E1218; color: #fff; }
  .fx__tabs button span { padding: 0 7px; border-radius: 999px; background: #B5F23B; color: #0E1218; font-size: 11px; }
  .fx__scan { display: flex; flex-wrap: wrap; gap: 8px 20px; align-items: center; padding: 10px 14px; border-radius: 12px; background: #0E1218; color: #D1D5DB; font-size: 13px; }
  .fx__scan b { color: #fff; font-weight: 600; }
  .fx__scan b.is-warn { color: #FCD34D; }
  .fx__scan-name { display: inline-flex; gap: 8px; align-items: center; color: #fff; font-weight: 600; }
  .fx__dot { width: 8px; height: 8px; border-radius: 50%; background: #B5F23B; }
  .fx__dot.is-busy { background: #60A5FA; }
  .fx__scan-err { color: #FCA5A5; }
  .fx__kpis { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 10px; }
  .fx__kpis > div { display: grid; gap: 2px; padding: 12px 14px; border: 1px solid var(--b2s-color-border); border-radius: 12px; background: var(--b2s-color-surface, #fff); }
  .fx__kpis span, .fx__kpis small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .fx__kpis b { font-size: 20px; }
  .fx__kpis b.is-warn { color: #B45309; }
  .fx__kpis b.is-bad { color: #B91C1C; }
  .fx__body { display: grid; grid-template-columns: minmax(0, 1fr) 360px; gap: 14px; align-items: start; }
  .fx__main { display: grid; gap: 12px; min-width: 0; }
  .fx__filters { display: flex; flex-wrap: wrap; gap: 6px; }
  .fx__filters button { height: 30px; padding: 0 12px; border: 1px solid var(--b2s-color-border); border-radius: 999px; background: var(--b2s-color-surface, #fff); font: inherit; font-size: var(--b2s-fs-sm); cursor: pointer; }
  .fx__filters button.is-on { background: #0E1218; border-color: #0E1218; color: #fff; }
  .fx__split { display: grid; grid-template-columns: 240px minmax(0, 1fr); gap: 12px; align-items: start; }
  .fx__tree { position: sticky; top: 12px; display: grid; gap: 1px; max-height: 70vh; overflow: auto; padding: 8px; border: 1px solid var(--b2s-color-border); border-radius: 12px; background: var(--b2s-color-surface, #fff); }
  .fx__tree button { display: grid; grid-template-columns: 16px minmax(0, 1fr) auto; gap: 6px; align-items: center; padding: 6px 8px; border: 0; border-radius: 8px; background: none; font: inherit; font-size: var(--b2s-fs-sm); text-align: left; cursor: pointer; color: inherit; }
  .fx__tree button:hover { background: #F5F8FC; }
  .fx__tree button.is-current { font-weight: 600; background: #EEF2FF; }
  .fx__tree button.is-sel { background: #F5FBE6; }
  .fx__tree i { color: #E0A526; }
  .fx__tree span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .fx__tree small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); white-space: nowrap; }
  .fx__table { overflow-x: auto; border: 1px solid var(--b2s-color-border); border-radius: 12px; background: var(--b2s-color-surface, #fff); }
  .fx__table tr { cursor: default; }
  .fx__table tbody tr:hover td { background: #F5F8FC; }
  .fx__table tr.is-sel td { background: #F5FBE6; }
  .fx__name { display: flex; gap: 8px; align-items: center; min-width: 0; }
  .fx__name i.bi-folder-fill { color: #E0A526; }
  .fx__name code { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: var(--b2s-fs-xs); max-width: 360px; }
  .fx__num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
  td.is-warn { color: #B45309; }
  td.is-bad { color: #B91C1C; font-weight: 600; }
  .fx__age { display: block; width: 44px; height: 8px; border-radius: 4px; background: linear-gradient(90deg, #2563EB 0 var(--a), #F59E0B var(--a) var(--b), #B91C1C var(--b) 100%); }
  .fx__pill { padding: 2px 9px; border-radius: 999px; font-size: var(--b2s-fs-xs); font-weight: 600; white-space: nowrap; }
  .fx__pill.is-ok { background: #ECFDF5; color: #047857; }
  .fx__pill.is-warn { background: #FFF7ED; color: #9A3412; }
  .fx__pill.is-none { background: #F3F4F6; color: #6B7280; font-weight: 500; }
  .fx__empty { padding: 20px; text-align: center; color: var(--b2s-color-text-muted); }
  .fx__trend { display: flex; flex-wrap: wrap; gap: 14px; align-items: center; padding: 12px 14px; border: 1px solid var(--b2s-color-border); border-radius: 12px; background: var(--b2s-color-surface, #fff); }
  .fx__trend b { font-size: 24px; }
  .fx__trend em { margin-left: 8px; font-style: normal; font-size: var(--b2s-fs-sm); font-weight: 600; }
  .fx__trend em.is-up { color: #047857; }
  .fx__trend em.is-down { color: #B91C1C; }
  .fx__trend small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .fx__spark { display: flex; align-items: flex-end; gap: 3px; height: 36px; flex: 1 1 200px; }
  .fx__spark i { flex: 0 0 8px; border-radius: 2px; }
  .fx__pillars { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; }
  .fx__pillars > div { display: grid; gap: 4px; padding: 12px; border: 1px solid var(--b2s-color-border); border-radius: 12px; background: var(--b2s-color-surface, #fff); cursor: help; }
  .fx__pill-head { display: flex; justify-content: space-between; align-items: baseline; }
  .fx__pill-head strong { font-size: 20px; }
  .fx__pillars small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .fx__bar { height: 6px; border-radius: 3px; background: #EEF0F3; overflow: hidden; }
  .fx__bar span { display: block; height: 100%; }
  .fx__board { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; align-items: start; }
  .fx__col { display: grid; gap: 8px; padding: 10px; border-radius: 12px; background: #E9ECEF; }
  .fx__col header { display: flex; justify-content: space-between; font-size: var(--b2s-fs-sm); }
  .fx__col article { display: grid; gap: 6px; justify-items: start; padding: 10px; border-radius: 10px; background: #fff; }
  .fx__col article b { font-size: var(--b2s-fs-sm); line-height: 1.35; overflow-wrap: anywhere; }
  .fx__col article small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .fx__tags { display: flex; gap: 6px; flex-wrap: wrap; }
  .fx__tag { padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; }
  .fx__tag.is-dup { background: #FEE2E2; color: #991B1B; }
  .fx__tag.is-old { background: #FFEDD5; color: #9A3412; }
  .fx__tag.is-junk { background: #E5E7EB; color: #1F2937; }
  .fx__tag.is-inh { background: #FEF3C7; color: #92400E; }
  .fx__tag.is-acl { background: #E0E7FF; color: #3730A3; }
  .fx__gain { padding: 2px 8px; border-radius: 999px; background: #F3F4F6; font-size: 11px; }
  .fx__none { margin: 4px; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .fx__sheet { position: sticky; top: 12px; display: grid; grid-template-columns: minmax(0, 1fr); gap: 10px; min-width: 0; }
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
  .fx__time .is-c { background: #9CA3AF; }
  .fx__time .is-m { background: #F59E0B; }
  .fx__time .is-a { background: #3B82F6; }
  .fx__time small { color: var(--b2s-color-text-muted); }
  .fx__path code { font-size: var(--b2s-fs-xs); overflow-wrap: anywhere; }
  .fx__hint { margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .fx__acl { display: grid; gap: 6px; margin: 0; padding: 0; list-style: none; font-size: var(--b2s-fs-sm); }
  .fx__acl li { display: flex; justify-content: space-between; gap: 8px; align-items: center; }
  .fx__acl li span { display: grid; min-width: 0; }
  .fx__acl li b { font-weight: 500; overflow-wrap: anywhere; }
  .fx__acl li small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .fx__acl li.is-own b { color: #9A3412; }
  .fx__acl em { font-style: normal; font-size: var(--b2s-fs-xs); font-weight: 600; white-space: nowrap; }
  .fx__acl em.is-F { color: #991B1B; }
  .fx__acl em.is-W { color: #1D4ED8; }
  .fx__acl em.is-R { color: #047857; }
  .fx__acl em[class*='is-deny'] { color: #7C2D12; }
  .fx__chain { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; font-size: var(--b2s-fs-xs); }
  .fx__chain span:first-child { color: var(--b2s-color-text-muted); margin-right: 2px; }
  .fx__chain span + span { padding: 2px 8px; border-radius: 999px; background: #ECFDF5; color: #047857; }
  .fx__chain span.is-broken { background: #FFF7ED; color: #9A3412; }
  .fx__dup { display: grid; gap: 4px; }
  .fx__dup small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .fx__dup div { display: flex; justify-content: space-between; gap: 8px; padding: 5px 8px; border: 1px solid var(--b2s-color-border); border-radius: 8px; font-size: var(--b2s-fs-xs); }
  .fx__dup div code { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .fx__dup div b { white-space: nowrap; color: #991B1B; }
  .fx__dup div.is-keep { border-color: #86EFAC; background: #F0FDF4; }
  .fx__dup div.is-keep b { color: #047857; }
  .fx__score { position: relative; outline: none; }
  .fx__score-card { position: absolute; right: 0; top: calc(100% + 8px); z-index: 30; width: 300px; display: grid; gap: 8px; padding: 14px; border-radius: 14px;
    background: #0E1218; color: #F3F4F6; box-shadow: 0 18px 40px rgba(14, 18, 24, 0.3); opacity: 0; visibility: hidden; transform: translateY(-4px);
    transition: opacity 140ms ease, transform 140ms ease, visibility 140ms; pointer-events: none; }
  .fx__score:hover .fx__score-card, .fx__score:focus-within .fx__score-card, .fx__score:focus .fx__score-card { opacity: 1; visibility: visible; transform: none; }
  .fx__score-card strong { display: flex; justify-content: space-between; font-size: var(--b2s-fs-sm); }
  .fx__score-card em { font-style: normal; font-weight: 500; color: #C9D1DA; }
  .fx__score-row { display: grid; grid-template-columns: 96px minmax(0, 1fr) 28px; gap: 8px; align-items: center; font-size: 12px; color: #D1D5DB; }
  .fx__score-row > i { height: 6px; border-radius: 999px; background: #1F2630; overflow: hidden; }
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
</style>
