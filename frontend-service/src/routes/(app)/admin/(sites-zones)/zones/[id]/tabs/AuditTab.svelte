<script lang="ts">
  import ActivityTimeline from '$lib/components/activity/ActivityTimeline.svelte';

  export let activity: any[] = [];
</script>

<ActivityTimeline items={activity} />
