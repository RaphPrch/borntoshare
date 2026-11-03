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
  import { goto } from '$app/navigation';
  import { bulkDecision } from '$lib/api/access-requests';
  import { repairStorageRootAcl } from '$lib/api/storage-root-permissions';
  import {
    acceptAclGap,
    explainStorageRootAccess,
    extendAccess,
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
   * Storage roots › Permissions, in cards: the state of the ACL, « who reaches it? » with the path
   * person → AD group → folder, the path of the accesses per AD group (click = filter), the people,
   * and on the side the entries set outside BornToShare, the AD groups and the next end dates.
   */
  export let data: StorageRootPermissionsData | null = null;
  export let loading = false;
  export let error: string | null = null;
  export let rootId: number | null = null;
  export let rootName = '';
  export let canManage = false;
  export let isAdmin = false;
  export let onChanged: () => void = () => {};

  let repairing = false;
  let repairAsked = false;
  async function repairAcl(): Promise<void> {
    if (!rootId) return;
    repairAsked = false;
    repairing = true;
    try {
      await repairStorageRootAcl(fetch, rootId);
      toast.success(t('ACL repaired on the folder. Its content follows in the background.'));
      setTimeout(onChanged, 4000);
    } catch (error: any) {
      reportUiError(error, t('Unable to repair the ACL.'), 'storage-root.acl-repair');
    } finally {
      repairing = false;
    }
  }

  // The tab follows a propagation in progress
  let propagationTimer: ReturnType<typeof setTimeout> | null = null;
  $: if (data?.propagation?.state === 'running' && !propagationTimer) {
    propagationTimer = setTimeout(() => {
      propagationTimer = null;
      onChanged();
    }, 15000);
  }
  onDestroy(() => {
    if (propagationTimer) clearTimeout(propagationTimer);
  });
  export let onToggleInheritance: () => void = () => {};
  /** Login to explain at once (⌘K palette, link from another page) */
  export let explainLogin: string | null = null;

  const STATE: Record<StorageRootPermissionsData['status'], { tone: string; word: () => string }> = {
    ok: { tone: 'ok', word: () => t('Compliant.') },
    applying: { tone: 'warn', word: () => t('Being applied.') },
    gap: { tone: 'warn', word: () => t('To review.') },
    missing_ace: { tone: 'bad', word: () => t('Incomplete.') },
    never_scanned: { tone: 'idle', word: () => t('Not read yet.') }
  };
  $: state = data ? STATE[data.status] : null;
  $: openGaps = data?.gaps.filter((g) => !g.accepted) ?? [];
  $: acceptedGaps = data?.gaps.filter((g) => g.accepted) ?? [];
  $: outsidePeople = data?.people.filter((p) => p.via.every((v) => v.kind === 'outside')) ?? [];
  $: governedPeople = data?.people.filter((p) => !p.via.every((v) => v.kind === 'outside')) ?? [];

  // ---------------------------------------------------------------- checker
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

  // ---------------------------------------------------------------- flow bands
  type Band = { key: string; group: string; level: 'read' | 'write' | null; managed: boolean; state: string; rights: string | null; members: PermissionPerson[] };
  const groupOfVia = (p: PermissionPerson) =>
    p.via.filter((v) => v.kind !== 'request' && 'group' in v).map((v) => String((v as { group: string }).group));
  $: bands = [
    ...(data?.groups ?? []).map(
      (g): Band => ({ key: `g:${g.name}`, group: g.name, level: g.level, managed: true, state: g.ace, rights: g.rights_label,
        members: data?.people.filter((p) => groupOfVia(p).includes(g.name)) ?? [] })
    ),
    ...openGaps
      .filter((g) => (g.members_count ?? 0) > 0 || g.kind === 'broad')
      .map((g): Band => ({ key: `x:${g.principal}`, group: g.name, level: g.level, managed: false, state: 'outside', rights: g.rights_label,
        members: data?.people.filter((p) => groupOfVia(p).includes(g.name)) ?? [] }))
  ];

  // ---------------------------------------------------------------- people
  let filter: 'all' | 'read' | 'write' | 'ending' = 'all';
  let groupFilter: string | null = null;
  let search = '';
  $: horizon = Date.now() + 30 * 86400000;
  $: people = governedPeople.filter((p) => {
    if (filter === 'read' || filter === 'write') if (p.level !== filter) return false;
    if (filter === 'ending' && !(p.expires_at && Date.parse(p.expires_at) <= horizon)) return false;
    if (groupFilter && !groupOfVia(p).includes(groupFilter)) return false;
    const q = search.trim().toLowerCase();
    return !q || `${p.name} ${p.username ?? ''}`.toLowerCase().includes(q);
  });

  const toggleGroup = (name: string) => (groupFilter = groupFilter === name ? null : name);
  const mainRequest = (p: PermissionPerson) =>
    p.via.find((v) => v.kind === 'request' && v.level === p.level) as Extract<PermissionPerson['via'][number], { kind: 'request' }> | undefined;

  // ---------------------------------------------------------------- drawer, actions
  let explainFor: string | null = null;
  let explainedFrom: string | null = null;
  $: if (explainLogin && explainLogin !== explainedFrom) {
    explainedFrom = explainLogin;
    explainFor = explainLogin;
  }
  let revoking: PermissionPerson | null = null;
  let showSystem = false;
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

  const gapPeople = (gap: AclEntry) => outsidePeople.filter((p) => groupOfVia(p).includes(gap.name));

  // ---------------------------------------------------------------- end dates
  $: ends = (data?.people ?? [])
    .filter((p) => p.expires_at)
    .sort((a, b) => String(a.expires_at).localeCompare(String(b.expires_at)))
    .slice(0, 5);
  let extending: string | null = null;
  async function extend(person: PermissionPerson) {
    const request = mainRequest(person) ?? (person.via.find((v) => v.kind === 'request' && v.expires_at) as ReturnType<typeof mainRequest>);
    if (!request) return;
    extending = person.key;
    try {
      const result = await extendAccess(fetch, request.request_id, 30);
      toast.success(t('Access extended until {date}.', { date: formatDate(result.expires_at ?? '') }));
      onChanged();
    } catch (err: unknown) {
      reportUiError(err, t('Unable to extend this access.'), 'permissions.extend');
    } finally {
      extending = null;
    }
  }

  $: ringShare = data && data.summary.groups ? Math.round((data.summary.groups_ok / data.summary.groups) * 100) : 0;
  const ACE_LABEL: Record<string, () => string> = {
    ok: () => t('ACE in place'),
    missing: () => t('ACE missing'),
    mismatch: () => t('Unexpected rights'),
    outside: () => t('outside BornToShare')
  };
</script>

{#if loading && !data}
  <LoadingState block>{t('Reading the permissions…')}</LoadingState>
{:else if error && !data}
  <InlineAlert tone="error">{error}</InlineAlert>
{:else if data && state}
  <div class="pm">
    <div class="pm-col">
      <!-- state of the ACL -->
      <section class="pm-card" aria-label={t('State of the ACL')}>
        <header>
          <h2>{t('State of the ACL')}</h2>
          {#if (canManage || isAdmin) && data.summary.groups > 0}
            <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" disabled={repairing} on:click={() => (repairAsked = true)}>{repairing ? t('Repairing…') : t('Repair the ACL')}</button>
          {/if}
          <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" disabled={!data.people.length} on:click={exportCsv}><i class="bi bi-download" aria-hidden="true"></i>{t('Export')}</button>
        </header>
        <div class="pm-state">
          <span class={`pm-ring is-${state.tone}`} style={`--share:${ringShare}%`} aria-hidden="true"><b>{data.summary.groups_ok}/{data.summary.groups}</b></span>
          <div class="pm-state__text">
            <strong class={`is-${state.tone}`}>{state.word().replace(/\.$/, '')}</strong>
            <p>
              {#if !data.acl_scanned_at}
                {t('Read the ACL to see who reaches this folder.')}
              {:else}
                {t('{count} person(s) reach this folder', { count: data.summary.people })}{#if data.summary.people},
                  <span class="is-read">{t('{count} read', { count: data.summary.read })}</span> {t('and')}
                  <span class="is-write">{t('{count} modify', { count: data.summary.write })}</span>{/if},
                {t('through {count} AD group(s)', { count: data.summary.groups })}.
                {#if data.summary.groups_ok < data.summary.groups}
                  <span class="is-bad">{t('{count} group(s) without their ACE.', { count: data.summary.groups - data.summary.groups_ok })}</span>
                {/if}
              {/if}
            </p>
            <div class="pm-facts">
              {#if data.acl_scanned_at}<span>{t('ACL read {ago}', { ago: timeAgo(data.acl_scanned_at) })}</span><span>{t('{count} entries', { count: data.acl_entries })}</span>{/if}
              {#if data.snapshot_at}<span>{t('directory synchronised {ago}', { ago: timeAgo(data.snapshot_at) })}</span>{/if}
              {#if data.inheritance?.known}
                <span class:is-warn={data.inheritance.broken}>
                  <i class={`bi ${data.inheritance.broken ? 'bi-scissors' : 'bi-diagram-3'}`} aria-hidden="true"></i>
                  {data.inheritance.broken ? t('inheritance broken') : t('inherits from the parent folder')}
                  {#if isAdmin}· <button type="button" class="pm-link" on:click={onToggleInheritance}>{data.inheritance.broken ? t('Restore') : t('Break')}</button>{/if}
                </span>
              {/if}
            </div>
          </div>
        </div>
        {#if data.propagation?.state === 'running'}
          <p class="pm-note"><span class="spinner-border spinner-border-sm" aria-hidden="true"></span> {t('The rights are being applied to the content of the folder. On a big folder it can take a while.')}</p>
        {:else if data.propagation?.state === 'failed'}
          <p class="pm-note is-bad"><i class="bi bi-exclamation-triangle" aria-hidden="true"></i> {t('The rights could not reach all the content of the folder: some people may be refused inside. Use « Repair the ACL ».')}</p>
        {/if}
      </section>

      <!-- who reaches it? -->
      <section class="pm-card" aria-label={t('Check the access of a person')}>
        <header><h2>{t('Who reaches it?')}</h2></header>
        <label class="pm-ask">
          <i class="bi bi-search" aria-hidden="true"></i>
          <input type="search" bind:value={query} placeholder={t('Type a login, e.g. paul.martin')} autocomplete="off" aria-label={t('Username')} />
        </label>
        <div aria-live="polite">
          {#if checking}
            <p class="pm-muted">{t('Checking…')}</p>
          {:else if checked?.found}
            <div class="pm-answer">
              <p><strong>{checked.person.name}</strong> {checked.person.level === 'write' ? t('modifies this folder') : t('reads this folder')}
                {#if checked.person.expires_at}<span class="is-write">· {t('ends {date}', { date: formatDate(checked.person.expires_at) })}</span>{/if}
                <button type="button" class="pm-link" on:click={() => checked?.found && (explainFor = checked.person.username ?? checked.person.name)}>{t('Details')} ›</button>
              </p>
              <div class="pm-chain">
                <span class="pm-step is-ok"><b>{checked.person.name}</b><small>{checked.person.username ?? ''}</small></span>
                {#each checked.steps as step}
                  <span class="pm-arrow" aria-hidden="true">→</span>
                  {#if step.kind === 'request'}
                    <span class="pm-step is-ok"><b>{t('{code} validated', { code: step.code })}</b><small>{step.approver ?? ''}</small></span>
                  {:else if step.kind === 'membership'}
                    <span class="pm-step is-ok"><b class="mono">{step.group}</b><small>{step.managed ? t('managed') : t('outside BornToShare')}</small></span>
                  {:else}
                    <span class={`pm-step ${step.state === 'ok' ? 'is-ok' : 'is-bad'}`}><b>{rootName}</b><small>{step.rights_label ? t(step.rights_label) : t('No ACE')}</small></span>
                  {/if}
                {/each}
              </div>
            </div>
          {:else if checkedMissing}
            <div class="pm-answer is-none">
              <p>
                {checkedMissing.known_in_directory
                  ? t('{name} has no access to this folder', { name: checkedMissing.display_name || checkedMissing.username })
                  : t('No directory account named {name}', { name: checkedMissing.username })}
              </p>
              {#if checkedMissing.known_in_directory && rootId}
                <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-primary" on:click={() => goto(`/access-requests/new?root=${rootId}`)}>{t('Request an access')}</button>
              {/if}
            </div>
          {:else}
            <p class="pm-muted">{t('The answer shows here, with the path request → AD group → folder.')}</p>
          {/if}
        </div>
      </section>

      <!-- path of the accesses -->
      {#if bands.length}
        <section class="pm-card" aria-label={t('Path of the accesses')}>
          <header><h2>{t('Path of the accesses')}</h2><small class="pm-muted">{t('Click a group to see only its members')}</small></header>
          {#each bands as band (band.key)}
            <button type="button" class={`pm-path is-${band.managed ? band.level ?? 'read' : 'outside'}`} class:is-active={groupFilter === band.group} aria-pressed={groupFilter === band.group} on:click={() => toggleGroup(band.group)}>
              <span class="pm-path__who">
                <span class="pm-stack">{#each band.members.slice(0, 4) as member (member.key)}<span class={`pm-face is-${band.level ?? 'read'}`}>{initials(member.name)}</span>{/each}</span>
                <span><b>{band.members.length ? t('{count} person(s)', { count: band.members.length }) : t('No member yet')}</b><small>{band.level === 'write' ? t('in modification') : t('in read')}</small></span>
              </span>
              <span class="pm-arrow" aria-hidden="true">→</span>
              <span class="pm-path__group"><b class="mono">{band.group}</b><small>{band.managed ? t('managed') : t('outside BornToShare')} · {ACE_LABEL[band.state]?.() ?? (band.rights ? t(band.rights) : '')}</small></span>
              <span class="pm-arrow" aria-hidden="true">→</span>
              <span class="pm-path__folder"><i class="bi bi-folder2-open" aria-hidden="true"></i>{rootName}</span>
            </button>
          {/each}
        </section>
      {/if}

      <!-- people -->
      <section class="pm-card" aria-label={t('Who has access')}>
        <header><h2>{t('Who has access')}</h2></header>
        <div class="pm-tools">
          <label class="pm-search"><i class="bi bi-search" aria-hidden="true"></i><input type="search" bind:value={search} placeholder={t('Search a person')} aria-label={t('Search a person')} /></label>
          <div class="pm-seg" role="group" aria-label={t('Filter by level')}>
            <button type="button" class:on={filter === 'all'} on:click={() => (filter = 'all')}>{t('All')}<span>{governedPeople.length}</span></button>
            <button type="button" class:on={filter === 'read'} on:click={() => (filter = 'read')}>{t('Read')}<span>{data.summary.read}</span></button>
            <button type="button" class:on={filter === 'write'} on:click={() => (filter = 'write')}>{t('Modify')}<span>{data.summary.write}</span></button>
            <button type="button" class:on={filter === 'ending'} on:click={() => (filter = 'ending')}>{t('Ending within 30 days')}<span>{data.summary.expiring_30d}</span></button>
          </div>
          {#if groupFilter}<button type="button" class="pm-chip is-filter" on:click={() => (groupFilter = null)}>{groupFilter} <i class="bi bi-x" aria-hidden="true"></i></button>{/if}
        </div>
        {#if people.length}
          <ul class="pm-rows">
            {#each people as person (person.key)}
              {@const request = mainRequest(person)}
              {@const progress = person.expires_at ? expiryProgress(request?.decided_at ?? null, person.expires_at) : null}
              <li>
                <button type="button" class="pm-who" on:click={() => (explainFor = person.username ?? person.name)}>
                  <span class={`pm-face is-lg is-${person.level}`}>{initials(person.name)}</span>
                  <span><strong>{person.name}</strong><small>{person.username ?? ''}</small></span>
                </button>
                <span><span class={`pm-level is-${person.level}`}>{levelLabel(person.level)}</span></span>
                <span class="pm-via" title={[...person.via.map((via) => viaLabel(via)), ...groupOfVia(person)].join(' · ')}>
                  <span>{person.via.map((via) => viaLabel(via)).join(' · ')}</span>
                  {#each groupOfVia(person) as group}<small class="mono">{group}</small>{/each}
                  {#if person.warnings.includes('awaiting_sync')}<small class="is-info" title={t('Approved recently: the next directory sync confirms the group membership.')}>{t('Sync pending')}</small>{/if}
                  {#if person.warnings.includes('missing_in_group')}<small class="is-bad">{t('Missing from the group')}</small>{/if}
                </span>
                <span class="pm-until">
                  {#if person.expires_at && progress}
                    <small class:is-warn={progress.soon} title={formatDateTime(person.expires_at)}>{t('in {days} d', { days: progress.daysLeft })}</small>
                    <span class="pm-time" class:is-soon={progress.soon} aria-hidden="true"><span style={`width: ${progress.percentLeft}%`}></span></span>
                  {:else}
                    <small class="pm-muted">{request ? t('Permanent') : '—'}</small>
                  {/if}
                </span>
                <span class="pm-actions">
                  {#if canManage && person.expires_at && request}
                    <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" disabled={extending === person.key} on:click={() => extend(person)}>+30 j</button>
                  {/if}
                  {#if canManage && person.revocable_request_ids.length}
                    <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-danger-outline" disabled={busy} on:click={() => (revoking = person)}>{t('Revoke')}</button>
                  {/if}
                </span>
              </li>
            {/each}
          </ul>
        {:else}
          <p class="pm-empty">{governedPeople.length ? t('Nobody matches this filter.') : t('Nobody reaches this folder through BornToShare yet.')}</p>
        {/if}
        {#if data.system.length}
          <div class="pm-system">
            <span><i class="bi bi-gear" aria-hidden="true"></i> {t('+ {count} expected system account(s)', { count: data.system.length })}</span>
            <button type="button" class="pm-link" aria-expanded={showSystem} on:click={() => (showSystem = !showSystem)}>{showSystem ? t('Hide') : t('Show')}</button>
          </div>
          {#if showSystem}
            <ul class="pm-system__list">
              {#each data.system as entry (entry.principal)}
                <li><span>{entry.kind === 'service' ? t('BornToShare account') : entry.name}</span><code>{entry.principal}</code><span class="pm-muted">{t(entry.rights_label)}</span></li>
              {/each}
            </ul>
          {/if}
        {/if}
      </section>
    </div>

    <div class="pm-col">
      <section class="pm-card" aria-label={t('Outside BornToShare')}>
        <header><h2>{t('Outside BornToShare')}</h2>{#if openGaps.length}<span class="pm-count is-warn">{openGaps.length}</span>{/if}</header>
        <p class="pm-muted">{t('NTFS entries that give an access without going through a request.')}</p>
        {#each openGaps as gap (gap.principal)}
          <div class="pm-gap">
            <span>
              <b>{gap.kind === 'broad' ? t('Folder open widely') : gap.name}</b>
              <small>{t('{rights}, set directly on the file server', { rights: t(gap.rights_label) })}</small>
              {#if gapPeople(gap).length}
                <span class="pm-gap__people">
                  {#each gapPeople(gap).slice(0, 4) as person (person.key)}<button type="button" class="pm-link" on:click={() => (explainFor = person.username ?? person.name)}>{person.name}</button>{/each}
                </span>
              {:else if gap.members_count}
                <small>{t('{count} member(s) without a request or a guardian', { count: gap.members_count })}</small>
              {/if}
            </span>
            {#if isAdmin}<button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" disabled={busy} on:click={() => toggleGap(gap, true)}>{t('Accept the gap')}</button>{/if}
          </div>
        {:else}
          <p class="pm-ok"><i class="bi bi-check2-circle" aria-hidden="true"></i> {t('Nothing: every access goes through BornToShare.')}</p>
        {/each}
        {#if acceptedGaps.length}
          <small class="pm-muted">{t('{count} accepted gap(s):', { count: acceptedGaps.length })}</small>
          {#each acceptedGaps as gap (gap.principal)}
            <div class="pm-accepted"><span class="mono">{gap.name}</span>{#if isAdmin}<button type="button" class="pm-link" disabled={busy} on:click={() => toggleGap(gap, false)}>{t('Report again')}</button>{/if}</div>
          {/each}
        {/if}
      </section>

      {#if data.groups.length}
        <section class="pm-card" aria-label={t('AD groups')}>
          <header><h2>{t('AD groups')}</h2></header>
          <dl class="pm-kv">
            {#each data.groups as group (group.name)}
              <div>
                <dt>{levelLabel(group.level)}</dt>
                <dd><span class="mono">{group.name}</span><small>{t('{count} member(s)', { count: group.members_count })} · {ACE_LABEL[group.ace]?.() ?? t('ACL not read')}</small></dd>
              </div>
            {/each}
          </dl>
        </section>
      {/if}

      {#if ends.length}
        <section class="pm-card" aria-label={t('Next end dates')}>
          <header><h2>{t('Next end dates')}</h2></header>
          {#each ends as person (person.key)}
            {@const request = mainRequest(person)}
            {@const progress = expiryProgress(request?.decided_at ?? null, String(person.expires_at))}
            <div class="pm-end">
              <span class={`pm-face is-${person.level}`}>{initials(person.name)}</span>
              <span class="pm-end__name"><b>{person.name}</b><span class="pm-time" class:is-soon={progress.soon} aria-hidden="true"><span style={`width: ${progress.percentLeft}%`}></span></span></span>
              <small class="pm-muted">{t('in {days} d', { days: progress.daysLeft })}</small>
              {#if canManage && request}<button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" disabled={extending === person.key} on:click={() => extend(person)}>+30 j</button>{/if}
            </div>
          {/each}
        </section>
      {/if}
    </div>
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
  open={repairAsked}
  onClose={() => (repairAsked = false)}
  onConfirm={repairAcl}
  title={t('Repair the ACL of this folder?')}
  impactItems={[t('The entries of the BornToShare groups are written again on the folder.'), t('They are then applied to all its content in the background: this can take several minutes on a large folder.')]}
  confirmLabel={t('Repair')}
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
  .pm { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(280px, 1fr); gap: 14px; align-items: start; }
  .pm-col { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
  .pm-card { display: flex; flex-direction: column; gap: 12px; min-width: 0; padding: 16px 18px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .pm-card header { display: flex; align-items: center; gap: 8px; }
  .pm-card h2 { margin: 0 auto 0 0; font-size: var(--b2s-fs-md); font-weight: 600; }
  .pm-muted { margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .mono { font-family: var(--b2s-font-mono); font-size: var(--b2s-fs-xs); }
  .pm-link { padding: 0; border: 0; background: none; color: var(--b2s-color-info-strong); font: inherit; font-size: var(--b2s-fs-sm); cursor: pointer; }
  .is-read { color: var(--b2s-color-info-strong); }
  .is-write, .is-warn { color: var(--b2s-color-warning-strong); }
  .is-bad { color: var(--b2s-color-danger-strong); }
  .is-info { color: var(--b2s-color-info-strong); }
  /* state */
  .pm-state { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 14px; align-items: center; }
  .pm-ring { position: relative; display: grid; place-items: center; width: 56px; height: 56px; border-radius: 50%; background: conic-gradient(var(--ring) var(--share), var(--b2s-color-neutral-soft) 0); --ring: var(--b2s-color-success); }
  .pm-ring.is-warn { --ring: var(--b2s-color-warning); }
  .pm-ring.is-bad { --ring: var(--b2s-color-danger); }
  .pm-ring.is-idle { --ring: var(--b2s-color-border-mid, #cdd2db); }
  .pm-ring::after { content: ''; position: absolute; inset: 6px; border-radius: 50%; background: var(--b2s-color-surface); }
  .pm-ring b { position: relative; z-index: 1; font-size: 13px; }
  .pm-state__text { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
  .pm-state__text strong { font-size: 17px; font-weight: 600; }
  .pm-state__text strong.is-ok { color: var(--b2s-color-success-strong); }
  .pm-state__text p { margin: 0; font-size: var(--b2s-fs-sm); }
  .pm-facts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; }
  .pm-facts > span { display: inline-flex; align-items: center; gap: 5px; padding: 2px 8px; border-radius: var(--b2s-radius-sm); background: var(--b2s-color-neutral-soft); font-size: var(--b2s-fs-xs); }
  .pm-facts .pm-link { font-size: var(--b2s-fs-xs); }
  .pm-note { margin: 0; font-size: var(--b2s-fs-sm); color: var(--b2s-color-text-muted); }
  .pm-note.is-bad { color: var(--b2s-color-danger); }
  /* who reaches it */
  .pm-ask { display: flex; align-items: center; gap: 8px; height: 40px; padding: 0 12px; border: 1px solid var(--b2s-color-border-mid, var(--b2s-color-border)); border-radius: var(--b2s-radius-md); }
  .pm-ask input { flex: 1; min-width: 0; border: 0; outline: 0; background: none; font: inherit; }
  .pm-answer { display: flex; flex-direction: column; gap: 10px; padding: 12px 14px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-md); background: var(--b2s-color-surface-soft, #f6f7f9); }
  .pm-answer p { margin: 0; font-size: var(--b2s-fs-sm); }
  .pm-answer .pm-link { margin-left: 6px; }
  .pm-answer.is-none { flex-direction: row; align-items: center; justify-content: space-between; }
  .pm-chain { display: flex; flex-wrap: wrap; align-items: stretch; gap: 6px; }
  .pm-step { display: flex; flex-direction: column; justify-content: center; min-width: 0; padding: 8px 12px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-md); background: var(--b2s-color-surface); }
  .pm-step b { font-size: var(--b2s-fs-sm); font-weight: 600; overflow-wrap: anywhere; }
  .pm-step small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .pm-step.is-ok { border-color: var(--b2s-color-success-border, #bfe6d1); background: var(--b2s-color-success-soft); }
  .pm-step.is-bad { border-color: var(--b2s-color-danger-border, #f0c4c4); background: var(--b2s-color-danger-soft); }
  .pm-arrow { align-self: center; color: var(--b2s-color-border-mid, #cdd2db); }
  /* path of the accesses */
  .pm-path { display: grid; grid-template-columns: minmax(150px, 0.8fr) 18px minmax(0, 1.4fr) 18px auto; gap: 8px; align-items: center; width: 100%; padding: 10px 12px; border: 1px solid var(--b2s-color-border); border-left-width: 3px; border-radius: var(--b2s-radius-md); background: none; color: inherit; font: inherit; text-align: left; cursor: pointer; }
  .pm-path.is-read { border-left-color: var(--b2s-color-info); }
  .pm-path.is-write { border-left-color: var(--b2s-color-warning); }
  .pm-path.is-outside { border-left-color: var(--b2s-color-danger); }
  .pm-path:hover, .pm-path.is-active { background: var(--b2s-color-surface-soft, #f6f7f9); }
  .pm-path.is-active { box-shadow: inset 0 0 0 1px var(--b2s-color-text); }
  .pm-path__who { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .pm-path__who b, .pm-path__group b { display: block; font-size: var(--b2s-fs-sm); }
  .pm-path__who small, .pm-path__group small { display: block; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .pm-path__group { min-width: 0; }
  .pm-path__group b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .pm-path__folder { display: inline-flex; align-items: center; gap: 6px; font-size: var(--b2s-fs-sm); white-space: nowrap; }
  .pm-path__folder i { color: var(--b2s-color-success-strong); }
  .pm-stack { display: flex; }
  .pm-face { display: inline-flex; align-items: center; justify-content: center; flex: none; width: 26px; height: 26px; margin-left: -6px; border: 2px solid var(--b2s-color-surface); border-radius: 50%; background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); font-size: 10px; font-weight: 700; }
  .pm-stack .pm-face:first-child { margin-left: 0; }
  .pm-face.is-write { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .pm-face.is-lg { width: 32px; height: 32px; margin: 0; border: 0; font-size: 11px; }
  /* people */
  .pm-tools { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .pm-search { display: flex; align-items: center; gap: 6px; flex: 1; min-width: 160px; max-width: 240px; height: 34px; padding: 0 10px; border: 1px solid var(--b2s-color-border-mid, var(--b2s-color-border)); border-radius: var(--b2s-radius-md); }
  .pm-search input { flex: 1; min-width: 0; border: 0; outline: 0; background: none; font: inherit; font-size: var(--b2s-fs-sm); }
  .pm-seg { display: flex; gap: 2px; padding: 3px; border-radius: var(--b2s-radius-md); background: var(--b2s-color-neutral-soft); }
  .pm-seg button { padding: 4px 10px; border: 0; border-radius: var(--b2s-radius-sm); background: none; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); white-space: nowrap; cursor: pointer; }
  .pm-seg button.on { background: var(--b2s-color-surface); color: var(--b2s-color-text); font-weight: 600; }
  .pm-seg span { margin-left: 5px; opacity: 0.7; }
  .pm-chip { display: inline-flex; align-items: center; gap: 4px; padding: 2px 9px; border: 0; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-text); color: #fff; font-size: var(--b2s-fs-xs); cursor: pointer; }
  .pm-rows { margin: 0; padding: 0; list-style: none; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-md); }
  .pm-rows li { display: grid; grid-template-columns: minmax(110px, 1fr) auto minmax(0, 1fr) auto auto; gap: 10px; align-items: center; padding: 10px 12px; }
  .pm-rows li + li { border-top: 1px solid var(--b2s-color-border); }
  .pm-who { display: flex; align-items: center; gap: 10px; min-width: 0; padding: 0; border: 0; background: none; color: inherit; font: inherit; text-align: left; cursor: pointer; }
  .pm-who strong { display: block; font-weight: 500; font-size: var(--b2s-fs-sm); }
  .pm-who small { display: block; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .pm-who:hover strong { text-decoration: underline; }
  .pm-level { padding: 2px 9px; border-radius: var(--b2s-radius-pill); font-size: var(--b2s-fs-xs); font-weight: 500; }
  .pm-level.is-read { background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); }
  .pm-level.is-write { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .pm-via { display: flex; flex-direction: column; gap: 2px; min-width: 0; font-size: var(--b2s-fs-xs); }
  .pm-via > * { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .pm-via .mono { color: var(--b2s-color-text-muted); }
  .pm-until { display: flex; flex-direction: column; gap: 4px; }
  .pm-time { display: block; height: 4px; overflow: hidden; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-border-soft, #e9ebf0); }
  .pm-time span { display: block; height: 4px; background: var(--b2s-color-info); }
  .pm-time.is-soon span { background: var(--b2s-color-warning); }
  .pm-actions { display: flex; justify-content: flex-end; gap: 6px; }
  .pm-empty { margin: 0; padding: 16px; border: 1px dashed var(--b2s-color-border); border-radius: var(--b2s-radius-md); color: var(--b2s-color-text-muted); text-align: center; }
  .pm-system { display: flex; align-items: center; gap: 8px; padding-top: 8px; border-top: 1px dashed var(--b2s-color-border); color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .pm-system .pm-link { margin-left: auto; }
  .pm-system__list { display: grid; gap: 4px; margin: 0; padding: 0; list-style: none; font-size: var(--b2s-fs-xs); }
  .pm-system__list li { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto; gap: 8px; }
  .pm-system__list code { color: var(--b2s-color-text-muted); }
  /* side */
  .pm-count { padding: 0 8px; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-warning-soft); font-size: var(--b2s-fs-xs); font-weight: 600; }
  .pm-gap { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; align-items: center; padding: 10px 12px; border: 1px solid var(--b2s-color-warning-border, #f3d9ad); border-radius: var(--b2s-radius-md); background: var(--b2s-color-warning-soft); }
  .pm-gap b { display: block; font-size: var(--b2s-fs-sm); overflow-wrap: anywhere; }
  .pm-gap small { display: block; color: var(--b2s-color-warning-strong); font-size: var(--b2s-fs-xs); }
  .pm-gap__people { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 2px; }
  .pm-gap__people .pm-link { font-size: var(--b2s-fs-xs); }
  .pm-ok { margin: 0; color: var(--b2s-color-success-strong); font-size: var(--b2s-fs-sm); }
  .pm-accepted { display: flex; justify-content: space-between; gap: 8px; font-size: var(--b2s-fs-sm); }
  .pm-kv { margin: 0; }
  .pm-kv div { display: grid; grid-template-columns: 96px minmax(0, 1fr); gap: 8px; padding: 8px 0; border-top: 1px solid var(--b2s-color-border); font-size: var(--b2s-fs-sm); }
  .pm-kv div:first-child { border-top: 0; }
  .pm-kv dt { color: var(--b2s-color-text-muted); }
  .pm-kv dd { display: flex; flex-direction: column; gap: 2px; margin: 0; min-width: 0; overflow-wrap: anywhere; }
  .pm-kv small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .pm-end { display: grid; grid-template-columns: 26px minmax(0, 1fr) auto auto; gap: 10px; align-items: center; }
  .pm-end .pm-face { margin: 0; border: 0; }
  .pm-end__name { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
  .pm-end__name b { font-size: var(--b2s-fs-sm); font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
