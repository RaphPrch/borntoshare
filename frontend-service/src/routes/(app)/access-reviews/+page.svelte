<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { intlLocale, t } from '$lib/i18n';
  import { apiGetData, apiGetList, apiPostData } from '$lib/api/client';
  import { formatDate } from '$lib/utils/format';
  import { reportUiError } from '$lib/errors';
  import { toast } from '$lib/stores/toast';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import Drawer from '$lib/components/ui/Drawer.svelte';
  import ContextMenu, { menuPositionFor, type ContextMenuItem } from '$lib/components/ui/ContextMenu.svelte';
  import { copyText } from '$lib/utils/clipboard';
  import { readParam, writeParams } from '$lib/utils/url-state';

  /**
   * Access review campaigns: each guardian keeps or removes, person by person, the accesses to their folders; the
   * closed campaign is the evidence of the review (ISO 27001, NIS2). One card per review with its progress (kept,
   * to remove, to review) and its due date; administrators open a review from a side panel.
   */
  type Review = { id: number; name: string; status: 'open' | 'closed'; due_at: string | null; created_by: string | null; created_at: string;
    closed_at: string | null; total: number; decided: number; keep: number; revoke: number; revoked: number; manual: number; failed: number; folders: number };
  type Folder = { storage_root_id: number; storage_root_name: string; root_path: string; zone_name?: string | null; storage_endpoint_name?: string | null };

  let isAdmin = $derived(Boolean(($page.data as any)?.me?.is_admin));
  let reviews = $state<Review[] | null>(null);
  let error = $state('');
  let tab = $state<'open' | 'closed'>(readParam('tab', 'open', ['open', 'closed'] as const));
  $effect(() => writeParams({ tab: tab === 'open' ? null : tab }));

  async function load() {
    try {
      reviews = await apiGetData<Review[]>(fetch, '/access-reviews');
    } catch (failure) {
      error = failure instanceof Error ? failure.message : t('Unable to load the reviews.');
    }
  }
  onMount(load);

  // ---- figures and cards ----
  let opened = $derived((reviews ?? []).filter((review) => review.status === 'open'));
  let closed = $derived((reviews ?? []).filter((review) => review.status === 'closed'));
  let shown = $derived(tab === 'open' ? opened : closed);
  let toReview = $derived(opened.reduce((sum, review) => sum + Math.max(0, review.total - review.decided), 0));
  let toApply = $derived(opened.reduce((sum, review) => sum + Math.max(0, review.revoke - review.revoked - review.manual - review.failed), 0));
  let nearest = $derived([...opened].filter((review) => review.due_at).sort((a, b) => Date.parse(String(a.due_at)) - Date.parse(String(b.due_at)))[0] ?? null);
  const pct = (part: number, whole: number) => (whole ? (part / whole) * 100 : 0);
  const daysLeft = (iso: string | null) => (iso ? Math.ceil((Date.parse(iso) - Date.now()) / 86400000) : null);
  function dueLabel(review: Review): { label: string; tone: 'mut' | 'ok' | 'warn' | 'bad' } {
    if (review.status === 'closed') return { label: review.closed_at ? t('closed {date}', { date: formatDate(review.closed_at) }) : t('Closed'), tone: 'mut' };
    const days = daysLeft(review.due_at);
    if (days == null) return { label: t('No due date'), tone: 'ok' };
    if (days < 0) return { label: t('{count} day(s) late', { count: -days }), tone: 'bad' };
    if (days === 0) return { label: t('due today'), tone: 'warn' };
    return { label: t('in {count} day(s)', { count: days }), tone: days <= 7 ? 'warn' : 'ok' };
  }

  // ---- right click on a card ----
  let menu = $state<{ review: Review; at: { x: number; y: number } } | null>(null);
  const menuItems = (review: Review): ContextMenuItem[] => [
    { key: 'open', label: t('Open the review'), icon: 'bi-box-arrow-up-right' },
    { key: 'summary', label: t('Summary and application'), icon: 'bi-list-check' },
    { key: 'link', label: t('Copy the link'), icon: 'bi-link-45deg' },
    ...(isAdmin ? [{ key: 'close', label: t('Close the review'), icon: 'bi-archive', separated: true, disabled: review.status !== 'open',
      hint: review.status !== 'open' ? t('Already closed') : undefined }] : [])
  ];
  async function pick(key: string) {
    const review = menu?.review;
    menu = null;
    if (!review) return;
    if (key === 'open') await goto(`/access-reviews/${review.id}`);
    else if (key === 'summary') await goto(`/access-reviews/${review.id}?view=summary`);
    else if (key === 'link') { if (await copyText(`${window.location.origin}/access-reviews/${review.id}`)) toast.success(t('Link copied.')); }
    else if (key === 'close') {
      try {
        await apiPostData(fetch, `/access-reviews/${review.id}/close`, {});
        toast.success(t('Review closed.'));
        await load();
      } catch (failure) {
        reportUiError(failure, t('Unable to close the review.'), 'access-reviews.close');
      }
    }
  }

  // ---- opening a review (administrators) ----
  let opening = $state(false);
  let creating = $state(false);
  let name = $state(`${t('Access review')} ${new Date().toLocaleDateString(intlLocale(), { month: 'long', year: 'numeric' })}`);
  let dueIn = $state<number>(21);
  let due = $state(new Date(Date.now() + 21 * 86400000).toISOString().slice(0, 10));
  let scope = $state<'all' | 'some'>('all');
  let folders = $state<Folder[]>([]);
  let chosen = $state(new Map<number, Folder>());
  let folderQuery = $state('');
  const DUES: Array<[number, string]> = [[14, 'In 2 weeks'], [21, 'In 3 weeks'], [30, 'In 1 month']];
  function setDue(days: number) {
    dueIn = days;
    due = new Date(Date.now() + days * 86400000).toISOString().slice(0, 10);
  }
  async function openForm() {
    opening = true;
    // The light list (name, path, zone, server): enough to choose
    if (!folders.length) folders = await apiGetList<Folder>(fetch, '/storage-roots/requestable').catch(() => []);
  }
  let needle = $derived(folderQuery.trim().toLowerCase());
  let found = $derived(needle ? folders.filter((row) => `${row.storage_root_name} ${row.root_path} ${row.zone_name ?? ''} ${row.storage_endpoint_name ?? ''}`.toLowerCase().includes(needle)).slice(0, 60) : []);
  function flip(row: Folder) {
    const next = new Map(chosen);
    if (next.has(row.storage_root_id)) next.delete(row.storage_root_id);
    else next.set(row.storage_root_id, row);
    chosen = next;
  }
  function chooseAll(rows: Folder[]) {
    const next = new Map(chosen);
    for (const row of rows) next.set(row.storage_root_id, row);
    chosen = next;
  }
  let folderCount = $derived(scope === 'all' ? folders.length : chosen.size);
  async function create() {
    if (creating || !name.trim() || (scope === 'some' && !chosen.size)) return;
    creating = true;
    try {
      const result = await apiPostData<{ id: number; items: number; folders: number; guardians_notified: number }>(fetch, '/access-reviews', {
        name: name.trim(), due_at: due ? `${due}T23:59:00Z` : null, root_ids: scope === 'some' ? [...chosen.keys()] : null });
      toast.success(t('Review opened: {count} access(es) to review on {folders} folder(s), {guardians} guardian(s) told.',
        { count: result?.items ?? 0, folders: result?.folders ?? 0, guardians: result?.guardians_notified ?? 0 }));
      opening = false;
      await goto(`/access-reviews/${result?.id}`);
    } catch (failure) {
      reportUiError(failure, t('Unable to open the review.'), 'access-reviews.open');
    } finally {
      creating = false;
    }
  }
</script>

<section class="v2 rl">
  <div class="v2-head">
    <div>
      <h1>{t('Access reviews')}</h1>
      <p>{t('At a given time, every person who reaches a folder is listed for its guardians, who keep or remove each access. The closed review is the evidence of the control.')}</p>
    </div>
    {#if isAdmin}<div class="v2-head__act"><button type="button" class="b2s-btn b2s-btn-primary" onclick={openForm}><i class="bi bi-plus-lg" aria-hidden="true"></i>{t('Open a review')}</button></div>{/if}
  </div>

  {#if error}
    <p class="v2-empty">{error}</p>
  {:else if !reviews}
    <LoadingState block skeleton="rows" rows={4} />
  {:else}
    <div class="v2-stats">
      <div class="v2-stat"><i class="bi bi-clipboard-check" aria-hidden="true"></i><small>{t('Reviews in progress')}</small><b>{opened.length}</b><span>{t('{count} access(es) concerned', { count: opened.reduce((sum, review) => sum + review.total, 0) })}</span></div>
      <div class="v2-stat"><i class="bi bi-people" aria-hidden="true"></i><small>{t('Accesses still to review')}</small><b>{toReview}</b><span>{t('in the reviews in progress')}</span></div>
      <div class="v2-stat"><i class="bi bi-calendar-event is-warn" aria-hidden="true"></i><small>{t('Nearest due date')}</small><b class:rl__warn={nearest && (daysLeft(nearest.due_at) ?? 99) <= 7}>{nearest ? dueLabel(nearest).label : '—'}</b><span>{nearest?.name ?? t('No review in progress')}</span></div>
      <div class="v2-stat"><i class="bi bi-person-dash is-bad" aria-hidden="true"></i><small>{t('Removals to apply')}</small><b class:rl__bad={toApply > 0}>{toApply}</b><span>{t('decided, not done yet')}</span></div>
    </div>

    <div class="v2-seg rl__tabs" role="group" aria-label={t('Reviews')}>
      <button type="button" class:is-on={tab === 'open'} aria-pressed={tab === 'open'} onclick={() => (tab = 'open')}>{t('In progress')} <b>{opened.length}</b></button>
      <button type="button" class:is-on={tab === 'closed'} aria-pressed={tab === 'closed'} onclick={() => (tab = 'closed')}>{t('Closed')} <b>{closed.length}</b></button>
    </div>

    <div class="rl__grid">
      {#each shown as review (review.id)}
        {@const dueInfo = dueLabel(review)}
        {@const todo = Math.max(0, review.total - review.decided)}
        <article class="rl__card" oncontextmenu={(event) => { event.preventDefault(); menu = { review, at: menuPositionFor(event) }; }}>
          <header>
            <div>
              <h2><a href={`/access-reviews/${review.id}`}>{review.name}</a></h2>
              <p>{t('{folders} folder(s) · {count} access(es) · opened {date} by {who}', { folders: review.folders, count: review.total, date: formatDate(review.created_at), who: review.created_by ?? '—' })}</p>
            </div>
            <span class={`rl__due is-${dueInfo.tone}`}>{dueInfo.label}</span>
          </header>
          <div class="rl__bar" role="img" aria-label={t('{pct} % decided', { pct: Math.round(pct(review.decided, review.total)) })}>
            <i class="is-keep" style={`width:${pct(review.keep, review.total)}%`}></i><i class="is-revoke" style={`width:${pct(review.revoke, review.total)}%`}></i>
          </div>
          <p class="rl__legend">
            <b>{Math.round(pct(review.decided, review.total))} %</b> {t('decided')}
            <span><i class="rl__dot is-keep"></i>{t('{count} kept', { count: review.keep })}</span>
            <span><i class="rl__dot is-revoke"></i>{t('{count} to remove', { count: review.revoke })}</span>
            <span><i class="rl__dot"></i>{t('{count} to review', { count: todo })}</span>
          </p>
          <footer>
            <span class="rl__note">
              {#if review.status === 'closed'}{t('{revoked} removed, {manual} by hand', { revoked: review.revoked, manual: review.manual })}
              {:else if review.revoke - review.revoked - review.manual - review.failed > 0}{t('{count} removal(s) to apply', { count: review.revoke - review.revoked - review.manual - review.failed })}
              {:else if todo}{t('The guardians decide folder by folder')}{:else}{t('Everything is decided: it can be closed')}{/if}
            </span>
            <a class="b2s-btn b2s-btn-secondary b2s-btn-sm" href={`/access-reviews/${review.id}?view=summary`}>{review.status === 'open' ? t('Review summary') : t('Export the evidence')}</a>
            <a class="b2s-btn b2s-btn-primary b2s-btn-sm" href={`/access-reviews/${review.id}`}>{review.status === 'open' ? t('Continue') : t('See')}</a>
          </footer>
        </article>
      {:else}
        <p class="v2-empty">{tab === 'open'
          ? (isAdmin ? t('No review in progress: open one to have every access checked by the guardians.') : t('No review of your folders for now.'))
          : t('No closed review yet.')}</p>
      {/each}
    </div>
  {/if}
</section>

<ContextMenu open={Boolean(menu)} title={menu?.review.name ?? ''} items={menu ? menuItems(menu.review) : []} at={menu?.at ?? { x: 0, y: 0 }}
  onClose={() => (menu = null)} onPick={(key) => void pick(key)} />

<Drawer open={opening} onClose={() => (opening = false)} title={t('Open a review')} subtitle={t('The guardians are told (bell, and e-mail when it is switched on).')} iconClass="bi bi-clipboard-check" size="md">
  <form id="rl-open" class="rl__form" onsubmit={(event) => { event.preventDefault(); void create(); }}>
    <label class="rl__field">{t('Name')}<input class="b2s-input" bind:value={name} maxlength="190" required /></label>

    <fieldset class="rl__field">
      <legend>{t('Scope')}</legend>
      <div class="rl__scopes">
        <button type="button" class:is-on={scope === 'all'} aria-pressed={scope === 'all'} onclick={() => (scope = 'all')}>
          <b>{t('Every governed folder')}</b><small>{t('{count} folder(s)', { count: folders.length })}</small></button>
        <button type="button" class:is-on={scope === 'some'} aria-pressed={scope === 'some'} onclick={() => (scope = 'some')}>
          <b>{t('A selection')}</b><small>{t('by name, zone or server')}</small></button>
      </div>
      {#if scope === 'some'}
        <label class="v2-search"><i class="bi bi-search" aria-hidden="true"></i><input type="search" bind:value={folderQuery} placeholder={t('Folder, zone, server…')} aria-label={t('Search a folder')} /></label>
        {#if found.length}
          <div class="rl__found">
            <button type="button" class="b2s-link-btn" onclick={() => chooseAll(found)}>{t('Choose the {count} found', { count: found.length })}</button>
            {#each found as row (row.storage_root_id)}
              <label class="rl__check"><input type="checkbox" checked={chosen.has(row.storage_root_id)} onchange={() => flip(row)} />
                <span><b>{row.storage_root_name}</b><small>{row.zone_name ?? ''}{row.storage_endpoint_name ? ` · ${row.storage_endpoint_name}` : ''}</small></span></label>
            {/each}
          </div>
        {/if}
        {#if chosen.size}
          <div class="rl__chips">
            {#each [...chosen.values()].slice(0, 30) as row (row.storage_root_id)}
              <button type="button" class="rl__chip" onclick={() => flip(row)} aria-label={t('Remove {name}', { name: row.storage_root_name })}>{row.storage_root_name} <i class="bi bi-x" aria-hidden="true"></i></button>
            {/each}
            {#if chosen.size > 30}<span class="rl__more">{t('and {count} more', { count: chosen.size - 30 })}</span>{/if}
          </div>
        {/if}
      {/if}
    </fieldset>

    <fieldset class="rl__field">
      <legend>{t('Due date')}</legend>
      <div class="rl__dues">
        {#each DUES as [days, label] (days)}
          <button type="button" class:is-on={dueIn === days} aria-pressed={dueIn === days} onclick={() => setDue(days)}>{t(label)}</button>
        {/each}
        <input class="b2s-input" type="date" bind:value={due} aria-label={t('Due date')} oninput={() => (dueIn = 0)} />
      </div>
    </fieldset>

    <div class="rl__preview">
      <b>{t('On opening')}</b>
      <span>{t('The accesses of {count} folder(s) are listed as they are today, for their guardians.', { count: folderCount })}</span>
      <span class="rl__muted">{t('A folder without a guardian is decided by the administrators. A person who gets an access later is not in this review.')}</span>
    </div>
  </form>
  {#snippet footer()}
    <button type="button" class="b2s-btn b2s-btn-secondary" onclick={() => (opening = false)}>{t('Cancel')}</button>
    <button type="submit" form="rl-open" class="b2s-btn b2s-btn-primary" disabled={creating || !name.trim() || (scope === 'some' && !chosen.size)}>
      <i class="bi bi-check2" aria-hidden="true"></i>{creating ? t('Opening…') : t('Open the review')}</button>
  {/snippet}
</Drawer>

<style>
  .rl { display: grid; gap: 18px; }
  .rl__warn { color: var(--b2s-color-warning-strong); }
  .rl__bad { color: var(--b2s-color-danger-strong); }
  .rl__tabs { justify-self: start; }
  .rl__grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
  .rl__card { display: grid; gap: 12px; padding: 18px; border: 1px solid var(--b2s-color-border-soft); border-radius: 16px; background: #fff; }
  .rl__card header { display: flex; gap: 12px; align-items: flex-start; }
  .rl__card header > div { flex: 1; min-width: 0; }
  .rl__card h2 { margin: 0; font-size: 17px; font-weight: 600; }
  .rl__card h2 a { color: inherit; text-decoration: none; }
  .rl__card h2 a:hover { text-decoration: underline; }
  .rl__card header p { margin: 4px 0 0; color: var(--b2s-color-text-muted); font-size: 13px; }
  .rl__due { flex: none; padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; white-space: nowrap; }
  .rl__due.is-ok { background: var(--b2s-color-surface-muted); color: var(--b2s-color-text-soft); }
  .rl__due.is-warn { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .rl__due.is-bad { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger-strong); }
  .rl__due.is-mut { background: var(--b2s-color-surface-soft); color: var(--b2s-color-text-muted); }
  .rl__bar { display: flex; height: 10px; border-radius: 999px; overflow: hidden; background: var(--b2s-color-surface-muted); }
  .rl__bar i { display: block; height: 100%; }
  .rl__bar .is-keep, .rl__dot.is-keep { background: var(--b2s-accent); }
  .rl__bar .is-revoke, .rl__dot.is-revoke { background: var(--b2s-color-danger-strong); }
  .rl__legend { display: flex; flex-wrap: wrap; gap: 6px 16px; margin: -4px 0 0; color: var(--b2s-color-text-soft); font-size: 12.5px; }
  .rl__legend span { display: inline-flex; align-items: center; gap: 6px; }
  .rl__dot { width: 9px; height: 9px; border-radius: 3px; background: var(--b2s-color-neutral-soft); }
  .rl__card footer { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .rl__note { flex: 1 1 200px; color: var(--b2s-color-text-muted); font-size: 12.5px; }
  .rl__form { display: grid; gap: 18px; }
  .rl__field { display: grid; gap: 8px; margin: 0; padding: 0; border: 0; font-size: 13px; font-weight: 500; }
  .rl__field legend { margin-bottom: 8px; padding: 0; font-weight: 500; }
  .rl__scopes { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; }
  .rl__scopes button { display: grid; gap: 2px; padding: 10px 12px; border: 1px solid var(--b2s-color-border-soft); border-radius: 10px; background: #fff; font: inherit; text-align: left; cursor: pointer; }
  .rl__scopes button.is-on { border-color: var(--b2s-accent); box-shadow: inset 0 0 0 1px var(--b2s-accent); }
  .rl__scopes b { font-size: 13px; font-weight: 600; }
  .rl__scopes small, .rl__check small, .rl__muted { color: var(--b2s-color-text-muted); font-size: 12px; font-weight: 400; }
  .rl__found { display: grid; gap: 2px; max-height: 240px; overflow: auto; padding: 6px; border: 1px solid var(--b2s-color-border-soft); border-radius: 10px; }
  .rl__found .b2s-link-btn { justify-self: start; margin: 2px 4px 6px; font-size: 12.5px; }
  .rl__check { display: flex; gap: 8px; align-items: center; padding: 4px; border-radius: 6px; font-weight: 400; cursor: pointer; }
  .rl__check:hover { background: var(--b2s-color-surface-soft); }
  .rl__check span { display: grid; }
  .rl__chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .rl__chip { display: inline-flex; gap: 4px; align-items: center; padding: 3px 6px 3px 10px; border: 0; border-radius: 999px; background: var(--b2s-color-surface-muted); font: inherit; font-size: 12px; font-weight: 500; cursor: pointer; }
  .rl__more { color: var(--b2s-color-text-muted); font-size: 12px; font-weight: 400; }
  .rl__dues { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
  .rl__dues button { height: 32px; padding: 0 12px; border: 1px solid var(--b2s-color-border); border-radius: 999px; background: #fff; font: inherit; font-size: 13px; font-weight: 400; cursor: pointer; }
  .rl__dues button.is-on { border-color: var(--b2s-accent); background: var(--b2s-accent); color: #fff; }
  .rl__dues input { width: 160px; height: 32px; }
  .rl__preview { display: grid; gap: 6px; padding: 14px; border-radius: 12px; background: var(--b2s-color-surface-soft); font-size: 13px; }
  .rl__preview b { font-weight: 600; }
</style>
