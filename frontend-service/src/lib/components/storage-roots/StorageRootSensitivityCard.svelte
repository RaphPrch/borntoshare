<script lang="ts">

  import { copyText } from '$lib/utils/clipboard';
  import { flip } from 'svelte/animate';
  import { dur, flashOn, MOTION, pop } from '$lib/utils/motion';
  import CountUp from '$lib/components/ui/CountUp.svelte';
  import ContextMenu, { menuPositionFor, type ContextMenuItem } from '$lib/components/ui/ContextMenu.svelte';
  import StorageRootRemediation from '$lib/components/storage-roots/StorageRootRemediation.svelte';
  import { onDestroy, untrack } from 'svelte';
  import { apiGetData, apiPostData } from '$lib/api/client';
  import { reportUiError } from '$lib/errors';
  import { toast } from '$lib/stores/toast';
  import { t } from '$lib/i18n';
  import { formatDateTime, timeAgo } from '$lib/utils/format';

  /**
   * Sensitivity of the folder: passwords, keys and password vaults the capsule runner found stored in it.
   * Only the path, the rule, the line and a masked excerpt are shown: the secret itself is never kept.
   */
  type Finding = { path: string; category: string; rule: string; line: number | null; excerpt: string | null; ignored?: boolean; ignored_reason?: string | null; ignored_by?: string | null; acl?: FileAcl | null };
  // Who can open the file: x = its own rights, e = « account|R/W/F|i » (i inherited, ! deny), broad = every user
  type FileAcl = { x: boolean; o: string; e: string[]; broad: boolean; by?: string[] };
  type Sensitivity = {
    status: 'running' | 'done' | 'failed';
    files_flagged: number;
    counts: Record<string, number>;
    findings: Finding[];
    files_listed?: number;
    files_read?: number;
    truncated?: boolean;
    target?: string;
    error?: string | null;
    method?: 'server' | 'smb';
    incremental?: { full: boolean | null; complete: boolean | null; pending: number | null };
    scanned_at?: string | null;
    files_open_to_all?: number;
    requested_at?: string | null;
  };
  interface Props {
    rootId?: number | null;
    sensitivity?: Sensitivity | null;
    isAdmin?: boolean;
  }

  let { rootId = null, sensitivity = null, isAdmin = false }: Props = $props();

  const CATEGORY = (): Record<string, { label: string; icon: string }> => ({
    password: { label: t('Passwords in clear'), icon: 'bi-key' },
    credentials_file: { label: t('Password files'), icon: 'bi-file-earmark-lock' },
    password_vault: { label: t('Password vaults'), icon: 'bi-safe' },
    private_key: { label: t('Private keys'), icon: 'bi-file-earmark-binary' },
    cloud_key: { label: t('API keys and tokens'), icon: 'bi-cloud-slash' },
    personal_data: { label: t('Personal data'), icon: 'bi-person-vcard' },
    bank_data: { label: t('Bank data'), icon: 'bi-credit-card' },
    backup_database: { label: t('Backups and databases'), icon: 'bi-database' },
    mailbox: { label: t('Mailboxes'), icon: 'bi-envelope-paper' },
    executable: { label: t('Programs and scripts'), icon: 'bi-filetype-exe' }
  });

  // svelte-ignore state_referenced_locally (an initial value, read once as before)
  let sensitivityScan: Sensitivity | null = $state(sensitivity);
  // svelte-ignore state_referenced_locally (an initial value, read once as before)
  let lastProp: Sensitivity | null = $state(sensitivity);
  let busy = $state(false);
  let showAll = $state(false);
  let timer: ReturnType<typeof setInterval> | null = null;
  let landed = $state(0);
  const PASSWORD_CATEGORIES = new Set(['password', 'credentials_file', 'password_vault']);
  function adopt(value: Sensitivity | null) {
    lastProp = value;
    sensitivityScan = value;
    showAll = false;
  }
  const RIGHT = (): Record<string, string> => ({ F: t('Full control'), W: t('Modify'), R: t('Read') });
  const aclRows = (acl: FileAcl) => acl.e.map((entry) => {
    const [who, right, inherited] = entry.split('|');
    return { who: who.replace(/^!/, ''), deny: who.startsWith('!'), right: RIGHT()[right] ?? right, inherited: inherited === 'i' };
  });
  let openAcl: string | null = $state(null);
  // Why every user can open them: in practice one folder gives read to everyone and all its files inherit it.
  // One line per cause (the accounts that open them, set on the folder or on the files), on their common folder.
  const RANK: Record<string, number> = { R: 1, W: 2, F: 3 };
  const parentOf = (path: string) => path.split('\\').slice(0, -1);
  const common = (a: string[], b: string[]) => {
    const out: string[] = [];
    for (let index = 0; index < a.length && a[index].toLowerCase() === b[index]?.toLowerCase(); index++) out.push(a[index]);
    return out;
  };
  let showIgnored = $state(false);
  let ignoringPath: string | null = $state(null);
  // « False positive » asks why, in a few words (an exception to a security finding is explained)
  let reasonFor: string | null = $state(null);
  let reasonText = $state('');
  // ---- right click on a file: false positive, who can open it, copy ----
  let menu: { path: string; hasAcl: boolean; at: { x: number; y: number } } | null = $state(null);
  function openMenu(file: { path: string; acl?: FileAcl | null }, event: MouseEvent) {
    event.preventDefault();
    menu = { path: file.path, hasAcl: Boolean(file.acl), at: menuPositionFor(event) };
  }
  function menuItems(current: NonNullable<typeof menu>): ContextMenuItem[] {
    return [
      { key: 'acl', label: openAcl === current.path ? t('Hide who can open it') : t('See who can open it'), icon: 'bi-people', disabled: !current.hasAcl, hint: !current.hasAcl ? t('Rights not read yet') : undefined },
      { key: 'copy', label: t('Copy the path'), icon: 'bi-clipboard' },
      { key: 'copy-folder', label: t('Copy the folder path'), icon: 'bi-folder2' },
      { key: 'fp', label: t('Mark as false positive…'), icon: 'bi-slash-circle', separated: true, disabled: !isAdmin || ignoringPath !== null, hint: !isAdmin ? t('Administrators only') : undefined }
    ];
  }
  function pickMenu(key: string) {
    const path = menu?.path;
    if (!path) return;
    const copy = (text: string) => void copyText(text).then((ok) => ok && toast.success(t('Path copied.')));
    if (key === 'acl') openAcl = openAcl === path ? null : path;
    else if (key === 'copy') copy(path);
    else if (key === 'copy-folder') copy(path.split('\\').slice(0, -1).join('\\'));
    else if (key === 'fp') { reasonFor = path; reasonText = ''; }
  }

  async function setIgnored(path: string, ignore: boolean, reason: string | null = null) {
    if (!rootId || ignoringPath) return;
    ignoringPath = path;
    try {
      sensitivityScan = await apiPostData<Sensitivity>(fetch, `/storage-roots/${rootId}/sensitivity/ignore`, { path, ignore, reason });
      reasonFor = null;
      reasonText = '';
      const name = path.split('\\').pop();
      toast.success(ignore ? t('« {name} » no longer counts.', { name }) : t('« {name} » counts again.', { name }), {
        action: { label: t('Undo'), run: async () => {
          sensitivityScan = await apiPostData<Sensitivity>(fetch, `/storage-roots/${rootId}/sensitivity/ignore`, { path, ignore: !ignore, reason: reason ?? previousReason(path) ?? 'annulation' });
        } }
      });
    } catch (error: unknown) {
      reportUiError(error, 'Unable to update the file.', 'storage-roots.sensitivity.ignore');
    } finally {
      ignoringPath = null;
    }
  }
  const previousReason = (path: string) => findings.find((item) => item.path === path)?.ignored_reason ?? null;

  const inside = (path: string) => (prefix && path.toLowerCase().startsWith(prefix.toLowerCase() + '\\') ? path.slice(prefix.length + 1) : path);

  async function refresh() {
    if (!rootId) return;
    try {
      const was = sensitivityScan?.status;
      sensitivityScan = (await apiGetData<Sensitivity | null>(fetch, `/storage-roots/${rootId}/sensitivity`)) ?? sensitivityScan;
      // The scan landed while the card was open: a short flash says so
      if (was === 'running' && sensitivityScan?.status === 'done') landed += 1;
    } catch {
      // the next tick tries again
    }
  }
  function startPolling() {
    if (!timer) timer = setInterval(refresh, 5000);
  }
  function stopPolling() {
    if (timer) clearInterval(timer);
    timer = null;
  }
  onDestroy(stopPolling);

  async function stopRun() {
    if (!rootId || busy) return;
    busy = true;
    try {
      await apiPostData(fetch, `/storage-roots/${rootId}/stop`, { kind: 'sensitivity' });
      await refresh();
    } catch (error: unknown) {
      reportUiError(error, 'Unable to stop the scan.', 'storage-roots.sensitivity.stop');
    } finally {
      busy = false;
    }
  }

  async function scan() {
    if (!rootId || busy) return;
    busy = true;
    try {
      const result = await apiPostData<{ queued: number[]; failed: Array<{ message: string }> }>(fetch, '/storage-roots/sensitivity-scan', { root_ids: [rootId] });
      if (result?.failed?.length) throw new Error(result.failed[0].message);
      sensitivityScan = { ...(sensitivityScan ?? { files_flagged: 0, counts: {}, findings: [] }), status: 'running', error: null };
    } catch (error: unknown) {
      reportUiError(error, 'Unable to start the scan.', 'storage-roots.sensitivity');
    } finally {
      busy = false;
    }
  }
  let passwordFiles = $derived(new Set((sensitivityScan?.findings ?? []).filter((item) => PASSWORD_CATEGORIES.has(item.category) && !item.ignored).map((item) => item.path.toLowerCase())).size);
  // A new folder or a reloaded overview: start again from what the page gives (polling keeps `state` fresh in between)
  $effect.pre(() => {
    if (sensitivity !== lastProp) untrack(() => adopt(sensitivity));
  });
  let running = $derived(sensitivityScan?.status === 'running');
  // Share of the folder already read, while a long scan goes on pass after pass
  let progress = $derived(sensitivityScan?.incremental?.pending && sensitivityScan?.files_listed
    ? Math.max(0, Math.min(99, Math.round((1 - Number(sensitivityScan.incremental.pending) / Number(sensitivityScan.files_listed)) * 100)))
    : null);
  $effect.pre(() => {
    const on = running; // only « running » starts it again (as the former « $: »)
    untrack(() => (on ? startPolling() : stopPolling()));
  });
  let findings = $derived(sensitivityScan?.findings ?? []);
  // One line per file: a file found by its name and by its content shows both
  let allFiles = $derived([...findings.reduce((map, item) => {
    const key = item.path.toLowerCase();
    if (!map.has(key)) map.set(key, { path: item.path, ignored: Boolean(item.ignored), items: [] as Finding[], acl: null as FileAcl | null });
    const file = map.get(key)!;
    file.items.push(item);
    file.acl = file.acl ?? item.acl ?? null;
    return map;
  }, new Map<string, { path: string; ignored: boolean; items: Finding[]; acl: FileAcl | null }>()).values()]);
  // A file marked as a false positive no longer counts: listed apart, folded. The files every user can open first.
  let files = $derived(allFiles.filter((file) => !file.ignored).sort((a, b) => Number(Boolean(b.acl?.broad)) - Number(Boolean(a.acl?.broad))));
  let openToAll = $derived(files.filter((file) => file.acl?.broad).length);
  let causes = $derived([...files.filter((file) => file.acl?.broad).reduce((map, file) => {
    const by = [...(file.acl?.by ?? [])].sort();
    const broadEntries = (file.acl?.e ?? []).filter((entry) => !entry.startsWith('!') && by.includes(entry.split('|')[0]));
    const inherited = broadEntries.length > 0 && broadEntries.every((entry) => entry.split('|')[2] === 'i');
    const key = `${by.join(',')}|${inherited}`;
    const cause = map.get(key) ?? { by, inherited, files: [] as string[], folder: null as string[] | null, right: 'R' };
    cause.files.push(file.path);
    cause.folder = cause.folder === null ? parentOf(file.path) : common(cause.folder, parentOf(file.path));
    for (const entry of broadEntries) { const right = entry.split('|')[1]; if ((RANK[right] ?? 0) > (RANK[cause.right] ?? 0)) cause.right = right; }
    map.set(key, cause);
    return map;
  }, new Map<string, { by: string[]; inherited: boolean; files: string[]; folder: string[] | null; right: string }>()).values()]
    .sort((a, b) => b.files.length - a.files.length));
  let ignoredFiles = $derived(allFiles.filter((file) => file.ignored));
  let shown = $derived(showAll ? files : files.slice(0, 6));
  let categories = $derived(Object.entries(sensitivityScan?.counts ?? {}).sort((a, b) => b[1] - a[1]));
  // The path inside the folder: \\server\share\folder is the same for every finding
  // \\server\share\folder: the findings are relative to the share, shown relative to the folder
  let prefix = $derived((sensitivityScan?.target ?? '').split('\\').filter(Boolean).slice(2).join('\\'));
</script>

<section class="sc" aria-label={t('Sensitivity')} use:flashOn={landed}>
  <header>
    <h2><i class="bi bi-shield-lock" aria-hidden="true"></i>{t('Sensitivity')}</h2>
    <small>
      {#if running}{t('Scan in progress…')}
        {#if isAdmin}· <button type="button" class="b2s-link-btn" disabled={busy} onclick={stopRun}>{t('Stop')}</button>{/if}
      {:else if sensitivityScan?.scanned_at}<span title={formatDateTime(sensitivityScan.scanned_at)}>{t('scanned {when}', { when: timeAgo(sensitivityScan.scanned_at) })}</span>
      {:else}{t('Never scanned')}{/if}
      {#if isAdmin && !running}
        · <button type="button" class="b2s-link-btn" disabled={busy} onclick={scan}>{sensitivityScan?.scanned_at ? t('Scan again') : t('Scan the folder')}</button>
      {/if}
    </small>
  </header>

  {#if running}
    <div class="sc__running" role="status"><span class="b2s-spinner b2s-spinner--sm" aria-hidden="true"></span>{t('The worker reads the folder: names of the files, then the content of the small text files.')}
      {#if sensitivityScan?.incremental?.pending}<b>{t('{count} file(s) still to read: the scan goes on by itself, pass after pass.', { count: sensitivityScan.incremental.pending })}</b>
        {#if progress != null}<span class="sc__progress" title={t('{percent} % read', { percent: progress })}><span style={`width:${progress}%`}></span></span><small>{progress} %</small>{/if}{/if}</div>
  {:else if sensitivityScan?.status === 'failed'}
    <p class="sc__error"><i class="bi bi-exclamation-octagon" aria-hidden="true"></i>{sensitivityScan.error ?? t('The scan failed')}</p>
  {:else if sensitivityScan?.status === 'done' && sensitivityScan.files_flagged === 0}
    <p class="sc__ok"><i class="bi bi-check2-circle" aria-hidden="true"></i>
      {t('Nothing sensitive found in {files} file(s), {read} read.', { files: sensitivityScan.files_listed ?? 0, read: sensitivityScan.files_read ?? 0 })}</p>
    {#if ignoredFiles.length}
      <div class="sc__ignored">
        <button type="button" class="b2s-link-btn" aria-expanded={showIgnored} onclick={() => (showIgnored = !showIgnored)}>
          {t('{count} file(s) marked as false positive', { count: ignoredFiles.length })}
        </button>
        {#if showIgnored}
          <ul>
            {#each ignoredFiles as file (file.path)}
              <li><span class="sc__ign"><code title={file.path} data-copy={file.path}>{inside(file.path)}</code>{#if file.items[0]?.ignored_reason}<small>{file.items[0].ignored_reason}{file.items[0].ignored_by ? ` · ${file.items[0].ignored_by}` : ''}</small>{/if}</span>
                {#if isAdmin}<button type="button" class="b2s-link-btn" disabled={ignoringPath !== null} onclick={() => setIgnored(file.path, false)}>{t('Count it again')}</button>{/if}
              </li>
            {/each}
          </ul>
        {/if}
      </div>
    {/if}
  {:else if sensitivityScan?.status === 'done'}
    <div class="sc__summary">
      <strong><CountUp value={sensitivityScan.files_flagged} duration={400} /> {t('sensitive file(s)')}</strong>
      {#if openToAll}<span class="sc__open"><i class="bi bi-people-fill" aria-hidden="true"></i>{t('{count} of them can be opened by every user', { count: openToAll })}</span>{/if}
      <div class="sc__cats">
        {#each categories as [key, count] (key)}
          <span class="sc__cat"><i class={`bi ${CATEGORY()[key]?.icon ?? 'bi-exclamation-triangle'}`} aria-hidden="true"></i>{CATEGORY()[key]?.label ?? key}<b>{count}</b></span>
        {/each}
      </div>
    </div>
    {#if causes.length}
      <div class="sc__causes">
        <b>{t('Why every user can open them')}</b>
        {#each causes as cause (cause.by.join(',') + cause.inherited)}
          <div class="sc__cause">
            <i class="bi bi-folder2-open" aria-hidden="true"></i>
            <span>
              <span><code>{cause.folder && cause.folder.length ? inside(cause.folder.join('\\')) : t('the share itself')}</code>
                {t('gives « {right} » to {who}', { right: RIGHT()[cause.right] ?? cause.right, who: cause.by.join(', ') })}</span>
              <small>{cause.inherited ? t('Inherited: set on this folder or above it, every file inside gets it.') : t('Set on the files themselves.')}
                · {t('{count} sensitive file(s)', { count: cause.files.length })}</small>
            </span>
          </div>
        {/each}
      </div>
    {/if}
    <ul class="sc__list">
      {#each shown as file (file.path)}
        <li animate:flip={{ duration: dur(MOTION.base) }} in:pop={{ y: 4 }} out:pop={{ duration: MOTION.fast, y: 0 }} oncontextmenu={(event) => openMenu(file, event)}>
          <i class={`bi ${CATEGORY()[file.items[0].category]?.icon ?? 'bi-file-earmark'}`} aria-hidden="true"></i>
          <div>
            <span class="sc__file"><code title={file.path} data-copy={file.path}>{#if file.acl?.broad}<i class="bi bi-people-fill sc__open-dot" title={t('Every user can open it')} aria-label={t('Every user can open it')}></i>{/if}{inside(file.path)}</code>
              {#if isAdmin && reasonFor !== file.path}<button type="button" class="b2s-link-btn sc__fp" disabled={ignoringPath !== null} onclick={() => { reasonFor = file.path; reasonText = ''; }}>{t('False positive')}</button>{/if}
            </span>
            {#if reasonFor === file.path}
              <span class="sc__reason">
                <input class="b2s-input" bind:value={reasonText} maxlength="300" placeholder={t('Why is it a false positive? (test file, sample…)')} aria-label={t('Reason')} />
                <button type="button" class="b2s-btn b2s-btn-primary b2s-btn-sm" disabled={reasonText.trim().length < 3 || ignoringPath !== null} onclick={() => setIgnored(file.path, true, reasonText.trim())}>{t('Confirm')}</button>
                <button type="button" class="b2s-link-btn" onclick={() => (reasonFor = null)}>{t('Cancel')}</button>
              </span>
            {/if}
            {#each file.items as item (item.category + (item.line ?? ''))}
              <small>{t(item.rule)}{#if item.line}{' · '}{t('line {line}', { line: item.line })}{/if}</small>
              {#if item.excerpt}<pre>{item.excerpt}</pre>{/if}
            {/each}
            {#if file.acl}
              <span class="sc__rights">
                {#if !file.acl.broad}<span class="sc__tag"><i class="bi bi-lock" aria-hidden="true"></i>{t('Limited access')}</span>{/if}
                {#if file.acl.x}<span class="sc__tag sc__tag--own" title={t('Rights of its own: they no longer follow the folder')}>{t('Own rights')}</span>{/if}
                <button type="button" class="b2s-link-btn" aria-expanded={openAcl === file.path} onclick={() => (openAcl = openAcl === file.path ? null : file.path)}>
                  {t('Who can open it ({count})', { count: file.acl.e.filter((entry) => !entry.startsWith('!')).length })}
                </button>
              </span>
              {#if openAcl === file.path}
                <ul class="sc__acl">
                  {#each aclRows(file.acl) as row (row.who + row.right + row.deny)}
                    <li class:is-deny={row.deny}><span>{row.deny ? t('Denied: {who}', { who: row.who }) : row.who}</span><em>{row.right}{row.inherited ? ` · ${t('inherited')}` : ''}</em></li>
                  {/each}
                  {#if file.acl.o}<li class="sc__owner"><span>{t('Owner')}</span><em>{file.acl.o}</em></li>{/if}
                </ul>
              {/if}
            {/if}
          </div>
        </li>
      {/each}
    </ul>
    {#if files.length > shown.length}
      <button type="button" class="b2s-link-btn" onclick={() => (showAll = true)}>{t('Show the {count} others', { count: files.length - shown.length })}</button>
    {/if}
    {#if ignoredFiles.length}
      <div class="sc__ignored">
        <button type="button" class="b2s-link-btn" aria-expanded={showIgnored} onclick={() => (showIgnored = !showIgnored)}>
          {t('{count} file(s) marked as false positive', { count: ignoredFiles.length })}
        </button>
        {#if showIgnored}
          <ul>
            {#each ignoredFiles as file (file.path)}
              <li><span class="sc__ign"><code title={file.path} data-copy={file.path}>{inside(file.path)}</code>{#if file.items[0]?.ignored_reason}<small>{file.items[0].ignored_reason}{file.items[0].ignored_by ? ` · ${file.items[0].ignored_by}` : ''}</small>{/if}</span>
                {#if isAdmin}<button type="button" class="b2s-link-btn" disabled={ignoringPath !== null} onclick={() => setIgnored(file.path, false)}>{t('Count it again')}</button>{/if}
              </li>
            {/each}
          </ul>
        {/if}
      </div>
    {/if}
    <p class="sc__note">
      {t('Move the secrets to a vault, delete the copies, then scan again.')}
      {#if sensitivityScan.truncated}{t('Large folder: only part of the files was read.')}{/if}
    </p>
  {:else}
    <p class="sc__empty">{t('Looks for passwords, keys and password vaults stored in the folder. Read only; the secrets themselves are never kept.')}</p>
  {/if}
  {#if !running && sensitivityScan?.status === 'done' && sensitivityScan.incremental}
    <p class="sc__note">
      {sensitivityScan.incremental.full ? t('Full scan') : t('Incremental scan: only the files changed since the last one were read')}
      · {t('{count} read', { count: sensitivityScan.files_read ?? 0 })}{sensitivityScan.method === 'server' ? ` · ${t('listed on the server')}` : ''}
      {#if sensitivityScan.incremental.pending}· <b>{t('{count} changed file(s) left: read at the next scan', { count: sensitivityScan.incremental.pending })}</b>{/if}
    </p>
  {/if}
  {#if !running && sensitivityScan?.status === 'done'}
    <StorageRootRemediation {rootId} {isAdmin} {passwordFiles} refreshKey={sensitivityScan?.scanned_at} />
  {/if}
</section>

<ContextMenu open={Boolean(menu)} title={menu ? (menu.path.split('\\').pop() ?? menu.path) : ''} subtitle={menu ? inside(menu.path) : ''}
  items={menu ? menuItems(menu) : []} at={menu?.at ?? { x: 0, y: 0 }} onClose={() => (menu = null)} onPick={pickMenu} />

<style>
  .sc { display: flex; flex-direction: column; gap: 10px; padding: 16px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .sc header { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
  .sc h2 { display: flex; align-items: center; gap: 8px; margin: 0; font-size: var(--b2s-fs-md); font-weight: 600; }
  .sc header small, .sc__empty, .sc__note { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .sc p { margin: 0; }
  .sc__ok, .sc__error { display: flex; gap: 8px; align-items: center; font-size: var(--b2s-fs-sm); }
  .sc__ok i { color: var(--b2s-color-success-strong, #1a7f37); }
  .sc__error { color: var(--b2s-color-danger-strong, #b42318); }
  .sc__progress { flex: 1 1 120px; height: 6px; border-radius: 3px; background: var(--b2s-color-border); overflow: hidden; }
  .sc__progress span { display: block; height: 100%; background: var(--b2s-color-primary, #2563eb); }
  .sc__running { display: flex; flex-wrap: wrap; gap: 6px 10px; align-items: center; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .sc__summary { display: flex; flex-direction: column; gap: 8px; padding: 12px; border-radius: var(--b2s-radius-md); background: var(--b2s-color-danger-soft, #fdecea); }
  .sc__summary strong { color: var(--b2s-color-danger-strong, #b42318); }
  .sc__cats { display: flex; flex-wrap: wrap; gap: 6px; }
  .sc__cat { display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-surface); font-size: var(--b2s-fs-xs); }
  .sc__cat b { font-variant-numeric: tabular-nums; }
  .sc__list { display: flex; flex-direction: column; gap: 2px; margin: 0; padding: 0; list-style: none; }
  .sc__list li { display: grid; grid-template-columns: 18px minmax(0, 1fr); gap: 10px; padding: 8px 4px; border-top: 1px solid var(--b2s-color-border); }
  .sc__list li > i { margin-top: 2px; color: var(--b2s-color-text-muted); }
  .sc__list div { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .sc__list code { color: var(--b2s-color-text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: var(--b2s-font-mono); font-size: var(--b2s-fs-xs); }
  .sc__list small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .sc__list pre { margin: 2px 0 0; padding: 4px 8px; overflow: hidden; text-overflow: ellipsis; white-space: pre; border-radius: var(--b2s-radius-sm, 6px); background: var(--b2s-color-surface-soft, #f6f7f9); font-family: var(--b2s-font-mono); font-size: var(--b2s-font-micro); }
  .sc__file { display: flex; align-items: center; justify-content: space-between; gap: 10px; min-width: 0; }
  .sc__fp { flex: none; font-size: var(--b2s-fs-xs); }
  .sc__ignored { display: flex; flex-direction: column; gap: 6px; padding-top: 8px; border-top: 1px dashed var(--b2s-color-border); font-size: var(--b2s-fs-xs); }
  .sc__ignored .b2s-link-btn { align-self: flex-start; font-size: var(--b2s-fs-xs); }
  .sc__ignored ul { display: flex; flex-direction: column; gap: 4px; margin: 0; padding: 0; list-style: none; }
  .sc__ignored li { display: flex; justify-content: space-between; gap: 10px; color: var(--b2s-color-text-muted); }
  .sc__ignored code { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: var(--b2s-font-mono); text-decoration: line-through; }
  .sc__reason { display: flex; gap: 6px; align-items: center; margin: 4px 0; }
  .sc__reason input { flex: 1; min-width: 0; height: 32px; font-size: var(--b2s-fs-xs); }
  .sc__ign { display: flex; flex-direction: column; min-width: 0; }
  .sc__ign small { color: var(--b2s-color-text-muted); font-size: var(--b2s-font-micro); text-decoration: none; }
  .sc__open { display: inline-flex; align-items: center; gap: 6px; color: var(--b2s-color-danger-strong, #b42318); font-size: var(--b2s-fs-sm); font-weight: 600; }
  .sc__rights { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-top: 4px; }
  .sc__rights .b2s-link-btn { font-size: var(--b2s-fs-xs); }
  .sc__tag { display: inline-flex; align-items: center; gap: 4px; padding: 1px 8px; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-surface-soft, #f6f7f9); color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .sc__tag--bad { background: var(--b2s-color-danger-soft, #fdecea); color: var(--b2s-color-danger-strong, #b42318); font-weight: 600; }
  .sc__tag--own { background: #FEF3C7; color: #92400E; }
  .sc__acl { display: grid; gap: 2px; margin: 4px 0 0; padding: 6px 8px; list-style: none; border-radius: var(--b2s-radius-sm, 6px); background: var(--b2s-color-surface-soft, #f6f7f9); font-size: var(--b2s-fs-xs); }
  .sc__acl li { display: flex; justify-content: space-between; gap: 10px; }
  .sc__acl li span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .sc__acl em { flex: none; font-style: normal; color: var(--b2s-color-text-muted); }
  .sc__acl li.is-deny span { color: var(--b2s-color-danger-strong, #b42318); }
  .sc__acl li.sc__owner { margin-top: 2px; padding-top: 4px; border-top: 1px dashed var(--b2s-color-border); color: var(--b2s-color-text-muted); }
  .sc__causes { display: grid; gap: 6px; padding: 10px 12px; border: 1px solid var(--b2s-color-danger-soft, #fdecea); border-radius: var(--b2s-radius-md); font-size: var(--b2s-fs-sm); }
  .sc__cause { display: grid; grid-template-columns: 18px minmax(0, 1fr); gap: 8px; }
  .sc__cause > i { margin-top: 2px; color: var(--b2s-color-danger-strong, #b42318); }
  .sc__cause > span { display: grid; gap: 2px; min-width: 0; }
  .sc__cause code { font-family: var(--b2s-font-mono); font-size: var(--b2s-fs-xs); }
  .sc__cause small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .sc__open-dot { margin-right: 6px; color: var(--b2s-color-danger-strong, #b42318); font-size: 11px; }
</style>
