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
  import { repairStorageRootAcl } from '$lib/api/storage-root-permissions';
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
   * Storage roots › Permissions, on one surface: the state of the ACL in a sentence, an access checker,
   * the flow people -> AD groups -> folder (bands sized by members, click = filter), the people,
   * the entries set outside BornToShare and the expected system accounts.
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
      toast.error(error?.message ?? t('Unable to repair the ACL.'));
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
  $: maxMembers = Math.max(1, ...bands.map((b) => b.members.length));
  const bandHeight = (count: number) => 34 + Math.round((Math.min(count, maxMembers) / maxMembers) * 42);

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
</script>

{#if loading && !data}
  <LoadingState block>{t('Reading the permissions…')}</LoadingState>
{:else if error && !data}
  <InlineAlert tone="error">{error}</InlineAlert>
{:else if data && state}
  <div class="pm">
    <!-- the state in one sentence -->
    <section class="pm-state" aria-label={t('State of the ACL')}>
      <p class="pm-sentence">
        <span class={`pm-word is-${state.tone}`}>{state.word()}</span>
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
          {#if openGaps.length}
            <span class="is-write">{t('{count} entry(ies) set outside BornToShare.', { count: openGaps.length })}</span>
          {/if}
        {/if}
      </p>
      {#if data.propagation?.state === 'running'}
        <p class="pm-propagation"><span class="spinner-border spinner-border-sm" aria-hidden="true"></span> {t('The rights are being applied to the content of the folder. On a big folder it can take a while.')}</p>
      {:else if data.propagation?.state === 'failed'}
        <p class="pm-propagation is-bad"><i class="bi bi-exclamation-triangle" aria-hidden="true"></i> {t('The rights could not reach all the content of the folder: some people may be refused inside. Use « Repair the ACL ».')}</p>
      {/if}
      <div class="pm-meta">
        {#if (canManage || isAdmin) && data.summary.groups > 0}
          <button type="button" class="pm-textbtn" disabled={repairing} on:click={() => (repairAsked = true)}>{repairing ? t('Repairing…') : t('Repair the ACL')}</button> ·
        {/if}
        {#if data.acl_scanned_at}
          <span>{t('ACL read {ago}', { ago: timeAgo(data.acl_scanned_at) })} · {t('{count} entries', { count: data.acl_entries })}</span>
        {/if}
        {#if data.snapshot_at}<span>· {t('directory synchronised {ago}', { ago: timeAgo(data.snapshot_at) })}</span>{/if}
        {#if data.inheritance?.known}
          <span class="pm-inherit" class:is-broken={data.inheritance.broken}>
            · <i class={`bi ${data.inheritance.broken ? 'bi-scissors' : 'bi-diagram-3'}`} aria-hidden="true"></i>
            {data.inheritance.broken ? t('inheritance broken') : t('inherits from the parent folder')}
            {#if isAdmin}<button type="button" class="pm-textbtn" on:click={onToggleInheritance}>{data.inheritance.broken ? t('Restore') : t('Break')}</button>{/if}
          </span>
        {/if}
        <button type="button" class="pm-textbtn pm-export" disabled={!data.people.length} on:click={exportCsv}>
          <i class="bi bi-download" aria-hidden="true"></i>{t('Export')}
        </button>
      </div>
    </section>

    <!-- checker -->
    <section class="pm-check" aria-label={t('Check the access of a person')}>
      <label class="pm-check__field">
        <i class="bi bi-search" aria-hidden="true"></i>
        <span class="pm-check__ask">{t('Who reaches it?')}</span>
        <input type="search" bind:value={query} placeholder={t('Type a login, e.g. paul.martin')} autocomplete="off" aria-label={t('Username')} />
      </label>
      <div class="pm-check__answer" aria-live="polite">
        {#if checking}
          <span class="pm-muted">{t('Checking…')}</span>
        {:else if checked?.found}
          <span class={`pm-dot is-${checked.person.level}`} aria-hidden="true"></span>
          <strong>{checked.person.name}</strong>
          <span>{checked.person.level === 'write' ? t('modifies this folder') : t('reads this folder')}</span>
          <span class="pm-muted">—</span>
          {#each checked.steps as step, index}
            {#if index}<span class="pm-muted" aria-hidden="true">→</span>{/if}
            {#if step.kind === 'request'}
              <span class="pm-chip">{t('{code} validated', { code: step.code })}{step.approver ? ` · ${step.approver}` : ''}</span>
            {:else if step.kind === 'membership'}
              <code class="pm-chip">{step.group}</code>
            {:else}
              <span class="pm-chip">{step.rights_label ? t(step.rights_label) : t('No ACE')}</span>
            {/if}
          {/each}
          {#if checked.person.expires_at}
            <span class="is-write">· {t('ends {date}', { date: formatDate(checked.person.expires_at) })}</span>
          {/if}
          <button type="button" class="pm-textbtn pm-push" on:click={() => checked?.found && (explainFor = checked.person.username ?? checked.person.name)}>{t('Details')}</button>
        {:else if checkedMissing}
          <span class="pm-dot is-none" aria-hidden="true"></span>
          <span>
            {checkedMissing.known_in_directory
              ? t('{name} has no access to this folder', { name: checkedMissing.display_name || checkedMissing.username })
              : t('No directory account named {name}', { name: checkedMissing.username })}
          </span>
        {:else}
          <span class="pm-muted">{t('The answer shows here, with the path request → AD group → folder.')}</span>
        {/if}
      </div>
    </section>

    <!-- flow -->
    {#if bands.length}
      <section class="pm-flow" aria-label={t('From the people to the folder')}>
        <h2>{t('From the people to the folder')}</h2>
        <div class="pm-flow__grid">
          <div class="pm-flow__bands">
            {#each bands as band (band.key)}
              <button
                type="button"
                class={`pm-band is-${band.managed ? band.level ?? 'read' : 'outside'}`}
                class:is-active={groupFilter === band.group}
                style={`height: ${bandHeight(band.members.length)}px`}
                aria-pressed={groupFilter === band.group}
                title={t('Show only its members')}
                on:click={() => toggleGroup(band.group)}
              >
                <span class="pm-band__people">
                  <span class="pm-stack">
                    {#each band.members.slice(0, 5) as member (member.key)}<span class="pm-face">{initials(member.name)}</span>{/each}
                  </span>
                  <span>{band.members.length ? t('{count} person(s)', { count: band.members.length }) : t('No member yet')}</span>
                </span>
                <span class="pm-band__group">
                  <code>{band.group}</code>
                  <small>
                    {band.managed ? t('managed') : t('outside BornToShare')} ·
                    {band.state === 'ok' ? t('ACE in place') : band.state === 'missing' ? t('ACE missing') : band.state === 'mismatch' ? t('Unexpected rights') : band.rights ? t(band.rights) : ''}
                  </small>
                </span>
              </button>
            {/each}
          </div>
          <div class="pm-flow__folder">
            <small class="pm-mono">{data.root_path ?? ''}</small>
            <strong>{rootName}</strong>
            <small>{data.inheritance?.broken ? t('inheritance broken') : t('folder, subfolders and files')}</small>
          </div>
        </div>
      </section>
    {/if}

    <!-- people -->
    <section class="pm-people" aria-label={t('Who has access')}>
      <div class="pm-people__head">
        <h2>{t('Who has access')}</h2>
        <div class="pm-filters" role="group" aria-label={t('Filter by level')}>
          <button type="button" class:is-active={filter === 'all'} on:click={() => (filter = 'all')}>{t('All')} {governedPeople.length}</button>
          <button type="button" class:is-active={filter === 'read'} on:click={() => (filter = 'read')}>{t('Read')} {data.summary.read}</button>
          <button type="button" class:is-active={filter === 'write'} on:click={() => (filter = 'write')}>{t('Modify')} {data.summary.write}</button>
          <button type="button" class:is-active={filter === 'ending'} on:click={() => (filter = 'ending')}>{t('Ending within 30 days')} {data.summary.expiring_30d}</button>
          {#if groupFilter}
            <button type="button" class="is-active is-group" on:click={() => (groupFilter = null)}>{groupFilter} <i class="bi bi-x" aria-hidden="true"></i></button>
          {/if}
        </div>
        <label class="pm-search">
          <i class="bi bi-search" aria-hidden="true"></i>
          <span class="visually-hidden">{t('Search a person')}</span>
          <input type="search" bind:value={search} placeholder={t('Search a person')} />
        </label>
      </div>

      {#if people.length === 0 && !openGaps.length}
        <p class="pm-empty">{governedPeople.length ? t('Nobody matches this filter.') : t('Nobody reaches this folder through BornToShare yet.')}</p>
      {/if}
      <ul class="pm-rows">
        {#each people as person (person.key)}
          {@const request = mainRequest(person)}
          {@const progress = person.expires_at ? expiryProgress(request?.decided_at ?? null, person.expires_at) : null}
          <li class="pm-row">
            <button type="button" class="pm-who" on:click={() => (explainFor = person.username ?? person.name)}>
              <span class={`pm-face is-lg is-${person.level}`}>{initials(person.name)}</span>
              <span><strong>{person.name}</strong><small>{person.username ?? ''}</small></span>
            </button>
            <span class={`pm-level is-${person.level}`}>{levelLabel(person.level)}</span>
            <span class="pm-via">
              {#each person.via as via}<span class={`pm-chip is-${via.kind}`}>{viaLabel(via)}</span>{/each}
              {#each groupOfVia(person) as group}<code>{group}</code>{/each}
              {#if person.warnings.includes('awaiting_sync')}<span class="pm-chip is-info" title={t('Approved recently: the next directory sync confirms the group membership.')}>{t('Sync pending')}</span>{/if}
              {#if person.warnings.includes('missing_in_group')}<span class="pm-chip is-outside">{t('Missing from the group')}</span>{/if}
            </span>
            <span class="pm-until">
              {#if person.expires_at && progress}
                <span title={formatDateTime(person.expires_at)}>{formatDate(person.expires_at)} · {t('in {days} d', { days: progress.daysLeft })}</span>
                <span class="pm-time" class:is-soon={progress.soon} aria-hidden="true"><span style={`width: ${progress.percentLeft}%`}></span></span>
              {:else}
                <span class="pm-muted">{request ? t('Permanent') : '—'}</span>
              {/if}
            </span>
            <span class="pm-actions">
              {#if canManage && person.revocable_request_ids.length}
                <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-danger-outline" disabled={busy} on:click={() => (revoking = person)}>{t('Revoke')}</button>
              {/if}
            </span>
          </li>
        {/each}

        <!-- entries set by hand on the file server, in the list -->
        {#each openGaps as gap (gap.principal)}
          <li class="pm-row is-gap">
            <span class="pm-who is-static">
              <span class="pm-face is-lg is-outside"><i class="bi bi-exclamation-lg" aria-hidden="true"></i></span>
              <span>
                <strong>{gap.kind === 'broad' ? t('Folder open widely') : gap.name}</strong>
                <small>{t('{rights}, set directly on the file server', { rights: t(gap.rights_label) })}</small>
              </span>
            </span>
            <span class="pm-via">
              {#each gapPeople(gap).slice(0, 4) as person (person.key)}
                <button type="button" class="pm-chip is-outside" on:click={() => (explainFor = person.username ?? person.name)}>{person.name}</button>
              {/each}
              {#if gap.members_count}<span class="pm-muted">{t('{count} member(s) without a request or a guardian', { count: gap.members_count })}</span>{/if}
            </span>
            <span class="pm-actions">
              {#if isAdmin}
                <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" disabled={busy} on:click={() => toggleGap(gap, true)}>{t('Accept the gap')}</button>
              {/if}
            </span>
          </li>
        {/each}
      </ul>

      <p class="pm-foot">
        {#if acceptedGaps.length}
          {t('{count} accepted gap(s):', { count: acceptedGaps.length })}
          {#each acceptedGaps as gap, i (gap.principal)}
            {i ? ', ' : ''}<span class="pm-mono">{gap.name}</span>{#if isAdmin} <button type="button" class="pm-textbtn" disabled={busy} on:click={() => toggleGap(gap, false)}>{t('Report again')}</button>{/if}
          {/each}
          <br />
        {/if}
        {#if data.system.length}
          {t('+ {count} expected system account(s)', { count: data.system.length })}
          <button type="button" class="pm-textbtn" aria-expanded={showSystem} on:click={() => (showSystem = !showSystem)}>{showSystem ? t('Hide') : t('Show')}</button>
        {/if}
      </p>
      {#if showSystem}
        <ul class="pm-system">
          {#each data.system as entry (entry.principal)}
            <li><span>{entry.kind === 'service' ? t('BornToShare account') : entry.name}</span><code>{entry.principal}</code><span class="pm-muted">{t(entry.rights_label)}</span></li>
          {/each}
        </ul>
      {/if}
    </section>
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
  .pm-propagation { margin: 8px 0 0; font-size: 13px; color: var(--b2s-color-text-muted); }
  .pm-propagation.is-bad { color: var(--b2s-color-danger); }
  .pm {
    display: grid;
    gap: 28px;
  }

  h2 {
    margin: 0;
    font-size: var(--b2s-fs-md);
    font-weight: 600;
  }

  .pm-muted {
    color: var(--b2s-color-text-muted);
  }

  .pm-mono,
  code {
    font-family: var(--b2s-font-mono);
    font-size: var(--b2s-fs-xs);
    overflow-wrap: anywhere;
  }

  .is-read { color: var(--b2s-color-info-strong); }
  .is-write { color: var(--b2s-color-warning-strong); }
  .is-bad { color: var(--b2s-color-danger-strong); }

  .pm-textbtn {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 0;
    border: 0;
    background: none;
    color: var(--b2s-color-info-strong);
    font: inherit;
    cursor: pointer;
  }

  .pm-textbtn:disabled {
    color: var(--b2s-color-text-faint);
    cursor: default;
  }

  /* state */
  .pm-state {
    display: grid;
    gap: 8px;
  }

  .pm-sentence {
    max-width: 920px;
    margin: 0;
    font-size: 22px;
    font-weight: 500;
    line-height: 1.4;
    letter-spacing: -0.01em;
  }

  .pm-word {
    font-weight: 700;
  }

  .pm-word.is-ok { color: var(--b2s-color-success-strong); }
  .pm-word.is-warn { color: var(--b2s-color-warning-strong); }
  .pm-word.is-bad { color: var(--b2s-color-danger-strong); }
  .pm-word.is-idle { color: var(--b2s-color-text-muted); }

  .pm-meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
  }

  .pm-inherit.is-broken {
    color: var(--b2s-color-warning-strong);
  }

  .pm-export {
    margin-left: auto;
  }

  /* checker */
  .pm-check {
    display: grid;
    gap: 10px;
  }

  .pm-check__field {
    display: flex;
    align-items: center;
    gap: 12px;
    height: 50px;
    padding: 0 16px;
    border: 1px solid var(--b2s-color-border);
    border-radius: 14px;
    background: var(--b2s-color-surface);
    box-shadow: 0 6px 24px rgba(15, 26, 58, 0.06);
    color: var(--b2s-color-text-muted);
  }

  .pm-check__field:focus-within {
    border-color: var(--b2s-color-info);
  }

  .pm-check__ask {
    white-space: nowrap;
  }

  .pm-check__field input {
    flex: 1;
    min-width: 0;
    border: 0;
    outline: 0;
    background: transparent;
    color: var(--b2s-color-text);
    font: inherit;
    font-size: var(--b2s-fs-md);
  }

  .pm-check__answer {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    min-height: 28px;
    padding: 0 6px;
    font-size: var(--b2s-fs-sm);
  }

  .pm-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--b2s-color-success);
  }

  .pm-dot.is-none {
    background: var(--b2s-color-danger);
  }

  .pm-push {
    margin-left: auto;
  }

  .pm-chip {
    padding: 2px 8px;
    border: 0;
    border-radius: 6px;
    background: var(--b2s-color-neutral-soft);
    color: var(--b2s-color-text-strong);
    font: inherit;
    font-size: var(--b2s-fs-xs);
  }

  button.pm-chip {
    cursor: pointer;
  }

  .pm-chip.is-ad_only,
  .pm-chip.is-outside { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .pm-chip.is-info { background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); }

  /* flow */
  .pm-flow {
    display: grid;
    gap: 12px;
  }

  .pm-flow__grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(180px, 0.32fr);
    align-items: stretch;
  }

  .pm-flow__bands {
    display: grid;
    gap: 8px;
  }

  .pm-band {
    display: grid;
    grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr);
    align-items: stretch;
    padding: 0;
    border: 0;
    border-radius: 12px 0 0 12px;
    background: transparent;
    color: var(--b2s-color-text);
    font: inherit;
    text-align: left;
    cursor: pointer;
    transition: transform 0.12s ease, box-shadow 0.12s ease;
  }

  .pm-band:hover,
  .pm-band.is-active {
    box-shadow: 0 0 0 2px var(--b2s-color-info);
  }

  .pm-band__people {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 0 14px;
    border-radius: 12px 0 0 12px;
    font-size: var(--b2s-fs-sm);
  }

  .pm-band__group {
    display: grid;
    align-content: center;
    gap: 2px;
    padding: 0 14px;
  }

  .pm-band__group small {
    color: var(--b2s-color-text-soft);
    font-size: var(--b2s-fs-xs);
  }

  .pm-band.is-read .pm-band__people { background: linear-gradient(90deg, var(--b2s-color-surface), var(--b2s-color-info-soft)); color: var(--b2s-color-info-strong); }
  .pm-band.is-read .pm-band__group { background: var(--b2s-color-info-soft); }
  .pm-band.is-write .pm-band__people { background: linear-gradient(90deg, var(--b2s-color-surface), var(--b2s-color-warning-soft)); color: var(--b2s-color-warning-strong); }
  .pm-band.is-write .pm-band__group { background: var(--b2s-color-warning-soft); }
  .pm-band.is-outside .pm-band__people,
  .pm-band.is-outside .pm-band__group {
    background: repeating-linear-gradient(135deg, var(--b2s-color-surface), var(--b2s-color-surface) 6px, var(--b2s-color-warning-soft) 6px, var(--b2s-color-warning-soft) 12px);
    color: var(--b2s-color-warning-strong);
  }

  .pm-flow__folder {
    display: grid;
    align-content: center;
    gap: 6px;
    padding: 16px 18px;
    border-radius: 0 14px 14px 0;
    background: var(--b2s-topbar-bg);
    color: var(--b2s-color-surface);
  }

  .pm-flow__folder small {
    color: #c7d2fe;
    font-size: var(--b2s-fs-xs);
  }

  .pm-flow__folder strong {
    font-size: var(--b2s-fs-md);
    overflow-wrap: anywhere;
  }

  .pm-stack {
    display: flex;
  }

  .pm-face {
    width: 26px;
    height: 26px;
    flex: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    margin-left: -7px;
    border: 2px solid var(--b2s-color-surface);
    border-radius: 50%;
    background: var(--b2s-color-primary-soft);
    color: var(--b2s-color-heading);
    font-size: 10px;
    font-weight: 700;
  }

  .pm-stack .pm-face:first-child { margin-left: 0; }

  .pm-face.is-lg {
    width: 32px;
    height: 32px;
    margin: 0;
    border: 0;
    font-size: 11px;
  }

  .pm-face.is-read { background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); }
  .pm-face.is-write { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .pm-face.is-outside { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }

  /* people */
  .pm-people {
    display: grid;
  }

  .pm-people__head {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 12px;
    padding-bottom: 12px;
  }

  .pm-filters {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .pm-filters button {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 4px 10px;
    border: 1px solid var(--b2s-color-border);
    border-radius: var(--b2s-radius-pill);
    background: var(--b2s-color-surface);
    color: var(--b2s-color-text-soft);
    font: inherit;
    font-size: var(--b2s-fs-xs);
    cursor: pointer;
  }

  .pm-filters button.is-active {
    border-color: var(--b2s-topbar-bg);
    background: var(--b2s-topbar-bg);
    color: var(--b2s-color-surface);
  }

  .pm-filters .is-group {
    font-family: var(--b2s-font-mono);
  }

  .pm-search {
    display: flex;
    align-items: center;
    gap: 8px;
    height: 34px;
    min-width: 220px;
    margin-left: auto;
    padding: 0 12px;
    border: 1px solid var(--b2s-color-border);
    border-radius: var(--b2s-radius-sm);
    color: var(--b2s-color-text-muted);
  }

  .pm-search input {
    flex: 1;
    min-width: 0;
    border: 0;
    outline: 0;
    background: transparent;
    font: inherit;
    font-size: var(--b2s-fs-sm);
  }

  .pm-empty {
    margin: 0;
    padding: 16px 0;
    color: var(--b2s-color-text-muted);
  }

  .pm-rows {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .pm-row {
    display: grid;
    grid-template-columns: minmax(200px, 1.2fr) 110px minmax(0, 1.6fr) 170px 90px;
    align-items: center;
    gap: 14px;
    padding: 10px 6px;
    border-top: 1px solid var(--b2s-color-border-soft);
  }

  .pm-row:hover {
    background: var(--b2s-color-surface-soft);
  }

  .pm-row.is-gap {
    grid-template-columns: minmax(200px, 1.2fr) minmax(0, 1.6fr) auto;
    border-top: 1px dashed var(--b2s-color-warning);
    border-bottom: 1px dashed var(--b2s-color-warning);
    background: var(--b2s-color-warning-soft);
  }

  .pm-who {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
    padding: 0;
    border: 0;
    background: none;
    font: inherit;
    text-align: left;
    cursor: pointer;
  }

  .pm-who.is-static {
    cursor: default;
  }

  .pm-who strong,
  .pm-who small {
    display: block;
  }

  .pm-who strong {
    color: var(--b2s-color-text);
    font-weight: 600;
  }

  button.pm-who:hover strong {
    color: var(--b2s-color-info-strong);
  }

  .pm-who small {
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
  }

  .pm-level {
    justify-self: start;
    padding: 2px 8px;
    border-radius: 6px;
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
    min-width: 0;
    font-size: var(--b2s-fs-xs);
  }

  .pm-until {
    display: grid;
    gap: 4px;
    font-size: var(--b2s-fs-sm);
    white-space: nowrap;
  }

  .pm-time {
    width: 120px;
    height: 4px;
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

  .pm-actions {
    justify-self: end;
  }

  .pm-foot {
    margin: 14px 6px 0;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
    line-height: 1.8;
  }

  .pm-system {
    display: grid;
    gap: 6px;
    margin: 8px 0 0;
    padding: 0 6px;
    list-style: none;
    font-size: var(--b2s-fs-xs);
  }

  .pm-system li {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
  }

  @media (max-width: 1000px) {
    .pm-row,
    .pm-row.is-gap {
      grid-template-columns: 1fr;
    }

    .pm-actions {
      justify-self: start;
    }

    .pm-flow__grid,
    .pm-band {
      grid-template-columns: 1fr;
    }

    .pm-flow__folder {
      border-radius: 0 0 14px 14px;
    }
  }
</style>
