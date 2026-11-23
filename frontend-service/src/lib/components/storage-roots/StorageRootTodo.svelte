<script lang="ts">
  import { governanceEnabled } from '$lib/utils/features';
  

  import AppModal from '$lib/components/ui/AppModal.svelte';
  import { goto } from '$app/navigation';
  import { t } from '$lib/i18n';
  import { initials } from '$lib/utils/format';
  import { listPendingRequestsForRoot, type PendingRootRequest } from '$lib/api/access-requests';

  type AlertItem = { key: string; type?: string; title: string; subtitle?: string | null; tone?: 'warning' | 'error'; message?: string | null; group?: string | null; people?: string[] };
  type Step = { key: string; type: string; tone: 'bad' | 'warn'; icon: string; title: string; detail: string; group: string; people: string[] };
  type Guide = { what: string; why: string; steps: string[]; people: string[]; action: { label: string; run: () => void } | null; second?: { label: string; run: () => void } };

  
  interface Props {
    /**
   * « To do on this folder »: its open alerts, each with the guide and the action that settles it, then one line
   * for its pending requests (decided on the requests page, not here).
   */
    rootId?: number | null;
    /** Name of the folder: the requests page opens filtered on it */
    rootName?: string;
    alertItems?: AlertItem[];
    busy?: boolean;
    onRunProbe?: () => void;
    onOpenGuardians?: () => void;
    onOpenPermissions?: () => void;
    onViewAllAlerts?: () => void;
  }

  let {
    rootId = null,
    rootName = '',
    alertItems = [],
    busy = false,
    onRunProbe = () => {},
    onOpenGuardians = () => {},
    onOpenPermissions = () => {},
    onViewAllAlerts = () => {}
  }: Props = $props();

  const PROBE_TYPES = ['root_probe_failed', 'root_probe_unknown', 'endpoint_unreachable', 'endpoint_probe_failed'];
  const PERMISSION_TYPES = ['acl_principal_not_governed', 'acl_inherited_not_governed', 'acl_profile_missing', 'ad_group_read_failed', 'acl_gap', 'missing_ace'];

  const typeOf = (item: AlertItem) => item.type || (String(item.key).match(/[a-z_]+$/)?.[0] ?? '');


  let requests: PendingRootRequest[] = $state([]);
  let loadedFor: number | null = $state(null);
  let seq = 0;


  async function load(id: number | null) {
    loadedFor = id;
    const current = ++seq;
    if (!id) {
      requests = [];
      return;
    }
    try {
      const rows = await listPendingRequestsForRoot(fetch, id);
      if (current === seq) requests = rows;
    } catch {
      if (current === seq) requests = [];
    }
  }

  // « GG_…_RW: Alice Martin, Bob Durand (+3) » → the group and the people named by the alert
  const groupOf = (detail: string) => (detail.includes(':') ? detail.split(':')[0].trim() : '');
  const peopleOf = (detail: string) => (detail.includes(':') ? detail.slice(detail.indexOf(':') + 1).split(',').map((name) => name.trim()).filter(Boolean) : []);
  let steps = $derived(alertItems
    .filter((item) => typeOf(item) !== 'pending_access_validation')
    // Without the governance (5S only): no guardian to add for the requests, no permissions tab to open
    .filter((item) => $governanceEnabled || (typeOf(item) !== 'missing_guardian' && !PERMISSION_TYPES.includes(typeOf(item))))
    .map((item): Step => {
      const type = typeOf(item);
      const detail = item.subtitle || item.message || '';
      const base = { key: item.key, type, tone: item.tone === 'error' ? 'bad' as const : 'warn' as const, title: item.title, detail,
        group: item.group || groupOf(item.message ?? ''), people: peopleOf(item.message ?? '').length ? peopleOf(item.message ?? '') : (item.people ?? []) };
      if (PROBE_TYPES.includes(type)) return { ...base, icon: 'bi-wifi-off' };
      if (type === 'missing_guardian') return { ...base, icon: 'bi-person-plus' };
      if (PERMISSION_TYPES.includes(type) || type.startsWith('ad_member')) return { ...base, icon: 'bi-shield-exclamation' };
      return { ...base, icon: 'bi-exclamation-triangle' };
    })
    .sort((a, b) => Number(b.tone === 'bad') - Number(a.tone === 'bad')));
  $effect.pre(() => {
    if (rootId !== loadedFor) void load(rootId);
  });
  let total = $derived(steps.length + (requests.length ? 1 : 0));

  // ---- « Details »: what the alert means, why it happens, what to do exactly, and the action that settles it ----
  let opened: Step | null = $state(null);
  const close = () => (opened = null);
  const then = (run: () => void) => () => { close(); run(); };
  function guideOf(step: Step): Guide {
    const group = step.group;
    if (step.type === 'ad_member_not_granted') return {
      what: t('These people are members of the AD group {group}, but BornToShare granted them no access to this folder.', { group }),
      why: t('They were added to the group directly in Active Directory, outside BornToShare: their access is not traced and has no end date.'),
      people: step.people,
      steps: [
        t('Check each person below with the guardian of the folder.'),
        t('If the access is legitimate: create an access request for the person; the guardian validates it and BornToShare traces it.'),
        t('Otherwise: remove the person from the group in Active Directory, or withdraw the access in the next access review.'),
        t('The alert disappears at the next directory synchronisation.')
      ],
      action: { label: t('Create a request'), run: then(() => void goto(`/access-requests/new?root=${Number(rootId)}`)) },
      second: { label: t('See the permissions'), run: then(onOpenPermissions) }
    };
    if (step.type === 'ad_member_missing') return {
      what: t('BornToShare granted these people an access, but they are not in the AD group {group}.', { group }),
      why: t('The worker could not add them, or someone removed them from the group in Active Directory.'),
      people: step.people,
      steps: [
        t('Look in Governance Jobs for the failed jobs of this folder.'),
        t('Repair the ACL from the permissions of the folder: the worker adds the missing members again.'),
        t('The alert disappears at the next directory synchronisation.')
      ],
      action: { label: t('See the permissions'), run: then(onOpenPermissions) },
      second: { label: t('See the failed jobs'), run: then(() => void goto('/observability?tab=jobs&status=FAILED')) }
    };
    if (PROBE_TYPES.includes(step.type)) return {
      what: t('BornToShare cannot reach this folder on the file server.'),
      why: t('The server is off or unreachable, the share was renamed or moved, or the service account lost its rights.'),
      people: [],
      steps: [
        t('Check that the file server answers and that the path of the folder is still right.'),
        t('Check that the service account of the server can still read the share.'),
        t('Test the folder again: the alert closes as soon as it answers.')
      ],
      action: { label: t('Test again'), run: then(onRunProbe) }
    };
    if (step.type === 'missing_guardian') return {
      what: t('Nobody guards this folder: its access requests go to the administrators.'),
      why: t('No guardian was named, or the guardians left the company.'),
      people: [],
      steps: [
        t('Choose at least one guardian among the people who know the content of the folder.'),
        t('Two guardians are better: one decides when the other is away.')
      ],
      action: { label: t('Add guardians'), run: then(onOpenGuardians) }
    };
    if (PERMISSION_TYPES.includes(step.type)) return {
      what: t('The ACL of the folder holds rights that BornToShare does not govern.'),
      why: t('Rights were set directly on the file server, outside BornToShare: nobody requested or validated them.'),
      people: step.people,
      steps: [
        t('Open the permissions of the folder and look at « Outside BornToShare ».'),
        t('If the right is legitimate, accept the gap; otherwise remove the entry on the file server.'),
        t('Read the ACL again: the alert disappears once the ACL matches.')
      ],
      action: { label: t('See the permissions'), run: then(onOpenPermissions) }
    };
    return {
      what: step.title,
      why: step.detail,
      people: [],
      steps: [t('Fix the cause, then read the ACL again: the alert closes when the folder is back in order.')],
      action: { label: t('Read the ACL again'), run: then(onRunProbe) },
      second: { label: t('All the alerts of the folder'), run: then(onViewAllAlerts) }
    };
  }
  let guide = $derived(opened ? guideOf(opened) : null);
</script>

{#if total}
  <section class="todo" aria-label={t('To do on this folder')}>
    <h2><i class="bi bi-exclamation-triangle-fill" aria-hidden="true"></i>{t('To do on this folder')} · {total}</h2>
    {#each steps as step (step.key)}
      <div class="todo__row">
        <span class={`todo__icon is-${step.tone}`} aria-hidden="true"><i class={`bi ${step.icon}`}></i></span>
        <span class="todo__text"><strong>{step.title}</strong>{#if step.detail}<small>{step.detail}</small>{/if}</span>
        <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" disabled={busy} onclick={() => (opened = step)}>{t('Details')}</button>
      </div>
    {/each}
    {#if requests.length}
      <div class="todo__row">
        <span class="todo__icon is-info" aria-hidden="true"><i class="bi bi-envelope"></i></span>
        <span class="todo__text"><strong>{t('{count} pending request(s)', { count: requests.length })}</strong><small>{t('To decide by the guardians of the folders')}</small></span>
        <a class="b2s-btn b2s-btn-sm b2s-btn-secondary" href={`/access-requests?status=pending&q=${encodeURIComponent(rootName)}`}>{t('See the requests')}</a>
      </div>
    {/if}
  </section>
{/if}

<AppModal open={Boolean(opened)} onClose={close} size="md" title={opened?.title ?? ''} iconClass={opened ? `bi ${opened.icon}` : null}>
  {#if guide}
    <div class="guide">
      <section><h3>{t('What it means')}</h3><p>{guide.what}</p></section>
      {#if guide.why}<section><h3>{t('Why')}</h3><p>{guide.why}</p></section>{/if}
      {#if guide.people.length}
        <section><h3>{t('People concerned')} · {guide.people.length}</h3>
          <ul class="guide__people">{#each guide.people as person (person)}<li><span class="todo__avatar" aria-hidden="true">{initials(person)}</span>{person}</li>{/each}</ul>
        </section>
      {/if}
      <section><h3>{t('What to do')}</h3><ol class="guide__steps">{#each guide.steps as text, index (index)}<li>{text}</li>{/each}</ol></section>
    </div>
  {/if}
  {#snippet footer()}
    <button type="button" class="b2s-btn b2s-btn-secondary" onclick={close}>{t('Close')}</button>
    {#if guide?.second}<button type="button" class="b2s-btn b2s-btn-secondary" onclick={guide.second.run}>{guide.second.label}</button>{/if}
    {#if guide?.action}<button type="button" class="b2s-btn b2s-btn-primary" onclick={guide.action.run}>{guide.action.label}</button>{/if}
  {/snippet}
</AppModal>

<style>
  .guide { display: grid; gap: 16px; }
  .guide h3 { margin: 0 0 6px; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; }
  .guide p { margin: 0; line-height: 1.5; }
  .guide__people { display: flex; flex-wrap: wrap; gap: 6px; margin: 0; padding: 0; list-style: none; }
  .guide__people li { display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px 2px 2px; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-surface-muted); font-size: var(--b2s-fs-sm); }
  .guide__people .todo__avatar { width: 24px; height: 24px; font-size: 10px; }
  .guide__steps { display: grid; gap: 8px; margin: 0; padding-left: 20px; line-height: 1.5; }
  .guide__steps li::marker { color: var(--b2s-accent); font-weight: 700; }
  .todo { overflow: hidden; border: 1px solid var(--b2s-color-warning-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .todo h2 { display: flex; align-items: center; gap: 8px; margin: 0; padding: 11px 16px; background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); font-size: var(--b2s-fs-sm); font-weight: 600; }
  .todo__row { display: grid; grid-template-columns: 28px minmax(0, 1fr) auto; gap: 12px; align-items: center; padding: 10px 16px; border-top: 1px solid var(--b2s-color-border); }
  .todo h2 + .todo__row { border-top: 0; }
  .todo__icon, .todo__avatar { display: grid; place-items: center; width: 28px; height: 28px; border-radius: 8px; font-size: 13px; }
  .todo__icon.is-bad { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger-strong); }
  .todo__icon.is-info { background: var(--b2s-accent-soft); color: var(--b2s-accent-strong); }
  .todo__icon.is-warn { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .todo__avatar { border-radius: 50%; background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); font-size: 11px; font-weight: 700; }
  .todo__text { display: flex; flex-direction: column; min-width: 0; }
  .todo__text strong { font-weight: 600; font-size: var(--b2s-fs-sm); }
  .todo__text small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); overflow-wrap: anywhere; }
</style>
