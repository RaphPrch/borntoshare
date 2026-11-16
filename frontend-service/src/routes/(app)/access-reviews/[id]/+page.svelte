<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { t } from '$lib/i18n';
  import { apiGetData, apiPostData } from '$lib/api/client';
  import { formatDate, formatDateTime } from '$lib/utils/format';
  import { csvFilename, downloadCsv } from '$lib/utils/csv';
  import { reportUiError } from '$lib/errors';
  import { toast } from '$lib/stores/toast';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import ConfirmActionModal from '$lib/components/ui/ConfirmActionModal.svelte';

  /**
   * One access review: for each folder, every person who reaches it and how (request, AD group, group outside
   * BornToShare). The guardian keeps or removes each access; « Apply the removals » revokes those a request granted
   * and marks the others « to remove by hand ». The administrator closes the review: its export is the evidence.
   */
  type Via = { kind: string; group?: string | null; code?: string; nested?: boolean };
  type Item = { id: number; storage_root_id: number; root_name: string; root_path: string; username: string | null; display_name: string | null;
    level: string | null; via: Via[]; revocable: boolean; decision: 'keep' | 'revoke' | null; note: string | null; decided_by: string | null;
    decided_at: string | null; outcome: 'revoked' | 'manual' | 'failed' | null; outcome_detail: string | null };
  type Data = { review: { id: number; name: string; status: 'open' | 'closed'; due_at: string | null; created_at: string; created_by: string | null; closed_at: string | null }; items: Item[] };

  let reviewId = $derived(Number($page.params.id));
  let isAdmin = $derived(Boolean(($page.data as any)?.me?.is_admin));
  let data = $state<Data | null>(null);
  let error = $state('');
  let filter = $state<'todo' | 'revoke' | 'all'>('todo');
  let query = $state('');
  let busy = $state(false);
  let confirmApply = $state(false);
  let confirmClose = $state(false);

  async function load() {
    try {
      data = await apiGetData<Data>(fetch, `/access-reviews/${reviewId}`);
    } catch (failure) {
      error = failure instanceof Error ? failure.message : t('Unable to load the review.');
    }
  }
  onMount(load);

  async function decide(items: Item[], decision: 'keep' | 'revoke' | null) {
    const ids = items.filter((item) => !item.outcome).map((item) => item.id);
    if (!ids.length || busy) return;
    busy = true;
    try {
      await apiPostData(fetch, `/access-reviews/${reviewId}/decisions`, { item_ids: ids, decision });
      await load();
    } catch (failure) {
      reportUiError(failure, t('Unable to record the decision.'), 'access-reviews.decide');
    } finally {
      busy = false;
    }
  }
  async function applyRemovals() {
    confirmApply = false;
    busy = true;
    try {
      const result = await apiPostData<{ revoked: number; manual: number; failed: number }>(fetch, `/access-reviews/${reviewId}/apply`, {});
      toast.success(t('{revoked} access(es) removed, {manual} to remove by hand, {failed} failed.', { revoked: result?.revoked ?? 0, manual: result?.manual ?? 0, failed: result?.failed ?? 0 }));
      await load();
    } catch (failure) {
      reportUiError(failure, t('Unable to apply the removals.'), 'access-reviews.apply');
    } finally {
      busy = false;
    }
  }
  async function closeReview() {
    confirmClose = false;
    busy = true;
    try {
      await apiPostData(fetch, `/access-reviews/${reviewId}/close`, {});
      toast.success(t('Review closed.'));
      await load();
    } catch (failure) {
      reportUiError(failure, t('Unable to close the review.'), 'access-reviews.close');
    } finally {
      busy = false;
    }
  }

  const viaText = (via: Via[]) => via.map((item) => item.kind === 'request' ? t('request {code}', { code: item.code ?? '' })
    : item.kind === 'outside' ? t('{group} (outside BornToShare)', { group: item.group ?? '' })
      : item.kind === 'ad_only' ? t('{group} (added in the directory)', { group: item.group ?? '' }) : `${item.group ?? ''}${item.nested ? ` (${t('nested group')})` : ''}`)
    .filter((value, index, all) => value && all.indexOf(value) === index).join(' · ');
  const OUTCOME = (): Record<string, string> => ({ revoked: t('Removed'), manual: t('To remove by hand'), failed: t('Removal failed') });

  let open = $derived(data?.review.status === 'open');
  let items = $derived((data?.items ?? []).filter((item) => (filter === 'all' || (filter === 'todo' ? !item.decision : item.decision === 'revoke'))
    && (!query.trim() || `${item.display_name ?? ''} ${item.username ?? ''} ${item.root_name}`.toLowerCase().includes(query.trim().toLowerCase()))));
  let byFolder = $derived(Object.values(items.reduce((groups: Record<number, { id: number; name: string; path: string; items: Item[] }>, item) => {
    (groups[item.storage_root_id] ??= { id: item.storage_root_id, name: item.root_name, path: item.root_path, items: [] }).items.push(item);
    return groups;
  }, {})));
  let counts = $derived({ total: data?.items.length ?? 0, todo: data?.items.filter((item) => !item.decision).length ?? 0,
    keep: data?.items.filter((item) => item.decision === 'keep').length ?? 0, revoke: data?.items.filter((item) => item.decision === 'revoke').length ?? 0,
    pending: data?.items.filter((item) => item.decision === 'revoke' && !item.outcome).length ?? 0, manual: data?.items.filter((item) => item.outcome === 'manual').length ?? 0 });

  const exportEvidence = () => downloadCsv(csvFilename(`revue-acces-${data?.review.name ?? reviewId}`), [
    { header: t('Folder'), value: (row: Item) => row.root_path }, { header: t('Person'), value: (row: Item) => row.display_name ?? '' },
    { header: t('Account'), value: (row: Item) => row.username ?? '' }, { header: t('Access'), value: (row: Item) => row.level ?? '' },
    { header: t('Through'), value: (row: Item) => viaText(row.via) }, { header: t('Decision'), value: (row: Item) => row.decision ?? '' },
    { header: t('Decided by'), value: (row: Item) => row.decided_by ?? '' }, { header: t('Date'), value: (row: Item) => row.decided_at ?? '' },
    { header: t('Result'), value: (row: Item) => (row.outcome ? OUTCOME()[row.outcome] : '') + (row.outcome_detail ? ` — ${row.outcome_detail}` : '') }
  ], data?.items ?? []);
</script>

<section class="v2 rd">
  <a class="rd__back" href="/access-reviews"><i class="bi bi-arrow-left" aria-hidden="true"></i>{t('All the reviews')}</a>
  {#if error}
    <p class="v2-empty">{error}</p>
  {:else if !data}
    <LoadingState block skeleton="rows" rows={6} />
  {:else}
    <div class="v2-head">
      <div>
        <h1>{data.review.name}</h1>
        <p>{t('Opened {date} by {who}', { date: formatDate(data.review.created_at), who: data.review.created_by ?? '—' })}{data.review.due_at ? ` · ${t('until {date}', { date: formatDate(data.review.due_at) })}` : ''}{data.review.closed_at ? ` · ${t('closed {date}', { date: formatDate(data.review.closed_at) })}` : ''}</p>
      </div>
      <div class="v2-head__act">
        <button type="button" class="b2s-btn b2s-btn-secondary" onclick={exportEvidence}><i class="bi bi-download" aria-hidden="true"></i>{t('Export the evidence')}</button>
        {#if open && counts.pending}<button type="button" class="b2s-btn b2s-btn-primary" disabled={busy} onclick={() => (confirmApply = true)}><i class="bi bi-person-dash" aria-hidden="true"></i>{t('Apply the {count} removal(s)', { count: counts.pending })}</button>{/if}
        {#if open && isAdmin}<button type="button" class="b2s-btn b2s-btn-secondary" disabled={busy} onclick={() => (confirmClose = true)}>{t('Close the review')}</button>{/if}
      </div>
    </div>

    <div class="v2-stats">
      <div class="v2-stat"><small>{t('To review')}</small><b>{counts.todo}</b><span>{t('of {count} access(es)', { count: counts.total })}</span></div>
      <div class="v2-stat"><small>{t('Kept')}</small><b>{counts.keep}</b></div>
      <div class="v2-stat"><small>{t('To remove')}</small><b>{counts.revoke}</b><span>{counts.pending ? t('{count} not applied yet', { count: counts.pending }) : t('all applied')}</span></div>
      <div class="v2-stat"><small>{t('To remove by hand')}</small><b>{counts.manual}</b><span>{t('accesses that BornToShare did not grant')}</span></div>
    </div>

    <div class="v2-sh">
      <div class="v2-seg" role="group" aria-label={t('Show')}>
        <button type="button" class:is-on={filter === 'todo'} onclick={() => (filter = 'todo')}>{t('To review')} <b>{counts.todo}</b></button>
        <button type="button" class:is-on={filter === 'revoke'} onclick={() => (filter = 'revoke')}>{t('To remove')} <b>{counts.revoke}</b></button>
        <button type="button" class:is-on={filter === 'all'} onclick={() => (filter = 'all')}>{t('All')} <b>{counts.total}</b></button>
      </div>
      <div class="v2-sh__r"><label class="v2-search"><i class="bi bi-search" aria-hidden="true"></i><input type="search" bind:value={query} placeholder={t('Person, folder…')} aria-label={t('Search')} /></label></div>
    </div>

    {#each byFolder as folder (folder.id)}
      <div class="v2-sec rd__folder">
        <div class="v2-sh"><div><h2>{folder.name}</h2><code class="v2-sub">{folder.path}</code></div>
          {#if open}<div class="v2-sh__r"><button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" disabled={busy || !folder.items.some((item) => !item.decision)}
            onclick={() => decide(folder.items.filter((item) => !item.decision), 'keep')}>{t('Keep all the others')}</button></div>{/if}</div>
        <div class="v2-list">
          {#each folder.items as item (item.id)}
            <div class="v2-row rd__row" class:is-revoke={item.decision === 'revoke'}>
              <span class="v2-nm"><b>{item.display_name ?? item.username}</b><span class="v2-sub">{item.username ?? ''}{item.via.length ? ` · ${viaText(item.via)}` : ''}</span></span>
              <span><span class={`v2-tag is-${item.level === 'write' ? 'warn' : 'info'}`}>{item.level === 'write' ? t('Modify') : t('Read')}</span></span>
              <span class="rd__state">
                {#if item.outcome}<span class={`v2-tag is-${item.outcome === 'revoked' ? 'ok' : item.outcome === 'manual' ? 'warn' : 'bad'}`} title={item.outcome_detail ?? ''}>{OUTCOME()[item.outcome]}</span>
                  {#if item.outcome_detail}<small>{item.outcome_detail}</small>{/if}
                {:else if item.decision}<small>{item.decision === 'keep' ? t('Kept') : t('To remove')} · {item.decided_by ?? ''} {item.decided_at ? formatDateTime(item.decided_at) : ''}</small>
                {:else if !item.revocable}<small>{t('Not granted by BornToShare: a removal is done by hand')}</small>{/if}
              </span>
              <span class="rd__acts">
                {#if open && !item.outcome}
                  <button type="button" class="b2s-btn b2s-btn-sm" class:b2s-btn-primary={item.decision === 'keep'} class:b2s-btn-secondary={item.decision !== 'keep'} disabled={busy}
                    onclick={() => decide([item], item.decision === 'keep' ? null : 'keep')}><i class="bi bi-check2" aria-hidden="true"></i>{t('Keep')}</button>
                  <button type="button" class="b2s-btn b2s-btn-sm" class:b2s-btn-danger={item.decision === 'revoke'} class:b2s-btn-secondary={item.decision !== 'revoke'} disabled={busy}
                    onclick={() => decide([item], item.decision === 'revoke' ? null : 'revoke')}><i class="bi bi-x-lg" aria-hidden="true"></i>{t('Remove the access')}</button>
                {/if}
              </span>
            </div>
          {/each}
        </div>
      </div>
    {:else}
      <p class="v2-empty">{filter === 'todo' ? t('Everything is reviewed here.') : t('Nothing here for this filter.')}</p>
    {/each}
  {/if}
</section>

<ConfirmActionModal open={confirmApply} title={t('Apply the removals')}
  subtitle={t('{count} access(es) decided « remove »: those granted by a request are revoked now (the person leaves the AD group of the folder); the others are marked « to remove by hand ».', { count: counts.pending })}
  confirmLabel={t('Remove the accesses')} onConfirm={applyRemovals} onClose={() => (confirmApply = false)} />
<ConfirmActionModal open={confirmClose} title={t('Close the review')}
  subtitle={counts.todo ? t('{count} access(es) are not reviewed: they stay as they are, and the export will say so.', { count: counts.todo }) : t('Every access is reviewed. The review becomes the evidence of the control.')}
  confirmLabel={t('Close the review')} onConfirm={closeReview} onClose={() => (confirmClose = false)} />

<style>
  .rd { display: grid; gap: 16px; padding: var(--b2s-page-padding); }
  .rd__back { display: inline-flex; gap: 6px; align-items: center; width: fit-content; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); text-decoration: none; }
  .rd__folder h2 { margin: 0; font-size: 17px; }
  .rd__row { grid-template-columns: minmax(220px, 2fr) 110px minmax(200px, 1.5fr) auto; }
  .rd__row.is-revoke { background: #fff5f5; }
  .rd__state { display: grid; gap: 2px; }
  .rd__state small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .rd__acts { display: flex; gap: 6px; justify-content: flex-end; }
</style>
