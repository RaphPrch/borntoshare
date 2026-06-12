<script lang="ts">
  import { formatActivityItem } from '$lib/activity/format';

  export let items: any[] = [];
  export let max: number | null = null;
  export let compact = false;
  export let onSelect: ((entry: any) => void) | null = null;

  const keyOf = (e: any) => e?.id ?? `${e?.created_at ?? e?.event_time}-${e?.action}`;

  const openDetails = (entry: any) => {
    onSelect?.(entry);
  };
</script>

<div class={"b2s-activity " + (compact ? "b2s-activity--compact" : "")}>
  {#if items.length === 0}
    <div class="text-muted">No activity yet.</div>
  {:else}
    {#each (max ? items.slice(0, max) : items) as entry (keyOf(entry))}
      {@const r = formatActivityItem(entry)}
      {#if onSelect}
        <button
          type="button"
          class="b2s-activity__row is-clickable"
          on:click={() => openDetails(entry)}
        >
          <div class="b2s-activity__dot {r.badgeKind === 'critical' ? 'is-critical' : r.badgeKind === 'admin' ? 'is-admin' : 'is-info'}"></div>

          <div class="b2s-activity__body">
            <div class="b2s-activity__headline">
              <span class="fw-semibold">{r.title}</span>
              {#if r.badgeLabel}
                <span class={r.badgeClass ?? 'b2s-badge b2s-badge--info'}>{r.badgeLabel}</span>
              {/if}
            </div>

            {#if r.subtitle1}
              <div class="small text-muted">{r.subtitle1}</div>
            {/if}
          </div>

          <div class="b2s-activity__chev text-muted">›</div>
        </button>
      {:else}
        <article class="b2s-activity__row">
          <div class="b2s-activity__dot {r.badgeKind === 'critical' ? 'is-critical' : r.badgeKind === 'admin' ? 'is-admin' : 'is-info'}"></div>

          <div class="b2s-activity__body">
            <div class="b2s-activity__headline">
              <span class="fw-semibold">{r.title}</span>
              {#if r.badgeLabel}
                <span class={r.badgeClass ?? 'b2s-badge b2s-badge--info'}>{r.badgeLabel}</span>
              {/if}
            </div>

            {#if r.subtitle1}
              <div class="small text-muted">{r.subtitle1}</div>
            {/if}
          </div>

          <div class="b2s-activity__chev text-muted"></div>
        </article>
      {/if}
    {/each}
  {/if}
</div>
