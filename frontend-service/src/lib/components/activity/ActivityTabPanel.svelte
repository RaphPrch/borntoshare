<script lang="ts">
  import { t } from '$lib/i18n';
  import ActivityEventsTable from '$lib/components/activity/ActivityEventsTable.svelte';

  export let title = t('Activity');
  export let items: any[] = [];
  export let emptyLabel = t('No activity found for this selection.');
  export let onSelect: ((entry: any) => void) | null = null;
</script>

<div class="activity-tab-panel" aria-label={title}>
  <ActivityEventsTable
    {items}
    {emptyLabel}
    clickableRows={Boolean(onSelect)}
    on:rowclick={(event) => onSelect?.(event.detail?.entry ?? null)}
  />
</div>

<style>
  .activity-tab-panel {
    min-width: 0;
  }
</style>
