<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { browser } from "$app/environment";
  import { goto } from "$app/navigation";
  import { page } from "$app/stores";
  import { invalidateAll } from "$app/navigation";

  import ZoneFormModal from "$lib/components/sites/modals/ZoneFormModal.svelte";
  import StorageEndpointWizardModal from "$lib/components/storage-endpoints/StorageEndpointWizardModal.svelte";
  import { listStorageEndpoints, updateStorageEndpoint } from "$lib/api/storage-endpoints";
  import PlanPreviewModal from "$lib/modals/PlanPreviewModal.svelte";
  import ActivityDetailsDrawer from "$lib/components/activity/ActivityDetailsDrawer.svelte";
  import ConfirmActionModal from "$lib/components/common/ConfirmActionModal.svelte";
  import EndpointAttachChoiceModal from "./components/EndpointAttachChoiceModal.svelte";

  import {
    createZone,
    deleteZone,
    putZoneProvisioningPolicy,
    type ZoneCreatePayload,
    type ZoneProvisioningPolicy,
    type ZoneOverview,
    updateZone,
  } from "$lib/api/zones";
  import { createActivityEvent } from "$lib/api/activity";
  import {
    runProbeWithPolling,
  } from "$lib/probe/probe-runner";
  import {
    buildStorageEndpointProbeRequestFromEndpoint,
    resolveStorageEndpointProbeConfig,
    validateStorageEndpointProbeConfig
  } from "$lib/probe/storage-endpoint-probe";
  import {
    normalizeProbeStatus,
  } from "$lib/services/mappers/visual-state.mapper";
  import { buildZoneOperationalAttentionItems } from "$lib/services/mappers/entity-operational.mapper";
  import {
    selectVisibleStorageRootAlertsForRootIds,
    storageRootAlertRootId,
    storageRootAlertSummarySubtitle,
    storageRootAlertTone,
    visibleStorageRootAlerts
  } from "$lib/services/mappers/storage-root-alerts.mapper";
  import { toast } from "$lib/utils/toast";
  import { dependencyDeleteMessage, isDependencyDeleteError } from "$lib/utils/delete-guard";

  import ZoneHeader from "./components/ZoneHeader.svelte";
  import EntityConsoleShell from "$lib/components/common/EntityConsoleShell.svelte";
  import EntityAlertDrawer from "$lib/components/common/EntityAlertDrawer.svelte";
  import EntityAlertStrip from "$lib/components/common/EntityAlertStrip.svelte";
  import type { EntityAlertStripItem } from "$lib/components/common/entity-alerts.types";
  import EntityTabs from "$lib/components/common/EntityTabs.svelte";

  const PROBE_SYNC_EVENT = "b2s:storage-endpoint-probe-updated";

  type ZoneTabKey = "overview" | "activity" | "provisioning";

  export let data: {
    zone: ZoneOverview & { site_name?: string; last_probe_at?: string | null };
    endpoints: any[];
    storageRoots: any[];
    storageRootAlerts?: any[];
    activity: any[];
    operationalSummary?: string;
    provisioningPolicy: ZoneProvisioningPolicy | null;
    zoneNamingPolicy?: { template?: string | null } | null;
    identitySources: any[];
    namingPolicyGlobal?: { template?: string | null } | null;
  };

  $: currentZoneId = Number(data.zone?.id ?? 0) || null;
  $: zoneNamingTemplateDefault = String(data?.zoneNamingPolicy?.template ?? "").trim();
  $: globalNamingTemplateDefault = String(data?.namingPolicyGlobal?.template ?? "").trim();

  const tabs: { key: ZoneTabKey; label: string; icon: string }[] = [
    { key: "overview", label: "Overview", icon: "bi-grid" },
    { key: "activity", label: "Activity", icon: "bi-activity" },
    { key: "provisioning", label: "Provisioning", icon: "bi-shield-check" },
  ];

  const tabLoaders: Record<ZoneTabKey, () => Promise<{ default: any }>> = {
    overview: () => import("./tabs/OverviewTab.svelte"),
    activity: () => import("./tabs/AuditTab.svelte"),
    provisioning: () => import("./tabs/PolicyTab.svelte"),
  };

  const validTabs = new Set<ZoneTabKey>(tabs.map((tab) => tab.key));
  const normalizeTab = (raw: string | null): ZoneTabKey => {
    if (!raw) return "overview";
    return validTabs.has(raw as ZoneTabKey) ? (raw as ZoneTabKey) : "overview";
  };

  let activeTab: ZoneTabKey = "overview";
  let loadingTab = true;
  let activeComponent: any = null;
  let loadedComponents: Partial<Record<ZoneTabKey, any>> = {};

  let zoneModalOpen = false;
  let zoneModalMode: "create" | "edit" | "delete" = "edit";
  let editingZone: ZoneOverview | null = null;

  let showEndpointWizard = false;
  let showEndpointAttachChoice = false;
  let attachEndpointsLoading = false;
  let attachEndpointBusyId: number | null = null;
  let attachableEndpoints: Array<{ id: number; name: string; host?: string | null; zoneName?: string | null }> = [];
  let discoverRunning = false;
  let probeResultsByEndpoint: Record<string, string> = {};

  let showPreviewModal = false;
  let policySaving = false;
  let policyError: string | null = null;
  let policyNotice = "";
  let handledCreateQuery = false;
  let activityDetailsOpen = false;
  let selectedActivityEntry: any | null = null;
  let showZoneAlertsDrawer = false;
  let zoneAlertItems: EntityAlertStripItem[] = [];
  let showLeaveProvisioningConfirm = false;
  let pendingTabAfterConfirm: ZoneTabKey | null = null;
  let probeSyncRefreshTimer: ReturnType<typeof setTimeout> | null = null;

  const resolveZoneBaseOu = (incoming: ZoneProvisioningPolicy | null | undefined): string | null => {
    const policyOu = String(incoming?.base_ou_dn ?? incoming?.static_ou_dn ?? "").trim();
    if (policyOu) return policyOu;
    return null;
  };

  const resolveZoneNamingTemplate = (): string => {
    if (zoneNamingTemplateDefault) return zoneNamingTemplateDefault;
    const fallbackEffectiveTemplate = String(data?.namingPolicyGlobal?.template ?? "").trim();
    if (fallbackEffectiveTemplate) return fallbackEffectiveTemplate;
    return globalNamingTemplateDefault;
  };

  const buildPolicyDraftFromData = (incoming: ZoneProvisioningPolicy | null | undefined): ZoneProvisioningPolicy => ({
    enabled: true,
    ou_strategy: "identity_default",
    base_ou_dn: resolveZoneBaseOu(incoming),
    static_ou_dn: null,
    effective_preview: incoming?.effective_preview ?? null,
  });

  const buildPolicySnapshot = (incoming: ZoneProvisioningPolicy | null | undefined) =>
    JSON.stringify({
      enabled: true,
      ou_strategy: "identity_default",
      base_ou_dn: resolveZoneBaseOu(incoming),
      static_ou_dn: null,
    });

  let policyDraft: ZoneProvisioningPolicy = buildPolicyDraftFromData(data.provisioningPolicy);

  let policySavedSnapshot = buildPolicySnapshot(data.provisioningPolicy);

  let policyDraftHydratedForZoneId: number | null = null;

  const isLikelyDn = (value: string) => /(^|,)\s*[A-Z]{1,3}=/i.test(String(value || "").trim());

  $: normalizedPolicyDraft = {
    enabled: true,
    ou_strategy: "identity_default",
    base_ou_dn: String(policyDraft.base_ou_dn ?? "").trim() || null,
    static_ou_dn: null,
  };

  $: if (currentZoneId && policyDraftHydratedForZoneId !== currentZoneId) {
    policyDraftHydratedForZoneId = currentZoneId;
    policyDraft = buildPolicyDraftFromData(data.provisioningPolicy);
    policySavedSnapshot = buildPolicySnapshot(data.provisioningPolicy);
    policyError = null;
    policyNotice = "";
  }

  $: policyValidationErrors = {
    base_ou_dn:
      normalizedPolicyDraft.base_ou_dn && !isLikelyDn(normalizedPolicyDraft.base_ou_dn)
        ? "Invalid DN format (example: OU=Groups,DC=corp,DC=local)"
        : undefined,
    static_ou_dn: undefined,
  };

  $: hasPolicyValidationError = Boolean(policyValidationErrors.base_ou_dn || policyValidationErrors.static_ou_dn);
  $: isPolicyDirty = JSON.stringify(normalizedPolicyDraft) !== policySavedSnapshot;
  $: provisioningReady = Boolean(
    resolveZoneBaseOu(data.provisioningPolicy) && resolveZoneNamingTemplate()
  );
  $: previewItems = [
    `Zone OU source: enabled`,
    `Zone OU: ${(normalizedPolicyDraft.base_ou_dn ?? "(empty)")}`,
    `Naming template (managed in Naming Policies): ${resolveZoneNamingTemplate() || "(empty)"}`,
  ];
  $: zoneProvisioningOverview = {
    namingPolicy: resolveZoneNamingTemplate() || "Not configured",
    guardians: Number((data.zone as any)?.guardians_count ?? (data.zone as any)?.guardian_count ?? 0),
    rootsTotal: storageRoots.length,
    rootsBroken: storageRoots.filter((root) => {
      const status = String(root?.last_probe_status ?? root?.status ?? root?.effective_availability ?? "").toLowerCase();
      const rootId = Number(root?.storage_root_id ?? root?.id ?? 0);
      const alerts = visibleStorageRootAlerts(data.storageRootAlerts ?? []).filter(
        (alert) => storageRootAlertRootId(alert) === rootId
      ).length;
      return status.includes("fail") || status.includes("unreachable") || alerts > 0;
    }).length,
  };

  const endpointEffectiveProbeStatus = (ep: any) => {
    const id = endpointId(ep);
    const runtime = id > 0 ? probeResultsByEndpoint[String(id)] : "";
    return String(runtime || ep?.last_probe_status || ep?.probe_status || "unknown").toLowerCase();
  };
  const endpointHost = (ep: any) => String(ep?.host ?? "").trim();
  const endpointAuthReady = (ep: any) => {
    const username = String(ep?.auth_username ?? ep?.username ?? ep?.bind_dn ?? "").trim();
    const secretRef = String(ep?.auth_secret_ref ?? ep?.bind_password_ref ?? "").trim();
    return Boolean(username && secretRef);
  };

  const endpointBusinessState = (ep: any) => {
    const id = endpointId(ep);
    const runtime = normalizeProbeStatus(id > 0 ? probeResultsByEndpoint[String(id)] : "");
    if (runtime === 'running') {
      return {
        reachability: 'checking',
        provisioning: 'unknown',
        authReadiness: endpointAuthReady(ep) ? 'ready' : 'missing_credentials',
        overall: 'attention'
      };
    }

    const state = String(ep?.operational_state ?? '').trim().toLowerCase();
    if (state === 'disabled') {
      return {
        reachability: 'unknown',
        provisioning: 'unknown',
        authReadiness: endpointAuthReady(ep) ? 'ready' : 'missing_credentials',
        overall: 'disabled'
      };
    }
    if (state === 'reachable') {
      return {
        reachability: 'reachable',
        provisioning: 'unknown',
        authReadiness: endpointAuthReady(ep) ? 'ready' : 'missing_credentials',
        overall: 'healthy'
      };
    }
    if (state === 'checking') {
      return {
        reachability: 'checking',
        provisioning: 'unknown',
        authReadiness: endpointAuthReady(ep) ? 'ready' : 'missing_credentials',
        overall: 'attention'
      };
    }
    if (state === 'unreachable') {
      return {
        reachability: 'unreachable',
        provisioning: 'unknown',
        authReadiness: endpointAuthReady(ep) ? 'ready' : 'missing_credentials',
        overall: 'critical'
      };
    }
    return {
      reachability: 'unknown',
      provisioning: 'unknown',
      authReadiness: endpointAuthReady(ep) ? 'ready' : 'missing_credentials',
      overall: 'unknown'
    };
  };

  const canonicalProbeStatus = (raw: unknown): "success" | "running" | "failed" | "unknown" =>
    normalizeProbeStatus(String(raw ?? ""));
  $: endpoints = Array.isArray(data.endpoints) ? data.endpoints : [];
  $: storageRoots = Array.isArray(data.storageRoots) ? data.storageRoots : [];
  $: activity = Array.isArray(data.activity) ? data.activity : [];
  $: hasAttachedEndpoints = endpoints.length > 0;
  $: hasAttachedStorageRoots = storageRoots.length > 0;

  const zoneLabel = () => String(data.zone?.name ?? data.zone?.code ?? `Zone #${currentZoneId ?? "-"}`);
  const storageRootId = (root: any) => Number(root?.storage_root_id ?? root?.id ?? 0);
  const storageRootName = (root: any) => String(root?.name ?? root?.storage_root_name ?? `Storage root #${storageRootId(root)}`);

  onMount(() => {
    if (!browser) return;

    const onProbeSync = (event: Event) => {
      const custom = event as CustomEvent<{
        endpoint_id?: number;
        last_probe_status?: string;
        persisted?: boolean;
      }>;
      const endpointIdValue = Number(custom?.detail?.endpoint_id ?? 0);
      if (!Number.isFinite(endpointIdValue) || endpointIdValue <= 0) return;

      const endpointInZone = endpoints.some((row) => endpointId(row) === endpointIdValue);
      if (!endpointInZone) return;

      probeResultsByEndpoint = {
        ...probeResultsByEndpoint,
        [String(endpointIdValue)]: canonicalProbeStatus(custom?.detail?.last_probe_status ?? "unknown"),
      };

      if (probeSyncRefreshTimer) clearTimeout(probeSyncRefreshTimer);
      probeSyncRefreshTimer = setTimeout(() => {
        invalidateAll();
      }, 180);
    };

    window.addEventListener(PROBE_SYNC_EVENT, onProbeSync as EventListener);
    return () => {
      window.removeEventListener(PROBE_SYNC_EVENT, onProbeSync as EventListener);
    };
  });

  onDestroy(() => {
    if (probeSyncRefreshTimer) {
      clearTimeout(probeSyncRefreshTimer);
      probeSyncRefreshTimer = null;
    }
  });

  async function logZoneActivity(action: string, payload: {
    outcome?: string;
    severity?: string;
    targetDisplay?: string;
    endpointId?: number | string;
    rootId?: number | string;
    context?: Record<string, unknown>;
  } = {}) {
    if (!currentZoneId) return;

    try {
      await createActivityEvent(fetch, {
        action,
        outcome: payload.outcome ?? "success",
        severity: payload.severity ?? "info",
        target_type: "zone",
        target_id: currentZoneId,
        target_display: payload.targetDisplay ?? zoneLabel(),
        zone_id: currentZoneId,
        endpoint_id: payload.endpointId,
        root_id: payload.rootId,
        context_json: {
          zone: zoneLabel(),
          ...(payload.context ?? {}),
        },
      });

      // Immediate UI refresh for the "Recent activity" panel
      activity = [
        {
          id: `ui-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          action,
          outcome: payload.outcome ?? "success",
          severity: payload.severity ?? "info",
          target_display: payload.targetDisplay ?? zoneLabel(),
          zone_id: currentZoneId,
          endpoint_id: payload.endpointId,
          root_id: payload.rootId,
          context_json: {
            zone: zoneLabel(),
            ...(payload.context ?? {}),
          },
          created_at: new Date().toISOString(),
        },
        ...activity,
      ];
    } catch {
      // best-effort logging only
    }
  }

  $: endpointStates = endpoints.map((ep) => ({
    endpoint: ep,
    state: endpointBusinessState(ep),
  }));
  $: endpointCount = endpointStates.length;
  $: reachableCount = endpointStates.filter((row) => row.state.reachability === "reachable").length;
  $: runnableCount = endpoints.filter((ep) => endpointHost(ep) && endpointAuthReady(ep)).length;

  const normalizedZoneOperationalSummary = (): 'healthy' | 'attention' => {
    const raw = String(data?.operationalSummary ?? '').trim().toLowerCase();
    return raw === 'healthy' ? 'healthy' : 'attention';
  };

  $: healthSummary = {
    endpointCount,
    reachableCount,
    runnableCount,
    nonRunnableCount: Math.max(0, endpointCount - runnableCount),
    lastProbeAt: data.zone?.last_probe_at ?? null,
    unhealthyCount: Math.max(0, endpointCount - reachableCount),
    healthLabel: normalizedZoneOperationalSummary() === "healthy" ? "ok" : "warning",
  } as {
    endpointCount: number;
    reachableCount: number;
    runnableCount: number;
    nonRunnableCount: number;
    lastProbeAt: string | null;
    unhealthyCount: number;
    healthLabel: "ok" | "warning";
  };

  const formatZoneProbeDate = (value: string | null | undefined): string => {
    const text = String(value ?? "").trim();
    if (!text) return "Never run";
    const date = new Date(text);
    if (!Number.isFinite(date.getTime())) return "Never run";
    return date.toLocaleString("en-GB", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  $: zoneHeaderAttentionItems = buildZoneOperationalAttentionItems({
    endpointCount,
    reachableCount,
    nonRunnableCount: healthSummary.nonRunnableCount,
    provisioningReady,
    healthLabel: healthSummary.healthLabel,
  });
  $: zoneHasAttention = zoneHeaderAttentionItems.length > 0;
  $: zoneAttentionMeta = `Last probe: ${formatZoneProbeDate(healthSummary.lastProbeAt)}`;
  const alertToneFromText = (value: string): "warning" | "error" => {
    const text = String(value ?? "").toLowerCase();
    return text.includes("unreachable") || text.includes("failed") || text.includes("down")
      ? "error"
      : "warning";
  };
  const operationalZoneAlertItems = (): EntityAlertStripItem[] =>
    zoneHeaderAttentionItems.map((item, index) => ({
      key: `zone-operational-alert-${index}-${item}`,
      title: item,
      subtitle: index === 0 ? zoneAttentionMeta : null,
      tone: alertToneFromText(item),
    }));

  const zoneRootGovernanceAlertItems = (): EntityAlertStripItem[] => {
    const rootIds = storageRoots.map((root) => storageRootId(root));
    const rootLabels = new Map(storageRoots.map((root) => [storageRootId(root), storageRootName(root)]));
    return selectVisibleStorageRootAlertsForRootIds(rootIds, data.storageRootAlerts ?? []).map((alert) => {
      const rootId = storageRootAlertRootId(alert);
      const rootLabel = rootLabels.get(rootId) ?? `Storage root #${rootId}`;
      const detail = storageRootAlertSummarySubtitle(alert);
      return {
        key: `zone-root-alert-${String(alert?.alert_key ?? alert?.id ?? `${alert?.alert_type ?? 'alert'}-${rootId}`)}`,
        title: String(alert?.title ?? 'Attention required'),
        subtitle: detail ? `${rootLabel} · ${detail}` : rootLabel,
        tone: storageRootAlertTone(alert),
      };
    });
  };

  const dedupeZoneAlertItems = (items: EntityAlertStripItem[]): EntityAlertStripItem[] => {
    const seen = new Set<string>();
    const out: EntityAlertStripItem[] = [];
    for (const item of items) {
      const key = `${String(item.title ?? "").trim().toLowerCase()}|${String(item.subtitle ?? "").trim().toLowerCase()}`;
      if (!key || seen.has(key)) continue;
      seen.add(key);
      out.push(item);
    }
    return out;
  };

  const buildZoneAlerts = (): EntityAlertStripItem[] =>
    dedupeZoneAlertItems([
      ...operationalZoneAlertItems(),
      ...zoneRootGovernanceAlertItems(),
    ]);

  $: zoneAlertItems = buildZoneAlerts();

  async function ensureTabLoaded(tab: ZoneTabKey) {
    if (loadedComponents[tab]) {
      activeComponent = loadedComponents[tab];
      loadingTab = false;
      return;
    }

    loadingTab = true;
    try {
      const module = await tabLoaders[tab]();
      loadedComponents = { ...loadedComponents, [tab]: module.default };
      activeComponent = module.default;
    } finally {
      loadingTab = false;
    }
  }

  function navigateToTab(tab: ZoneTabKey) {
    const url = new URL($page.url);
    if (tab === "overview") {
      url.searchParams.delete("tab");
    } else {
      url.searchParams.set("tab", tab);
    }
    goto(`${url.pathname}${url.search}`, {
      replaceState: true,
      noScroll: true,
      keepFocus: true,
    });
  }

  function setTab(tab: ZoneTabKey) {
    if (isPolicyDirty && activeTab === "provisioning" && tab !== "provisioning") {
      pendingTabAfterConfirm = tab;
      showLeaveProvisioningConfirm = true;
      return;
    }

    navigateToTab(tab);
  }

  function confirmLeaveProvisioningTab() {
    const nextTab = pendingTabAfterConfirm;
    showLeaveProvisioningConfirm = false;
    pendingTabAfterConfirm = null;
    if (!nextTab) return;
    navigateToTab(nextTab);
  }

  const endpointId = (ep: any) => Number(ep?.id ?? ep?.storage_endpoint_id ?? 0);
  async function runDiscoveryProbe() {
    if (!currentZoneId) return;
    if (endpoints.length === 0) {
      toast.warning("No storage endpoint is defined in this zone. Add one before running the discovery probe.");
      return;
    }

    discoverRunning = true;
    try {
      const runnable = endpoints.filter((ep) => endpointHost(ep) && endpointAuthReady(ep));
      if (runnable.length === 0) {
        toast.warning("No runnable endpoint found (missing host or credentials).");
        return;
      }

      let successCount = 0;
      let failedCount = 0;

      // Sequential execution in the current table display order (endpoints list order)
      for (const endpoint of runnable) {
        const probeConfig = resolveStorageEndpointProbeConfig(endpoint);
        const id = probeConfig.endpointId;
        const epName = String(endpoint?.name ?? endpoint?.storage_endpoint_name ?? `Endpoint #${id || "-"}`);
        const validation = validateStorageEndpointProbeConfig(probeConfig, { label: 'Storage endpoint' });

        if (!validation.ok) {
          probeResultsByEndpoint = {
            ...probeResultsByEndpoint,
            [String(id || Math.random())]: "invalid-config",
          };
          continue;
        }

        const request = buildStorageEndpointProbeRequestFromEndpoint(endpoint, {
          discover: true,
          timeoutSec: 20,
          uiOrigin: "admin",
        });

        probeResultsByEndpoint = { ...probeResultsByEndpoint, [String(id)]: "running" };

        try {
          const final = await runProbeWithPolling({
            fetchFn: fetch,
            request,
            intervalMs: 1200,
            maxAttempts: 25,
          });

          const finalStatus = String(final?.status ?? (final?.ok ? "success" : "failed")).toLowerCase();
          const persistedProbeStatus = canonicalProbeStatus(finalStatus);
          const persistedProbeAt = new Date().toISOString();
          probeResultsByEndpoint = {
            ...probeResultsByEndpoint,
            [String(id)]: persistedProbeStatus,
          };

          try {
            await updateStorageEndpoint(fetch, id, {
              last_probe_status: persistedProbeStatus,
              last_probe_at: persistedProbeAt,
              last_probe_message: final?.ok
                ? "probe completed"
                : String(final?.errorMessage ?? "Probe failed"),
            });
          } catch {
            // non-blocking: keep UI runtime state even if persistence fails
          }

          await logZoneActivity("zone.probe_rerun", {
            outcome: final?.ok ? "success" : "failed",
            severity: final?.ok ? "info" : "critical",
            endpointId: id,
            context: {
              endpoint: epName,
              protocol: probeConfig.protocol,
              host: probeConfig.host,
              probe_status: persistedProbeStatus,
            },
          });

          if (final?.ok) {
            successCount += 1;
          } else {
            failedCount += 1;
          }
        } catch {
          failedCount += 1;
          const persistedProbeAt = new Date().toISOString();
          probeResultsByEndpoint = {
            ...probeResultsByEndpoint,
            [String(id)]: "failed",
          };
          try {
            await updateStorageEndpoint(fetch, id, {
              last_probe_status: "failed",
              last_probe_at: persistedProbeAt,
              last_probe_message: "Probe failed",
            });
          } catch {
            // non-blocking
          }
          await logZoneActivity("zone.probe_rerun", {
            outcome: "failed",
            severity: "critical",
            endpointId: id,
            context: {
              endpoint: epName,
              protocol: probeConfig.protocol,
              host: probeConfig.host,
              probe_status: "failed",
            },
          });
        }
      }

      if (failedCount > 0) {
        toast.warning(`Discovery probes finished (${successCount} success, ${failedCount} warning/error).`);
      } else {
        toast.success(`Discovery probes finished (${successCount}/${runnable.length} successful).`);
      }
    } catch (e) {
      toast.error(e?.message ?? "Discovery probe failed");
    } finally {
      discoverRunning = false;
    }
  }

  async function runEndpointProbe(endpoint: any) {
    const probeConfig = resolveStorageEndpointProbeConfig(endpoint);
    const id = probeConfig.endpointId;
    const epName = String(endpoint?.name ?? endpoint?.storage_endpoint_name ?? `Endpoint #${id || "-"}`);

    if (!id) {
      toast.error("Invalid storage endpoint for probe run.");
      return;
    }

    if (normalizeProbeStatus(probeResultsByEndpoint[String(id)]) === "running") {
      return;
    }

    const validation = validateStorageEndpointProbeConfig(probeConfig, { label: "Storage endpoint" });
    if (!validation.ok) {
      toast.error(validation.message ?? "Storage endpoint credentials are required before running a probe.");
      return;
    }

    const request = buildStorageEndpointProbeRequestFromEndpoint(endpoint, {
      discover: false,
      timeoutSec: 20,
      uiOrigin: "admin",
      label: "Storage endpoint",
    });

    probeResultsByEndpoint = { ...probeResultsByEndpoint, [String(id)]: "running" };

    try {
      const final = await runProbeWithPolling({
        fetchFn: fetch,
        request,
        intervalMs: 1200,
        maxAttempts: 25,
      });

      const finalStatus = String(final?.status ?? (final?.ok ? "success" : "failed")).toLowerCase();
      const persistedProbeStatus = canonicalProbeStatus(finalStatus);
      const persistedProbeAt = new Date().toISOString();
      const message = final?.ok ? "endpoint probe completed" : String(final?.errorMessage ?? "Probe failed");

      probeResultsByEndpoint = {
        ...probeResultsByEndpoint,
        [String(id)]: persistedProbeStatus,
      };

      try {
        await updateStorageEndpoint(fetch, id, {
          last_probe_status: persistedProbeStatus,
          last_probe_at: persistedProbeAt,
          last_probe_message: message,
        });
      } catch {
        // non-blocking: runtime state and activity still reflect the probe result
      }

      await logZoneActivity("zone.endpoint_probe_run", {
        outcome: final?.ok ? "success" : "failed",
        severity: final?.ok ? "info" : "critical",
        endpointId: id,
        context: {
          endpoint: epName,
          protocol: probeConfig.protocol,
          host: probeConfig.host,
          probe_status: persistedProbeStatus,
        },
      });

      if (final?.ok) {
        toast.success(`Probe OK for ${epName}.`);
      } else {
        toast.error(`Probe failed for ${epName}.`);
      }

      if (browser) await invalidateAll();
    } catch (e) {
      const persistedProbeAt = new Date().toISOString();
      const message = String(e?.message ?? "Probe failed");
      probeResultsByEndpoint = {
        ...probeResultsByEndpoint,
        [String(id)]: "failed",
      };

      try {
        await updateStorageEndpoint(fetch, id, {
          last_probe_status: "failed",
          last_probe_at: persistedProbeAt,
          last_probe_message: message,
        });
      } catch {
        // non-blocking
      }

      await logZoneActivity("zone.endpoint_probe_run", {
        outcome: "failed",
        severity: "critical",
        endpointId: id,
        context: {
          endpoint: epName,
          protocol: probeConfig.protocol,
          host: probeConfig.host,
          probe_status: "failed",
        },
      });

      toast.error(message);
    }
  }

  async function savePolicy() {
    if (!currentZoneId || policySaving || hasPolicyValidationError) return;
    policySaving = true;
    policyError = null;
    policyNotice = "";

    try {
      const updated = await putZoneProvisioningPolicy(fetch, currentZoneId, {
        enabled: normalizedPolicyDraft.enabled,
        ou_strategy: normalizedPolicyDraft.ou_strategy,
        base_ou_dn: normalizedPolicyDraft.base_ou_dn,
        static_ou_dn: normalizedPolicyDraft.static_ou_dn,
      });

      policyDraft = {
        ...policyDraft,
        ...updated,
      };
      policySavedSnapshot = JSON.stringify({
        enabled: true,
        ou_strategy: "identity_default",
        base_ou_dn: updated?.base_ou_dn ?? policyDraft.base_ou_dn ?? null,
        static_ou_dn: null,
      });
      policyNotice = "Settings saved";
      await logZoneActivity("zone.provisioning_settings_saved", {
        outcome: "success",
        severity: "admin",
        context: {
          ou_strategy: policyDraft.ou_strategy,
          naming_template_source: "naming-policies",
        },
      });
      toast.success("Provisioning policy saved.");
    } catch (e) {
      policyError = e?.message ?? "Unable to save policy";
      toast.error(policyError);
    } finally {
      policySaving = false;
    }
  }

  function resetPolicyDefaults() {
    policyError = null;
    policyNotice = "";
      policyDraft = {
      enabled: true,
      ou_strategy: "identity_default",
      base_ou_dn: null,
      static_ou_dn: null,
      effective_preview: null,
    };
  }

  function updatePolicyDraft(next: ZoneProvisioningPolicy) {
    policyDraft = {
      ...policyDraft,
      ...next,
    };
  }

  function openEditZone() {
    editingZone = data.zone;
    zoneModalMode = "edit";
    zoneModalOpen = true;
  }

  function openCreateZone() {
    editingZone = null;
    zoneModalMode = "create";
    zoneModalOpen = true;
  }

  function openDeleteZone() {
    if (hasAttachedEndpoints || hasAttachedStorageRoots) {
      const blockers = [
        hasAttachedEndpoints
          ? `${endpoints.length} storage endpoint${endpoints.length > 1 ? "s" : ""}`
          : null,
        hasAttachedStorageRoots
          ? `${storageRoots.length} storage root${storageRoots.length > 1 ? "s" : ""}`
          : null,
      ].filter(Boolean);
      toast.error(`This zone cannot be deleted while ${blockers.join(" and ")} remain attached.`);
      return;
    }

    editingZone = data.zone;
    zoneModalMode = "delete";
    zoneModalOpen = true;
  }

  async function submitZone(payload: Partial<ZoneCreatePayload>) {
    try {
      if (zoneModalMode === "edit" && editingZone?.id) {
        await updateZone(fetch, editingZone.id, payload);
        toast.success("Zone updated");
        zoneModalOpen = false;
        if (browser && currentZoneId) goto(`/admin/zones/${currentZoneId}`, { invalidateAll: true });
        return;
      }

      if (zoneModalMode === "create") {
        const fallbackName = `Zone ${new Date().toISOString().slice(0, 19).replace(/[-:T]/g, "")}`;
        const payloadWithName: ZoneCreatePayload = {
          name: String(payload?.name ?? "").trim() || fallbackName,
          code: String(payload?.code ?? "").trim() || fallbackName,
          description: payload?.description ?? null,
        };

        if (!payloadWithName.name || !payloadWithName.code) {
          toast.error("Zone name and code are required.");
          return;
        }

        const { id } = await createZone(fetch, payloadWithName);
        toast.success("Zone created");
        zoneModalOpen = false;
        if (browser) goto(`/admin/zones/${id}`, { invalidateAll: true });
      }
    } catch (e) {
      toast.error(e?.message ?? "Zone operation failed");
    }
  }

  async function confirmDeleteZone() {
    if (!editingZone?.id) return;
    if (hasAttachedEndpoints || hasAttachedStorageRoots) {
      toast.error("Remove all storage endpoints and storage roots attached to this zone before deleting it.");
      zoneModalOpen = false;
      return;
    }
    try {
      await deleteZone(fetch, editingZone.id);
      toast.success("Zone deleted");
      zoneModalOpen = false;
      await goto("/admin/zones");
    } catch (e) {
      if (isDependencyDeleteError(e)) {
        zoneModalOpen = false;
        toast.error(dependencyDeleteMessage("zone", "storage endpoints or storage roots"));
        return;
      }
      toast.error(e?.message ?? "Zone delete failed");
    }
  }

  function openActivityDetails(entry: any) {
    selectedActivityEntry = entry ?? null;
    activityDetailsOpen = Boolean(selectedActivityEntry);
  }

  async function loadAttachableEndpoints() {
    if (!currentZoneId) return;
    attachEndpointsLoading = true;
    try {
      const rows = await listStorageEndpoints(fetch);
      attachableEndpoints = (Array.isArray(rows) ? rows : [])
        .filter((ep) => Number(ep?.zone_id ?? 0) !== Number(currentZoneId))
        .map((ep) => ({
          id: Number(ep?.id ?? 0),
          name: String(ep?.name ?? `Endpoint #${ep?.id ?? '-'}`),
          host: String(ep?.host ?? '').trim() || null,
          zoneName: String(ep?.zone_name ?? '').trim() || null
        }))
        .filter((ep) => ep.id > 0)
        .sort((a, b) => a.name.localeCompare(b.name, 'en', { sensitivity: 'base' }));
    } catch (e: any) {
      attachableEndpoints = [];
      toast.error(String(e?.message ?? 'Unable to load existing endpoints.'));
    } finally {
      attachEndpointsLoading = false;
    }
  }

  async function openEndpointAttachChoice() {
    showEndpointAttachChoice = true;
    await loadAttachableEndpoints();
  }

  function startCreateEndpointWizard() {
    showEndpointAttachChoice = false;
    showEndpointWizard = true;
  }

  async function attachExistingEndpoint(endpointId: number) {
    if (!currentZoneId || !endpointId) return;
    attachEndpointBusyId = endpointId;
    try {
      await updateStorageEndpoint(fetch, endpointId, { zone_id: currentZoneId });
      toast.success('Endpoint attached to this zone.');
      showEndpointAttachChoice = false;
      await invalidateAll();
    } catch (e: any) {
      toast.error(String(e?.message ?? 'Unable to attach endpoint.'));
    } finally {
      attachEndpointBusyId = null;
    }
  }

  function closeActivityDetails() {
    activityDetailsOpen = false;
    selectedActivityEntry = null;
  }

  $: activeTab = normalizeTab($page.url.searchParams.get("tab"));
  $: {
    const shouldOpenCreate = $page.url.searchParams.get("create") === "1";
    if (shouldOpenCreate && !handledCreateQuery) {
      handledCreateQuery = true;
      openCreateZone();
    }
    if (!shouldOpenCreate) {
      handledCreateQuery = false;
    }
  }
  $: void ensureTabLoaded(activeTab);
  $: tabProps = {
    overview: {
      zone: data.zone,
      endpoints,
      storageRootCount: storageRoots.length,
      probeResultsByEndpoint,
      activity,
      healthSummary,
      discoverRunning,
      onCreateZone: openCreateZone,
      onCreateEndpoint: openEndpointAttachChoice,
      onRunEndpointProbe: runEndpointProbe,
      onViewAllActivity: () => setTab("activity"),
      onSelectActivity: openActivityDetails,
      onOpenEndpoint: (endpointId: number | string) => goto(`/admin/storage-endpoints/${endpointId}`),
    },
    activity: {
      activity,
      onSelectActivity: openActivityDetails,
    },
    provisioning: {
      policy: policyDraft,
      namingTemplateLabel: resolveZoneNamingTemplate(),
      saving: policySaving,
      error: policyError,
      isDirty: isPolicyDirty,
      canSave: !hasPolicyValidationError,
      validationErrors: policyValidationErrors,
      inheritanceOverview: zoneProvisioningOverview,
      onChange: updatePolicyDraft,
      onSave: savePolicy,
      onReset: resetPolicyDefaults,
      onPreview: () => (showPreviewModal = true),
    },
  };
</script>

<EntityConsoleShell>
  <svelte:fragment slot="header">
      <ZoneHeader
        zone={data.zone}
      endpointCount={endpoints.length}
      healthLabel={healthSummary.healthLabel}
      showAttention={false}
      onEdit={openEditZone}
      onDelete={openDeleteZone}
    />
    <EntityAlertStrip
      items={zoneAlertItems}
      onViewAll={() => (showZoneAlertsDrawer = true)}
      ariaLabel="Zone alerts"
    />
  </svelte:fragment>

  <svelte:fragment slot="tabs">
    <EntityTabs
      {tabs}
      activeKey={activeTab}
      ariaLabel="Zone sections"
      onChange={(key) => setTab(normalizeTab(String(key ?? 'overview')))}
    />
  </svelte:fragment>

  {#if loadingTab || !activeComponent}
    <div class="zone-console__skeleton" aria-label="Loading tab content"></div>
  {:else}
    <svelte:component this={activeComponent} {...tabProps[activeTab]} />
  {/if}
</EntityConsoleShell>

<div class="visually-hidden" aria-live="polite">{policyNotice || policyError || ""}</div>

<EntityAlertDrawer
  open={showZoneAlertsDrawer}
  onClose={() => (showZoneAlertsDrawer = false)}
  title="Zone alerts"
  subtitle={`Zone · ${zoneLabel()}`}
  items={zoneAlertItems}
  emptyLabel="No alert found for this zone."
  ariaLabelledby="zone-alerts-drawer-title"
/>

<ZoneFormModal
  open={zoneModalOpen}
  zone={editingZone}
  mode={zoneModalMode}
  onClose={() => {
    zoneModalOpen = false;
    editingZone = null;
  }}
  onSubmit={submitZone}
  onDelete={confirmDeleteZone}
/>

<StorageEndpointWizardModal
  open={showEndpointWizard}
  onClose={() => (showEndpointWizard = false)}
  wizardProps={{ initialZoneId: currentZoneId, lockZone: true }}
  on:done={async () => {
    showEndpointWizard = false;
    if (browser) {
      await invalidateAll();
    }
  }}
/>

<EndpointAttachChoiceModal
  open={showEndpointAttachChoice}
  existingEndpoints={attachableEndpoints}
  loading={attachEndpointsLoading}
  busyAttachId={attachEndpointBusyId}
  onClose={() => (showEndpointAttachChoice = false)}
  onCreateNew={startCreateEndpointWizard}
  onAttachExisting={attachExistingEndpoint}
/>

<PlanPreviewModal
  open={showPreviewModal}
  title="Provisioning policy changes preview"
  items={previewItems}
  onClose={() => (showPreviewModal = false)}
/>

<ActivityDetailsDrawer
  open={activityDetailsOpen}
  entry={selectedActivityEntry}
  onClose={closeActivityDetails}
  width="620px"
/>

<ConfirmActionModal
  open={showLeaveProvisioningConfirm}
  onClose={() => {
    showLeaveProvisioningConfirm = false;
    pendingTabAfterConfirm = null;
  }}
  onConfirm={confirmLeaveProvisioningTab}
  severity="warning"
  title="Leave provisioning tab?"
  subtitle="You have unsaved changes."
  impactTitle="Impact"
  impactItems={[
    'Any unsaved provisioning changes will be lost.'
  ]}
  cancelLabel="Stay"
  confirmLabel="Leave tab"
/>
