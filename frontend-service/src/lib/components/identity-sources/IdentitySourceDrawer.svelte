<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import Drawer from '$lib/components/ui/Drawer.svelte';
  import Tabs from '$lib/components/ui/Tabs.svelte';
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import type { IdentitySourceCardVM } from '$lib/services/mappers/identity-sources.mapper';

  export let open = false;
  export let source: IdentitySourceCardVM | null = null;
  type IdentitySourceInternalMeta = {
    id?: number;
    bind_dn?: string | null;
    bind_password_ref?: string | null;
    client_secret_ref?: string | null;
    last_probe_message?: string | null;
    last_snapshot_at?: string | null;
    last_snapshot_status?: string | null;
    last_snapshot_version?: number | null;
    last_snapshot_objects_count?: number | null;
    last_snapshot_users_count?: number | null;
    last_snapshot_groups_count?: number | null;
    last_snapshot_memberships_count?: number | null;
  };

  export let internal: IdentitySourceInternalMeta | null = null;
  export let loading = false;
  export let loadError: string | null = null;
  export let snapshotDebugRows: Array<{
    key: string;
    type: string;
    snapshotVersion: number | null;
    firstName: string | null;
    lastName: string | null;
    displayName: string | null;
    username: string | null;
    email: string | null;
    upn: string | null;
    dn: string | null;
    enabled: string | null;
  }> = [];
  export let snapshotDebugLoading = false;
  export let snapshotDebugError: string | null = null;
  export let snapshotDebugVersion: number | null = null;
  export let busy = false;
  export let probeRunning = false;
  export let snapshotRunning = false;

  const allTabs = [
    { key: 'overview', label: 'Overview' },
    { key: 'health', label: 'Health' },
    { key: 'snapshot', label: 'Snapshot' },
    { key: 'advanced', label: 'Advanced' }
  ];
  let tabs = allTabs;

  let activeTab = 'overview';
  let activeSourceId = 0;

  $: if (open && source && Number(source.id) !== activeSourceId) {
    activeSourceId = Number(source.id);
    activeTab = 'overview';
  }

  $: tabs = source?.supportsSnapshot
    ? allTabs
    : allTabs.filter((tab) => tab.key !== 'snapshot');

  $: if (activeTab === 'snapshot' && source && !source.supportsSnapshot) {
    activeTab = 'overview';
  }

  const dispatch = createEventDispatcher<{
    close: void;
    refresh: void;
    edit: void;
    runProbe: void;
    runSnapshot: void;
    toggle: void;
  }>();

  const valueOrDash = (value: unknown, fallback = '—') => {
    const str = String(value ?? '').trim();
    return str || fallback;
  };

  const boolLabel = (value: unknown, yes = 'Yes', no = 'No') => (value ? yes : no);
</script>

<Drawer
  open={open}
  title={source?.name ?? 'Identity source'}
  subtitle={source?.typeLabel ?? null}
  width="640px"
  onClose={() => dispatch('close')}
>
  {#if source}
    <div class="identity-drawer-v2-head">
      <StatusBadge status={source.healthLabel} label={source.healthLabel} variant={source.healthTone} compact={true} />
      <StatusBadge status={source.snapshotLabel} label={source.snapshotLabel} variant={source.snapshotTone} compact={true} showDot={false} />
      <button type="button" class="identity-inline-btn" on:click={() => dispatch('refresh')} disabled={loading}>
        <i class="bi bi-arrow-clockwise" aria-hidden="true"></i>
        Refresh
      </button>
    </div>

    <Tabs tabs={tabs} activeKey={activeTab} onChange={(key) => (activeTab = key)} />

    {#if loading}
      <div class="identity-drawer-loading">Loading metadata…</div>
    {:else if loadError}
      <div class="identity-drawer-error" role="alert">{loadError}</div>
    {/if}

    {#if activeTab === 'overview'}
      <div class="identity-drawer-grid">
        <div>
          <h4>Type</h4>
          <p>{source.typeLabel}</p>
        </div>
        <div>
          <h4>Status</h4>
          <p>{source.healthLabel}</p>
        </div>
        <div>
          <h4>Endpoint / Issuer</h4>
          <p>{source.endpointLabel}</p>
        </div>
        <div>
          <h4>Protocol</h4>
          <p>{valueOrDash(source.raw?.protocol)}</p>
        </div>
        <div>
          <h4>Bind DN</h4>
          <p>{source.bindDn}</p>
        </div>
        <div>
          <h4>Issuer</h4>
          <p>{source.issuer}</p>
        </div>
        <div class="full">
          <h4>Configuration summary</h4>
          <p>{source.subtitle}</p>
        </div>
      </div>
    {/if}

    {#if activeTab === 'health'}
      <div class="identity-drawer-grid">
        {#if source.supportsProbe}
          <div>
            <h4>Last probe</h4>
            <p>{source.lastProbeLabel}</p>
          </div>
        {/if}
        <div>
          <h4>Probe status</h4>
          <p>{source.supportsProbe ? (probeRunning ? 'Running' : source.healthLabel) : 'Not applicable'}</p>
        </div>
        <div>
          <h4>TLS / Transport</h4>
          <p>{String(source.raw?.protocol ?? '').toLowerCase() === 'ldaps' ? 'TLS enabled (LDAPS)' : 'Plain LDAP / n/a'}</p>
        </div>
        <div>
          <h4>Authentication mode</h4>
          <p>{valueOrDash(source.raw?.capabilities?.auth_mode, 'Unknown')}</p>
        </div>
        <div class="full">
          <h4>Error / message</h4>
          <p>{valueOrDash(internal?.last_probe_message ?? source.raw?.last_probe_message, 'Unknown')}</p>
        </div>
      </div>
    {/if}

    {#if activeTab === 'snapshot'}
      <div class="identity-drawer-grid">
        <div>
          <h4>Snapshot status</h4>
          <p>{source.snapshotLabel}</p>
        </div>
        <div>
          <h4>Last run</h4>
          <p>{source.lastSnapshotLabel}</p>
        </div>
        <div>
          <h4>Users</h4>
          <p>{source.usersCount ?? '—'}</p>
        </div>
        <div>
          <h4>Groups</h4>
          <p>{source.groupsCount ?? '—'}</p>
        </div>
        <div>
          <h4>Memberships</h4>
          <p>{source.membershipsCount ?? internal?.last_snapshot_memberships_count ?? source.raw?.last_snapshot_memberships_count ?? '—'}</p>
        </div>
        <div>
          <h4>Version</h4>
          <p>{internal?.last_snapshot_version ?? source.raw?.last_snapshot_version ?? '—'}</p>
        </div>
        <div>
          <h4>Objects</h4>
          <p>{internal?.last_snapshot_objects_count ?? source.raw?.last_snapshot_objects_count ?? '—'}</p>
        </div>
        <div class="full">
          {#if source.supportsSnapshot}
            <button
              type="button"
              class="identity-inline-btn primary"
              disabled={busy || snapshotRunning}
              on:click={() => dispatch('runSnapshot')}
            >
              {snapshotRunning ? 'Snapshot running…' : 'Run Snapshot'}
            </button>
          {/if}
        </div>

        <div class="full snapshot-debug-wrap">
          <h4>Snapshot debug rows</h4>
          <p class="snapshot-debug-subtitle">
            Last snapshot version: {snapshotDebugVersion ?? internal?.last_snapshot_version ?? source.raw?.last_snapshot_version ?? '—'}
          </p>

          {#if snapshotDebugLoading}
            <div class="identity-drawer-loading">Loading snapshot rows…</div>
          {:else if snapshotDebugError}
            <div class="identity-drawer-error" role="alert">{snapshotDebugError}</div>
          {:else if snapshotDebugRows.length === 0}
            <div class="snapshot-debug-empty">No snapshot row available for debug.</div>
          {:else}
            <div class="snapshot-debug-table-wrap">
              <table class="snapshot-debug-table">
                <thead>
                  <tr>
                    <th>Version</th>
                    <th>Type</th>
                    <th>First name</th>
                    <th>Nom</th>
                    <th>Display</th>
                    <th>Username</th>
                    <th>Email</th>
                    <th>UPN</th>
                    <th>Enabled</th>
                    <th>DN</th>
                  </tr>
                </thead>
                <tbody>
                  {#each snapshotDebugRows as row (row.key)}
                    <tr>
                      <td>{row.snapshotVersion ?? '—'}</td>
                      <td>{row.type || '—'}</td>
                      <td>{row.firstName ?? '—'}</td>
                      <td>{row.lastName ?? '—'}</td>
                      <td>{row.displayName ?? '—'}</td>
                      <td>{row.username ?? '—'}</td>
                      <td>{row.email ?? '—'}</td>
                      <td>{row.upn ?? '—'}</td>
                      <td>{row.enabled ?? '—'}</td>
                      <td class="snapshot-debug-dn">{row.dn ?? '—'}</td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {/if}
        </div>
      </div>
    {/if}

    {#if activeTab === 'advanced'}
      <div class="identity-drawer-grid">
        <div>
          <h4>Enabled</h4>
          <p>{boolLabel(source.isEnabled, 'Enabled', 'Disabled')}</p>
        </div>
        <div>
          <h4>Used by endpoints</h4>
          <p>{boolLabel(source.raw?.used, 'Yes', 'No')}</p>
        </div>
        <div>
          <h4>Auth capability</h4>
          <p>{boolLabel(source.raw?.capabilities?.auth, 'Enabled', 'Disabled')}</p>
        </div>
        <div>
          <h4>Import groups</h4>
          <p>{boolLabel(source.raw?.capabilities?.import_groups, 'Enabled', 'Disabled')}</p>
        </div>
        <div class="full">
          <h4>Security transport details</h4>
          <p>{String(source.raw?.protocol ?? '').toLowerCase() === 'ldaps' ? 'Encrypted LDAP transport (LDAPS).' : 'No explicit TLS transport metadata.'}</p>
        </div>
      </div>
    {/if}
  {/if}

  <svelte:fragment slot="footer">
    {#if source}
      <button type="button" class="identity-inline-btn" disabled={busy} on:click={() => dispatch('edit')}>
        <i class="bi bi-pencil-square" aria-hidden="true"></i>
        Edit
      </button>
      {#if source.supportsProbe}
        <button
          type="button"
          class="identity-inline-btn"
          disabled={busy || probeRunning}
          on:click={() => dispatch('runProbe')}
        >
          <i class="bi bi-activity" aria-hidden="true"></i>
          {probeRunning ? 'Probe running…' : 'Run Probe'}
        </button>
      {/if}
      <button
        type="button"
        class="identity-inline-btn"
        disabled={busy}
        on:click={() => dispatch('toggle')}
      >
        <i class={`bi ${source.isEnabled ? 'bi-toggle-on' : 'bi-toggle-off'}`} aria-hidden="true"></i>
        {source.isEnabled ? 'Disable' : 'Enable'}
      </button>
    {/if}
  </svelte:fragment>
</Drawer>

<style>
  .identity-drawer-v2-head {
    display: flex;
    align-items: center;
    gap: 0.45rem;
    flex-wrap: wrap;
    margin-bottom: 0.62rem;
  }

  .identity-drawer-grid {
    margin-top: 0.72rem;
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.72rem;
  }

  .identity-drawer-grid .full {
    grid-column: 1 / -1;
  }

  .identity-drawer-grid h4 {
    margin: 0;
    font-size: 0.74rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #475569;
    font-weight: 800;
  }

  .identity-drawer-grid p {
    margin: 0.2rem 0 0;
    font-size: 0.86rem;
    color: #0f172a;
  }

  .identity-inline-btn {
    border: 1px solid rgba(148, 163, 184, 0.4);
    background: #fff;
    color: #334155;
    border-radius: 10px;
    height: 34px;
    padding: 0 0.72rem;
    display: inline-flex;
    align-items: center;
    gap: 0.42rem;
    font-size: 0.78rem;
    font-weight: 700;
  }

  .identity-inline-btn.primary {
    border-color: #0b1530;
    background: #0b1530;
    color: #fff;
  }

  .identity-inline-btn:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }

  .identity-drawer-loading {
    margin-top: 0.68rem;
    color: #64748b;
    font-size: 0.84rem;
    font-weight: 600;
  }

  .identity-drawer-error {
    margin-top: 0.68rem;
    padding: 0.56rem 0.64rem;
    border-radius: 10px;
    border: 1px solid rgba(185, 28, 28, 0.24);
    background: rgba(254, 242, 242, 0.8);
    color: #991b1b;
    font-size: 0.8rem;
    font-weight: 600;
  }

  .snapshot-debug-wrap {
    margin-top: 0.2rem;
    border-top: 1px dashed rgba(148, 163, 184, 0.45);
    padding-top: 0.6rem;
  }

  .snapshot-debug-subtitle {
    margin: 0.2rem 0 0.45rem;
    color: #475569;
    font-size: 0.78rem;
    font-weight: 600;
  }

  .snapshot-debug-empty {
    color: #64748b;
    font-size: 0.8rem;
    font-weight: 600;
  }

  .snapshot-debug-table-wrap {
    max-height: 280px;
    overflow: auto;
    border: 1px solid rgba(148, 163, 184, 0.32);
    border-radius: 10px;
    background: #fff;
  }

  .snapshot-debug-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.75rem;
    color: #0f172a;
  }

  .snapshot-debug-table th,
  .snapshot-debug-table td {
    padding: 0.34rem 0.42rem;
    border-bottom: 1px solid rgba(226, 232, 240, 0.8);
    vertical-align: top;
    text-align: left;
    white-space: nowrap;
  }

  .snapshot-debug-table th {
    position: sticky;
    top: 0;
    z-index: 1;
    background: #f8fafc;
    color: #334155;
    font-weight: 800;
  }

  .snapshot-debug-table tbody tr:last-child td {
    border-bottom: 0;
  }

  .snapshot-debug-dn {
    white-space: normal;
    min-width: 260px;
    word-break: break-word;
  }

  @media (max-width: 940px) {
    .identity-drawer-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
