<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { FetchLike } from '$lib/api/client';
  import type { ProbeRunRequest } from '$lib/api/probes';
  import { runCapsuleProbe } from '$lib/probe/probe-runner';
  import { normalizeProbeError, type NormalizedProbeError } from '$lib/probe/probe-errors';
  import ProbePanel from './ProbePanel.svelte';

  export let fetchFn: FetchLike;
  export let request: ProbeRunRequest | null = null;
  export let requestFactory: (() => ProbeRunRequest | null | Promise<ProbeRunRequest | null>) | null = null;

  export let mode: 'inline' | 'detailed' = 'inline';
  export let label = 'Run probe';
  export let busyLabel = 'Running…';
  export let disabled = false;
  export let fullWidth = false;
  export let showIcon = false;
  export let iconClass = 'bi bi-activity';
  export let busyIconClass = 'bi bi-hourglass-split';
  export let buttonClass = '';
  export let hideSuccessPanel = false;

  /** Optional hook executed right before running the probe (ex: store secret). */
  export let beforeRun: (() => Promise<void>) | null = null;

  const dispatch = createEventDispatcher<{
    done: { ok: boolean; status: string; jobId?: string; error?: NormalizedProbeError };
  }>();

  let running = false;
  let ok: boolean | null = null;
  let status: string | null = null;
  let result: any = null;
  let error: NormalizedProbeError | null = null;
  $: shouldShowProbePanel = ok === true ? !hideSuccessPanel : (ok !== null || result);

  async function run() {
    error = null;
    ok = null;
    status = null;
    result = null;

    running = true;
    try {
      if (beforeRun) await beforeRun();
      const resolvedRequest = requestFactory ? await requestFactory() : request;
      if (!resolvedRequest) {
        error = { type: 'VALIDATION', message: 'Missing required fields.' };
        dispatch('done', { ok: false, status: 'failed', error });
        return;
      }
      const out = await runCapsuleProbe({
        fetchFn,
        request: resolvedRequest,
        intervalMs: 1500,
        maxAttempts: 40,
        onUpdate: (snap) => {
          status = snap.status;
        }
      });

      if (out.ok) {
        ok = true;
        status = out.result.status;
        result = out.result.result;
        dispatch('done', { ok: true, status: out.result.status, jobId: out.result.jobId });
      } else {
        ok = false;
        status = out.result?.status ?? 'failed';
        result = out.result?.result;
        error = out.error;
        dispatch('done', { ok: false, status: status ?? 'failed', jobId: out.result?.jobId, error: out.error });
      }
    } catch (e) {
      ok = false;
      status = 'failed';
      result = null;
      error = normalizeProbeError(e);
      dispatch('done', { ok: false, status: 'failed', error });
    } finally {
      running = false;
    }
  }
</script>

<div class="run-probe" class:run-probe--full={fullWidth}>
  <button
    type="button"
    class={buttonClass}
    on:click={run}
    disabled={disabled || running}
  >
    {#if showIcon}
      <i class={running ? busyIconClass : iconClass} aria-hidden="true"></i>
    {/if}
    <span>{running ? busyLabel : label}</span>
  </button>

  {#if error}
    <div class="probe-error {error.type}">
      <strong>{error.message}</strong>
      {#if error.technical}
        <details>
          <summary>Technical details</summary>
          <pre>{error.technical}</pre>
        </details>
      {/if}
    </div>
  {/if}

  {#if shouldShowProbePanel}
    <ProbePanel {mode} {ok} {status} {result} errorMessage={error?.message ?? null} />
  {/if}
</div>

<style>
  .run-probe {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .run-probe--full {
    width: 100%;
  }

  .run-probe--full button {
    width: 100%;
    justify-content: center;
  }

  .probe-error {
    padding: 10px 12px;
    border-radius: 12px;
    border: 1px solid rgba(0, 0, 0, 0.08);
    background: rgba(0, 0, 0, 0.02);
    font-size: 0.92rem;
  }

  .run-probe button {
    display: inline-flex;
    align-items: center;
    gap: 8px;
  }
  .probe-error.NETWORK { background: #fff3e0; }
  .probe-error.TIMEOUT { background: #fff8e1; }
  .probe-error.SECRET { background: #f3e5f5; }
  .probe-error.CAPSULE { background: #ffebee; }
  .probe-error.VALIDATION { background: #e8f0fe; }

  pre { white-space: pre-wrap; }
</style>
