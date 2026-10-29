<script lang="ts">
  import { t } from '$lib/i18n';
  import EntityActionGroup, { type EntityActionItem } from './EntityActionGroup.svelte';

  /** Header of an entity page, without a card: breadcrumb, name, one status pill, actions, a code or path. */
  export let crumbs: string[] = [];
  export let title = '';
  export let statusLabel = '';
  export let statusTone: 'success' | 'warning' | 'danger' | 'neutral' = 'neutral';
  /** UNC path, zone code… */
  export let code = '';
  export let actions: EntityActionItem[] = [];
  export let actionsAriaLabel = t('Entity actions');
</script>

<header class="eph">
  {#if crumbs.length}
    <nav class="eph__crumbs" aria-label={t('Location')}>
      {#each crumbs as crumb, index}
        {#if index}<i class="bi bi-chevron-right" aria-hidden="true"></i>{/if}<span>{crumb}</span>
      {/each}
    </nav>
  {/if}
  <div class="eph__row">
    <h1>{title}</h1>
    {#if statusLabel}
      <span class={`eph__pill is-${statusTone}`}><span aria-hidden="true"></span>{statusLabel}</span>
    {/if}
    <div class="eph__actions">
      <EntityActionGroup {actions} ariaLabel={actionsAriaLabel} />
    </div>
  </div>
  {#if code}<code class="eph__code">{code}</code>{/if}
</header>

<style>
  .eph {
    display: grid;
    gap: 8px;
  }

  .eph__crumbs {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
  }

  .eph__crumbs i {
    font-size: 10px;
  }

  .eph__row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 12px;
  }

  h1 {
    margin: 0;
    font-size: var(--b2s-fs-page-title);
    font-weight: 700;
    letter-spacing: -0.01em;
    overflow-wrap: anywhere;
  }

  .eph__pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 10px;
    border-radius: var(--b2s-radius-pill);
    font-size: var(--b2s-fs-xs);
    font-weight: 600;
  }

  .eph__pill span {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: currentColor;
  }

  .eph__pill.is-success { background: var(--b2s-color-success-soft); color: var(--b2s-color-success-strong); }
  .eph__pill.is-warning { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .eph__pill.is-danger { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger-strong); }
  .eph__pill.is-neutral { background: var(--b2s-color-neutral-soft); color: var(--b2s-color-text-muted); }

  .eph__actions {
    margin-left: auto;
  }

  .eph__code {
    justify-self: start;
    max-width: 100%;
    padding: 3px 8px;
    border-radius: 6px;
    background: var(--b2s-color-neutral-soft);
    color: var(--b2s-color-text-soft);
    font-family: var(--b2s-font-mono);
    font-size: var(--b2s-fs-xs);
    overflow-wrap: anywhere;
  }
</style>
