<script lang="ts">
  
  import { reportUiError } from '$lib/errors/report';
  import { formatDateTime } from '$lib/utils/format';
  import { t } from '$lib/i18n';
  import { onDestroy, onMount } from "svelte";
  import { browser } from "$app/environment";
  import { goto } from "$app/navigation";
  import { page } from "$app/stores";
  import { invalidateAll } from "$app/navigation";

  import ZoneFormModal from "$lib/components/zones/ZoneFormModal.svelte";
  import { listStorageEndpoints, updateStorageEndpoint } from "$lib/api/storage-endpoints";
  import ConfirmActionModal from "$lib/components/ui/ConfirmActionModal.svelte";
  import EndpointAttachChoiceModal from "./components/EndpointAttachChoiceModal.svelte";
  import { putZoneNamingPolicy } from "$lib/api/naming-policies";

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
  } from "$lib/jobs/probe-runner";
  import {
    buildStorageEndpointProbeRequestFromEndpoint,
    resolveStorageEndpointProbeConfig,
    validateStorageEndpointProbeConfig
  } from "$lib/jobs/storage-endpoint-probe";
  import {
    normalizeProbeStatus,
  } from "$lib/mappers/visual-state.mapper";
  import { toast } from "$lib/stores/toast";
  import { dependencyDeleteMessage, isDependencyDeleteError } from "$lib/utils/delete-guard";

  import ZoneHero from "./components/ZoneHero.svelte";
  import EntityConsoleShell from "$lib/components/entity/EntityConsoleShell.svelte";
  import ZoneTiles from "$lib/components/zones/ZoneTiles.svelte";
  import ZoneTodo from "$lib/components/zones/ZoneTodo.svelte";
  import { summarizeZone } from "$lib/components/zones/zone-summary";
  import { apiPostData } from "$lib/api/client";
  import Tabs from "$lib/components/ui/Tabs.svelte";

  const PROBE_SYNC_EVENT = "b2s:storage-endpoint-probe-updated";

  type ZoneTabKey = "overview" | "activity" | "provisioning";

  interface Props {
    data: {
    zone: ZoneOverview & { site_name?: string; last_probe_at?: string | null };
    endpoints: any[];
    storageRoots: any[];
    storageRootAlerts?: any[];
    activity: any[];
    operationalSummary?: string;
    provisioningPolicy: ZoneProvisioningPolicy | null;
    zoneNamingPolicy?: { template?: string | null; override_enabled?: boolean | number | null } | null;
    identitySources: any[];
    namingPolicyGlobal?: { template?: string | null } | null;
    zones?: Array<{ id?: number; pendingRequests?: number; identitySourceIds?: number[] }>;
  };
  }

  let { data }: Props = $props();

  let currentZoneId = $derived(Number(data.zone?.id ?? 0) || null);
  let globalNamingTemplateDefault = $derived(String(data?.namingPolicyGlobal?.template ?? "").trim());

  const zoneTabs: { key: ZoneTabKey; label: string; icon: string }[] = [
    { key: "overview", label: t('Overview'), icon: "bi-grid" },
    { key: "provisioning", label: t('Provisioning'), icon: "bi-shield-check" },
    { key: "activity", label: t('Activity'), icon: "bi-activity" },
  ];

  const tabLoaders: Record<ZoneTabKey, () => Promise<{ default: any }>> = {
    overview: () => import("./tabs/OverviewTab.svelte"),
    activity: () => import("./tabs/AuditTab.svelte"),
    provisioning: () => import("./tabs/PolicyTab.svelte"),
  };

  const validTabs = new Set<ZoneTabKey>(zoneTabs.map((tab) => tab.key));
  const normalizeTab = (raw: string | null): ZoneTabKey => {
    if (!raw) return "overview";
    return validTabs.has(raw as ZoneTabKey) ? (raw as ZoneTabKey) : "overview";
  };

  let activeTab: ZoneTabKey = $state("overview");
  let loadingTab = $state(true);
  let activeComponent: any = $state(null);
  let loadedComponents: Partial<Record<ZoneTabKey, any>> = {};

  let zoneModalOpen = $state(false);
  let zoneModalMode: "create" | "edit" | "delete" = $state("edit");
  let editingZone: ZoneOverview | null = $state(null);

  let showEndpointAttachChoice = $state(false);
  let attachEndpointsLoading = $state(false);
  let attachEndpointBusyId: number | null = $state(null);
  let attachableEndpoints: Array<{ id: number; name: string; host?: string | null; zoneName?: string | null }> = $state([]);
  let discoverRunning = false;
  let probeResultsByEndpoint: Record<string, string> = $state({});

  let policySaving = $state(false);
  let policyError: string | null = $state(null);
  let policyNotice = $state("");
  let handledCreateQuery = $state(false);
  let showRereadConfirm = $state(false);
  let rereadBusy = $state(false);
  let showLeaveProvisioningConfirm = $state(false);
  let pendingTabAfterConfirm: ZoneTabKey | null = $state(null);
  let probeSyncRefreshTimer: ReturnType<typeof setTimeout> | null = null;

  const resolveZoneBaseOu = (incoming: ZoneProvisioningPolicy | null | undefined): string | null => {
    const policyOu = String(incoming?.base_ou_dn ?? incoming?.static_ou_dn ?? "").trim();
    if (policyOu) return policyOu;
    return null;
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

  // svelte-ignore state_referenced_locally (an initial value, read once as before)
  let policyDraft: ZoneProvisioningPolicy = $state(buildPolicyDraftFromData(data.provisioningPolicy));

  // Naming template of the zone (naming policy override); empty or equal to the global one = inherit the global template
  const initialNamingTemplate = (): string =>
    (data?.zoneNamingPolicy?.override_enabled ? String(data?.zoneNamingPolicy?.template ?? "").trim() : "") ||
    String(data?.namingPolicyGlobal?.template ?? "").trim();
  let namingDraft = $state(initialNamingTemplate());
  // svelte-ignore state_referenced_locally (an initial value, read once as before)
  let namingSaved = $state(namingDraft);
  function setNamingDraft(value: string): void {
    namingDraft = value;
  }

  // svelte-ignore state_referenced_locally (an initial value, read once as before)
  let policySavedSnapshot = $state(buildPolicySnapshot(data.provisioningPolicy));

  let policyDraftHydratedForZoneId: number | null = $state(null);

  const isLikelyDn = (value: string) => /(^|,)\s*[A-Z]{1,3}=/i.test(String(value || "").trim());

  let normalizedPolicyDraft = $derived({
    enabled: true,
    ou_strategy: "identity_default" as const,
    base_ou_dn: String(policyDraft.base_ou_dn ?? "").trim() || null,
    static_ou_dn: null,
  });

  $effect.pre(() => {
    if (currentZoneId && policyDraftHydratedForZoneId !== currentZoneId) {
      policyDraftHydratedForZoneId = currentZoneId;
      policyDraft = buildPolicyDraftFromData(data.provisioningPolicy);
      policySavedSnapshot = buildPolicySnapshot(data.provisioningPolicy);
      const zoneTemplate = initialNamingTemplate();
      namingDraft = zoneTemplate;
      namingSaved = zoneTemplate;
      policyError = null;
      policyNotice = "";
    }
  });

  let policyValidationErrors = $derived({
    base_ou_dn:
      normalizedPolicyDraft.base_ou_dn && !isLikelyDn(normalizedPolicyDraft.base_ou_dn)
        ? t('Invalid DN format (example: OU=Groups,DC=corp,DC=local)')
        : undefined,
    static_ou_dn: undefined,
  });

  let hasPolicyValidationError = $derived(Boolean(policyValidationErrors.base_ou_dn || policyValidationErrors.static_ou_dn));
  let isPolicyDirty = $derived(JSON.stringify(normalizedPolicyDraft) !== policySavedSnapshot || namingDraft.trim() !== namingSaved.trim());
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
  let endpoints = $derived(Array.isArray(data.endpoints) ? data.endpoints : []);
  let storageRoots = $derived(Array.isArray(data.storageRoots) ? data.storageRoots : []);
  let activity = $derived(Array.isArray(data.activity) ? data.activity : []);
  let hasAttachedEndpoints = $derived(endpoints.length > 0);
  let hasAttachedStorageRoots = $derived(storageRoots.length > 0);

  const zoneLabel = () => String(data.zone?.name ?? data.zone?.code ?? t('Zone #{value}', { value: (currentZoneId ?? "-") }));

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

  let endpointStates = $derived(endpoints.map((ep) => ({
    endpoint: ep,
    state: endpointBusinessState(ep),
  })));
  let endpointCount = $derived(endpointStates.length);
  let reachableCount = $derived(endpointStates.filter((row) => row.state.reachability === "reachable").length);
  let runnableCount = $derived(endpoints.filter((ep) => endpointHost(ep) && endpointAuthReady(ep)).length);

  const normalizedZoneOperationalSummary = (): 'healthy' | 'attention' => {
    const raw = String(data?.operationalSummary ?? '').trim().toLowerCase();
    return raw === 'healthy' ? 'healthy' : 'attention';
  };

  let healthSummary = $derived({
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
  });

  // Servers reachable or not and folders to review, from the open alerts of the folders of the zone
  let summary = $derived(summarizeZone(endpoints, storageRoots, (data.storageRootAlerts ?? []) as any[], (id) =>
    normalizeProbeStatus(probeResultsByEndpoint[String(id)] ?? "") === "running" ? "checking" : null
  ));
  let zoneEntry = $derived((data.zones ?? []).find((zone) => Number(zone?.id) === currentZoneId));
  let pendingRequests = $derived(Number(zoneEntry?.pendingRequests ?? 0));
  let directories = $derived((zoneEntry?.identitySourceIds ?? [])
    .map((id) => (data.identitySources ?? []).find((source: any) => Number(source?.id) === Number(id)))
    .map((source: any) => String(source?.name ?? source?.display_name ?? "").trim())
    .filter(Boolean));
  let serversLabel = $derived([
    summary.files.length ? t('{count} file server(s)', { count: summary.files.length }) : "",
    summary.dfs.length ? t('{count} DFS namespace(s)', { count: summary.dfs.length }) : "",
  ].filter(Boolean).join(" · "));
  let foldersHref = $derived(`/storage-roots?zone=${currentZoneId ?? ""}`);

  // Folders whose test failed or whose ACL has a gap, on servers that answer: read again by the worker
  async function rereadFolders() {
    showRereadConfirm = false;
    const ids = summary.reread.map((root) => root.id);
    if (!ids.length || rereadBusy) return;
    rereadBusy = true;
    try {
      let queued = 0;
      for (let start = 0; start < ids.length; start += 100) {
        const answer = await apiPostData<{ queued: number[] }>(fetch, "/storage-roots/bulk-check", { root_ids: ids.slice(start, start + 100) });
        queued += answer?.queued?.length ?? 0;
      }
      toast.success(t('{count} folder(s) queued for a test and an ACL read.', { count: queued }));
      await invalidateAll();
    } catch (e: any) {
      toast.error(String(e?.message ?? t('The action failed.')));
    } finally {
      rereadBusy = false;
    }
  }

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

  async function runEndpointProbe(endpoint: any) {
    const probeConfig = resolveStorageEndpointProbeConfig(endpoint);
    const id = probeConfig.endpointId;
    const epName = String(endpoint?.name ?? endpoint?.storage_endpoint_name ?? t('Endpoint #{value}', { value: (id || "-") }));

    if (!id) {
      toast.error(t('Invalid storage endpoint for probe run.'));
      return;
    }

    if (normalizeProbeStatus(probeResultsByEndpoint[String(id)]) === "running") {
      return;
    }

    const validation = validateStorageEndpointProbeConfig(probeConfig, { label: t('Storage endpoint') });
    if (!validation.ok) {
      toast.error(validation.message ?? t('Storage endpoint credentials are required before running a probe.'));
      return;
    }

    const request = buildStorageEndpointProbeRequestFromEndpoint(endpoint, {
      discover: false,
      timeoutSec: 20,
      uiOrigin: "admin",
      label: t('Storage endpoint'),
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
      const message = final?.ok ? "endpoint probe completed" : String(final?.errorMessage ?? t('Probe failed'));

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
        toast.success(t('Probe OK for {epName}.', { epName }));
      } else {
        toast.error(t('Probe failed for {epName}.', { epName }));
      }

      if (browser) await invalidateAll();
    } catch (e) {
      const persistedProbeAt = new Date().toISOString();
      const message = String(e?.message ?? t('Probe failed'));
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

      const template = namingDraft.trim();
      const globalTemplate = String(data?.namingPolicyGlobal?.template ?? "").trim();
      const override = Boolean(template) && template !== globalTemplate;
      await putZoneNamingPolicy(fetch, currentZoneId, { override_enabled: override, template: override ? template : null });
      namingSaved = namingDraft;

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
          naming_template: namingDraft.trim() || null,
        },
      });
      toast.success(t('Provisioning policy saved.'));
    } catch (e) {
      policyError = e?.message ?? t('Unable to save policy');
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

  function discardPolicyChanges() {
    policyDraft = buildPolicyDraftFromData(data.provisioningPolicy);
    namingDraft = namingSaved;
    policyError = null;
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
          ? t('{count} storage endpoint{value}', { count: endpoints.length, value: (endpoints.length > 1 ? "s" : "") })
          : null,
        hasAttachedStorageRoots
          ? t('{count} storage root{value}', { count: storageRoots.length, value: (storageRoots.length > 1 ? "s" : "") })
          : null,
      ].filter(Boolean);
      toast.error(t('This zone cannot be deleted while {join} remain attached.', { join: blockers.join(" and ") }));
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
        toast.success(t('Zone updated'));
        zoneModalOpen = false;
        if (browser && currentZoneId) goto(`/admin/zones/${currentZoneId}`, { invalidateAll: true });
        return;
      }

      if (zoneModalMode === "create") {
        const fallbackName = t('Zone {value}', { value: (new Date().toISOString().slice(0, 19).replace(/[-:T]/g, "")) });
        const payloadWithName: ZoneCreatePayload = {
          name: String(payload?.name ?? "").trim() || fallbackName,
          code: String(payload?.code ?? "").trim() || fallbackName,
          description: payload?.description ?? null,
        };

        if (!payloadWithName.name || !payloadWithName.code) {
          toast.error(t('Zone name and code are required.'));
          return;
        }

        const { id } = await createZone(fetch, payloadWithName);
        toast.success(t('Zone created'));
        zoneModalOpen = false;
        if (browser) goto(`/admin/zones/${id}`, { invalidateAll: true });
      }
    } catch (e) {
      reportUiError(e, t('Zone operation failed'), 'zone.operation');
    }
  }

  async function confirmDeleteZone() {
    if (!editingZone?.id) return;
    if (hasAttachedEndpoints || hasAttachedStorageRoots) {
      toast.error(t('Remove all storage endpoints and storage roots attached to this zone before deleting it.'));
      zoneModalOpen = false;
      return;
    }
    try {
      await deleteZone(fetch, editingZone.id);
      toast.success(t('Zone deleted'));
      zoneModalOpen = false;
      await goto("/admin/zones");
    } catch (e) {
      if (isDependencyDeleteError(e)) {
        zoneModalOpen = false;
        toast.error(dependencyDeleteMessage("zone", "storage endpoints or storage roots"));
        return;
      }
      reportUiError(e, t('Zone delete failed'), 'zone.delete');
    }
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
          name: String(ep?.name ?? t('Endpoint #{value}', { value: (ep?.id ?? '-') })),
          host: String(ep?.host ?? '').trim() || null,
          zoneName: String(ep?.zone_name ?? '').trim() || null
        }))
        .filter((ep) => ep.id > 0)
        .sort((a, b) => a.name.localeCompare(b.name, 'en', { sensitivity: 'base' }));
    } catch (e: any) {
      attachableEndpoints = [];
      toast.error(String(e?.message ?? t('Unable to load existing endpoints.')));
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
    void goto(`/admin/storage-endpoints/new?zone=${currentZoneId}`);
  }

  async function attachExistingEndpoint(endpointId: number) {
    if (!currentZoneId || !endpointId) return;
    attachEndpointBusyId = endpointId;
    try {
      await updateStorageEndpoint(fetch, endpointId, { zone_id: currentZoneId });
      toast.success(t('Endpoint attached to this zone.'));
      showEndpointAttachChoice = false;
      await invalidateAll();
    } catch (e: any) {
      toast.error(String(e?.message ?? t('Unable to attach endpoint.')));
    } finally {
      attachEndpointBusyId = null;
    }
  }

  $effect.pre(() => {
    activeTab = normalizeTab($page.url.searchParams.get("tab"));
  });
  // ?action=edit|add-server|delete: from the right-click menu of the zones list
  let handledAction = $state("");
  $effect.pre(() => {
    const action = $page.url.searchParams.get("action") ?? "";
    const key = `${currentZoneId}:${action}`;
    if (browser && action && data.zone && handledAction !== key) {
      handledAction = key;
      if (action === "edit") openEditZone();
      else if (action === "add-server") void openEndpointAttachChoice();
      else if (action === "delete") openDeleteZone();
      const next = new URL($page.url);
      next.searchParams.delete("action");
      void goto(`${next.pathname}${next.search}`, { replaceState: true, noScroll: true, keepFocus: true });
    }
    if (!action) handledAction = "";
  });
  $effect.pre(() => {
    const shouldOpenCreate = $page.url.searchParams.get("create") === "1";
    if (shouldOpenCreate && !handledCreateQuery) {
      handledCreateQuery = true;
      void goto('/admin/zones/new');
    }
    if (!shouldOpenCreate) {
      handledCreateQuery = false;
    }
  });
  // Browser only: during SSR the component fetch cannot resolve relative /api URLs
  $effect.pre(() => {
    if (browser) void ensureTabLoaded(activeTab);
  });
  let tabProps = $derived({
    overview: {
      zoneId: currentZoneId,
      summary,
      namingTemplateLabel: namingSaved.trim(),
      provisioningOu: resolveZoneBaseOu(data.provisioningPolicy) ?? '',
      directories,
      activity,
      onOpenEndpoint: (endpointId: number | string) => goto(`/admin/storage-endpoints/${endpointId}`),
      onOpenProvisioning: () => setTab("provisioning"),
      onAddServer: openEndpointAttachChoice,
    },
    activity: {
      activity,
    },
    provisioning: {
      zoneId: currentZoneId,
      policy: policyDraft,
      namingTemplateLabel: namingDraft,
      onChangeNamingTemplate: setNamingDraft,
      saving: policySaving,
      error: policyError,
      isDirty: isPolicyDirty,
      canSave: !hasPolicyValidationError,
      validationErrors: policyValidationErrors,
      onChange: updatePolicyDraft,
      onSave: savePolicy,
      onDiscard: discardPolicyChanges,
      onReset: resetPolicyDefaults,
    },
  });
</script>

<EntityConsoleShell>
  {#snippet header()}
  
      <div class="zone-top">
        <ZoneHero
          zone={data.zone}
          endpointCount={endpoints.length}
          healthLabel={healthSummary.healthLabel}
          {directories}
          {serversLabel}
          onEdit={openEditZone}
          onDelete={openDeleteZone}
          onAddEndpoint={openEndpointAttachChoice}
        />
        <ZoneTiles
          {summary}
          {pendingRequests}
          onOpenServers={() => setTab("overview")}
          onOpenFolders={() => goto(foldersHref)}
          onOpenRequests={() => goto("/access-requests?status=pending")}
          onOpenGuardians={() => goto(`${foldersHref}&filter=no-guardian`)}
        />
        <ZoneTodo
          {summary}
          {pendingRequests}
          ouMissing={!resolveZoneBaseOu(data.provisioningPolicy)}
          {rereadBusy}
          onOpenServer={(id) => goto(`/admin/storage-endpoints/${id}`)}
          onAddGuardians={() => goto(`${foldersHref}&filter=no-guardian&bulk=guardians`)}
          onReread={() => (showRereadConfirm = true)}
          onOpenRequests={() => goto("/access-requests?status=pending")}
          onOpenProvisioning={() => setTab("provisioning")}
        />
      </div>
    
  {/snippet}

  {#snippet tabs()}
  
      <Tabs
        tabs={zoneTabs}
        activeKey={activeTab}
        ariaLabel={t('Zone sections')}
        onChange={(key) => setTab(normalizeTab(String(key ?? 'overview')))}
      />
    
  {/snippet}

  {#if loadingTab || !activeComponent}
    <div class="zone-console__skeleton" aria-label={t('Loading tab content')}></div>
  {:else}
    {@const SvelteComponent = activeComponent}
    <SvelteComponent {...tabProps[activeTab]} />
  {/if}
</EntityConsoleShell>

<div class="visually-hidden" aria-live="polite">{policyNotice || policyError || ""}</div>


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


<EndpointAttachChoiceModal
  open={showEndpointAttachChoice}
  existingEndpoints={attachableEndpoints}
  loading={attachEndpointsLoading}
  busyAttachId={attachEndpointBusyId}
  onClose={() => (showEndpointAttachChoice = false)}
  onCreateNew={startCreateEndpointWizard}
  onAttachExisting={attachExistingEndpoint}
/>

<ConfirmActionModal
  open={showRereadConfirm}
  onClose={() => (showRereadConfirm = false)}
  onConfirm={rereadFolders}
  severity="warning"
  title={t('Read the ACLs of {count} folder(s)?', { count: summary.reread.length })}
  impactItems={[t('The worker tests each folder and reads its NTFS permissions. The results appear on each folder in the next minutes.')]}
  confirmLabel={t('Start the reads')}
/>


<ConfirmActionModal
  open={showLeaveProvisioningConfirm}
  onClose={() => {
    showLeaveProvisioningConfirm = false;
    pendingTabAfterConfirm = null;
  }}
  onConfirm={confirmLeaveProvisioningTab}
  severity="warning"
  title={t('Leave provisioning tab?')}
  subtitle={t('You have unsaved changes.')}
  impactTitle={t('Impact')}
  impactItems={[
    t('Any unsaved provisioning changes will be lost.')
  ]}
  cancelLabel={t('Stay')}
  confirmLabel={t('Leave tab')}
/>

<style>
  .zone-top {
    display: grid;
    gap: 14px;
  }
</style>
