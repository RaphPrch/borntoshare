<script lang="ts">
  // styles consolidated in app.css
  import { goto } from "$app/navigation";

  import ZonesSidebar from "$lib/components/zones/ZonesSidebar.svelte";

  export let data: { zones: any[]; selectedZoneId?: number | null };

  $: zones = data.zones ?? [];
  let selectedZoneId: number | null = null;
  $: selectedZoneId = data?.selectedZoneId ?? selectedZoneId;
  $: defaultCreateZoneId = selectedZoneId ?? (zones.length > 0 ? Number(zones[0]?.id ?? 0) : null);
</script>

<div class="b2s-zones-layout" class:empty={!zones.length}>
  {#if zones.length}
    <aside class="b2s-zones-sidebar b2s-zones-sidebar--entity">
      <ZonesSidebar
        {zones}
        {selectedZoneId}
        onCreateZone={() => {
          const targetZoneId = Number(defaultCreateZoneId ?? 0);
          if (targetZoneId > 0) {
            goto(`/admin/zones/${targetZoneId}?create=1`);
            return;
          }
          goto('/admin/zones?create=1');
        }}
        onSelectZone={(id) => {
          selectedZoneId = id;
          goto(`/admin/zones/${id}`);
        }}
      />
    </aside>
  {/if}

  <main class="b2s-sites-content">
    <slot />
  </main>
</div>
