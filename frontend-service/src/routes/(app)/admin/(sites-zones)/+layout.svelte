<script lang="ts">
  import { t } from '$lib/i18n';
  import { goto } from "$app/navigation";
  import { page } from "$app/stores";
  import EntityWorkspace from "$lib/components/entity/EntityWorkspace.svelte";
  import ZonesSidebar from "$lib/components/zones/ZonesSidebar.svelte";

  export let data: { zones: any[]; selectedZoneId?: number | null };

  $: zones = data.zones ?? [];
  let selectedZoneId: number | null = null;
  $: selectedZoneId = data?.selectedZoneId ?? selectedZoneId;

  function createZone() {
    goto('/admin/zones/new');
  }

  // The add page stands alone, like the one of the servers
  $: addPage = /\/admin\/zones\/new\/?$/.test($page.url.pathname);
</script>

{#if zones.length && !addPage}
  <EntityWorkspace title={t('Zones')}>
    <svelte:fragment slot="list">
      <ZonesSidebar
        onAdd={createZone}
        addLabel={t('New zone')}
        {zones}
        {selectedZoneId}
        onSelectZone={(id) => {
          selectedZoneId = id;
          goto(`/admin/zones/${id}`);
        }}
      />
    </svelte:fragment>
    <slot />
  </EntityWorkspace>
{:else}
  <slot />
{/if}
