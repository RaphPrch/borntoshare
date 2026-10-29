<script lang="ts">
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

  /**
   * « To review »: the pending requests of the storage root, decided in place.
   * Validating shows what the worker will do (AD group, OU, ACL) before it runs.
   */
  export let rootId: number | null = null;
  export let onDecided: () => void = () => {};

  let requests: PendingRootRequest[] = [];
  let loadedFor: number | null = null;
  let seq = 0;
  let deciding: { request: PendingRootRequest; decision: 'approve' | 'reject' } | null = null;
  let preview: ApprovalPreview | null = null;
  let busy = false;

  $: if (rootId !== loadedFor) void load(rootId);

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

  $: previewItem = preview?.items?.[0];
  $: impact = deciding?.decision === 'approve'
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
    : [t('{name} is told that the request is refused; nothing changes on the folder.', { name: deciding?.request.requested_for_display ?? '' })];

  async function decide() {
    const target = deciding;
    deciding = null;
    if (!target) return;
    busy = true;
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
      busy = false;
    }
  }

  const levelLabel = (code: string | null) => (String(code ?? '').toLowerCase() === 'write' ? t('modify') : t('read'));
</script>

{#if requests.length}
  <section class="todo" aria-label={t('To review')}>
    {#each requests.slice(0, 3) as request (request.request_id)}
      <div class="todo__row">
        <span class="todo__avatar" aria-hidden="true">{initials(request.requested_for_display ?? '')}</span>
        <span class="todo__text">
          <strong>{request.requested_for_display ?? t('Someone')}</strong>
          {t('asks for {level}', { level: levelLabel(request.access_profile_name) })}
          {#if request.justification}<span class="todo__why">· {request.justification}</span>{/if}
          {#if request.created_at}<span class="todo__when">· {timeAgo(request.created_at)}</span>{/if}
        </span>
        <a class="todo__link" href={`/access-requests?request=${request.request_id}`}>{request.request_code ?? t('Details')}</a>
        <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" disabled={busy} on:click={() => ask(request, 'reject')}>{t('Refuse')}</button>
        <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-primary" disabled={busy} on:click={() => ask(request, 'approve')}>{t('Validate')}</button>
      </div>
    {/each}
    {#if requests.length > 3}
      <a class="todo__more" href="/access-requests?status=pending">{t('{count} more request(s) to review', { count: requests.length - 3 })}</a>
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
  .todo {
    display: grid;
    gap: 2px;
    padding: 6px 14px;
    border-radius: var(--b2s-radius-lg);
    background: var(--b2s-color-warning-soft);
    color: var(--b2s-color-warning-strong);
  }

  .todo__row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px;
    padding: 6px 0;
  }

  .todo__avatar {
    width: 28px;
    height: 28px;
    flex: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    background: var(--b2s-color-warning-border);
    font-size: 11px;
    font-weight: 700;
  }

  .todo__text {
    flex: 1 1 320px;
    min-width: 0;
  }

  .todo__text strong {
    font-weight: 600;
  }

  .todo__why,
  .todo__when {
    opacity: 0.85;
  }

  .todo__link,
  .todo__more {
    color: inherit;
    font-size: var(--b2s-fs-xs);
    text-decoration: underline;
  }

  .todo__more {
    padding: 4px 0 6px 38px;
  }
</style>
