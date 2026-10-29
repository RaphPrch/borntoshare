<script lang="ts">
  import FieldError from '$lib/components/ui/FieldError.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import ChoiceCard from '$lib/components/ui/ChoiceCard.svelte';
  import { t } from '$lib/i18n';
  import IdentityBrowserModal from '$lib/components/identity/IdentityBrowserModal.svelte';
  import AppModal from '$lib/components/ui/AppModal.svelte';
  import { checkExistingAccess, createAccessRequest, type CheckExistingAccessResponse } from '$lib/api/access-requests';
  import { getStorageRootOverview, listStorageRootsContext, type StorageRootContext } from '$lib/api/storage-roots';
  import { initials } from '$lib/utils/format';
  import {
    type PrincipalSearchItem,
    principalKey,
    principalLabel,
    principalSubtitle
  } from '$lib/utils/principal-search';
  import { toast } from '$lib/stores/toast';

  export let open = false;
  export let prefillStorageRootId: number | null = null;
  export let prefillAccessLevel: string | null = null;
  /** Beneficiary chosen beforehand (⌘K palette « Request access for… ») */
  export let prefillPrincipal: PrincipalSearchItem | null = null;
  export let onClose: () => void = () => {};
  export let onCreated: () => void = () => {};

  // Only READ and WRITE exist: an AD group per level of the storage root
  type AccessChoice = 'read' | 'contribution';
  type TtlPreset = '7' | '30' | '90' | 'custom';

  let roots: StorageRootContext[] = [];
  let loadingRoots = false;
  let storageRootId = '';
  let justification = '';
  let submitting = false;
  let selectedAccess: AccessChoice = 'read';
  let ttlPreset: TtlPreset = '30';
  let customTtlDays = 45;
  let showAdBrowser = false;
  let selectedPrincipals: PrincipalSearchItem[] = [];
  let selectedPrincipalKeys: string[] = [];
  let overviewByRootId: Record<string, Record<string, unknown>> = {};
  let overviewLoadingRootId: number | null = null;
  let overviewLoadSeq = 0;
  let wasOpen = false;
  let existingAccessCheckSeq = 0;
  let existingAccessCheckLoading = false;
  let existingAccessCheckMessage = '';
  let existingAccessCheckTone: 'neutral' | 'success' | 'warning' | 'error' = 'neutral';
  let existingAccessBlocking = false;

  let errors = {
    storageRootId: '',
    permissions: '',
    principal: '',
    justification: '',
    ttl: ''
  };

  $: selectedRoot = roots.find((root) => Number(root.id) === Number(storageRootId)) ?? null;
  $: rootsByZone = Object.entries(
    roots.reduce((acc: Record<string, StorageRootContext[]>, root) => {
      (acc[rootZone(root)] ??= []).push(root);
      return acc;
    }, {})
  )
    .map(([zone, items]) => [zone, [...items].sort((a, b) => rootName(a).localeCompare(rootName(b), 'fr', { numeric: true }))] as const)
    .sort((a, b) => a[0].localeCompare(b[0], 'fr'));
  $: selectedRootOverview = selectedRoot ? (overviewByRootId[String(Number(selectedRoot.id))] ?? null) : null;
  $: selectedPermissions = [selectedAccess];
  $: selectedPrincipalsCount = selectedPrincipals.length;
  $: selectedPrincipal = selectedPrincipals[0] ?? null;
  $: existingAccessCheckKey = open
    ? [storageRootId, selectedAccess, selectedPrincipalKeys.join('|')].join(':')
    : '';
  $: ttlDays = ttlPreset === 'custom' ? Number(customTtlDays) : Number(ttlPreset);
  $: TTL_PRESETS = [['7', t('7 days')], ['30', t('30 days')], ['90', t('90 days')], ['custom', t('Custom')]] as Array<[TtlPreset, string]>;
  $: provisioningChecks = buildProvisioningChecks();
  $: blockingProvisioningChecks = provisioningChecks.filter((check) => check.blocking);
  $: canSubmit =
    Boolean(selectedRoot) &&
    selectedPermissions.length > 0 &&
    selectedPrincipalsCount > 0 &&
    Number.isFinite(ttlDays) &&
    ttlDays > 0 &&
    justification.trim().length > 0 &&
    blockingProvisioningChecks.length === 0 &&
    !existingAccessBlocking &&
    !existingAccessCheckLoading;

  const compact = (value: unknown, fallback = '—') => String(value ?? '').trim() || fallback;

  function normalizePrefillAccessChoice(value: unknown): AccessChoice {
    const raw = String(value ?? '').trim().toLowerCase();
    if (raw === 'write' || raw === 'contribution' || raw === 'rw') return 'contribution';
    return 'read';
  }

  function rootName(root: any): string {
    return compact(root?.name ?? root?.storage_root_name ?? root?.root_name, root?.id ? t('Root #{id}', { id: root.id }) : '—');
  }

  function rootPath(root: any): string {
    return compact(root?.root_path ?? root?.normalized_root_path ?? root?.path);
  }

  function rootZone(root: any): string {
    return compact(root?.zone_name ?? root?.zone_code ?? root?.storage_zone_name);
  }

  function endpointName(root: any): string {
    return compact(root?.storage_endpoint_name ?? root?.endpoint_name);
  }

  function guardianCount(root: any): number {
    const values = [
      root?.guardian_count,
      root?.guardians_count,
      Array.isArray(root?.guardians) ? root.guardians.length : null,
      Array.isArray(root?.owners) ? root.owners.filter((owner: any) => String(owner?.role ?? '').toLowerCase() === 'guardian').length : null
    ];
    for (const value of values) {
      const n = Number(value);
      if (Number.isFinite(n) && n >= 0) return n;
    }
    return 0;
  }

  function selectedAccessCode(): string {
    if (selectedAccess === 'contribution') return 'WRITE';
    return 'READ';
  }

  function approvalLabel(): string {
    const count = guardianCount(selectedRoot);
    if (count > 0) return t('{count} approver{value} required', { count, value: (count > 1 ? 's' : '') });
    return t('Guardian review');
  }

  function resetErrors() {
    errors = {
      storageRootId: '',
      permissions: '',
      principal: '',
      justification: '',
      ttl: ''
    };
  }

  function resetFlow() {
    showAdBrowser = false;
    selectedPrincipals = prefillPrincipal ? [prefillPrincipal] : [];
    selectedPrincipalKeys = prefillPrincipal ? [principalKey(prefillPrincipal as Record<string, unknown>) || 'principal-0'] : [];
    selectedAccess = normalizePrefillAccessChoice(prefillAccessLevel);
    ttlPreset = '30';
    customTtlDays = 45;
    justification = '';
    existingAccessCheckMessage = '';
    existingAccessCheckTone = 'neutral';
    existingAccessBlocking = false;
    existingAccessCheckLoading = false;
    resetErrors();
  }

  $: if (open) {
    selectedAccess = normalizePrefillAccessChoice(prefillAccessLevel);
  }

  function clearExistingAccessCheck() {
    existingAccessCheckMessage = '';
    existingAccessCheckTone = 'neutral';
    existingAccessBlocking = false;
    existingAccessCheckLoading = false;
  }

  async function loadSelectedRootOverview(rootId: number) {
    if (!Number.isFinite(rootId) || rootId <= 0 || overviewByRootId[String(rootId)]) return;
    const seq = ++overviewLoadSeq;
    overviewLoadingRootId = rootId;
    try {
      const overview = await getStorageRootOverview(fetch, rootId);
      if (seq !== overviewLoadSeq) return;
      overviewByRootId = { ...overviewByRootId, [String(rootId)]: overview };
    } catch {
      if (seq === overviewLoadSeq) {
        overviewByRootId = {
          ...overviewByRootId,
          [String(rootId)]: { _load_error: t('Unable to load storage root validation details') }
        };
      }
    } finally {
      if (seq === overviewLoadSeq) overviewLoadingRootId = null;
    }
  }

  $: if (open && Number(storageRootId) > 0) {
    void loadSelectedRootOverview(Number(storageRootId));
  }

  async function runExistingAccessCheck() {
    const rootId = Number(storageRootId);
    if (!open || !Number.isFinite(rootId) || rootId <= 0 || selectedPrincipals.length === 0) {
      clearExistingAccessCheck();
      return;
    }

    const seq = ++existingAccessCheckSeq;
    existingAccessCheckLoading = true;
    existingAccessCheckMessage = '';
    existingAccessBlocking = false;
    existingAccessCheckTone = 'neutral';

    try {
      const results = await Promise.all(
        selectedPrincipals.map(async (principal) => {
          const result = await checkExistingAccess(fetch, {
            storage_root_id: rootId,
            access_level: selectedAccessCode(),
            requested_principal: toRequestedPrincipalPayload(principal)
          });
          return { principal, result: result as CheckExistingAccessResponse };
        })
      );

      if (seq !== existingAccessCheckSeq) return;

      const blockingResult = results.find(({ result }) => !result?.can_request);
      if (blockingResult) {
        existingAccessBlocking = true;
        existingAccessCheckTone = 'error';
        existingAccessCheckMessage = `${principalLabel(blockingResult.principal)} · ${blockingResult.result.message || t('This request cannot be submitted.')}`;
        return;
      }

      const elevationResult = results.find(({ result }) => result?.code === 'ELEVATION_ALLOWED' || result?.reason === 'ELEVATION_ALLOWED');
      if (elevationResult) {
        existingAccessCheckTone = 'warning';
        existingAccessCheckMessage = `${principalLabel(elevationResult.principal)} · ${elevationResult.result.message || t('This request will be handled as an elevation.')}`;
        return;
      }

      existingAccessCheckTone = 'success';
      existingAccessCheckMessage =
        results.length > 1
          ? t('{count} beneficiaries can receive this request.', { count: results.length })
          : t('No existing access blocks this request.');
    } catch {
      if (seq !== existingAccessCheckSeq) return;
      existingAccessCheckTone = 'neutral';
      existingAccessCheckMessage = t('Existing access could not be checked; it will be checked on submission.');
    } finally {
      if (seq === existingAccessCheckSeq) existingAccessCheckLoading = false;
    }
  }

  $: if (existingAccessCheckKey) {
    void runExistingAccessCheck();
  } else {
    clearExistingAccessCheck();
  }

  function buildProvisioningChecks() {
    if (!selectedRoot) return [];
    const checks: Array<{ key: string; label: string; detail: string; tone: 'success' | 'warning' | 'error' | 'pending'; blocking: boolean }> = [];
    const overview = selectedRootOverview as any;
    const loading = overviewLoadingRootId === Number(selectedRoot.id);
    if (loading && !overview) {
      return [
        {
          key: 'loading',
          label: t('Checking'),
          detail: t('Loading the storage root context.'),
          tone: 'pending',
          blocking: true
        }
      ];
    }
    if (overview?._load_error) {
      return [
        {
          key: 'overview_load',
          label: t('Check unavailable'),
          detail: String(overview._load_error),
          tone: 'error',
          blocking: true
        }
      ];
    }

    const availability = String(
      overview?.effective_availability ??
        overview?.last_probe_status ??
        overview?.status ??
        (selectedRoot as any)?.last_probe_status ??
        ''
    ).toLowerCase();
    const reachable = ['reachable', 'success', 'healthy', 'available'].some((token) => availability.includes(token));
    const unreachable = ['unreachable', 'failed', 'error', 'blocked'].some((token) => availability.includes(token));
    checks.push({
      key: 'reachability',
      label: t('Storage root reachable'),
      detail: reachable
        ? t('Last probe OK.')
        : unreachable
          ? String(overview?.last_probe_message ?? overview?.revalidation_reason ?? t('The last probe reports the storage root unreachable.'))
          : t('No recent probe confirms that the storage root is reachable.'),
      tone: reachable ? 'success' : 'error',
      blocking: !reachable
    });

    return checks;
  }

  async function loadRoots() {
    if (loadingRoots) return;
    loadingRoots = true;
    try {
      const rows = await listStorageRootsContext(fetch);
      roots = rows;

      const candidate = Number(prefillStorageRootId ?? 0);
      if (candidate > 0 && roots.some((root) => Number(root.id) === candidate)) {
        storageRootId = String(candidate);
      } else if (candidate > 0) {
        storageRootId = '';
        errors.storageRootId = t('This storage root is not available.');
      } else if (!storageRootId && roots.length > 0) {
        storageRootId = String(roots[0].id);
      }
    } catch {
      toast.error(t('Unable to load storage roots'));
      roots = [];
    } finally {
      loadingRoots = false;
    }
  }

  $: {
    if (open && !wasOpen) {
      wasOpen = true;
      resetFlow();
      loadRoots();
    }
    if (!open && wasOpen) {
      wasOpen = false;
    }
  }

  function close() {
    if (submitting) return;
    onClose();
  }

  function validate() {
    resetErrors();
    const rootId = Number(storageRootId);
    if (!Number.isFinite(rootId) || rootId <= 0) {
      errors.storageRootId = t('Select a storage root');
    }
    if (selectedPermissions.length === 0) {
      errors.permissions = t('Select an access level');
    }
    if (selectedPrincipals.length === 0) {
      errors.principal = t('Select a beneficiary from the identity source');
    }
    if (!Number.isFinite(ttlDays) || ttlDays <= 0) {
      errors.ttl = t('Invalid duration');
    }
    if (!justification.trim()) {
      errors.justification = t('A justification is required');
    }
    if (blockingProvisioningChecks.length > 0) {
      errors.permissions = blockingProvisioningChecks[0]?.detail || t('The request cannot be provisioned.');
    }
    if (existingAccessBlocking && !errors.principal) {
      errors.principal = existingAccessCheckMessage || t('This request cannot be submitted.');
    }
    return !errors.storageRootId && !errors.permissions && !errors.principal && !errors.ttl && !errors.justification;
  }

  function computeExpiresAtIso(): string | null {
    if (!Number.isFinite(ttlDays) || ttlDays <= 0) return null;
    const end = new Date(Date.now() + ttlDays * 24 * 60 * 60 * 1000);
    return end.toISOString();
  }

  function openAdBrowser() {
    if (submitting) return;
    showAdBrowser = true;
  }

  function onConfirmAdBrowser(event: CustomEvent<any>) {
    const items = Array.isArray(event.detail?.selectedItems) ? event.detail.selectedItems : [];
    const normalized = items.filter(Boolean) as PrincipalSearchItem[];
    const keyed = normalized.map((item, index) => ({
      key: principalKey(item as Record<string, unknown>) || `principal-${index}`,
      item
    }));

    const deduplicated = keyed.reduce(
      (acc, entry) => {
        if (!entry.key || acc.seen.has(entry.key)) return acc;
        acc.seen.add(entry.key);
        acc.keys.push(entry.key);
        acc.items.push(entry.item);
        return acc;
      },
      {
        seen: new Set<string>(),
        keys: [] as string[],
        items: [] as PrincipalSearchItem[]
      }
    );

    if (deduplicated.items.length === 0) {
      toast.warning(t('No identity selected'));
      return;
    }

    selectedPrincipals = deduplicated.items;
    selectedPrincipalKeys = deduplicated.keys.slice(0, selectedPrincipals.length);
    errors.principal = '';
    showAdBrowser = false;
  }

  function onSelectIdentity(payload: any) {
    onConfirmAdBrowser({ detail: payload } as CustomEvent<any>);
  }

  function removeSelectedPrincipalByKey(key: string) {
    const idx = selectedPrincipalKeys.findIndex((itemKey) => itemKey === key);
    if (idx < 0) return;
    selectedPrincipals = selectedPrincipals.filter((_, i) => i !== idx);
    selectedPrincipalKeys = selectedPrincipalKeys.filter((_, i) => i !== idx);
  }

  const toRequestedPrincipalPayload = (principal: PrincipalSearchItem) => {
    const normalizedDn = String(principal?.dn ?? '').trim() || null;
    let normalizedUsername = String(principal?.username ?? principal?.upn ?? '').trim() || null;
    const normalizedExternalId = String(principal?.external_id ?? principal?.id ?? '').trim() || null;

    if (!normalizedDn && !normalizedUsername && normalizedExternalId) {
      normalizedUsername = normalizedExternalId;
    }

    return {
      id: String(principal?.id ?? ''),
      external_id: normalizedExternalId,
      dn: normalizedDn,
      username: normalizedUsername,
      display_name: principal?.display_name ?? null,
      email: principal?.email ?? null,
      auth_source: principal?.auth_source ?? 'ad',
      type: String(principal?.type ?? 'user').toLowerCase(),
      identity_source_id: Number(principal?.identity_source_id ?? 0) || null
    };
  };

  async function submit() {
    if (submitting) return;
    if (!validate()) return;

    const rootId = Number(storageRootId);
    const expiresAt = computeExpiresAtIso();
    submitting = true;
    try {
      for (const principal of selectedPrincipals) {
        const precheck = await checkExistingAccess(fetch, {
          storage_root_id: rootId,
          access_level: selectedAccessCode(),
          requested_principal: toRequestedPrincipalPayload(principal)
        });
        if (!precheck?.can_request) {
          existingAccessBlocking = true;
          existingAccessCheckTone = 'error';
          existingAccessCheckMessage = `${principalLabel(principal)} · ${precheck?.message || t('This request cannot be submitted.')}`;
          throw new Error(existingAccessCheckMessage);
        }
        await createAccessRequest(fetch, {
          storage_root_id: rootId,
          permissions: selectedPermissions,
          expires_at: expiresAt,
          justification: justification.trim(),
          requested_principal: toRequestedPrincipalPayload(principal)
        });
      }

      toast.success(
        selectedPrincipalsCount > 1
          ? t('{selectedPrincipalsCount} access requests created', { selectedPrincipalsCount })
          : t('Access request created')
      );
      onCreated();
      onClose();
    } catch (error: any) {
      toast.error(String(error?.message || t('Failed to create request')));
    } finally {
      submitting = false;
    }
  }
</script>

<AppModal
  {open}
  onClose={close}
  size="lg"
  iconClass="bi bi-folder-plus"
  title={t('Request governed access')}
  subtitle={t('Choose the storage root, the access level, who needs it and for how long.')}
  closeOnBackdrop={false}
>
  <div class="nar">
    <section class="nar-step">
      <h3><span>1</span>{t('Storage root')}</h3>
      <select class="b2s-select" aria-label={t('Storage root')} bind:value={storageRootId} disabled={loadingRoots || submitting} class:is-invalid={Boolean(errors.storageRootId)}>
        {#if loadingRoots}<option value="">{t('Loading...')}</option>{/if}
        {#each rootsByZone as [zone, items] (zone)}
          <optgroup label={zone}>
            {#each items as root (root.id)}
              <option value={String(root.id)}>{rootName(root)} — {rootPath(root)}</option>
            {/each}
          </optgroup>
        {/each}
      </select>
      {#if selectedRoot}
        <p class="nar-hint">
          <i class="bi bi-shield-check" aria-hidden="true"></i>
          {endpointName(selectedRoot)} · {approvalLabel()}
          <a href={`/storage-roots?selected=${Number(selectedRoot.id)}`}>{t('Review policy')}</a>
        </p>
      {/if}
      {#if errors.storageRootId}<FieldError>{errors.storageRootId}</FieldError>{/if}
    </section>

    <section class="nar-step">
      <h3><span>2</span>{t('Access needed')}</h3>
      <div class="nar-choices">
        <ChoiceCard
          icon="bi-eye"
          title={t('Read access')}
          description={t('View files and folders')}
          badge={t('Recommended')}
          selected={selectedAccess === 'read'}
          onSelect={() => (selectedAccess = 'read')}
        />
        <ChoiceCard
          icon="bi-pencil-square"
          title={t('Write access')}
          description={t('Create, update or delete content')}
          selected={selectedAccess === 'contribution'}
          onSelect={() => (selectedAccess = 'contribution')}
        />
      </div>
      {#if errors.permissions}<FieldError>{errors.permissions}</FieldError>{/if}
    </section>

    <section class="nar-step">
      <h3><span>3</span>{t('Who needs access?')}</h3>
      <div class="nar-principal" class:is-invalid={Boolean(errors.principal)}>
        {#if selectedPrincipals.length === 0}
          <span class="nar-avatar is-empty"><i class="bi bi-person" aria-hidden="true"></i></span>
          <span class="nar-principal__text">
            <strong>{t('No beneficiary selected')}</strong>
            <small>{t('Select a user or group from the identity source.')}</small>
          </span>
        {:else}
          <ul class="nar-principals">
            {#each selectedPrincipals as principal, idx (selectedPrincipalKeys[idx] ?? String(idx))}
              <li>
                <span class="nar-avatar">{initials(principalLabel(principal))}</span>
                <span class="nar-principal__text">
                  <strong>{principalLabel(principal)}</strong>
                  <small>{principalSubtitle(principal)}</small>
                </span>
                <button type="button" class="b2s-btn b2s-btn-ghost b2s-btn-sm b2s-btn-icon" aria-label={t('Remove principal')} disabled={submitting} on:click={() => removeSelectedPrincipalByKey(selectedPrincipalKeys[idx] ?? '')}>
                  <i class="bi bi-x-lg" aria-hidden="true"></i>
                </button>
              </li>
            {/each}
          </ul>
        {/if}
        <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" on:click={openAdBrowser} disabled={submitting}>
          <i class="bi bi-search" aria-hidden="true"></i>
          {selectedPrincipals.length === 0 ? t('Choose') : t('Change')}
        </button>
      </div>
      {#if errors.principal}<FieldError>{errors.principal}</FieldError>{/if}
      {#if existingAccessCheckLoading}
        <p class="nar-hint">{t('Checking existing access…')}</p>
      {:else if existingAccessCheckMessage}
        <InlineAlert tone={existingAccessCheckTone === 'error' ? 'error' : existingAccessCheckTone === 'warning' ? 'warning' : existingAccessCheckTone === 'success' ? 'success' : 'info'}>
          {existingAccessCheckMessage}
        </InlineAlert>
      {/if}
    </section>

    <section class="nar-step">
      <h3><span>4</span>{t('Duration & reason')}</h3>
      <div class="nar-ttl">
        <div class="nar-segments" role="group" aria-label={t('Duration')}>
          {#each TTL_PRESETS as [value, label]}
            <button type="button" class:is-active={ttlPreset === value} aria-pressed={ttlPreset === value} on:click={() => (ttlPreset = value)}>{label}</button>
          {/each}
        </div>
        {#if ttlPreset === 'custom'}
          <label class="nar-custom">
            <input class="b2s-input" type="number" min="1" max="365" bind:value={customTtlDays} aria-label={t('Custom duration in days')} />
            {t('days')}
          </label>
        {/if}
      </div>
      {#if errors.ttl}<FieldError>{errors.ttl}</FieldError>{/if}
      <label class="nar-justification">
        <span>{t('Justification')}</span>
        <textarea bind:value={justification} maxlength="230" rows="3" placeholder={t('Explain why this access is needed...')} class:is-invalid={Boolean(errors.justification)}></textarea>
        <small>{justification.length}/230</small>
      </label>
      {#if errors.justification}<FieldError>{errors.justification}</FieldError>{/if}
    </section>

    {#each blockingProvisioningChecks as check (check.key)}
      <InlineAlert tone={check.tone === 'pending' ? 'info' : 'error'}>
        <strong>{check.label}</strong> · {check.detail}
      </InlineAlert>
    {/each}
  </div>

  <svelte:fragment slot="footer-start">
    <span class="nar-ready" class:is-ready={canSubmit}>
      <i class={`bi ${canSubmit ? 'bi-check-circle' : 'bi-info-circle'}`} aria-hidden="true"></i>
      {canSubmit ? t('Ready to submit') : blockingProvisioningChecks.length > 0 ? t('Cannot provision yet') : t('Missing required fields')}
    </span>
  </svelte:fragment>
  <svelte:fragment slot="footer">
    <button type="button" class="b2s-btn b2s-btn-secondary" on:click={close} disabled={submitting}>{t('Cancel')}</button>
    <button type="button" class="b2s-btn b2s-btn-primary" on:click={submit} disabled={submitting || !canSubmit}>
      {submitting ? t('Submitting...') : selectedPrincipalsCount > 1 ? t('Submit {count} requests', { count: selectedPrincipalsCount }) : t('Submit request')}
    </button>
  </svelte:fragment>
</AppModal>

<IdentityBrowserModal
  open={showAdBrowser}
  storageRootId={Number(storageRootId || 0) > 0 ? Number(storageRootId) : null}
  onClose={() => (showAdBrowser = false)}
  onSelect={onSelectIdentity}
  identitySources={[]}
  initialSourceId={null}
  title={t('Browse Active Directory')}
  subtitle={t('Select users and groups receiving the request.')}
  mode="multiple"
  allowedPrincipalType="all"
  includeImportCandidates={true}
  initialSelectedKeys={selectedPrincipalKeys}
  busy={submitting}
  confirmLabel={t('Confirm')}
  confirmBusyLabel={t('Confirming…')}
/>

<style>
  .nar {
    display: grid;
    gap: 18px;
  }

  .nar-step {
    display: grid;
    gap: 10px;
  }

  .nar-step h3 {
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 0;
    font-size: var(--b2s-fs-md);
    font-weight: 600;
  }

  .nar-step h3 span {
    width: 22px;
    height: 22px;
    display: grid;
    place-items: center;
    border-radius: var(--b2s-radius-pill);
    background: var(--b2s-topbar-bg);
    color: #fff;
    font-size: 12px;
  }

  .nar-hint {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
    margin: 0;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
  }

  .nar-hint a {
    margin-left: auto;
  }

  .nar-choices {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
  }

  .nar-principal {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 14px;
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-md);
  }

  .nar-principal.is-invalid {
    border-color: #fca5a5;
  }

  .nar-principals {
    flex: 1 1 auto;
    min-width: 0;
    display: grid;
    gap: 8px;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .nar-principals li {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .nar-principal__text {
    flex: 1 1 auto;
    min-width: 0;
    display: grid;
  }

  .nar-principal__text strong,
  .nar-principal__text small {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .nar-principal__text strong {
    font-size: var(--b2s-fs-sm);
    font-weight: 500;
  }

  .nar-principal__text small {
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
  }

  .nar-avatar {
    width: 32px;
    height: 32px;
    flex: 0 0 auto;
    display: grid;
    place-items: center;
    border-radius: var(--b2s-radius-pill);
    background: #e0e7ff;
    color: #3730a3;
    font-size: 12px;
    font-weight: 700;
  }

  .nar-avatar.is-empty {
    background: var(--b2s-color-neutral-soft);
    color: var(--b2s-color-text-faint);
  }

  .nar-ttl {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 12px;
  }

  .nar-segments {
    display: inline-flex;
    gap: 2px;
    padding: 3px;
    border-radius: 9px;
    background: var(--b2s-color-neutral-soft);
  }

  .nar-segments button {
    padding: 6px 14px;
    border: none;
    border-radius: 7px;
    background: transparent;
    color: var(--b2s-color-text-soft);
    font-size: var(--b2s-fs-sm);
    cursor: pointer;
  }

  .nar-segments button.is-active {
    background: var(--b2s-color-surface);
    color: var(--b2s-color-text);
    font-weight: 600;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.12);
  }

  .nar-custom {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: var(--b2s-fs-sm);
  }

  .nar-custom input {
    width: 90px;
    height: 36px;
    padding: 0 10px;
    border: 1px solid var(--b2s-color-border);
    border-radius: var(--b2s-radius-sm);
  }

  .nar-justification {
    display: grid;
    gap: 6px;
    font-size: var(--b2s-fs-sm);
    font-weight: 500;
  }

  .nar-justification textarea {
    width: 100%;
    padding: 10px 12px;
    border: 1px solid var(--b2s-color-border);
    border-radius: var(--b2s-radius-sm);
    font: inherit;
    font-weight: 400;
    resize: vertical;
  }

  .nar-justification textarea.is-invalid,
  select.is-invalid {
    border-color: #fca5a5;
  }

  .nar-justification small {
    justify-self: end;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
    font-weight: 400;
  }

  .nar-ready {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    color: var(--b2s-color-text-muted);
  }

  .nar-ready.is-ready {
    color: var(--b2s-color-success-strong);
  }

  @media (max-width: 640px) {
    .nar-choices {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
