<script lang="ts">
  import ActivityTimeline from '$lib/components/activity/ActivityTimeline.svelte';

  interface Props {
    activity?: any[];
  }

  let { activity = [] }: Props = $props();
</script>

<ActivityTimeline items={activity} />
