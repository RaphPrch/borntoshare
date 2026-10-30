<script lang="ts">
  import { t } from '$lib/i18n';
  import { timeAgo } from '$lib/utils/format';
  import Drawer from '$lib/components/ui/Drawer.svelte';
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import FieldError from '$lib/components/ui/FieldError.svelte';
  import ConfirmActionModal from '$lib/components/ui/ConfirmActionModal.svelte';
  import { toast } from '$lib/stores/toast';
  import { reportUiError } from '$lib/errors';
  import { resolveCredentials } from '$lib/api/credentials';
  import { STATUS_VARIANT, formatDuration, statusLabel } from '$lib/utils/infrastructure';
  import {
    checkWorker,
    createWorker,
    deleteWorker,
    testWorker,
    updateWorker,
    type AgentCheck,
    type InfraWorker,
    type WorkerInput
  } from '$lib/api/infrastructure';

  export let workers: InfraWorker[] = [];
  export let onChanged: () => Promise<void> | void = () => {};

  const QUEUE_LABELS: Record<string, string> = {
    capsule_identity: 'Directory',
    capsule_provisioning: 'AD groups',
    capsule_acl: 'ACL',
    capsule_probes: 'Checks'
  };

  // ---- Drawer (add / edit)
  let drawerOpen = false;
  let editing: InfraWorker | null = null;
  let form = { name: '', host: '', port: 8443, use_tls: true, verify_tls: true, username: '', password: '', is_enabled: true };
  let showPassword = false;
  let showErrors = false;
  let testing = false;
  let saving = false;
  let check: AgentCheck | null = null;
  let checkedKey = '';
  let busyId: number | null = null;
  let removing: InfraWorker | null = null;

  $: formKey = JSON.stringify([form.host, form.port, form.use_tls, form.verify_tls, form.username, form.password]);
  $: needsPassword = !editing || !!form.password;
  $: valid = !!form.name.trim() && !!form.host.trim() && !!form.port && !!form.username.trim() && (!!form.password || !!editing);
  $: checkFresh = !!check && checkedKey === formKey;

  /** Default ports of the agent: 8443 in HTTPS, 8080 in HTTP; a port chosen by hand is kept */
  function setTls(useTls: boolean) {
    form.use_tls = useTls;
    if (useTls && Number(form.port) === 8080) form.port = 8443;
    if (!useTls && Number(form.port) === 8443) form.port = 8080;
  }

  function openAdd() {
    editing = null;
    form = { name: '', host: '', port: 8443, use_tls: true, verify_tls: true, username: 'b2s-agent', password: '', is_enabled: true };
    check = null;
    showErrors = false;
    drawerOpen = true;
  }

  function openEdit(worker: InfraWorker) {
    editing = worker;
    form = { name: worker.name, host: worker.host, port: worker.port, use_tls: worker.use_tls, verify_tls: worker.verify_tls, username: worker.username, password: '', is_enabled: worker.is_enabled };
    check = null;
    showErrors = false;
    drawerOpen = true;
  }

  function closeDrawer() {
    drawerOpen = false;
    form.password = '';
  }

  /** Stores the typed password in the secret broker (one secret per worker) and returns its reference */
  async function passwordRef(): Promise<string | null> {
    if (!form.password) return null;
    const resolved = await resolveCredentials(
      fetch,
      { username: form.username.trim(), password: form.password, secret_ref: null },
      { secretName: `infrastructure-worker/${form.host.trim()}/${form.port}`, mode: 'create' }
    );
    return resolved.secret_ref ?? null;
  }

  function payload(ref: string | null): WorkerInput {
    return {
      name: form.name.trim(),
      host: form.host.trim(),
      port: Number(form.port),
      use_tls: form.use_tls,
      verify_tls: form.verify_tls,
      username: form.username.trim(),
      is_enabled: form.is_enabled,
      ...(ref ? { password_ref: ref } : {})
    };
  }

  async function runTest() {
    if (!valid) {
      showErrors = true;
      return;
    }
    testing = true;
    check = null;
    const key = formKey;
    try {
      // Editing without a new password: the stored password of this worker is used
      check = await testWorker(fetch, { ...payload(await passwordRef()), ...(editing ? { worker_id: editing.id } : {}) });
      checkedKey = key;
    } catch (e) {
      reportUiError(e, t('Worker test failed.'), 'infrastructure.workers.test');
    } finally {
      testing = false;
    }
  }

  async function save() {
    if (!valid) {
      showErrors = true;
      return;
    }
    saving = true;
    try {
      const ref = await passwordRef();
      if (editing) {
        await updateWorker(fetch, editing.id, payload(ref));
        toast.success(t('Worker updated.'));
      } else {
        await createWorker(fetch, payload(ref));
        toast.success(t('Worker added: its agent answered.'));
      }
      closeDrawer();
      await onChanged();
    } catch (e) {
      reportUiError(e, t('Unable to save the worker.'), 'infrastructure.workers.save');
    } finally {
      saving = false;
    }
  }

  async function recheck(worker: InfraWorker) {
    busyId = worker.id;
    try {
      const updated = await checkWorker(fetch, worker.id);
      workers = workers.map((w) => (w.id === worker.id ? updated : w));
      if (updated.status === 'healthy') toast.success(t('Worker {name} answers.', { name: worker.name }));
      else toast.warning(`${worker.name}: ${updated.last_message ?? statusLabel(updated.status)}`);
    } catch (e) {
      reportUiError(e, t('Worker check failed.'), 'infrastructure.workers.check');
    } finally {
      busyId = null;
    }
  }

  async function toggleEnabled(worker: InfraWorker) {
    busyId = worker.id;
    try {
      await updateWorker(fetch, worker.id, { is_enabled: !worker.is_enabled });
      await onChanged();
    } catch (e) {
      reportUiError(e, t('Unable to update the worker.'), 'infrastructure.workers.toggle');
    } finally {
      busyId = null;
    }
  }

  async function confirmRemove() {
    const worker = removing;
    removing = null;
    if (!worker) return;
    try {
      await deleteWorker(fetch, worker.id);
      toast.success(t('Worker removed.'));
      await onChanged();
    } catch (e) {
      reportUiError(e, t('Unable to remove the worker.'), 'infrastructure.workers.remove');
    }
  }
</script>

<div class="toolbar">
  <p>{t('Workers run the jobs (directory, AD groups, ACL, checks). The platform checks each one through its HTTPS agent.')}</p>
  <button type="button" class="b2s-btn b2s-btn-primary" on:click={openAdd}>
    <i class="bi bi-plus-lg" aria-hidden="true"></i>{t('Add a worker')}
  </button>
</div>

{#if workers.length === 0}
  <div class="empty">
    <i class="bi bi-cpu" aria-hidden="true"></i>
    <strong>{t('No worker registered')}</strong>
    <span>{t('Add the workers so their state appears here and in the health check.')}</span>
  </div>
{/if}

<div class="cards">
  {#each workers as worker (worker.id)}
    <article class="card" class:is-disabled={!worker.is_enabled}>
      <header class="card__head">
        <span class={`card__icon is-${worker.status}`}><i class="bi bi-cpu" aria-hidden="true"></i></span>
        <div class="card__title">
          <strong>{worker.name}</strong>
          <span class="mono">{worker.agent_url}</span>
        </div>
        {#if worker.is_enabled}
          <StatusBadge compact={true} status={worker.status} label={statusLabel(worker.status)} variant={STATUS_VARIANT[worker.status]} />
        {:else}
          <StatusBadge compact={true} status="disabled" label={t('Disabled')} variant="disabled" />
        {/if}
      </header>

      {#if worker.last_message}
        <p class={`card__msg is-${worker.status}`}>{worker.last_message}</p>
      {/if}

      <dl class="facts">
        <dt>{t('Host')}</dt><dd class="mono">{worker.hostname ?? '—'}</dd>
        <dt>{t('Version')}</dt><dd>{worker.version ?? '—'}</dd>
        <dt>{t('Scope')}</dt><dd>{worker.max_scope ?? '—'}</dd>
        <dt>{t('Job processes')}</dt><dd>{worker.details.worker_processes ?? '—'}</dd>
        <dt>{t('Uptime')}</dt><dd>{formatDuration(worker.details.uptime_seconds)}</dd>
        <dt>{t('Last seen')}</dt><dd>{worker.last_seen_at ? timeAgo(worker.last_seen_at) : t('Never')}</dd>
      </dl>

      {#if worker.details.broker?.queues}
        <div class="queues" aria-label={t('Jobs waiting')}>
          {#each Object.entries(worker.details.broker.queues) as [queue, depth] (queue)}
            <span class="queue" class:is-busy={depth > 0}>
              {t(QUEUE_LABELS[queue] ?? queue)}<b>{depth}</b>
            </span>
          {/each}
        </div>
      {/if}

      <div class="chips">
        <span class="chip" class:is-ok={worker.use_tls && worker.details.agent_tls !== false}>
          <i class={`bi ${worker.use_tls ? 'bi-lock-fill' : 'bi-unlock'}`} aria-hidden="true"></i>
          {worker.use_tls ? t('Agent over HTTPS') : t('Agent without TLS')}
        </span>
        {#if worker.details.ldap_tls_verify !== undefined}
          <span class="chip" class:is-ok={worker.details.ldap_tls_verify && worker.details.ldap_ca_file_present}>
            <i class="bi bi-patch-check" aria-hidden="true"></i>
            {worker.details.ldap_tls_verify ? (worker.details.ldap_ca_file_present ? t('LDAPS certificates checked') : t('LDAPS check on, CA missing')) : t('LDAPS certificates not checked')}
          </span>
        {/if}
      </div>

      <footer class="card__actions">
        <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" on:click={() => recheck(worker)} disabled={busyId === worker.id || !worker.is_enabled}>
          <i class={`bi ${busyId === worker.id ? 'bi-hourglass-split' : 'bi-arrow-repeat'}`} aria-hidden="true"></i>{t('Check')}
        </button>
        <button type="button" class="b2s-btn b2s-btn-ghost b2s-btn-sm" on:click={() => openEdit(worker)}>
          <i class="bi bi-pencil" aria-hidden="true"></i>{t('Edit')}
        </button>
        <button type="button" class="b2s-btn b2s-btn-ghost b2s-btn-sm" on:click={() => toggleEnabled(worker)} disabled={busyId === worker.id}>
          <i class={`bi ${worker.is_enabled ? 'bi-pause-circle' : 'bi-play-circle'}`} aria-hidden="true"></i>
          {worker.is_enabled ? t('Disable') : t('Enable')}
        </button>
        <button type="button" class="b2s-btn b2s-btn-danger-outline b2s-btn-sm card__remove" aria-label={t('Remove')} on:click={() => (removing = worker)}>
          <i class="bi bi-trash3" aria-hidden="true"></i>
        </button>
      </footer>
    </article>
  {/each}
</div>

<details class="howto">
  <summary><i class="bi bi-info-circle" aria-hidden="true"></i>{t('Prepare the agent of a worker')}</summary>
  <ol>
    <li>{t('On the worker (capsule-runner), set the agent credentials:')} <code>AGENT_USERNAME</code>, <code>AGENT_PASSWORD</code>.</li>
    <li>{t('For HTTPS, give its certificate and key:')} <code>AGENT_TLS_CERT</code>, <code>AGENT_TLS_KEY</code> {t('(port 8443 by default, AGENT_PORT).')}</li>
    <li>{t('Without certificate the agent answers in HTTP on port 8080 (AGENT_PORT to change it): internal network only, uncheck “HTTPS”.')}</li>
    <li>{t('Open the port from core-service to the worker only, then add the worker here with the same user name and password.')}</li>
    <li>{t('Certificate from a private authority: give it to core-service with B2S_AGENT_CA_FILE, or uncheck “Verify certificate”.')}</li>
  </ol>
</details>

<Drawer
  open={drawerOpen}
  title={editing ? t('Edit the worker') : t('Add a worker')}
  subtitle={editing ? editing.name : t('Reached through its HTTPS agent')}
  iconClass="bi bi-cpu"
  ariaLabelledby="infra-worker-drawer-title"
  onClose={closeDrawer}
>
  <div class="dform">
    <label class="f f--full">
      <span>{t('Name')}</span>
      <input bind:value={form.name} placeholder={t('Main worker')} autocomplete="off" />
      {#if showErrors && !form.name.trim()}<FieldError>{t('Required')}</FieldError>{/if}
    </label>
    <label class="f f--wide">
      <span>{t('IP address or DNS host name')}</span>
      <input bind:value={form.host} placeholder="worker01.example.com" autocomplete="off" spellcheck="false" />
      {#if showErrors && !form.host.trim()}<FieldError>{t('Required')}</FieldError>{/if}
    </label>
    <label class="f">
      <span>{t('Port')}</span>
      <input type="number" min="1" max="65535" bind:value={form.port} />
    </label>
    <label class="f">
      <span>{t('User name')}</span>
      <input bind:value={form.username} autocomplete="off" />
      {#if showErrors && !form.username.trim()}<FieldError>{t('Required')}</FieldError>{/if}
    </label>
    <label class="f f--wide">
      <span>{t('Password')}</span>
      <div class="b2s-input-with-action">
        <input type={showPassword ? 'text' : 'password'} bind:value={form.password} autocomplete="new-password" placeholder={editing ? t('Unchanged') : ''} />
        <button type="button" class="b2s-input-action" aria-label={showPassword ? t('Hide password') : t('Show password')} on:click={() => (showPassword = !showPassword)}>
          <i class={`bi ${showPassword ? 'bi-eye-slash' : 'bi-eye'}`} aria-hidden="true"></i>
        </button>
      </div>
      {#if showErrors && needsPassword && !form.password && !editing}<FieldError>{t('Required')}</FieldError>{/if}
      <small>{t('Stored in the secret broker, never shown again.')}</small>
    </label>
    <div class="toggles f--full">
      <label class="toggle">
        <input type="checkbox" class="cap-switch" checked={form.use_tls} on:change={(e) => setTls(e.currentTarget.checked)} />
        <span>{t('HTTPS (recommended)')}</span>
      </label>
      <label class="toggle" class:is-off={!form.use_tls}>
        <input type="checkbox" class="cap-switch" bind:checked={form.verify_tls} disabled={!form.use_tls} />
        <span>{t('Verify certificate')}</span>
      </label>
      {#if editing}
        <label class="toggle">
          <input type="checkbox" class="cap-switch" bind:checked={form.is_enabled} />
          <span>{t('Enabled')}</span>
        </label>
      {/if}
    </div>
    {#if !form.use_tls}
      <p class="warn f--full"><i class="bi bi-exclamation-triangle" aria-hidden="true"></i>{t('Without TLS the password travels unencrypted: internal network only.')}</p>
    {/if}

    {#if check}
      <div class={`result f--full is-${check.status}`} class:is-outdated={!checkFresh}>
        <i class={`bi ${check.status === 'healthy' ? 'bi-check-circle-fill' : check.status === 'degraded' ? 'bi-exclamation-circle-fill' : 'bi-x-circle-fill'}`} aria-hidden="true"></i>
        <div>
          <strong>{statusLabel(check.status)}</strong>
          <span>{check.message}</span>
          {#if check.details?.worker_processes !== undefined}
            <small>{t('{n} job processes · queue {queue}', { n: check.details.worker_processes, queue: check.details.broker?.reachable ? t('reachable') : t('unreachable') })}</small>
          {/if}
        </div>
      </div>
    {/if}
  </div>

  <svelte:fragment slot="footer">
    <div class="dfoot">
      <button type="button" class="b2s-btn b2s-btn-ghost" on:click={closeDrawer}>{t('Cancel')}</button>
      <button type="button" class="b2s-btn b2s-btn-secondary" on:click={runTest} disabled={testing || saving}>
        <i class={`bi ${testing ? 'bi-hourglass-split' : 'bi-plug'}`} aria-hidden="true"></i>{testing ? t('Testing…') : t('Test the agent')}
      </button>
      <button type="button" class="b2s-btn b2s-btn-primary" on:click={save} disabled={saving || testing}>
        {saving ? t('Saving…') : editing ? t('Save changes') : t('Add the worker')}
      </button>
    </div>
  </svelte:fragment>
</Drawer>

<ConfirmActionModal
  open={!!removing}
  title={t('Remove the worker')}
  subtitle={t('{name} is no longer checked. Jobs keep running on it while it consumes the queue.', { name: removing?.name ?? '' })}
  confirmLabel={t('Remove')}
  onConfirm={confirmRemove}
  onClose={() => (removing = null)}
/>

<style>
  .toolbar {
    display: flex;
    align-items: center;
    gap: 14px;
    justify-content: space-between;
    margin-bottom: 14px;
  }

  .toolbar p {
    margin: 0;
    color: var(--b2s-color-text-soft);
    font-size: var(--b2s-fs-sm);
  }

  .empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    padding: 36px 16px;
    border: 1px dashed var(--b2s-color-border-mid);
    border-radius: var(--b2s-radius-md);
    color: var(--b2s-color-text-muted);
    text-align: center;
    margin-bottom: 14px;
  }

  .empty i {
    font-size: 1.8rem;
    color: var(--b2s-color-text-faint);
  }

  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
    gap: 12px;
  }

  .card {
    display: grid;
    gap: 12px;
    padding: 16px;
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-md);
    background: var(--b2s-color-surface);
  }

  .card.is-disabled {
    opacity: 0.7;
  }

  .card__head {
    display: grid;
    grid-template-columns: auto 1fr auto;
    gap: 10px;
    align-items: center;
  }

  .card__icon {
    width: 38px;
    height: 38px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--b2s-radius-sm);
    background: var(--b2s-color-neutral-soft);
    color: var(--b2s-color-text-muted);
    font-size: 1.15rem;
  }

  .card__icon.is-healthy {
    background: var(--b2s-color-success-soft);
    color: var(--b2s-color-success-strong);
  }

  .card__icon.is-degraded {
    background: var(--b2s-color-warning-soft);
    color: var(--b2s-color-warning-strong);
  }

  .card__icon.is-down {
    background: var(--b2s-color-danger-soft);
    color: var(--b2s-color-danger-strong);
  }

  .card__title {
    min-width: 0;
    display: grid;
  }

  .card__title strong {
    color: var(--b2s-color-heading);
  }

  .card__title span {
    font-size: var(--b2s-fs-xs);
    color: var(--b2s-color-text-muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .card__msg {
    margin: 0;
    font-size: var(--b2s-fs-xs);
    padding: 6px 10px;
    border-radius: var(--b2s-radius-sm);
    background: var(--b2s-color-surface-soft);
    color: var(--b2s-color-text-soft);
  }

  .card__msg.is-down {
    background: var(--b2s-color-danger-soft);
    color: var(--b2s-color-danger-strong);
  }

  .card__msg.is-degraded {
    background: var(--b2s-color-warning-soft);
    color: var(--b2s-color-warning-strong);
  }

  .facts {
    display: grid;
    grid-template-columns: repeat(2, max-content minmax(0, 1fr));
    gap: 6px 10px;
    margin: 0;
    font-size: var(--b2s-fs-xs);
  }

  .facts dt {
    color: var(--b2s-color-text-muted);
  }

  .facts dd {
    margin: 0;
    color: var(--b2s-color-text);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .mono {
    font-family: var(--b2s-font-mono);
  }

  .queues,
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .queue {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 8px;
    border-radius: var(--b2s-radius-pill);
    background: var(--b2s-color-neutral-soft);
    font-size: var(--b2s-fs-xs);
    color: var(--b2s-color-text-soft);
  }

  .queue b {
    color: var(--b2s-color-text);
  }

  .queue.is-busy {
    background: #e0e7ff;
    color: #3730a3;
  }

  .chip {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 3px 8px;
    border-radius: var(--b2s-radius-pill);
    border: 1px solid #fde68a;
    background: #fffbeb;
    font-size: var(--b2s-fs-xs);
    color: var(--b2s-color-warning-strong);
  }

  .chip.is-ok {
    border-color: var(--b2s-color-success-border);
    background: var(--b2s-color-success-soft);
    color: var(--b2s-color-success-strong);
  }

  .card__actions {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    border-top: 1px solid var(--b2s-color-neutral-soft);
    padding-top: 10px;
  }

  .card__remove {
    margin-left: auto;
  }

  .howto {
    margin-top: 16px;
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-md);
    background: var(--b2s-color-surface-soft);
    padding: 10px 14px;
    font-size: var(--b2s-fs-sm);
    color: var(--b2s-color-text-strong);
  }

  .howto summary {
    cursor: pointer;
    font-weight: 600;
    display: flex;
    gap: 8px;
    align-items: center;
  }

  .howto ol {
    margin: 10px 0 0;
    padding-left: 20px;
    display: grid;
    gap: 6px;
  }

  .dform {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
  }

  .f {
    display: grid;
    align-content: start;
    gap: 4px;
    min-width: 0;
  }

  .f--wide {
    grid-column: span 2;
  }

  .f--full {
    grid-column: 1 / -1;
  }

  .f span {
    font-size: var(--b2s-fs-xs);
    font-weight: 600;
    color: var(--b2s-color-text-strong);
  }

  .f small {
    font-size: var(--b2s-fs-xs);
    color: var(--b2s-color-text-muted);
  }

  .f input {
    width: 100%;
    height: 38px;
    padding: 0 12px;
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-sm);
    font-size: var(--b2s-fs-sm);
    color: var(--b2s-color-heading);
  }

  .f input:focus {
    outline: 0;
    border-color: #8db5ff;
    box-shadow: 0 0 0 3px rgba(11, 99, 244, 0.12);
  }

  .toggles {
    display: flex;
    flex-wrap: wrap;
    gap: 18px;
  }

  .toggle {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: var(--b2s-fs-sm);
    color: var(--b2s-color-text-strong);
    cursor: pointer;
  }

  .toggle.is-off {
    opacity: 0.5;
  }





  .warn {
    margin: 0;
    display: flex;
    gap: 8px;
    font-size: var(--b2s-fs-xs);
    color: var(--b2s-color-warning-strong);
  }

  .result {
    display: flex;
    gap: 10px;
    padding: 10px 12px;
    border-radius: var(--b2s-radius-sm);
    font-size: var(--b2s-fs-sm);
    border: 1px solid var(--b2s-color-border-soft);
  }

  .result div {
    display: grid;
    gap: 2px;
  }

  .result small {
    color: inherit;
    opacity: 0.85;
  }

  .result.is-healthy {
    background: var(--b2s-color-success-soft);
    border-color: var(--b2s-color-success-border);
    color: #14532d;
  }

  .result.is-degraded {
    background: #fffbeb;
    border-color: #fde68a;
    color: #78350f;
  }

  .result.is-down,
  .result.is-unknown {
    background: var(--b2s-color-danger-soft);
    border-color: var(--b2s-color-danger-border);
    color: var(--b2s-color-danger-strong);
  }

  .result.is-outdated {
    opacity: 0.65;
  }

  .dfoot {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
    width: 100%;
  }

</style>
