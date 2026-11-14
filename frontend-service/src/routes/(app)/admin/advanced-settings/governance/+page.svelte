<script lang="ts">
  import RequestPolicyCard from '$lib/components/settings/RequestPolicyCard.svelte';

  interface Props {
    data: any;
  }

  let { data }: Props = $props();
</script>

<RequestPolicyCard requests={data.advanced?.requests ?? {}} />
