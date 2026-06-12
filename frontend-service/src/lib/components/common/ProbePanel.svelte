<script lang="ts">
  /**
   * Generic probe result display.
   * Accepts either ProbeRunResult or job.result payload.
   */
  export let mode: 'inline' | 'detailed' = 'inline';
  export let ok: boolean | null = null;
  export let status: string | null = null;
  export let result: any = null;
  export let errorMessage: string | null = null;
  export let lastRunAt: string | null = null;
  export let durationMs: number | null = null;
  export let jobId: string | number | null = null;
  export let technicalHref: string | null = null;
  export let technicalLabel = 'Technical details';
  export let retryLabel = 'Retry';
  export let onRetry: (() => void) | null = null;

  const asChecks = (r: any) => {
    const checks = r?.checks;
    if (Array.isArray(checks)) return checks;
    if (Array.isArray(r?.result?.checks)) return r.result.checks;
    if (Array.isArray(r?.details?.checks)) return r.details.checks;
    return [];
  };

  const text = (value: unknown) => String(value ?? '').trim();
  const checkKey = (check: any, index: number) => text(check?.key) || text(check?.name) || `check-${index}`;
  const checkLabel = (check: any) => (text(check?.label) || text(check?.name) || text(check?.key) || 'Probe step').replaceAll('_', ' ');
  const checkOk = (check: any) => {
    const rawStatus = text(check?.status).toLowerCase();
    if (typeof check?.ok === 'boolean') return check.ok;
    if (rawStatus === 'success' || rawStatus === 'ok' || rawStatus === 'passed') return true;
    if (rawStatus === 'failed' || rawStatus === 'error') return false;
    return null;
  };
  const formatDateTime = (value: string | null) => {
    if (!value) return null;
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return new Intl.DateTimeFormat('fr-FR', {
      dateStyle: 'short',
      timeStyle: 'short'
    }).format(date);
  };
  const formatDuration = (value: number | null) => {
    if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) return null;
    if (value < 1000) return `${Math.round(value)} ms`;
    return `${(value / 1000).toFixed(value < 10000 ? 1 : 0)} s`;
  };

  $: checks = asChecks(result);
  $: banner = ok === true ? 'success' : ok === false ? 'danger' : 'info';
  $: title = ok === true ? 'Probe OK' : ok === false ? 'Probe failed' : 'Probe';
  $: iconClass = ok === true ? 'bi-check2-circle' : ok === false ? 'bi-x-circle' : 'bi-activity';
  $: lastRunLabel = formatDateTime(lastRunAt);
  $: durationLabel = formatDuration(durationMs);
</script>

<div class="probe-panel {mode}">
  <div class="probe-summary {banner}">
    <div class="probe-title">
      <i class={`bi ${iconClass}`} aria-hidden="true"></i>
      <span>{title}</span>
    </div>
    <div class="probe-actions">
      {#if status}
        <div class="probe-status">{status}</div>
      {/if}
      {#if onRetry}
        <button type="button" on:click={onRetry}>{retryLabel}</button>
      {/if}
    </div>
  </div>

  {#if lastRunLabel || durationLabel || jobId}
    <div class="probe-meta">
      {#if lastRunLabel}<span>Dernier run {lastRunLabel}</span>{/if}
      {#if durationLabel}<span>Durée {durationLabel}</span>{/if}
      {#if jobId}<span>Job #{jobId}</span>{/if}
    </div>
  {/if}

  {#if errorMessage}
    <div class="probe-error">{errorMessage}</div>
  {/if}

  {#if mode === 'detailed' && checks.length}
    <div class="probe-checks">
      {#each checks as c, index (checkKey(c, index))}
        {@const stepOk = checkOk(c)}
        <div class={`probe-check is-${stepOk === true ? 'success' : stepOk === false ? 'danger' : 'info'}`}>
          <span class="probe-check-icon">
            <i class={`bi ${stepOk === true ? 'bi-check2' : stepOk === false ? 'bi-x-lg' : 'bi-hourglass-split'}`} aria-hidden="true"></i>
          </span>
          <span class="probe-check-key">{checkLabel(c)}</span>
          {#if c.message}
            <span class="probe-check-msg">{c.message}</span>
          {/if}
        </div>
      {/each}
    </div>
  {/if}

  {#if technicalHref}
    <a class="probe-technical-link" href={technicalHref}>{technicalLabel}</a>
  {:else if mode === 'detailed' && result}
    <details class="probe-raw">
      <summary>{technicalLabel}</summary>
      <pre>{JSON.stringify(result, null, 2)}</pre>
    </details>
  {/if}
</div>

<style>
  .probe-panel {
    display: flex;
    flex-direction: column;
    gap: 10px;
    border: 1px solid rgba(0, 0, 0, 0.08);
    border-radius: 12px;
    padding: 12px;
    background: white;
  }
  .probe-panel.inline {
    padding: 10px;
  }
  .probe-summary {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    font-weight: 600;
  }
  .probe-summary.success { color: #166534; }
  .probe-summary.danger { color: #991b1b; }
  .probe-summary.info { color: #1f2937; }

  .probe-title,
  .probe-actions {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }

  .probe-actions button {
    height: 30px;
    border: 1px solid #d5e0ef;
    border-radius: 8px;
    background: #fff;
    color: #102243;
    font-size: 12px;
    font-weight: 700;
    padding: 0 10px;
  }

  .probe-status {
    font-weight: 500;
    opacity: 0.75;
    font-size: 0.9rem;
  }
  .probe-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 14px;
    color: #5d6f89;
    font-size: 0.82rem;
    font-weight: 600;
  }
  .probe-error {
    color: #991b1b;
    font-size: 0.9rem;
  }
  .probe-checks { display: grid; gap: 8px; }
  .probe-check { display: flex; gap: 10px; align-items: baseline; }
  .probe-check.is-success { color: #166534; }
  .probe-check.is-danger { color: #991b1b; }
  .probe-check.is-info { color: #475569; }
  .probe-check-key { font-weight: 600; min-width: 140px; }
  .probe-check-msg { opacity: 0.8; font-size: 0.9rem; }
  .probe-technical-link {
    width: fit-content;
    color: #0a5de8;
    font-size: 0.9rem;
    font-weight: 700;
    text-decoration: none;
  }
  .probe-raw pre {
    max-height: 260px;
    overflow: auto;
    background: rgba(0,0,0,0.03);
    padding: 10px;
    border-radius: 10px;
  }
</style>
