<script lang="ts">
  import Drawer from '$lib/components/ui/Drawer.svelte';
  import { renderActivity } from '$lib/activity/formatter';

  export let open = false;
  export let entry: any | null = null;
  export let onClose: (() => void) | null = null;
  export let width = '620px';
  export let topOffset = '0px';
  export let titleFallback = 'Activity details';
  export let subtitleFallback = 'Detailed payload from current logging data';

  function toDetailRows(value: unknown): Array<{ key: string; before: string; after: string }> {
    const obj = value && typeof value === 'object' ? (value as Record<string, unknown>) : null;
    if (!obj) return [];

    const before =
      obj.before && typeof obj.before === 'object' ? (obj.before as Record<string, unknown>) : {};
    const after =
      obj.after && typeof obj.after === 'object' ? (obj.after as Record<string, unknown>) : {};
    const updatedFields = Array.isArray(obj.updated_fields)
      ? obj.updated_fields.map((f) => String(f ?? '').trim()).filter(Boolean)
      : [];

    const keys = new Set<string>([
      ...Object.keys(before),
      ...Object.keys(after),
      ...updatedFields
    ]);

    return Array.from(keys)
      .sort((a, b) => a.localeCompare(b, 'en'))
      .map((field) => {
        const beforeValue = (before as Record<string, unknown>)[field];
        const afterValue = (after as Record<string, unknown>)[field];
        return {
          key: field,
          before: beforeValue == null ? '—' : String(beforeValue),
          after: afterValue == null ? '—' : String(afterValue)
        };
      });
  }

  const formatDateTime = (value: unknown): string => {
    const raw = String(value ?? '').trim();
    if (!raw) return '—';
    const d = new Date(raw);
    if (!Number.isFinite(d.getTime())) return raw;
    return d.toLocaleString('en-GB', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  };

  const contextOf = (activityEntry: any): Record<string, unknown> | null => {
    const candidates = [activityEntry?.context_json, activityEntry?.metadata_json];
    for (const candidate of candidates) {
      if (candidate && typeof candidate === 'object') return candidate as Record<string, unknown>;
      if (typeof candidate === 'string' && candidate.trim()) {
        try {
          const parsed = JSON.parse(candidate);
          if (parsed && typeof parsed === 'object') return parsed as Record<string, unknown>;
        } catch {
          // Ignore malformed payload.
        }
      }
    }
    return null;
  };

  $: rendered = entry ? renderActivity(entry) : null;
  $: context = contextOf(entry);
  $: changeRows = toDetailRows(context);
</script>

<Drawer
  {open}
  title={rendered?.title ?? titleFallback}
  subtitle={rendered?.description ?? subtitleFallback}
  {width}
  {topOffset}
  showFooter={false}
  onClose={() => onClose?.()}
>
  {#if entry}
    <div class="activity-details-drawer__meta">
      <div><strong>Action</strong><span>{String(entry?.action ?? '—')}</span></div>
      <div><strong>Severity</strong><span>{String(entry?.severity ?? entry?.outcome ?? 'info')}</span></div>
      <div><strong>Date & time</strong><span>{formatDateTime(entry?.created_at ?? entry?.event_time)}</span></div>
      <div><strong>Target</strong><span>{String(entry?.target_display ?? '—')}</span></div>
    </div>

    {#if changeRows.length > 0}
      <div class="activity-details-drawer__section">
        <h3>Changed values</h3>
        <div class="activity-details-drawer__table" role="table" aria-label="Changed values">
          <div role="row" class="head">
            <span role="columnheader">Field</span>
            <span role="columnheader">Before</span>
            <span role="columnheader">After</span>
          </div>
          {#each changeRows as row}
            <div role="row">
              <span role="cell">{row.key}</span>
              <span role="cell">{row.before}</span>
              <span role="cell">{row.after}</span>
            </div>
          {/each}
        </div>
      </div>
    {/if}

    <div class="activity-details-drawer__section">
      <h3>Raw context</h3>
      <pre>{JSON.stringify(context ?? {}, null, 2)}</pre>
    </div>
  {/if}
</Drawer>

<style>
  .activity-details-drawer__meta {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.7rem;
    margin-bottom: 0.9rem;
  }

  .activity-details-drawer__meta > div {
    display: grid;
    gap: 0.15rem;
    padding: 0.55rem 0.65rem;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    background: #f8fafc;
  }

  .activity-details-drawer__meta strong {
    font-size: 0.78rem;
    color: #64748b;
    font-weight: 700;
  }

  .activity-details-drawer__meta span {
    font-size: 0.9rem;
    color: #0f172a;
    word-break: break-word;
  }

  .activity-details-drawer__section {
    margin-top: 0.8rem;
  }

  .activity-details-drawer__section h3 {
    margin: 0 0 0.45rem;
    font-size: 0.9rem;
    font-weight: 700;
    color: #334155;
  }

  .activity-details-drawer__table {
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    overflow: hidden;
  }

  .activity-details-drawer__table > div {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 0;
  }

  .activity-details-drawer__table > div > span {
    padding: 0.5rem 0.6rem;
    border-bottom: 1px solid #edf2f7;
    border-right: 1px solid #edf2f7;
    font-size: 0.84rem;
    color: #0f172a;
    word-break: break-word;
  }

  .activity-details-drawer__table > div > span:last-child {
    border-right: none;
  }

  .activity-details-drawer__table > div.head {
    background: #f8fafc;
  }

  .activity-details-drawer__table > div.head > span {
    font-weight: 700;
    color: #334155;
  }

  .activity-details-drawer__section pre {
    margin: 0;
    padding: 0.7rem;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    background: #0f172a;
    color: #e2e8f0;
    font-size: 0.78rem;
    max-height: 260px;
    overflow: auto;
  }
</style>
