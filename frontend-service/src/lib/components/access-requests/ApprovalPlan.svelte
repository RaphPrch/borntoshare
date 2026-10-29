<script lang="ts">
  import { t } from '$lib/i18n';
  import type { ApprovalPreview, ApprovalPreviewItem } from '$lib/api/access-requests';

  /** What the approval does, step by step: before (« will ») or after it succeeded (« done ») */
  export let preview: ApprovalPreview;
  export let done = false;
  /** Outcome of the group step read from the provisioning log, once applied: created, reused, adopted… */
  export let groupOutcome: string | null = null;

  $: who = preview.principal?.display || preview.principal?.username || t('the requester');

  function groupLine(item: ApprovalPreviewItem): string {
    const action = done && groupOutcome ? groupOutcome : item.group_action;
    if (action === 'create' || action === 'created' || action === 'recreated')
      return done ? t('Created in {ou}', { ou: item.target_ou_dn ?? '—' }) : t('Will be created in {ou}', { ou: item.target_ou_dn ?? '—' });
    if (action === 'adopt' || action === 'adopted') return done ? t('Existing group adopted') : t('An existing group will be adopted');
    return t('Already exists, reused');
  }

  const aclLabel = (item: ApprovalPreviewItem) => (item.acl === 'modify' ? t('Modify') : t('Read and execute'));
</script>

<div class="ap" class:is-done={done}>
  {#each preview.items as item (item.id)}
    <ol class="ap__steps">
      <li class:has-problem={item.problems.length > 0}>
        <i class="bi bi-people" aria-hidden="true"></i>
        <div>
          <strong>{t('AD group')} <span class="ap__mono">{item.group_name ?? '—'}</span></strong>
          <span>{groupLine(item)}{#if item.identity_source_name}{' · '}{t('via {source}', { source: item.identity_source_name })}{/if}</span>
        </div>
      </li>
      <li>
        <i class="bi bi-person-plus" aria-hidden="true"></i>
        <div>
          <strong>{done ? t('{who} added to the group', { who }) : t('{who} is added to the group', { who })}</strong>
          <span>{t('Done by a worker on a domain controller of the identity source')}</span>
        </div>
      </li>
      <li>
        <i class="bi bi-shield-check" aria-hidden="true"></i>
        <div>
          <strong>{t('NTFS permission: {right}', { right: aclLabel(item) })}</strong>
          <span>
            {#if item.root_path}<span class="ap__mono">{item.root_path}</span>{' · '}{/if}{t('this folder, subfolders and files')}
          </span>
        </div>
      </li>
    </ol>
    {#if item.problems.length}
      <ul class="ap__problems">
        {#each item.problems as problem (problem.code)}<li><i class="bi bi-x-octagon" aria-hidden="true"></i>{t(problem.message)}</li>{/each}
      </ul>
    {/if}
  {/each}

  {#each preview.warnings as warning (warning.code)}
    <p class="ap__warning"><i class="bi bi-exclamation-triangle" aria-hidden="true"></i>{t(warning.message)}</p>
  {/each}

  {#if done}
    <p class="ap__note">
      <i class="bi bi-info-circle" aria-hidden="true"></i>
      {t('{who} must sign out of Windows and sign in again for the new group to apply.', { who })}
    </p>
  {/if}
</div>

<style>
  .ap {
    display: grid;
    gap: 10px;
  }

  .ap__steps {
    display: grid;
    gap: 0;
    margin: 0;
    padding: 0;
    list-style: none;
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-md);
    background: var(--b2s-color-surface);
  }

  .ap__steps li {
    display: grid;
    grid-template-columns: 28px minmax(0, 1fr);
    gap: 10px;
    align-items: start;
    padding: 12px 14px;
  }

  .ap__steps li + li {
    border-top: 1px solid var(--b2s-color-border-soft);
  }

  .ap__steps i {
    display: inline-grid;
    place-items: center;
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: var(--b2s-color-info-soft);
    color: var(--b2s-color-info-strong);
  }

  .is-done .ap__steps i {
    background: var(--b2s-color-success-soft);
    color: var(--b2s-color-success-strong);
  }

  .ap__steps li.has-problem i {
    background: var(--b2s-color-danger-soft);
    color: var(--b2s-color-danger-strong);
  }

  .ap__steps strong {
    display: block;
    font-weight: 600;
    color: var(--b2s-color-text);
  }

  .ap__steps span {
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-sm);
  }

  .ap__mono {
    font-family: var(--b2s-font-mono);
    font-size: var(--b2s-fs-sm);
    overflow-wrap: anywhere;
  }

  .ap__problems {
    display: grid;
    gap: 6px;
    margin: 0;
    padding: 10px 14px;
    list-style: none;
    border: 1px solid var(--b2s-color-danger-border);
    border-radius: var(--b2s-radius-md);
    background: var(--b2s-color-danger-soft);
    color: var(--b2s-color-danger-strong);
    font-size: var(--b2s-fs-sm);
  }

  .ap__problems i,
  .ap__warning i,
  .ap__note i {
    margin-right: 8px;
  }

  .ap__warning,
  .ap__note {
    margin: 0;
    padding: 10px 14px;
    border-radius: var(--b2s-radius-md);
    font-size: var(--b2s-fs-sm);
  }

  .ap__warning {
    border: 1px solid var(--b2s-color-warning-border);
    background: var(--b2s-color-warning-soft);
    color: var(--b2s-color-warning-strong);
  }

  .ap__note {
    border: 1px solid var(--b2s-color-info-border);
    background: var(--b2s-color-info-soft);
    color: var(--b2s-color-info-strong);
  }
</style>
