<script lang="ts">
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
  import { listUserSessions, revokeUserSession } from '$lib/api/admin-advanced-settings';

  export let data: any;
  let sessions: UserSession[] = data.sessions ?? [];
  let isLoading = false;
  let revokingId: string | null = null;
  let query = '';
  let statusFilter: 'all' | 'active' | 'expired' | 'revoked' = 'all';
  let sortBy: 'user' | 'last_seen' | 'created_at' | 'status' = 'last_seen';
  let sortDir: 'asc' | 'desc' = 'desc';
  let confirmDisconnectOpen = false;
  let pendingSessionId: string | null = null;

  const toTimestamp = (value: unknown) => {
    const time = new Date(String(value ?? '')).getTime();
    return Number.isFinite(time) ? time : 0;
  };

  $: filteredSessions = sessions.filter((s) => {
    if (statusFilter !== 'all' && s.status !== statusFilter) return false;
    const q = normalizeText(query);
    if (!q) return true;
    const haystack = [s.user, s.auth_source, s.status, (s.roles ?? []).join(' ')].map(normalizeText).join(' ');
    return haystack.includes(q);
  });

  $: sortedSessions = [...filteredSessions].sort((a, b) => {
    const dir = sortDir === 'asc' ? 1 : -1;
    if (sortBy === 'user') return a.user.localeCompare(b.user, 'en', { sensitivity: 'base' }) * dir;
    if (sortBy === 'status') return String(a.status).localeCompare(String(b.status)) * dir;
    if (sortBy === 'created_at') return (toTimestamp(a.created_at) - toTimestamp(b.created_at)) * dir;
    return (toTimestamp(a.last_seen) - toTimestamp(b.last_seen)) * dir;
  });

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

<ConfigCard title={t('User sessions')} subtitle={t('Active sessions')} icon="bi-person-lines-fill">
  <div class="adv-toolbar">
    <div class="adv-toolbar-left">
      <div class="adv-search">
        <i class="bi bi-search"></i>
        <input class="form-control" type="search" bind:value={query} placeholder={t('Search user, role, source…')} />
      </div>
      <select class="form-select" bind:value={statusFilter}>
        <option value="all">{t('All statuses')}</option>
        <option value="active">{t('Active')}</option>
        <option value="expired">{t('Expired')}</option>
        <option value="revoked">{t('Revoked')}</option>
      </select>
      <select class="form-select" bind:value={sortBy}>
        <option value="last_seen">{t('Sort: Last activity')}</option>
        <option value="created_at">{t('Sort: Created')}</option>
        <option value="user">{t('Sort: User')}</option>
        <option value="status">{t('Sort: Status')}</option>
      </select>
      <button class="b2s-btn b2s-btn-secondary" type="button" on:click={() => (sortDir = sortDir === 'asc' ? 'desc' : 'asc')}>
        {sortDir === 'asc' ? '↑ Ascending' : '↓ Descending'}
      </button>
    </div>
    <button class="b2s-btn b2s-btn-secondary" type="button" on:click={refresh} disabled={isLoading || !!revokingId}>
      {isLoading ? t('Loading…') : t('Refresh')}
    </button>
  </div>

  <div class="adv-hint">{t('{sortedSessionsCount} session{value} shown', { sortedSessionsCount: sortedSessions.length, value: (sortedSessions.length > 1 ? 's' : '') })}</div>

  <div class="table-responsive">
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
          <tr>
            <td><strong>{s.user}</strong></td>
            <td>
              <StatusBadge compact showDot={false} variant="info" label={s.roles?.length ? s.roles.join(', ') : 'user'} />
            </td>
            <td>
              {#if s.status === 'active'}
                <StatusBadge compact variant="success" label={t('Active')} />
              {:else}
                <StatusBadge compact status={s.status} />
              {/if}
            </td>
            <td>{timeAgo(s.last_seen)}</td>
            <td>{s.auth_source ?? '-'}</td>
            <td>{timeAgo(s.created_at)}</td>
            <td class="text-end">
              <button
                class="b2s-btn b2s-btn-danger-outline b2s-btn-sm"
                type="button"
                on:click={() => requestRevoke(s.id)}
                disabled={isLoading || !!revokingId}
              >
                {revokingId === s.id ? t('Disconnecting…') : t('Disconnect')}
              </button>
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
    'The user will be signed out from this session.',
    'A new login will be required to continue.'
  ]}
  cancelLabel={t('Cancel')}
  confirmLabel={t('Disconnect')}
  confirmBusyLabel={t('Disconnecting…')}
  busy={Boolean(revokingId)}
  severity="warning"
/>
