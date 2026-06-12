<script lang="ts">
  import { getRequestOverallVariant, getRequestStatusMeta } from '$lib/utils/access-request-status';
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';

  export let status: string | null | undefined;
  export let compact = false;

  $: meta = getRequestStatusMeta(status);
  $: variant = getRequestOverallVariant(status);
</script>

<StatusBadge status={meta.label} {compact} {variant} />
