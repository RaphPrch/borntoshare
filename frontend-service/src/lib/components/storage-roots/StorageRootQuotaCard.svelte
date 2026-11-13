<script lang="ts">
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import { flip } from 'svelte/animate';
  import { dur, flashOn, MOTION, pop } from '$lib/utils/motion';
  import CountUp from '$lib/components/ui/CountUp.svelte';
  import { onDestroy } from 'svelte';
  import { page } from '$app/stores';
  import {
    decideQuotaRequest,
    getFolderQuota,
    refreshFolderQuota,
    removeFolderQuota,
    requestMoreQuota,
    setFolderQuota,
    type FolderQuotaState
  } from '$lib/api/quotas';
  import RelativeTime from '$lib/components/ui/RelativeTime.svelte';
  import { reportUiError } from '$lib/errors';
  import { t } from '$lib/i18n';
  import { toast } from '$lib/stores/toast';
  import { formatBytes } from '$lib/utils/format';

  /**
   * Quota of the folder, held by its Windows file server (FSRM): how full it is, and how to get more room.
   * Administrators set, change or remove it; guardians ask for more with a reason; an administrator decides.
   * The server stays the truth: after every change the worker reads the quota back from it.
   */
  export let rootId: number | null = null;
  export let isAdmin = false;
  /** DFS folders have no quota of their own: it lives on their target folder */
  export let isDfs = false;

  const UNITS: Array<[string, number]> = [['Mo', 1024 ** 2], ['Go', 1024 ** 3], ['To', 1024 ** 4]];
  const WARN = [75, 80, 85, 90, 95];

  let state: FolderQuotaState | null = null;
  let loadedFor: number | null = null;
  let loading = false;
  let busy = false;
  let timer: ReturnType<typeof setInterval> | null = null;
  let polls = 0;
  // Grows each time a job of the server lands while the card is open (flash)
  let landed = 0;
  // Forms: the quota (administrators), more room (guardians), refusal note (administrators)
  let mode: 'none' | 'edit' | 'ask' | 'reject' | 'remove' = 'none';
  let amount = 10;
  let unit = 'Go';
  let soft = false;
  let warn = 85;
  let reason = '';
  let note = '';

  $: if (rootId && rootId !== loadedFor && !isDfs) load();
  $: quota = state?.quota ?? null;
  $: pending = state?.pending_request ?? null;
  $: decided = (state?.requests ?? []).filter((row) => row.status !== 'pending').slice(0, 3);
  $: has = !!quota && quota.status !== 'none' && quota.limit_bytes != null && !(quota.status === 'failed' && !quota.read_at);
  $: working = quota?.status === 'pending' || quota?.pending_operation === 'read';
  $: working ? startPolling() : stopPolling();
  $: percent = quota?.used_percent ?? null;
  $: tone = percent == null ? 'neutral' : percent >= 100 ? 'danger' : percent >= (quota?.warn_percent ?? 85) ? 'warning' : 'ok';
  $: myId = Number($page.data?.user?.id ?? 0);
  $: bytes = Math.round(Number(amount || 0) * (UNITS.find(([name]) => name === unit)?.[1] ?? 1024 ** 3));

  async function load() {
    loadedFor = rootId;
    mode = 'none';
    loading = true;
    try {
      state = await getFolderQuota(fetch, Number(rootId));
    } catch {
      state = null;
    } finally {
      loading = false;
    }
  }
  function startPolling() {
    if (timer) return;
    polls = 0;
    timer = setInterval(async () => {
      polls += 1;
      if (!rootId || polls > 60) return stopPolling();
      try {
        const next = await getFolderQuota(fetch, rootId);
        const before = state?.quota?.status;
        const wasWorking = state?.quota?.status === 'pending' || state?.quota?.pending_operation === 'read';
        state = next;
        if (wasWorking && next.quota?.status !== 'pending' && !next.quota?.pending_operation && next.quota?.status !== 'failed') landed += 1;
        if (before === 'pending' && next.quota?.status === 'failed') toast.error(t('The server refused the quota: {message}', { message: next.quota.error_message ?? '' }));
      } catch {
        /* the next tick tries again */
      }
    }, 3000);
  }
  function stopPolling() {
    if (timer) clearInterval(timer);
    timer = null;
  }
  onDestroy(stopPolling);

  /** 53 687 091 200 → 50 Go in the form */
  function fill(limit: number | null) {
    const value = Number(limit || 10 * 1024 ** 3);
    const [name, factor] = [...UNITS].reverse().find(([, f]) => value >= f && value % (f / 1024) === 0) ?? ['Go', 1024 ** 3];
    unit = name;
    amount = Math.round((value / factor) * 100) / 100;
  }
  function openEdit() {
    fill(quota?.limit_bytes ?? null);
    soft = quota?.soft ?? false;
    warn = quota?.warn_percent ?? 85;
    mode = 'edit';
  }
  function openAsk() {
    fill(Math.ceil(((quota?.limit_bytes ?? 0) * 1.5) / 1024 ** 3) * 1024 ** 3);
    reason = '';
    mode = 'ask';
  }

  async function run(work: () => Promise<FolderQuotaState>, done: string, context: string) {
    if (busy || !rootId) return;
    busy = true;
    try {
      state = await work();
      mode = 'none';
      if (done) toast.success(done);
    } catch (error: unknown) {
      reportUiError(error, 'Unable to change the quota.', context);
    } finally {
      busy = false;
    }
  }
  const save = () => run(() => setFolderQuota(fetch, Number(rootId), { limit_bytes: bytes, soft, warn_percent: warn }),
    t('Quota sent to the server.'), 'quota.set');
  const remove = () => run(() => removeFolderQuota(fetch, Number(rootId)), t('Quota removal sent to the server.'), 'quota.remove');
  const refresh = () => run(() => refreshFolderQuota(fetch, Number(rootId)), '', 'quota.refresh');
  const ask = () => run(() => requestMoreQuota(fetch, Number(rootId), { requested_limit_bytes: bytes, reason: reason.trim() }),
    t('Request sent: an administrator decides.'), 'quota.request');
  const approve = () => pending && run(() => decideQuotaRequest(fetch, pending!.id, { decision: 'approve' }),
    t('Request approved: the new quota goes to the server.'), 'quota.approve');
  const reject = () => pending && run(() => decideQuotaRequest(fetch, pending!.id, { decision: 'reject', note: note.trim() }),
    t('Request refused.'), 'quota.reject');
  const cancel = () => pending && run(() => decideQuotaRequest(fetch, pending!.id, { decision: 'cancel' }), t('Request cancelled.'), 'quota.cancel');
</script>

{#if rootId}
  <section class="qc" aria-label={t('Quota')} use:flashOn={landed}>
    <header>
      <h2><i class="bi bi-speedometer2" aria-hidden="true"></i>{t('Quota')}</h2>
      {#if has && !isDfs}
        <small>{t('read')} <RelativeTime value={quota?.read_at} /></small>
      {/if}
    </header>

    {#if isDfs}
      <p class="qc__muted">{t('A DFS folder has no quota of its own: it is set on its target folder, on the file server.')}</p>
    {:else if loading && !state}
      <LoadingState skeleton="rows" rows={2}>{t('Loading…')}</LoadingState>
    {:else}
      {#if working}
        <p class="qc__running"><span class="b2s-spinner b2s-spinner--sm" aria-hidden="true"></span>
          {quota?.pending_operation === 'read' ? t('Reading the quota on the server…') : quota?.pending_operation === 'remove' ? t('Removing the quota on the server…') : t('Applying the quota on the server…')}</p>
      {/if}

      {#if quota?.status === 'failed'}
        <p class="qc__error" role="alert"><i class="bi bi-exclamation-octagon" aria-hidden="true"></i>
          <span>{t('The server refused or could not be reached')}: {quota.error_message || quota.error_code}</span></p>
      {/if}

      {#if has && quota}
        <div class="qc__gauge" data-tone={tone}>
          <div class="qc__figures">
            <strong><CountUp value={quota.used_bytes} format={(n) => formatBytes(Math.round(n))} /></strong>
            <span>{t('of {limit}', { limit: formatBytes(quota.limit_bytes) })}</span>
            {#if percent != null}<b class="qc__pct"><CountUp value={percent} format={(n) => n.toLocaleString('fr-FR', { maximumFractionDigits: 1 })} /> %</b>{/if}
          </div>
          <div class="qc__bar" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.min(100, percent ?? 0)}
            aria-label={t('Quota used')}>
            <span class="b2s-grow" style={`width:${Math.min(100, percent ?? 0)}%`}></span>
            <i class="qc__mark" style={`left:${quota.warn_percent}%`} title={t('Warning at {percent} %', { percent: quota.warn_percent })}></i>
          </div>
          <div class="qc__chips">
            <span class="qc__chip">{quota.soft ? t('Soft quota: warns, never blocks') : t('Hard quota: blocks writes beyond it')}</span>
            <span class="qc__chip">{t('Warning at {percent} %', { percent: quota.warn_percent })}</span>
            {#if quota.peak_bytes}<span class="qc__chip">{t('Peak {size}', { size: formatBytes(quota.peak_bytes) })}</span>{/if}
          </div>
          {#if quota.local_path}<code class="qc__path" title={t('Path on the server')} data-copy={quota.local_path}>{quota.local_path}</code>{/if}
        </div>
      {:else if !working && quota?.status !== 'failed'}
        <p class="qc__muted">{t('No quota on the server: the folder can grow until the disk is full.')}</p>
      {/if}

      {#if pending}
        <div class="qc__request">
          <p><b>{pending.requested_by || t('Someone')}</b> {t('asks for {size}', { size: formatBytes(pending.requested_limit_bytes) })}
            <small>({t('now {size}', { size: formatBytes(pending.current_limit_bytes) })} · <RelativeTime value={pending.created_at} />)</small></p>
          <blockquote>{pending.reason}</blockquote>
          {#if mode === 'reject'}
            <label class="qc__field">{t('Why is it refused? The person who asked reads it.')}
              <input class="b2s-input" bind:value={note} maxlength="500" placeholder={t('e.g. Archive the 2019 projects first')} /></label>
            <div class="qc__btns">
              <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" on:click={() => (mode = 'none')}>{t('Back')}</button>
              <button type="button" class="b2s-btn b2s-btn-danger b2s-btn-sm" disabled={busy || note.trim().length < 3} on:click={reject}>{t('Refuse')}</button>
            </div>
          {:else}
            <div class="qc__btns">
              {#if Number(pending.requested_by_identity_id) === myId && !isAdmin}
                <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" disabled={busy} on:click={cancel}>{t('Cancel my request')}</button>
              {/if}
              {#if isAdmin}
                <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" disabled={busy} on:click={() => { note = ''; mode = 'reject'; }}>{t('Refuse')}</button>
                <button type="button" class="b2s-btn b2s-btn-primary b2s-btn-sm" disabled={busy || working} on:click={approve}>
                  {t('Approve: {size}', { size: formatBytes(pending.requested_limit_bytes) })}</button>
              {/if}
            </div>
          {/if}
        </div>
      {/if}

      {#if mode === 'edit' || mode === 'ask'}
        <div class="qc__form">
          <label class="qc__field">{mode === 'ask' ? t('Room needed') : t('Limit')}
            <span class="qc__size">
              <input class="b2s-input" type="number" min="1" step="any" bind:value={amount} />
              <select class="b2s-input" bind:value={unit}>{#each UNITS as [name] (name)}<option value={name}>{name}</option>{/each}</select>
            </span>
          </label>
          {#if mode === 'edit'}
            <div class="qc__field">{t('When it is full')}
              <span class="qc__seg" role="radiogroup" aria-label={t('When it is full')}>
                <button type="button" role="radio" aria-checked={!soft} class:is-on={!soft} on:click={() => (soft = false)}>{t('Block writes')}</button>
                <button type="button" role="radio" aria-checked={soft} class:is-on={soft} on:click={() => (soft = true)}>{t('Only warn')}</button>
              </span>
            </div>
            <label class="qc__field">{t('Warn from')}
              <select class="b2s-input" bind:value={warn}>{#each WARN as value (value)}<option value={value}>{value} %</option>{/each}</select>
            </label>
            {#if quota?.used_bytes != null && !soft && bytes < quota.used_bytes}
              <p class="qc__warn qc__wide">{t('The folder already uses {size}: a hard quota below it would block every write.', { size: formatBytes(quota.used_bytes) })}</p>
            {/if}
          {:else}
            <label class="qc__field qc__wide">{t('Why does the folder need it?')}
              <input class="b2s-input" bind:value={reason} maxlength="500" placeholder={t('e.g. The 2027 budget files arrive in January')} /></label>
          {/if}
          <div class="qc__btns qc__wide">
            <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" on:click={() => (mode = 'none')}>{t('Cancel')}</button>
            {#if mode === 'edit'}
              <button type="button" class="b2s-btn b2s-btn-primary b2s-btn-sm" disabled={busy || bytes < 1024 ** 2} on:click={save}>
                {has ? t('Change to {size}', { size: formatBytes(bytes) }) : t('Set {size}', { size: formatBytes(bytes) })}</button>
            {:else}
              <button type="button" class="b2s-btn b2s-btn-primary b2s-btn-sm" disabled={busy || reason.trim().length < 5 || bytes <= (quota?.limit_bytes ?? 0)} on:click={ask}>
                {t('Ask for {size}', { size: formatBytes(bytes) })}</button>
            {/if}
          </div>
        </div>
      {:else if mode === 'remove'}
        <div class="qc__form">
          <p class="qc__wide">{t('The folder will be able to grow until the disk is full. The server keeps no trace of the quota.')}</p>
          <div class="qc__btns qc__wide">
            <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" on:click={() => (mode = 'none')}>{t('Cancel')}</button>
            <button type="button" class="b2s-btn b2s-btn-danger b2s-btn-sm" disabled={busy} on:click={remove}>{t('Remove the quota')}</button>
          </div>
        </div>
      {:else if !working}
        <div class="qc__actions">
          {#if isAdmin}
            <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" on:click={openEdit}>
              <i class="bi bi-sliders" aria-hidden="true"></i>{has ? t('Change') : t('Set a quota')}</button>
            {#if has}<button type="button" class="b2s-link-btn" on:click={() => (mode = 'remove')}>{t('Remove')}</button>{/if}
          {/if}
          {#if has && !pending}
            <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" on:click={openAsk}><i class="bi bi-arrow-up-circle" aria-hidden="true"></i>{t('Ask for more room')}</button>
          {/if}
          {#if has || quota?.status === 'failed'}
            <button type="button" class="b2s-link-btn" disabled={busy} on:click={refresh}>{t('Read again')}</button>
          {/if}
        </div>
      {/if}

      {#if decided.length}
        <ul class="qc__history">
          {#each decided as row (row.id)}
            <li animate:flip={{ duration: dur(MOTION.base) }} in:pop={{ y: 4 }} out:pop={{ duration: MOTION.fast, y: 0 }}>
              <i class={`bi ${row.status === 'approved' ? 'bi-check-circle' : row.status === 'rejected' ? 'bi-x-circle' : 'bi-dash-circle'}`} aria-hidden="true"></i>
              <span>{row.status === 'approved' ? t('{size} granted', { size: formatBytes(row.requested_limit_bytes) })
                : row.status === 'rejected' ? t('{size} refused', { size: formatBytes(row.requested_limit_bytes) })
                : t('{size} cancelled', { size: formatBytes(row.requested_limit_bytes) })}
                <small>· {row.requested_by ?? ''}{row.decided_by && row.status !== 'cancelled' ? ` → ${row.decided_by}` : ''}{row.decision_note ? ` · « ${row.decision_note} »` : ''} · <RelativeTime value={row.decided_at} /></small></span>
            </li>
          {/each}
        </ul>
      {/if}
    {/if}
  </section>
{/if}

<style>
  .qc { display: flex; flex-direction: column; gap: 12px; padding: 16px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .qc header { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
  .qc h2 { display: flex; align-items: center; gap: 8px; margin: 0; font-size: var(--b2s-fs-md); font-weight: 600; }
  .qc header small, .qc__muted { margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .qc__muted { font-size: var(--b2s-fs-sm); }
  .qc__running { display: flex; gap: 10px; align-items: center; margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .qc__error { display: flex; gap: 8px; align-items: flex-start; margin: 0; color: var(--b2s-color-danger-strong, #b42318); font-size: var(--b2s-fs-sm); }
  .qc__gauge { display: flex; flex-direction: column; gap: 8px; --qc-fill: var(--b2s-color-info-strong); }
  .qc__gauge[data-tone='ok'] { --qc-fill: var(--b2s-color-success-strong, #1a7f37); }
  .qc__gauge[data-tone='warning'] { --qc-fill: var(--b2s-color-warning-strong, #9a5b00); }
  .qc__gauge[data-tone='danger'] { --qc-fill: var(--b2s-color-danger-strong, #b42318); }
  .qc__figures { display: flex; align-items: baseline; gap: 8px; }
  .qc__figures strong { font-size: 22px; font-weight: 650; font-variant-numeric: tabular-nums; }
  .qc__figures span { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .qc__pct { margin-left: auto; color: var(--qc-fill); font-variant-numeric: tabular-nums; }
  .qc__bar { position: relative; height: 10px; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-neutral-soft); }
  .qc__bar span { position: absolute; inset: 0 auto 0 0; border-radius: inherit; background: var(--qc-fill); transition: width var(--b2s-motion-slow) var(--b2s-ease-out), background-color var(--b2s-motion-base); }
  .qc__mark { position: absolute; top: -3px; bottom: -3px; width: 2px; background: var(--b2s-color-text-muted); border-radius: 1px; }
  .qc__chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .qc__chip { padding: 2px 10px; border-radius: var(--b2s-radius-pill); border: 1px solid var(--b2s-color-border); font-size: var(--b2s-fs-xs); color: var(--b2s-color-text-muted); }
  .qc__path { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--b2s-color-text-muted); font-family: var(--b2s-font-mono); font-size: var(--b2s-fs-xs); }
  .qc__request { display: flex; flex-direction: column; gap: 8px; padding: 12px; border-radius: var(--b2s-radius-md); background: var(--b2s-color-info-soft); }
  .qc__request p { margin: 0; font-size: var(--b2s-fs-sm); }
  .qc__request small { color: var(--b2s-color-text-muted); }
  .qc__request blockquote { margin: 0; padding-left: 10px; border-left: 3px solid var(--b2s-color-border-strong); font-size: var(--b2s-fs-sm); }
  .qc__form { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; padding: 12px; border: 1px dashed var(--b2s-color-border-strong); border-radius: 12px; }
  .qc__form p { margin: 0; font-size: var(--b2s-fs-sm); }
  .qc__field { display: flex; flex-direction: column; gap: 5px; font-size: var(--b2s-fs-sm); font-weight: 500; }
  .qc__wide { grid-column: 1 / -1; }
  .qc__size { display: grid; grid-template-columns: minmax(0, 1fr) 72px; gap: 6px; }
  .qc__seg { display: flex; gap: 2px; padding: 3px; border-radius: 10px; background: var(--b2s-color-neutral-soft); }
  .qc__seg button { flex: 1; padding: 6px 8px; border: 0; border-radius: 8px; background: transparent; color: var(--b2s-color-text-muted); font: inherit; font-size: var(--b2s-fs-xs); font-weight: 600; cursor: pointer; }
  .qc__seg button.is-on { background: var(--b2s-color-surface); color: var(--b2s-color-text); box-shadow: 0 1px 3px rgba(14, 18, 24, 0.12); }
  .qc__warn { color: var(--b2s-color-warning-strong, #9a5b00); }
  .qc__btns { display: flex; justify-content: flex-end; gap: 8px; }
  .qc__actions { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
  .qc__actions .b2s-btn i { margin-right: 6px; }
  .qc__history { display: flex; flex-direction: column; gap: 4px; margin: 0; padding: 8px 0 0; border-top: 1px solid var(--b2s-color-border); list-style: none; font-size: var(--b2s-fs-xs); }
  .qc__history li { display: flex; gap: 8px; align-items: baseline; }
  .qc__history small { color: var(--b2s-color-text-muted); }
</style>
