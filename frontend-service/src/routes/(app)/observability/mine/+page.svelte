<script lang="ts">
  import SegmentedFilter from '$lib/components/ui/SegmentedFilter.svelte';
  import { t } from '$lib/i18n';
  import PageHeader from '$lib/components/ui/PageHeader.svelte';
  import EmptyStateInline from '$lib/components/ui/EmptyStateInline.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import { formatActivityItem } from '$lib/activity/format';
  import { formatDateTime } from '$lib/utils/format';

  export let data: { events: Record<string, any>[]; failed: boolean };

  let filter: 'all' | 'failed' = 'all';
  const isFailure = (event: Record<string, any>) => /fail|error|denied|refus/i.test(String(event.outcome ?? event.result ?? ''));
  $: shown = data.events.filter((event) => filter === 'all' || isFailure(event));
  $: failures = data.events.filter(isFailure).length;
</script>

<svelte:head><title>{t('Monitoring')} · BornToShare</title></svelte:head>

<section class="b2s-page mine">
  <PageHeader title={t('Monitoring')} subtitle={t('What happened to your requests, your accesses and the folders you guard.')}>
    <svelte:fragment slot="actions">
      <SegmentedFilter ariaLabel={t('Filter the events')} bind:value={filter} options={[
        { key: 'all', label: t('All'), count: data.events.length },
        { key: 'failed', label: t('Failures'), count: failures }
      ]} />
    </svelte:fragment>
  </PageHeader>

  {#if data.failed}<InlineAlert tone="warning">{t('The activity log cannot be read for now.')}</InlineAlert>{/if}

  <section class="panel">
    {#each shown as event (event.id)}
      {@const item = formatActivityItem(event as any)}
      <div class="line" class:line--bad={isFailure(event)}>
        <span class="main"><strong>{item.title ?? t('Event')}</strong>{#if item.subtitle1}<small>{item.subtitle1}</small>{/if}</span>
        <small>{event.actor_display_name ?? event.actor_display ?? ''}</small>
        <small>{formatDateTime(event.created_at ?? event.event_time)}</small>
      </div>
    {:else}
      <EmptyStateInline message={filter === 'failed' ? t('No failure.') : t('Nothing yet: your requests and their decisions appear here.')} />
    {/each}
  </section>
</section>

<style>
  .mine { display: flex; flex-direction: column; gap: 16px; padding: var(--b2s-page-padding); }
  .panel { padding: 6px 16px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .line { display: grid; grid-template-columns: minmax(0, 1fr) 180px 150px; gap: 12px; align-items: center; padding: 10px 0; border-top: 1px solid var(--b2s-color-border); }
  .line:first-child { border-top: 0; }
  .line--bad strong { color: var(--b2s-color-danger-strong); }
  .main { display: flex; flex-direction: column; min-width: 0; }
  .main strong { font-weight: 500; }
  .main small, .line > small { color: var(--b2s-color-text-muted); font-size: var(--b2s-font-micro); }
</style>
