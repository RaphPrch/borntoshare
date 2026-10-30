<script lang="ts">
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import Pagination from '$lib/components/ui/Pagination.svelte';
  import { t } from '$lib/i18n';
  import type { StatusVariant } from '$lib/utils/status';
  import { normalizeText } from '$lib/utils/values';
  import { invalidateAll } from '$app/navigation';
  import { page } from '$app/stores';
  import { onMount } from 'svelte';
  import EntityActionButton from '$lib/components/entity/EntityActionButton.svelte';
  import Drawer from '$lib/components/ui/Drawer.svelte';
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import IdentityWizardModal from './components/IdentityWizardModal.svelte';
  import EditIdentityModal from './components/EditIdentityModal.svelte';
  import ConfirmDeleteDialog from '$lib/components/ui/ConfirmDeleteDialog.svelte';
  import EmptyStateInline from '$lib/components/ui/EmptyStateInline.svelte';
  import {
    deleteIdentity,
    getIdentityJob,
    listIdentityGroupMembers,
    type IdentityGroupMember
  } from '$lib/api/identity';
  import { runIdentitySnapshot } from '$lib/api/identity-sources';
  import { notifyError, toAppError } from '$lib/errors';
  import { showApiErrorToast } from '$lib/errors/api-toast';
  import { timeAgo } from '$lib/utils/format';
  import { toast } from '$lib/stores/toast';

  export let data: {
    users?: any[];
    groups?: any[];
    items?: any[];
  };

  type IdentityRow = {
    id: string | number | null;
    type: 'user' | 'group';
    display_name: string;
    username: string;
    email: string | null;
    source: 'local' | 'ad' | string;
    sourceLabel: string;
    identity_source_id: number | null;
    role: string;
    roles: string[];
    is_admin: boolean;
    is_self: boolean;
    status: 'active' | 'inactive';
    members_count: number | null;
    created_at: string | null;
    updated_at: string | null;
    last_snapshot_at: string | null;
    raw: any;
  };

  let showWizard = false;
  let showEditIdentity = false;
  let showMembersDrawer = false;
  let targetIdentity: IdentityRow | null = null;
  let selectedId: string | null = null;
  // The detail opens in a drawer on a row click
  let detailOpen = false;
  let search = '';
  let tab: 'all' | 'local_admins' | 'ad_admins' | 'ad_groups' = 'all';
  let statusSourceFilter = 'all';
  let pageIndex = 1;
  let pageSize = 10;

  let members: IdentityGroupMember[] = [];
  let membersLoading = false;
  let syncRunning = false;
  let deleteBusy = false;
  let deleteTarget: IdentityRow | null = null;

  let meId: string | number | null = null;
  $: meId = $page.data?.me?.id ?? null;

  const displayText = (value: unknown, fallback = 'Unknown') => String(value ?? '').trim() || fallback;
  const asNumberOrNull = (value: unknown): number | null => {
    const n = Number(value);
    return Number.isFinite(n) && n > 0 ? n : null;
  };

  const normalizeSource = (row: any) => {
    const authSource = normalizeText(row?.auth_source ?? row?.source);
    if (authSource === 'local') return 'local';
    if (authSource === 'ad') return 'ad';
    if (row?.identity_source_id != null || row?.source_id != null || row?.dn || row?.external_id) return 'ad';
    return authSource || 'local';
  };

  const roleLabel = (role: string) => {
    const normalized = normalizeText(role);
    if (normalized === 'platform_admin') return t('Platform Administrator');
    if (normalized === 'support_admin') return t('Support Administrator');
    if (normalized === 'admin') return t('Administrator');
    if (normalized === 'user') return t('User');
    return role
      .split('_')
      .filter(Boolean)
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(' ');
  };

  const sourceLabel = (row: any, source: string) => {
    if (source === 'local') return t('Local');
    return displayText(row?.source_name ?? row?.snapshot_source, 'AD');
  };

  const mapItemToIdentity = (row: any): IdentityRow => {
    const type = normalizeText(row?.type ?? 'user') === 'group' ? 'group' : 'user';
    const source = normalizeSource(row);
    const roles = Array.isArray(row?.roles) ? row.roles.map((r: unknown) => String(r)).filter(Boolean) : [];
    const isAdmin = roles.some((r: string) => ['platform_admin', 'support_admin', 'admin'].includes(normalizeText(r)));
    const name = displayText(row?.display_name ?? row?.username ?? row?.name, 'Unknown');
    return {
      id: row?.id ?? row?.identity_id ?? null,
      type,
      display_name: name,
      username: displayText(row?.username ?? name, name),
      email: row?.email ?? null,
      source,
      sourceLabel: sourceLabel(row, source),
      identity_source_id: asNumberOrNull(row?.identity_source_id ?? row?.source_id),
      role: type === 'group' ? 'group' : isAdmin ? 'admin' : 'user',
      roles,
      is_admin: isAdmin,
      is_self: row?.id != null && meId != null && String(row?.id) === String(meId),
      status: row?.is_active === false || normalizeText(row?.status) === 'inactive' ? 'inactive' : 'active',
      members_count: type === 'group' ? Number(row?.members_count ?? 0) : null,
      created_at: row?.created_at ?? null,
      updated_at: row?.updated_at ?? null,
      last_snapshot_at: row?.last_snapshot_at ?? null,
      raw: row
    };
  };

  let identities: IdentityRow[] = [];
  $: identities = (data?.items ?? []).map(mapItemToIdentity);
  $: sourceOptions = Array.from(new Set(identities.map((i) => i.sourceLabel).filter(Boolean))).sort();
  $: stats = {
    total: identities.length,
    adminAccounts: identities.filter((i) => i.type === 'user' && i.is_admin).length,
    adGroups: identities.filter((i) => i.type === 'group').length
  };

  const matchesTab = (identity: IdentityRow) => {
    if (tab === 'local_admins') return identity.type === 'user' && identity.is_admin && identity.source === 'local';
    if (tab === 'ad_admins') return identity.type === 'user' && identity.is_admin && identity.source !== 'local';
    if (tab === 'ad_groups') return identity.type === 'group';
    return true;
  };

  $: filteredIdentities = identities.filter((identity) => {
    const q = normalizeText(search);
    const haystack = [
      identity.display_name,
      identity.username,
      identity.email,
      identity.sourceLabel,
      identity.roles.join(' ')
    ].map(normalizeText).join(' ');
    if (q && !haystack.includes(q)) return false;
    if (!matchesTab(identity)) return false;
    if (statusSourceFilter === 'active' && identity.status !== 'active') return false;
    if (statusSourceFilter === 'inactive' && identity.status !== 'inactive') return false;
    if (statusSourceFilter.startsWith('source:') && identity.sourceLabel !== statusSourceFilter.slice(7)) return false;
    return true;
  });

  $: totalPages = Math.max(1, Math.ceil(filteredIdentities.length / pageSize));
  $: if (pageIndex > totalPages) pageIndex = totalPages;
  $: pagedIdentities = filteredIdentities.slice((pageIndex - 1) * pageSize, pageIndex * pageSize);
  $: selectedIdentity =
    (selectedId ? identities.find((identity) => String(identity.id) === selectedId) : null) ??
    filteredIdentities[0] ??
    identities[0] ??
    null;

  const identityIcon = (identity: IdentityRow | null) => {
    if (!identity) return 'bi-person';
    return identity.type === 'group' ? 'bi-people' : identity.source === 'local' ? 'bi-person' : 'bi-person-badge';
  };

  const identityTone = (identity: IdentityRow | null) => {
    if (!identity) return 'blue';
    if (identity.type === 'group') return 'purple';
    if (identity.source === 'local') return 'blue';
    return 'violet';
  };

  const typeLabel = (identity: IdentityRow | null) => {
    if (!identity) return '-';
    if (identity.type === 'group') return t('Directory group');
    if (identity.source === 'local') return t('Local user');
    return t('Directory user');
  };

  const isDefaultLocalAdmin = (identity: IdentityRow | null) => {
    if (!identity || identity.type !== 'user') return false;
    const provisioningSource = normalizeText(identity.raw?.provisioning_source);
    const username = normalizeText(identity.raw?.username ?? identity.username);
    const authSource = normalizeText(identity.raw?.auth_source ?? identity.source);
    return authSource === 'local' && provisioningSource === 'system' && username === 'admin';
  };

  const canDeleteIdentity = (identity: IdentityRow | null) => !isDefaultLocalAdmin(identity);
  const roleBadgeVariant = (role: string): StatusVariant => normalizeText(role) === 'platform_admin' ? 'warning' : 'muted';

  const lastActivityLabel = (identity: IdentityRow) =>
    identity.updated_at ? timeAgo(identity.updated_at) : identity.created_at ? timeAgo(identity.created_at) : '-';

  async function refreshIdentityData() {
    await invalidateAll();
  }

  function requestDeleteIdentity(identity: IdentityRow | null = selectedIdentity) {
    if (!identity?.id) return;
    if (!canDeleteIdentity(identity)) {
      toast.warning(t('Default local admin is protected.'));
      return;
    }
    deleteTarget = identity;
  }

  async function handleDeleteIdentity() {
    const identity = deleteTarget;
    if (!identity?.id || !canDeleteIdentity(identity)) return;
    deleteBusy = true;
    try {
      await deleteIdentity(fetch, identity.id, identity.type);
      if (selectedId && String(selectedId) === String(identity.id)) {
        selectedId = null;
      }
      toast.success(t('Identity deleted.'));
      await refreshIdentityData();
      deleteTarget = null;
    } catch (error) {
      notifyError(toAppError(error, { source: 'ui' }));
      showApiErrorToast(error, 'Unable to delete identity.');
    } finally {
      deleteBusy = false;
    }
  }

  async function syncSelected() {
    if (!selectedIdentity?.identity_source_id || syncRunning) return;
    syncRunning = true;
    try {
      const run = await runIdentitySnapshot(fetch, selectedIdentity.identity_source_id, 'auto');
      let status = '';
      if (run?.job_id) {
        for (let i = 0; i < 40; i += 1) {
          const job = await getIdentityJob(fetch, Number(run.job_id));
          status = normalizeText(job?.status);
          if (['failed', 'error'].includes(status)) throw new Error(String(job?.error?.message ?? t('Snapshot failed')));
          if (['success', 'succeeded'].includes(status)) break;
          await new Promise((resolve) => setTimeout(resolve, 1500));
        }
      }
      toast.success(['success', 'succeeded'].includes(status) ? t('Directory synchronized.') : t('Sync started.'));
      await refreshIdentityData();
    } catch (error) {
      const appError = toAppError(error, { source: 'ui' });
      if (appError.code === 'SNAPSHOT_ALREADY_RUNNING') toast.info(t('A snapshot is already running for this identity source.'));
      else notifyError(appError);
    } finally {
      syncRunning = false;
    }
  }

  async function openMembersDrawer() {
    if (!selectedIdentity || selectedIdentity.type !== 'group' || !selectedIdentity.id) return;
    showMembersDrawer = true;
    membersLoading = true;
    members = [];
    try {
      members = await listIdentityGroupMembers(fetch, selectedIdentity.id);
    } catch (error) {
      notifyError(toAppError(error, { source: 'ui' }));
    } finally {
      membersLoading = false;
    }
  }

  function openEdit(identity: IdentityRow | null = selectedIdentity) {
    if (!identity) return;
    targetIdentity = identity;
    showEditIdentity = true;
  }

  onMount(() => {
    search = '';
    tab = 'all';
    statusSourceFilter = 'all';
  });
</script>

<section class="identity-page">
  <header class="identity-head">
    <div class="identity-title">
      <h1>{t('Identities')}</h1>
      <p>{t('{total} with access · {admins} admin accounts · {groups} AD groups', { total: stats.total, admins: stats.adminAccounts, groups: stats.adGroups })}</p>
    </div>
    <label class="identity-search">
      <i class="bi bi-search" aria-hidden="true"></i>
      <input type="search" bind:value={search} on:input={() => (pageIndex = 1)} placeholder={t('Search identities...')} aria-label={t('Search identities...')} />
    </label>
    <EntityActionButton variant="primary" icon="bi-plus-lg" label={t('Create identity')} onClick={() => (showWizard = true)} />
  </header>

  <div class="identity-filters">
    <div class="identity-chips" role="group" aria-label={t('Identity type')}>
      <button type="button" class:on={tab === 'all'} on:click={() => { tab = 'all'; pageIndex = 1; }}>{t('All')}</button>
      <button type="button" class:on={tab === 'local_admins'} on:click={() => { tab = 'local_admins'; pageIndex = 1; }}>{t('Local admins')}</button>
      <button type="button" class:on={tab === 'ad_admins'} on:click={() => { tab = 'ad_admins'; pageIndex = 1; }}>{t('AD admins')}</button>
      <button type="button" class:on={tab === 'ad_groups'} on:click={() => { tab = 'ad_groups'; pageIndex = 1; }}>{t('AD groups')}</button>
    </div>
    <select class="identity-select" bind:value={statusSourceFilter} on:change={() => (pageIndex = 1)} aria-label={t('All status / source')}>
      <option value="all">{t('All status / source')}</option>
      <option value="active">{t('Active')}</option>
      <option value="inactive">{t('Inactive')}</option>
      {#each sourceOptions as option}
        <option value={`source:${option}`}>{option}</option>
      {/each}
    </select>
  </div>

  <div class="identity-layout">
    <section class="identity-list-card">
      <table class="b2s-table identity-table">
        <thead>
          <tr>
            <th>{t('Identity')}</th>
            <th>{t('Type')}</th>
            <th>{t('Source')}</th>
            <th>{t('Status')}</th>
            <th>{t('Last activity')}</th>
          </tr>
        </thead>
        <tbody>
          {#each pagedIdentities as identity}
            <tr class:active={detailOpen && selectedIdentity && String(selectedIdentity.id) === String(identity.id)} on:click={() => { selectedId = String(identity.id); detailOpen = true; }}>
              <td>
                <div class="identity-cell">
                  <span class={`identity-avatar ${identityTone(identity)}`}><i class={`bi ${identityIcon(identity)}`} aria-hidden="true"></i></span>
                  <div class="identity-cell-stack">
                    <strong>{identity.display_name}</strong>
                    {#if isDefaultLocalAdmin(identity)}
                      <div class="identity-badges">
                        <StatusBadge status="protected" label={t('Protected')} compact={true} variant="warning" showDot={false} />
                      </div>
                    {/if}
                  </div>
                </div>
              </td>
              <td>{typeLabel(identity)}</td>
              <td>{identity.sourceLabel}</td>
              <td><StatusBadge status={identity.status === 'active' ? 'active' : 'disabled'} label={identity.status === 'active' ? t('Active') : t('Disabled')} compact={true} variant={identity.status === 'active' ? 'success' : 'disabled'} /></td>
              <td>{lastActivityLabel(identity)}</td>
            </tr>
          {:else}
            <tr><td colspan="5" class="identity-empty">{t('No identities found.')}</td></tr>
          {/each}
        </tbody>
      </table>
      {#if filteredIdentities.length > 0}
        <Pagination total={filteredIdentities.length} bind:page={pageIndex} bind:pageSize pageSizes={[10, 25, 50]} />
      {/if}
    </section>

    <aside class="identity-side" aria-label={t('Details')}>
      {#if detailOpen && selectedIdentity}
        <div class="identity-side-head">
          <span class={`identity-avatar ${identityTone(selectedIdentity)}`}><i class={`bi ${identityIcon(selectedIdentity)}`} aria-hidden="true"></i></span>
          <div>
            <h2>{selectedIdentity.display_name}</h2>
            <small>{typeLabel(selectedIdentity)} · {selectedIdentity.sourceLabel}</small>
          </div>
          <button type="button" class="identity-close" aria-label={t('Close')} on:click={() => (detailOpen = false)}><i class="bi bi-x-lg" aria-hidden="true"></i></button>
        </div>
    {#if selectedIdentity}
      <div class="identity-detail-grid">
        <dl>
          <div><dt>{t('Type')}</dt><dd>{typeLabel(selectedIdentity)}</dd></div>
          <div><dt>{t('Source')}</dt><dd>{selectedIdentity.sourceLabel}</dd></div>
          <div><dt>{t('Status')}</dt><dd>{selectedIdentity.status === 'active' ? t('Active') : t('Disabled')}</dd></div>
          {#if selectedIdentity.type === 'group'}
            <div><dt>{t('Members')}</dt><dd>{selectedIdentity.members_count ?? 0}</dd></div>
          {:else}
            <div><dt>{t('Username')}</dt><dd>{selectedIdentity.username}</dd></div>
          {/if}
          <div><dt>{t('Scope')}</dt><dd>{t('Application access')}</dd></div>
          <div><dt>{t('Last sync')}</dt><dd>{selectedIdentity.last_snapshot_at ? timeAgo(selectedIdentity.last_snapshot_at) : t('Not available')}</dd></div>
        </dl>
        <section>
          <h3>{t('Application roles')}</h3>
          {#if selectedIdentity.roles.length}
            <div class="identity-badges">
              {#each selectedIdentity.roles as role}
                <StatusBadge status={role} label={roleLabel(role)} compact={true} variant={roleBadgeVariant(role)} showDot={false} />
              {/each}
            </div>
          {:else}
            <p>{t('No application role assigned.')}</p>
          {/if}
          {#if selectedIdentity.source !== 'local'}
            <p class="identity-muted">{t('Directory binding: {sourceLabel}', { sourceLabel: selectedIdentity.sourceLabel })}</p>
          {/if}
          {#if selectedIdentity.type === 'group'}
            <p class="identity-muted">{t('Members of this group inherit the selected application role.')}</p>
          {/if}
          {#if isDefaultLocalAdmin(selectedIdentity)}
            <div class="identity-badges">
              <StatusBadge status="protected" label={t('Protected')} compact={true} variant="warning" showDot={false} />
            </div>
            <p class="identity-muted">{t('This default local admin cannot be deleted.')}</p>
          {/if}
        </section>
      </div>
    {/if}
        <div class="identity-side-actions">
      {#if selectedIdentity}
        <EntityActionButton variant="secondary" icon="bi-pencil" label={t('Edit')} onClick={() => openEdit()} />
        {#if selectedIdentity.type === 'group' && selectedIdentity.source !== 'local'}
          <EntityActionButton variant="secondary" icon="bi-people" label={t('View members')} onClick={openMembersDrawer} />
        {/if}
        {#if selectedIdentity.source !== 'local' && selectedIdentity.identity_source_id}
          <EntityActionButton
            variant="primary"
            icon="bi-arrow-repeat"
            busy={syncRunning}
            label={syncRunning ? t('Synchronizing…') : t('Sync now')}
            onClick={syncSelected}
          />
        {/if}
      {/if}
    </div>
        <div class="identity-side-danger">
      {#if selectedIdentity}
        {#if canDeleteIdentity(selectedIdentity)}
          <EntityActionButton variant="danger-outline" icon="bi-trash" label={t('Delete')} onClick={() => requestDeleteIdentity()} />
        {:else}
          <EntityActionButton variant="danger-outline" icon="bi-trash" label={t('Delete')} disabled={true} title={t('Default local admin cannot be deleted')} />
        {/if}
      {/if}
    </div>
      {:else}
        <div class="identity-side-empty">
          <i class="bi bi-person" aria-hidden="true"></i>
          <p>{t('Select an identity to see its roles.')}</p>
          <small>{t('This page governs application access only, not NTFS permissions.')}</small>
        </div>
      {/if}
    </aside>
  </div>

  <IdentityWizardModal
    open={showWizard}
    onClose={() => (showWizard = false)}
    on:done={async (event) => {
      showWizard = false;
      const nextId = event.detail?.id;
      if (nextId != null) selectedId = String(nextId);
      await refreshIdentityData();
    }}
  />

  <EditIdentityModal
    open={showEditIdentity}
    identity={targetIdentity}
    onClose={() => {
      showEditIdentity = false;
      targetIdentity = null;
    }}
    on:done={() => {
      showEditIdentity = false;
      targetIdentity = null;
      void refreshIdentityData();
    }}
  />

  <Drawer
    iconClass="bi bi-people"
    open={showMembersDrawer}
    title={t('Group members')}
    subtitle={selectedIdentity?.display_name ?? null}
    onClose={() => (showMembersDrawer = false)}
  >
    {#if membersLoading}
      <LoadingState block>{t('Loading members...')}</LoadingState>
    {:else if members.length}
      <div class="identity-members-list">
        {#each members as member}
          <article>
            <span class="identity-avatar blue"><i class="bi bi-person" aria-hidden="true"></i></span>
            <div>
              <strong>{member.display_name ?? member.username ?? member.email ?? member.id}</strong>
              <small>{member.email ?? member.username ?? t('No email')}</small>
            </div>
          </article>
        {/each}
      </div>
    {:else}
      <p class="identity-muted">{t('No members found for this group.')}</p>
    {/if}
  </Drawer>

  <ConfirmDeleteDialog
    open={Boolean(deleteTarget)}
    onClose={() => {
      if (deleteBusy) return;
      deleteTarget = null;
    }}
    onConfirm={() => void handleDeleteIdentity()}
    title={t('Delete identity')}
    description={deleteTarget ? t('Remove {display_name} from application access.', { display_name: deleteTarget.display_name }) : null}
    deleteLabel={t('Delete')}
    deleteBusyLabel={t('Deleting...')}
    busy={deleteBusy}
    impactItems={[
      'This removes application access only.',
      t('It does not delete the AD user/group.'),
      'It does not modify NTFS permissions.'
    ]}
  />
</section>

<style>
  .identity-page { display: flex; flex-direction: column; gap: 18px; padding: var(--b2s-page-padding); color: var(--b2s-color-text); }
  .identity-head { display: flex; align-items: flex-end; gap: 12px; }
  .identity-title { flex: 1 1 320px; min-width: 0; }
  .identity-title h1 { margin: 0; font-size: 38px; line-height: 1.05; font-weight: 600; letter-spacing: -.03em; }
  .identity-title p { margin: 6px 0 0; color: var(--b2s-color-text-muted); font-size: 15px; }
  .identity-search { flex: 0 1 420px; display: flex; align-items: center; gap: 10px; min-height: 44px; margin: 0; padding: 0 14px; border-radius: 12px; background: var(--b2s-color-surface); border: 1px solid var(--b2s-color-border-strong); color: var(--b2s-color-text-muted); }
  .identity-search:focus-within { border-color: var(--b2s-color-text); }
  .identity-search input { flex: 1; min-width: 0; border: 0; outline: 0; background: transparent; color: var(--b2s-color-text); font: inherit; }
  .identity-filters { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .identity-chips { display: flex; flex-wrap: wrap; gap: 8px; }
  .identity-chips button { min-height: 36px; padding: 0 13px; border-radius: 999px; border: 1px solid var(--b2s-color-border-strong); background: var(--b2s-color-surface); color: var(--b2s-color-text-muted); font: inherit; font-size: 13px; cursor: pointer; }
  .identity-chips button.on { background: var(--b2s-color-text); border-color: var(--b2s-color-text); color: #fff; font-weight: 600; }
  .identity-select { min-height: 36px; padding: 0 10px; border-radius: 10px; border: 1px solid var(--b2s-color-border-strong); background: var(--b2s-color-surface); color: var(--b2s-color-text); font: inherit; font-size: 13px; }
  .identity-layout { display: flex; align-items: flex-start; gap: 18px; }
  .identity-list-card, .identity-side { background: var(--b2s-color-surface); border: 1px solid var(--b2s-color-border); border-radius: 18px; box-shadow: 0 1px 2px rgba(14, 18, 24, .05), 0 8px 24px rgba(14, 18, 24, .06); }
  .identity-list-card { flex: 1; min-width: 0; overflow: hidden; }
  .identity-side { flex: 0 0 400px; position: sticky; top: 16px; max-height: calc(100vh - 32px); overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 16px; }
  .identity-side-head { display: flex; align-items: center; gap: 12px; }
  .identity-side-head > div { flex: 1; min-width: 0; }
  .identity-side-head h2 { margin: 0; font-size: 22px; font-weight: 600; letter-spacing: -.02em; overflow-wrap: anywhere; }
  .identity-side-head small { color: var(--b2s-color-text-muted); font-size: 12px; }
  .identity-close { width: 32px; height: 32px; flex: none; border: 0; border-radius: 8px; background: transparent; color: var(--b2s-color-text-muted); cursor: pointer; }
  .identity-close:hover { background: var(--b2s-color-neutral-soft); }
  .identity-side-actions { display: flex; flex-wrap: wrap; gap: 8px; }
  .identity-side-danger { padding-top: 12px; border-top: 1px solid var(--b2s-color-border); }
  .identity-side-empty { display: grid; justify-items: center; gap: 10px; padding: 40px 24px; text-align: center; color: var(--b2s-color-text-muted); }
  .identity-side-empty i { font-size: 26px; }
  .identity-side-empty p { margin: 0; }
  .identity-side-empty small { font-size: 12px; }
  .identity-cell-stack { display: grid; gap: 6px; }
  .identity-badges { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
  .identity-table { width: 100%; border-collapse: collapse; }
  .identity-table tr { cursor: pointer; }
  .identity-table tr.active td { background: var(--b2s-accent-soft); }
  .identity-cell { display: flex; align-items: center; gap: 10px; }
  .identity-avatar { width: 32px; height: 32px; flex: none; display: grid; place-items: center; border-radius: 50%; background: var(--b2s-color-neutral-soft); color: var(--b2s-color-text); font-size: 15px; }
  .identity-detail-grid { display: grid; gap: 16px; }
  .identity-detail-grid dl { display: grid; gap: 10px; margin: 0; }
  .identity-detail-grid div { display: grid; grid-template-columns: 110px 1fr; gap: 12px; }
  .identity-detail-grid dt, .identity-detail-grid h3 { margin: 0; color: var(--b2s-color-text-muted); font-size: 12px; font-weight: 400; }
  .identity-detail-grid h3 { margin-bottom: 6px; }
  .identity-detail-grid dd, .identity-detail-grid p { margin: 0; font-size: 14px; }
  .identity-members-list { display: grid; gap: 12px; }
  .identity-members-list article { display: flex; align-items: center; gap: 12px; }
  .identity-members-list strong, .identity-members-list small { display: block; }
  .identity-members-list small, .identity-muted { color: var(--b2s-color-text-muted); font-size: 12px; }
  .identity-empty { padding: 24px; text-align: center; color: var(--b2s-color-text-muted); }
</style>
