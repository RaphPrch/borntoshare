<script lang="ts">
  import { goto } from '$app/navigation';
  import { t } from '$lib/i18n';
  import Drawer from '$lib/components/ui/Drawer.svelte';
  import { checkExistingAccess, createAccessRequest } from '$lib/api/access-requests';
  import { getPublicSettings } from '$lib/api/admin-advanced-settings';
  import { toast } from '$lib/stores/toast';
  import { reportUiError } from '$lib/errors';

  /**
   * Access to one folder, asked from its page: the folder and its guardians are known, only the level, the
   * duration and the reason are left. For someone else or several folders: the full form, this folder added.
   */
  export let open = false;
  export let rootId: number | null = null;
  export let rootName = '';
  export let rootPath = '';
  export let guardians: string[] = [];
  export let onClose: () => void = () => {};

  let policy = { durations: [7, 30, 90], allowPermanent: true, maxDays: 365, minReasonLength: 10 };
  let level: 'READ' | 'WRITE' = 'READ';
  let duration = '30';
  let reason = '';
  let sending = false;
  let state: { kind: 'checking' | 'ok' | 'blocked' | 'elevation'; message: string } = { kind: 'checking', message: '' };
  let loadedFor: number | null = null;

  $: if (open && rootId && loadedFor !== rootId) void prepare(rootId);
  $: if (open && rootId) void check(rootId, level);

  async function prepare(id: number) {
    loadedFor = id;
    reason = '';
    level = 'READ';
    const settings: any = await getPublicSettings(fetch).catch(() => null);
    if (settings?.requests) policy = settings.requests;
    const keys = [...policy.durations.map(String), ...(policy.allowPermanent ? ['permanent'] : [])];
    if (!keys.includes(duration)) duration = keys[Math.min(1, keys.length - 1)] ?? 'permanent';
  }

  let checkToken = 0;
  async function check(id: number, wanted: 'READ' | 'WRITE') {
    const token = ++checkToken;
    state = { kind: 'checking', message: '' };
    try {
      const result: any = await Promise.race([
        checkExistingAccess(fetch, { storage_root_id: id, access_level: wanted } as any),
        new Promise((resolve) => setTimeout(() => resolve({ can_request: true, timed_out: true }), 15000))
      ]);
      if (token !== checkToken) return;
      state = !result?.can_request
        ? { kind: 'blocked', message: String(result?.message ?? t('This request cannot be submitted.')) }
        : result?.code === 'ELEVATION_ALLOWED' || result?.reason === 'ELEVATION_ALLOWED'
          ? { kind: 'elevation', message: String(result?.message ?? t('This request will be handled as an elevation.')) }
          : { kind: 'ok', message: result?.timed_out ? t('Not checked in time: checked again when the request is sent.') : '' };
    } catch {
      if (token === checkToken) state = { kind: 'ok', message: '' };
    }
  }

  $: options = [
    ...policy.durations.map((days) => ({ key: String(days), label: t('{count} days', { count: days }) })),
    ...(policy.allowPermanent ? [{ key: 'permanent', label: t('Permanent') }] : [])
  ];
  $: endDate = duration === 'permanent' ? null : new Date(Date.now() + Number(duration) * 86_400_000);
  $: tooShort = reason.trim().length < policy.minReasonLength;

  async function send() {
    if (!rootId || sending || tooShort || state.kind === 'blocked' || state.kind === 'checking') return;
    sending = true;
    try {
      await createAccessRequest(fetch, {
        storage_root_id: rootId,
        permissions: [level],
        expires_at: endDate ? endDate.toISOString() : null,
        justification: reason.trim()
      } as any);
      toast.success(t('Access request created'));
      onClose();
    } catch (error: unknown) {
      reportUiError(error, t('Failed to create request'), 'access-requests.quick');
    } finally {
      sending = false;
    }
  }
</script>

<Drawer {open} {onClose} title={t('Access to « {name} »', { name: rootName })} subtitle={rootPath} iconClass="bi bi-key">
  <div class="qr">
    <div class="qr__who">
      <i class="bi bi-person-check" aria-hidden="true"></i>
      <span><b>{guardians.length ? t('Guardians: {names}', { names: guardians.join(', ') }) : t('No guardian: an administrator decides')}</b>
        <small>{state.kind === 'checking' ? t('Checking…') : state.kind === 'blocked' ? state.message : state.kind === 'elevation' ? state.message : state.message || t('You can ask for this access.')}</small></span>
    </div>
    {#if state.kind === 'blocked'}<p class="qr__bad">{state.message}</p>{/if}

    <fieldset class="qr__levels">
      <legend>{t('I need to')}</legend>
      <label class:is-on={level === 'READ'}><input type="radio" bind:group={level} value="READ" /><b>{t('Read')}</b><small>{t('Open and copy the files')}</small></label>
      <label class:is-on={level === 'WRITE'}><input type="radio" bind:group={level} value="WRITE" /><b>{t('Modify')}</b><small>{t('Create, change and delete')}</small></label>
    </fieldset>

    <fieldset class="qr__durations">
      <legend>{t('For how long?')}</legend>
      <div>
        {#each options as option (option.key)}
          <button type="button" class:is-on={duration === option.key} on:click={() => (duration = option.key)}>{option.label}</button>
        {/each}
      </div>
      <small>{endDate ? t('Removed automatically on {date}.', { date: endDate.toLocaleDateString() }) : t('No end date.')}</small>
    </fieldset>

    <label class="qr__why">{t('Why?')}
      <textarea class="b2s-input" rows="3" bind:value={reason} placeholder={t('One sentence for the guardians')}></textarea>
      <small class:is-bad={reason.length > 0 && tooShort}>{t('At least {count} characters', { count: policy.minReasonLength })}</small>
    </label>

    <button type="button" class="qr__more" on:click={() => { onClose(); void goto(`/access-requests/new?root=${rootId}`); }}>
      <i class="bi bi-people" aria-hidden="true"></i>{t('For someone else, or several folders')}
    </button>
  </div>
  <svelte:fragment slot="footer">
    <button type="button" class="b2s-btn b2s-btn-secondary" on:click={onClose}>{t('Cancel')}</button>
    <button type="button" class="b2s-btn b2s-btn-primary" disabled={sending || tooShort || state.kind === 'blocked' || state.kind === 'checking'} on:click={send}>
      {sending ? t('Sending…') : t('Ask for the access')}
    </button>
  </svelte:fragment>
</Drawer>

<style>
  .qr { display: grid; gap: 18px; }
  .qr__who { display: flex; gap: 12px; align-items: center; padding: 12px; border-radius: 12px; background: var(--b2s-color-surface-muted, #f6f7f9); }
  .qr__who i { font-size: 20px; color: #3730A3; }
  .qr__who span { display: grid; gap: 2px; }
  .qr__who small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .qr__bad { margin: 0; padding: 8px 12px; border-radius: 10px; background: #FEF2F2; color: #991B1B; font-size: var(--b2s-fs-sm); }
  fieldset { display: grid; gap: 8px; margin: 0; padding: 0; border: 0; }
  legend { margin-bottom: 6px; font-weight: 600; font-size: var(--b2s-fs-sm); }
  .qr__levels { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .qr__levels legend { grid-column: 1 / -1; }
  .qr__levels label { display: grid; gap: 2px; padding: 12px; border: 1px solid var(--b2s-color-border); border-radius: 12px; cursor: pointer; }
  .qr__levels label.is-on { border: 2px solid #0E1218; background: #FAFFF0; }
  .qr__levels input { position: absolute; opacity: 0; }
  .qr__levels small, .qr__durations small, .qr__why small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .qr__durations div { display: flex; flex-wrap: wrap; gap: 6px; }
  .qr__durations button { height: 38px; padding: 0 14px; border: 1px solid var(--b2s-color-border); border-radius: 999px; background: var(--b2s-color-surface, #fff); font: inherit; font-size: var(--b2s-fs-sm); cursor: pointer; }
  .qr__durations button.is-on { background: #0E1218; border-color: #0E1218; color: #fff; }
  .qr__why { display: grid; gap: 6px; font-weight: 600; font-size: var(--b2s-fs-sm); }
  .qr__why textarea { font-weight: 400; }
  .qr__why small.is-bad { color: #B91C1C; }
  .qr__more { display: inline-flex; gap: 8px; align-items: center; justify-self: start; border: 0; background: none; padding: 0; color: var(--b2s-color-primary, #2563eb); font: inherit; font-size: var(--b2s-fs-sm); cursor: pointer; }
</style>
