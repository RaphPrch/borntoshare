<script lang="ts">
  import ActivityTabPanel from '$lib/components/activity/ActivityTabPanel.svelte';

  export let activity: any[] = [];
  export let onSelectActivity: ((entry: any) => void) | null = null;
</script>

<ActivityTabPanel items={activity} onSelect={onSelectActivity} />
