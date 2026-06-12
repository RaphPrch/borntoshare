<script lang="ts">
  import ConfigCard from '$lib/components/advanced-settings/v3/ConfigCard.svelte';
  import ConfirmActionModal from '$lib/components/common/ConfirmActionModal.svelte';
  import { toasts } from '$lib/stores/toast';
  import { notifyError, toAppError } from '$lib/core/errors';
  import { logAppError } from '$lib/core/logging';
  import { timeAgo } from '$lib/utils/timeAgo';
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

  const GENERIC_ERROR_MESSAGES = new Set(['Unexpected error', 'Backend error', 'Network error', 'Request timeout']);

  const toUiErrorMessage = (error: unknown, fallback: string, action: string): string => {
    const normalized = toAppError(error, { source: 'ui' });
    const appError = GENERIC_ERROR_MESSAGES.has(normalized.message)
      ? { ...normalized, message: fallback }
      : normalized;
    logAppError(appError, { action });
    notifyError(appError);
    return appError.message;
  };

  const normalizeText = (value: unknown) => String(value ?? '').trim().toLowerCase();
  const toTimestamp = (value: unknown) => {
    const t = new Date(String(value ?? '')).getTime();
    return Number.isFinite(t) ? t : 0;
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
      toUiErrorMessage(e, 'Unable to refresh sessions.', 'advanced_settings.user_sessions.refresh');
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
        toasts.success('Session disconnected.');
        await refresh();
      } else {
        const appError = toAppError(new Error(String(res?.message ?? 'Unable to disconnect session.')), {
          source: 'ui',
          details: res
        });
        logAppError(appError, { action: 'advanced_settings.user_sessions.revoke', sessionId });
        notifyError(appError);
      }
    } catch (e: unknown) {
      toUiErrorMessage(e, 'Unable to disconnect session.', 'advanced_settings.user_sessions.revoke');
    } finally {
      revokingId = null;
    }
  }
</script>

<ConfigCard title="User sessions" subtitle="Active sessions" icon="bi-person-lines-fill">
  <div class="adv-toolbar">
    <div class="adv-toolbar-left">
      <div class="adv-search">
        <i class="bi bi-search"></i>
        <input class="form-control" type="search" bind:value={query} placeholder="Search user, role, source…" />
      </div>
      <select class="form-select" bind:value={statusFilter}>
        <option value="all">All statuses</option>
        <option value="active">Active</option>
        <option value="expired">Expired</option>
        <option value="revoked">Revoked</option>
      </select>
      <select class="form-select" bind:value={sortBy}>
        <option value="last_seen">Sort: Last activity</option>
        <option value="created_at">Sort: Created</option>
        <option value="user">Sort: User</option>
        <option value="status">Sort: Status</option>
      </select>
      <button class="btn btn-outline-secondary" type="button" on:click={() => (sortDir = sortDir === 'asc' ? 'desc' : 'asc')}>
        {sortDir === 'asc' ? '↑ Ascending' : '↓ Descending'}
      </button>
    </div>
    <button class="btn btn-secondary" type="button" on:click={refresh} disabled={isLoading || !!revokingId}>
      {isLoading ? 'Loading…' : 'Refresh'}
    </button>
  </div>

  <div class="adv-hint">{sortedSessions.length} session{sortedSessions.length > 1 ? 's' : ''} shown</div>

  <div class="table-responsive">
    <table class="table table-hover align-middle">
      <thead>
        <tr>
          <th>User</th>
          <th>Role</th>
          <th>Status</th>
          <th>Last seen</th>
          <th>Auth</th>
          <th>Created</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {#each sortedSessions as s}
          <tr>
            <td><strong>{s.user}</strong></td>
            <td>
              <span class="badge text-bg-primary">
                {s.roles?.length ? s.roles.join(', ') : 'user'}
              </span>
            </td>
            <td>
              {#if s.status === 'active'}
                <span class="badge text-bg-success">active</span>
              {:else}
                <span class="badge text-bg-secondary">{s.status}</span>
              {/if}
            </td>
            <td>{timeAgo(s.last_seen)}</td>
            <td>{s.auth_source ?? '-'}</td>
            <td>{timeAgo(s.created_at)}</td>
            <td class="text-end">
              <button
                class="btn btn-outline-danger btn-sm"
                type="button"
                on:click={() => requestRevoke(s.id)}
                disabled={isLoading || !!revokingId}
              >
                {revokingId === s.id ? 'Disconnecting…' : 'Disconnect'}
              </button>
            </td>
          </tr>
        {:else}
          <tr>
            <td colspan="7" class="text-center text-muted">No active sessions.</td>
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
  title="Disconnect session"
  subtitle="This will immediately revoke this active session."
  impactTitle="Impact"
  impactItems={[
    'The user will be signed out from this session.',
    'A new login will be required to continue.'
  ]}
  cancelLabel="Cancel"
  confirmLabel="Disconnect"
  confirmBusyLabel="Disconnecting…"
  busy={Boolean(revokingId)}
  severity="warning"
/>
