<script lang="ts">
  import IdentityBrowserModal from '$lib/components/identity/IdentityBrowserModal.svelte';
  import AppModal from '$lib/components/common/AppModal.svelte';
  import { checkExistingAccess, createAccessRequest, type CheckExistingAccessResponse } from '$lib/api/access-requests';
  import { getStorageRootOverview, listStorageRootsContext, type StorageRootContext } from '$lib/api/storage-roots';
  import { initialsFromLabel } from '$lib/utils/initials';
  import {
    type PrincipalSearchItem,
    principalKey,
    principalLabel,
    principalSubtitle
  } from '$lib/utils/principal-search';
  import { toast } from '$lib/utils/toast';

  export let open = false;
  export let prefillStorageRootId: number | null = null;
  export let prefillAccessLevel: string | null = null;
  export let onClose: () => void = () => {};
  export let onCreated: () => void = () => {};

  type AccessChoice = 'read' | 'contribution' | 'audit';
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
  $: selectedRootOverview = selectedRoot ? (overviewByRootId[String(Number(selectedRoot.id))] ?? null) : null;
  $: selectedPermissions = [selectedAccess];
  $: selectedPrincipalsCount = selectedPrincipals.length;
  $: selectedPrincipal = selectedPrincipals[0] ?? null;
  $: existingAccessCheckKey = open
    ? [storageRootId, selectedAccess, selectedPrincipalKeys.join('|')].join(':')
    : '';
  $: ttlDays = ttlPreset === 'custom' ? Number(customTtlDays) : Number(ttlPreset);
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

  const initials = (value: string) => initialsFromLabel(value, '??');
  const compact = (value: unknown, fallback = '—') => String(value ?? '').trim() || fallback;

  function normalizePrefillAccessChoice(value: unknown): AccessChoice {
    const raw = String(value ?? '').trim().toLowerCase();
    if (raw === 'write' || raw === 'contribution' || raw === 'rw') return 'contribution';
    if (raw === 'audit') return 'audit';
    return 'read';
  }

  function rootName(root: any): string {
    return compact(root?.name ?? root?.storage_root_name ?? root?.root_name, root?.id ? `Root #${root.id}` : '—');
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

  function selectedAccessLabel(): string {
    if (selectedAccess === 'contribution') return 'Write access';
    if (selectedAccess === 'audit') return 'Audit access';
    return 'Read access';
  }

  function selectedAccessCode(): string {
    if (selectedAccess === 'contribution') return 'WRITE';
    if (selectedAccess === 'audit') return 'AUDIT';
    return 'READ';
  }

  function selectedAccessDescription(): string {
    if (selectedAccess === 'contribution') return 'Create, update or delete content.';
    if (selectedAccess === 'audit') return 'View access and security information.';
    return 'View files and folders.';
  }

  function approvalLabel(): string {
    const count = guardianCount(selectedRoot);
    if (count > 0) return `${count} approver${count > 1 ? 's' : ''} required`;
    return 'Guardian review';
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
    selectedPrincipals = [];
    selectedPrincipalKeys = [];
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
          [String(rootId)]: { _load_error: 'Unable to load storage root validation details' }
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
        existingAccessCheckMessage = `${principalLabel(blockingResult.principal)} · ${blockingResult.result.message || 'Cette demande ne peut pas etre soumise.'}`;
        return;
      }

      const elevationResult = results.find(({ result }) => result?.code === 'ELEVATION_ALLOWED' || result?.reason === 'ELEVATION_ALLOWED');
      if (elevationResult) {
        existingAccessCheckTone = 'warning';
        existingAccessCheckMessage = `${principalLabel(elevationResult.principal)} · ${elevationResult.result.message || 'Cette demande sera traitee comme une elevation.'}`;
        return;
      }

      existingAccessCheckTone = 'success';
      existingAccessCheckMessage =
        results.length > 1
          ? `${results.length} beneficiaires peuvent recevoir cette demande.`
          : 'Aucun acces existant bloquant detecte.';
    } catch {
      if (seq !== existingAccessCheckSeq) return;
      existingAccessCheckTone = 'neutral';
      existingAccessCheckMessage = "Verification d'acces indisponible. La validation finale sera faite a la soumission.";
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
          label: 'Validation en cours',
          detail: 'Chargement du contexte DAL du storage root.',
          tone: 'pending',
          blocking: true
        }
      ];
    }
    if (overview?._load_error) {
      return [
        {
          key: 'overview_load',
          label: 'Validation indisponible',
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
      label: 'Storage root joignable',
      detail: reachable
        ? 'Dernier probe OK.'
        : unreachable
          ? String(overview?.last_probe_message ?? overview?.revalidation_reason ?? 'Le dernier probe indique un root non joignable.')
          : 'Aucun probe récent ne confirme la joignabilité.',
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
        errors.storageRootId = 'Selected storage root is not available in the DAL context';
      } else if (!storageRootId && roots.length > 0) {
        storageRootId = String(roots[0].id);
      }
    } catch {
      toast.error('Unable to load storage roots');
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
      errors.storageRootId = 'Select a storage root';
    }
    if (selectedPermissions.length === 0) {
      errors.permissions = "Selectionne un niveau d'acces";
    }
    if (selectedPrincipals.length === 0) {
      errors.principal = 'Select a beneficiary from the identity source';
    }
    if (!Number.isFinite(ttlDays) || ttlDays <= 0) {
      errors.ttl = 'TTL invalide';
    }
    if (!justification.trim()) {
      errors.justification = 'La justification est obligatoire';
    }
    if (blockingProvisioningChecks.length > 0) {
      errors.permissions = blockingProvisioningChecks[0]?.detail || 'La demande ne peut pas être provisionnée.';
    }
    if (existingAccessBlocking && !errors.principal) {
      errors.principal = existingAccessCheckMessage || "Cette demande ne peut pas etre soumise.";
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
      toast.warning('No identity selected');
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
          existingAccessCheckMessage = `${principalLabel(principal)} · ${precheck?.message || 'Cette demande ne peut pas etre soumise.'}`;
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
          ? `${selectedPrincipalsCount} access requests created`
          : 'Access request created'
      );
      onCreated();
      onClose();
    } catch (error: any) {
      toast.error(String(error?.message || 'Failed to create request'));
    } finally {
      submitting = false;
    }
  }
</script>

<AppModal
  {open}
  onClose={close}
  backdropClass="b2s-modal-backdrop ar-governed-backdrop"
  modalClass="b2s-modal ar-governed-modal"
  ariaLabelledby="ar-governed-title"
  showClose={false}
  wrapContent={false}
  closeOnBackdrop={false}
>
  <div class="ar-create">
    <header class="ar-create__header">
      <div>
        <h2 id="ar-governed-title">Request governed access</h2>
        <p>Create a governed access request in one simple form.</p>
      </div>
      <button type="button" class="ar-close" aria-label="Close" on:click={close}>
        <i class="bi bi-x-lg" aria-hidden="true"></i>
      </button>
    </header>

    <div class="ar-create__content">
      <section class="ar-form-card">
        <div class="ar-step">
          <h3>1. Target location</h3>
          <div class="target-card" class:error={Boolean(errors.storageRootId)}>
            <span class="target-icon"><i class="bi bi-folder-fill" aria-hidden="true"></i></span>
            <div>
              <strong>{selectedRoot ? rootName(selectedRoot) : loadingRoots ? 'Loading...' : '—'}</strong>
              <small>{rootZone(selectedRoot)}{endpointName(selectedRoot) !== '—' ? ` · ${endpointName(selectedRoot)}` : ''}</small>
              <small>Path: {rootPath(selectedRoot)}</small>
            </div>
            {#if selectedRoot}
              <span class="approval-badge"><i class="bi bi-shield-check" aria-hidden="true"></i>{approvalLabel()}</span>
            {/if}
          </div>
          {#if errors.storageRootId}
            <small class="field-error">{errors.storageRootId}</small>
          {/if}
        </div>

        <div class="ar-step">
          <h3>2. Access needed</h3>
          <div class="access-grid">
            <button type="button" class:active={selectedAccess === 'read'} on:click={() => (selectedAccess = 'read')}>
              <span class="choice-icon read"><i class="bi bi-file-earmark" aria-hidden="true"></i></span>
              <strong>Read access</strong>
              <small>View files and folders</small>
              <em>Recommended</em>
              {#if selectedAccess === 'read'}<i class="bi bi-check-circle-fill choice-check" aria-hidden="true"></i>{/if}
            </button>
            <button type="button" class:active={selectedAccess === 'contribution'} on:click={() => (selectedAccess = 'contribution')}>
              <span class="choice-icon write"><i class="bi bi-pencil-square" aria-hidden="true"></i></span>
              <strong>Write access</strong>
              <small>Create, update or delete content</small>
              <em class="warn">Approval required</em>
              {#if selectedAccess === 'contribution'}<i class="bi bi-check-circle-fill choice-check" aria-hidden="true"></i>{/if}
            </button>
            <button type="button" class:active={selectedAccess === 'audit'} on:click={() => (selectedAccess = 'audit')}>
              <span class="choice-icon audit"><i class="bi bi-shield-check" aria-hidden="true"></i></span>
              <strong>Audit access</strong>
              <small>View access and security information</small>
              <em class="sensitive">Sensitive</em>
              {#if selectedAccess === 'audit'}<i class="bi bi-check-circle-fill choice-check" aria-hidden="true"></i>{/if}
            </button>
          </div>
          {#if errors.permissions}
            <small class="field-error">{errors.permissions}</small>
          {/if}
        </div>

        <div class="ar-step">
          <h3>3. Who needs access?</h3>
          <div class="principal-card" class:error={Boolean(errors.principal)}>
            {#if selectedPrincipal}
              <span class="avatar">{initials(principalLabel(selectedPrincipal))}</span>
              <div>
                <strong>{principalLabel(selectedPrincipal)}</strong>
                <small>{principalSubtitle(selectedPrincipal)}</small>
              </div>
            {:else}
              <span class="avatar muted"><i class="bi bi-person" aria-hidden="true"></i></span>
              <div>
                <strong>No beneficiary selected</strong>
                <small>Select a user or group from the identity source.</small>
              </div>
            {/if}
            <button type="button" aria-label="Browse identities" on:click={openAdBrowser} disabled={submitting}>
              <i class="bi bi-search" aria-hidden="true"></i>
            </button>
          </div>
          {#if selectedPrincipalsCount > 1}
            <div class="principal-list">
              {#each selectedPrincipals as principal, idx (selectedPrincipalKeys[idx] ?? String(idx))}
                <span>
                  {principalLabel(principal)}
                  <button type="button" aria-label="Remove principal" on:click={() => removeSelectedPrincipalByKey(selectedPrincipalKeys[idx] ?? '')}>×</button>
                </span>
              {/each}
            </div>
          {/if}
          {#if errors.principal}
            <small class="field-error">{errors.principal}</small>
          {/if}
          {#if existingAccessCheckLoading}
            <small class="field-hint">Verification des acces existants…</small>
          {:else if existingAccessCheckMessage}
            <small class={`field-hint field-hint--${existingAccessCheckTone}`}>{existingAccessCheckMessage}</small>
          {/if}
        </div>

        <div class="ar-step">
          <h3>4. Duration &amp; reason</h3>
          <div class="ttl-row">
            <button type="button" class:active={ttlPreset === '7'} on:click={() => (ttlPreset = '7')}>7 days</button>
            <button type="button" class:active={ttlPreset === '30'} on:click={() => (ttlPreset = '30')}>30 days</button>
            <button type="button" class:active={ttlPreset === '90'} on:click={() => (ttlPreset = '90')}>90 days</button>
            <button type="button" class:active={ttlPreset === 'custom'} on:click={() => (ttlPreset = 'custom')}>
              <i class="bi bi-calendar4-week" aria-hidden="true"></i>Custom
            </button>
          </div>
          {#if ttlPreset === 'custom'}
            <input class="custom-ttl" type="number" min="1" max="365" bind:value={customTtlDays} aria-label="Custom duration in days" />
          {/if}
          {#if errors.ttl}
            <small class="field-error">{errors.ttl}</small>
          {/if}
          <label class="justification">
            <span>Justification</span>
            <textarea bind:value={justification} maxlength="230" placeholder="Explain why this access is needed..."></textarea>
          </label>
          {#if errors.justification}
            <small class="field-error">{errors.justification}</small>
          {/if}
        </div>

        <footer class="info-strip">
          <i class="bi bi-info-circle-fill" aria-hidden="true"></i>
          <span>Access is requested through governed profiles. No AD group or NTFS details are exposed.</span>
        </footer>
      </section>

      <aside class="summary-panel">
        <div class:ready={canSubmit} class="ready-state">
          <i class={`bi ${canSubmit ? 'bi-check-circle' : 'bi-exclamation-circle'}`} aria-hidden="true"></i>
          {canSubmit ? 'Ready to submit' : blockingProvisioningChecks.length > 0 ? 'Cannot provision yet' : 'Missing required fields'}
        </div>

        {#if selectedRoot}
          <a class="policy-link" href={`/storage-roots/${Number(selectedRoot.id)}/policies`}>
            Review policy <i class="bi bi-box-arrow-up-right" aria-hidden="true"></i>
          </a>
        {:else}
          <span class="policy-link disabled">
            Review policy <i class="bi bi-box-arrow-up-right" aria-hidden="true"></i>
          </span>
        {/if}
      </aside>
    </div>

    <footer class="ar-create__footer">
      <button type="button" class="cancel" on:click={close} disabled={submitting}>Cancel</button>
      <button type="button" class="submit" on:click={submit} disabled={submitting || !canSubmit}>
        {submitting ? 'Submitting...' : 'Submit request'}
      </button>
    </footer>
  </div>
</AppModal>

<IdentityBrowserModal
  open={showAdBrowser}
  storageRootId={Number(storageRootId || 0) > 0 ? Number(storageRootId) : null}
  onClose={() => (showAdBrowser = false)}
  onSelect={onSelectIdentity}
  identitySources={[]}
  initialSourceId={null}
  title="Browse Active Directory"
  subtitle="Select users and groups receiving the request."
  mode="multiple"
  allowRoleAssignment={false}
  allowedPrincipalType="all"
  includeImportCandidates={true}
  initialSelectedKeys={selectedPrincipalKeys}
  busy={submitting}
  confirmLabel="Valider"
  confirmBusyLabel="Validation…"
/>

<style>
  :global(.ar-governed-backdrop) {
    background: rgba(7, 20, 50, 0.2);
    align-items: flex-start;
    padding-top: 70px;
  }

  :global(.ar-governed-modal) {
    width: min(1136px, calc(100vw - 40px));
    max-height: calc(100vh - 92px);
    overflow: hidden;
    border-radius: 14px;
    border: 1px solid #dfe6f2;
    box-shadow: 0 24px 70px rgba(6, 24, 73, 0.24);
    background: #fff;
  }

  .ar-create {
    color: #071b4a;
    background: #fff;
    font-family: Inter, system-ui, -apple-system, "Segoe UI", sans-serif;
  }

  .ar-create__header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    padding: 28px 36px 12px;
  }

  .ar-create__header h2 {
    margin: 0;
    font-size: 34px;
    line-height: 1.08;
    letter-spacing: 0;
    font-weight: 830;
    color: #061849;
  }

  .ar-create__header p {
    margin: 8px 0 0;
    color: #405178;
    font-size: 16px;
    font-weight: 450;
  }

  .ar-close {
    width: 43px;
    height: 43px;
    border-radius: 10px;
    border: 1px solid #dce4f1;
    background: #fff;
    color: #071b4a;
    font-size: 20px;
  }

  .ar-create__content {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 320px;
    gap: 28px;
    padding: 0 36px 22px;
    overflow: auto;
    max-height: calc(100vh - 230px);
  }

  .ar-form-card,
  .summary-card,
  .result-card,
  .validation-card {
    border: 1px solid #dfe6f2;
    border-radius: 12px;
    background: #fff;
  }

  .ar-form-card {
    overflow: hidden;
  }

  .ar-step {
    padding: 16px 18px 0;
  }

  .ar-step h3,
  .summary-panel h3 {
    margin: 0 0 9px;
    color: #061849;
    font-size: 16px;
    font-weight: 760;
  }

  .target-card {
    min-height: 92px;
    display: grid;
    grid-template-columns: 52px minmax(0, 1fr) auto;
    align-items: center;
    gap: 16px;
    border: 1px solid #d9e2ef;
    border-radius: 10px;
    padding: 14px 18px;
  }

  .target-card.error,
  .principal-card.error {
    border-color: #ff9b9b;
  }

  .target-icon {
    width: 42px;
    height: 42px;
    border-radius: 8px;
    display: grid;
    place-items: center;
    background: #fff4d9;
    color: #f9ad1b;
    font-size: 28px;
  }

  .target-card strong,
  .principal-card strong,
  .summary-list strong {
    display: block;
    color: #061849;
    font-weight: 730;
  }

  .target-card small,
  .principal-card small {
    display: block;
    margin-top: 3px;
    color: #405178;
    font-size: 13px;
  }

  .approval-badge {
    min-height: 36px;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    border-radius: 8px;
    background: #e7f6e8;
    color: #0b7a1e;
    padding: 0 12px;
    font-size: 13px;
    font-weight: 650;
    white-space: nowrap;
  }

  .access-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 14px;
  }

  .access-grid button {
    position: relative;
    min-height: 140px;
    border: 1px solid #d9e2ef;
    border-radius: 10px;
    background: #fff;
    color: #071b4a;
    text-align: center;
    padding: 20px 14px 14px;
  }

  .access-grid button.active {
    border-color: #061849;
    box-shadow: inset 0 0 0 1px #061849;
  }

  .choice-icon {
    width: 40px;
    height: 40px;
    margin: 0 auto 9px;
    border-radius: 8px;
    display: grid;
    place-items: center;
    font-size: 24px;
  }

  .choice-icon.read { background: #edf3ff; color: #0c3ea4; }
  .choice-icon.write { background: #e7f6e8; color: #0c9a2b; }
  .choice-icon.audit { background: #f2e8ff; color: #7a2dff; }

  .access-grid strong {
    display: block;
    font-size: 16px;
    font-weight: 760;
  }

  .access-grid small {
    display: block;
    min-height: 36px;
    margin-top: 8px;
    color: #405178;
    font-size: 13px;
    line-height: 1.35;
  }

  .access-grid em {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 28px;
    margin-top: 10px;
    border-radius: 999px;
    background: #061849;
    color: #fff;
    padding: 0 15px;
    font-style: normal;
    font-size: 12px;
    font-weight: 700;
  }

  .access-grid em.warn {
    background: #fff2e4;
    color: #f47b00;
    border: 1px solid #ffc48c;
  }

  .access-grid em.sensitive {
    background: #f3e8ff;
    color: #7a2dff;
  }

  .choice-check {
    position: absolute;
    top: 11px;
    right: 11px;
    color: #061849;
    font-size: 19px;
  }

  .principal-card {
    min-height: 66px;
    display: grid;
    grid-template-columns: 48px minmax(0, 1fr) 43px;
    gap: 13px;
    align-items: center;
    border: 1px solid #d9e2ef;
    border-radius: 10px;
    padding: 9px 12px 9px 16px;
  }

  .avatar {
    width: 45px;
    height: 45px;
    border-radius: 50%;
    background: #061849;
    color: #fff;
    display: grid;
    place-items: center;
    font-weight: 780;
  }

  .avatar.muted {
    background: #edf3ff;
    color: #0b2b70;
  }

  .principal-card > button {
    width: 41px;
    height: 41px;
    border-radius: 9px;
    border: 1px solid #d9e2ef;
    background: #fff;
    color: #061849;
    font-size: 20px;
  }

  .principal-list {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 10px;
  }

  .principal-list span {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    border: 1px solid #d9e2ef;
    border-radius: 999px;
    padding: 4px 9px 4px 12px;
    color: #071b4a;
    font-size: 12px;
  }

  .principal-list button {
    border: 0;
    background: transparent;
    color: #c22323;
  }

  .ttl-row {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    margin-bottom: 10px;
  }

  .ttl-row button {
    height: 36px;
    border: 1px solid #d9e2ef;
    border-radius: 999px;
    background: #fff;
    color: #071b4a;
    padding: 0 20px;
    font-weight: 650;
    display: inline-flex;
    align-items: center;
    gap: 8px;
  }

  .ttl-row button.active {
    background: #061849;
    border-color: #061849;
    color: #fff;
  }

  .custom-ttl {
    width: 130px;
    height: 36px;
    border: 1px solid #d9e2ef;
    border-radius: 9px;
    padding: 0 12px;
    color: #071b4a;
  }

  .justification span {
    display: block;
    margin-bottom: 7px;
    color: #405178;
    font-size: 13px;
  }

  .justification textarea {
    width: 100%;
    height: 61px;
    border: 1px solid #d9e2ef;
    border-radius: 9px;
    resize: vertical;
    padding: 13px 15px;
    color: #071b4a;
    outline: none;
  }

  .justification textarea::placeholder {
    color: #66779c;
  }

  .field-error {
    display: block;
    margin-top: 6px;
    color: #c22323;
    font-size: 12px;
    font-weight: 620;
  }

  .field-hint {
    display: block;
    margin-top: 6px;
    color: #44506b;
    font-size: 12px;
    font-weight: 520;
  }

  .field-hint--success {
    color: #0f7b6c;
  }

  .field-hint--warning {
    color: #9a6700;
  }

  .field-hint--error {
    color: #c22323;
  }

  .info-strip {
    min-height: 48px;
    margin-top: 18px;
    padding: 0 18px;
    display: flex;
    align-items: center;
    gap: 13px;
    border-top: 1px solid #dfe6f2;
    background: #f7f9fd;
    color: #2c3d65;
    font-size: 13px;
  }

  .info-strip i {
    color: #061849;
  }

  .summary-panel {
    display: grid;
    gap: 18px;
    align-content: start;
  }

  .summary-card,
  .result-card,
  .validation-card {
    padding: 20px;
  }

  .summary-list {
    border: 1px solid #dfe6f2;
    border-radius: 10px;
    overflow: hidden;
  }

  .summary-list > div {
    min-height: 70px;
    display: grid;
    grid-template-columns: 31px minmax(0, 1fr);
    gap: 12px;
    align-items: center;
    padding: 11px 14px;
    border-bottom: 1px solid #e8edf5;
  }

  .summary-list > div:last-child {
    border-bottom: 0;
  }

  .summary-list i {
    color: #061849;
    font-size: 20px;
  }

  .summary-list i.folder {
    color: #f9ad1b;
  }

  .summary-list small {
    display: block;
    color: #405178;
    font-size: 12px;
    font-weight: 650;
  }

  .summary-list strong {
    margin-top: 3px;
    font-size: 14px;
    font-weight: 540;
  }

  .result-card h3,
  .validation-card h3 {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .result-card h3 i,
  .validation-card h3 i {
    color: #1559ff;
  }

  .result-card p {
    margin: 0;
    color: #071b4a;
    font-size: 14px;
    line-height: 1.45;
  }

  .result-card small {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 16px;
    color: #071b4a;
    font-size: 13px;
  }

  .validation-card > div {
    display: grid;
    gap: 8px;
  }

  .validation-row {
    display: grid;
    grid-template-columns: 28px minmax(0, 1fr);
    gap: 10px;
    align-items: flex-start;
  }

  .validation-row > span {
    width: 26px;
    height: 26px;
    border-radius: 7px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 13px;
  }

  .validation-row.is-success > span {
    background: #e7f6e8;
    color: #08721b;
  }

  .validation-row.is-warning > span,
  .validation-row.is-pending > span {
    background: #fff6e9;
    color: #b76700;
  }

  .validation-row.is-error > span {
    background: #fff0f0;
    color: #db1f1f;
  }

  .validation-row div {
    min-width: 0;
    display: grid;
    gap: 2px;
  }

  .validation-row strong {
    overflow: hidden;
    color: #071b4a;
    font-size: 13px;
    font-weight: 720;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .validation-row small {
    color: #405178;
    font-size: 12px;
    line-height: 1.35;
  }

  .ready-state {
    height: 44px;
    border-radius: 9px;
    background: #fff6e9;
    color: #b76700;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    font-weight: 680;
  }

  .ready-state.ready {
    background: #e7f6e8;
    color: #08721b;
  }

  .policy-link {
    border: 0;
    background: transparent;
    color: #061849;
    display: inline-flex;
    justify-content: center;
    align-items: center;
    gap: 8px;
    font-weight: 700;
    text-decoration: none;
  }

  .policy-link.disabled {
    opacity: 0.45;
  }

  .ar-create__footer {
    display: flex;
    justify-content: flex-end;
    gap: 12px;
    padding: 0 36px 20px;
  }

  .ar-create__footer button {
    height: 48px;
    border-radius: 10px;
    padding: 0 22px;
    font-size: 15px;
    font-weight: 760;
  }

  .ar-create__footer .cancel {
    border: 1px solid #d9e2ef;
    background: #fff;
    color: #061849;
  }

  .ar-create__footer .submit {
    border: 1px solid #061849;
    background: #061849;
    color: #fff;
    box-shadow: 0 10px 24px rgba(6, 24, 73, 0.2);
  }

  .ar-create__footer button:disabled {
    opacity: 0.65;
    cursor: not-allowed;
  }

  @media (max-width: 980px) {
    :global(.ar-governed-backdrop) {
      padding-top: 20px;
    }

    .ar-create__content {
      grid-template-columns: 1fr;
      max-height: calc(100vh - 210px);
    }

    .access-grid {
      grid-template-columns: 1fr;
    }

    .target-card {
      grid-template-columns: 52px minmax(0, 1fr);
    }

    .approval-badge {
      grid-column: 1 / -1;
      width: max-content;
    }
  }
</style>
