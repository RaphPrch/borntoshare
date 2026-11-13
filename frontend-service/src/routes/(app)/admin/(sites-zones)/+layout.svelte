<script lang="ts">
  
  import { t } from '$lib/i18n';
  import { goto } from "$app/navigation";
  import { page } from "$app/stores";
  import EntityWorkspace from "$lib/components/entity/EntityWorkspace.svelte";
  import ZonesSidebar, { type ZonesSidebarZone } from "$lib/components/zones/ZonesSidebar.svelte";
  import ContextMenu, { menuPositionFor, type ContextMenuItem } from "$lib/components/ui/ContextMenu.svelte";

  interface Props {
    data: { zones: any[]; selectedZoneId?: number | null };
    children?: import('svelte').Snippet;
  }

  let { data, children }: Props = $props();

  let selectedZoneId: number | null = $state(null);

  function createZone() {
    goto('/admin/zones/new');
  }

  // Right click on a zone: its actions (those of the zone page, reached by ?action= / ?tab=)
  let menuZone: ZonesSidebarZone | null = $state(null);
  let menuAt = $state({ x: 0, y: 0 });
  function zoneMenuItems(zone: ZonesSidebarZone): ContextMenuItem[] {
    const servers = Number(zone.endpointCount ?? 0);
    const folders = Number(zone.storage_roots_count ?? 0);
    const blocked = servers > 0 || folders > 0;
    return [
      { key: "edit", label: t("Edit"), icon: "bi-pencil" },
      { key: "add-server", label: t("Add a server"), icon: "bi-plus-lg" },
      { key: "folders", label: t("See its folders"), icon: "bi-folder2", disabled: folders === 0, hint: folders === 0 ? t("No folder in this zone yet") : "" },
      { key: "provisioning", label: t("Provisioning"), icon: "bi-shield-check" },
      { key: "activity", label: t("Activity"), icon: "bi-activity" },
      {
        key: "delete", label: t("Delete zone"), icon: "bi-trash", danger: true, separated: true, disabled: blocked,
        hint: blocked ? t("{servers} server(s) and {folders} folder(s) attached: move or remove them first", { servers, folders }) : ""
      }
    ];
  }
  function pickZoneAction(key: string) {
    const id = Number(menuZone?.id ?? 0);
    if (!id) return;
    if (key === "folders") void goto(`/storage-roots?zone=${id}`);
    else if (key === "provisioning" || key === "activity") void goto(`/admin/zones/${id}?tab=${key}`);
    else void goto(`/admin/zones/${id}?action=${key}`);
  }

  let zones = $derived(data.zones ?? []);
  $effect.pre(() => {
    selectedZoneId = data?.selectedZoneId ?? selectedZoneId;
  });
  let menuItems = $derived(menuZone ? zoneMenuItems(menuZone) : []);
  // The add page stands alone, like the one of the servers
  let addPage = $derived(/\/admin\/zones\/new\/?$/.test($page.url.pathname));
</script>

<ContextMenu open={Boolean(menuZone)} title={String(menuZone?.name ?? "")} subtitle={String(menuZone?.code ?? "")}
  items={menuItems} at={menuAt} onClose={() => (menuZone = null)} onPick={pickZoneAction} />

{#if zones.length && !addPage}
  <EntityWorkspace title={t('Zones')} contentKey={selectedZoneId}>
    {#snippet list()}
      
        <ZonesSidebar
          onAdd={createZone}
          addLabel={t('New zone')}
          {zones}
          {selectedZoneId}
          onSelectZone={(id) => {
            selectedZoneId = id;
            goto(`/admin/zones/${id}`);
          }}
          onZoneMenu={(zone, event) => {
            menuAt = menuPositionFor(event);
            menuZone = zone;
          }}
        />
      
      {/snippet}
    {@render children?.()}
  </EntityWorkspace>
{:else}
  {@render children?.()}
{/if}
