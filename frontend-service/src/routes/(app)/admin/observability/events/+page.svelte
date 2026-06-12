<script lang="ts">
  import { formatActivityItem } from '$lib/activity/format';

  type UiSeverity = 'Info' | 'Warning' | 'Error' | 'Audit success';
  type SeverityTone = 'info' | 'warning' | 'error' | 'success';

  type EventRow = {
    id: string | number;
    timestampModule: string;
    severityLabel: UiSeverity;
    severityTone: SeverityTone;
    severityIcon: string;
    timeSort: number;
    action: string;
    actor: string;
    target: string;
    details: string;
    module: string;
    searchText: string;
  };

  export let data: { items: any[]; generatedAt?: string };

  let q = '';

  const prettyToken = (value: unknown): string => {
    const raw = String(value ?? '').trim();
    if (!raw) return 'Platform';
    return raw
      .replace(/[._-]+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
      .replace(/\b\w/g, (m) => m.toUpperCase());
  };

  const moduleFromEvent = (entry: any): string => {
    const targetType = String(entry?.target_type ?? '').trim();
    if (targetType) return prettyToken(targetType);

    const action = String(entry?.action ?? '').trim();
    if (!action) return 'Platform';

    if (action.includes('.')) return prettyToken(action.split('.')[0]);

    const prefix = action.match(/^(zone|storage_root|storage_endpoint|access_profile|access_request|identity_source|security|tag|role|member|api)/)?.[1];
    if (prefix) return prettyToken(prefix);

    const parts = action.split('_').filter(Boolean);
    if (parts.length >= 2) return prettyToken(`${parts[0]}_${parts[1]}`);
    return prettyToken(parts[0] ?? action);
  };

  const toTimeLabel = (value: unknown): string => {
    const text = String(value ?? '').trim();
    if (!text) return '—';
    const d = new Date(text);
    if (Number.isNaN(d.getTime())) return text;
    return d.toLocaleString('en-GB', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  };

  const actionLabel = (entry: any): string => {
    const raw = String(entry?.action ?? entry?.event ?? '').trim();
    if (!raw) return 'event';
    if (raw.includes('.')) {
      const [prefix, suffix] = raw.split('.', 2);
      return `${prettyToken(prefix)} · ${prettyToken(suffix)}`;
    }
    return prettyToken(raw);
  };

  const targetLabel = (entry: any): string => {
    const type = String(entry?.target_type ?? entry?.entity_type ?? '').trim();
    const display = String(entry?.target_display ?? '').trim();
    const id = String(entry?.target_id ?? entry?.entity_id ?? '').trim();
    const left = type ? prettyToken(type) : 'Platform';
    if (display) return `${left} · ${display}`;
    if (id) return `${left} #${id}`;
    return left;
  };

  const normalizeDetailValue = (value: unknown): string => {
    if (value == null) return '∅';
    const text = String(value).trim();
    return text || '∅';
  };

  const detailsLabel = (entry: any): string => {
    const changes = Array.isArray(entry?.details_changes) ? entry.details_changes : [];
    if (changes.length > 0) {
      return changes
        .slice(0, 2)
        .map((c: any) => {
          const field = prettyToken(c?.field ?? 'field');
          const from = normalizeDetailValue(c?.from);
          const to = normalizeDetailValue(c?.to);
          return `${field}: ${from} → ${to}`;
        })
        .join(' · ');
    }

    const rendered = formatActivityItem(entry);
    const details = String(rendered?.subtitle1 ?? '').trim();
    if (details) return details;
    return 'No field change';
  };

  const severityMeta = (
    entry: any,
    badgeKind?: 'info' | 'admin' | 'critical'
  ): { label: UiSeverity; tone: SeverityTone; icon: string } => {
    const raw = String(entry?.severity ?? entry?.level ?? '').toLowerCase();
    const outcome = String(entry?.outcome ?? entry?.result ?? '').toLowerCase();

    if (
      raw === 'critical' ||
      raw === 'high' ||
      raw === 'error' ||
      raw === 'fatal' ||
      outcome === 'failed' ||
      badgeKind === 'critical'
    ) {
      return { label: 'Error', tone: 'error', icon: 'bi-x-circle-fill' };
    }

    if (raw === 'warning' || raw === 'warn' || raw === 'medium') {
      return { label: 'Warning', tone: 'warning', icon: 'bi-exclamation-triangle-fill' };
    }

    if (raw === 'audit_success' || raw === 'audit' || (badgeKind === 'admin' && outcome !== 'failed')) {
      return { label: 'Audit success', tone: 'success', icon: 'bi-check-circle-fill' };
    }

    return { label: 'Info', tone: 'info', icon: 'bi-info-circle-fill' };
  };

  $: rows = (Array.isArray(data?.items) ? data.items : [])
    .map((entry: any): EventRow => {
      const rendered = formatActivityItem(entry);
      const sev = severityMeta(entry, rendered?.badgeKind);
      const tsRaw = entry?.created_at ?? entry?.event_time ?? entry?.timestamp;
      const parsedTs = Number.isNaN(new Date(String(tsRaw ?? '')).getTime())
        ? 0
        : new Date(String(tsRaw)).getTime();

      const module = moduleFromEvent(entry);
      const time = toTimeLabel(tsRaw);
      const actor = String(entry?.actor_display_name ?? entry?.actor_display ?? entry?.actor ?? 'system');
      const action = actionLabel(entry);
      const target = targetLabel(entry);
      const details = detailsLabel(entry);

      return {
        id: entry?.id ?? `${entry?.created_at ?? ''}-${entry?.action ?? ''}`,
        timestampModule: `${time} · ${module}`,
        severityLabel: sev.label,
        severityTone: sev.tone,
        severityIcon: sev.icon,
        timeSort: parsedTs,
        action,
        actor,
        target,
        details,
        module,
        searchText: `${sev.label} ${module} ${action} ${actor} ${target} ${details}`.toLowerCase()
      };
    })
    .sort((a, b) => b.timeSort - a.timeSort);

  $: filtered = rows.filter((row) => !q.trim() || row.searchText.includes(q.toLowerCase().trim()));
  $: updatedAt = toTimeLabel(data?.generatedAt ?? null);
</script>

<div class="container-fluid events-page">
  <div class="events-head">
    <div>
      <h1 class="events-title">Events</h1>
      <div class="events-subtitle">All platform actions from activity logs</div>
    </div>
    <div class="events-updated">Updated {updatedAt}</div>
  </div>

  <div class="events-toolbar card b2s-card">
    <div class="card-body d-flex align-items-center justify-content-between gap-3 flex-wrap">
      <div class="d-flex align-items-center gap-2">
        <label class="events-label" for="events-time-range">Time Period</label>
        <select id="events-time-range" class="form-select form-select-sm" style="width: 140px" disabled>
          <option>Last 2 days</option>
        </select>
      </div>

      <div class="events-filter-wrap">
        <i class="bi bi-funnel" aria-hidden="true"></i>
        <input
          class="form-control"
          placeholder="Filter"
          aria-label="Filter events"
          bind:value={q}
        />
      </div>
    </div>
  </div>

  <div class="card b2s-card events-table-card">
    <div class="card-body p-0">
      <div class="table-responsive">
        <table class="table events-table mb-0 align-middle">
          <thead>
            <tr>
              <th>Timestamp / Module</th>
              <th>Severity</th>
              <th>Action</th>
              <th>Actor</th>
              <th>Target</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            {#if filtered.length === 0}
              <tr>
                <td colspan={6} class="events-empty">No events found.</td>
              </tr>
            {:else}
              {#each filtered as row (row.id)}
                <tr>
                  <td class="events-col-time-module">{row.timestampModule}</td>
                  <td class="events-col-severity">
                    <span class={`events-severity events-severity--${row.severityTone}`}>
                      <i class={`bi ${row.severityIcon}`} aria-hidden="true"></i>
                      <span>{row.severityLabel}</span>
                    </span>
                  </td>
                  <td class="events-col-action" title={row.action}>{row.action}</td>
                  <td class="events-col-actor" title={row.actor}>{row.actor}</td>
                  <td class="events-col-target" title={row.target}>{row.target}</td>
                  <td class="events-col-details" title={row.details}>{row.details}</td>
                </tr>
              {/each}
            {/if}
          </tbody>
        </table>
      </div>
    </div>
  </div>
</div>

<style>
  .events-page {
    display: grid;
    gap: 12px;
  }

  .events-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
  }

  .events-title {
    margin: 0;
    font-size: 1.5rem;
    font-weight: 700;
    color: #0f172a;
  }

  .events-subtitle {
    color: #64748b;
    font-size: 0.9rem;
    margin-top: 2px;
  }

  .events-updated {
    color: #64748b;
    font-size: 0.87rem;
    white-space: nowrap;
    margin-top: 8px;
  }

  .events-toolbar .card-body {
    padding: 0.7rem 0.9rem;
  }

  .events-label {
    font-size: 0.86rem;
    color: #334155;
    font-weight: 600;
  }

  .events-filter-wrap {
    min-width: 260px;
    width: min(420px, 100%);
    position: relative;
  }

  .events-filter-wrap i {
    position: absolute;
    left: 10px;
    top: 50%;
    transform: translateY(-50%);
    color: #64748b;
    pointer-events: none;
  }

  .events-filter-wrap input {
    padding-left: 32px;
  }

  .events-table-card {
    overflow: hidden;
  }

  .events-table {
    table-layout: fixed;
  }

  .events-table thead th {
    font-size: 0.86rem;
    font-weight: 700;
    color: #334155;
    background: #f8fafc;
    border-bottom: 1px solid #e2e8f0;
    white-space: nowrap;
  }

  .events-table tbody td {
    font-size: 0.87rem;
    color: #0f172a;
    border-color: #e2e8f0;
    vertical-align: middle;
  }

  .events-col-time-module {
    width: 240px;
    color: #334155;
    white-space: nowrap;
    font-weight: 500;
  }

  .events-col-severity {
    width: 170px;
  }

  .events-col-action {
    width: 170px;
    color: #1e293b;
    font-weight: 500;
  }

  .events-col-actor {
    width: 150px;
    color: #334155;
  }

  .events-col-target {
    width: 190px;
    color: #334155;
  }

  .events-col-details {
    color: #334155;
  }

  .events-empty {
    color: #64748b;
    text-align: center;
    padding: 24px;
  }

  .events-severity {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: 0.82rem;
    font-weight: 600;
    line-height: 1;
  }

  .events-severity--info {
    color: #0369a1;
  }

  .events-severity--warning {
    color: #b45309;
  }

  .events-severity--error {
    color: #b91c1c;
  }

  .events-severity--success {
    color: #15803d;
  }
</style>
