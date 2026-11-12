<script lang="ts">
  import RequestPolicyCard from '$lib/components/settings/RequestPolicyCard.svelte';
  import BroadGroupsCard from '$lib/components/settings/BroadGroupsCard.svelte';

  export let data: any;
</script>

<RequestPolicyCard requests={data.advanced?.requests ?? {}} />
<BroadGroupsCard groups={data.advanced?.exposure?.broadGroups ?? []} />
<BroadGroupsCard kind="system" groups={data.advanced?.exposure?.systemAccounts ?? []} />
