<script lang="ts">
  import Pagination from '$lib/components/ui/Pagination.svelte';
  import { t } from '$lib/i18n';
  import type { StatusVariant } from '$lib/utils/status';
  import { normalizeText } from '$lib/utils/values';
  import { invalidateAll } from '$app/navigation';
  import { page } from '$app/stores';
  import { onMount } from 'svelte';
  import EntityActionButton from '$lib/components/entity/EntityActionButton.svelte';
  import PageHeader from '$lib/components/ui/PageHeader.svelte';
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
      if (run?.job_id) {
        for (let i = 0; i < 18; i += 1) {
          const job = await getIdentityJob(fetch, Number(run.job_id));
          const status = normalizeText(job?.status);
          if (['success', 'succeeded', 'failed', 'error'].includes(status)) break;
          await new Promise((resolve) => setTimeout(resolve, 1000));
        }
      }
      toast.success(t('Sync started.'));
      await refreshIdentityData();
    } catch (error) {
      notifyError(toAppError(error, { source: 'ui' }));
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
  <PageHeader
    title={t('Identity')}
    subtitle={t('Manage local admin accounts, AD admin accounts, and AD groups that can access the platform.')}
  />
  <span class="identity-note"><i class="bi bi-info-circle" aria-hidden="true"></i> {t('This page governs application access only, not NTFS permissions.')}</span>

  <section class="identity-kpis" aria-label={t('Identity summary')}>
    <article class="identity-kpi">
      <span class="identity-kpi__icon blue"><i class="bi bi-people-fill" aria-hidden="true"></i></span>
      <div><span>{t('Total identities')}</span><strong>{stats.total}</strong><small>{t('All identities with access')}</small></div>
    </article>
    <article class="identity-kpi">
      <span class="identity-kpi__icon green"><i class="bi bi-person-fill" aria-hidden="true"></i></span>
      <div><span>{t('Admin accounts')}</span><strong>{stats.adminAccounts}</strong><small>{t('Local and AD admin accounts')}</small></div>
    </article>
    <article class="identity-kpi">
      <span class="identity-kpi__icon purple"><i class="bi bi-people" aria-hidden="true"></i></span>
      <div><span>{t('AD groups')}</span><strong>{stats.adGroups}</strong><small>{t('Groups allowed to sign in')}</small></div>
    </article>
  </section>

  <section class="identity-toolbar-card" aria-label={t('Identity filters')}>
    <label class="identity-search">
      <i class="bi bi-search" aria-hidden="true"></i>
      <input type="search" bind:value={search} on:input={() => (pageIndex = 1)} placeholder={t('Search identities...')} />
    </label>
    <div class="identity-tabs" role="tablist" aria-label={t('Identity type')}>
      <button type="button" class:active={tab === 'all'} on:click={() => { tab = 'all'; pageIndex = 1; }}>{t('All')}</button>
      <button type="button" class:active={tab === 'local_admins'} on:click={() => { tab = 'local_admins'; pageIndex = 1; }}>{t('Local admins')}</button>
      <button type="button" class:active={tab === 'ad_admins'} on:click={() => { tab = 'ad_admins'; pageIndex = 1; }}>{t('AD admins')}</button>
      <button type="button" class:active={tab === 'ad_groups'} on:click={() => { tab = 'ad_groups'; pageIndex = 1; }}>{t('AD groups')}</button>
    </div>
    <label class="identity-select">
      <i class="bi bi-funnel" aria-hidden="true"></i>
      <select bind:value={statusSourceFilter} on:change={() => (pageIndex = 1)}>
        <option value="all">{t('All status / source')}</option>
        <option value="active">{t('Active')}</option>
        <option value="inactive">{t('Inactive')}</option>
        {#each sourceOptions as option}
          <option value={`source:${option}`}>{option}</option>
        {/each}
      </select>
    </label>
    <EntityActionButton
      variant="primary"
      icon="bi-plus-lg"
      label={t('Create identity')}
      onClick={() => (showWizard = true)}
    />
  </section>

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
            <th aria-label={t('Actions')}></th>
          </tr>
        </thead>
        <tbody>
          {#each pagedIdentities as identity}
            <tr class:active={selectedIdentity && String(selectedIdentity.id) === String(identity.id)} on:click={() => (selectedId = String(identity.id))}>
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
              <td>
                <div class="identity-row-actions">
                  <EntityActionButton
                    variant="secondary"
                    icon="bi-pencil"
                    label={t('Edit identity')}
                    iconOnly={true}
                    stopPropagation={true}
                    onClick={() => openEdit(identity)}
                  />
                  {#if canDeleteIdentity(identity)}
                    <EntityActionButton
                      variant="danger-outline"
                      icon="bi-trash"
                      label={t('Delete identity')}
                      iconOnly={true}
                      stopPropagation={true}
                      onClick={() => requestDeleteIdentity(identity)}
                    />
                  {:else}
                    <EntityActionButton
                      variant="danger-outline"
                      icon="bi-trash"
                      label={t('Delete identity')}
                      iconOnly={true}
                      disabled={true}
                      title={t('Default local admin cannot be deleted')}
                    />
                  {/if}
                </div>
              </td>
            </tr>
          {:else}
            <tr><td colspan="6" class="identity-empty">{t('No identities found.')}</td></tr>
          {/each}
        </tbody>
      </table>
      {#if filteredIdentities.length > 0}
        <Pagination total={filteredIdentities.length} bind:page={pageIndex} bind:pageSize pageSizes={[10, 25, 50]} />
      {/if}
    </section>

    <aside class="identity-detail-card">
      {#if selectedIdentity}
        <header class="identity-detail-head">
          <span class={`identity-avatar identity-avatar--large ${identityTone(selectedIdentity)}`}><i class={`bi ${identityIcon(selectedIdentity)}`}></i></span>
          <div>
            <h2>{selectedIdentity.display_name}</h2>
            <div class="identity-pills">
              <span class="identity-dot"></span>
              <span>{typeLabel(selectedIdentity)}</span>
              <span>{selectedIdentity.sourceLabel}</span>
              <span class={selectedIdentity.status}>{selectedIdentity.status === 'active' ? t('Active') : t('Inactive')}</span>
            </div>
          </div>
        </header>

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

        <footer class="identity-detail-actions">
          <EntityActionButton variant="secondary" icon="bi-pencil" label={t('Edit')} onClick={() => openEdit()} />
          {#if selectedIdentity.type === 'group' && selectedIdentity.source !== 'local'}
            <EntityActionButton variant="secondary" icon="bi-people" label={t('View members')} onClick={openMembersDrawer} />
          {/if}
          {#if selectedIdentity.source !== 'local' && selectedIdentity.identity_source_id}
            <EntityActionButton
              variant="primary"
              icon="bi-arrow-repeat"
              busy={syncRunning}
              label={syncRunning ? t('Syncing...') : t('Sync now')}
              onClick={syncSelected}
            />
          {/if}
        </footer>
        <section class="identity-danger-zone">
          <h3>{t('Danger zone')}</h3>
          <p>{t('Delete removes application access only.')}</p>
          {#if canDeleteIdentity(selectedIdentity)}
            <EntityActionButton variant="danger-outline" icon="bi-trash" label={t('Delete')} onClick={() => requestDeleteIdentity()} />
          {:else}
            <EntityActionButton variant="danger-outline" icon="bi-trash" label={t('Delete')} disabled={true} title={t('Default local admin cannot be deleted')} />
            <p class="identity-danger-zone__hint">{t('Default local admin cannot be deleted.')}</p>
          {/if}
        </section>
      {:else}
        <EmptyStateInline message={t('Select an identity to review application access.')} />
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
      <p class="identity-muted">{t('Loading members...')}</p>
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

  .identity-page {
    --identity-navy: #061a44;
    --identity-blue: #0b59d1;
    min-height: calc(100vh - 68px);
    padding: var(--b2s-page-padding);
    color: #071638;
  }

  .identity-note {
    display: inline-flex;
    align-items: center;
    gap: 9px;
    color: #465b78;
    font-size: var(--b2s-fs-md);
    margin-top: 12px;
  }

  .identity-kpis {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 22px;
    margin: 22px 0 24px;
  }

  .identity-kpi,
  .identity-toolbar-card,
  .identity-list-card,
  .identity-detail-card {
    background: var(--b2s-color-surface, #ffffff);
    border: 1px solid var(--b2s-color-border, #dbe3ef);
    border-radius: var(--b2s-radius-sm, 8px);
    box-shadow: 0 6px 18px rgba(15, 23, 42, 0.06);
  }

  .identity-kpi {
    min-height: 88px;
    display: flex;
    align-items: center;
    gap: 22px;
    padding: 18px 28px;
  }

  .identity-kpi__icon,
  .identity-avatar {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex: 0 0 auto;
  }

  .identity-cell-stack {
    display: grid;
    gap: 6px;
  }

  .identity-badges {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    align-items: center;
  }

  .identity-kpi__icon {
    width: 22px;
    height: 22px;
    font-size: 1.35rem;
  }

  .identity-kpi__icon.blue,
  .identity-avatar.blue {
    color: #0b59d1;
    background: transparent;
  }

  .identity-kpi__icon.green,
  .identity-avatar.green {
    color: #059669;
    background: transparent;
  }

  .identity-kpi__icon.purple,
  .identity-avatar.purple,
  .identity-avatar.violet {
    color: #7c3aed;
    background: transparent;
  }

  .identity-kpi span {
    display: block;
    color: #596985;
    font-size: var(--b2s-fs-lg);
    line-height: 1.2;
    font-weight: 500;
  }

  .identity-kpi strong {
    display: block;
    margin-top: 3px;
    color: #071638;
    font-size: var(--b2s-fs-2xl);
    line-height: 1;
    font-weight: 650;
  }

  .identity-kpi small {
    display: block;
    margin-top: 6px;
    color: #596985;
    font-size: var(--b2s-fs-md);
  }

  .identity-toolbar-card {
    display: grid;
    grid-template-columns: minmax(260px, 330px) minmax(360px, 1fr) 210px auto;
    gap: 20px;
    align-items: center;
    padding: 16px 20px;
    margin-bottom: 18px;
  }

  .identity-search,
  .identity-select {
    min-height: 44px;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 0 14px;
    border: 1px solid #d8e2ef;
    border-radius: var(--b2s-radius-sm);
    background: #fff;
    color: #526682;
  }

  .identity-search input,
  .identity-select select {
    width: 100%;
    border: 0;
    outline: 0;
    background: transparent;
    color: #071638;
    font-size: var(--b2s-fs-md);
  }

  .identity-tabs {
    height: 44px;
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    border: 1px solid #d8e2ef;
    border-radius: var(--b2s-radius-sm);
    overflow: hidden;
  }

  .identity-tabs button {
    border: 0;
    border-right: 1px solid #d8e2ef;
    background: #fff;
    color: #223552;
    font-size: var(--b2s-fs-md);
    font-weight: 650;
  }

  .identity-tabs button:last-child {
    border-right: 0;
  }

  .identity-tabs button.active {
    color: var(--identity-blue);
    background: #f3f8ff;
    box-shadow: inset 0 -2px 0 var(--identity-blue);
  }

  .identity-layout {
    display: grid;
    grid-template-columns: minmax(0, 1.45fr) minmax(420px, 0.95fr);
    gap: 22px;
    align-items: start;
  }

  .identity-table {
    width: 100%;
    border-collapse: collapse;
  }

  .identity-table tr {
    cursor: pointer;
  }

  .identity-table tr.active {
    box-shadow: inset 3px 0 0 #0b63f4;
  }

  .identity-cell {
    display: flex;
    align-items: center;
    gap: 14px;
    padding-block: 10px;
  }

  .identity-avatar {
    width: 22px;
    height: 22px;
    font-size: var(--b2s-fs-xl);
  }

  .identity-avatar--large {
    width: 22px;
    height: 22px;
    font-size: var(--b2s-fs-xl);
  }

  .identity-dot {
    font-size: 0.42rem;
  }

  .identity-pills .active {
    color: #047857;
    background: #dff8ec;
  }

  .identity-pills .inactive {
    color: #64748b;
    background: #edf2f7;
  }

  .identity-row-actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
  }

  .identity-detail-card {
    padding: 22px 26px 0;
    overflow: hidden;
  }

  .identity-detail-head {
    display: flex;
    align-items: flex-start;
    gap: 18px;
    margin-bottom: 22px;
  }

  .identity-detail-head h2 {
    margin: 0 0 10px;
    color: #071638;
    font-size: var(--b2s-fs-xl);
    line-height: 1.15;
    font-weight: 650;
  }

  .identity-pills {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
  }

  .identity-pills span:not(.identity-dot) {
    display: inline-flex;
    align-items: center;
    min-height: 26px;
    padding: 0 12px;
    border-radius: var(--b2s-radius-pill);
    color: #0b59d1;
    background: #eaf2ff;
    font-size: 0.76rem;
    font-weight: 700;
  }

  .identity-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #0b8f49;
  }

  .identity-detail-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 24px;
    padding-bottom: 22px;
    border-bottom: 1px solid #dfe7f2;
  }

  .identity-detail-grid dl {
    display: grid;
    gap: 12px;
    margin: 0;
  }

  .identity-detail-grid div {
    display: grid;
    grid-template-columns: 100px 1fr;
    gap: 14px;
  }

  .identity-detail-grid dt,
  .identity-detail-grid h3 {
    margin: 0;
    color: #344664;
    font-size: var(--b2s-fs-sm);
    font-weight: 760;
  }

  .identity-detail-grid dd,
  .identity-detail-grid p {
    margin: 0;
    color: #071638;
    font-size: var(--b2s-fs-md);
  }

  .identity-members-list article {
    display: flex;
    align-items: center;
    gap: 14px;
  }

  .identity-members-list strong,
  .identity-members-list small {
    display: block;
  }

  .identity-members-list small,
  .identity-muted {
    color: #5d6f8a;
    font-size: var(--b2s-fs-sm);
  }

  .identity-detail-actions {
    display: grid;
    grid-template-columns: 1fr 1.25fr 1fr;
    gap: 16px;
  }

  .identity-danger-zone {
    padding: 18px 0 0;
    border-top: 1px solid #dfe7f2;
    display: grid;
    gap: 10px;
  }

  .identity-danger-zone h3,
  .identity-danger-zone p {
    margin: 0;
  }

  .identity-danger-zone h3 {
    font-size: var(--b2s-fs-lg);
    color: var(--b2s-color-danger, #dc3545);
  }

  .identity-danger-zone p,
  .identity-danger-zone__hint {
    font-size: var(--b2s-fs-md);
    color: #64748b;
  }

  .identity-members-list {
    display: grid;
    gap: 14px;
  }

  .identity-empty {
    height: 180px !important;
    text-align: center;
    color: #64748b !important;
  }

  @media (max-width: 1280px) {
    .identity-toolbar-card,
    .identity-layout {
      grid-template-columns: 1fr;
    }
  }
</style>
