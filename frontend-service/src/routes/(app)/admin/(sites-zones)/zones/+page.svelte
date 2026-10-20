<script lang="ts">
  import { t } from '$lib/i18n';
  import { goto, invalidateAll } from "$app/navigation";
  import EmptyState from "$lib/components/ui/EmptyState.svelte";
  import ZoneFormModal from "$lib/components/zones/ZoneFormModal.svelte";
  import { createZone } from "$lib/api/zones";
  import { notifyError, toAppError } from "$lib/errors";
  import { logAppError, logInfo } from "$lib/logging";
  import { toast } from "$lib/stores/toast";

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

<EmptyState
  containerClass="storage-endpoints-empty"
  iconClass="bi bi-diagram-2"
  title={t('No zones defined yet')}
  description={t('Zones organize governance policies and scope for storage endpoints and storage roots.')}
  ctaLabel={t('Create your first zone')}
  onCta={() => (zoneModalOpen = true)}
  hint={t('The wizard-style modal will guide you step by step.')}
/>

<ZoneFormModal
  open={zoneModalOpen}
  zone={null}
  mode="create"
  onClose={() => (zoneModalOpen = false)}
  onSubmit={submitZone}
  onDelete={async () => {}}
/>
