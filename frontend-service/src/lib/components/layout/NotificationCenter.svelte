<script lang="ts">
  import { bulkDecision } from '$lib/api/access-requests';
  import { reportUiError } from '$lib/errors';
  import { goto } from '$app/navigation';
  import { onDestroy } from 'svelte';
  import { t } from '$lib/i18n';
  import { apiGetData, apiPost } from '$lib/api/client';
  import { live, markNoticesRead } from '$lib/stores/live';
  import { toast } from '$lib/stores/toast';
  import { pulseOnIncrease } from '$lib/utils/motion';
  import Drawer from '$lib/components/ui/Drawer.svelte';
  import RelativeTime from '$lib/components/ui/RelativeTime.svelte';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';

  /**
   * The bell of the top bar: what concerns the person (a request to decide, a decision on theirs, an access that ends,
   * a breakdown for the administrators). Pushed live; a new notice also shows as a toast that opens it.
   */
  type Notice = { id: number; kind: string; severity: string; title: string; body: string | null; link: string | null; created_at: string; read_at: string | null };

  let open = $state(false);
  let loading = $state(false);
  let items: Notice[] = $state([]);
  let filter = $state<'all' | 'unread'>('all');

  const ICON: Record<string, string> = { review: 'bi-clipboard-check', request: 'bi-inbox', decision: 'bi-check2-circle', expiry: 'bi-hourglass-split', alert: 'bi-exclamation-octagon', task: 'bi-check2-all' };
  const kindLabel = (kind: string) =>
    ({ review: t('Access review'), request: t('Request to decide'), decision: t('Decision'), expiry: t('End of access'), alert: t('Platform'), task: t('Task') })[kind] ?? kind;

  async function load() {
    loading = true;
    try {
      const data = await apiGetData<{ items: Notice[]; unread: number }>(fetch, '/me/notifications', { limit: 60 });
      items = data?.items ?? [];
    } catch {
      items = [];
    } finally {
      loading = false;
    }
  }

  function show() {
    open = true;
    void load();
  }

  async function markRead(ids: number[] | 'all') {
    const fresh = ids === 'all' ? items.filter((n) => !n.read_at).map((n) => n.id) : ids.filter((id) => items.find((n) => n.id === id && !n.read_at));
    if (ids !== 'all' && !fresh.length) return;
    const now = new Date().toISOString();
    items = items.map((n) => (ids === 'all' || fresh.includes(n.id) ? { ...n, read_at: n.read_at ?? now } : n));
    markNoticesRead(ids === 'all' ? 'all' : fresh.length);
    await apiPost(fetch, '/me/notifications/read', ids === 'all' ? {} : { ids: fresh }).catch(() => undefined);
  }

  function openNotice(notice: Pick<Notice, 'id' | 'link'>) {
    void markRead([notice.id]);
    open = false;
    if (notice.link) void goto(notice.link);
  }

  // A notice that arrives while the app is open: a toast that leads to it
  let lastSeen: number | null = null;
  const stop = live.subscribe((state) => {
    const latest = state.latest;
    if (!latest) return;
    if (lastSeen === null) {
      lastSeen = latest.id;
      return;
    }
    if (latest.id > lastSeen) {
      lastSeen = latest.id;
      const type = latest.severity === 'danger' ? 'error' : latest.severity === 'success' ? 'success' : latest.severity === 'warning' ? 'warning' : 'info';
      toast[type](latest.title, latest.link ? { action: { label: t('Open'), run: () => openNotice(latest) } } : undefined);
      if (open) void load();
    }
  });
  onDestroy(stop);

  // ---- act from the notice: approve a request (a refusal needs its reason: the request opens) ----
  const requestOf = (notice: Notice) => (notice.kind === 'request' ? Number(/focus=(\d+)/.exec(notice.link ?? '')?.[1] ?? 0) || null : null);
  let deciding = $state<number | null>(null);
  let decided = $state(new Set<number>());
  async function approve(notice: Notice) {
    const id = requestOf(notice);
    if (!id || deciding) return;
    deciding = notice.id;
    try {
      const result = await bulkDecision(fetch, [id], 'approve');
      const failed = (result as any)?.failed_ids?.length;
      if (failed) toast.error(t('The request could not be approved: open it to see why.'), { action: { label: t('Open'), run: () => openNotice(notice) } });
      else {
        toast.success(t('Request approved: the access is being applied.'));
        decided = new Set([...decided, notice.id]);
        void markRead([notice.id]);
      }
    } catch (failure) {
      reportUiError(failure, t('Unable to approve the request.'), 'notifications.approve');
    } finally {
      deciding = null;
    }
  }

  let unread = $derived($live.unread);
  let shown = $derived(filter === 'unread' ? items.filter((n) => !n.read_at) : items);
  // Grouped by kind (what to decide first), newest first inside each
  const ORDER = ['request', 'review', 'alert', 'expiry', 'decision', 'task'];
  let groups = $derived(Object.entries(shown.reduce((all: Record<string, Notice[]>, notice) => {
    (all[notice.kind] ??= []).push(notice);
    return all;
  }, {})).sort(([a], [b]) => (ORDER.indexOf(a) + 1 || 99) - (ORDER.indexOf(b) + 1 || 99)));
</script>

<button type="button" class="nc-trigger" class:has-unread={unread > 0} onclick={show}
  aria-label={unread ? t('Notifications ({count} unread)', { count: unread }) : t('Notifications')}
  title={unread ? t('Notifications ({count} unread)', { count: unread }) : t('Notifications')}>
  <i class="bi bi-bell" aria-hidden="true"></i>
  {#if unread}<b class="nc-badge" use:pulseOnIncrease={unread}>{unread > 99 ? '99+' : unread}</b>{/if}
</button>

<Drawer {open} onClose={() => (open = false)} title={t('Notifications')} subtitle={unread ? t('{count} unread', { count: unread }) : t('All read')}
  iconClass="bi bi-bell" showFooter={false} ariaLabelledby="nc-title">
  <div class="nc-tools">
    <div class="nc-filter" role="group" aria-label={t('Show')}>
      <button type="button" class:is-on={filter === 'all'} aria-pressed={filter === 'all'} onclick={() => (filter = 'all')}>{t('All')}</button>
      <button type="button" class:is-on={filter === 'unread'} aria-pressed={filter === 'unread'} onclick={() => (filter = 'unread')}>{t('Unread')}</button>
    </div>
    <button type="button" class="b2s-link-btn" disabled={!items.some((n) => !n.read_at)} onclick={() => markRead('all')}>{t('Mark all as read')}</button>
  </div>
  {#if loading && !items.length}
    <LoadingState skeleton="rows" rows={5} />
  {:else if !shown.length}
    <p class="nc-empty"><i class="bi bi-bell-slash" aria-hidden="true"></i>{filter === 'unread' ? t('Nothing new: you are up to date.') : t('No notification yet. Requests to decide, decisions and ends of access will show here.')}</p>
  {:else}
    {#each groups as [kind, notices] (kind)}
    <h3 class="nc-group">{kindLabel(kind)} <small>{notices.length}</small></h3>
    <ul class="nc-list">
      {#each notices as notice (notice.id)}
        <li class:is-unread={!notice.read_at} class={`is-${notice.severity}`}>
          <button type="button" onclick={() => openNotice(notice)}>
            <span class="nc-icon" aria-hidden="true"><i class={`bi ${ICON[notice.kind] ?? 'bi-bell'}`}></i></span>
            <span class="nc-text">
              <small>{kindLabel(notice.kind)} · <RelativeTime value={notice.created_at} /></small>
              <strong>{notice.title}</strong>
              {#if notice.body}<span class="nc-body">{notice.body}</span>{/if}
            </span>
            {#if !notice.read_at}<span class="nc-dot" aria-label={t('Unread')}></span>{/if}
          </button>
          {#if requestOf(notice) && !decided.has(notice.id)}
            <div class="nc-acts">
              <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-primary" disabled={deciding !== null} onclick={() => approve(notice)}>
                <i class="bi bi-check2" aria-hidden="true"></i>{deciding === notice.id ? t('Approving…') : t('Approve')}</button>
              <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" onclick={() => openNotice(notice)}>{t('Refuse…')}</button>
            </div>
          {:else if decided.has(notice.id)}
            <p class="nc-done"><i class="bi bi-check2-circle" aria-hidden="true"></i> {t('Approved from here')}</p>
          {/if}
        </li>
      {/each}
    </ul>
    {/each}
  {/if}
</Drawer>

<style>
  .nc-group { display: flex; gap: 6px; align-items: baseline; margin: 14px 0 6px; color: var(--b2s-color-text-muted); font-size: 11px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; }
  .nc-group small { font-size: 11px; }
  .nc-acts { display: flex; gap: 8px; padding: 0 12px 10px 52px; }
  .nc-done { margin: 0; padding: 0 12px 10px 52px; color: var(--b2s-color-success-strong); font-size: var(--b2s-fs-xs); }
  .nc-trigger { position: relative; width: 38px; height: 38px; display: flex; align-items: center; justify-content: center; padding: 0;
    border: 1px solid var(--b2s-color-border-soft); border-radius: 11px; background: var(--b2s-color-surface); color: var(--b2s-color-text-muted); font: inherit; cursor: pointer; }
  .nc-trigger:hover { background: var(--b2s-color-surface-muted); color: var(--b2s-color-text); }
  .nc-trigger i { font-size: 16px; }
  .nc-trigger.has-unread i { color: var(--b2s-color-text); }
  .nc-badge { position: absolute; top: -6px; right: -6px; min-width: 18px; height: 18px; padding: 0 5px; border: 2px solid #fff; border-radius: 999px; background: var(--b2s-color-danger); color: #fff;
    font-size: 10px; font-weight: 700; line-height: 18px; text-align: center; }
  .nc-tools { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
  .nc-filter { display: inline-flex; padding: 3px; border-radius: 10px; background: var(--b2s-color-surface-muted); }
  .nc-filter button { border: 0; background: transparent; padding: 5px 12px; border-radius: 8px; font: inherit; font-size: var(--b2s-fs-sm); color: var(--b2s-color-text-muted); cursor: pointer; }
  .nc-filter button.is-on { background: var(--b2s-color-surface); color: var(--b2s-color-text); font-weight: 600; box-shadow: 0 1px 3px rgba(18, 31, 64, 0.1); }
  .nc-empty { display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 40px 12px; color: var(--b2s-color-text-muted); text-align: center; font-size: var(--b2s-fs-sm); }
  .nc-empty i { font-size: 26px; }
  .nc-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; }
  .nc-list button { width: 100%; display: grid; grid-template-columns: 34px minmax(0, 1fr) 10px; gap: 12px; align-items: start; padding: 12px; border: 0; border-radius: 12px;
    background: transparent; font: inherit; text-align: left; color: var(--b2s-color-text); cursor: pointer; transition: background var(--b2s-motion-fast, 120ms); }
  .nc-list button:hover { background: var(--b2s-color-surface-muted); }
  .nc-list li.is-unread button { background: var(--b2s-accent-soft); }
  .nc-icon { width: 34px; height: 34px; border-radius: 10px; display: flex; align-items: center; justify-content: center; background: var(--b2s-accent-soft); color: var(--b2s-accent-strong); }
  .is-success .nc-icon { background: var(--b2s-color-success-soft); color: var(--b2s-color-success-strong); }
  .is-warning .nc-icon { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .is-danger .nc-icon { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger-strong); }
  .nc-text { display: grid; gap: 3px; min-width: 0; }
  .nc-text small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .nc-text strong { font-size: var(--b2s-fs-sm); font-weight: 600; }
  .nc-body { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; white-space: pre-line; }
  .nc-dot { width: 8px; height: 8px; margin-top: 6px; border-radius: 50%; background: var(--b2s-accent-vivid); }
</style>
