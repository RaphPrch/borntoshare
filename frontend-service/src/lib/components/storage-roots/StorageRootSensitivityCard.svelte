<script lang="ts">
  import { flip } from 'svelte/animate';
  import { dur, flashOn, MOTION, pop } from '$lib/utils/motion';
  import CountUp from '$lib/components/ui/CountUp.svelte';
  import StorageRootRemediation from '$lib/components/storage-roots/StorageRootRemediation.svelte';
  import { onDestroy } from 'svelte';
  import { apiGetData, apiPostData } from '$lib/api/client';
  import { reportUiError } from '$lib/errors';
  import { toast } from '$lib/stores/toast';
  import { t } from '$lib/i18n';
  import { formatDateTime, timeAgo } from '$lib/utils/format';

  /**
   * Sensitivity of the folder: passwords, keys and password vaults the capsule runner found stored in it.
   * Only the path, the rule, the line and a masked excerpt are shown: the secret itself is never kept.
   */
  type Finding = { path: string; category: string; rule: string; line: number | null; excerpt: string | null; ignored?: boolean; ignored_reason?: string | null; ignored_by?: string | null };
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
    scanned_at?: string | null;
    requested_at?: string | null;
  };
  export let rootId: number | null = null;
  export let sensitivity: Sensitivity | null = null;
  export let isAdmin = false;

  const CATEGORY = (): Record<string, { label: string; icon: string }> => ({
    password: { label: t('Passwords in clear'), icon: 'bi-key' },
    credentials_file: { label: t('Password files'), icon: 'bi-file-earmark-lock' },
    password_vault: { label: t('Password vaults'), icon: 'bi-safe' },
    private_key: { label: t('Private keys'), icon: 'bi-file-earmark-binary' },
    cloud_key: { label: t('API keys and tokens'), icon: 'bi-cloud-slash' }
  });

  let state: Sensitivity | null = sensitivity;
  let lastProp: Sensitivity | null = sensitivity;
  let busy = false;
  let showAll = false;
  let timer: ReturnType<typeof setInterval> | null = null;
  let landed = 0;
  const PASSWORD_CATEGORIES = new Set(['password', 'credentials_file', 'password_vault']);
  $: passwordFiles = new Set((state?.findings ?? []).filter((item) => PASSWORD_CATEGORIES.has(item.category) && !item.ignored).map((item) => item.path.toLowerCase())).size;
  // A new folder or a reloaded overview: start again from what the page gives (polling keeps `state` fresh in between)
  $: if (sensitivity !== lastProp) adopt(sensitivity);
  function adopt(value: Sensitivity | null) {
    lastProp = value;
    state = value;
    showAll = false;
  }
  $: running = state?.status === 'running';
  $: running ? startPolling() : stopPolling();
  $: findings = state?.findings ?? [];
  // One line per file: a file found by its name and by its content shows both
  $: allFiles = [...findings.reduce((map, item) => {
    const key = item.path.toLowerCase();
    if (!map.has(key)) map.set(key, { path: item.path, ignored: Boolean(item.ignored), items: [] as Finding[] });
    map.get(key)!.items.push(item);
    return map;
  }, new Map<string, { path: string; ignored: boolean; items: Finding[] }>()).values()];
  // A file marked as a false positive no longer counts: listed apart, folded
  $: files = allFiles.filter((file) => !file.ignored);
  $: ignoredFiles = allFiles.filter((file) => file.ignored);
  let showIgnored = false;
  let ignoringPath: string | null = null;
  // « False positive » asks why, in a few words (an exception to a security finding is explained)
  let reasonFor: string | null = null;
  let reasonText = '';
  async function setIgnored(path: string, ignore: boolean, reason: string | null = null) {
    if (!rootId || ignoringPath) return;
    ignoringPath = path;
    try {
      state = await apiPostData<Sensitivity>(fetch, `/storage-roots/${rootId}/sensitivity/ignore`, { path, ignore, reason });
      reasonFor = null;
      reasonText = '';
      const name = path.split('\\').pop();
      toast.success(ignore ? t('« {name} » no longer counts.', { name }) : t('« {name} » counts again.', { name }), {
        action: { label: t('Undo'), run: async () => {
          state = await apiPostData<Sensitivity>(fetch, `/storage-roots/${rootId}/sensitivity/ignore`, { path, ignore: !ignore, reason: reason ?? previousReason(path) ?? 'annulation' });
        } }
      });
    } catch (error: unknown) {
      reportUiError(error, 'Unable to update the file.', 'storage-roots.sensitivity.ignore');
    } finally {
      ignoringPath = null;
    }
  }
  const previousReason = (path: string) => findings.find((item) => item.path === path)?.ignored_reason ?? null;

  $: shown = showAll ? files : files.slice(0, 6);
  $: categories = Object.entries(state?.counts ?? {}).sort((a, b) => b[1] - a[1]);
  // The path inside the folder: \\server\share\folder is the same for every finding
  // \\server\share\folder: the findings are relative to the share, shown relative to the folder
  $: prefix = (state?.target ?? '').split('\\').filter(Boolean).slice(2).join('\\');
  const inside = (path: string) => (prefix && path.toLowerCase().startsWith(prefix.toLowerCase() + '\\') ? path.slice(prefix.length + 1) : path);

  async function refresh() {
    if (!rootId) return;
    try {
      const was = state?.status;
      state = (await apiGetData<Sensitivity | null>(fetch, `/storage-roots/${rootId}/sensitivity`)) ?? state;
      // The scan landed while the card was open: a short flash says so
      if (was === 'running' && state?.status === 'done') landed += 1;
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

  async function scan() {
    if (!rootId || busy) return;
    busy = true;
    try {
      const result = await apiPostData<{ queued: number[]; failed: Array<{ message: string }> }>(fetch, '/storage-roots/sensitivity-scan', { root_ids: [rootId] });
      if (result?.failed?.length) throw new Error(result.failed[0].message);
      state = { ...(state ?? { files_flagged: 0, counts: {}, findings: [] }), status: 'running', error: null };
    } catch (error: unknown) {
      reportUiError(error, 'Unable to start the scan.', 'storage-roots.sensitivity');
    } finally {
      busy = false;
    }
  }
</script>

<section class="sc" aria-label={t('Sensitivity')} use:flashOn={landed}>
  <header>
    <h2><i class="bi bi-shield-lock" aria-hidden="true"></i>{t('Sensitivity')}</h2>
    <small>
      {#if running}{t('Scan in progress…')}
      {:else if state?.scanned_at}<span title={formatDateTime(state.scanned_at)}>{t('scanned {when}', { when: timeAgo(state.scanned_at) })}</span>
      {:else}{t('Never scanned')}{/if}
      {#if isAdmin && !running}
        · <button type="button" class="b2s-link-btn" disabled={busy} on:click={scan}>{state?.scanned_at ? t('Scan again') : t('Scan the folder')}</button>
      {/if}
    </small>
  </header>

  {#if running}
    <div class="sc__running" role="status"><span class="b2s-spinner b2s-spinner--sm" aria-hidden="true"></span>{t('The worker reads the folder: names of the files, then the content of the small text files.')}</div>
  {:else if state?.status === 'failed'}
    <p class="sc__error"><i class="bi bi-exclamation-octagon" aria-hidden="true"></i>{state.error ?? t('The scan failed')}</p>
  {:else if state?.status === 'done' && state.files_flagged === 0}
    <p class="sc__ok"><i class="bi bi-check2-circle" aria-hidden="true"></i>
      {t('Nothing sensitive found in {files} file(s), {read} read.', { files: state.files_listed ?? 0, read: state.files_read ?? 0 })}</p>
    {#if ignoredFiles.length}
      <div class="sc__ignored">
        <button type="button" class="b2s-link-btn" aria-expanded={showIgnored} on:click={() => (showIgnored = !showIgnored)}>
          {t('{count} file(s) marked as false positive', { count: ignoredFiles.length })}
        </button>
        {#if showIgnored}
          <ul>
            {#each ignoredFiles as file (file.path)}
              <li><span class="sc__ign"><code title={file.path}>{inside(file.path)}</code>{#if file.items[0]?.ignored_reason}<small>{file.items[0].ignored_reason}{file.items[0].ignored_by ? ` · ${file.items[0].ignored_by}` : ''}</small>{/if}</span>
                {#if isAdmin}<button type="button" class="b2s-link-btn" disabled={ignoringPath !== null} on:click={() => setIgnored(file.path, false)}>{t('Count it again')}</button>{/if}
              </li>
            {/each}
          </ul>
        {/if}
      </div>
    {/if}
  {:else if state?.status === 'done'}
    <div class="sc__summary">
      <strong><CountUp value={state.files_flagged} duration={400} /> {t('sensitive file(s)')}</strong>
      <div class="sc__cats">
        {#each categories as [key, count] (key)}
          <span class="sc__cat"><i class={`bi ${CATEGORY()[key]?.icon ?? 'bi-exclamation-triangle'}`} aria-hidden="true"></i>{CATEGORY()[key]?.label ?? key}<b>{count}</b></span>
        {/each}
      </div>
    </div>
    <ul class="sc__list">
      {#each shown as file (file.path)}
        <li animate:flip={{ duration: dur(MOTION.base) }} in:pop={{ y: 4 }} out:pop={{ duration: MOTION.fast, y: 0 }}>
          <i class={`bi ${CATEGORY()[file.items[0].category]?.icon ?? 'bi-file-earmark'}`} aria-hidden="true"></i>
          <div>
            <span class="sc__file"><code title={file.path}>{inside(file.path)}</code>
              {#if isAdmin && reasonFor !== file.path}<button type="button" class="b2s-link-btn sc__fp" disabled={ignoringPath !== null} on:click={() => { reasonFor = file.path; reasonText = ''; }}>{t('False positive')}</button>{/if}
            </span>
            {#if reasonFor === file.path}
              <span class="sc__reason">
                <input class="b2s-input" bind:value={reasonText} maxlength="300" placeholder={t('Why is it a false positive? (test file, sample…)')} aria-label={t('Reason')} />
                <button type="button" class="b2s-btn b2s-btn-primary b2s-btn-sm" disabled={reasonText.trim().length < 3 || ignoringPath !== null} on:click={() => setIgnored(file.path, true, reasonText.trim())}>{t('Confirm')}</button>
                <button type="button" class="b2s-link-btn" on:click={() => (reasonFor = null)}>{t('Cancel')}</button>
              </span>
            {/if}
            {#each file.items as item (item.category + (item.line ?? ''))}
              <small>{t(item.rule)}{#if item.line}{' · '}{t('line {line}', { line: item.line })}{/if}</small>
              {#if item.excerpt}<pre>{item.excerpt}</pre>{/if}
            {/each}
          </div>
        </li>
      {/each}
    </ul>
    {#if files.length > shown.length}
      <button type="button" class="b2s-link-btn" on:click={() => (showAll = true)}>{t('Show the {count} others', { count: files.length - shown.length })}</button>
    {/if}
    {#if ignoredFiles.length}
      <div class="sc__ignored">
        <button type="button" class="b2s-link-btn" aria-expanded={showIgnored} on:click={() => (showIgnored = !showIgnored)}>
          {t('{count} file(s) marked as false positive', { count: ignoredFiles.length })}
        </button>
        {#if showIgnored}
          <ul>
            {#each ignoredFiles as file (file.path)}
              <li><span class="sc__ign"><code title={file.path}>{inside(file.path)}</code>{#if file.items[0]?.ignored_reason}<small>{file.items[0].ignored_reason}{file.items[0].ignored_by ? ` · ${file.items[0].ignored_by}` : ''}</small>{/if}</span>
                {#if isAdmin}<button type="button" class="b2s-link-btn" disabled={ignoringPath !== null} on:click={() => setIgnored(file.path, false)}>{t('Count it again')}</button>{/if}
              </li>
            {/each}
          </ul>
        {/if}
      </div>
    {/if}
    <p class="sc__note">
      {t('Move the secrets to a vault, delete the copies, then scan again.')}
      {#if state.truncated}{t('Large folder: only part of the files was read.')}{/if}
    </p>
  {:else}
    <p class="sc__empty">{t('Looks for passwords, keys and password vaults stored in the folder. Read only; the secrets themselves are never kept.')}</p>
  {/if}
  {#if !running && state?.status === 'done'}
    <StorageRootRemediation {rootId} {isAdmin} {passwordFiles} refreshKey={state?.scanned_at} />
  {/if}
</section>

<style>
  .sc { display: flex; flex-direction: column; gap: 10px; padding: 16px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .sc header { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
  .sc h2 { display: flex; align-items: center; gap: 8px; margin: 0; font-size: var(--b2s-fs-md); font-weight: 600; }
  .sc header small, .sc__empty, .sc__note { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .sc p { margin: 0; }
  .sc__ok, .sc__error { display: flex; gap: 8px; align-items: center; font-size: var(--b2s-fs-sm); }
  .sc__ok i { color: var(--b2s-color-success-strong, #1a7f37); }
  .sc__error { color: var(--b2s-color-danger-strong, #b42318); }
  .sc__running { display: flex; gap: 10px; align-items: center; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
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
</style>
