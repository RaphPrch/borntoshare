<script lang="ts">
  import FieldError from '$lib/components/ui/FieldError.svelte';
  import { t } from '$lib/i18n';
  import Drawer from "$lib/components/ui/Drawer.svelte";
  import ConfirmActionModal from '$lib/components/ui/ConfirmActionModal.svelte';
  import EntityActionButton from "$lib/components/entity/EntityActionButton.svelte";
  import ActionFooter from "$lib/components/ui/ActionFooter.svelte";
  import Tabs from "$lib/components/ui/Tabs.svelte";
  import StatusBadge from "$lib/components/ui/StatusBadge.svelte";

  import {
    listStorageEndpoints,
    updateStorageEndpoint,
    type StorageEndpointOverview,
    type StorageEndpointUpdatePayload
  } from '$lib/api/storage-endpoints';
  import { runProbeJob } from "$lib/api/probes";
  import { resolveCredentials } from "$lib/api/credentials";
  import { createStorageRoot } from '$lib/api/storage-roots';
  import { listZones, type ZoneOverview } from "$lib/api/zones";
  import { listIdentitySources, type IdentitySourceListItem } from '$lib/api/identity-sources';
  import { pollProbeJob } from '$lib/jobs/probe-polling';
  import { showApiErrorToast } from '$lib/errors/api-toast';
  import { isValidHostname, isValidIPv4 } from '$lib/utils/host-validate';
  import { toast } from "$lib/stores/toast";

  export let open = false;
  type EditableEndpoint = {
    id?: number;
    storage_endpoint_id?: number;
    is_active?: boolean;
    zone?: { id?: number | null } | null;
    auth_secret_ref?: string | null;
    bind_password_ref?: string | null;
    [key: string]: unknown;
  };

  export let endpoint: EditableEndpoint | null = null;
  export let onClose: () => void;
  export let onSaved: (() => void) | null = null;

  let saving = false;
  let showPassword = false;
  let resolveHint: { ok: boolean; message: string } | null = null;

  let name = "";
  let description = "";
  let protocol: string = "smb";
  let host = "";
  let port: number | null = 445;
  let username = "";
  let password = "";
  let zoneId: number | null = null;
  let identitySourceId: number | null = null;
  let isActive: boolean = true;

  let touched: Record<string, boolean> = {};

  let zones: ZoneOverview[] = [];
  let zonesLoading = false;
  let zonesError: string | null = null;

  type IdentitySourceOption = IdentitySourceListItem;

  let identitySources: IdentitySourceOption[] = [];
  let identitySourcesLoading = false;
  let identitySourcesError: string | null = null;

  let existingEndpoints: StorageEndpointOverview[] = [];
  let activeTab: "endpoint" | "roots" = "endpoint";
  let rootsQuery = "";
  let discoverStatus: "idle" | "running" | "success" | "failed" = "idle";
  let discoverError: string | null = null;
  let detectedRoots: string[] = [];
  let selectedRoots: string[] = [];
  let closeConfirmOpen = false;
  let initialSnapshot: {
    name: string;
    description: string | null;
    protocol: string;
    host: string;
    port: number;
    username: string;
    zoneId: number | null;
    identitySourceId: number | null;
    isActive: boolean;
  } | null = null;

  const pick = (obj: Record<string, unknown> | null | undefined, ...keys: string[]) => {
    for (const k of keys) {
      const v = obj?.[k];
      if (v !== undefined && v !== null) return v;
    }
    return null;
  };

  const toNullableInt = (value: unknown): number | null => {
    if (value === null || value === undefined) return null;
    const raw = String(value).trim().toLowerCase();
    if (!raw || raw === "null" || raw === "undefined") return null;
    const parsed = Number(raw);
    if (!Number.isFinite(parsed)) return null;
    const asInt = Math.trunc(parsed);
    return asInt > 0 ? asInt : null;
  };

  const buildSnapshot = () => ({
    name: name.trim(),
    description: description.trim() || null,
    protocol: String(protocol || "smb").trim().toLowerCase(),
    host: host.trim(),
    port: Number(port),
    username: username.trim(),
    zoneId: toNullableInt(zoneId),
    identitySourceId: toNullableInt(identitySourceId),
    isActive: Boolean(isActive)
  });

  const normalizeRoot = (value: string) => String(value ?? "").trim();
  const rootLabel = (value: string) => {
    const normalized = normalizeRoot(value);
    const parts = normalized.split("\\");
    return parts[parts.length - 1] || normalized;
  };
  const isSelectedRoot = (value: string) => selectedRoots.includes(normalizeRoot(value));
  const toggleRoot = (value: string) => {
    const normalized = normalizeRoot(value);
    if (!normalized) return;
    if (selectedRoots.includes(normalized)) {
      selectedRoots = selectedRoots.filter((r) => r !== normalized);
    } else {
      selectedRoots = [...selectedRoots, normalized];
    }
  };

  $: zoneId = toNullableInt(zoneId);
  $: identitySourceId = toNullableInt(identitySourceId);

  $: if (open && endpoint) {
    name = String(pick(endpoint, "name", "storage_endpoint_name") ?? "");
    description = String(pick(endpoint, "description") ?? "");
    protocol = String(
      pick(endpoint, "type", "protocol", "storage_endpoint_type", "endpoint_type") ?? "smb"
    ).toLowerCase();
    host = String(pick(endpoint, "host") ?? "");
    port = pick(endpoint, "port") != null ? Number(pick(endpoint, "port")) : 445;
    // The account is stored as bind_dn (auth_username only on older rows)
    username = String(pick(endpoint, "auth_username", "bind_dn") ?? "");
    password = "";
    zoneId =
      pick(endpoint, "zone_id") != null
        ? toNullableInt(pick(endpoint, "zone_id"))
        : pick(endpoint, "zone", "id") != null
          ? toNullableInt(endpoint?.zone?.id)
          : null;
    identitySourceId = toNullableInt(pick(endpoint, "identity_source_id"));
    isActive = endpoint.is_active !== false;

    showPassword = false;
    resolveHint = null;
    touched = {};
    initialSnapshot = buildSnapshot();
    activeTab = "endpoint";
    rootsQuery = "";
    discoverStatus = "idle";
    discoverError = null;
    detectedRoots = [];
    selectedRoots = [];
  }

  $: filteredDetectedRoots = (() => {
    const query = rootsQuery.trim().toLowerCase();
    if (!query) return detectedRoots;
    return detectedRoots.filter((root) => root.toLowerCase().includes(query));
  })();

  $: if (open) {
    if (!zonesLoading && zones.length === 0) {
      zonesLoading = true;
      zonesError = null;
      listZones(fetch)
        .then((z) => (zones = z))
        .catch((e: unknown) => {
          zones = [];
          zonesError = String((e as { message?: string })?.message ?? t('Unable to load zones.'));
        })
        .finally(() => (zonesLoading = false));
    }

    if (!identitySourcesLoading && identitySources.length === 0) {
      identitySourcesLoading = true;
      identitySourcesError = null;
      listIdentitySources(fetch)
        .then((rows: IdentitySourceListItem[]) => {
          identitySources = rows;
        })
        .catch((e: unknown) => {
          identitySources = [];
          identitySourcesError = String((e as { message?: string })?.message ?? t('Unable to load identity sources.'));
        })
        .finally(() => (identitySourcesLoading = false));
    }

    if (existingEndpoints.length === 0) {
      listStorageEndpoints(fetch)
        .then((rows) => (existingEndpoints = rows))
        .catch(() => (existingEndpoints = []));
    }
  }

  function touch(field: "name" | "host" | "port" | "username") {
    touched = { ...touched, [field]: true };
  }

  function normalizedHost(value?: string | null): string {
    return String(value ?? "").trim().toLowerCase();
  }

  function resolveHostInput() {
    const value = host.trim();
    if (!value) {
      resolveHint = { ok: false, message: t('Type un hostname ou une IP.') };
      return;
    }
    if (isValidIPv4(value)) {
      resolveHint = { ok: true, message: t('IP valide.') };
      return;
    }
    if (isValidHostname(value)) {
      resolveHint = { ok: true, message: t('Hostname valide.') };
      return;
    }
    resolveHint = { ok: false, message: t('Format hostname/IP invalide.') };
  }

  const required = (v?: string | number | null) =>
    v !== undefined && v !== null && String(v).trim().length > 0;

  $: currentNormalizedHost = normalizedHost(host);
  $: duplicateEndpoint = existingEndpoints.find((ep) => {
    const id = Number(ep?.id ?? 0);
    const currentId = Number(endpoint?.id ?? endpoint?.storage_endpoint_id ?? 0);
    if (id && currentId && id === currentId) return false;
    const candidateHost = normalizedHost(String(ep?.host ?? ""));
    return Boolean(candidateHost && candidateHost === currentNormalizedHost);
  });

  $: errName = Boolean(touched.name) && !required(name);
  $: errHost = Boolean(touched.host) && !required(host);
  $: errHostFormat = Boolean(touched.host) && required(host) && !isValidIPv4(host) && !isValidHostname(host);
  $: errPort = Boolean(touched.port) && (!required(port) || Number(port) < 1 || Number(port) > 65535);
  $: errUsername = Boolean(touched.username) && !required(username);

  $: activeAdIdentitySources = identitySources.filter((s) => {
    const kind = String(s?.type ?? "").trim().toUpperCase();
    const active = s?.is_active !== false;
    return active && (kind === "AD" || kind === "LDAP" || kind === "LDAPS");
  });

  $: canSave =
    required(name) &&
    required(host) &&
    (isValidIPv4(host) || isValidHostname(host)) &&
    required(port) &&
    Number(port) >= 1 &&
    Number(port) <= 65535 &&
    zoneId !== null &&
    required(username) &&
    !duplicateEndpoint;
  $: endpointDirty = JSON.stringify(buildSnapshot()) !== JSON.stringify(initialSnapshot ?? buildSnapshot());
  $: rootsDirty = selectedRoots.length > 0;
  $: isDirty = endpointDirty || rootsDirty || Boolean(password.trim());
  $: endpointSaveReason = !required(name)
    ? t('Name is required.')
    : !required(host)
      ? t('Hostname or IP is required.')
      : (!isValidIPv4(host) && !isValidHostname(host))
        ? t('Enter a valid hostname or IP.')
        : !required(port) || Number(port) < 1 || Number(port) > 65535
          ? t('Port must be between 1 and 65535.')
          : zoneId === null
            ? t('Select a zone first.')
            : !required(username)
              ? t('Username is required.')
              : duplicateEndpoint
                ? t('A storage endpoint with the same host already exists.')
                : null;

  function requestClose() {
    if (saving || discoverStatus === 'running') return;
    if (isDirty) {
      closeConfirmOpen = true;
      return;
    }
    onClose?.();
  }

  function discardAndClose() {
    closeConfirmOpen = false;
    onClose?.();
  }

  async function save() {
    if (!endpoint) return;

    const endpointNumericId = Number(pick(endpoint, "id", "storage_endpoint_id") ?? 0);
    if (!endpointNumericId) {
      toast.error(t('Endpoint id invalide.'));
      return;
    }

    if (!canSave) {
      toast.error(t('Champs manquants.'));
      return;
    }

    if (duplicateEndpoint) {
      toast.error(t('A file server with the same IP/hostname already exists.'));
      return;
    }

    saving = true;
    try {
      let secretRef: string | null =
        String(endpoint?.auth_secret_ref ?? endpoint?.bind_password_ref ?? "").trim() || null;
      const current = buildSnapshot();
      const previous = initialSnapshot ?? current;

      if (password.trim()) {
        if (!current.username) {
          toast.error(t('Username required to update password.'));
          saving = false;
          return;
        }
        const resolved = await resolveCredentials(fetch, {
          username: current.username,
          password: String(password),
          secret_ref: secretRef
        }, {
          secretName: `storage-endpoint/${protocol}/${name.trim() || host.trim() || "endpoint"}`,
          mode: "edit"
        });
        secretRef = resolved.secret_ref ?? secretRef;
      }

      const updates: StorageEndpointUpdatePayload = {};

      if (current.name !== previous.name) updates.name = current.name;
      if (current.description !== previous.description) updates.description = current.description;
      if (current.protocol !== previous.protocol) {
        updates.endpoint_type = current.protocol;
        updates.protocol = current.protocol;
      }
      if (current.host !== previous.host) updates.host = current.host;
      if (current.port !== previous.port) updates.port = current.port;
      if (current.zoneId !== previous.zoneId) updates.zone_id = current.zoneId;
      if (current.identitySourceId !== previous.identitySourceId) {
        updates.identity_source_id = current.identitySourceId;
      }
      if (current.isActive !== previous.isActive) updates.is_active = current.isActive;
      if (current.username !== previous.username) {
        updates.bind_dn = current.username;
      }

      if (password.trim()) {
        updates.auth_type = "ntlm";
        updates.bind_password_ref = secretRef;
      }

      if (Object.keys(updates).length === 0) {
        onClose?.();
        onSaved?.();
        return;
      }

      await updateStorageEndpoint(fetch, endpointNumericId, updates);

      initialSnapshot = current;
      password = "";
      showPassword = false;

      toast.success(t('Storage endpoint updated.'));
      onClose?.();
      onSaved?.();
    } catch (e) {
      const code = String(e?.code ?? e?.details?.error?.code ?? "").trim();
      if (code === "SECRET_PERSISTENCE_FAILURE") {
        toast.error(t('Secret could not be persisted. Endpoint was not saved.'));
      } else if (code === "SECRET_DECRYPT_FAILED") {
        toast.error(t('Broker could not encrypt or store the password.'));
      } else if (code === "SECRET_NOT_FOUND") {
        toast.error(t('The secure password for this endpoint was not found. Re-save credentials.'));
      } else {
        showApiErrorToast(e, "Unable to save storage endpoint.");
      }
    } finally {
      saving = false;
    }
  }

  async function discoverStorageRoots() {
    if (!canSave) {
      toast.error(t('Complete endpoint fields before running discovery.'));
      return;
    }

    discoverStatus = "running";
    discoverError = null;
    detectedRoots = [];
    selectedRoots = [];

    try {
      let secretRef: string | null =
        String(endpoint?.auth_secret_ref ?? endpoint?.bind_password_ref ?? "").trim() || null;

      if (password.trim()) {
        if (!username.trim()) {
          discoverStatus = "failed";
          discoverError = "Username required to resolve password.";
          return;
        }
        const resolved = await resolveCredentials(fetch, {
          username: username.trim(),
          password: String(password),
          secret_ref: secretRef
        }, {
          secretName: `storage-endpoint/${protocol}/${name.trim() || host.trim() || "endpoint"}`,
          mode: "edit"
        });
        secretRef = resolved.secret_ref ?? secretRef;
      }

      const targetHost = host.trim();
      if (!targetHost) {
        discoverStatus = "failed";
        discoverError = "Hostname / IP invalide";
        return;
      }

      const { job_id } = await runProbeJob(fetch, {
        kind: "storage-endpoint",
        protocol: "smb",
        scope: "read",
        target: {
          host: targetHost,
          port: Number(port)
        },
        auth: {
          mode: "ntlm",
          username: username.trim(),
          secret_ref: secretRef ?? undefined,
          password: secretRef ? undefined : password
        },
        options: {
          timeout_sec: 30,
          discover: true
        },
        context: { ui_origin: "edit-modal" }
      });

      const polled = await pollProbeJob(fetch, job_id, {
        intervalMs: 3000,
        intervalMsByAttempt: (attempt) => (attempt < 2 ? 3000 : attempt < 6 ? 5000 : 8000)
      });

      if (polled.status === "success") {
        const job: any = polled.payload;
        const roots =
          (job?.result?.details?.roots as string[]) ||
          (job?.result?.roots as string[]) ||
          [];
        detectedRoots = Array.isArray(roots) ? roots.map(normalizeRoot).filter(Boolean) : [];
        discoverStatus = "success";
      } else {
        discoverStatus = "failed";
        discoverError = polled.errorMessage ?? t('Discovery failed');
      }
    } catch (e) {
      discoverStatus = "failed";
      discoverError = "Unable to run discovery.";
    }
  }

  async function saveSelectedRoots() {
    const endpointNumericId = Number(pick(endpoint, "id", "storage_endpoint_id") ?? 0);
    if (!endpointNumericId) {
      toast.error(t('Endpoint id invalide.'));
      return;
    }
    if (selectedRoots.length === 0) {
      toast.error(t('No storage root selected.'));
      return;
    }

    saving = true;
    try {
      const created = await Promise.allSettled(
        selectedRoots.map((locator) =>
          createStorageRoot(fetch, {
            storage_endpoint_id: endpointNumericId,
            name: locator.split("\\").pop() || locator,
            root_path: locator,
            status: "active"
          })
        )
      );

      const ok = created.filter((r) => r.status === "fulfilled").length;
      const ko = created.length - ok;
      toast.success(`Storage roots created: ${ok}${ko > 0 ? ` · failures: ${ko}` : ""}.`);
      onSaved?.();
    } catch (e) {
      showApiErrorToast(e, "Unable to create storage roots.");
    } finally {
      saving = false;
    }
  }
</script>

{#if open}
<Drawer
  {open}
  onClose={requestClose}
  title={t('Edit storage endpoint')}
  subtitle={t('Update identity, target and credentials.')}
  iconClass="bi bi-hdd-network"
  ariaLabelledby="se-edit-title"
  size="lg"
  rootClass="se-edit-drawer"
  showFooter={true}
>
  <svelte:fragment slot="header-meta">
    <StatusBadge compact showDot={false} variant="info" label={`SMB · ${t('Windows / Samba shares')}`} />
  </svelte:fragment>

  <div class="se-edit">
    <Tabs
      tabs={[
        { key: "endpoint", label: t('Endpoint'), icon: "bi-hdd-network" },
        { key: "roots", label: t('Storage roots'), icon: "bi-folder2" }
      ]}
      activeKey={activeTab}
      onChange={(key) => (activeTab = key === "roots" ? "roots" : "endpoint")}
      ariaLabel={t('Edit storage endpoint')}
    />

    {#if activeTab === "endpoint"}

    <div class="se-form-block">
      <h3>{t('Identity')}</h3>
      <div class="se-form-grid se-form-grid--identity">
        <div>
          <label for="se-edit-name">{t('Name')} <span class="req">*</span></label>
          <input
            id="se-edit-name"
            class="se-input"
            class:invalid={errName}
            bind:value={name}
            placeholder={t('Main file server')}
            on:blur={() => touch("name")}
          />
          {#if errName}
            <FieldError>{t('Name is required.')}</FieldError>
          {/if}
        </div>

        <div>
          <label for="se-edit-description">{t('Description')}</label>
          <input
            id="se-edit-description"
            class="se-input"
            bind:value={description}
            placeholder={t('Production SMB storage')}
          />
        </div>
      </div>
    </div>

    <div class="se-form-block">
      <h3>{t('Zone')}</h3>
      <div class="se-form-grid se-form-grid--identity">
        <div>
          <label for="se-edit-zone">{t('Existing zone')} <span class="req">*</span></label>
          <select id="se-edit-zone" class="se-input" bind:value={zoneId} disabled={zonesLoading}>
            <option value="">{t('Select zone')}</option>
            {#each zones as z (z.id)}
              <option value={z.id}>{z.name}</option>
            {/each}
          </select>
          {#if zonesLoading}
            <div class="se-field-hint">{t('Loading zones…')}</div>
          {/if}
          {#if zonesError}
            <FieldError>{zonesError}</FieldError>
          {/if}
        </div>

        <div>
          <label for="se-edit-identity-source">{t('Identity source (AD)')}</label>
          <select id="se-edit-identity-source" class="se-input" bind:value={identitySourceId}>
            <option value="">{t('No identity source (optional)')}</option>
            {#each activeAdIdentitySources as src (src.id)}
              <option value={src.id}>{src.name ?? t('Source #{id}', { id: src.id })}</option>
            {/each}
          </select>
          {#if identitySourcesLoading}
            <div class="se-field-hint">{t('Loading identity sources…')}</div>
          {/if}
          {#if identitySourcesError}
            <FieldError>{identitySourcesError}</FieldError>
          {/if}
          {#if !identitySourcesLoading && !identitySourcesError && activeAdIdentitySources.length === 0}
            <div class="se-field-hint">{t('No active AD identity source available (optional field).')}</div>
          {/if}
        </div>
      </div>
    </div>

    <div class="se-form-block">
      <h3>{t('Target')}</h3>
      <div class="se-form-grid se-form-grid--target">
        <div>
          <label for="se-edit-host">{t('Hostname / IP')} <span class="req">*</span></label>
          <div class="b2s-input-with-action">
            <input
              id="se-edit-host"
              class="se-input"
              class:invalid={errHost || errHostFormat}
              bind:value={host}
              placeholder={t('fileserver.domain.local ou 10.0.0.12')}
              on:blur={() => touch("host")}
            />
            <button
              class="b2s-input-action"
              type="button"
              tabindex="-1"
              aria-label={t('Resolve host')}
              on:click={resolveHostInput}
            >
              <i class="bi bi-search" aria-hidden="true"></i>
            </button>
          </div>
          {#if errHost}
            <FieldError>{t('Hostname/IP is required.')}</FieldError>
          {/if}
          {#if errHostFormat}
            <FieldError>{t('Invalid hostname/IP.')}</FieldError>
          {/if}
          {#if duplicateEndpoint}
            <FieldError>{t('A file server with the same IP/hostname already exists.')}</FieldError>
          {/if}
          {#if resolveHint}
            <div class={`se-field-hint ${resolveHint.ok ? "ok" : ""}`}>{resolveHint.message}</div>
          {/if}
        </div>

        <div>
          <label for="se-edit-port">{t('Port')} <span class="req">*</span></label>
          <input
            id="se-edit-port"
            class="se-input"
            type="number"
            min="1"
            max="65535"
            class:invalid={errPort}
            bind:value={port}
            on:blur={() => touch("port")}
          />
          {#if errPort}
            <FieldError>{t('Port must be between 1 and 65535.')}</FieldError>
          {/if}
        </div>
      </div>
    </div>

    <div class="se-form-block">
      <h3>{t('Credentials')}</h3>
      <div class="se-form-grid se-form-grid--creds">
        <div>
          <label for="se-edit-username">{t('Username')} <span class="req">*</span></label>
          <input
            id="se-edit-username"
            class="se-input"
            class:invalid={errUsername}
            bind:value={username}
            placeholder="DOMAIN\service-account"
            on:blur={() => touch("username")}
          />
          {#if errUsername}
            <FieldError>{t('Username is required.')}</FieldError>
          {/if}
        </div>

        <div>
          <label for="se-edit-password">{t('Password')}</label>
          <div class="b2s-input-with-action">
            <input
              id="se-edit-password"
              class="se-input"
              type={showPassword ? "text" : "password"}
              bind:value={password}
              placeholder={t('Leave empty to keep current')}
            />
            <button
              class="b2s-input-action"
              type="button"
              tabindex="-1"
              aria-label={showPassword ? t('Hide password') : t('Show password')}
              on:click={() => (showPassword = !showPassword)}
            >
              <i class={`bi ${showPassword ? "bi-eye-slash" : "bi-eye"}`} aria-hidden="true"></i>
            </button>
          </div>
        </div>
      </div>
    </div>

    <label class="se-edit-switch" for="se-active">
      <input class="cap-switch" id="se-active" type="checkbox" bind:checked={isActive} />
      <span>
        <strong>{isActive ? t('Enabled') : t('Disabled')}</strong>
        <small>{t('A disabled file server is no longer probed and its roots cannot be requested.')}</small>
      </span>
    </label>

    {:else}
    <div class="se-form-block">
      <h3>{t('Storage roots discovery')}</h3>
      <p class="se-field-hint">{t('Run SMB share discovery and select roots to govern.')}</p>

      {#if discoverStatus === "failed"}
        <FieldError>{discoverError ?? t('Discovery failed')}</FieldError>
      {/if}

      <div class="se-form-block">
        <label for="se-edit-roots-filter">{t('Filter roots')}</label>
        <input id="se-edit-roots-filter" class="se-input" bind:value={rootsQuery} placeholder={t('Filter discovered roots…')} />
      </div>

      <div class="se-root-rows">
        {#if filteredDetectedRoots.length === 0}
          <div class="se-field-hint">{t('No discovered roots yet.')}</div>
        {:else}
          {#each filteredDetectedRoots as r}
            <button type="button" class={`se-root-row ${isSelectedRoot(r) ? 'selected' : ''}`} on:click={() => toggleRoot(r)}>
              <i class="bi bi-folder-fill se-root-row__icon" aria-hidden="true"></i>
              <div class="se-root-row__main">
                <div class="se-root-row__name">{rootLabel(r)}</div>
                <div class="se-root-row__path mono">{r}</div>
              </div>
              <span class="se-root-row__action">
                <i class={`bi ${isSelectedRoot(r) ? 'bi-check-circle-fill' : 'bi-chevron-right'}`} aria-hidden="true"></i>
              </span>
            </button>
          {/each}
        {/if}
      </div>

      <div class="se-field-hint">{t('Selected: {selectedRootsCount}', { selectedRootsCount: selectedRoots.length })}</div>
    </div>
    {/if}
  </div>

  <svelte:fragment slot="footer">
    <ActionFooter align="end" className="se-edit-drawer__actions">
      {#if activeTab === "endpoint"}
        <EntityActionButton variant="secondary" label={t('Cancel')} disabled={saving} onClick={requestClose} />
        <EntityActionButton
          variant="primary"
          icon={saving ? "bi-arrow-repeat" : "bi-check2"}
          busy={saving}
          label={saving ? t('Saving…') : t('Save changes')}
          disabled={saving || !canSave}
          onClick={save}
        />
        {#if endpointSaveReason}
          <div class="se-edit-disabled-reason">{endpointSaveReason}</div>
        {/if}
      {:else}
        <EntityActionButton
          variant="secondary"
          icon={discoverStatus === "running" ? "bi-arrow-repeat" : "bi-search"}
          busy={discoverStatus === "running"}
          label={discoverStatus === "running" ? t('Discovering…') : t('Discover')}
          disabled={discoverStatus === "running" || saving}
          onClick={discoverStorageRoots}
        />
        <EntityActionButton
          variant="primary"
          icon={saving ? "bi-arrow-repeat" : "bi-folder-plus"}
          busy={saving}
          label={saving ? t('Saving…') : t('Create selected roots')}
          disabled={saving || selectedRoots.length === 0}
          onClick={saveSelectedRoots}
        />
        {#if selectedRoots.length === 0}
          <div class="se-edit-disabled-reason">{t('Select at least one storage root first.')}</div>
        {/if}
      {/if}
      {#if isDirty}
        <div class="se-edit-unsaved">{t('Unsaved changes')}</div>
      {/if}
    </ActionFooter>
  </svelte:fragment>
</Drawer>
{/if}

<ConfirmActionModal
  open={closeConfirmOpen}
  onClose={() => (closeConfirmOpen = false)}
  onConfirm={discardAndClose}
  title={t('Discard unsaved changes')}
  subtitle={t('Your edits have not been saved.')}
  confirmLabel={t('Discard changes')}
  confirmVariant="warning"
  severity="warning"
  impactItems={[t('All unsaved edits in this drawer will be lost.')]}
/>

<style>
  :global(.se-edit-drawer .b2s-entity-drawer__footer) {
    padding: 16px 24px;
  }

  .se-edit {
    display: grid;
    gap: 16px;
  }

  .se-edit :global(.se-form-block) {
    margin-bottom: 0;
  }

  .se-edit-switch {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 12px 14px;
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-md);
    cursor: pointer;
  }

  .se-edit-switch strong,
  .se-edit-switch small {
    display: block;
  }

  .se-edit-switch strong {
    font-size: var(--b2s-fs-sm);
    font-weight: 600;
  }

  .se-edit-switch small {
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
  }

  .se-edit-drawer__actions {
    width: 100%;
    display: flex;
    justify-content: flex-end;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }

  .se-edit-unsaved,
  .se-edit-disabled-reason {
    width: 100%;
    text-align: right;
    font-size: var(--b2s-fs-xs);
    font-weight: 600;
  }

  .se-edit-unsaved {
    color: var(--b2s-color-warning-strong);
  }

  .se-edit-disabled-reason {
    color: var(--b2s-color-text-muted);
  }

  @media (max-width: 820px) {
    .se-edit :global(.se-form-grid--identity),
    .se-edit :global(.se-form-grid--target),
    .se-edit :global(.se-form-grid--creds) {
      grid-template-columns: 1fr;
    }
  }
</style>
