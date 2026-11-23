<script lang="ts">
  import ContextMenu, { menuPositionFor, type ContextMenuItem } from '$lib/components/ui/ContextMenu.svelte';
  import { copyText } from '$lib/utils/clipboard';
  import RelativeTime from '$lib/components/ui/RelativeTime.svelte';
  import SearchField from '$lib/components/ui/SearchField.svelte';
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import { t } from '$lib/i18n';
  import { normalizeText } from '$lib/utils/values';
  import ConfigCard from '$lib/components/settings/ConfigCard.svelte';
  import ConfirmActionModal from '$lib/components/ui/ConfirmActionModal.svelte';
  import { toast } from '$lib/stores/toast';
  import { notifyError, reportUiError, toAppError } from '$lib/errors';
  import { logAppError } from '$lib/logging';
  import { timeAgo } from '$lib/utils/format';
  import type { UserSession } from '$lib/api/admin-advanced-settings';
  import { listUserSessions, revokeUserSession, saveAdvancedSections, saveSessionLimits } from '$lib/api/admin-advanced-settings';
  import { guardUnsaved } from '$lib/utils/unsaved';
  import SettingRow from '$lib/components/settings/SettingRow.svelte';
  import FieldError from '$lib/components/ui/FieldError.svelte';


  interface Props {
    data: any;
  }

  let { data }: Props = $props();

  // svelte-ignore state_referenced_locally (an initial value, read once as before)
  let ttlHours = $state(Math.round(Number(data.settings?.sessions?.ttlSeconds ?? 28800) / 3600));
  // svelte-ignore state_referenced_locally (an initial value, read once as before)
  let idleMinutes = $state(Math.round(Number(data.settings?.sessions?.idleSeconds ?? 1800) / 60));
  // svelte-ignore state_referenced_locally (an initial value, read once as before)
  let savedLimits = $state(`${ttlHours}/${idleMinutes}`);
  let savingLimits = $state(false);

  let limitsError =
    $derived(Number.isInteger(Number(ttlHours)) && ttlHours >= 1 && ttlHours <= 720 && Number.isInteger(Number(idleMinutes)) && idleMinutes >= 1 && idleMinutes <= ttlHours * 60
      ? null
      : t('From 1 to 720 hours; inactivity from 1 minute to the maximum duration.'));
  // Failed sign-ins before a pause (applied by auth-service within a minute)
  // svelte-ignore state_referenced_locally (an initial value, read once as before)
  let perAccount = $state(Number(data.advanced?.signIn?.maxFailuresPerAccount ?? 5));
  // svelte-ignore state_referenced_locally (an initial value, read once as before)
  let perAddress = $state(Number(data.advanced?.signIn?.maxFailuresPerAddress ?? 50));
  // svelte-ignore state_referenced_locally (an initial value, read once as before)
  let windowMinutes = $state(Number(data.advanced?.signIn?.windowMinutes ?? 15));
  const signInSnap = () => JSON.stringify([Number(perAccount), Number(perAddress), Number(windowMinutes)]);
  // svelte-ignore state_referenced_locally (an initial value, read once as before)
  let savedSignIn = $state(signInSnap());

  // One « Save »: the session limits and the sign-in limits, each written only when it changed
  let limitsDirty = $derived(`${ttlHours}/${idleMinutes}` !== savedLimits);
  let signInDirty = $derived(signInSnap() !== savedSignIn);
  let canSaveLimits = $derived(!savingLimits && !limitsError && (limitsDirty || signInDirty));
  guardUnsaved(() => limitsDirty || signInDirty);

  async function saveLimits() {
    if (!canSaveLimits) return;
    savingLimits = true;
    try {
      if (limitsDirty) {
        await saveSessionLimits(fetch, Number(ttlHours) * 3600, Number(idleMinutes) * 60);
        savedLimits = `${ttlHours}/${idleMinutes}`;
      }
      if (signInDirty) {
        await saveAdvancedSections(fetch, { signIn: { maxFailuresPerAccount: Number(perAccount), maxFailuresPerAddress: Number(perAddress), windowMinutes: Number(windowMinutes) } });
        savedSignIn = signInSnap();
      }
      toast.success(t('Settings saved.'));
    } catch (e: unknown) {
      reportUiError(e, t('Unable to save the settings.'), 'advanced_settings.sessions.save');
    } finally {
      savingLimits = false;
    }
  }

  // svelte-ignore state_referenced_locally (an initial value, read once as before)
  let sessions = $state<UserSession[]>(data.sessions ?? []);
  let isLoading = $state(false);
  let revokingId = $state<string | null>(null);
  let query = $state('');
  let statusFilter = $state<'all' | 'active' | 'expired' | 'revoked'>('all');
  let sortBy = $state<'user' | 'last_seen' | 'created_at' | 'status'>('last_seen');
  let sortDir = $state<'asc' | 'desc'>('desc');
  let confirmDisconnectOpen = $state(false);
  let pendingSessionId = $state<string | null>(null);

  const toTimestamp = (value: unknown) => {
    const time = new Date(String(value ?? '')).getTime();
    return Number.isFinite(time) ? time : 0;
  };

  let filteredSessions = $derived(sessions.filter((s) => {
    if (statusFilter !== 'all' && s.status !== statusFilter) return false;
    const q = normalizeText(query);
    if (!q) return true;
    const haystack = [s.user, s.auth_source, s.status, (s.roles ?? []).join(' ')].map(normalizeText).join(' ');
    return haystack.includes(q);
  }));

  let sortedSessions = $derived([...filteredSessions].sort((a, b) => {
    const dir = sortDir === 'asc' ? 1 : -1;
    if (sortBy === 'user') return a.user.localeCompare(b.user, 'en', { sensitivity: 'base' }) * dir;
    if (sortBy === 'status') return String(a.status).localeCompare(String(b.status)) * dir;
    if (sortBy === 'created_at') return (toTimestamp(a.created_at) - toTimestamp(b.created_at)) * dir;
    return (toTimestamp(a.last_seen) - toTimestamp(b.last_seen)) * dir;
  }));

  async function refresh() {
    isLoading = true;
    try {
      const res = await listUserSessions(fetch);
      sessions = res.sessions ?? [];
    } catch (e: unknown) {
      reportUiError(e, 'Unable to refresh sessions.', 'advanced_settings.user_sessions.refresh');
    } finally {
      isLoading = false;
    }
  }

  function requestRevoke(sessionId: string) {
    if (revokingId) return;
    pendingSessionId = sessionId;
    confirmDisconnectOpen = true;
  }

  // ---- right click on a session ----
  let menu = $state<{ session: any; at: { x: number; y: number } } | null>(null);
  const sessionItems = (session: any): ContextMenuItem[] => [
    { key: 'disconnect', label: t('Disconnect'), icon: 'bi-box-arrow-right', danger: true, disabled: session.is_current || isLoading || !!revokingId,
      hint: session.is_current ? t('This session') : undefined },
    { key: 'person', label: t('See this person'), icon: 'bi-person', separated: true },
    { key: 'copy', label: t('Copy the login'), icon: 'bi-clipboard' }
  ];
  async function pickSession(key: string) {
    const session = menu?.session;
    menu = null;
    if (!session) return;
    if (key === 'disconnect') requestRevoke(session.id);
    else if (key === 'person') window.location.assign(`/admin/identity?q=${encodeURIComponent(String(session.user ?? ''))}`);
    else if (await copyText(String(session.user ?? ''))) toast.success(t('Login copied.'));
  }

  async function revokeConfirmed() {
    if (revokingId || !pendingSessionId) return;
    const sessionId = pendingSessionId;
    confirmDisconnectOpen = false;
    pendingSessionId = null;

    revokingId = sessionId;
    try {
      const res = await revokeUserSession(fetch, sessionId);
      if (res?.ok) {
        toast.success(t('Session disconnected.'));
        await refresh();
      } else {
        const appError = toAppError(new Error(String(res?.message ?? t('Unable to disconnect session.'))), {
          source: 'ui',
          details: res
        });
        logAppError(appError, { action: 'advanced_settings.user_sessions.revoke', sessionId });
        notifyError(appError);
      }
    } catch (e: unknown) {
      reportUiError(e, 'Unable to disconnect session.', 'advanced_settings.user_sessions.revoke');
    } finally {
      revokingId = null;
    }
  }
</script>

<ConfigCard title={t('Sessions and sign-ins')} subtitle={t('Apply within a minute, also to the sessions already open.')} icon="bi-shield-lock">
  <section class="us-group">
    <h3>{t('Session limits')}</h3>
    <div class="adv-form-grid">
      <SettingRow label={t('Maximum duration (hours)')}>
        <input class="b2s-input" type="number" min="1" max="720" step="1" bind:value={ttlHours} />
      </SettingRow>
      <SettingRow label={t('Disconnect after inactivity (minutes)')}>
        <input class="b2s-input" type="number" min="1" step="1" bind:value={idleMinutes} />
        {#if limitsError}<FieldError>{limitsError}</FieldError>{/if}
      </SettingRow>
    </div>
  </section>
  <section class="us-group">
    <h3>{t('Failed sign-ins')}</h3>
    <p class="us-hint">{t('Beyond these failures, the next attempts wait until the window has passed.')}</p>
    <div class="adv-form-grid">
      <SettingRow label={t('Failures per account')}><input class="b2s-input" type="number" min="3" max="50" bind:value={perAccount} /></SettingRow>
      <SettingRow label={t('Failures per address')}><input class="b2s-input" type="number" min="10" max="1000" bind:value={perAddress} /></SettingRow>
      <SettingRow label={t('Window (minutes)')}><input class="b2s-input" type="number" min="1" max="1440" bind:value={windowMinutes} /></SettingRow>
    </div>
  </section>
  <div class="adv-actions">
    <button class="b2s-btn b2s-btn-primary" type="button" onclick={saveLimits} disabled={!canSaveLimits}>
      <i class="bi bi-check2" aria-hidden="true"></i>{savingLimits ? t('Saving…') : t('Save changes')}
    </button>
  </div>
</ConfigCard>

<ConfigCard title={t('User sessions')} subtitle={t('Active sessions')} icon="bi-person-lines-fill">
  <div class="b2s-toolbar is-plain">
      <SearchField wrapperClass="b2s-toolbar__search" placeholder={t('Search user, role, source…')} ariaLabel={t('Search sessions')} bind:value={query} />
      <select class="b2s-select" bind:value={statusFilter} aria-label={t('Status')}>
        <option value="all">{t('All statuses')}</option>
        <option value="active">{t('Active')}</option>
        <option value="expired">{t('Expired')}</option>
        <option value="revoked">{t('Revoked')}</option>
      </select>
      <select class="b2s-select" bind:value={sortBy} aria-label={t('Sort')}>
        <option value="last_seen">{t('Sort: Last activity')}</option>
        <option value="created_at">{t('Sort: Created')}</option>
        <option value="user">{t('Sort: User')}</option>
        <option value="status">{t('Sort: Status')}</option>
      </select>
      <button class="b2s-btn b2s-btn-secondary" type="button" onclick={() => (sortDir = sortDir === 'asc' ? 'desc' : 'asc')}>
        {sortDir === 'asc' ? `↑ ${t('Ascending')}` : `↓ ${t('Descending')}`}
      </button>
    <button class="b2s-btn b2s-btn-secondary b2s-toolbar__end" type="button" onclick={refresh} disabled={isLoading || !!revokingId}>
      {isLoading ? t('Loading…') : t('Refresh')}
    </button>
  </div>

  <div class="adv-hint">{t('{sortedSessionsCount} session{value} shown', { sortedSessionsCount: sortedSessions.length, value: (sortedSessions.length > 1 ? 's' : '') })}</div>

  <div class="b2s-table-wrap">
    <table class="table table-hover align-middle">
      <thead>
        <tr>
          <th>{t('User')}</th>
          <th>{t('Role')}</th>
          <th>{t('Status')}</th>
          <th>{t('Last seen')}</th>
          <th>{t('Auth')}</th>
          <th>{t('Created')}</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {#each sortedSessions as s}
          <tr oncontextmenu={(event) => { event.preventDefault(); menu = { session: s, at: menuPositionFor(event) }; }}>
            <td>
              <strong>{s.user}</strong>
              {#if s.is_current}<span class="adv-current-session">{t('This session')}</span>{/if}
            </td>
            <td>
              <StatusBadge compact showDot={false} variant="info" label={s.roles?.length ? s.roles.join(', ') : t('user')} />
            </td>
            <td>
              {#if s.status === 'active'}
                <StatusBadge compact variant="success" label={t('Active')} />
              {:else}
                <StatusBadge compact status={s.status} />
              {/if}
            </td>
            <td><RelativeTime value={s.last_seen} /></td>
            <td>{s.auth_source ?? '-'}</td>
            <td><RelativeTime value={s.created_at} /></td>
            <td class="text-end">
              {#if !s.is_current}
              <button
                class="b2s-btn b2s-btn-danger-outline b2s-btn-sm"
                type="button"
                onclick={() => requestRevoke(s.id)}
                disabled={isLoading || !!revokingId}
              >
                {revokingId === s.id ? t('Disconnecting…') : t('Disconnect')}
              </button>
              {/if}
            </td>
          </tr>
        {:else}
          <tr>
            <td colspan="7" class="text-center text-muted">{t('No active sessions.')}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</ConfigCard>

<ConfirmActionModal
  open={confirmDisconnectOpen}
  onClose={() => {
    confirmDisconnectOpen = false;
    pendingSessionId = null;
  }}
  onConfirm={revokeConfirmed}
  title={t('Disconnect session')}
  subtitle={t('This will immediately revoke this active session.')}
  impactTitle={t('Impact')}
  impactItems={[
    t('The user will be signed out from this session.'),
    t('A new login will be required to continue.')
  ]}
  cancelLabel={t('Cancel')}
  confirmLabel={t('Disconnect')}
  confirmBusyLabel={t('Disconnecting…')}
  busy={Boolean(revokingId)}
  severity="warning"
/>

<ContextMenu open={Boolean(menu)} title={menu?.session.user ?? ''} items={menu ? sessionItems(menu.session) : []} at={menu?.at ?? { x: 0, y: 0 }}
  onClose={() => (menu = null)} onPick={(key) => void pickSession(key)} />

<style>
  .us-group { display: grid; gap: 8px; padding: 4px 0 14px; border-bottom: 1px solid var(--b2s-color-border-soft); }
  .us-group + .us-group { padding-top: 14px; }
  .us-group h3 { margin: 0; color: var(--b2s-color-heading); font-size: var(--b2s-fs-md); font-weight: 600; }
  .us-hint { margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .adv-current-session {
    margin-left: 8px;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
  }
</style>
