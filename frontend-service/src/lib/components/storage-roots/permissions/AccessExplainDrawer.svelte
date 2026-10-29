<script lang="ts">
  import Drawer from '$lib/components/ui/Drawer.svelte';
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import ConfirmActionModal from '$lib/components/ui/ConfirmActionModal.svelte';
  import { t } from '$lib/i18n';
  import { formatDate, formatDateTime, timeAgo } from '$lib/utils/format';
  import { reportUiError } from '$lib/errors';
  import { toast } from '$lib/stores/toast';
  import { bulkDecision } from '$lib/api/access-requests';
  import { explainStorageRootAccess, extendAccess, notFound, type AccessExplanation } from '$lib/api/storage-root-permissions';
  import { expiryProgress, levelLabel } from './permissions-format';

  /** « Why does this person reach the folder? »: request -> AD group -> ACE -> effective level, with its actions */
  export let open = false;
  export let rootId: number | null = null;
  export let username: string | null = null;
  export let canManage = false;
  export let onClose: () => void = () => {};
  export let onChanged: () => void = () => {};

  let explanation: AccessExplanation | null = null;
  let loading = false;
  let busy = false;
  let confirmRevoke = false;
  let loadedFor = '';

  $: key = open && rootId && username ? `${rootId}:${username}` : '';
  $: if (key && key !== loadedFor) void load(key);

  async function load(target: string) {
    loadedFor = target;
    loading = true;
    explanation = null;
    try {
      explanation = await explainStorageRootAccess(fetch, Number(rootId), String(username));
    } catch (error: unknown) {
      reportUiError(error, t('Unable to explain this access.'), 'permissions.explain');
    } finally {
      loading = false;
    }
  }

  $: person = explanation?.found ? explanation.person : null;
  $: missing = notFound(explanation);
  $: requestVia = person?.via.find((v) => v.kind === 'request' && v.level === person?.level) as
    | Extract<NonNullable<typeof person>['via'][number], { kind: 'request' }>
    | undefined;
  $: progress = person?.expires_at ? expiryProgress(requestVia?.decided_at ?? null, person.expires_at) : null;

  async function extend() {
    if (!requestVia) return;
    busy = true;
    try {
      const result = await extendAccess(fetch, requestVia.request_id, 30);
      toast.success(t('Access extended until {date}.', { date: formatDate(result.expires_at ?? '') }));
      loadedFor = '';
      onChanged();
    } catch (error: unknown) {
      reportUiError(error, t('Unable to extend this access.'), 'permissions.extend');
    } finally {
      busy = false;
    }
  }

  async function revoke() {
    confirmRevoke = false;
    if (!person?.revocable_request_ids.length) return;
    busy = true;
    try {
      const result = await bulkDecision(fetch, person.revocable_request_ids, 'revoke');
      if (Number(result?.failed_ids?.length ?? 0) > 0) throw new Error(String(Object.values(result?.failed_reasons ?? {})[0] ?? ''));
      toast.success(t('Access revoked: {name} is removed from the AD group.', { name: person.name }));
      onClose();
      onChanged();
    } catch (error: unknown) {
      reportUiError(error, t('Revocation failed.'), 'permissions.revoke');
    } finally {
      busy = false;
    }
  }
</script>

<Drawer
  {open}
  {onClose}
  iconClass="bi bi-person-lock"
  title={person?.name ?? (missing ? missing.display_name || missing.username : username ?? t('Access'))}
  subtitle={person?.username ?? null}
  ariaLabelledby="access-explain-title"
>
  <svelte:fragment slot="header-meta">
    {#if person?.level}
      <StatusBadge compact showDot={false} variant={person.level === 'write' ? 'warning' : 'info'} label={levelLabel(person.level)} />
    {/if}
    {#if explanation?.snapshot_at}
      <StatusBadge compact showDot={false} variant="success" label={t('Directory read {ago}', { ago: timeAgo(explanation.snapshot_at) })} />
    {/if}
  </svelte:fragment>

  {#if loading}
    <LoadingState />
  {:else if missing}
    <InlineAlert tone="info">
      {missing.known_in_directory
        ? t('{name} has no access to this folder: no request in force, no group on its ACL.', { name: missing.display_name || missing.username })
        : t('No directory account named {name}.', { name: missing.username })}
    </InlineAlert>
  {:else if person}
    <div class="ax">
      <h3>{t('Why {name} has access', { name: person.name })}</h3>
      <ol class="ax__steps">
        {#each explanation?.found ? explanation.steps : [] as step, index}
          <li>
            <span class="ax__dot">{index + 1}</span>
            <div>
              {#if step.kind === 'request'}
                <strong>{t('Request {code} approved', { code: step.code })}</strong>
                <span>
                  {step.requester ? t('Requested by {name}', { name: step.requester }) : t('Request')}{step.approver ? ` · ${t('approved by {name}', { name: step.approver })}` : ''}
                </span>
                <small>{formatDateTime(step.decided_at ?? '')}</small>
              {:else if step.kind === 'membership'}
                <strong>{t('Member of {group}', { group: step.group })}</strong>
                <span>
                  {#if !step.managed}
                    {t('Group put on the folder outside BornToShare.')}
                  {:else if step.outside_request}
                    {t('Added to the AD group directly, without a request.')}
                  {:else}
                    {t('Added to the AD group by the worker')}{step.ou ? `, ${t('in {ou}', { ou: step.ou })}` : ''}.
                  {/if}
                  {#if step.nested}{' '}{t('Through a nested group.')}{/if}
                </span>
              {:else}
                <strong>{step.rights_label ? t(step.rights_label) : t('No ACE')} {t('on the folder')}</strong>
                <span>
                  {#if step.state === 'missing'}
                    {t('The ACE of the group is missing from the folder: approve a request again to put it back.')}
                  {:else if step.state === 'mismatch'}
                    {t('The ACE of the group does not have the expected rights.')}
                  {:else}
                    {step.inherited_scope ? t('This folder, its subfolders and files.') : t('This folder only.')}
                  {/if}
                </span>
                <small>{t('Present at the last ACL read')}{explanation?.found && explanation.acl_scanned_at ? `, ${timeAgo(explanation.acl_scanned_at)}` : ''}</small>
              {/if}
            </div>
          </li>
        {/each}
        <li class="is-final">
          <span class="ax__dot">✓</span>
          <div>
            <strong>{t('Effective access: {level}', { level: levelLabel(person.level).toLowerCase() })}</strong>
            <span>{t('The highest level among all the ways above.')}</span>
          </div>
        </li>
      </ol>

      {#if person.warnings.includes('awaiting_sync')}
        <InlineAlert tone="info">{t('Approved recently: the next directory sync confirms the group membership.')}</InlineAlert>
      {:else if person.warnings.includes('missing_in_group')}
        <InlineAlert tone="warning">{t('Approved, but not found in the AD group at the last sync.')}</InlineAlert>
      {/if}

      {#if person.expires_at && progress}
        <div class="ax__expiry" class:is-soon={progress.soon}>
          <strong>{t('Ends on {date}, in {days} days', { date: formatDate(person.expires_at), days: progress.daysLeft })}</strong>
          <div class="ax__bar" aria-hidden="true"><span style={`width: ${progress.percentLeft}%`}></span></div>
          <small>{t('On that date BornToShare removes {name} from the group: the folder closes at the next sign-in.', { name: person.name })}</small>
        </div>
      {/if}

      {#if explanation?.found && explanation.other_roots.length}
        <section class="ax__others">
          <h4>{t('Other folders of {name}', { name: person.name })}</h4>
          {#each explanation.other_roots as other (other.storage_root_id)}
            <a href={`/storage-roots?selected=${other.storage_root_id}`}>
              <span>{other.name}</span><strong class:is-write={other.level === 'write'}>{levelLabel(other.level)}</strong>
            </a>
          {/each}
        </section>
      {/if}
    </div>
  {/if}

  <svelte:fragment slot="footer">
    {#if person && canManage}
      {#if person.revocable_request_ids.length}
        <button type="button" class="b2s-btn b2s-btn-danger-outline" disabled={busy} on:click={() => (confirmRevoke = true)}>
          <i class="bi bi-person-x" aria-hidden="true"></i>{t('Revoke')}
        </button>
      {/if}
      {#if requestVia?.expires_at}
        <button type="button" class="b2s-btn b2s-btn-primary" disabled={busy} on:click={extend}>
          <i class="bi bi-calendar-plus" aria-hidden="true"></i>{t('Extend by 30 days')}
        </button>
      {/if}
    {/if}
  </svelte:fragment>
</Drawer>

<ConfirmActionModal
  open={confirmRevoke}
  onClose={() => (confirmRevoke = false)}
  onConfirm={revoke}
  title={t('Revoke the access of {name}?', { name: person?.name ?? '' })}
  impactItems={[t('{name} is removed from the AD group by the worker.', { name: person?.name ?? '' }), t('The group and its ACL stay on the folder for the other members.')]}
  confirmLabel={t('Revoke')}
/>

<style>
  .ax {
    display: grid;
    gap: 18px;
  }

  .ax h3 {
    margin: 0;
    font-size: var(--b2s-fs-md);
    font-weight: 600;
  }

  .ax__steps {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .ax__steps li {
    position: relative;
    display: grid;
    grid-template-columns: 32px minmax(0, 1fr);
    gap: 12px;
    padding-bottom: 18px;
  }

  .ax__steps li:not(:last-child)::before {
    content: '';
    position: absolute;
    left: 15px;
    top: 34px;
    bottom: 2px;
    width: 2px;
    background: var(--b2s-color-border-soft);
  }

  .ax__dot {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: var(--b2s-topbar-bg);
    color: var(--b2s-color-surface);
    font-size: var(--b2s-fs-sm);
    font-weight: 700;
  }

  .is-final .ax__dot {
    background: var(--b2s-color-info-soft);
    color: var(--b2s-color-info-strong);
  }

  .ax__steps div > strong,
  .ax__steps div > span,
  .ax__steps div > small {
    display: block;
  }

  .ax__steps div > strong {
    font-weight: 600;
  }

  .ax__steps div > span {
    color: var(--b2s-color-text-soft);
  }

  .ax__steps div > small {
    margin-top: 2px;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
  }

  .ax__expiry {
    display: grid;
    gap: 8px;
    padding: 14px 16px;
    border: 1px solid var(--b2s-color-info-border);
    border-radius: var(--b2s-radius-md);
    background: var(--b2s-color-info-soft);
  }

  .ax__expiry.is-soon {
    border-color: var(--b2s-color-warning-border);
    background: var(--b2s-color-warning-soft);
  }

  .ax__expiry small {
    color: var(--b2s-color-text-soft);
    font-size: var(--b2s-fs-xs);
  }

  .ax__bar {
    height: 6px;
    border-radius: var(--b2s-radius-pill);
    background: var(--b2s-color-border-soft);
    overflow: hidden;
  }

  .ax__bar span {
    display: block;
    height: 6px;
    background: var(--b2s-color-info);
  }

  .is-soon .ax__bar span {
    background: var(--b2s-color-warning);
  }

  .ax__others {
    display: grid;
    gap: 8px;
  }

  .ax__others h4 {
    margin: 0;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }

  .ax__others a {
    display: flex;
    justify-content: space-between;
    padding: 10px 12px;
    border-radius: var(--b2s-radius-sm);
    background: var(--b2s-color-surface-soft);
    color: var(--b2s-color-text);
    text-decoration: none;
  }

  .ax__others strong {
    color: var(--b2s-color-info-strong);
    font-weight: 600;
  }

  .ax__others strong.is-write {
    color: var(--b2s-color-warning-strong);
  }
</style>
