<script lang="ts">
  import { governanceEnabled } from '$lib/utils/features';
  

  import ConfirmActionModal from '$lib/components/ui/ConfirmActionModal.svelte';
  import { t } from '$lib/i18n';
  import { initials, timeAgo } from '$lib/utils/format';
  import { reportUiError } from '$lib/errors';
  import { toast } from '$lib/stores/toast';
  import {
    bulkDecision,
    getApprovalPreview,
    listPendingRequestsForRoot,
    type ApprovalPreview,
    type PendingRootRequest
  } from '$lib/api/access-requests';

  type AlertItem = { key: string; type?: string; title: string; subtitle?: string | null; tone?: 'warning' | 'error' };
  type Step = { key: string; tone: 'bad' | 'warn'; icon: string; title: string; detail: string; label: string; run: () => void };

  
  interface Props {
    /**
   * « To do on this folder »: its open alerts, each with the action that settles it, then its pending
   * requests decided in place (validating shows what the worker will do before it runs).
   */
    rootId?: number | null;
    alertItems?: AlertItem[];
    busy?: boolean;
    onRunProbe?: () => void;
    onOpenGuardians?: () => void;
    onOpenPermissions?: () => void;
    onViewAllAlerts?: () => void;
    onDecided?: () => void;
  }

  let {
    rootId = null,
    alertItems = [],
    busy = false,
    onRunProbe = () => {},
    onOpenGuardians = () => {},
    onOpenPermissions = () => {},
    onViewAllAlerts = () => {},
    onDecided = () => {}
  }: Props = $props();

  const PROBE_TYPES = ['root_probe_failed', 'root_probe_unknown', 'endpoint_unreachable', 'endpoint_probe_failed'];
  const PERMISSION_TYPES = ['acl_principal_not_governed', 'acl_inherited_not_governed', 'acl_profile_missing', 'ad_group_read_failed', 'acl_gap', 'missing_ace'];

  const typeOf = (item: AlertItem) => item.type || (String(item.key).match(/[a-z_]+$/)?.[0] ?? '');


  let requests: PendingRootRequest[] = $state([]);
  let loadedFor: number | null = $state(null);
  let seq = 0;
  let deciding: { request: PendingRootRequest; decision: 'approve' | 'reject' } | null = $state(null);
  let preview: ApprovalPreview | null = $state(null);
  let decidingBusy = $state(false);


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

  async function ask(request: PendingRootRequest, decision: 'approve' | 'reject') {
    deciding = { request, decision };
    preview = null;
    if (decision === 'approve') {
      try {
        preview = await getApprovalPreview(fetch, request.request_id);
      } catch {
        preview = null;
      }
    }
  }


  async function decide() {
    const target = deciding;
    deciding = null;
    if (!target) return;
    decidingBusy = true;
    try {
      const result = await bulkDecision(fetch, [target.request.request_id], target.decision);
      if (Number(result?.failed_ids?.length ?? 0) > 0) throw new Error(String(Object.values(result?.failed_reasons ?? {})[0] ?? ''));
      toast.success(target.decision === 'approve' ? t('Request validated: the access is in place.') : t('Request refused.'));
      await load(rootId);
      onDecided();
    } catch (error: unknown) {
      reportUiError(error, t('The decision failed.'), 'storage-root.todo');
      await load(rootId);
    } finally {
      decidingBusy = false;
    }
  }

  const levelLabel = (code: string | null) => (String(code ?? '').toLowerCase() === 'write' ? t('modify') : t('read'));
  let steps = $derived(alertItems
    .filter((item) => typeOf(item) !== 'pending_access_validation')
    // Without the governance (5S only): no guardian to add for the requests, no permissions tab to open
    .filter((item) => $governanceEnabled || (typeOf(item) !== 'missing_guardian' && !PERMISSION_TYPES.includes(typeOf(item))))
    .map((item): Step => {
      const type = typeOf(item);
      const base = { key: item.key, tone: item.tone === 'error' ? 'bad' as const : 'warn' as const, title: item.title, detail: item.subtitle ?? '' };
      if (PROBE_TYPES.includes(type)) return { ...base, icon: 'bi-wifi-off', label: t('Test again'), run: onRunProbe };
      if (type === 'missing_guardian') return { ...base, icon: 'bi-person-plus', label: t('Add guardians'), run: onOpenGuardians };
      if (PERMISSION_TYPES.includes(type)) return { ...base, icon: 'bi-shield-exclamation', label: t('See the permissions'), run: onOpenPermissions };
      return { ...base, icon: 'bi-exclamation-triangle', label: t('Details'), run: onViewAllAlerts };
    })
    .sort((a, b) => Number(b.tone === 'bad') - Number(a.tone === 'bad')));
  $effect.pre(() => {
    if (rootId !== loadedFor) void load(rootId);
  });
  let previewItem = $derived(preview?.items?.[0]);
  let impact = $derived(deciding?.decision === 'approve'
    ? [
        ...(previewItem
          ? [
              previewItem.group_action === 'create'
                ? t('The AD group {group} is created in {ou}.', { group: previewItem.group_name ?? '', ou: previewItem.target_ou_dn ?? '' })
                : t('The AD group {group} is reused.', { group: previewItem.group_name ?? '' }),
              t('{name} is added to the group by the worker.', { name: deciding.request.requested_for_display ?? '' }),
              previewItem.acl === 'modify' ? t('The group gets Modify on the folder.') : t('The group gets Read and execute on the folder.')
            ]
          : []),
        ...(preview?.blockers ?? []).map((b) => b.message)
      ]
    : [t('{name} is told that the request is refused; nothing changes on the folder.', { name: deciding?.request.requested_for_display ?? '' })]);
  let total = $derived(steps.length + requests.length);
</script>

{#if total}
  <section class="todo" aria-label={t('To do on this folder')}>
    <h2><i class="bi bi-exclamation-triangle-fill" aria-hidden="true"></i>{t('To do on this folder')} · {total}</h2>
    {#each steps as step (step.key)}
      <div class="todo__row">
        <span class={`todo__icon is-${step.tone}`} aria-hidden="true"><i class={`bi ${step.icon}`}></i></span>
        <span class="todo__text"><strong>{step.title}</strong>{#if step.detail}<small>{step.detail}</small>{/if}</span>
        <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" disabled={busy} onclick={step.run}>{step.label}</button>
      </div>
    {/each}
    {#each requests.slice(0, 5) as request (request.request_id)}
      <div class="todo__row">
        <span class="todo__avatar" aria-hidden="true">{initials(request.requested_for_display ?? '')}</span>
        <span class="todo__text">
          <strong>{t('{name} asks for {level}', { name: request.requested_for_display ?? t('Someone'), level: levelLabel(request.access_profile_name) })}</strong>
          <small>
            {#if request.justification}{request.justification} · {/if}{#if request.created_at}{timeAgo(request.created_at)} · {/if}<a href={`/access-requests?request=${request.request_id}`}>{request.request_code ?? t('Details')}</a>
          </small>
        </span>
        <span class="todo__decide">
          <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" disabled={decidingBusy} onclick={() => ask(request, 'reject')}>{t('Refuse')}</button>
          <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-primary" disabled={decidingBusy} onclick={() => ask(request, 'approve')}>{t('Validate')}</button>
        </span>
      </div>
    {/each}
    {#if requests.length > 5}
      <a class="todo__more" href="/access-requests?status=pending">{t('{count} more request(s) to review', { count: requests.length - 5 })}</a>
    {/if}
  </section>
{/if}

<ConfirmActionModal
  open={Boolean(deciding)}
  onClose={() => (deciding = null)}
  onConfirm={decide}
  severity={deciding?.decision === 'approve' ? 'warning' : 'danger'}
  title={deciding?.decision === 'approve'
    ? t('Validate the request of {name}?', { name: deciding?.request.requested_for_display ?? '' })
    : t('Refuse the request of {name}?', { name: deciding?.request.requested_for_display ?? '' })}
  impactItems={impact}
  confirmLabel={deciding?.decision === 'approve' ? t('Validate') : t('Refuse')}
  confirmVariant={deciding?.decision === 'approve' ? 'primary' : 'danger'}
/>

<style>
  .todo { overflow: hidden; border: 1px solid var(--b2s-color-warning-border, #f3d9ad); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .todo h2 { display: flex; align-items: center; gap: 8px; margin: 0; padding: 11px 16px; background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); font-size: var(--b2s-fs-sm); font-weight: 600; }
  .todo__row { display: grid; grid-template-columns: 28px minmax(0, 1fr) auto; gap: 12px; align-items: center; padding: 10px 16px; border-top: 1px solid var(--b2s-color-border); }
  .todo h2 + .todo__row { border-top: 0; }
  .todo__icon, .todo__avatar { display: grid; place-items: center; width: 28px; height: 28px; border-radius: 8px; font-size: 13px; }
  .todo__icon.is-bad { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger-strong); }
  .todo__icon.is-warn { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .todo__avatar { border-radius: 50%; background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); font-size: 11px; font-weight: 700; }
  .todo__text { display: flex; flex-direction: column; min-width: 0; }
  .todo__text strong { font-weight: 600; font-size: var(--b2s-fs-sm); }
  .todo__text small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); overflow-wrap: anywhere; }
  .todo__text a { color: inherit; text-decoration: underline; }
  .todo__decide { display: flex; gap: 6px; }
  .todo__more { display: block; padding: 8px 16px 10px 56px; border-top: 1px solid var(--b2s-color-border); color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
</style>
