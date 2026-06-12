<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { formatActivityItem } from '$lib/activity/format';

  export let items: any[] = [];
  export let emptyLabel = 'No activity available';
  export let clickableRows = false;

  type ActivityTone = 'critical' | 'warning' | 'success' | 'info' | 'sync' | 'neutral' | 'access';

  type ActivityRow = {
    id: string;
    raw: any;
    timestampMs: number | null;
    timeLabel: string;
    typeLabel: string;
    tone: ActivityTone;
    icon: string;
    title: string;
    description: string;
    actor: string;
    actorSubtitle: string;
    actorInitials: string;
    source: string;
    searchable: string;
  };

  const dispatch = createEventDispatcher<{
    rowclick: { entry: any; row: ActivityRow; index: number };
  }>();

  let query = '';
  let dateFilter = 'all';
  let typeFilter = 'all';
  let actorFilter = 'all';
  let currentPage = 1;
  const rowsPerPage = 8;

  const isRecord = (value: unknown): value is Record<string, unknown> =>
    Boolean(value) && typeof value === 'object' && !Array.isArray(value);

  const firstString = (...values: unknown[]) => {
    for (const value of values) {
      if (value == null) continue;
      if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
        const text = String(value).trim();
        if (text) return text;
      }
      if (isRecord(value)) {
        const text = firstString(
          value.display_name,
          value.displayName,
          value.name,
          value.label,
          value.title,
          value.username,
          value.email,
          value.id
        );
        if (text) return text;
      }
    }
    return '';
  };

  const eventContext = (entry: any) => {
    const context = isRecord(entry?.context_json) ? entry.context_json : {};
    const metadata = isRecord(entry?.metadata_json) ? entry.metadata_json : {};
    const nestedContext = isRecord((context as any)?.context_json) ? (context as any).context_json : {};
    return { ...nestedContext, ...context, ...metadata };
  };

  const parseTimestamp = (entry: any) => {
    const raw = firstString(entry?.event_time, entry?.created_at, entry?.timestamp, entry?.time);
    if (!raw) return null;
    const parsed = new Date(raw);
    return Number.isNaN(parsed.getTime()) ? null : parsed.getTime();
  };

  const formatTime = (timestampMs: number | null, entry: any) => {
    if (!timestampMs) return firstString(entry?.event_time, entry?.created_at, entry?.timestamp, entry?.time) || '-';
    return new Date(timestampMs).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    });
  };

  const humanize = (value: unknown) => {
    const text = firstString(value);
    if (!text) return 'Activity';
    return text
      .replace(/^[a-z0-9]+[._-]/i, '')
      .replace(/[._-]+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
      .replace(/\b\w/g, (char) => char.toUpperCase());
  };

  const actorLabel = (entry: any, ctx: Record<string, unknown>) => {
    const label = firstString(
      entry?.actor_display_name,
      entry?.actor_display,
      entry?.actor_name,
      entry?.actor_username,
      entry?.actor_email,
      entry?.actor,
      ctx.actor_display_name,
      ctx.actor_name,
      ctx.performed_by,
      ctx.deleted_by
    );

    if (!label || label.toLowerCase() === 'system') return 'System';
    return label;
  };

  const actorRole = (entry: any, ctx: Record<string, unknown>) => {
    const role = firstString(ctx.actor_role, ctx.role, entry?.actor_role, entry?.actor_type);
    if (!role || role.toLowerCase() === 'system') return '';
    return humanize(role);
  };

  const initials = (label: string) => {
    if (!label || label === 'System') return 'SY';
    const parts = label.split(/[\s._-]+/).filter(Boolean);
    const chars = parts.length >= 2 ? `${parts[0][0]}${parts[1][0]}` : label.slice(0, 2);
    return chars.toUpperCase();
  };

  const sourceLabel = (entry: any, ctx: Record<string, unknown>, action: string) => {
    const explicit = firstString(
      entry?.source_display,
      entry?.source_service,
      entry?.source,
      ctx.source_display,
      ctx.source_label,
      ctx.source,
      ctx.job_type,
      ctx.probe_type
    );
    if (explicit) return humanize(explicit);

    const normalized = action.toLowerCase();
    if (normalized.includes('probe') || normalized.startsWith('test_')) return 'Probe';
    if (normalized.includes('provision') || normalized.includes('ad_group')) return 'Provisioning job';
    if (normalized.includes('policy') || normalized.includes('config')) return 'Configuration check';
    if (normalized.includes('access_request')) return 'Access request';
    if (normalized.includes('sync') || normalized.includes('snapshot')) return 'Sync job';
    if (actorLabel(entry, ctx) === 'System') return 'System';
    return 'Manual action';
  };

  const classify = (entry: any, title: string, action: string, badgeKind?: string): { typeLabel: string; tone: ActivityTone; icon: string } => {
    const normalized = `${action} ${title}`.toLowerCase();
    const severity = firstString(entry?.severity, entry?.level).toLowerCase();
    const outcome = firstString(entry?.outcome, entry?.result, entry?.status).toLowerCase();

    if (
      severity === 'critical' ||
      severity === 'high' ||
      severity === 'error' ||
      outcome === 'failed' ||
      outcome === 'failure' ||
      normalized.includes('failed') ||
      normalized.includes('unreachable')
    ) {
      return { typeLabel: 'Alert', tone: 'critical', icon: 'exclamation-triangle-fill' };
    }

    if (normalized.includes('revoke') || normalized.includes('removed')) {
      return { typeLabel: 'Access revoked', tone: 'access', icon: 'people' };
    }

    if (normalized.includes('access_request.approved') || normalized.includes('granted') || normalized.includes('approved')) {
      return { typeLabel: 'Access granted', tone: 'success', icon: 'check-circle' };
    }

    if (normalized.includes('sync') || normalized.includes('snapshot')) {
      return { typeLabel: 'Sync', tone: 'sync', icon: 'arrow-repeat' };
    }

    if (normalized.includes('probe') || normalized.startsWith('test_')) {
      return { typeLabel: 'Probe', tone: 'info', icon: 'activity' };
    }

    if (
      normalized.includes('config') ||
      normalized.includes('policy') ||
      normalized.includes('provision') ||
      normalized.includes('group') ||
      badgeKind === 'admin'
    ) {
      return { typeLabel: 'Configuration', tone: 'warning', icon: 'exclamation-triangle-fill' };
    }

    if (badgeKind === 'critical') return { typeLabel: 'Alert', tone: 'critical', icon: 'exclamation-triangle-fill' };
    return { typeLabel: 'Activity', tone: 'info', icon: 'info-circle' };
  };

  const buildRow = (entry: any, index: number): ActivityRow => {
    const item = formatActivityItem(entry);
    const ctx = eventContext(entry);
    const action = firstString(entry?.action, entry?.type, entry?.event) || 'event';
    const title = firstString(item?.title, action) || 'Activity recorded';
    const description = firstString(item?.subtitle1, entry?.description, ctx.description, ctx.message) || 'Activity recorded';
    const type = classify(entry, title, action, (item as any)?.badgeKind);
    const actor = actorLabel(entry, ctx);
    const timestampMs = parseTimestamp(entry);
    const source = sourceLabel(entry, ctx, action);

    const row: ActivityRow = {
      id: firstString(entry?.id, `${timestampMs ?? index}-${action}`),
      raw: entry,
      timestampMs,
      timeLabel: formatTime(timestampMs, entry),
      typeLabel: type.typeLabel,
      tone: type.tone,
      icon: type.icon,
      title,
      description,
      actor,
      actorSubtitle: actorRole(entry, ctx),
      actorInitials: initials(actor),
      source,
      searchable: ''
    };

    row.searchable = [
      row.timeLabel,
      row.typeLabel,
      row.title,
      row.description,
      row.actor,
      row.actorSubtitle,
      row.source,
      action
    ]
      .join(' ')
      .toLowerCase();

    return row;
  };

  const matchesDate = (row: ActivityRow) => {
    if (dateFilter === 'all') return true;
    if (!row.timestampMs) return false;

    const now = Date.now();
    const day = 24 * 60 * 60 * 1000;
    if (dateFilter === 'today') return new Date(row.timestampMs).toDateString() === new Date().toDateString();
    if (dateFilter === '7d') return row.timestampMs >= now - 7 * day;
    if (dateFilter === '30d') return row.timestampMs >= now - 30 * day;
    return true;
  };

  const resetPage = () => {
    currentPage = 1;
  };

  const selectRow = (row: ActivityRow, index: number) => {
    if (!clickableRows) return;
    dispatch('rowclick', { entry: row.raw, row, index });
  };

  $: rows = (Array.isArray(items) ? items : []).map(buildRow).sort((a, b) => (b.timestampMs ?? 0) - (a.timestampMs ?? 0));
  $: typeOptions = Array.from(new Set(rows.map((row) => row.typeLabel))).sort((a, b) => a.localeCompare(b));
  $: actorOptions = Array.from(new Set(rows.map((row) => row.actor))).sort((a, b) => a.localeCompare(b));
  $: normalizedQuery = query.trim().toLowerCase();
  $: filteredRows = rows.filter((row) => {
    const queryOk = !normalizedQuery || row.searchable.includes(normalizedQuery);
    const typeOk = typeFilter === 'all' || row.typeLabel === typeFilter;
    const actorOk = actorFilter === 'all' || row.actor === actorFilter;
    return queryOk && typeOk && actorOk && matchesDate(row);
  });
  $: totalPages = Math.max(1, Math.ceil(filteredRows.length / rowsPerPage));
  $: currentPage = Math.min(currentPage, totalPages);
  $: pageStart = (currentPage - 1) * rowsPerPage;
  $: pageRows = filteredRows.slice(pageStart, pageStart + rowsPerPage);
  $: pageEnd = Math.min(pageStart + pageRows.length, filteredRows.length);
</script>

<article class="activity-log-card">
  <div class="activity-log-toolbar" aria-label="Activity filters">
    <label class="activity-search">
      <i class="bi bi-search" aria-hidden="true"></i>
      <input
        bind:value={query}
        type="search"
        placeholder="Search activity..."
        aria-label="Search activity"
        on:input={resetPage}
      />
    </label>

    <label class="activity-select activity-select--date">
      <i class="bi bi-calendar3" aria-hidden="true"></i>
      <select bind:value={dateFilter} aria-label="Filter by date" on:change={resetPage}>
        <option value="all">All dates</option>
        <option value="today">Today</option>
        <option value="7d">Last 7 days</option>
        <option value="30d">Last 30 days</option>
      </select>
    </label>

    <label class="activity-select">
      <select bind:value={typeFilter} aria-label="Filter by activity type" on:change={resetPage}>
        <option value="all">All types</option>
        {#each typeOptions as option}
          <option value={option}>{option}</option>
        {/each}
      </select>
      <i class="bi bi-chevron-down" aria-hidden="true"></i>
    </label>

    <label class="activity-select">
      <select bind:value={actorFilter} aria-label="Filter by actor" on:change={resetPage}>
        <option value="all">All actors</option>
        {#each actorOptions as option}
          <option value={option}>{option}</option>
        {/each}
      </select>
      <i class="bi bi-chevron-down" aria-hidden="true"></i>
    </label>
  </div>

  <div class="activity-table-wrap">
    <table class="activity-table">
      <thead>
        <tr>
          <th scope="col" class="col-time">Time <i class="bi bi-chevron-expand" aria-hidden="true"></i></th>
          <th scope="col" class="col-type">Type</th>
          <th scope="col">Description</th>
          <th scope="col" class="col-actor">Actor</th>
          <th scope="col" class="col-source">Source</th>
          <th scope="col" class="col-actions"><span class="visually-hidden">Actions</span></th>
        </tr>
      </thead>
      <tbody>
        {#if pageRows.length === 0}
          <tr>
            <td colspan="6">
              <div class="activity-empty">{emptyLabel}</div>
            </td>
          </tr>
        {:else}
          {#each pageRows as row, index (row.id)}
            <tr
              class:activity-row--clickable={clickableRows}
              tabindex={clickableRows ? 0 : undefined}
              on:click={() => selectRow(row, pageStart + index)}
              on:keydown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') selectRow(row, pageStart + index);
              }}
            >
              <td class="activity-time">{row.timeLabel}</td>
              <td>
                <span class={`activity-type activity-type--${row.tone}`}>
                  <i class={`bi bi-${row.icon}`} aria-hidden="true"></i>
                  <span>{row.typeLabel}</span>
                </span>
              </td>
              <td>
                <div class="activity-description">
                  <strong>{row.title}</strong>
                  <span>{row.description}</span>
                </div>
              </td>
              <td>
                <div class="activity-actor">
                  <span class="activity-avatar" aria-hidden="true">{row.actorInitials}</span>
                  <span>
                    <strong>{row.actor}</strong>
                    {#if row.actorSubtitle}
                      <small>({row.actorSubtitle})</small>
                    {/if}
                  </span>
                </div>
              </td>
              <td class="activity-source">{row.source}</td>
              <td class="activity-actions">
                {#if clickableRows}
                  <button
                    type="button"
                    class="activity-more"
                    aria-label="Open activity details"
                    on:click|stopPropagation={() => selectRow(row, pageStart + index)}
                  >
                    <i class="bi bi-three-dots-vertical" aria-hidden="true"></i>
                  </button>
                {/if}
              </td>
            </tr>
          {/each}
        {/if}
      </tbody>
    </table>
  </div>

  <footer class="activity-log-footer">
    <span>
      {#if filteredRows.length === 0}
        Showing 0 entries
      {:else}
        Showing {pageStart + 1} to {pageEnd} of {filteredRows.length} entries
      {/if}
    </span>

    {#if totalPages > 1}
      <nav class="activity-pagination" aria-label="Activity pagination">
        <button type="button" disabled={currentPage === 1} on:click={() => (currentPage -= 1)} aria-label="Previous page">
          <i class="bi bi-chevron-left" aria-hidden="true"></i>
        </button>
        {#each Array(totalPages) as _, pageIndex}
          {#if pageIndex < 3 || pageIndex === totalPages - 1 || Math.abs(pageIndex + 1 - currentPage) <= 1}
            <button
              type="button"
              class:activity-page--active={currentPage === pageIndex + 1}
              on:click={() => (currentPage = pageIndex + 1)}
            >
              {pageIndex + 1}
            </button>
          {:else if pageIndex === 3 && currentPage < totalPages - 2}
            <span>...</span>
          {/if}
        {/each}
        <button type="button" disabled={currentPage === totalPages} on:click={() => (currentPage += 1)} aria-label="Next page">
          <i class="bi bi-chevron-right" aria-hidden="true"></i>
        </button>
      </nav>
    {/if}
  </footer>
</article>

<style>
  .activity-log-card {
    border: 1px solid #dbe5f2;
    border-radius: 12px;
    background: #fff;
    box-shadow: 0 12px 30px rgba(15, 23, 42, 0.03);
    padding: 16px 18px 18px;
    min-width: 0;
  }

  .activity-log-toolbar {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 12px;
  }

  .activity-search,
  .activity-select {
    min-height: 42px;
    border: 1px solid #d8e2f0;
    border-radius: 8px;
    background: #fff;
    color: #0f1f3d;
    display: inline-flex;
    align-items: center;
    gap: 10px;
    padding: 0 12px;
  }

  .activity-search {
    min-width: min(100%, 280px);
    flex: 1 1 260px;
  }

  .activity-select {
    flex: 0 0 auto;
  }

  .activity-select--date {
    min-width: 210px;
  }

  .activity-search i,
  .activity-select i {
    color: #536680;
    font-size: 15px;
  }

  .activity-search input,
  .activity-select select {
    border: 0;
    outline: 0;
    background: transparent;
    color: #0f1f3d;
    font: inherit;
    font-size: 13px;
    min-width: 0;
  }

  .activity-search input {
    width: 100%;
  }

  .activity-select select {
    appearance: none;
    min-width: 132px;
    padding-right: 4px;
  }

  .activity-select--date select {
    min-width: 150px;
  }

  .activity-table-wrap {
    width: 100%;
    overflow-x: auto;
  }

  .activity-table {
    width: 100%;
    min-width: 860px;
    border-collapse: collapse;
    color: #0f1f3d;
  }

  .activity-table th {
    padding: 14px 10px;
    border-bottom: 1px solid #dfe7f3;
    color: #50627f;
    font-size: 12px;
    font-weight: 700;
    text-align: left;
  }

  .activity-table td {
    padding: 14px 10px;
    border-bottom: 1px solid #e7edf6;
    color: #182744;
    font-size: 13px;
    vertical-align: middle;
  }

  .activity-table tbody tr:last-child td {
    border-bottom: 0;
  }

  .activity-row--clickable {
    cursor: pointer;
  }

  .activity-row--clickable:hover {
    background: #f7faff;
  }

  .activity-row--clickable:focus {
    outline: 2px solid rgba(13, 99, 255, 0.35);
    outline-offset: -2px;
  }

  .col-time {
    width: 170px;
  }

  .col-type {
    width: 180px;
  }

  .col-actor {
    width: 190px;
  }

  .col-source {
    width: 170px;
  }

  .col-actions {
    width: 48px;
  }

  .activity-time,
  .activity-source {
    color: #30415f;
    white-space: nowrap;
  }

  .activity-type {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
    color: #20314f;
    white-space: nowrap;
  }

  .activity-type i {
    font-size: 17px;
  }

  .activity-type--critical i {
    color: #ef4444;
  }

  .activity-type--warning i {
    color: #f59e0b;
  }

  .activity-type--success i {
    color: #16a34a;
  }

  .activity-type--info i {
    color: var(--b2s-topbar-bg, #111b3f);
  }

  .activity-type--sync i {
    color: #6b7280;
  }

  .activity-type--access i {
    color: #a855f7;
  }

  .activity-description {
    display: grid;
    gap: 3px;
    min-width: 240px;
  }

  .activity-description strong,
  .activity-actor strong {
    color: #0f1f3d;
    font-size: 13px;
    font-weight: 700;
  }

  .activity-description span,
  .activity-actor small {
    color: #526580;
    font-size: 12px;
  }

  .activity-actor {
    display: flex;
    align-items: center;
    gap: 9px;
    min-width: 0;
  }

  .activity-actor > span:last-child {
    display: grid;
    gap: 2px;
    min-width: 0;
  }

  .activity-avatar {
    width: 30px;
    height: 30px;
    border-radius: 999px;
    background: rgba(77, 163, 255, 0.12);
    color: var(--b2s-topbar-bg, #111b3f);
    display: inline-grid;
    place-items: center;
    font-size: 11px;
    font-weight: 800;
    flex: 0 0 auto;
  }

  .activity-more {
    width: 32px;
    height: 32px;
    border: 0;
    border-radius: 8px;
    background: transparent;
    color: #0f1f3d;
    display: inline-grid;
    place-items: center;
  }

  .activity-more:hover {
    background: rgba(77, 163, 255, 0.12);
    color: var(--b2s-topbar-bg, #111b3f);
  }

  .activity-empty {
    min-height: 140px;
    display: grid;
    place-items: center;
    color: #637493;
    text-align: center;
  }

  .activity-log-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 14px;
    padding: 12px 2px 0;
    color: #526580;
    font-size: 13px;
    flex-wrap: wrap;
  }

  .activity-pagination {
    display: inline-flex;
    align-items: center;
    gap: 8px;
  }

  .activity-pagination button {
    width: 36px;
    height: 36px;
    border: 1px solid #d8e2f0;
    border-radius: 8px;
    background: #fff;
    color: #0f1f3d;
    font-weight: 700;
  }

  .activity-pagination button:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }

  .activity-pagination .activity-page--active {
    border-color: var(--b2s-topbar-bg, #111b3f);
    background: var(--b2s-topbar-bg, #111b3f);
    color: #fff;
  }

  @media (max-width: 900px) {
    .activity-log-card {
      padding: 14px;
    }

    .activity-search,
    .activity-select,
    .activity-select--date {
      width: 100%;
      min-width: 0;
      flex: 1 1 100%;
    }

    .activity-select select,
    .activity-select--date select {
      width: 100%;
    }
  }
</style>
