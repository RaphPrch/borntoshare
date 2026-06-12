<script lang="ts">
  import { goto, invalidateAll } from "$app/navigation";
  import EmptyStateCard from "$lib/components/common/EmptyStateCard.svelte";
  import ZoneFormModal from "$lib/components/sites/modals/ZoneFormModal.svelte";
  import { createZone } from "$lib/api/zones";
  import { notifyError, toAppError } from "$lib/core/errors";
  import { logAppError, logInfo } from "$lib/core/logging";
  import { toast } from "$lib/utils/toast";

  export let data: {
    zones: { id: number; name: string }[];
    selectedZoneId?: number | null;
  };

  let zoneModalOpen = false;

  async function submitZone(payload: any) {
    logInfo("Zone creation requested", {
      action: "zones.create.submit",
      route: "/admin/zones"
    });

    try {
      const { id } = await createZone(fetch, payload);
      logInfo("Zone created", {
        action: "zones.create.success",
        route: "/admin/zones",
        zoneId: id
      });
      toast.success("Zone created");
      zoneModalOpen = false;
      await invalidateAll();
      await goto(`/admin/zones/${id}`);
    } catch (e) {
      const err = toAppError(e, { source: "ui" });
      logAppError(err, {
        action: "zones.create.failed",
        route: "/admin/zones"
      });
      notifyError(err);
    }
  }
</script>

<EmptyStateCard
  containerClass="storage-endpoints-empty"
  iconClass="bi bi-diagram-2"
  title="No zones defined yet"
  description="Zones organize governance policies and scope for storage endpoints and storage roots."
  ctaLabel="Create your first zone"
  onCta={() => (zoneModalOpen = true)}
  hint="The wizard-style modal will guide you step by step."
/>

<ZoneFormModal
  open={zoneModalOpen}
  zone={null}
  mode="create"
  onClose={() => (zoneModalOpen = false)}
  onSubmit={submitZone}
  onDelete={async () => {}}
/>
