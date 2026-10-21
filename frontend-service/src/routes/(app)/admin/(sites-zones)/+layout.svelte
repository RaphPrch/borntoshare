<script lang="ts">
  import { t } from '$lib/i18n';
  import { goto } from "$app/navigation";
  import EntityWorkspace from "$lib/components/entity/EntityWorkspace.svelte";
  import ZonesSidebar from "$lib/components/zones/ZonesSidebar.svelte";

  export let data: { zones: any[]; selectedZoneId?: number | null };

  $: zones = data.zones ?? [];
  let selectedZoneId: number | null = null;
  $: selectedZoneId = data?.selectedZoneId ?? selectedZoneId;
  $: defaultCreateZoneId = selectedZoneId ?? (zones.length > 0 ? Number(zones[0]?.id ?? 0) : null);

  function createZone() {
    const targetZoneId = Number(defaultCreateZoneId ?? 0);
    goto(targetZoneId > 0 ? `/admin/zones/${targetZoneId}?create=1` : '/admin/zones?create=1');
  }
</script>

{#if zones.length}
  <EntityWorkspace title={t('Zones')} subtitle={t('Sites and their storage endpoints, provisioning OU and naming rules.')}>
    <svelte:fragment slot="actions">
      <button type="button" class="b2s-btn b2s-btn-primary" on:click={createZone}>
        <i class="bi bi-plus-lg" aria-hidden="true"></i>
        {t('New zone')}
      </button>
    </svelte:fragment>
    <svelte:fragment slot="list">
      <ZonesSidebar
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
