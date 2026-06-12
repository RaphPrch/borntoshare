<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { createIdentity, type CreateIdentityPayload } from '$lib/api/identity';
  import { listIdentitySources, type IdentitySourceListItem } from '$lib/api/identity-sources';
  import IdentityBrowserModal from '$lib/components/identity/IdentityBrowserModal.svelte';
  import { toasts } from '$lib/stores/toast';
  import { presentErrorHint, presentErrorMessage, toAppError } from '$lib/core/errors';
  import { searchBrowserDirectory } from '$lib/components/identity/identity-browser.controller';
  import type { PrincipalSearchItem } from '$lib/utils/principal-search';
  import type { IdentityBrowserSelectionPayload } from '$lib/types/identityBrowser';

  export let open = false;
  export let onCancel: () => void;

  type IdentityMode = 'local' | 'directory_user' | 'directory_group' | null;
  type ApplicationRole = 'user' | 'platform_admin';

  const dispatch = createEventDispatcher<{ done: { id?: string | number } }>();

  const modeCards: Array<{
    id: Exclude<IdentityMode, null>;
    label: string;
    badge: string;
    icon: string;
    description: string[];
  }> = [
    {
      id: 'local',
      label: 'Local user',
      badge: 'Local',
      icon: 'bi-person',
      description: [
        'Create a BornToShare account that is managed locally.',
        'Best for break-glass admins or local platform users.'
      ]
    },
    {
      id: 'directory_user',
      label: 'Directory user',
      badge: 'AD/LDAP',
      icon: 'bi-people',
      description: [
        'Import one user from a configured identity source.',
        'The user keeps authenticating through the directory.'
      ]
    },
    {
      id: 'directory_group',
      label: 'Directory group',
      badge: 'Group',
      icon: 'bi-people-fill',
      description: [
        'Allow all members of an AD/LDAP group to sign in.',
        'Useful for platform admins or delegated users.'
      ]
    }
  ];

  let step = 1;
  let mode: IdentityMode = null;
  let loadingSources = false;
  let submitting = false;
  let searchLoading = false;
  let errorMessage = '';
  let errorHint = '';
  let adSources: IdentitySourceListItem[] = [];
  let selectedSourceId: number | null = null;
  let searchQuery = '';
  let searchResults: PrincipalSearchItem[] = [];
  let selectedPrincipal: PrincipalSearchItem | null = null;
  let showAdBrowser = false;
  let applicationRole: ApplicationRole = 'user';
  let localUsername = '';
  let localDisplayName = '';
  let localEmail = '';
  let localPassword = '';
  let requirePasswordChange = true;
  let searchDebounce: ReturnType<typeof setTimeout> | null = null;
  let searchAbort: AbortController | null = null;
  let wasOpen = false;
  let attemptedSubmit = false;

  const isDirectoryMode = (value: IdentityMode): value is 'directory_user' | 'directory_group' =>
    value === 'directory_user' || value === 'directory_group';

  const trimmed = (value: unknown) => String(value ?? '').trim();
  const normalizeDirectoryObjectType = (item: Record<string, unknown> | null | undefined): 'user' | 'group' | null => {
    const rawCandidates = [
      item?.type,
      item?.principalType,
      item?.principal_type,
      item?.objectType,
      item?.object_type,
      item?.kind,
      item?.objectClass
    ];
    const tokens = rawCandidates.flatMap((value) => {
      if (Array.isArray(value)) return value.map((entry) => String(entry ?? '').trim().toLowerCase()).filter(Boolean);
      const raw = String(value ?? '').trim().toLowerCase();
      return raw ? raw.split(/[\s,;|/]+/).filter(Boolean) : [];
    });
    if (tokens.some((token) => ['group', 'groups', 'directory_group'].includes(token))) return 'group';
    if (tokens.some((token) => ['user', 'users', 'person', 'directory_user'].includes(token))) return 'user';
    return null;
  };

  const resetState = () => {
    step = 1;
    mode = null;
    submitting = false;
    searchLoading = false;
    errorMessage = '';
    errorHint = '';
    searchQuery = '';
    searchResults = [];
    selectedPrincipal = null;
    showAdBrowser = false;
    applicationRole = 'user';
    localUsername = '';
    localDisplayName = '';
    localEmail = '';
    localPassword = '';
    requirePasswordChange = true;
    if (searchDebounce) {
      clearTimeout(searchDebounce);
      searchDebounce = null;
    }
    if (searchAbort) {
      searchAbort.abort();
      searchAbort = null;
    }
    attemptedSubmit = false;
  };

  $: if (open && !wasOpen) {
    wasOpen = true;
    resetState();
  } else if (!open && wasOpen) {
    wasOpen = false;
    resetState();
  }

  const activeAdSources = (sources: IdentitySourceListItem[]) =>
    (sources ?? []).filter((source) => {
      const type = trimmed(source?.type ?? 'ad').toLowerCase();
      return type === 'ad' && source?.is_active !== false;
    });

  async function ensureAdSources(): Promise<boolean> {
    if (adSources.length > 0) return true;
    loadingSources = true;
    try {
      adSources = activeAdSources(await listIdentitySources(fetch));
      if (!adSources.length) {
        onCancel();
        toasts.warning("Import impossible: aucune identity source Active Directory active n'est definie.");
        return false;
      }
      if (!selectedSourceId) {
        selectedSourceId = Number(adSources[0]?.id ?? 0) || null;
      }
      return true;
    } catch (error) {
      const appError = toAppError(error, { source: 'ui' });
      errorMessage = presentErrorMessage(appError);
      errorHint = presentErrorHint(appError) ?? '';
      return false;
    } finally {
      loadingSources = false;
    }
  }

  async function chooseMode(nextMode: Exclude<IdentityMode, null>) {
    errorMessage = '';
    errorHint = '';
    if (nextMode === 'local') {
      mode = nextMode;
      step = 2;
      return;
    }
    const hasSources = await ensureAdSources();
    if (!hasSources) return;
    mode = nextMode;
    step = 2;
  }

  function handleBack() {
    errorMessage = '';
    errorHint = '';
    step = 1;
    mode = null;
    searchQuery = '';
    searchResults = [];
    selectedPrincipal = null;
    if (searchAbort) {
      searchAbort.abort();
      searchAbort = null;
    }
  }

  function roleLabel(role: ApplicationRole): string {
    return role === 'platform_admin' ? 'Platform Administrator' : 'User';
  }

  function principalTitle(item: PrincipalSearchItem | null): string {
    if (!item) return '';
    return trimmed(item.display_name ?? item.username ?? item.email ?? item.dn ?? item.external_id ?? item.id);
  }

  function principalSubline(item: PrincipalSearchItem | null): string {
    if (!item) return '';
    return trimmed(item.email ?? item.username ?? item.upn ?? item.dn);
  }

  function principalThirdLine(item: PrincipalSearchItem | null): string {
    if (!item) return '';
    if (String(item.type ?? '').toLowerCase() === 'group') {
      const count = Number(item.group_count ?? 0);
      return count > 0 ? `${count} members` : trimmed(item.dn ?? item.external_id);
    }
    return trimmed(item.dn ?? item.external_id);
  }

  function principalAvatar(item: PrincipalSearchItem | null): string {
    const source = principalTitle(item);
    if (!source) return 'ID';
    return source
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part.charAt(0).toUpperCase())
      .join('');
  }

  function clearSelection() {
    selectedPrincipal = null;
  }

  function scheduleSearch() {
    errorMessage = '';
    errorHint = '';
    if (!isDirectoryMode(mode) || !selectedSourceId) return;
    if (searchDebounce) clearTimeout(searchDebounce);

    const query = trimmed(searchQuery);
    if (query.length < 2) {
      searchResults = [];
      searchLoading = false;
      return;
    }

    searchDebounce = setTimeout(async () => {
      if (searchAbort) searchAbort.abort();
      searchAbort = new AbortController();
      searchLoading = true;
      try {
        const result = await searchBrowserDirectory(
          fetch,
          {
            selectedSourceId: Number(selectedSourceId),
            query,
            activeDn: null,
            resolvedRootDn: null,
            principalTypeFilter: mode === 'directory_group' ? 'group' : 'user',
            searchLimit: 12,
            includeImportCandidates: true
          },
          searchAbort.signal
        );
        searchResults = result.rows;
      } catch (error) {
        if (String((error as Error)?.name ?? '') === 'AbortError') return;
        const appError = toAppError(error, { source: 'ui' });
        errorMessage = presentErrorMessage(appError);
        errorHint = presentErrorHint(appError) ?? '';
        searchResults = [];
      } finally {
        searchLoading = false;
      }
    }, 250);
  }

  function handleSourceChange() {
    selectedPrincipal = null;
    searchResults = [];
    scheduleSearch();
  }

  function choosePrincipal(item: PrincipalSearchItem) {
    selectedPrincipal = item;
    searchResults = [];
    searchQuery = principalTitle(item);
    errorMessage = '';
    errorHint = '';
  }

  async function openAdBrowser() {
    errorMessage = '';
    errorHint = '';
    const hasSources = await ensureAdSources();
    if (!hasSources) return;
    if (!selectedSourceId) {
      toasts.warning("Impossible d'ouvrir le browser AD : aucune identity source Active Directory n'est selectionnee.");
      return;
    }
    showAdBrowser = true;
  }

  function onSelectFromAdBrowser(payload: IdentityBrowserSelectionPayload) {
    const selected = Array.isArray(payload?.selectedItems) ? payload.selectedItems[0] : null;
    if (!selected) {
      toasts.warning('No directory identity selected.');
      return;
    }

    const selectedType = normalizeDirectoryObjectType(selected as Record<string, unknown>);
    mode = selectedType === 'group' ? 'directory_group' : 'directory_user';
    selectedSourceId =
      Number(payload?.sourceId ?? selected?.identity_source_id ?? selectedSourceId ?? 0) || selectedSourceId;
    choosePrincipal(selected);
    showAdBrowser = false;
  }

  $: selectedPrincipalType = normalizeDirectoryObjectType(selectedPrincipal as Record<string, unknown> | null);
  $: isSelectedUser = selectedPrincipalType === 'user';
  $: isSelectedGroup = selectedPrincipalType === 'group';
  $: effectiveDirectoryPrincipalType =
    selectedPrincipalType ?? (mode === 'directory_group' ? 'group' : mode === 'directory_user' ? 'user' : null);
  $: resolvedDirectorySourceId =
    Number(selectedSourceId ?? selectedPrincipal?.identity_source_id ?? 0) > 0
      ? Number(selectedSourceId ?? selectedPrincipal?.identity_source_id ?? 0)
      : null;
  $: canImportDirectoryPrincipal =
    Boolean(resolvedDirectorySourceId) &&
    Boolean(selectedPrincipal) &&
    Boolean(applicationRole) &&
    Boolean(effectiveDirectoryPrincipalType) &&
    !submitting;

  const localFormValid = () =>
    trimmed(localUsername).length > 0 &&
    trimmed(localDisplayName).length > 0 &&
    trimmed(localPassword).length > 0 &&
    Boolean(applicationRole);

  const directoryFormValid = () => canImportDirectoryPrincipal;
  $: localUsernameError = attemptedSubmit && !trimmed(localUsername) ? 'Username is required.' : '';
  $: localDisplayNameError = attemptedSubmit && !trimmed(localDisplayName) ? 'Display name is required.' : '';
  $: localPasswordError = attemptedSubmit && !trimmed(localPassword) ? 'Temporary password is required.' : '';
  $: sourceError = attemptedSubmit && isDirectoryMode(mode) && !resolvedDirectorySourceId ? 'Select an identity source first.' : '';
  $: principalError = attemptedSubmit && isDirectoryMode(mode) && !selectedPrincipal
    ? mode === 'directory_group'
      ? 'Select a directory group first.'
      : 'Select a directory user first.'
    : '';
  $: roleError = attemptedSubmit && !applicationRole ? 'Select an application role first.' : '';
  $: submitDisabledReason = mode === 'local'
    ? localUsernameError || localDisplayNameError || localPasswordError || roleError || 'Complete required fields first.'
    : sourceError || principalError || roleError || 'Complete required fields first.';

  function buildCreatePayload(): CreateIdentityPayload {
    if (mode === 'local') {
      return {
        identity_type: 'user',
        auth_source: 'local',
        username: trimmed(localUsername),
        display_name: trimmed(localDisplayName),
        email: trimmed(localEmail) || null,
        temporary_password: localPassword,
        require_password_change: requirePasswordChange,
        application_role: applicationRole
      };
    }

    const principal = selectedPrincipal;
    const principalType = effectiveDirectoryPrincipalType === 'group' ? 'group' : 'user';
    return {
      identity_type: principalType,
      auth_source: 'ad',
      identity_source_id: Number(resolvedDirectorySourceId),
      application_role: applicationRole,
      principal: {
        type: principalType,
        external_id: trimmed(principal?.external_id ?? principal?.dn ?? principal?.username ?? principal?.upn ?? principal?.email) || null,
        dn: trimmed(principal?.dn) || null,
        username: trimmed(principal?.username) || null,
        upn: trimmed(principal?.upn) || null,
        display_name: principalTitle(principal) || null,
        email: trimmed(principal?.email) || null
      }
    };
  }

  async function submit() {
    attemptedSubmit = true;
    errorMessage = '';
    errorHint = '';

    if (mode === 'local' && !localFormValid()) return;
    if (isDirectoryMode(mode)) {
      if (!resolvedDirectorySourceId) {
        toasts.warning('Select an identity source first.');
        return;
      }
      if (!selectedPrincipal) {
        toasts.warning('Select a user or group first.');
        return;
      }
      if (!applicationRole) {
        toasts.warning('Select an application role first.');
        return;
      }
      if (!directoryFormValid()) {
        toasts.warning('Unable to import identity.');
        return;
      }
    }

    submitting = true;
    try {
      const created = await createIdentity(fetch, buildCreatePayload());
      toasts.success(isSelectedGroup ? 'Group imported.' : 'Identity imported.');
      dispatch('done', { id: created?.id });
    } catch (error) {
      const appError = toAppError(error, { source: 'ui' });
      errorMessage = presentErrorMessage(appError);
      errorHint = presentErrorHint(appError) ?? '';
      toasts.error('Unable to import identity.');
    } finally {
      submitting = false;
    }
  }

  function submitLabel(): string {
    if (mode === 'local') return submitting ? 'Creating...' : 'Create local user';
    if (effectiveDirectoryPrincipalType === 'group') return submitting ? 'Importing...' : 'Import group';
    if (effectiveDirectoryPrincipalType === 'user') return submitting ? 'Importing...' : 'Import user';
    return submitting ? 'Importing...' : 'Import identity';
  }

  function helperText(): string {
    if (effectiveDirectoryPrincipalType === 'group') {
      return 'Define the application role that will be applied to all members.';
    }
    return 'Define the application role for this user.';
  }

  function currentDirectoryTitle(): string {
    if (effectiveDirectoryPrincipalType === 'group') return 'Directory group';
    if (effectiveDirectoryPrincipalType === 'user') return 'Directory user';
    return mode === 'directory_group' ? 'Directory group' : 'Directory user';
  }

  function currentDirectoryBadge(): string {
    if (effectiveDirectoryPrincipalType === 'group') return 'Group';
    if (effectiveDirectoryPrincipalType === 'user') return 'AD/LDAP';
    return mode === 'directory_group' ? 'Group' : 'AD/LDAP';
  }
</script>

<div class="identity-wizard">
  <header class="identity-wizard__header">
    <div>
      <h2 id="identity-wizard-title">Add identity</h2>
      <p>Grant application access to a local account, AD user, or AD group.</p>
      <p>This does not modify NTFS permissions.</p>
    </div>
  </header>

  <div class="identity-wizard__stepper" aria-label="Add identity steps">
    <div class:active={step === 1} class:complete={step > 1}>
      <span>1</span>
      <strong>Choose type</strong>
    </div>
    <i></i>
    <div class:active={step === 2}>
      <span>2</span>
      <strong>Configure</strong>
    </div>
  </div>

  {#if errorMessage}
    <div class="identity-wizard__error" role="alert">
      <strong>{errorMessage}</strong>
      {#if errorHint}
        <span>{errorHint}</span>
      {/if}
    </div>
  {/if}

  {#if step === 1}
    <section class="identity-wizard__step">
      <h3>How do you want to add access?</h3>
      <div class="identity-wizard__cards">
        {#each modeCards as card}
          <button
            type="button"
            class="identity-wizard__choice"
            on:click={() => void chooseMode(card.id)}
            disabled={loadingSources}
          >
            <span class="identity-wizard__choice-icon" aria-hidden="true"><i class={`bi ${card.icon}`}></i></span>
            <span class="identity-wizard__choice-body">
              <span class="identity-wizard__choice-head">
                <strong>{card.label}</strong>
                <em>{card.badge}</em>
              </span>
              {#each card.description as line}
                <small>{line}</small>
              {/each}
            </span>
            <span class="identity-wizard__choice-arrow" aria-hidden="true"><i class="bi bi-chevron-right"></i></span>
          </button>
        {/each}
      </div>
    </section>
  {:else if mode}
    <section class="identity-wizard__step">
      <div class="identity-wizard__section-head">
        <div>
          <h3>{mode === 'local' ? 'Local user' : currentDirectoryTitle()}</h3>
          <p>
            {#if mode === 'local'}
              Create a new local account that is managed within BornToShare.
            {:else if isSelectedGroup || mode === 'directory_group'}
              Allow all members of an AD/LDAP group to sign in.
            {:else}
              Import one user from a configured identity source.
            {/if}
          </p>
        </div>
        <span class="identity-wizard__badge">{mode === 'local' ? 'Local' : currentDirectoryBadge()}</span>
      </div>

      {#if mode === 'local'}
        <div class="identity-wizard__form-grid">
          <label>
            <span>Username *</span>
            <input bind:value={localUsername} maxlength="255" placeholder="e.g., jdoe" />
            {#if localUsernameError}<small class="identity-wizard__field-error">{localUsernameError}</small>{/if}
          </label>
          <label>
            <span>Display name *</span>
            <input bind:value={localDisplayName} maxlength="255" placeholder="e.g., John Doe" />
            {#if localDisplayNameError}<small class="identity-wizard__field-error">{localDisplayNameError}</small>{/if}
          </label>
          <label>
            <span>Email</span>
            <input bind:value={localEmail} maxlength="255" placeholder="e.g., john.doe@example.com" />
          </label>
          <label>
            <span>Temporary password *</span>
            <input bind:value={localPassword} type="password" maxlength="255" placeholder="Enter a strong password" />
            {#if localPasswordError}<small class="identity-wizard__field-error">{localPasswordError}</small>{/if}
          </label>
        </div>

        <label class="identity-wizard__checkbox">
          <input bind:checked={requirePasswordChange} type="checkbox" />
          <span>
            <strong>Require password change at first login</strong>
            <small>User will be forced to change their password on first sign-in.</small>
          </span>
        </label>
      {:else}
        <div class="identity-wizard__form-grid">
          <label>
            <span>Identity source *</span>
            <select bind:value={selectedSourceId} on:change={handleSourceChange}>
              {#each adSources as source}
                <option value={source.id}>{source.name ?? `Identity source #${source.id}`}</option>
              {/each}
            </select>
            {#if sourceError}<small class="identity-wizard__field-error">{sourceError}</small>{/if}
          </label>
          <label>
            <span>{mode === 'directory_group' ? 'Search group *' : 'Search user *'}</span>
            <div class="identity-wizard__search-row">
              <div class="identity-wizard__search">
                <input
                  bind:value={searchQuery}
                  placeholder={mode === 'directory_group' ? 'Search by group name or DN' : 'Search by name, username or email'}
                  on:input={scheduleSearch}
                />
                <i class="bi bi-search" aria-hidden="true"></i>
              </div>
              <button type="button" class="identity-wizard__browse" on:click={() => void openAdBrowser()}>
                Browse directory
              </button>
            </div>
            {#if principalError}<small class="identity-wizard__field-error">{principalError}</small>{/if}
          </label>
        </div>

        {#if searchLoading}
          <div class="identity-wizard__search-state">Searching directory...</div>
        {:else if searchResults.length}
          <div class="identity-wizard__results">
            {#each searchResults as item}
              <button type="button" class="identity-wizard__result" on:click={() => choosePrincipal(item)}>
                <span class="identity-wizard__result-avatar">{principalAvatar(item)}</span>
                <span class="identity-wizard__result-body">
                  <strong>{principalTitle(item)}</strong>
                  <small>{principalSubline(item) || (mode === 'directory_group' ? 'Directory group' : 'Directory user')}</small>
                  {#if principalThirdLine(item)}
                    <small>{principalThirdLine(item)}</small>
                  {/if}
                </span>
              </button>
            {/each}
          </div>
        {:else if !selectedPrincipal}
          <div class="identity-wizard__empty-state">
            No directory {mode === 'directory_group' ? 'group' : 'user'} selected yet.
          </div>
        {/if}

        {#if selectedPrincipal}
          <div class="identity-wizard__selection">
            <div class="identity-wizard__selection-head">Selected {isSelectedGroup ? 'group' : 'user'}</div>
            <div class="identity-wizard__selection-card">
              <span class="identity-wizard__result-avatar">{principalAvatar(selectedPrincipal)}</span>
              <div>
                <strong>{principalTitle(selectedPrincipal)}</strong>
                <small>{principalSubline(selectedPrincipal)}</small>
                {#if principalThirdLine(selectedPrincipal)}
                  <small>{principalThirdLine(selectedPrincipal)}</small>
                {/if}
              </div>
              <button type="button" aria-label="Clear selection" on:click={clearSelection}>
                <i class="bi bi-x-lg"></i>
              </button>
            </div>
          </div>
        {/if}

        <div class:warning={isSelectedGroup || mode === 'directory_group'} class="identity-wizard__info">
          <i class={`bi ${isSelectedGroup || mode === 'directory_group' ? 'bi-exclamation-triangle' : 'bi-info-circle'}`} aria-hidden="true"></i>
          <span>
            {#if isSelectedGroup || mode === 'directory_group'}
              Members of this group will inherit the selected application role. NTFS permissions are not modified.
            {:else}
              The user will be able to sign in to BornToShare using their directory credentials.
            {/if}
          </span>
        </div>
      {/if}

      <div class="identity-wizard__role-section">
        <div class="identity-wizard__role-head">
          <h4>{isSelectedGroup || mode === 'directory_group' ? 'Application role for group members *' : 'Application role *'}</h4>
          <p>{helperText()}</p>
        </div>
        <div class="identity-wizard__roles">
          <button
            type="button"
            class:selected={applicationRole === 'user'}
            on:click={() => (applicationRole = 'user')}
          >
            <span class="identity-wizard__role-icon"><i class="bi bi-person"></i></span>
            <span>
              <strong>User</strong>
              <small>Standard platform access.</small>
            </span>
            <i class={`bi ${applicationRole === 'user' ? 'bi-record-circle-fill' : 'bi-circle'}`}></i>
          </button>
          <button
            type="button"
            class:selected={applicationRole === 'platform_admin'}
            on:click={() => (applicationRole = 'platform_admin')}
          >
            <span class="identity-wizard__role-icon"><i class="bi bi-shield"></i></span>
            <span>
              <strong>Platform Administrator</strong>
              <small>Full platform administration.</small>
            </span>
            <i class={`bi ${applicationRole === 'platform_admin' ? 'bi-record-circle-fill' : 'bi-circle'}`}></i>
          </button>
        </div>
        {#if roleError}
          <small class="identity-wizard__field-error">{roleError}</small>
        {/if}
      </div>
    </section>
  {/if}

  <footer class="identity-wizard__footer">
    {#if step === 1}
      <div class="identity-wizard__footer-note">
        <i class="bi bi-info-circle" aria-hidden="true"></i>
        <span>Application roles only: User and Platform Administrator. NTFS permissions are managed from Storage Roots.</span>
      </div>
      <div class="identity-wizard__footer-actions">
        <button class="identity-wizard__ghost" type="button" on:click={onCancel}>Cancel</button>
      </div>
    {:else}
      <div class="identity-wizard__footer-actions">
        <button class="identity-wizard__ghost" type="button" on:click={onCancel}>Cancel</button>
        <button class="identity-wizard__ghost" type="button" on:click={handleBack}>Back</button>
        <button
          class="identity-wizard__primary"
          type="button"
          on:click={() => void submit()}
          disabled={submitting || (mode === 'local' ? !localFormValid() : !directoryFormValid())}
          title={submitting || (mode === 'local' ? localFormValid() : directoryFormValid()) ? undefined : submitDisabledReason}
        >
          {submitLabel()}
        </button>
      </div>
      {#if !submitting && ((mode === 'local' && !localFormValid()) || (isDirectoryMode(mode) && !directoryFormValid()))}
        <div class="identity-wizard__footer-reason">{submitDisabledReason}</div>
      {/if}
    {/if}
  </footer>
</div>

<IdentityBrowserModal
  open={showAdBrowser}
  onClose={() => (showAdBrowser = false)}
  onSelect={onSelectFromAdBrowser}
  identitySources={[]}
  initialSourceId={selectedSourceId}
  title="Browse Active Directory"
  subtitle="Select a directory user or group to grant application access."
  mode="single"
  allowRoleAssignment={false}
  allowedPrincipalType="all"
  includeImportCandidates={true}
  busy={submitting}
  confirmLabel="Use selected"
  confirmBusyLabel="Applying..."
/>

<style>
  .identity-wizard {
    width: min(100%, 930px);
    max-height: min(88vh, 920px);
    overflow: auto;
    padding: 24px 28px 18px;
    color: #0d1b44;
  }

  .identity-wizard__header h2 {
    margin: 0;
    font-size: 2.1rem;
    line-height: 1.05;
    font-weight: 760;
  }

  .identity-wizard__header p {
    margin: 4px 0 0;
    color: #465b78;
    font-size: 0.96rem;
  }

  .identity-wizard__field-error,
  .identity-wizard__footer-reason {
    display: block;
    margin-top: 6px;
    font-size: 12px;
    font-weight: 700;
    color: var(--b2s-color-danger, #dc3545);
  }

  .identity-wizard__footer-reason {
    color: var(--b2s-color-text-muted, #64748b);
    text-align: right;
  }

  .identity-wizard__stepper {
    display: flex;
    align-items: center;
    gap: 12px;
    margin: 18px 0 18px;
  }

  .identity-wizard__stepper > div {
    display: flex;
    align-items: center;
    gap: 12px;
    color: #5d708f;
    font-weight: 600;
  }

  .identity-wizard__stepper > div span {
    width: 34px;
    height: 34px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 999px;
    border: 1px solid #ced8e6;
    background: #fff;
  }

  .identity-wizard__stepper > div.active span,
  .identity-wizard__stepper > div.complete span {
    border-color: #2268f4;
    background: #2268f4;
    color: #fff;
  }

  .identity-wizard__stepper > i {
    flex: 1 1 auto;
    height: 1px;
    background: #dbe4f0;
  }

  .identity-wizard__error {
    display: grid;
    gap: 4px;
    padding: 14px 16px;
    margin-bottom: 14px;
    border: 1px solid #f0c7c7;
    border-radius: 8px;
    background: #fff4f4;
    color: #8d1f1f;
  }

  .identity-wizard__step h3 {
    margin: 0 0 12px;
    font-size: 1.45rem;
    line-height: 1.1;
    font-weight: 730;
  }

  .identity-wizard__cards {
    display: grid;
    gap: 12px;
  }

  .identity-wizard__choice {
    width: 100%;
    display: grid;
    grid-template-columns: 60px minmax(0, 1fr) 20px;
    gap: 18px;
    align-items: center;
    padding: 14px 16px;
    border: 1px solid #d8e1ef;
    border-radius: 12px;
    background: #fff;
    text-align: left;
    transition: border-color 0.16s ease, box-shadow 0.16s ease, background 0.16s ease;
  }

  .identity-wizard__choice:hover {
    border-color: #2268f4;
    background: #f7faff;
    box-shadow: 0 10px 24px rgba(34, 104, 244, 0.08);
  }

  .identity-wizard__choice-icon,
  .identity-wizard__result-avatar {
    width: 48px;
    height: 48px;
    border-radius: 14px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: #edf3ff;
    color: #2268f4;
    font-size: 1.35rem;
    font-weight: 700;
  }

  .identity-wizard__choice-body {
    display: grid;
    gap: 4px;
  }

  .identity-wizard__choice-head {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
  }

  .identity-wizard__choice-head strong {
    font-size: 1.12rem;
  }

  .identity-wizard__choice-head em,
  .identity-wizard__badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 4px 12px;
    border-radius: 999px;
    background: #eef5ff;
    color: #2268f4;
    font-style: normal;
    font-size: 0.82rem;
    font-weight: 700;
  }

  .identity-wizard__choice-body small,
  .identity-wizard__section-head p,
  .identity-wizard__role-head p,
  .identity-wizard__checkbox small,
  .identity-wizard__info span,
  .identity-wizard__footer-note span,
  .identity-wizard__search-state {
    color: #546881;
    font-size: 0.95rem;
    line-height: 1.45;
  }

  .identity-wizard__choice-arrow {
    justify-self: end;
    color: #6d7f99;
    font-size: 1.1rem;
  }

  .identity-wizard__section-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 12px;
  }

  .identity-wizard__form-grid {
    display: grid;
    gap: 12px;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    margin-bottom: 12px;
  }

  .identity-wizard__form-grid label {
    display: grid;
    gap: 8px;
  }

  .identity-wizard__form-grid label span,
  .identity-wizard__selection-head,
  .identity-wizard__role-head h4 {
    font-size: 0.98rem;
    font-weight: 700;
    color: #10214f;
  }

  .identity-wizard__form-grid input,
  .identity-wizard__form-grid select,
  .identity-wizard__search input {
    width: 100%;
    min-height: 46px;
    border: 1px solid #d8e1ef;
    border-radius: 10px;
    padding: 0 16px;
    background: #fff;
    color: #10214f;
    font-size: 0.98rem;
  }

  .identity-wizard__search {
    position: relative;
  }

  .identity-wizard__search-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 12px;
    align-items: center;
  }

  .identity-wizard__search input {
    padding-right: 42px;
  }

  .identity-wizard__search i {
    position: absolute;
    right: 14px;
    top: 50%;
    transform: translateY(-50%);
    color: #687c98;
  }

  .identity-wizard__browse {
    min-height: 46px;
    padding: 0 16px;
    border: 1px solid #d8e1ef;
    border-radius: 10px;
    background: #fff;
    color: #10214f;
    font-size: 0.95rem;
    font-weight: 700;
    transition: border-color 0.16s ease, box-shadow 0.16s ease, color 0.16s ease;
  }

  .identity-wizard__browse:hover {
    border-color: #2268f4;
    color: #2268f4;
  }

  .identity-wizard__browse:focus-visible {
    outline: none;
    border-color: #2268f4;
    box-shadow: 0 0 0 3px rgba(34, 104, 244, 0.14);
  }

  .identity-wizard__checkbox {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    padding: 2px 0 6px;
  }

  .identity-wizard__checkbox input {
    margin-top: 3px;
    width: 18px;
    height: 18px;
    accent-color: #2268f4;
  }

  .identity-wizard__checkbox strong {
    display: block;
    margin-bottom: 4px;
    font-size: 0.98rem;
  }

  .identity-wizard__results {
    display: grid;
    gap: 10px;
    max-height: 200px;
    overflow: auto;
    margin-bottom: 12px;
  }

  .identity-wizard__empty-state {
    margin-bottom: 12px;
    padding: 12px 14px;
    border: 1px dashed #d8e1ef;
    border-radius: 10px;
    color: #5d708f;
    font-size: 0.92rem;
    background: #fbfcfe;
  }

  .identity-wizard__result,
  .identity-wizard__selection-card {
    display: grid;
    grid-template-columns: 48px minmax(0, 1fr) auto;
    gap: 14px;
    align-items: center;
    padding: 14px 16px;
    border: 1px solid #d8e1ef;
    border-radius: 12px;
    background: #fff;
    text-align: left;
  }

  .identity-wizard__result {
    width: 100%;
  }

  .identity-wizard__result:hover {
    border-color: #2268f4;
    background: #f8fbff;
  }

  .identity-wizard__result-body,
  .identity-wizard__selection-card div {
    display: grid;
    gap: 3px;
  }

  .identity-wizard__result-body strong,
  .identity-wizard__selection-card strong {
    font-size: 1rem;
    color: #10214f;
  }

  .identity-wizard__result-body small,
  .identity-wizard__selection-card small {
    color: #5d708f;
    font-size: 0.9rem;
    line-height: 1.35;
  }

  .identity-wizard__selection {
    margin-bottom: 12px;
  }

  .identity-wizard__selection-head {
    margin-bottom: 10px;
  }

  .identity-wizard__selection-card button {
    width: 34px;
    height: 34px;
    border-radius: 10px;
    border: 1px solid #d8e1ef;
    background: #fff;
    color: #4e617b;
  }

  .identity-wizard__info {
    display: flex;
    gap: 12px;
    align-items: flex-start;
    padding: 12px 14px;
    border-radius: 10px;
    background: #eef5ff;
    color: #2268f4;
    margin-bottom: 14px;
  }

  .identity-wizard__info.warning {
    background: #fff7e7;
    color: #c67b00;
  }

  .identity-wizard__role-section {
    padding-top: 2px;
  }

  .identity-wizard__role-head h4 {
    margin: 0 0 6px;
  }

  .identity-wizard__role-head p {
    margin: 0 0 10px;
  }

  .identity-wizard__roles {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 16px;
  }

  .identity-wizard__roles button {
    display: grid;
    grid-template-columns: 32px minmax(0, 1fr) 20px;
    gap: 12px;
    align-items: start;
    padding: 14px 14px;
    border: 1px solid #d8e1ef;
    border-radius: 12px;
    background: #fff;
    text-align: left;
  }

  .identity-wizard__roles button.selected {
    border-color: #2268f4;
    background: #f7faff;
    box-shadow: inset 0 0 0 1px rgba(34, 104, 244, 0.15);
  }

  .identity-wizard__role-icon {
    color: #10214f;
    font-size: 1.25rem;
    padding-top: 2px;
  }

  .identity-wizard__roles strong {
    display: block;
    margin-bottom: 5px;
    font-size: 1rem;
  }

  .identity-wizard__roles small {
    color: #5d708f;
    font-size: 0.9rem;
    line-height: 1.35;
  }

  .identity-wizard__roles .bi-record-circle-fill {
    color: #2268f4;
  }

  .identity-wizard__footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding-top: 16px;
    margin-top: 16px;
    border-top: 1px solid #e3eaf4;
    position: sticky;
    bottom: 0;
    background: #fff;
  }

  .identity-wizard__footer-note {
    display: flex;
    gap: 12px;
    align-items: flex-start;
    max-width: 560px;
    color: #2268f4;
  }

  .identity-wizard__footer-actions {
    margin-left: auto;
    display: flex;
    gap: 12px;
    align-items: center;
  }

  .identity-wizard__ghost,
  .identity-wizard__primary {
    min-width: 120px;
    min-height: 44px;
    padding: 0 18px;
    border-radius: 10px;
    font-size: 0.97rem;
    font-weight: 700;
  }

  .identity-wizard__ghost {
    border: 1px solid #d8e1ef;
    background: #fff;
    color: #10214f;
  }

  .identity-wizard__primary {
    border: 1px solid #0a4fcb;
    background: #2268f4;
    color: #fff;
  }

  .identity-wizard__primary:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }

  @media (max-width: 900px) {
    .identity-wizard {
      width: 100%;
      padding: 24px 20px;
    }

    .identity-wizard__form-grid,
    .identity-wizard__roles {
      grid-template-columns: 1fr;
    }

    .identity-wizard__search-row {
      grid-template-columns: 1fr;
    }

    .identity-wizard__section-head,
    .identity-wizard__footer {
      flex-direction: column;
      align-items: stretch;
    }

    .identity-wizard__footer-actions {
      margin-left: 0;
      width: 100%;
      justify-content: flex-end;
      flex-wrap: wrap;
    }
  }
</style>
