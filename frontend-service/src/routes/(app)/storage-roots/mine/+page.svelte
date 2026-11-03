<script lang="ts">
  import { t } from '$lib/i18n';
  import PageHeader from '$lib/components/ui/PageHeader.svelte';
  import EmptyStateInline from '$lib/components/ui/EmptyStateInline.svelte';
  import { formatDate } from '$lib/utils/format';

  type Access = {
    request_id: number;
    storage_root_name: string;
    target_path: string;
    permission: string;
    expires_at: string | null;
    created_at: string | null;
    requested_for: string;
    status: string;
  };
  export let data: { inForce: Access[]; waiting: Access[]; isAdmin: boolean };

  let query = '';
  const matches = (row: Access) => `${row.storage_root_name} ${row.target_path} ${row.requested_for}`.toLowerCase().includes(query.trim().toLowerCase());
  const access = (row: Access) => (row.permission.toLowerCase().includes('write') ? t('Modify') : t('Read'));
  $: inForce = data.inForce.filter(matches);
  $: waiting = data.waiting.filter(matches);
</script>

<svelte:head><title>{t('My folders')} · BornToShare</title></svelte:head>

<section class="b2s-page mine">
  <PageHeader title={t('My folders')} subtitle={t('The folders you reach through your requests.')}>
    <svelte:fragment slot="actions">
      <input class="b2s-input" aria-label={t('Search my folders')} placeholder={t('Search a folder…')} bind:value={query} />
      <a class="b2s-btn b2s-btn-primary" href="/access-requests/new"><i class="bi bi-plus-lg" aria-hidden="true"></i>{t('Request access')}</a>
    </svelte:fragment>
  </PageHeader>

  <section class="panel">
    <h2>{t('Accesses in force')} <span class="count">{inForce.length}</span></h2>
    {#each inForce as row (row.request_id)}
      <a class="line" href={`/access-requests?status=applied&request=${row.request_id}`}>
        <span class="main"><strong>{row.storage_root_name}</strong><small class="mono">{row.target_path}</small></span>
        <span class="pill" class:pill--write={access(row) === t('Modify')}>{access(row)}</span>
        <small>{row.requested_for ? t('For {name}', { name: row.requested_for }) : ''}</small>
        <small>{row.expires_at ? t('Ends on {date}', { date: formatDate(row.expires_at) }) : t('No end date')}</small>
      </a>
    {:else}
      <EmptyStateInline message={query ? t('No folder matches this search.') : t('You have no access in force yet: request one.')} />
    {/each}
  </section>

  {#if waiting.length || !query}
    <section class="panel">
      <h2>{t('Waiting for a decision')} <span class="count">{waiting.length}</span></h2>
      {#each waiting as row (row.request_id)}
        <a class="line" href={`/access-requests?status=pending&request=${row.request_id}`}>
          <span class="main"><strong>{row.storage_root_name}</strong><small class="mono">{row.target_path}</small></span>
          <span class="pill" class:pill--write={access(row) === t('Modify')}>{access(row)}</span>
          <small>{row.requested_for ? t('For {name}', { name: row.requested_for }) : ''}</small>
          <small>{t('Asked on {date}', { date: formatDate(row.created_at) })}</small>
        </a>
      {:else}
        <EmptyStateInline message={t('No request waiting.')} />
      {/each}
    </section>
  {/if}
</section>

<style>
  .mine { display: flex; flex-direction: column; gap: 16px; padding: var(--b2s-page-padding); }
  .mine :global(.b2s-input) { width: 260px; }
  .panel { padding: 14px 16px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  h2 { display: flex; align-items: center; gap: 8px; margin: 0 0 8px; font-size: var(--b2s-fs-lg); font-weight: 600; }
  .count { padding: 0 8px; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-neutral-soft); font-size: var(--b2s-font-micro); font-weight: 500; }
  .line { display: grid; grid-template-columns: minmax(0, 1fr) 90px 180px 150px; gap: 12px; align-items: center; padding: 9px 0; border-top: 1px solid var(--b2s-color-border); color: inherit; text-decoration: none; }
  .line:hover strong { text-decoration: underline; }
  .main { display: flex; flex-direction: column; min-width: 0; }
  .main strong { font-weight: 500; }
  .main small, .line > small { color: var(--b2s-color-text-muted); font-size: var(--b2s-font-micro); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .mono { font-family: var(--b2s-font-mono); }
  .pill { justify-self: start; padding: 1px 9px; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); font-size: var(--b2s-font-micro); font-weight: 500; }
  .pill--write { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
</style>
