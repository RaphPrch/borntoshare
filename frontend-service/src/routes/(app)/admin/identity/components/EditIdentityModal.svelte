<script lang="ts">
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import FieldError from '$lib/components/ui/FieldError.svelte';
  import { t } from '$lib/i18n';
  import { normalizeText } from '$lib/utils/values';
  import { createEventDispatcher } from 'svelte';
  import ConfirmActionModal from '$lib/components/ui/ConfirmActionModal.svelte';
  import Drawer from '$lib/components/ui/Drawer.svelte';
  import { adminChangePassword, updateIdentity } from '$lib/api/identity';
  import { toast } from '$lib/stores/toast';
  import { initials } from '$lib/utils/format';

  export let open = false;
  export let identity: any = null;
  export let onClose: (() => void) | null = null;

  const dispatch = createEventDispatcher<{ done: void }>();

  let displayName = '';
  let active = true;
  let selectedRole: 'user' | 'platform_admin' = 'user';
  let currentPassword = '';
  let newPassword = '';
  let confirmPassword = '';
  let loading = false;
  let error: string | null = null;
  let initKey = '';
  let closeConfirmOpen = false;
  let attemptedSubmit = false;

  $: isGroup = identity?.type === 'group';
  $: isUser = identity?.type !== 'group';
  $: isLocalUser = isUser && normalizeText(identity?.auth_source ?? identity?.source) === 'local';
  let currentRole: 'platform_admin' | 'user' = 'user';
  $: currentRole = Array.isArray(identity?.roles) && identity.roles.some((role: string) => normalizeText(role) === 'platform_admin')
    ? 'platform_admin'
    : 'user';
  $: currentKey = `${open ? 'open' : 'closed'}:${identity?.type ?? 'none'}:${identity?.id ?? 'none'}`;
  $: if (currentKey !== initKey) {
    displayName = String(identity?.display_name ?? identity?.username ?? '');
    active = identity?.status !== 'inactive';
    selectedRole = currentRole;
    currentPassword = '';
    newPassword = '';
    confirmPassword = '';
    error = null;
    initKey = currentKey;
  }

  $: title = isGroup ? t('Edit group') : t('Edit account');
  $: subtitle = String(identity?.display_name ?? identity?.username ?? '').trim() || t('Unknown identity');
  $: roleLabel = selectedRole === 'platform_admin' ? t('Platform administrator') : t('User');
  $: canEditPassword = isLocalUser;
  $: canToggleActive = isUser;
  $: baselineDisplayName = String(identity?.display_name ?? identity?.username ?? '').trim();
  $: baselineActive = identity?.status !== 'inactive';
  $: isDirty =
    displayName.trim() !== baselineDisplayName ||
    active !== baselineActive ||
    selectedRole !== currentRole ||
    Boolean(currentPassword || newPassword || confirmPassword);
  $: displayNameError = attemptedSubmit && !displayName.trim() ? t('Display name is required.') : '';
  $: currentPasswordError =
    attemptedSubmit && canEditPassword && Boolean(newPassword || confirmPassword) && !currentPassword.trim()
      ? t('Current password is required.')
      : '';
  $: newPasswordError =
    attemptedSubmit && canEditPassword && Boolean(currentPassword || confirmPassword) && !newPassword.trim()
      ? t('New password is required.')
      : '';
  $: confirmPasswordError =
    attemptedSubmit && canEditPassword && Boolean(newPassword) && newPassword !== confirmPassword
      ? t('Password confirmation must match.')
      : '';

  function close() {
    if (loading) return;
    if (isDirty) {
      closeConfirmOpen = true;
      return;
    }
    attemptedSubmit = false;
    error = null;
    currentPassword = '';
    newPassword = '';
    confirmPassword = '';
    onClose?.();
  }

  function handleBackdropClose() {
    close();
  }

  function discardAndClose() {
    closeConfirmOpen = false;
    attemptedSubmit = false;
    error = null;
    currentPassword = '';
    newPassword = '';
    confirmPassword = '';
    onClose?.();
  }

  async function submit() {
    if (!identity?.id) return;
    attemptedSubmit = true;
    error = null;

    const nextDisplayName = displayName.trim();
    if (!nextDisplayName) {
      return;
    }

    const wantsPasswordChange = canEditPassword && Boolean(currentPassword || newPassword || confirmPassword);
    if (wantsPasswordChange) {
      if (!currentPassword.trim()) {
        return;
      }
      if (!newPassword.trim()) {
        return;
      }
      if (newPassword !== confirmPassword) {
        return;
      }
    }

    const payload: {
      identity_type: 'user' | 'group';
      display_name?: string;
      is_active?: boolean;
      application_role?: 'user' | 'platform_admin';
    } = {
      identity_type: isGroup ? 'group' : 'user'
    };

    if (nextDisplayName !== String(identity?.display_name ?? '').trim()) {
      payload.display_name = nextDisplayName;
    }
    if (canToggleActive) {
      const wasActive = identity?.status !== 'inactive';
      if (active !== wasActive) {
        payload.is_active = active;
      }
    }
    if (selectedRole !== currentRole) {
      payload.application_role = selectedRole;
    }

    loading = true;
    try {
      if (payload.display_name !== undefined || payload.is_active !== undefined || payload.application_role !== undefined) {
        await updateIdentity(fetch, identity.id, payload);
      }

      if (wantsPasswordChange) {
        await adminChangePassword(fetch, {
          username: String(identity?.username ?? '').trim(),
          current_password: currentPassword,
          new_password: newPassword
        });
      }

      toast.success(t('Identity updated.'));
      dispatch('done');
      close();
    } catch (err: any) {
      error = err?.message ?? t('Failed to save changes.');
    } finally {
      loading = false;
    }
  }
</script>

<Drawer
  {open}
  onClose={handleBackdropClose}
  title={title}
  subtitle={subtitle}
  rootClass="identity-edit-drawer"
  bodyClass="identity-edit-drawer__body"
  footerClass="identity-edit-drawer__footer"
>
  <div class="identity-edit-head" slot="header-icon">
    <span class={`identity-edit-head__avatar ${isGroup ? 'is-group' : 'is-user'}`} aria-hidden="true">
      {#if isGroup}
        <i class="bi bi-people"></i>
      {:else}
        {initials(subtitle)}
      {/if}
    </span>
  </div>

  <div class="identity-edit-shell">
    <section class="identity-edit-section">
      <div class="identity-edit-section__heading">
        <span class="identity-edit-section__index">1</span>
        <div>
          <h3>{t('Account profile')}</h3>
        </div>
      </div>

      <div class="identity-edit-field">
        <label for="identity-display-name">{t('Display name')}</label>
        <input
          id="identity-display-name"
          class="identity-edit-input"
          class:invalid={Boolean(displayNameError)}
          type="text"
          bind:value={displayName}
          disabled={loading}
        />
        {#if displayNameError}
          <FieldError>{displayNameError}</FieldError>
        {/if}
      </div>

      <div class="identity-edit-field">
        <span>{t('Active account')}</span>
        <label class={`identity-edit-toggle ${!canToggleActive ? 'is-disabled' : ''}`}>
          <input type="checkbox" bind:checked={active} disabled={!canToggleActive || loading} />
          <span class="identity-edit-toggle__track"><span class="identity-edit-toggle__thumb"></span></span>
        </label>
        {#if !canToggleActive}
          <p class="identity-edit-helper">{t('Only user accounts can be disabled.')}</p>
        {/if}
      </div>
    </section>

    <section class="identity-edit-section">
      <div class="identity-edit-section__heading">
        <span class="identity-edit-section__index">2</span>
        <div>
          <h3>{t('Application access')}</h3>
        </div>
      </div>

      <div class="identity-edit-field">
        <span class="identity-edit-label" id="identity-edit-role">{t('Application role')}</span>
        <div class="identity-edit-role-grid" role="radiogroup" aria-labelledby="identity-edit-role">
          <label class={`identity-edit-role-card ${selectedRole === 'user' ? 'is-selected' : ''}`}>
            <input type="radio" bind:group={selectedRole} value="user" disabled={loading} />
            <div>
              <strong>{t('User')}</strong>
              <small>{t('Basic access to application features')}</small>
            </div>
          </label>

          <label class={`identity-edit-role-card ${selectedRole === 'platform_admin' ? 'is-selected' : ''}`}>
            <input type="radio" bind:group={selectedRole} value="platform_admin" disabled={loading} />
            <div>
              <strong>{t('Platform administrator')}</strong>
              <small>{t('Full administrative access within the application')}</small>
            </div>
          </label>
        </div>
        <p class="identity-edit-helper">{t('Currently selected: {roleLabel}', { roleLabel })}</p>
        <p class="identity-edit-helper">
          {t('Application roles control access within BornToShare only and do not grant NTFS or file system permissions.')}
        </p>
      </div>
    </section>

    {#if canEditPassword}
      <section class="identity-edit-section">
        <div class="identity-edit-section__heading">
          <span class="identity-edit-section__index">3</span>
          <div>
            <h3>{t('Security')}</h3>
          </div>
        </div>

        <div class="identity-edit-field">
          <label for="identity-current-password">{t('Current password')}</label>
          <input
            id="identity-current-password"
            class="identity-edit-input"
            type="password"
            bind:value={currentPassword}
            autocomplete="current-password"
            disabled={loading}
          />
          {#if currentPasswordError}
            <FieldError>{currentPasswordError}</FieldError>
          {/if}
        </div>

        <div class="identity-edit-password-grid">
          <div class="identity-edit-field">
            <label for="identity-new-password">{t('New password optional')}</label>
            <input
              id="identity-new-password"
              class="identity-edit-input"
              type="password"
              bind:value={newPassword}
              autocomplete="new-password"
              disabled={loading}
            />
            {#if newPasswordError}
              <FieldError>{newPasswordError}</FieldError>
            {/if}
          </div>

          <div class="identity-edit-field">
            <label for="identity-confirm-password">{t('Confirm password')}</label>
            <input
              id="identity-confirm-password"
              class="identity-edit-input"
              type="password"
              bind:value={confirmPassword}
              autocomplete="new-password"
              disabled={loading}
            />
            {#if confirmPasswordError}
              <FieldError>{confirmPasswordError}</FieldError>
            {/if}
          </div>
        </div>

        <p class="identity-edit-helper">{t('Leave password fields empty to keep the current password.')}</p>
      </section>
    {/if}

    {#if error}
      <InlineAlert tone="error">{error}</InlineAlert>
    {/if}
  </div>

  <svelte:fragment slot="footer">
    <div class="identity-edit-actions">
      {#if isDirty}
        <span class="identity-edit-unsaved">{t('Unsaved changes')}</span>
      {/if}
      <button type="button" class="b2s-btn b2s-btn-secondary" on:click={close} disabled={loading}>{t('Cancel')}</button>
      <button type="button" class="b2s-btn b2s-btn-primary" on:click={submit} disabled={loading}>
        {loading ? t('Saving changes…') : t('Save changes')}
      </button>
    </div>
  </svelte:fragment>
</Drawer>

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

  .identity-edit-shell {
    display: grid;
    gap: 16px;
  }

  .identity-edit-head__avatar {
    width: 48px;
    height: 48px;
    border-radius: var(--b2s-radius-pill);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: #2f6df6;
    color: #fff;
    font-size: var(--b2s-fs-lg);
    font-weight: 700;
  }

  .identity-edit-head__avatar.is-group {
    background: #7c4dff;
  }

  .identity-edit-section {
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-md);
    background: #fff;
    padding: 18px;
    display: grid;
    gap: 16px;
  }

  .identity-edit-section__heading {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .identity-edit-section__heading h3 {
    margin: 0;
    font-size: var(--b2s-fs-lg);
    font-weight: 700;
    color: var(--b2s-color-text);
  }

  .identity-edit-section__index {
    width: 28px;
    height: 28px;
    border-radius: var(--b2s-radius-md);
    border: 1px solid #d8e3f4;
    background: #f4f8ff;
    color: #2f6df6;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: var(--b2s-fs-md);
    font-weight: 700;
  }

  .identity-edit-field {
    display: grid;
    gap: 8px;
  }

  .identity-edit-field label,
  .identity-edit-field .identity-edit-label,
  .identity-edit-field > span {
    color: var(--b2s-color-text);
    font-size: var(--b2s-fs-md);
    font-weight: 600;
  }

  .identity-edit-input {
    width: 100%;
    min-height: 44px;
    border: 1px solid #d7dfec;
    border-radius: var(--b2s-radius-md);
    padding: 0 14px;
    background: #fff;
    color: var(--b2s-color-heading);
    font-size: var(--b2s-fs-md);
  }

  .identity-edit-input:focus {
    outline: none;
    border-color: #2f6df6;
    box-shadow: 0 0 0 3px rgba(47, 109, 246, 0.12);
  }

  .identity-edit-input.invalid {
    border-color: var(--b2s-color-danger, var(--b2s-color-danger));
  }

  .identity-edit-toggle {
    display: inline-flex;
    align-items: center;
    width: fit-content;
    cursor: pointer;
  }

  .identity-edit-toggle input {
    position: absolute;
    opacity: 0;
    pointer-events: none;
  }

  .identity-edit-toggle__track {
    width: 42px;
    height: 24px;
    border-radius: var(--b2s-radius-pill);
    background: #cfd8e6;
    position: relative;
    transition: background 0.2s ease;
  }

  .identity-edit-toggle__thumb {
    position: absolute;
    top: 3px;
    left: 3px;
    width: 18px;
    height: 18px;
    border-radius: var(--b2s-radius-pill);
    background: #fff;
    box-shadow: 0 2px 6px rgba(15, 23, 42, 0.18);
    transition: transform 0.2s ease;
  }

  .identity-edit-toggle input:checked + .identity-edit-toggle__track {
    background: #2f6df6;
  }

  .identity-edit-toggle input:checked + .identity-edit-toggle__track .identity-edit-toggle__thumb {
    transform: translateX(18px);
  }

  .identity-edit-toggle.is-disabled {
    cursor: not-allowed;
    opacity: 0.55;
  }

  .identity-edit-role-grid {
    display: grid;
    gap: 12px;
  }

  .identity-edit-role-card {
    border: 1px solid #dbe3f0;
    border-radius: var(--b2s-radius-md);
    background: #fff;
    padding: 14px 16px;
    display: grid;
    grid-template-columns: 20px 1fr;
    align-items: flex-start;
    gap: 12px;
    cursor: pointer;
  }

  .identity-edit-role-card input {
    margin-top: 3px;
  }

  .identity-edit-role-card strong {
    display: block;
    margin: 0 0 4px;
    color: var(--b2s-color-text);
    font-size: var(--b2s-fs-lg);
  }

  .identity-edit-role-card small {
    color: #5d6f8a;
    font-size: var(--b2s-fs-sm);
  }

  .identity-edit-role-card.is-selected {
    border-color: #2f6df6;
    box-shadow: inset 0 0 0 1px #2f6df6;
  }

  .identity-edit-password-grid {
    display: grid;
    gap: 12px;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .identity-edit-helper {
    margin: 0;
    color: #5d6f8a;
    font-size: var(--b2s-fs-sm);
    line-height: 1.5;
  }

  .identity-edit-actions {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 12px;
    flex-wrap: wrap;
  }

  .identity-edit-unsaved {
    margin-right: auto;
    font-size: var(--b2s-fs-xs);
    font-weight: 700;
    color: var(--b2s-color-warning-strong, var(--b2s-color-warning-strong));
  }

  @media (max-width: 640px) {
    .identity-edit-password-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
