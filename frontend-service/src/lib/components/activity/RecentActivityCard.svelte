<script lang="ts">
  import { t } from '$lib/i18n';
  import { formatActivityItem } from '$lib/activity/format';
  import { timeAgo } from '$lib/utils/format';

  export let title = t('Recent activity');
  export let items: any[] = [];
  export let max: number | null = 5;
  export let emptyLabel = t('No recent activity');
  export let emptyText = t('Activity related to this item will appear here.');
  export let onViewAll: (() => void) | null = null;
  export let onSelect: ((entry: any) => void) | null = null;

  const iconTone = (rendered: ReturnType<typeof formatActivityItem>) => {
    if (rendered.badgeKind === 'critical') return 'critical';
    if (rendered.badgeKind === 'admin') return 'warning';
    if (rendered.variant === 'ok') return 'success';
    if (rendered.variant === 'warn') return 'warning';
    return 'info';
  };

  const actorOf = (entry: any): string =>
    String(entry.actor_display_name ?? entry.actor_name ?? entry.actor_display ?? t('System'));

  $: visible = max === null ? (Array.isArray(items) ? items : []) : (Array.isArray(items) ? items : []).slice(0, max);
</script>

<article class="b2s-panel activity-card">
  <div class="b2s-panel__head">
    <h2>{title}</h2>
    {#if onViewAll}
      <button type="button" class="b2s-panel__link" on:click={() => onViewAll?.()}>{t('View all')}</button>
    {/if}
  </div>

  {#if visible.length === 0}
    <div class="activity-card__empty">
      <strong>{emptyLabel}</strong>
      <span>{emptyText}</span>
    </div>
  {:else}
    <ul class="activity-card__list">
      {#each visible as entry, idx (entry.id ?? `${entry.created_at ?? entry.event_time ?? entry.timestamp ?? ''}-${idx}`)}
        {@const rendered = formatActivityItem(entry)}
        <li>
          <svelte:element
            this={onSelect ? 'button' : 'div'}
            type={onSelect ? 'button' : undefined}
            class="activity-card__row"
            class:is-clickable={Boolean(onSelect)}
            role={onSelect ? undefined : 'group'}
            on:click={() => onSelect?.(entry)}
          >
            <span class={`activity-card__icon is-${iconTone(rendered)}`} aria-hidden="true">
              <i class={`bi bi-${rendered.icon ?? 'info-circle'}`}></i>
            </span>
            <span class="activity-card__copy">
              <strong>{rendered.title ?? String(entry.action ?? t('Activity'))}</strong>
              {#if rendered.subtitle1}<small>{rendered.subtitle1}</small>{/if}
              <span class="activity-card__meta">
                {actorOf(entry)} · {timeAgo(entry.created_at ?? entry.event_time ?? entry.timestamp ?? null) || '—'}
              </span>
            </span>
          </svelte:element>
        </li>
      {/each}
    </ul>
  {/if}
</article>

<style>
  .activity-card__list {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .activity-card__list li + li {
    border-top: 1px solid #f1f5f9;
  }

  .activity-card__row {
    width: 100%;
    display: flex;
    align-items: flex-start;
    gap: 12px;
    padding: 12px 20px;
    border: none;
    background: transparent;
    color: inherit;
    text-align: left;
  }

  .activity-card__row.is-clickable {
    cursor: pointer;
  }

  .activity-card__row.is-clickable:hover {
    background: #f8fafc;
  }

  .activity-card__icon {
    width: 30px;
    height: 30px;
    flex: 0 0 auto;
    display: grid;
    place-items: center;
    border-radius: var(--b2s-radius-pill);
    font-size: var(--b2s-fs-md);
    background: #eaf2ff;
    color: #1d4ed8;
  }

  .activity-card__icon.is-success { background: #e8f8ef; color: #15803d; }
  .activity-card__icon.is-warning { background: #fff4e5; color: #c2410c; }
  .activity-card__icon.is-critical { background: #fdecec; color: #b91c1c; }

  .activity-card__copy {
    min-width: 0;
    display: grid;
    gap: 2px;
  }

  .activity-card__copy strong {
    font-size: var(--b2s-fs-sm);
    font-weight: 500;
    color: var(--b2s-color-text);
  }

  .activity-card__copy small {
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
    line-height: 1.4;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .activity-card__meta {
    color: #94a3b8;
    font-size: var(--b2s-fs-xs);
  }

  .activity-card__empty {
    display: grid;
    gap: 4px;
    padding: 20px;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-sm);
  }

  .activity-card__empty strong {
    color: var(--b2s-color-text);
    font-weight: 500;
  }
</style>
