<script lang="ts">
  import { t } from '$lib/i18n';
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import type { StatusVariant } from '$lib/utils/status';

  type AssociatedRootRow = {
    id: number;
    name: string;
    path: string;
    pendingCount: number | null;
    /** Result of the last check of the root: healthy | degraded | unhealthy | unknown */
    health?: string | null;
    alertCount?: number;
  };

  export let rows: AssociatedRootRow[] = [];
  export let dense = false;
  export let emptyLabel = t('No associated roots');

  function state(row: AssociatedRootRow): { label: string; variant: StatusVariant } {
    if (row.health === 'unhealthy') return { label: t('Unreachable'), variant: 'error' };
    if (row.alertCount) return { label: t('{count} alert(s)', { count: row.alertCount }), variant: 'warning' };
    if (row.health === 'degraded') return { label: t('Needs review'), variant: 'warning' };
    if (row.health === 'healthy') return { label: t('OK'), variant: 'success' };
    return { label: t('Not checked'), variant: 'muted' };
  }
</script>

<div class={`sed-table-wrap ${dense ? 'is-dense' : ''}`}>
  <table class="b2s-table sed-table">
    <thead>
      <tr>
        <th>{t('Storage root')}</th>
        <th class="sed-col-state">{t('State')}</th>
        <th class="sed-col-requests">{t('Pending requests')}</th>
      </tr>
    </thead>
    <tbody>
      {#if rows.length === 0}
        <tr>
          <td colspan="3" class="sed-empty-row">{emptyLabel}</td>
        </tr>
      {:else}
        {#each rows as row (row.id)}
          {@const s = state(row)}
          <tr>
            <td>
              <a class="sed-root-link" href={`/storage-roots?selected=${row.id}`}>
                <i class="bi bi-folder2" aria-hidden="true"></i>{row.name}
              </a>
              <small class="sed-root-path">{row.path}</small>
            </td>
            <td><StatusBadge compact variant={s.variant} label={s.label} /></td>
            <td class="sed-col-requests">
              {#if row.pendingCount}
                <a class="sed-pending" href="/access-requests?status=pending">{row.pendingCount}</a>
              {:else}
                <span class="sed-none">—</span>
              {/if}
            </td>
          </tr>
        {/each}
      {/if}
    </tbody>
  </table>
</div>

<style>
  .sed-root-link {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-weight: 600;
  }

  .sed-root-path {
    display: block;
    margin-top: 2px;
    color: var(--b2s-color-text-muted);
    font-family: var(--b2s-font-mono);
    font-size: var(--b2s-fs-xs);
    overflow-wrap: anywhere;
  }

  .sed-col-state {
    width: 150px;
  }

  .sed-col-requests {
    width: 140px;
    text-align: right;
  }

  .sed-pending {
    display: inline-block;
    min-width: 24px;
    padding: 0 8px;
    border-radius: var(--b2s-radius-pill);
    background: var(--b2s-color-warning-soft);
    color: var(--b2s-color-warning-strong);
    font-weight: 600;
    text-align: center;
  }

  .sed-none {
    color: var(--b2s-color-text-faint);
  }
</style>
