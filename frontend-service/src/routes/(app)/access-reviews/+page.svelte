<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { t } from '$lib/i18n';
  import { apiGetData, apiGetList, apiPostData } from '$lib/api/client';
  import { formatDate } from '$lib/utils/format';
  import { reportUiError } from '$lib/errors';
  import { toast } from '$lib/stores/toast';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import AppModal from '$lib/components/ui/AppModal.svelte';

  /**
   * Access review campaigns: each guardian keeps or removes, person by person, the accesses to their folders; the
   * closed campaign is the evidence of the review (ISO 27001, NIS2). Administrators open and close them.
   */
  type Review = { id: number; name: string; status: 'open' | 'closed'; due_at: string | null; created_by: string | null; created_at: string;
    closed_at: string | null; total: number; decided: number; keep: number; revoke: number; revoked: number; manual: number; failed: number; folders: number };

  let isAdmin = $derived(Boolean(($page.data as any)?.me?.is_admin));
  let reviews = $state<Review[] | null>(null);
  let error = $state('');
  let opening = $state(false);
  let creating = $state(false);
  let name = $state(`Revue des accès ${new Date().toLocaleDateString('fr-FR', { month: 'long', year: 'numeric' })}`);
  let due = $state(new Date(Date.now() + 21 * 86400000).toISOString().slice(0, 10));
  let scope = $state<'all' | 'some'>('all');
  let folders = $state<Array<{ storage_root_id: number; storage_root_name: string; root_path: string }>>([]);
  let chosen = $state(new Set<number>());
  let folderQuery = $state('');

  async function load() {
    try {
      reviews = await apiGetData<Review[]>(fetch, '/access-reviews');
    } catch (failure) {
      error = failure instanceof Error ? failure.message : t('Unable to load the reviews.');
    }
  }
  onMount(load);

  async function openForm() {
    opening = true;
    if (!folders.length) folders = await apiGetList<(typeof folders)[number]>(fetch, '/storage-roots/context').catch(() => []);
  }
  async function create() {
    if (creating || !name.trim() || (scope === 'some' && !chosen.size)) return;
    creating = true;
    try {
      const result = await apiPostData<{ id: number; items: number; folders: number; guardians_notified: number }>(fetch, '/access-reviews', {
        name: name.trim(), due_at: due ? `${due}T23:59:00Z` : null, root_ids: scope === 'some' ? [...chosen] : null });
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
  const pct = (review: Review) => (review.total ? Math.round((review.decided / review.total) * 100) : 0);
  let shownFolders = $derived(folders.filter((row) => !folderQuery.trim() || `${row.storage_root_name} ${row.root_path}`.toLowerCase().includes(folderQuery.trim().toLowerCase())));
</script>

<section class="v2 rv">
  <div class="v2-head">
    <div>
      <h1>{t('Access reviews')}</h1>
      <p>{t('At a given time, every person who reaches a folder is listed for its guardians, who keep or remove each access. The closed review is the evidence of the control.')}</p>
    </div>
    {#if isAdmin}<div class="v2-head__act"><button type="button" class="b2s-btn b2s-btn-primary" onclick={openForm}><i class="bi bi-plus-lg" aria-hidden="true"></i>{t('New review')}</button></div>{/if}
  </div>

  {#if error}
    <p class="v2-empty">{error}</p>
  {:else if !reviews}
    <LoadingState block skeleton="rows" rows={4} />
  {:else}
    <div class="v2-list">
      {#each reviews as review (review.id)}
        <a class="v2-row rv__row" href={`/access-reviews/${review.id}`}>
          <span class="v2-nm"><b>{review.name}</b>
            <span class="v2-sub">{t('{folders} folder(s) · opened {date} by {who}', { folders: review.folders, date: formatDate(review.created_at), who: review.created_by ?? '—' })}{review.due_at ? ` · ${t('until {date}', { date: formatDate(review.due_at) })}` : ''}</span></span>
          <span class="rv__progress"><span class="v2-bar is-accent"><i style={`width:${pct(review)}%`}></i></span>
            <small>{t('{done} / {total} reviewed', { done: review.decided, total: review.total })}</small></span>
          <span class="v2-sub">{t('{keep} kept · {revoke} removed', { keep: review.keep, revoke: review.revoke })}{review.manual ? ` · ${t('{count} by hand', { count: review.manual })}` : ''}</span>
          <span><span class={`v2-tag is-${review.status === 'open' ? (review.due_at && new Date(review.due_at).getTime() < Date.now() ? 'bad' : 'info') : 'ok'}`}>
            {review.status === 'open' ? (review.due_at && new Date(review.due_at).getTime() < Date.now() ? t('Overdue') : t('In progress')) : t('Closed')}</span></span>
        </a>
      {:else}
        <p class="v2-empty">{isAdmin ? t('No review yet: open the first one to have every access checked by the guardians.') : t('No review of your folders for now.')}</p>
      {/each}
    </div>
  {/if}
</section>

<AppModal open={opening} onClose={() => (opening = false)} size="md" title={t('New access review')}>
  <form class="rv__form" onsubmit={(event) => { event.preventDefault(); void create(); }}>
    <label>{t('Name')}<input class="b2s-input" bind:value={name} maxlength="190" required /></label>
    <label>{t('To finish by')}<input class="b2s-input" type="date" bind:value={due} /></label>
    <fieldset>
      <legend>{t('Folders')}</legend>
      <label class="rv__check"><input type="radio" bind:group={scope} value="all" /> {t('Every governed folder')}</label>
      <label class="rv__check"><input type="radio" bind:group={scope} value="some" /> {t('Some folders')}</label>
      {#if scope === 'some'}
        <input class="b2s-input" placeholder={t('Search a folder…')} bind:value={folderQuery} aria-label={t('Search a folder')} />
        <div class="rv__folders">
          {#each shownFolders.slice(0, 200) as row (row.storage_root_id)}
            <label class="rv__check"><input type="checkbox" checked={chosen.has(row.storage_root_id)}
              onchange={(event) => { const next = new Set(chosen); if ((event.currentTarget as HTMLInputElement).checked) next.add(row.storage_root_id); else next.delete(row.storage_root_id); chosen = next; }} />
              {row.storage_root_name} <small>{row.root_path}</small></label>
          {/each}
        </div>
        <small>{t('{count} folder(s) chosen', { count: chosen.size })}</small>
      {/if}
    </fieldset>
    <p class="rv__hint">{t('The guardians are told (bell, and e-mail when it is switched on). The list is the one of today: a person who gets an access later is not in this review.')}</p>
    <div class="rv__btns">
      <button type="button" class="b2s-btn b2s-btn-secondary" onclick={() => (opening = false)}>{t('Cancel')}</button>
      <button type="submit" class="b2s-btn b2s-btn-primary" disabled={creating || (scope === 'some' && !chosen.size)}><i class="bi bi-check2" aria-hidden="true"></i>{t('Open the review')}</button>
    </div>
  </form>
</AppModal>

<style>
  .rv { display: grid; gap: 18px; padding: var(--b2s-page-padding); }
  .rv__row { grid-template-columns: minmax(260px, 2fr) minmax(180px, 1fr) minmax(160px, 1fr) 110px; color: inherit; text-decoration: none; }
  .rv__progress { display: grid; gap: 4px; }
  .rv__progress small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .rv__form { display: grid; gap: 12px; }
  .rv__form > label { display: grid; gap: 4px; font-size: var(--b2s-fs-sm); font-weight: 500; }
  .rv__form fieldset { display: grid; gap: 6px; margin: 0; padding: 10px 12px; border: 1px solid var(--b2s-color-border); border-radius: 12px; }
  .rv__form legend { padding: 0 6px; font-size: var(--b2s-fs-sm); font-weight: 600; }
  .rv__check { display: flex; gap: 8px; align-items: center; font-size: var(--b2s-fs-sm); }
  .rv__check small { color: var(--b2s-color-text-muted); }
  .rv__folders { display: grid; gap: 4px; max-height: 240px; overflow: auto; }
  .rv__hint { margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .rv__btns { display: flex; justify-content: flex-end; gap: 8px; }
</style>
