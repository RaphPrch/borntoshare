<script lang="ts">
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  import EntityCard from '$lib/components/common/EntityCard.svelte';
  import EntityActionButton from '$lib/components/common/EntityActionButton.svelte';
  import StandardModalShell from '$lib/components/common/StandardModalShell.svelte';
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import {
    detachStorageRootAccessProfileMapping,
    listAccessProfileMembers,
    listAccessProfiles,
    listStorageRootAccessProfileMappings,
    upsertStorageRootAccessProfileMapping
  } from '$lib/api/access-profiles';
  import type {
    AccessProfile,
    AccessProfileMember
  } from '$lib/api/access-profiles';

  export let storageRootId: string;

  let loading = true;
  let busy = false;
  let showAttachModal = false;
  let showDetailModal = false;
  let errorMsg = '';
  let infoMsg = '';

  let allProfiles: AccessProfile[] = [];
  let attachSearch = '';
  let selectedAttachProfileId = '';

  let profiles: AccessProfile[] = [];
  let attachedProfiles: AccessProfile[] = [];
  let detailsLoading = false;
  let detailsError = '';
  let currentProfileId: number | null = null;
  let currentProfile: AccessProfile | null = null;
  let members: AccessProfileMember[] = [];

  const statusLabel = (status: string): string => {
    const value = String(status || '').toUpperCase();
    if (value === 'ACTIVE' || value === 'SUCCEEDED' || value === 'CREATED') return 'Active';
    if (value === 'FAILED') return 'Failed';
    if (value === 'RUNNING') return 'Running';
    if (value === 'PENDING') return 'Pending';
    return value || 'Unknown';
  };

  const formatUpdate = (value: string | undefined | null): string => {
    if (!value) return '—';
    const d = new Date(String(value));
    if (!Number.isFinite(d.getTime())) return '—';
    return d.toLocaleString('en-GB');
  };

  let pollTimer: ReturnType<typeof setTimeout> | null = null;
  let pollAttempts = 0;
  let pollDeadline = 0;

  const stopPolling = () => {
    if (pollTimer) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
    pollAttempts = 0;
    pollDeadline = 0;
  };

  const startPolling = () => {
    stopPolling();
    pollDeadline = Date.now() + 30_000;
    pollAttempts = 0;

    const scheduleNext = (delayMs: number) => {
      pollTimer = setTimeout(async () => {
        if (Date.now() >= pollDeadline) {
          stopPolling();
          return;
        }

        try {
          pollAttempts += 1;
          await refreshMappings();
          const stillPending = (attachedProfiles ?? []).some((p) => {
            const s = String(p?.status ?? '').toUpperCase();
            return s === 'PENDING' || s === 'RUNNING';
          });

          if (!stillPending) {
            stopPolling();
            return;
          }
        } catch {
          // silent while polling
        }

        // Progressive backoff to reduce API churn during long provisioning windows.
        const nextDelayMs = pollAttempts < 2 ? 2500 : pollAttempts < 5 ? 5000 : 10000;
        scheduleNext(nextDelayMs);
      }, delayMs);
    };

    scheduleNext(2500);
  };

  const normalizedLevel = (row: AccessProfile): string => {
    const level = String(row?.access_level_code ?? row?.permission ?? '')
      .trim()
      .toUpperCase();
    if (level === 'READ' || level === 'WRITE') {
      return level;
    }
    return 'READ';
  };

  const attachedProfileIdSet = () =>
    new Set(
      attachedProfiles
        .map((row) => Number((row as any)?.access_profile_id ?? row?.id ?? 0))
        .filter((id) => Number.isFinite(id) && id > 0)
    );

  const isAttached = (profileId: number) => attachedProfileIdSet().has(Number(profileId));

  const profileStatus = (profile: AccessProfile | null | undefined): string =>
    String(profile?.status ?? 'PROVISIONING').toUpperCase();

  const profileSource = (profile: AccessProfile | null | undefined): 'INHERITED' | 'LOCAL' => {
    const value = String(profile?.source ?? 'LOCAL').toUpperCase();
    return value === 'INHERITED' || value === 'ZONE' ? 'INHERITED' : 'LOCAL';
  };

  const expectedGroupName = (profile: AccessProfile | null | undefined): string =>
    String(profile?.group_name ?? profile?.name ?? profile?.code ?? normalizedLevel((profile ?? {}) as AccessProfile) ?? '—');

  const aclAlignment = (profile: AccessProfile | null | undefined): string =>
    String(profile?.acl_alignment ?? 'unknown').trim().toLowerCase();

  const aclAlignmentLabel = (profile: AccessProfile | null | undefined): string => {
    const value = aclAlignment(profile);
    if (value === 'present' || value === 'aligned') return 'Aligned';
    if (value === 'missing') return 'Missing ACL';
    if (value === 'extra') return 'Extra ACL';
    return 'Not scanned';
  };

  const aclAlignmentStatus = (profile: AccessProfile | null | undefined): string => {
    const value = aclAlignment(profile);
    if (value === 'present' || value === 'aligned') return 'active';
    if (value === 'missing' || value === 'extra') return 'failed';
    return 'unknown';
  };

  let inheritedProfileRows: AccessProfile[] = [];
  let customProfileRows: AccessProfile[] = [];
  let attachableProfileRows: AccessProfile[] = [];

  $: inheritedProfileRows = (profiles ?? []).filter((p) => profileSource(p) === 'INHERITED');
  $: customProfileRows = (profiles ?? []).filter((p) => profileSource(p) === 'LOCAL');
  $: {
    const q = attachSearch.trim().toLowerCase();
    const attached = new Set(
      attachedProfiles
        .map((row) => Number((row as any)?.access_profile_id ?? row?.id ?? 0))
        .filter((id) => Number.isFinite(id) && id > 0)
    );
    attachableProfileRows = allProfiles.filter((p) => {
      const id = Number(p?.id ?? 0);
      if (!Number.isFinite(id) || id <= 0) return false;
      if (attached.has(id)) return false;
      if (!q) return true;
      const hay = [p?.name, p?.code, p?.permission]
        .map((v) => String(v ?? '').toLowerCase())
        .join(' ');
      return hay.includes(q);
    });
  }

  const isProfileActive = (profile: AccessProfile | null | undefined): boolean =>
    ['ACTIVE', 'SUCCEEDED', 'CREATED'].includes(profileStatus(profile));

  const canMutateProfile = (profile: AccessProfile | null | undefined): boolean =>
    isProfileActive(profile) && !busy && profileSource(profile) !== 'INHERITED';

  async function refreshMappings() {
    const state = await listStorageRootAccessProfileMappings(fetch, storageRootId);
    attachedProfiles = state.attached_profiles ?? [];
    profiles = attachedProfiles;
  }

  async function refreshCatalog() {
    allProfiles = await listAccessProfiles(fetch);
  }

  async function loadAll() {
    loading = true;
    infoMsg = '';
    errorMsg = '';
    try {
      await Promise.all([refreshMappings(), refreshCatalog()]);
    } catch (e: unknown) {
      errorMsg = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  }

  async function detach(profileId: number) {
    busy = true;
    infoMsg = '';
    errorMsg = '';
    try {
      await detachStorageRootAccessProfileMapping(fetch, storageRootId, profileId);
      await refreshMappings();
      infoMsg = 'Access profile detached.';
    } catch (e: unknown) {
      errorMsg = e instanceof Error ? e.message : String(e);
    } finally {
      busy = false;
    }
  }

  async function attachSelectedProfile() {
    const accessProfileId = Number(selectedAttachProfileId);
    if (!Number.isFinite(accessProfileId) || accessProfileId <= 0) {
      errorMsg = 'Select an access profile to attach.';
      return;
    }

    if (isAttached(accessProfileId)) {
      errorMsg = 'This access profile is already attached to this storage root.';
      return;
    }

    const selectedProfile = (allProfiles ?? []).find((row) => Number(row?.id ?? 0) === accessProfileId) ?? null;
    const selectedLevel = normalizedLevel((selectedProfile ?? {}) as AccessProfile);

    busy = true;
    infoMsg = '';
    errorMsg = '';
    try {
      await upsertStorageRootAccessProfileMapping(fetch, storageRootId, { access_level: selectedLevel });
      await refreshMappings();
      await refreshCatalog();
      startPolling();
      showAttachModal = false;
      selectedAttachProfileId = '';
      attachSearch = '';
      infoMsg = 'Access profile attached.';
    } catch (e: unknown) {
      errorMsg = e instanceof Error ? e.message : String(e);
    } finally {
      busy = false;
    }
  }

  async function loadMembers(profileId: number) {
    members = await listAccessProfileMembers(fetch, profileId);
  }

  async function openDetail(profile: AccessProfile) {
    const profileId = Number(profile?.id ?? 0);
    if (!profileId) return;
    currentProfileId = profileId;
    currentProfile = profile;
    showDetailModal = true;
    detailsLoading = true;
    detailsError = '';

    try {
      await loadMembers(profileId);
    } catch (e: unknown) {
      detailsError = e instanceof Error ? e.message : String(e);
    } finally {
      detailsLoading = false;
    }
  }

  async function openAccessRequest(profile: AccessProfile) {
    const level = normalizedLevel(profile);
    await goto(`/access-requests?create=1&root=${encodeURIComponent(String(storageRootId))}&permission=${encodeURIComponent(level)}`);
  }

  onMount(loadAll);
</script>

{#if loading}
  <div class="b2s-muted">Loading mapping…</div>
{:else}
  <div class="sr-access-profiles-shell">
    <section class="sr-access-profiles-summary" aria-label="Access profile summary">
      <div class="sr-access-profile-stat">
        <span>Attached</span>
        <strong>{attachedProfiles.length}</strong>
      </div>
      <div class="sr-access-profile-stat">
        <span>Inherited</span>
        <strong>{inheritedProfileRows.length}</strong>
      </div>
      <div class="sr-access-profile-stat">
        <span>Local</span>
        <strong>{customProfileRows.length}</strong>
      </div>
      <EntityActionButton
        compact={true}
        variant="primary"
        icon="bi-plus-lg"
        label="Attach access profile"
        className="sr-access-profiles-attach"
        disabled={busy}
        onClick={() => (showAttachModal = true)}
      />
    </section>

    {#if errorMsg}
      <div class="b2s-alert b2s-alert--danger">{errorMsg}</div>
    {/if}
    {#if infoMsg}
      <div class="b2s-alert b2s-alert--success">{infoMsg}</div>
    {/if}

    <EntityCard title={`Inherited profiles (${inheritedProfileRows.length})`} panelClass="sr-access-profiles-card">
      <div class="b2s-table-wrap sr-access-profiles-table-wrap">
        <table class="b2s-table">
          <thead>
            <tr>
              <th>Group</th>
              <th>Source</th>
              <th>Expected AD group</th>
              <th>Filesystem ACL</th>
              <th>Provisioning</th>
              <th>Members</th>
              <th>Status</th>
              <th style="width: 1%">Action</th>
            </tr>
          </thead>
          <tbody>
            {#if inheritedProfileRows.length === 0}
              <tr>
                <td colspan="8" class="b2s-muted">No inherited profile from zone.</td>
              </tr>
            {/if}
            {#each inheritedProfileRows as p (p.id)}
              <tr>
                <td>
                  <span class="b2s-strong">{String(p?.name ?? p?.code ?? normalizedLevel(p))}</span>
                  <div class="b2s-muted">{String(p?.code ?? normalizedLevel(p) ?? '')}</div>
                </td>
                <td><StatusBadge status="inherited" label="INHERITED" variant="muted" compact={true} /></td>
                <td>
                  <span class="b2s-strong">{expectedGroupName(p)}</span>
                  <div class="b2s-muted">{normalizedLevel(p)} policy group</div>
                </td>
                <td>
                  <StatusBadge status={aclAlignmentStatus(p)} label={aclAlignmentLabel(p)} compact={true} />
                  <div class="b2s-muted">{String(p?.acl_principal ?? 'ACL not scanned yet')}</div>
                </td>
                <td>
                  <span class="b2s-muted">Updated: {formatUpdate(p?.updated_at)}</span>
                </td>
                <td>{Number(p?.members_count ?? 0)}</td>
                <td>
                  <StatusBadge status={profileStatus(p)} label={statusLabel(profileStatus(p))} compact={true} />
                </td>
                <td>
                  <div class="sr-access-actions">
                    <EntityActionButton compact={true} variant="secondary" icon="bi-eye" label="Members" disabled={busy} onClick={() => openDetail(p)} />
                    <EntityActionButton compact={true} variant="ghost" icon="bi-lock" label="Read-only" disabled={true} title="Inherited from zone (read-only)" />
                  </div>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </EntityCard>

    <EntityCard title={`Local profiles (${customProfileRows.length})`} panelClass="sr-access-profiles-card">
      <div class="b2s-table-wrap sr-access-profiles-table-wrap">
        <table class="b2s-table">
          <thead>
            <tr>
              <th>Group</th>
              <th>Source</th>
              <th>Expected AD group</th>
              <th>Filesystem ACL</th>
              <th>Provisioning</th>
              <th>Members</th>
              <th>Status</th>
              <th style="width: 1%">Action</th>
            </tr>
          </thead>
          <tbody>
            {#if customProfileRows.length === 0}
              <tr>
                <td colspan="8" class="b2s-muted">No local READ/WRITE profile attached to this storage root.</td>
              </tr>
            {/if}
            {#each customProfileRows as p (p.id)}
              <tr>
                <td>
                  <span class="b2s-strong">{String(p?.name ?? p?.code ?? normalizedLevel(p))}</span>
                  <div class="b2s-muted">{String(p?.code ?? normalizedLevel(p) ?? '')}</div>
                </td>
                <td><StatusBadge status="local" label="LOCAL" variant="info" compact={true} /></td>
                <td>
                  <span class="b2s-strong">{expectedGroupName(p)}</span>
                  <div class="b2s-muted">{normalizedLevel(p)} policy group</div>
                </td>
                <td>
                  <StatusBadge status={aclAlignmentStatus(p)} label={aclAlignmentLabel(p)} compact={true} />
                  <div class="b2s-muted">{String(p?.acl_principal ?? 'ACL not scanned yet')}</div>
                </td>
                <td>
                  <span class="b2s-muted">Updated: {formatUpdate(p?.updated_at)}</span>
                </td>
                <td>{Number(p?.members_count ?? 0)}</td>
                <td>
                  <StatusBadge status={profileStatus(p)} label={statusLabel(profileStatus(p))} compact={true} />
                  {#if String(p?.status ?? '').toUpperCase() === 'FAILED' && p?.last_error_message}
                    <div class="b2s-muted mt-1" style="max-width: 340px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                      {String(p.last_error_message)}
                    </div>
                  {/if}
                </td>
                <td>
                  <div class="sr-access-actions">
                    <EntityActionButton compact={true} variant="secondary" icon="bi-eye" label="Members" disabled={busy} onClick={() => openDetail(p)} />
                    <EntityActionButton compact={true} variant="secondary" icon="bi-person-plus" label="Access request" disabled={busy} onClick={() => openAccessRequest(p)} />
                    <EntityActionButton
                      compact={true}
                      variant="danger"
                      icon="bi-trash"
                      label="Remove"
                      disabled={!canMutateProfile(p)}
                      title={!isProfileActive(p) ? 'Mutation disabled while profile is not ACTIVE' : ''}
                      onClick={() => detach(Number(p.id ?? 0))}
                    />
                  </div>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </EntityCard>
  </div>

  <StandardModalShell
    open={showAttachModal}
    onClose={() => (showAttachModal = false)}
    title="Attach access profile"
    showFooter={true}
    showClose={true}
    confirmLabel={busy ? 'Attaching…' : 'Attach'}
    cancelLabel="Cancel"
    onConfirm={attachSelectedProfile}
    modalClass="b2s-modal sr-modal sr-modal--floating"
    backdropClass="b2s-modal-backdrop sr-modal-backdrop"
  >
    <div class="d-flex flex-column gap-2">
      <label class="form-label" for="ap-search">Search profile</label>
      <input id="ap-search" class="form-control" bind:value={attachSearch} placeholder="Search by name/code..." />

      <label class="form-label" for="ap-select">Access Profile</label>
      <select id="ap-select" class="form-select" bind:value={selectedAttachProfileId}>
        <option value="">Select an access profile...</option>
        {#each attachableProfileRows as p}
          <option value={String(p.id)}>{String(p.name ?? p.code ?? `Profile #${p.id}`)}</option>
        {/each}
      </select>

      {#if attachableProfileRows.length === 0}
        <div class="b2s-muted">No attachable profile available.</div>
      {/if}
    </div>
  </StandardModalShell>

  <StandardModalShell
    open={showDetailModal}
    onClose={() => (showDetailModal = false)}
    title="Group member management"
    showFooter={false}
    showClose={true}
    modalClass="b2s-modal sr-modal sr-modal--floating"
    backdropClass="b2s-modal-backdrop sr-modal-backdrop"
  >
    {#if detailsLoading}
      <div class="b2s-muted">Loading profile…</div>
    {:else if detailsError}
      <div class="b2s-alert b2s-alert--danger">{detailsError}</div>
    {:else if currentProfileId}
      <div class="mb-3">
        <div class="b2s-muted mb-2">
          Group: <strong>{currentProfile ? normalizedLevel(currentProfile) : '—'}</strong>
        </div>
        <div class="b2s-alert b2s-alert--info">
          Membership is read-only and is derived from identity sources plus approved access requests.
        </div>
      </div>

      {#if !isProfileActive(currentProfile)}
        <div class="b2s-alert b2s-alert--warning">Provisioning in progress</div>
      {:else}
        <div class="b2s-table-wrap">
          <table class="b2s-table">
            <thead>
              <tr>
                <th>Identity</th>
                <th>Source</th>
                <th>Added At</th>
              </tr>
            </thead>
            <tbody>
              {#if members.length === 0}
                <tr><td colspan="3" class="b2s-muted">No member.</td></tr>
              {/if}
              {#each members as m}
                <tr>
                  <td>{m.display_name ?? m.identity_id} <span class="b2s-muted">({m.identity_kind ?? 'identity'})</span></td>
                  <td>{m.source ?? '—'}</td>
                  <td>{m.added_at ?? '—'}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {/if}
    {/if}
  </StandardModalShell>
{/if}
