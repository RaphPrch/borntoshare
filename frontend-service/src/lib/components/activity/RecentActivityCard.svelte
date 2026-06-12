<script lang="ts">
  import { formatActivityItem } from '$lib/activity/format';
  import { timeAgo } from '$lib/utils/timeAgo';

  export let title = 'Recent activity';
  export let items: any[] = [];
  export let max: number | null = 5;
  export let emptyLabel = 'No recent activity';
  export let emptyText = 'Activity related to this item will appear here.';
  export let onViewAll: (() => void) | null = null;
  export let onSelect: ((entry: any) => void) | null = null;

  const iconTone = (rendered: ReturnType<typeof formatActivityItem>) => {
    if (rendered.badgeKind === 'critical') return 'critical';
    if (rendered.badgeKind === 'admin') return 'warning';
    if (rendered.variant === 'ok') return 'success';
    if (rendered.variant === 'warn') return 'warning';
    return 'info';
  };

  $: visible = max === null ? (Array.isArray(items) ? items : []) : (Array.isArray(items) ? items : []).slice(0, max);
</script>

<article class="activity-summary-card">
  <div class="activity-summary-card__head">
    <h2>{title}</h2>
    {#if onViewAll}
      <button type="button" class="activity-summary-card__link" on:click={() => onViewAll?.()}>
        View all activity
      </button>
    {/if}
  </div>

  {#if visible.length === 0}
    <div class="activity-summary-card__empty">
      <strong>{emptyLabel}</strong>
      <span>{emptyText}</span>
    </div>
  {:else}
    <div class="activity-summary-card__list">
      {#each visible as entry, idx (entry.id ?? `${entry.created_at ?? entry.event_time ?? entry.timestamp ?? ''}-${idx}`)}
        {@const rendered = formatActivityItem(entry)}
        {#if onSelect}
          <button type="button" class="activity-summary-card__row is-clickable" on:click={() => onSelect?.(entry)}>
            <span class={`activity-summary-card__icon is-${iconTone(rendered)}`} aria-hidden="true">
              <i class={`bi bi-${rendered.icon ?? 'info-circle'}`}></i>
            </span>
            <span class="activity-summary-card__copy">
              <strong>{rendered.title ?? String(entry.action ?? 'Activity')}</strong>
              <small>{rendered.subtitle1 ?? String(entry.actor_display_name ?? entry.actor_name ?? 'System')}</small>
            </span>
            <time>{timeAgo(entry.created_at ?? entry.event_time ?? entry.timestamp ?? null) || '—'}</time>
            <span class="activity-summary-card__actor">{String(entry.actor_display_name ?? entry.actor_name ?? entry.actor_display ?? 'System')}</span>
          </button>
        {:else}
        <div class="activity-summary-card__row">
          <span class={`activity-summary-card__icon is-${iconTone(rendered)}`} aria-hidden="true">
            <i class={`bi bi-${rendered.icon ?? 'info-circle'}`}></i>
          </span>
          <span class="activity-summary-card__copy">
            <strong>{rendered.title ?? String(entry.action ?? 'Activity')}</strong>
            <small>{rendered.subtitle1 ?? String(entry.actor_display_name ?? entry.actor_name ?? 'System')}</small>
          </span>
          <time>{timeAgo(entry.created_at ?? entry.event_time ?? entry.timestamp ?? null) || '—'}</time>
          <span class="activity-summary-card__actor">{String(entry.actor_display_name ?? entry.actor_name ?? entry.actor_display ?? 'System')}</span>
        </div>
        {/if}
      {/each}
    </div>
  {/if}

</article>

<style>
  .activity-summary-card {
    min-width: 0;
    min-height: 166px;
    border: 1px solid #dfe7f3;
    border-radius: 8px;
    background: #fff;
    padding: 16px 18px;
    box-shadow: 0 12px 30px rgba(15, 23, 42, 0.025);
    display: grid;
    align-content: start;
  }

  .activity-summary-card__head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 8px;
  }

  .activity-summary-card__head h2 {
    margin: 0;
    color: #0f1f3d;
    font-size: 14px;
    font-weight: 700;
    letter-spacing: 0;
    display: inline-flex;
    align-items: center;
    gap: 9px;
  }

  .activity-summary-card__empty {
    min-height: 78px;
    display: grid;
    place-content: center;
    gap: 4px;
    text-align: center;
    color: #637493;
  }

  .activity-summary-card__empty strong {
    color: #637493;
    font-size: 14px;
    font-weight: 600;
  }

  .activity-summary-card__empty span {
    font-size: 13px;
  }

  .activity-summary-card__list {
    display: grid;
  }

  .activity-summary-card__row {
    min-width: 0;
    width: 100%;
    display: grid;
    grid-template-columns: 24px minmax(0, 1fr) minmax(130px, auto) minmax(72px, auto);
    gap: 12px;
    align-items: center;
    border: 0;
    border-top: 1px solid #edf1f7;
    border-radius: 0;
    background: #fff;
    padding: 10px 0;
    text-align: left;
  }

  .activity-summary-card__row:last-child {
    border-bottom: 1px solid #edf1f7;
  }

  .activity-summary-card__row.is-clickable:hover {
    border-color: #d5e3fb;
    background: #f7faff;
  }

  .activity-summary-card__icon {
    width: 22px;
    height: 22px;
    border-radius: 999px;
    display: inline-grid;
    place-items: center;
    font-size: 14px;
    line-height: 1;
  }

  .activity-summary-card__icon i {
    display: block;
    line-height: 1;
  }

  .activity-summary-card__icon.is-critical {
    color: #ef3340;
  }

  .activity-summary-card__icon.is-warning {
    color: #f5a524;
  }

  .activity-summary-card__icon.is-success {
    color: #12a365;
  }

  .activity-summary-card__icon.is-info,
  .activity-summary-card__icon.is-sync,
  .activity-summary-card__icon.is-neutral,
  .activity-summary-card__icon.is-access {
    color: var(--b2s-topbar-bg, #111b3f);
  }

  .activity-summary-card__copy,
  .activity-summary-card__copy strong,
  .activity-summary-card__copy small {
    display: block;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .activity-summary-card__copy strong {
    color: #142747;
    font-size: 13px;
    font-weight: 650;
  }

  .activity-summary-card__copy small,
  .activity-summary-card__row time,
  .activity-summary-card__actor {
    color: #687a98;
    font-size: 12px;
  }

  .activity-summary-card__row time,
  .activity-summary-card__actor {
    text-align: right;
    white-space: nowrap;
  }

  .activity-summary-card__link {
    justify-self: end;
    border: none;
    background: transparent;
    color: var(--b2s-topbar-bg, #111b3f);
    font-size: 14px;
    font-weight: 650;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 0;
    text-decoration: none;
  }

  .activity-summary-card__link:hover {
    color: #174a9e;
  }
</style>
