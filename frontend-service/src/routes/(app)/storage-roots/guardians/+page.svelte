<script lang="ts">
  import { invalidate } from '$app/navigation';
  import { t } from '$lib/i18n';
  import { apiPostData } from '$lib/api/client';
  import GovernancePicker from '$lib/components/storage-roots/GovernancePicker.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';

  type Root = { id: number; name: string; path: string; zone: string; guardians: number };
  export let data: { roots: Root[]; people: { id: number; label: string; hint?: string }[]; minGuardians: number };

  const BATCH_SIZE = 25;

  let query = '';
  let checked = new Set<number>();
  let guardianIds: number[] = [];
  let running = false;
  let done = 0;
  let updatedCount: number | null = null;
  let failures: { name: string; message: string }[] = [];

  $: visible = data.roots.filter((root) => `${root.name} ${root.path} ${root.zone}`.toLowerCase().includes(query.trim().toLowerCase()));
  $: allChecked = visible.length > 0 && visible.every((root) => checked.has(root.id));
  // A folder keeps the guardians it has: what counts is the one with the fewest once these are added
  $: fewest = Math.min(...data.roots.filter((root) => checked.has(root.id)).map((root) => root.guardians), Number.POSITIVE_INFINITY);
  $: tooFew = guardianIds.length > 0 && checked.size > 0 && fewest + guardianIds.length < data.minGuardians;
  $: canApply = checked.size > 0 && guardianIds.length > 0 && !tooFew && !running;

  function toggle(id: number) {
    if (checked.has(id)) checked.delete(id);
    else checked.add(id);
    checked = checked;
  }

  function toggleAll() {
    const check = !allChecked;
    for (const root of visible) {
      if (check) checked.add(root.id);
      else checked.delete(root.id);
    }
    checked = checked;
  }

  async function apply() {
    if (!canApply) return;
    const ids = [...checked];
    running = true;
    done = 0;
    updatedCount = 0;
    failures = [];
    const nameOf = (id: number) => data.roots.find((root) => root.id === id)?.name ?? String(id);
    try {
      for (let start = 0; start < ids.length; start += BATCH_SIZE) {
        const batch = ids.slice(start, start + BATCH_SIZE);
        const answer = await apiPostData<{ updated: number[]; failed: { storage_root_id: number; message: string }[] }>(fetch, '/storage-roots/bulk-guardians', {
          root_ids: batch,
          guardian_ids: guardianIds
        });
        for (const id of answer.updated) checked.delete(id);
        updatedCount += answer.updated.length;
        failures = [...failures, ...answer.failed.map((row) => ({ name: nameOf(row.storage_root_id), message: t(row.message) }))];
        done += batch.length;
        checked = checked;
      }
    } catch (error) {
      failures = [...failures, { name: t('Interrupted'), message: error instanceof Error ? error.message : t('The server did not answer.') }];
    }
    running = false;
    await invalidate('app:storage-roots-guardians');
  }
</script>

<section class="page">
  <a class="crumb" href="/storage-roots"><i class="bi bi-chevron-left" aria-hidden="true"></i>{t('Folders')}</a>
  <h1>{t('Choose guardians')}</h1>
  <p class="lead">{t('{count} folder(s) do not have the {min} guardians required.', { count: data.roots.length, min: data.minGuardians })}</p>

  <div class="work">
    <section class="pane">
      <div class="head">
        <input class="b2s-input" aria-label={t('Filter the folders')} placeholder={t('Filter the folders…')} bind:value={query} />
        <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" disabled={!visible.length} on:click={toggleAll}>
          {allChecked ? t('Uncheck all') : t('Check {count}', { count: visible.length })}
        </button>
      </div>
      <div class="scroll">
        {#each visible as root (root.id)}
          <button type="button" class="line" class:sel={checked.has(root.id)} title={root.path} on:click={() => toggle(root.id)}>
            <span class="check" aria-hidden="true">{#if checked.has(root.id)}<i class="bi bi-check-lg"></i>{/if}</span>
            <span class="ell name">{root.name}</span>
            <span class="ell mono">{root.path}</span>
            <small class="ell">{root.zone}</small>
            <small>{t('{count} guardian(s)', { count: root.guardians })}</small>
          </button>
        {:else}
          <p class="note">{data.roots.length ? t('No folder matches this search.') : t('Every folder has its guardians.')}</p>
        {/each}
      </div>
    </section>

    <aside class="pane side">
      <div class="body">
        <h2>{t('Your selection')}</h2>
        <div><span class="big">{checked.size}</span> <span class="muted">{t('folder(s)')}</span></div>
        <GovernancePicker id="bulk-guardians" label={t('Guardians')} placeholder={t('Search a person…')} options={data.people} bind:selected={guardianIds} />
        <small class="muted">{t('They are added to the guardians the folders already have.')}</small>
        {#if tooFew}<small class="error">{t('With these people, a checked folder stays under the {min} guardians required.', { min: data.minGuardians })}</small>{/if}
        {#if updatedCount !== null && !running}
          <InlineAlert tone={failures.length ? 'warning' : 'success'}>{t('Updated: {updated}. Refused: {failed}.', { updated: updatedCount, failed: failures.length })}</InlineAlert>
        {/if}
        {#each failures as failure}<small class="muted"><b>{failure.name}</b> {failure.message}</small>{/each}
      </div>
      <div class="foot">
        <button type="button" class="b2s-btn b2s-btn-primary wide" disabled={!canApply} on:click={apply}>
          {running ? t('{done} of {total} folders', { done, total: done + checked.size }) : t('Apply to the checked folders')}
        </button>
      </div>
    </aside>
  </div>
</section>

<style>
  .page { padding: 20px 24px; }
  .crumb { display: inline-flex; align-items: center; gap: 4px; color: var(--b2s-color-text-muted); font-size: var(--b2s-text-sm); text-decoration: none; }
  h1 { margin: 2px 0 0; font-size: var(--b2s-fs-page-title); color: var(--b2s-color-heading); }
  .lead { margin: 2px 0 14px; color: var(--b2s-color-text-muted); }
  h2 { margin: 0; font-size: var(--b2s-fs-md); font-weight: 600; }
  .work { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 14px; height: calc(100vh - 130px); min-height: 480px; }
  .pane { display: flex; flex-direction: column; min-height: 0; overflow: hidden; background: var(--b2s-color-surface); border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); box-shadow: var(--b2s-shadow-sm); }
  .head { display: flex; gap: 8px; align-items: center; padding: 13px 14px; border-bottom: 1px solid var(--b2s-color-border); }
  .head .b2s-input { flex: 1; }
  .scroll { flex: 1; min-height: 0; overflow: auto; }
  .line { display: grid; grid-template-columns: 20px minmax(0, 1fr) minmax(0, 1.2fr) 110px 76px; gap: 12px; align-items: center; width: 100%; padding: 7px 14px; border: 0; border-bottom: 1px solid var(--b2s-color-border); background: var(--b2s-color-surface); text-align: left; font-size: var(--b2s-text-sm); cursor: pointer; }
  .line:hover { background: var(--b2s-color-surface-soft); }
  .line.sel { background: var(--b2s-accent-soft); }
  .line small, .muted { color: var(--b2s-color-text-muted); font-size: var(--b2s-font-micro); }
  .check { display: grid; place-items: center; width: 18px; height: 18px; border: 1.5px solid var(--b2s-color-border-mid); border-radius: 5px; font-size: 12px; }
  .sel .check { background: var(--b2s-accent-strong); border-color: var(--b2s-accent-strong); color: var(--b2s-on-accent); }
  .name { font-weight: 500; }
  .mono { font-family: var(--b2s-font-mono); font-size: var(--b2s-font-micro); color: var(--b2s-color-text-muted); }
  .ell { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .note { padding: 24px; text-align: center; color: var(--b2s-color-text-muted); }
  .body { flex: 1; min-height: 0; overflow: auto; display: flex; flex-direction: column; gap: 12px; padding: 15px; }
  .foot { padding: 13px 15px; border-top: 1px solid var(--b2s-color-border); }
  .wide { width: 100%; justify-content: center; }
  .big { font-size: 32px; font-weight: 600; line-height: 1; }
  .error { color: var(--b2s-color-danger-strong); font-size: var(--b2s-font-micro); }
</style>
