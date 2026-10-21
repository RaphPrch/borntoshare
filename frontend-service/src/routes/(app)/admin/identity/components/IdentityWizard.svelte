<script lang="ts">
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import FieldError from '$lib/components/ui/FieldError.svelte';
  import { t } from '$lib/i18n';
  import WizardShell from '$lib/components/ui/WizardShell.svelte';
  import ChoiceCard from '$lib/components/ui/ChoiceCard.svelte';
  import { createEventDispatcher } from 'svelte';
  import { createIdentity, type CreateIdentityPayload } from '$lib/api/identity';
  import { listIdentitySources, type IdentitySourceListItem } from '$lib/api/identity-sources';
  import IdentityBrowserModal from '$lib/components/identity/IdentityBrowserModal.svelte';
  import { toast } from '$lib/stores/toast';
  import { presentErrorHint, presentErrorMessage, toAppError } from '$lib/errors';
  import { searchBrowserDirectory } from '$lib/components/identity/identity-browser.controller';
  import type { PrincipalSearchItem } from '$lib/utils/principal-search';
  import type { IdentityBrowserSelectionPayload } from '$lib/types/identity-browser';

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
      label: t('Local user'),
      badge: t('Local'),
      icon: 'bi-person',
      description: [
        'Create a BornToShare account that is managed locally.',
        'Best for break-glass admins or local platform users.'
      ]
    },
    {
      id: 'directory_user',
      label: t('Directory user'),
      badge: 'AD/LDAP',
      icon: 'bi-people',
      description: [
        'Import one user from a configured identity source.',
        'The user keeps authenticating through the directory.'
      ]
    },
    {
      id: 'directory_group',
      label: t('Directory group'),
      badge: t('Group'),
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
        toast.warning(t('Import impossible: aucune identity source Active Directory active n\'est definie.'));
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
      return count > 0 ? t('{count} members', { count }) : trimmed(item.dn ?? item.external_id);
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
      toast.warning(t('Impossible d\'ouvrir le browser AD : aucune identity source Active Directory n\'est selectionnee.'));
      return;
    }
    showAdBrowser = true;
  }

  function onSelectFromAdBrowser(payload: IdentityBrowserSelectionPayload) {
    const selected = Array.isArray(payload?.selectedItems) ? payload.selectedItems[0] : null;
    if (!selected) {
      toast.warning(t('No directory identity selected.'));
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

  // Reactive (not functions): template expressions must re-run when a field changes
  $: localFormValid =
    trimmed(localUsername).length > 0 &&
    trimmed(localDisplayName).length > 0 &&
    trimmed(localPassword).length > 0 &&
    Boolean(applicationRole);

  $: directoryFormValid = canImportDirectoryPrincipal;
  $: localUsernameError = attemptedSubmit && !trimmed(localUsername) ? t('Username is required.') : '';
  $: localDisplayNameError = attemptedSubmit && !trimmed(localDisplayName) ? t('Display name is required.') : '';
  $: localPasswordError = attemptedSubmit && !trimmed(localPassword) ? t('Temporary password is required.') : '';
  $: sourceError = attemptedSubmit && isDirectoryMode(mode) && !resolvedDirectorySourceId ? t('Select an identity source first.') : '';
  $: principalError = attemptedSubmit && isDirectoryMode(mode) && !selectedPrincipal
    ? mode === 'directory_group'
      ? t('Select a directory group first.')
      : t('Select a directory user first.')
    : '';
  $: roleError = attemptedSubmit && !applicationRole ? t('Select an application role first.') : '';
  $: submitDisabledReason = mode === 'local'
    ? localUsernameError || localDisplayNameError || localPasswordError || roleError || t('Complete required fields first.')
    : sourceError || principalError || roleError || t('Complete required fields first.');

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

    if (mode === 'local' && !localFormValid) return;
    if (isDirectoryMode(mode)) {
      if (!resolvedDirectorySourceId) {
        toast.warning(t('Select an identity source first.'));
        return;
      }
      if (!selectedPrincipal) {
        toast.warning(t('Select a user or group first.'));
        return;
      }
      if (!applicationRole) {
        toast.warning(t('Select an application role first.'));
        return;
      }
      if (!directoryFormValid) {
        toast.warning(t('Unable to import identity.'));
        return;
      }
    }

    submitting = true;
    try {
      const created = await createIdentity(fetch, buildCreatePayload());
      toast.success(isSelectedGroup ? t('Group imported.') : t('Identity imported.'));
      dispatch('done', { id: created?.id });
    } catch (error) {
      const appError = toAppError(error, { source: 'ui' });
      errorMessage = presentErrorMessage(appError);
      errorHint = presentErrorHint(appError) ?? '';
      toast.error(t('Unable to import identity.'));
    } finally {
      submitting = false;
    }
  }

  function submitLabel(): string {
    if (mode === 'local') return submitting ? t('Creating...') : t('Create local user');
    if (effectiveDirectoryPrincipalType === 'group') return submitting ? t('Importing...') : t('Import group');
    if (effectiveDirectoryPrincipalType === 'user') return submitting ? t('Importing...') : t('Import user');
    return submitting ? t('Importing...') : t('Import identity');
  }

  function helperText(): string {
    if (effectiveDirectoryPrincipalType === 'group') {
      return t('Define the application role that will be applied to all members.');
    }
    return t('Define the application role for this user.');
  }

  function currentDirectoryTitle(): string {
    if (effectiveDirectoryPrincipalType === 'group') return t('Directory group');
    if (effectiveDirectoryPrincipalType === 'user') return t('Directory user');
    return mode === 'directory_group' ? t('Directory group') : t('Directory user');
  }

  function currentDirectoryBadge(): string {
    if (effectiveDirectoryPrincipalType === 'group') return t('Group');
    if (effectiveDirectoryPrincipalType === 'user') return t('AD/LDAP');
    return mode === 'directory_group' ? t('Group') : t('AD/LDAP');
  }
</script>

<WizardShell
  {open}
  onClose={onCancel}
  title={t('Add identity')}
  subtitle={t('Grant application access to a local account, AD user, or AD group. NTFS permissions are not modified.')}
  iconClass="bi bi-person-plus"
  ariaLabelledby="identity-wizard-title"
  steps={[
    { label: t('Choose type'), hint: t('Local account, AD user or AD group') },
    { label: t('Configure'), hint: t('Identity and application role') }
  ]}
  current={step}
>
<div class="identity-wizard">
  {#if errorMessage}
    <InlineAlert tone="error" title={errorMessage}>{errorHint ?? ''}</InlineAlert>
  {/if}

  {#if step === 1}
    <section class="identity-wizard__step">
      <h3>{t('How do you want to add access?')}</h3>
      <div class="identity-wizard__cards">
        {#each modeCards as card}
          <ChoiceCard
            icon={card.icon}
            title={card.label}
            description={card.description.map((line) => t(line)).join(' ')}
            badge={card.badge}
            navigates
            disabled={loadingSources}
            onSelect={() => void chooseMode(card.id)}
          />
        {/each}
      </div>
    </section>
  {:else if mode}
    <section class="identity-wizard__step">
      <div class="identity-wizard__section-head">
        <div>
          <h3>{mode === 'local' ? t('Local user') : currentDirectoryTitle()}</h3>
          <p>
            {#if mode === 'local'}
              {t('Create a new local account that is managed within BornToShare.')}
            {:else if isSelectedGroup || mode === 'directory_group'}
              {t('Allow all members of an AD/LDAP group to sign in.')}
            {:else}
              {t('Import one user from a configured identity source.')}
            {/if}
          </p>
        </div>
        <span class="identity-wizard__badge">{mode === 'local' ? t('Local') : currentDirectoryBadge()}</span>
      </div>

      {#if mode === 'local'}
        <div class="identity-wizard__form-grid">
          <label>
            <span>{t('Username *')}</span>
            <input bind:value={localUsername} maxlength="255" placeholder={t('e.g., jdoe')} />
            {#if localUsernameError}<FieldError>{localUsernameError}</FieldError>{/if}
          </label>
          <label>
            <span>{t('Display name *')}</span>
            <input bind:value={localDisplayName} maxlength="255" placeholder={t('e.g., John Doe')} />
            {#if localDisplayNameError}<FieldError>{localDisplayNameError}</FieldError>{/if}
          </label>
          <label>
            <span>{t('Email')}</span>
            <input bind:value={localEmail} maxlength="255" placeholder={t('e.g., john.doe@example.com')} />
          </label>
          <label>
            <span>{t('Temporary password *')}</span>
            <input bind:value={localPassword} type="password" maxlength="255" placeholder={t('Enter a strong password')} />
            {#if localPasswordError}<FieldError>{localPasswordError}</FieldError>{/if}
          </label>
        </div>

        <label class="identity-wizard__checkbox">
          <input bind:checked={requirePasswordChange} type="checkbox" />
          <span>
            <strong>{t('Require password change at first login')}</strong>
            <small>{t('User will be forced to change their password on first sign-in.')}</small>
          </span>
        </label>
      {:else}
        <div class="identity-wizard__form-grid">
          <label>
            <span>{t('Identity source *')}</span>
            <select bind:value={selectedSourceId} on:change={handleSourceChange}>
              {#each adSources as source}
                <option value={source.id}>{source.name ?? t('Identity source #{id}', { id: source.id })}</option>
              {/each}
            </select>
            {#if sourceError}<FieldError>{sourceError}</FieldError>{/if}
          </label>
          <label>
            <span>{mode === 'directory_group' ? t('Search group *') : t('Search user *')}</span>
            <div class="identity-wizard__search-row">
              <div class="identity-wizard__search">
                <input
                  bind:value={searchQuery}
                  placeholder={mode === 'directory_group' ? t('Search by group name or DN') : t('Search by name, username or email')}
                  on:input={scheduleSearch}
                />
                <i class="bi bi-search" aria-hidden="true"></i>
              </div>
              <button type="button" class="b2s-btn b2s-btn-secondary" on:click={() => void openAdBrowser()}>
                {t('Browse directory')}
              </button>
            </div>
            {#if principalError}<FieldError>{principalError}</FieldError>{/if}
          </label>
        </div>

        {#if searchLoading}
          <div class="identity-wizard__search-state">{t('Searching directory...')}</div>
        {:else if searchResults.length}
          <div class="identity-wizard__results">
            {#each searchResults as item}
              <button type="button" class="identity-wizard__result" on:click={() => choosePrincipal(item)}>
                <span class="identity-wizard__result-avatar">{principalAvatar(item)}</span>
                <span class="identity-wizard__result-body">
                  <strong>{principalTitle(item)}</strong>
                  <small>{principalSubline(item) || (mode === 'directory_group' ? t('Directory group') : t('Directory user'))}</small>
                  {#if principalThirdLine(item)}
                    <small>{principalThirdLine(item)}</small>
                  {/if}
                </span>
              </button>
            {/each}
          </div>
        {:else if !selectedPrincipal}
          <div class="identity-wizard__empty-state">
            {mode === 'directory_group' ? t('No directory group selected yet.') : t('No directory user selected yet.')}
          </div>
        {/if}

        {#if selectedPrincipal}
          <div class="identity-wizard__selection">
            <div class="identity-wizard__selection-head">{isSelectedGroup ? t('Selected group') : t('Selected user')}</div>
            <div class="identity-wizard__selection-card">
              <span class="identity-wizard__result-avatar">{principalAvatar(selectedPrincipal)}</span>
              <div>
                <strong>{principalTitle(selectedPrincipal)}</strong>
                <small>{principalSubline(selectedPrincipal)}</small>
                {#if principalThirdLine(selectedPrincipal)}
                  <small>{principalThirdLine(selectedPrincipal)}</small>
                {/if}
              </div>
              <button type="button" aria-label={t('Clear selection')} on:click={clearSelection}>
                <i class="bi bi-x-lg"></i>
              </button>
            </div>
          </div>
        {/if}

        {#if isSelectedGroup || mode === 'directory_group'}
          <InlineAlert tone="warning" compact>
            {t('Members of this group will inherit the selected application role. NTFS permissions are not modified.')}
          </InlineAlert>
        {:else}
          <InlineAlert tone="info" compact>
            {t('The user will be able to sign in to BornToShare using their directory credentials.')}
          </InlineAlert>
        {/if}
      {/if}

      <div class="identity-wizard__role-section">
        <div class="identity-wizard__role-head">
          <h4>{isSelectedGroup || mode === 'directory_group' ? t('Application role for group members *') : t('Application role *')}</h4>
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
              <strong>{t('User')}</strong>
              <small>{t('Standard platform access.')}</small>
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
              <strong>{t('Platform Administrator')}</strong>
              <small>{t('Full platform administration.')}</small>
            </span>
            <i class={`bi ${applicationRole === 'platform_admin' ? 'bi-record-circle-fill' : 'bi-circle'}`}></i>
          </button>
        </div>
        {#if roleError}
          <FieldError>{roleError}</FieldError>
        {/if}
      </div>
    </section>
  {/if}

</div>

  <svelte:fragment slot="footer-start">
    {#if step === 1}
      {t('Application roles only: User and Platform Administrator. NTFS permissions are managed from Storage Roots.')}
    {:else if !submitting && ((mode === 'local' && !localFormValid) || (isDirectoryMode(mode) && !directoryFormValid))}
      {submitDisabledReason}
    {/if}
  </svelte:fragment>

  <svelte:fragment slot="footer">
    <button class="b2s-btn b2s-btn-ghost" type="button" on:click={onCancel}>{t('Cancel')}</button>
    {#if step > 1}
      <button class="b2s-btn b2s-btn-secondary" type="button" on:click={handleBack}>
        <i class="bi bi-arrow-left" aria-hidden="true"></i>
        {t('Back')}
      </button>
      <button
        class="b2s-btn b2s-btn-primary"
        type="button"
        on:click={() => void submit()}
        disabled={submitting || (mode === 'local' ? !localFormValid : !directoryFormValid)}
      >
        {submitLabel()}
      </button>
    {/if}
  </svelte:fragment>
</WizardShell>

<IdentityBrowserModal
  open={showAdBrowser}
  onClose={() => (showAdBrowser = false)}
  onSelect={onSelectFromAdBrowser}
  identitySources={[]}
  initialSourceId={selectedSourceId}
  title={t('Browse Active Directory')}
  subtitle={t('Select a directory user or group to grant application access.')}
  mode="single"
  allowRoleAssignment={false}
  allowedPrincipalType="all"
  includeImportCandidates={true}
  busy={submitting}
  confirmLabel={t('Use selected')}
  confirmBusyLabel={t('Applying...')}
/>

<style>
  .identity-wizard {
    color: var(--b2s-color-text);
  }

  .identity-wizard__step h3 {
    margin: 0 0 12px;
    font-size: var(--b2s-fs-lg);
    line-height: 1.3;
    font-weight: 600;
  }

  .identity-wizard__cards {
    display: grid;
    gap: 12px;
  }
  .identity-wizard__result-avatar {
    width: 48px;
    height: 48px;
    border-radius: var(--b2s-radius-lg);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: #edf3ff;
    color: #2268f4;
    font-size: 1.35rem;
    font-weight: 700;
  }
  .identity-wizard__badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 4px 12px;
    border-radius: var(--b2s-radius-pill);
    background: #eef5ff;
    color: #2268f4;
    font-style: normal;
    font-size: var(--b2s-fs-sm);
    font-weight: 700;
  }
  .identity-wizard__section-head p,
  .identity-wizard__role-head p,
  .identity-wizard__checkbox small,
  .identity-wizard__search-state {
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-sm);
    line-height: 1.45;
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
    font-size: var(--b2s-fs-sm);
    font-weight: 500;
    color: var(--b2s-color-text);
  }

  .identity-wizard__form-grid input,
  .identity-wizard__form-grid select,
  .identity-wizard__search input {
    width: 100%;
    min-height: 40px;
    border: 1px solid var(--b2s-color-border);
    border-radius: var(--b2s-radius-sm);
    padding: 0 12px;
    background: #fff;
    color: #10214f;
    font-size: var(--b2s-fs-lg);
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
    font-size: var(--b2s-fs-lg);
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
    border-radius: var(--b2s-radius-md);
    color: #5d708f;
    font-size: var(--b2s-fs-md);
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
    border-radius: var(--b2s-radius-md);
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
    font-size: var(--b2s-fs-lg);
    color: #10214f;
  }

  .identity-wizard__result-body small,
  .identity-wizard__selection-card small {
    color: #5d708f;
    font-size: var(--b2s-fs-md);
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
    border-radius: var(--b2s-radius-md);
    border: 1px solid #d8e1ef;
    background: #fff;
    color: #4e617b;
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
    border-radius: var(--b2s-radius-md);
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
    font-size: var(--b2s-fs-lg);
  }

  .identity-wizard__roles small {
    color: #5d708f;
    font-size: var(--b2s-fs-md);
    line-height: 1.35;
  }

  .identity-wizard__roles .bi-record-circle-fill {
    color: #2268f4;
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

    .identity-wizard__section-head{
      flex-direction: column;
      align-items: stretch;
    }
  }
</style>
