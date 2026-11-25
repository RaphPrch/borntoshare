<script lang="ts">
  import { t } from '$lib/i18n';
  import type { ApprovalPreview, ApprovalPreviewItem } from '$lib/api/access-requests';
  import { timeAgo } from '$lib/utils/format';
  import { changeSentence, kindLabel, rightsLabel, riskSentence } from '$lib/utils/acl-preview';

  
  
  interface Props {
    /** What the approval does, step by step: before (« will ») or after it succeeded (« done ») */
    preview: ApprovalPreview;
    done?: boolean;
    /** Outcome of the group step read from the provisioning log, once applied: created, reused, adopted… */
    groupOutcome?: string | null;
  }

  let { preview, done = false, groupOutcome = null }: Props = $props();

  let who = $derived(preview.principal?.display || preview.principal?.username || t('the requester'));

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
          {#if !done && item.acl_preview}
            {@const acl = item.acl_preview}
            <div class="ap__acl">
              <p class={`ap__change is-${acl.change}`}><b>{t('Simulation, nothing is changed')}</b> · {changeSentence(acl)}</p>
              {#if acl.current.length}
                <details>
                  <summary>{t('Current ACL ({n} entries, read {ago})', { n: acl.current.length, ago: acl.read_at ? timeAgo(acl.read_at) : '—' })}</summary>
                  <ul class="ap__aces">
                    {#each acl.current as ace (`${ace.principal}|${ace.rights}`)}
                      <li>
                        <span class="ap__mono">{ace.principal}</span>
                        <small>
                          {rightsLabel(ace.rights)}{#if ace.inherited} · {t('Inherited from the parent')}{/if}
                          <span class={`v2-tag ${ace.kind === 'other' || ace.kind === 'broad' ? 'is-warn' : ace.kind === 'managed' ? 'is-ok' : ''}`}>{kindLabel(ace.kind)}</span>
                        </small>
                      </li>
                    {/each}
                  </ul>
                </details>
              {/if}
            </div>
          {/if}
        </div>
      </li>
    </ol>
    {#if !done && item.acl_preview?.risks.length}
      <div class="ap__risks">
        <strong>{t('Risks before approving')}</strong>
        <ul>
          {#each item.acl_preview.risks as risk (risk.code)}<li><i class="bi bi-exclamation-triangle" aria-hidden="true"></i>{riskSentence(risk)}</li>{/each}
        </ul>
      </div>
    {/if}
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

  .ap__steps > li {
    display: grid;
    grid-template-columns: 28px minmax(0, 1fr);
    gap: 10px;
    align-items: start;
    padding: 12px 14px;
  }

  .ap__steps > li + li {
    border-top: 1px solid var(--b2s-color-border-soft);
  }

  .ap__steps > li > i {
    display: inline-grid;
    place-items: center;
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: var(--b2s-color-info-soft);
    color: var(--b2s-color-info-strong);
  }

  .is-done .ap__steps > li > i {
    background: var(--b2s-color-success-soft);
    color: var(--b2s-color-success-strong);
  }

  .ap__steps > li.has-problem > i {
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

  .ap__acl {
    display: grid;
    gap: 6px;
    margin-top: 8px;
  }

  .ap__change {
    margin: 0;
    font-size: var(--b2s-fs-sm);
    color: var(--b2s-color-text);
  }

  .ap__change.is-unknown {
    color: var(--b2s-color-warning-strong);
  }

  .ap__acl summary {
    cursor: pointer;
    color: var(--b2s-accent);
    font-size: var(--b2s-fs-sm);
  }

  .ap__aces {
    display: grid;
    gap: 4px;
    margin: 6px 0 0;
    padding: 0;
    list-style: none;
  }

  .ap__aces li {
    display: grid;
    gap: 2px;
    padding: 6px 0;
    border-top: 1px solid var(--b2s-color-border-soft);
    font-size: var(--b2s-fs-sm);
  }

  .ap__aces small {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
    color: var(--b2s-color-text-muted);
  }

  .ap__risks {
    padding: 10px 14px;
    border: 1px solid var(--b2s-color-warning-border);
    border-radius: var(--b2s-radius-md);
    background: var(--b2s-color-warning-soft);
    color: var(--b2s-color-warning-strong);
    font-size: var(--b2s-fs-sm);
  }

  .ap__risks ul {
    display: grid;
    gap: 4px;
    margin: 6px 0 0;
    padding: 0;
    list-style: none;
  }

  .ap__risks i {
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
