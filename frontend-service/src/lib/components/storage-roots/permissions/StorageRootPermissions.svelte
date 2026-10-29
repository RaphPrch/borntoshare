<script lang="ts">
  import { onDestroy } from 'svelte';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import ConfirmActionModal from '$lib/components/ui/ConfirmActionModal.svelte';
  import { t } from '$lib/i18n';
  import { formatDate, formatDateTime, timeAgo, initials } from '$lib/utils/format';
  import { csvFilename, downloadCsv } from '$lib/utils/csv';
  import { reportUiError } from '$lib/errors';
  import { toast } from '$lib/stores/toast';
  import { bulkDecision } from '$lib/api/access-requests';
  import {
    acceptAclGap,
    explainStorageRootAccess,
    notFound,
    reopenAclGap,
    type AccessExplanation,
    type AclEntry,
    type PermissionPerson,
    type StorageRootPermissionsData
  } from '$lib/api/storage-root-permissions';
  import AccessExplainDrawer from './AccessExplainDrawer.svelte';
  import { expiryProgress, levelLabel, viaLabel } from './permissions-format';

  /**
   * Storage roots › Permissions: who reaches the folder and why.
   * State of the ACL, an access checker, the map people -> AD groups -> folder, the people,
   * the entries added outside BornToShare and the expected system accounts.
   */
  export let data: StorageRootPermissionsData | null = null;
  export let loading = false;
  export let error: string | null = null;
  export let rootId: number | null = null;
  export let rootName = '';
  export let canManage = false;
  export let isAdmin = false;
  export let rescanBusy = false;
  export let onRescan: (() => void) | null = null;
  export let onChanged: () => void = () => {};

  // ---------------------------------------------------------------- state of the ACL
  const STATUS: Record<StorageRootPermissionsData['status'], { tone: string; icon: string; title: () => string }> = {
    ok: { tone: 'ok', icon: 'bi-shield-check', title: () => t('ACL compliant with BornToShare') },
    gap: { tone: 'warn', icon: 'bi-shield-exclamation', title: () => t('ACL compliant, gap(s) to review') },
    missing_ace: { tone: 'bad', icon: 'bi-shield-x', title: () => t('A BornToShare group is missing from the ACL') },
    never_scanned: { tone: 'idle', icon: 'bi-shield', title: () => t('ACL never read') }
  };
  $: status = data ? STATUS[data.status] : null;
  $: openGaps = data?.gaps.filter((g) => !g.accepted) ?? [];
  $: acceptedGaps = data?.gaps.filter((g) => g.accepted) ?? [];

  // ---------------------------------------------------------------- access checker
  let query = '';
  let checking = false;
  let checked: AccessExplanation | null = null;
  $: checkedMissing = notFound(checked);
  let timer: ReturnType<typeof setTimeout> | null = null;
  let checkSeq = 0;

  $: scheduleCheck(query);
  function scheduleCheck(value: string) {
    if (timer) clearTimeout(timer);
    const login = value.trim();
    if (!login || !rootId) {
      checked = null;
      return;
    }
    timer = setTimeout(async () => {
      const seq = ++checkSeq;
      checking = true;
      try {
        const result = await explainStorageRootAccess(fetch, rootId as number, login);
        if (seq === checkSeq) checked = result;
      } catch {
        if (seq === checkSeq) checked = null;
      } finally {
        if (seq === checkSeq) checking = false;
      }
    }, 400);
  }
  onDestroy(() => {
    if (timer) clearTimeout(timer);
  });

  // ---------------------------------------------------------------- map
  $: lanes = [
    ...(data?.groups ?? []).map((g) => ({
      key: `g:${g.name}`,
      group: g.name,
      managed: true,
      level: g.level,
      state: g.ace,
      rights: g.rights_label,
      scope: g.inherited_scope,
      members: data?.people.filter((p) => p.via.some((v) => v.kind !== 'request' && 'group' in v && v.group === g.name)) ?? []
    })),
    ...openGaps
      .filter((g) => (g.members_count ?? 0) > 0 || g.kind === 'broad')
      .map((g) => ({
        key: `x:${g.principal}`,
        group: g.name,
        managed: false,
        level: g.level,
        state: 'outside' as const,
        rights: g.rights_label,
        scope: g.inherited_scope,
        members: data?.people.filter((p) => p.via.some((v) => v.kind === 'outside' && v.group === g.name)) ?? []
      }))
  ];

  // ---------------------------------------------------------------- people
  let levelFilter: 'all' | 'read' | 'write' = 'all';
  let search = '';
  $: people = (data?.people ?? []).filter((p) => {
    if (levelFilter !== 'all' && p.level !== levelFilter) return false;
    const q = search.trim().toLowerCase();
    return !q || `${p.name} ${p.username ?? ''}`.toLowerCase().includes(q);
  });

  const mainRequest = (p: PermissionPerson) =>
    p.via.find((v) => v.kind === 'request' && v.level === p.level) as Extract<PermissionPerson['via'][number], { kind: 'request' }> | undefined;
  const groupOf = (p: PermissionPerson) => p.via.find((v) => v.kind !== 'request' && 'group' in v)?.['group' as never] as string | undefined;

  // ---------------------------------------------------------------- drawer, actions
  let explainFor: string | null = null;
  let revoking: PermissionPerson | null = null;
  let busy = false;

  async function revoke() {
    const target = revoking;
    revoking = null;
    if (!target?.revocable_request_ids.length) return;
    busy = true;
    try {
      const result = await bulkDecision(fetch, target.revocable_request_ids, 'revoke');
      if (Number(result?.failed_ids?.length ?? 0) > 0) throw new Error(String(Object.values(result?.failed_reasons ?? {})[0] ?? ''));
      toast.success(t('Access revoked: {name} is removed from the AD group.', { name: target.name }));
      onChanged();
    } catch (err: unknown) {
      reportUiError(err, t('Revocation failed.'), 'permissions.revoke');
    } finally {
      busy = false;
    }
  }

  async function toggleGap(gap: AclEntry, accept: boolean) {
    if (!rootId) return;
    busy = true;
    try {
      if (accept) await acceptAclGap(fetch, rootId, gap.principal);
      else await reopenAclGap(fetch, rootId, gap.principal);
      toast.success(accept ? t('Gap accepted: it is no longer reported.') : t('The gap is reported again.'));
      onChanged();
    } catch (err: unknown) {
      reportUiError(err, t('Unable to update the gap.'), 'permissions.gap');
    } finally {
      busy = false;
    }
  }

  function exportCsv() {
    downloadCsv(csvFilename(`permissions-${rootName || rootId}`), [
      { header: t('Person'), value: (p: PermissionPerson) => p.name },
      { header: t('Username'), value: (p: PermissionPerson) => p.username ?? '' },
      { header: t('Access'), value: (p: PermissionPerson) => levelLabel(p.level) },
      { header: t('By'), value: (p: PermissionPerson) => p.via.map((v) => `${viaLabel(v)}${'group' in v && v.group ? ` (${v.group})` : ''}`).join(' + ') },
      { header: t('Until'), value: (p: PermissionPerson) => (p.expires_at ? formatDate(p.expires_at) : t('Permanent')) }
    ], data?.people ?? []);
  }
</script>

{#if loading && !data}
  <LoadingState block>{t('Reading the permissions…')}</LoadingState>
{:else if error && !data}
  <InlineAlert tone="error">{error}</InlineAlert>
{:else if data && status}
  <div class="pm">
    <!-- State of the ACL -->
    <section class={`pm-hero is-${status.tone}`} aria-label={t('State of the ACL')}>
      <span class="pm-hero__icon"><i class={`bi ${status.icon}`} aria-hidden="true"></i></span>
      <div class="pm-hero__text">
        <strong>{status.title()}</strong>
        <span>
          {#if data.acl_scanned_at}
            {t('Read on the file server {ago}', { ago: timeAgo(data.acl_scanned_at) })} · {t('{count} entries', { count: data.acl_entries })} ·
            {t('{ok}/{total} BornToShare groups in place', { ok: data.summary.groups_ok, total: data.summary.groups })}
            {#if data.summary.gaps} · {t('{count} entry(ies) outside BornToShare', { count: data.summary.gaps })}{/if}
          {:else}
            {t('Read the ACL to see who reaches this folder.')}
          {/if}
        </span>
        {#if data.snapshot_at}<small>{t('Directory synchronised {ago}', { ago: timeAgo(data.snapshot_at) })}</small>{/if}
      </div>
      <div class="pm-hero__actions">
        {#if onRescan}
          <button type="button" class="b2s-btn b2s-btn-secondary" disabled={rescanBusy} on:click={() => onRescan?.()}>
            <i class={`bi ${rescanBusy ? 'bi-hourglass-split' : 'bi-arrow-clockwise'}`} aria-hidden="true"></i>{rescanBusy ? t('Reading…') : t('Read the ACL')}
          </button>
        {/if}
        <button type="button" class="b2s-btn b2s-btn-secondary" disabled={!data.people.length} on:click={exportCsv}>
          <i class="bi bi-download" aria-hidden="true"></i>{t('Export')}
        </button>
      </div>
    </section>

    <!-- Summary -->
    <section class="pm-tiles" aria-label={t('Summary')}>
      <div class="pm-tile">
        <span>{t('People with access')}</span>
        <strong>{data.summary.people}</strong>
        {#if data.summary.people}
          <div class="pm-split" aria-hidden="true">
            <span class="is-read" style={`flex: ${data.summary.read}`}></span><span class="is-write" style={`flex: ${data.summary.write}`}></span>
          </div>
          <small><i class="pm-key is-read"></i>{t('{count} read', { count: data.summary.read })} <i class="pm-key is-write"></i>{t('{count} modify', { count: data.summary.write })}</small>
        {/if}
      </div>
      <div class="pm-tile">
        <span>{t('BornToShare groups')}</span>
        <strong>{data.summary.groups_ok}<em>/{data.summary.groups}</em></strong>
        <small>{data.summary.groups_ok === data.summary.groups ? t('Each group has its ACE on the folder.') : t('A group has lost its ACE: approve a request again to put it back.')}</small>
      </div>
      <div class="pm-tile">
        <span>{t('Accesses ending within 30 days')}</span>
        <strong>{data.summary.expiring_30d}</strong>
        <small>{t('Removed from their group automatically at the end date.')}</small>
      </div>
    </section>

    <!-- Access checker -->
    <section class="pm-check" aria-label={t('Check the access of a person')}>
      <div>
        <strong>{t('Check the access of a person')}</strong>
        <span>{t('Type a login: BornToShare says whether the person reaches this folder, at which level and why.')}</span>
      </div>
      <div class="pm-check__row">
        <label class="pm-check__input">
          <i class="bi bi-search" aria-hidden="true"></i>
          <span class="visually-hidden">{t('Username')}</span>
          <input type="search" bind:value={query} placeholder={t('e.g. paul.martin')} autocomplete="off" />
        </label>
        <div class="pm-check__answer" aria-live="polite">
          {#if checking}
            <span class="pm-check__muted">{t('Checking…')}</span>
          {:else if checked?.found}
            <span class={`pm-check__verdict is-${checked.person.level}`}>
              {t('{name} has {level} access', { name: checked.person.name, level: levelLabel(checked.person.level).toLowerCase() })}
            </span>
            {#each checked.person.via as via}
              <span class="pm-chip">{viaLabel(via)}</span>
              {#if 'group' in via && via.group && via.kind !== 'request'}<span class="pm-chip is-mono">{via.group}</span>{/if}
            {/each}
            <button type="button" class="pm-check__more" on:click={() => checked?.found && (explainFor = checked.person.username ?? checked.person.name)}>{t('Details')}</button>
          {:else if checkedMissing}
            <span class="pm-check__verdict is-none">
              {checkedMissing.known_in_directory
                ? t('{name} has no access to this folder', { name: checkedMissing.display_name || checkedMissing.username })
                : t('No directory account named {name}', { name: checkedMissing.username })}
            </span>
          {:else}
            <span class="pm-check__muted">{t('The answer shows here, with the path request → AD group → folder.')}</span>
          {/if}
        </div>
      </div>
    </section>

    <!-- Map -->
    {#if lanes.length}
      <section class="b2s-panel" aria-label={t('Access map')}>
        <div class="b2s-panel__head">
          <h2>{t('Access map')}</h2>
          <span class="pm-sub">{t('From the people to the folder, through the AD groups')}</span>
        </div>
        <div class="pm-map">
          {#each lanes as lane (lane.key)}
            <div class="pm-lane">
              <div class="pm-lane__people">
                {#each lane.members.slice(0, 6) as member (member.key)}
                  <button type="button" class="pm-person" on:click={() => (explainFor = member.username ?? member.name)}>
                    <span class="pm-avatar">{initials(member.name)}</span>{member.name}
                  </button>
                {:else}
                  <span class="pm-lane__empty">{t('No member yet')}</span>
                {/each}
                {#if lane.members.length > 6}<span class="pm-lane__more">+{lane.members.length - 6}</span>{/if}
              </div>
              <span class="pm-link" aria-hidden="true"></span>
              <div class={`pm-group is-${lane.managed ? lane.level : 'outside'}`}>
                <strong class="is-mono">{lane.group}</strong>
                <small>
                  {t('{count} member(s)', { count: lane.members.length })} ·
                  {lane.managed ? t('managed by BornToShare') : t('outside BornToShare')}
                </small>
                {#if lane.state === 'missing'}<em class="pm-flag">{t('ACE missing')}</em>{:else if lane.state === 'mismatch'}<em class="pm-flag">{t('Unexpected rights')}</em>{/if}
              </div>
              <span class="pm-link" aria-hidden="true"></span>
              <div class="pm-folder">
                <strong>{lane.rights ? t(lane.rights) : t('No ACE')}</strong>
                <small>{lane.scope ? t('this folder, subfolders and files') : t('this folder only')}</small>
              </div>
            </div>
          {/each}
        </div>
      </section>
    {/if}

    <!-- People -->
    <section class="b2s-panel" aria-label={t('Who has access')}>
      <div class="b2s-panel__head pm-people-head">
        <h2>{t('Who has access')}</h2>
        <div class="b2s-segments" role="group" aria-label={t('Filter by level')}>
          <button type="button" class:is-active={levelFilter === 'all'} on:click={() => (levelFilter = 'all')}>{t('All')} <span>{data.summary.people}</span></button>
          <button type="button" class:is-active={levelFilter === 'read'} on:click={() => (levelFilter = 'read')}>{t('Read')} <span>{data.summary.read}</span></button>
          <button type="button" class:is-active={levelFilter === 'write'} on:click={() => (levelFilter = 'write')}>{t('Modify')} <span>{data.summary.write}</span></button>
        </div>
        <label class="pm-search">
          <i class="bi bi-search" aria-hidden="true"></i>
          <span class="visually-hidden">{t('Search a person')}</span>
          <input type="search" bind:value={search} placeholder={t('Search a person')} />
        </label>
      </div>
      {#if people.length === 0}
        <p class="pm-empty">{data.summary.people ? t('Nobody matches this filter.') : t('Nobody reaches this folder through BornToShare yet.')}</p>
      {:else}
        <div class="b2s-table-wrap">
          <table class="b2s-table pm-table">
            <thead>
              <tr>
                <th>{t('Person')}</th>
                <th>{t('Access')}</th>
                <th>{t('By')}</th>
                <th>{t('Until')}</th>
                <th><span class="visually-hidden">{t('Actions')}</span></th>
              </tr>
            </thead>
            <tbody>
              {#each people as person (person.key)}
                {@const request = mainRequest(person)}
                {@const progress = person.expires_at ? expiryProgress(request?.decided_at ?? null, person.expires_at) : null}
                <tr>
                  <td>
                    <button type="button" class="pm-who" on:click={() => (explainFor = person.username ?? person.name)}>
                      <span class="pm-avatar is-lg">{initials(person.name)}</span>
                      <span><strong>{person.name}</strong><small>{person.username ?? ''}</small></span>
                    </button>
                  </td>
                  <td><span class={`pm-level is-${person.level}`}>{levelLabel(person.level)}</span></td>
                  <td>
                    <div class="pm-via">
                      {#each person.via as via}
                        <span class={`pm-chip is-${via.kind}`}>{viaLabel(via)}</span>
                      {/each}
                      {#if groupOf(person)}<span class="pm-mono">{groupOf(person)}</span>{/if}
                      {#if person.warnings.includes('awaiting_sync')}<span class="pm-chip is-info" title={t('Approved recently: the next directory sync confirms the group membership.')}>{t('Sync pending')}</span>{/if}
                      {#if person.warnings.includes('missing_in_group')}<span class="pm-chip is-outside">{t('Missing from the group')}</span>{/if}
                    </div>
                  </td>
                  <td>
                    {#if person.expires_at && progress}
                      <span title={formatDateTime(person.expires_at)}>{formatDate(person.expires_at)} · {t('in {days} d', { days: progress.daysLeft })}</span>
                      <div class="pm-time" class:is-soon={progress.soon} aria-hidden="true"><span style={`width: ${progress.percentLeft}%`}></span></div>
                    {:else}
                      <span class="pm-muted">{request ? t('Permanent') : '—'}</span>
                    {/if}
                  </td>
                  <td class="pm-actions">
                    {#if canManage && person.revocable_request_ids.length}
                      <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-danger-outline" disabled={busy} on:click={() => (revoking = person)}>{t('Revoke')}</button>
                    {/if}
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {/if}
    </section>

    <!-- Gaps -->
    {#each openGaps as gap (gap.principal)}
      <section class="pm-gap" aria-label={t('Entry outside BornToShare')}>
        <div>
          <strong>{gap.kind === 'broad' ? t('Folder open widely') : t('Added outside BornToShare')}</strong>
          <span>
            <span class="pm-mono">{gap.principal}</span>
            {t('has {rights} on this folder, set directly on the file server.', { rights: t(gap.rights_label).toLowerCase() })}
            {#if gap.members_count}{t('Its {count} member(s) reach it without a request or a guardian.', { count: gap.members_count })}{/if}
          </span>
        </div>
        {#if isAdmin}
          <button type="button" class="b2s-btn b2s-btn-secondary" disabled={busy} on:click={() => toggleGap(gap, true)}>{t('Accept the gap')}</button>
        {/if}
      </section>
    {/each}

    {#if acceptedGaps.length}
      <details class="pm-details">
        <summary>{t('Accepted gaps')} <span>· {acceptedGaps.length}</span></summary>
        <ul class="pm-list">
          {#each acceptedGaps as gap (gap.principal)}
            <li>
              <span><strong>{gap.name}</strong><small class="pm-mono">{gap.principal} · {t(gap.rights_label)}</small></span>
              <span class="pm-muted">{gap.accepted_by ? t('accepted by {name}', { name: gap.accepted_by }) : ''}</span>
              {#if isAdmin}<button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" disabled={busy} on:click={() => toggleGap(gap, false)}>{t('Report again')}</button>{/if}
            </li>
          {/each}
        </ul>
      </details>
    {/if}

    <!-- System accounts -->
    {#if data.system.length}
      <details class="pm-details">
        <summary>{t('System and administration accounts')} <span>· {t('{count} expected entries', { count: data.system.length })}</span></summary>
        <ul class="pm-list is-grid">
          {#each data.system as entry (entry.principal)}
            <li>
              <span><strong>{entry.kind === 'service' ? t('BornToShare account') : entry.name}</strong><small class="pm-mono">{entry.principal}</small></span>
              <span class="pm-muted">{t(entry.rights_label)}</span>
            </li>
          {/each}
        </ul>
      </details>
    {/if}
  </div>
{/if}

<AccessExplainDrawer
  open={Boolean(explainFor)}
  {rootId}
  username={explainFor}
  {canManage}
  onClose={() => (explainFor = null)}
  onChanged={() => {
    explainFor = null;
    onChanged();
  }}
/>

<ConfirmActionModal
  open={Boolean(revoking)}
  onClose={() => (revoking = null)}
  onConfirm={revoke}
  title={t('Revoke the access of {name}?', { name: revoking?.name ?? '' })}
  impactItems={[t('{name} is removed from the AD group by the worker.', { name: revoking?.name ?? '' }), t('The group and its ACL stay on the folder for the other members.')]}
  confirmLabel={t('Revoke')}
/>

<style>
  .pm {
    display: grid;
    gap: 16px;
  }

  .pm-hero {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 16px;
    padding: 18px 20px;
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-lg);
    background: var(--b2s-color-surface);
  }

  .pm-hero__icon {
    width: 46px;
    height: 46px;
    flex: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    font-size: 22px;
  }

  .is-ok .pm-hero__icon { background: var(--b2s-color-success-soft); color: var(--b2s-color-success-strong); }
  .is-warn .pm-hero__icon { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .is-bad .pm-hero__icon { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger-strong); }
  .is-idle .pm-hero__icon { background: var(--b2s-color-neutral-soft); color: var(--b2s-color-text-muted); }

  .pm-hero__text {
    flex: 1 1 380px;
    display: grid;
    gap: 3px;
  }

  .pm-hero__text strong {
    font-size: var(--b2s-fs-lg);
    font-weight: 700;
  }

  .pm-hero__text span,
  .pm-hero__text small {
    color: var(--b2s-color-text-muted);
  }

  .pm-hero__text small {
    font-size: var(--b2s-fs-xs);
  }

  .pm-hero__actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .pm-tiles {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 16px;
  }

  .pm-tile {
    display: grid;
    gap: 8px;
    align-content: start;
    padding: 16px 18px;
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-md);
    background: var(--b2s-color-surface);
  }

  .pm-tile > span {
    color: var(--b2s-color-text-muted);
    font-weight: 500;
  }

  .pm-tile > strong {
    font-size: var(--b2s-fs-2xl);
    font-weight: 700;
  }

  .pm-tile em {
    color: var(--b2s-color-text-faint);
    font-style: normal;
    font-size: var(--b2s-fs-lg);
  }

  .pm-tile small {
    color: var(--b2s-color-text-soft);
    font-size: var(--b2s-fs-xs);
  }

  .pm-split {
    display: flex;
    gap: 2px;
    height: 8px;
    overflow: hidden;
    border-radius: var(--b2s-radius-pill);
  }

  .pm-split .is-read,
  .pm-key.is-read { background: var(--b2s-color-info); }
  .pm-split .is-write,
  .pm-key.is-write { background: var(--b2s-color-warning); }

  .pm-key {
    display: inline-block;
    width: 8px;
    height: 8px;
    margin: 0 6px 0 0;
    border-radius: 2px;
  }

  .pm-key.is-write {
    margin-left: 12px;
  }

  /* Checker: the dark band of the mock-up */
  .pm-check {
    display: grid;
    gap: 14px;
    padding: 18px 20px;
    border-radius: var(--b2s-radius-lg);
    background: var(--b2s-topbar-bg);
    color: var(--b2s-color-surface);
  }

  .pm-check > div:first-child {
    display: grid;
    gap: 4px;
  }

  .pm-check > div:first-child strong {
    font-size: var(--b2s-fs-lg);
  }

  .pm-check > div:first-child span,
  .pm-check__muted {
    color: #c7d2fe;
  }

  .pm-check__row {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
  }

  .pm-check__input {
    flex: 1 1 260px;
    display: flex;
    align-items: center;
    gap: 10px;
    height: 44px;
    padding: 0 14px;
    border-radius: var(--b2s-radius-md);
    background: var(--b2s-color-surface);
    color: var(--b2s-color-text-muted);
  }

  .pm-check__input input {
    flex: 1;
    border: none;
    outline: none;
    background: transparent;
    color: var(--b2s-color-text);
    font: inherit;
  }

  .pm-check__answer {
    flex: 2 1 420px;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    min-height: 44px;
    padding: 6px 14px;
    border: 1px solid rgba(255, 255, 255, 0.18);
    border-radius: var(--b2s-radius-md);
    background: rgba(255, 255, 255, 0.08);
  }

  .pm-check__verdict {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-weight: 600;
  }

  .pm-check__verdict::before {
    content: '';
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: #4ade80;
  }

  .pm-check__verdict.is-none::before {
    background: #fca5a5;
  }

  .pm-check .pm-chip {
    background: rgba(255, 255, 255, 0.14);
    color: var(--b2s-color-surface);
  }

  .pm-check__more {
    margin-left: auto;
    padding: 0;
    border: none;
    background: none;
    color: var(--b2s-color-surface);
    font: inherit;
    font-weight: 600;
    text-decoration: underline;
    cursor: pointer;
  }

  .pm-sub {
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-sm);
  }

  /* Map: people -> group -> folder */
  .pm-map {
    display: grid;
    gap: 12px;
    padding: 16px 20px 20px;
  }

  .pm-lane {
    display: grid;
    grid-template-columns: minmax(0, 1.3fr) 32px minmax(0, 1fr) 32px minmax(0, 0.8fr);
    align-items: center;
  }

  .pm-lane__people {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
    min-height: 44px;
    padding: 10px;
    border: 1px dashed var(--b2s-color-border-mid);
    border-radius: var(--b2s-radius-md);
  }

  .pm-lane__empty,
  .pm-lane__more {
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-sm);
  }

  .pm-person {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 10px 3px 3px;
    border: none;
    border-radius: var(--b2s-radius-pill);
    background: var(--b2s-color-neutral-soft);
    color: var(--b2s-color-text);
    font: inherit;
    font-size: var(--b2s-fs-sm);
    cursor: pointer;
  }

  .pm-person:hover {
    background: var(--b2s-color-info-soft);
  }

  .pm-avatar {
    width: 24px;
    height: 24px;
    flex: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    background: var(--b2s-color-primary-soft);
    color: var(--b2s-color-heading);
    font-size: 11px;
    font-weight: 700;
  }

  .pm-avatar.is-lg {
    width: 34px;
    height: 34px;
    font-size: var(--b2s-fs-xs);
  }

  .pm-link {
    height: 2px;
    margin: 0 4px;
    background: var(--b2s-color-border-mid);
  }

  .pm-group {
    display: grid;
    gap: 3px;
    padding: 10px 12px;
    border: 1px solid var(--b2s-color-info-border);
    border-radius: var(--b2s-radius-md);
    background: var(--b2s-color-info-soft);
  }

  .pm-group.is-write {
    border-color: var(--b2s-color-warning-border);
    background: var(--b2s-color-warning-soft);
  }

  .pm-group.is-outside {
    border-style: dashed;
    border-color: var(--b2s-color-warning);
    background: var(--b2s-color-surface);
  }

  .pm-group small {
    color: var(--b2s-color-text-soft);
    font-size: var(--b2s-fs-xs);
  }

  .pm-flag {
    justify-self: start;
    padding: 1px 8px;
    border-radius: var(--b2s-radius-pill);
    background: var(--b2s-color-danger-soft);
    color: var(--b2s-color-danger-strong);
    font-size: var(--b2s-fs-xs);
    font-style: normal;
    font-weight: 600;
  }

  .pm-folder {
    display: grid;
    gap: 3px;
    padding: 10px 12px;
    border-radius: var(--b2s-radius-md);
    background: var(--b2s-color-text);
    color: var(--b2s-color-surface);
  }

  .pm-folder small {
    color: var(--b2s-color-border-mid);
    font-size: var(--b2s-fs-xs);
  }

  .is-mono,
  .pm-mono {
    font-family: var(--b2s-font-mono);
    font-size: var(--b2s-fs-xs);
    overflow-wrap: anywhere;
  }

  .pm-people-head {
    flex-wrap: wrap;
    gap: 12px;
  }

  .pm-search {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 8px;
    height: 36px;
    min-width: 220px;
    padding: 0 12px;
    border: 1px solid var(--b2s-color-border);
    border-radius: var(--b2s-radius-sm);
    color: var(--b2s-color-text-muted);
  }

  .pm-search input {
    flex: 1;
    border: none;
    outline: none;
    background: transparent;
    font: inherit;
    font-size: var(--b2s-fs-sm);
  }

  .pm-empty {
    margin: 0;
    padding: 16px 20px 20px;
    color: var(--b2s-color-text-muted);
  }

  .pm-who {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    padding: 0;
    border: none;
    background: none;
    font: inherit;
    text-align: left;
    cursor: pointer;
  }

  .pm-who strong,
  .pm-who small {
    display: block;
  }

  .pm-who strong {
    color: var(--b2s-color-text);
    font-weight: 600;
  }

  .pm-who:hover strong {
    color: var(--b2s-color-info-strong);
  }

  .pm-who small,
  .pm-muted {
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
  }

  .pm-level {
    display: inline-block;
    padding: 2px 10px;
    border-radius: var(--b2s-radius-pill);
    font-size: var(--b2s-fs-xs);
    font-weight: 600;
  }

  .pm-level.is-read { background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); }
  .pm-level.is-write { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }

  .pm-via {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
  }

  .pm-chip {
    padding: 2px 8px;
    border-radius: 6px;
    background: var(--b2s-color-neutral-soft);
    color: var(--b2s-color-text-strong);
    font-size: var(--b2s-fs-xs);
  }

  .pm-chip.is-ad_only,
  .pm-chip.is-outside { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .pm-chip.is-info { background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); }

  .pm-time {
    width: 120px;
    height: 4px;
    margin-top: 4px;
    overflow: hidden;
    border-radius: var(--b2s-radius-pill);
    background: var(--b2s-color-border-soft);
  }

  .pm-time span {
    display: block;
    height: 4px;
    background: var(--b2s-color-success);
  }

  .pm-time.is-soon span {
    background: var(--b2s-color-warning);
  }

  .pm-table td:nth-child(4) {
    white-space: nowrap;
  }

  .pm-actions {
    text-align: right;
    white-space: nowrap;
  }

  .pm-gap {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 16px;
    padding: 16px 20px;
    border: 1px solid var(--b2s-color-warning-border);
    border-radius: var(--b2s-radius-lg);
    background: var(--b2s-color-warning-soft);
  }

  .pm-gap > div {
    flex: 1 1 420px;
    display: grid;
    gap: 4px;
  }

  .pm-gap strong {
    color: var(--b2s-color-warning-strong);
  }

  .pm-details {
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-lg);
    background: var(--b2s-color-surface);
  }

  .pm-details summary {
    padding: 14px 20px;
    font-weight: 600;
    cursor: pointer;
  }

  .pm-details summary span {
    color: var(--b2s-color-text-muted);
    font-weight: 400;
  }

  .pm-list {
    display: grid;
    gap: 8px;
    margin: 0;
    padding: 0 20px 18px;
    list-style: none;
  }

  .pm-list.is-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .pm-list li {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    padding: 10px 12px;
    border-radius: var(--b2s-radius-sm);
    background: var(--b2s-color-surface-soft);
  }

  .pm-list li strong,
  .pm-list li small {
    display: block;
  }

  .pm-list li small {
    color: var(--b2s-color-text-muted);
  }

  @media (max-width: 900px) {
    .pm-tiles,
    .pm-list.is-grid {
      grid-template-columns: 1fr;
    }

    .pm-lane {
      grid-template-columns: 1fr;
      gap: 6px;
    }

    .pm-link {
      display: none;
    }
  }
</style>
