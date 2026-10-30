<script lang="ts">
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import { t } from '$lib/i18n';
  import { createEventDispatcher } from 'svelte';
  import Drawer from '$lib/components/ui/Drawer.svelte';
  import Tabs from '$lib/components/ui/Tabs.svelte';
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import type { IdentitySourceCardVM } from '$lib/mappers/identity-sources.mapper';

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
  /** Last 7 days of health checks, one point a day */
  export let recentHealth: Array<{ key: string; label: string; tone: string; title: string; icon: string }> = [];
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
    { key: 'overview', label: t('Overview') },
    { key: 'health', label: t('Health') },
    { key: 'snapshot', label: t('Snapshot') },
    { key: 'advanced', label: t('Advanced') }
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
    delete: void;
  }>();

  const valueOrDash = (value: unknown, fallback = '—') => {
    const str = String(value ?? '').trim();
    return str || fallback;
  };

  const boolLabel = (value: unknown, yes = 'Yes', no = 'No') => (value ? yes : no);
</script>

<Drawer
  iconClass="bi bi-person-vcard"
  open={open}
  title={source?.name ?? t('Identity source')}
  subtitle={source?.typeLabel ?? null}
  size="lg"
  onClose={() => dispatch('close')}
>
  {#if source}
    <div class="identity-drawer-v2-head">
      <StatusBadge status={source.healthLabel} label={source.healthLabel} variant={source.healthTone} compact={true} />
      <StatusBadge status={source.snapshotLabel} label={source.snapshotLabel} variant={source.snapshotTone} compact={true} showDot={false} />
      <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" on:click={() => dispatch('refresh')} disabled={loading}>
        <i class="bi bi-arrow-clockwise" aria-hidden="true"></i>
        {t('Refresh')}
      </button>
    </div>

    <Tabs tabs={tabs} activeKey={activeTab} onChange={(key) => (activeTab = key)} />

    {#if loading}
      <LoadingState block>{t('Loading metadata…')}</LoadingState>
    {:else if loadError}
      <InlineAlert tone="error">{loadError}</InlineAlert>
    {/if}

    {#if activeTab === 'overview'}
      <div class="identity-drawer-grid">
        <div>
          <h4>{t('Type')}</h4>
          <p>{source.typeLabel}</p>
        </div>
        <div>
          <h4>{t('Status')}</h4>
          <p>{source.healthLabel}</p>
        </div>
        <div>
          <h4>{t('Endpoint / Issuer')}</h4>
          <p>{source.endpointLabel}</p>
        </div>
        <div>
          <h4>{t('Protocol')}</h4>
          <p>{valueOrDash(source.raw?.protocol)}</p>
        </div>
        <div>
          <h4>{t('Bind DN')}</h4>
          <p>{source.bindDn}</p>
        </div>
        <div>
          <h4>{t('Issuer')}</h4>
          <p>{source.issuer}</p>
        </div>
        <div class="full">
          <h4>{t('Configuration summary')}</h4>
          <p>{source.subtitle}</p>
        </div>
      </div>
    {/if}

    {#if activeTab === 'health'}
      {#if recentHealth.length}
        <div class="isd-health" aria-label={t('Recent health status')}>
          <h4>{t('Recent health')} <small>{t('Last 7 days')}</small></h4>
          <ol>
            {#each recentHealth as point (point.key)}
              <li class={point.tone} title={point.title}>
                <i class={`bi ${point.icon}`} aria-hidden="true"></i>
                <small>{point.label}</small>
              </li>
            {/each}
          </ol>
        </div>
      {/if}
      <div class="identity-drawer-grid">
        {#if source.supportsProbe}
          <div>
            <h4>{t('Last probe')}</h4>
            <p>{source.lastProbeLabel}</p>
          </div>
        {/if}
        <div>
          <h4>{t('Probe status')}</h4>
          <p>{source.supportsProbe ? (probeRunning ? t('Running') : source.healthLabel) : t('Not applicable')}</p>
        </div>
        <div>
          <h4>{t('TLS / Transport')}</h4>
          <p>{String(source.raw?.protocol ?? '').toLowerCase() === 'ldaps' ? t('TLS enabled (LDAPS)') : t('Plain LDAP / n/a')}</p>
        </div>
        <div>
          <h4>{t('Authentication mode')}</h4>
          <p>{valueOrDash(source.raw?.capabilities?.auth_mode, t('Unknown'))}</p>
        </div>
        <div class="full">
          <h4>{t('Error / message')}</h4>
          <p>{valueOrDash(internal?.last_probe_message ?? source.raw?.last_probe_message, t('Unknown'))}</p>
        </div>
      </div>
    {/if}

    {#if activeTab === 'snapshot'}
      <div class="identity-drawer-grid">
        <div>
          <h4>{t('Snapshot status')}</h4>
          <p>{source.snapshotLabel}</p>
        </div>
        <div>
          <h4>{t('Last run')}</h4>
          <p>{source.lastSnapshotLabel}</p>
        </div>
        <div>
          <h4>{t('Users')}</h4>
          <p>{source.usersCount ?? '—'}</p>
        </div>
        <div>
          <h4>{t('Groups')}</h4>
          <p>{source.groupsCount ?? '—'}</p>
        </div>
        <div>
          <h4>{t('Memberships')}</h4>
          <p>{source.membershipsCount ?? internal?.last_snapshot_memberships_count ?? source.raw?.last_snapshot_memberships_count ?? '—'}</p>
        </div>
        <div>
          <h4>{t('Version')}</h4>
          <p>{internal?.last_snapshot_version ?? source.raw?.last_snapshot_version ?? '—'}</p>
        </div>
        <div>
          <h4>{t('Objects')}</h4>
          <p>{internal?.last_snapshot_objects_count ?? source.raw?.last_snapshot_objects_count ?? '—'}</p>
        </div>
        <div class="full">
          {#if source.supportsSnapshot}
            <button
              type="button"
              class="b2s-btn b2s-btn-primary b2s-btn-sm"
              disabled={busy || snapshotRunning}
              on:click={() => dispatch('runSnapshot')}
            >
              {snapshotRunning ? t('Synchronizing…') : t('Sync now')}
            </button>
          {/if}
        </div>

        <div class="full snapshot-debug-wrap">
          <h4>{t('Snapshot debug rows')}</h4>
          <p class="snapshot-debug-subtitle">
            {t('Last snapshot version: {value}', { value: (snapshotDebugVersion ?? internal?.last_snapshot_version ?? source.raw?.last_snapshot_version ?? '—') })}
          </p>

          {#if snapshotDebugLoading}
            <LoadingState block>{t('Loading snapshot rows…')}</LoadingState>
          {:else if snapshotDebugError}
            <InlineAlert tone="error">{snapshotDebugError}</InlineAlert>
          {:else if snapshotDebugRows.length === 0}
            <div class="snapshot-debug-empty">{t('No snapshot row available for debug.')}</div>
          {:else}
            <div class="snapshot-debug-table-wrap">
              <table class="snapshot-debug-table">
                <thead>
                  <tr>
                    <th>{t('Version')}</th>
                    <th>{t('Type')}</th>
                    <th>{t('First name')}</th>
                    <th>{t('Nom')}</th>
                    <th>{t('Display')}</th>
                    <th>{t('Username')}</th>
                    <th>{t('Email')}</th>
                    <th>UPN</th>
                    <th>{t('Enabled')}</th>
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
          <h4>{t('Enabled')}</h4>
          <p>{boolLabel(source.isEnabled, t('Enabled'), t('Disabled'))}</p>
        </div>
        <div>
          <h4>{t('Used by endpoints')}</h4>
          <p>{boolLabel(source.raw?.used, t('Yes'), t('No'))}</p>
        </div>
        <div>
          <h4>{t('Auth capability')}</h4>
          <p>{boolLabel(source.raw?.capabilities?.auth, t('Enabled'), t('Disabled'))}</p>
        </div>
        <div>
          <h4>{t('Import groups')}</h4>
          <p>{boolLabel(source.raw?.capabilities?.import_groups, t('Enabled'), t('Disabled'))}</p>
        </div>
        <div class="full">
          <h4>{t('Security transport details')}</h4>
          <p>{String(source.raw?.protocol ?? '').toLowerCase() === 'ldaps' ? t('Encrypted LDAP transport (LDAPS).') : t('No explicit TLS transport metadata.')}</p>
        </div>
      </div>
    {/if}
  {/if}

  <svelte:fragment slot="footer-start">
    {#if source}
      <button type="button" class="b2s-btn b2s-btn-danger-outline b2s-btn-sm" disabled={busy} on:click={() => dispatch('delete')}>
        <i class="bi bi-trash3" aria-hidden="true"></i>
        {t('Delete')}
      </button>
    {/if}
  </svelte:fragment>
  <svelte:fragment slot="footer">
    {#if source}
      <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" disabled={busy} on:click={() => dispatch('toggle')}>
        <i class={`bi ${source.isEnabled ? 'bi-toggle-on' : 'bi-toggle-off'}`} aria-hidden="true"></i>
        {source.isEnabled ? t('Disable') : t('Enable')}
      </button>
      <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" disabled={busy} on:click={() => dispatch('edit')}>
        <i class="bi bi-pencil-square" aria-hidden="true"></i>
        {t('Edit')}
      </button>
      {#if source.supportsProbe}
        <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" disabled={busy || probeRunning} on:click={() => dispatch('runProbe')}>
          <i class="bi bi-activity" aria-hidden="true"></i>
          {probeRunning ? t('Probe running…') : t('Test connection')}
        </button>
      {/if}
      {#if source.supportsSnapshot}
        <button type="button" class="b2s-btn b2s-btn-primary b2s-btn-sm" disabled={busy || snapshotRunning} on:click={() => dispatch('runSnapshot')}>
          <i class={`bi ${snapshotRunning ? 'bi-hourglass-split' : 'bi-arrow-clockwise'}`} aria-hidden="true"></i>
          {snapshotRunning ? t('Synchronizing…') : t('Sync now')}
        </button>
      {/if}
    {/if}
  </svelte:fragment>
</Drawer>

<style>
  .isd-health {
    margin-top: 0.72rem;
    padding: 12px 14px;
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-md);
  }

  .isd-health h4 {
    margin: 0 0 10px;
    font-size: var(--b2s-fs-sm);
    font-weight: 600;
  }

  .isd-health h4 small {
    margin-left: 6px;
    color: var(--b2s-color-text-muted);
    font-weight: 400;
  }

  .isd-health ol {
    display: grid;
    grid-template-columns: repeat(7, minmax(0, 1fr));
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .isd-health li {
    display: grid;
    justify-items: center;
    gap: 4px;
    color: var(--b2s-color-text-faint);
  }

  .isd-health li i {
    display: inline-grid;
    place-items: center;
    width: 22px;
    height: 22px;
    border-radius: 50%;
    background: var(--b2s-color-neutral-soft);
    font-size: 11px;
  }

  .isd-health li.is-success i { background: var(--b2s-color-success-soft); color: var(--b2s-color-success); }
  .isd-health li.is-warning i { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning); }
  .isd-health li.is-error i { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger); }

  .isd-health small {
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
  }

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
    display: block;
    color: var(--b2s-color-text-muted);
    font-size: 12px;
    font-weight: 400;
  }

  .identity-drawer-grid p {
    margin: 0.2rem 0 0;
    font-size: var(--b2s-fs-md);
    color: var(--b2s-color-text);
  }

  .snapshot-debug-wrap {
    margin-top: 0.2rem;
    border-top: 1px dashed rgba(148, 163, 184, 0.45);
    padding-top: 0.6rem;
  }

  .snapshot-debug-subtitle {
    margin: 0.2rem 0 0.45rem;
    color: var(--b2s-color-text-soft);
    font-size: var(--b2s-fs-xs);
    font-weight: 600;
  }

  .snapshot-debug-empty {
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-sm);
    font-weight: 600;
  }

  .snapshot-debug-table-wrap {
    max-height: 280px;
    overflow: auto;
    border: 1px solid rgba(148, 163, 184, 0.32);
    border-radius: var(--b2s-radius-md);
    background: #fff;
  }

  .snapshot-debug-table {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--b2s-fs-xs);
    color: var(--b2s-color-text);
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
    background: var(--b2s-color-surface-soft);
    color: var(--b2s-color-text-strong);
    font-weight: 700;
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
