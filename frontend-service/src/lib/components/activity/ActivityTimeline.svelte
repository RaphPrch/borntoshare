<script lang="ts">
  import ShowMore from '$lib/components/ui/ShowMore.svelte';
  import { t } from '$lib/i18n';
  import { formatDate, formatDateTime, initials } from '$lib/utils/format';
  import { formatActivityItem } from '$lib/activity/format';
  import { activitySummary, categoryOf, changedValues, eventTime, groupByDay, dayKey, type ActivityCategory } from '$lib/activity/timeline';

  /**
   * Activity of an entity (folder, zone, server): four figures of the last 30 days, a timeline grouped
   * by day with one icon per category, filters in one click, and the detail of an event on the side.
   */
  export let items: any[] = [];
  export let emptyLabel = t('No activity yet.');

  type Period = '1' | '7' | '30' | 'all';
  type Filter = 'all' | ActivityCategory;
  const PAGE = 30;

  const CATEGORY: Record<ActivityCategory, { label: () => string; icon: string }> = {
    access: { label: () => t('Access'), icon: 'bi-key' },
    config: { label: () => t('Configuration'), icon: 'bi-sliders' },
    check: { label: () => t('Checks'), icon: 'bi-arrow-repeat' },
    failure: { label: () => t('Failures'), icon: 'bi-exclamation-triangle' }
  };

  let query = '';
  let filter: Filter = 'all';
  let period: Period = '30';
  let shown = PAGE;
  let selected: any | null = null;

  const actorOf = (entry: any): string => {
    const name = String(entry?.actor_display_name ?? entry?.actor_display ?? entry?.actor_username ?? entry?.actor_name ?? '').trim();
    return !name || name.toLowerCase() === 'system' ? t('System') : name;
  };

  $: rows = items.map((entry, index) => {
    const item = formatActivityItem(entry);
    return { key: String(entry?.id ?? index), entry, item, ms: eventTime(entry), category: categoryOf(entry), actor: actorOf(entry) };
  });
  $: summary = activitySummary(items);
  $: since = period === 'all' ? 0 : Date.now() - Number(period) * 86_400_000;
  $: inPeriod = rows.filter((row) => period === 'all' || (row.ms ?? 0) >= since);
  $: counts = {
    all: inPeriod.length,
    access: inPeriod.filter((row) => row.category === 'access').length,
    config: inPeriod.filter((row) => row.category === 'config').length,
    check: inPeriod.filter((row) => row.category === 'check').length,
    failure: inPeriod.filter((row) => row.category === 'failure').length
  };
  $: visible = inPeriod
    .filter((row) => filter === 'all' || row.category === filter)
    .filter((row) => !query.trim() || `${row.item.title} ${row.item.subtitle1 ?? ''} ${row.actor}`.toLowerCase().includes(query.trim().toLowerCase()));
  $: days = groupByDay(visible.slice(0, shown));
  $: if (filter || period || query !== undefined) shown = PAGE;
  $: authors = [...visible.reduce((map, row) => map.set(row.actor, (map.get(row.actor) ?? 0) + 1), new Map<string, number>())]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);

  const today = dayKey(Date.now());
  const yesterday = dayKey(Date.now() - 86_400_000);
  const dayLabel = (key: string, ms: number | null) =>
    key === today ? t('Today') : key === yesterday ? t('Yesterday') : ms ? formatDate(new Date(ms).toISOString()) : t('Unknown date');
  const hour = (ms: number | null) => (ms ? new Date(ms).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '');

  $: detail = selected ? rows.find((row) => row.entry === selected) ?? null : null;
  $: changes = detail ? changedValues(detail.entry) : [];
  const safeContext = (entry: any) => {
    const ctx = entry?.context_json && typeof entry.context_json === 'object' ? entry.context_json : {};
    return JSON.stringify(ctx, (key, value) => (/secret|password|hash/i.test(key) ? undefined : value), 2);
  };
</script>

<div class="at">
  <section class="at__sum" aria-label={t('Last 30 days')}>
    <div><span>{t('Accesses granted · 30 d')}</span><b>{summary.granted}</b></div>
    <div><span>{t('Accesses removed · 30 d')}</span><b>{summary.revoked}</b></div>
    <div><span>{t('Configuration changes · 30 d')}</span><b>{summary.config}</b></div>
    <div><span>{t('Failures · 30 d')}</span><b class:bad={summary.failures > 0}>{summary.failures}</b></div>
  </section>

  <div class="at__grid">
    <section class="at__card" aria-label={t('Activity')}>
      <div class="at__tools">
        <label class="at__search"><i class="bi bi-search" aria-hidden="true"></i><input type="search" bind:value={query} placeholder={t('Search the activity…')} aria-label={t('Search the activity…')} /></label>
        <div class="at__seg" role="group" aria-label={t('Filter by type')}>
          <button type="button" class:on={filter === 'all'} on:click={() => (filter = 'all')}>{t('All')}<span>{counts.all}</span></button>
          {#each Object.entries(CATEGORY) as [key, category] (key)}
            {#if counts[key] > 0}
              <button type="button" class:on={filter === key} on:click={() => (filter = key as Filter)}>{category.label()}<span>{counts[key]}</span></button>
            {/if}
          {/each}
        </div>
        <div class="at__seg at__period" role="group" aria-label={t('Period')}>
          {#each [['1', t('24 h')], ['7', t('7 d')], ['30', t('30 d')], ['all', t('All')]] as [key, label] (key)}
            <button type="button" class:on={period === key} on:click={() => (period = key as Period)}>{label}</button>
          {/each}
        </div>
      </div>

      {#if days.length}
        {#each days as day (day.key)}
          <h3 class="at__day">{dayLabel(day.key, day.ms)}</h3>
          <ol class="at__list">
            {#each day.rows as row (row.key)}
              <li>
                <button type="button" class="at__ev" class:sel={selected === row.entry} on:click={() => (selected = row.entry)}>
                  <span class={`at__icon is-${row.category}`} aria-hidden="true"><i class={`bi ${CATEGORY[row.category].icon}`}></i></span>
                  <span class="at__body">
                    <strong>{row.item.title}</strong>
                    {#if row.item.subtitle1}<small>{row.item.subtitle1}</small>{/if}
                    <span class="at__actor"><span class="at__face">{initials(row.actor)}</span>{row.actor}</span>
                  </span>
                  <span class="at__time">{hour(row.ms)}</span>
                </button>
              </li>
            {/each}
          </ol>
        {/each}
        {#if visible.length > shown}
          <ShowMore {shown} total={visible.length} page={PAGE} onMore={() => (shown += PAGE)} />
        {/if}
      {:else}
        <p class="at__empty">{items.length ? t('No event matches these filters.') : emptyLabel}</p>
      {/if}
    </section>

    <div class="at__side">
      <section class="at__card" aria-label={t('Detail')}>
        <h2>{t('Detail')}</h2>
        {#if detail}
          <div class="at__detail">
            <strong>{detail.item.title}</strong>
            {#if detail.item.subtitle1}<p>{detail.item.subtitle1}</p>{/if}
            <small>{detail.ms ? formatDateTime(new Date(detail.ms).toISOString()) : ''} · {detail.actor}</small>
            {#if changes.length}
              <table>
                <thead><tr><th>{t('Field')}</th><th>{t('Before')}</th><th>{t('After')}</th></tr></thead>
                <tbody>{#each changes as change (change.key)}<tr><td>{change.key}</td><td>{change.before}</td><td>{change.after}</td></tr>{/each}</tbody>
              </table>
            {/if}
            <details>
              <summary>{t('Raw context')}</summary>
              <pre>{safeContext(detail.entry)}</pre>
            </details>
          </div>
        {:else}
          <p class="at__muted">{t('Click an event to see who did what, and the values before and after.')}</p>
        {/if}
      </section>
      {#if authors.length}
        <section class="at__card" aria-label={t('Authors')}>
          <h2>{t('Authors')}</h2>
          {#each authors as [name, count] (name)}
            <div class="at__author"><span class="at__face is-lg">{initials(name)}</span><span><b>{name}</b><small>{t('{count} event(s)', { count })}</small></span></div>
          {/each}
        </section>
      {/if}
    </div>
  </div>
</div>

<style>
  .at { display: flex; flex-direction: column; gap: 14px; }
  .at__sum { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
  .at__sum div { padding: 10px 14px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .at__sum span { display: block; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .at__sum b { font-size: 22px; font-weight: 600; }
  .at__sum b.bad { color: var(--b2s-color-danger-strong); }
  .at__grid { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(280px, 1fr); gap: 14px; align-items: start; }
  .at__side { display: flex; flex-direction: column; gap: 14px; min-width: 0; position: sticky; top: 16px; }
  .at__card { display: flex; flex-direction: column; gap: 10px; min-width: 0; padding: 16px 18px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .at__card h2 { margin: 0; font-size: var(--b2s-fs-md); font-weight: 600; }
  .at__tools { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .at__search { display: flex; align-items: center; gap: 6px; flex: 1; min-width: 160px; max-width: 240px; height: 34px; padding: 0 10px; border: 1px solid var(--b2s-color-border-mid, var(--b2s-color-border)); border-radius: var(--b2s-radius-md); }
  .at__search input { flex: 1; min-width: 0; border: 0; outline: 0; background: none; font: inherit; font-size: var(--b2s-fs-sm); }
  .at__seg { display: flex; gap: 2px; padding: 3px; border-radius: var(--b2s-radius-md); background: var(--b2s-color-neutral-soft); }
  .at__seg button { padding: 4px 10px; border: 0; border-radius: var(--b2s-radius-sm); background: none; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); white-space: nowrap; cursor: pointer; }
  .at__seg button.on { background: var(--b2s-color-surface); color: var(--b2s-color-text); font-weight: 600; }
  .at__seg span { margin-left: 5px; opacity: 0.7; }
  .at__period { margin-left: auto; }
  .at__day { margin: 8px 0 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; }
  .at__list { position: relative; margin: 0; padding: 0; list-style: none; }
  .at__list li { position: relative; }
  .at__list li::before { content: ''; position: absolute; top: 0; bottom: 0; left: 16px; width: 2px; background: var(--b2s-color-border); }
  .at__list li:first-child::before { top: 20px; }
  .at__list li:last-child::before { bottom: calc(100% - 20px); }
  .at__list li:only-child::before { display: none; }
  .at__ev { display: grid; grid-template-columns: 34px minmax(0, 1fr) auto; gap: 12px; width: 100%; padding: 8px 6px 8px 0; border: 0; border-radius: var(--b2s-radius-md); background: none; color: inherit; font: inherit; text-align: left; cursor: pointer; }
  .at__ev:hover .at__body, .at__ev.sel .at__body { background: var(--b2s-color-surface-soft, #f6f7f9); }
  .at__ev.sel .at__body { box-shadow: inset 0 0 0 1px var(--b2s-color-border-mid, #cdd2db); }
  .at__icon { position: relative; z-index: 1; display: grid; place-items: center; width: 34px; height: 34px; border-radius: 10px; font-size: 15px; }
  .at__icon.is-access { background: var(--b2s-color-success-soft); color: var(--b2s-color-success-strong); }
  .at__icon.is-config { background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); }
  .at__icon.is-check { background: var(--b2s-color-neutral-soft); color: var(--b2s-color-text-muted); }
  .at__icon.is-failure { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger-strong); }
  .at__body { display: flex; flex-direction: column; gap: 1px; min-width: 0; margin: -2px 0; padding: 2px 8px; border-radius: var(--b2s-radius-md); }
  .at__body strong { font-weight: 600; font-size: var(--b2s-fs-sm); }
  .at__body small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); overflow-wrap: anywhere; }
  .at__actor { display: inline-flex; align-items: center; gap: 6px; margin-top: 4px; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .at__face { display: inline-grid; place-items: center; width: 20px; height: 20px; border-radius: 50%; background: var(--b2s-color-neutral-soft); color: var(--b2s-color-text); font-size: 9px; font-weight: 700; }
  .at__face.is-lg { width: 30px; height: 30px; font-size: 11px; }
  .at__time { padding-top: 2px; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); white-space: nowrap; }
  .at__empty, .at__muted { margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .at__empty { padding: 20px; text-align: center; }
  .at__detail { display: flex; flex-direction: column; gap: 6px; }
  .at__detail strong { font-size: var(--b2s-fs-sm); }
  .at__detail p { margin: 0; font-size: var(--b2s-fs-sm); }
  .at__detail small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .at__detail table { width: 100%; border-collapse: collapse; font-size: var(--b2s-fs-xs); }
  .at__detail th { text-align: left; color: var(--b2s-color-text-muted); font-weight: 500; padding: 4px 6px; border-bottom: 1px solid var(--b2s-color-border); }
  .at__detail td { padding: 4px 6px; border-bottom: 1px solid var(--b2s-color-border); overflow-wrap: anywhere; }
  .at__detail summary { cursor: pointer; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .at__detail pre { max-height: 240px; margin: 6px 0 0; padding: 10px; overflow: auto; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-md); background: var(--b2s-color-surface-soft, #f6f7f9); font-family: var(--b2s-font-mono); font-size: 11px; white-space: pre-wrap; }
  .at__author { display: flex; align-items: center; gap: 10px; }
  .at__author b { display: block; font-weight: 500; font-size: var(--b2s-fs-sm); }
  .at__author small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
</style>
