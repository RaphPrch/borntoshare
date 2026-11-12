<script lang="ts">
  import ShowMore from '$lib/components/ui/ShowMore.svelte';
  import SegmentedFilter from '$lib/components/ui/SegmentedFilter.svelte';
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { t } from '$lib/i18n';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import IdentityBrowserModal from '$lib/components/identity/IdentityBrowserModal.svelte';
  import { checkExistingAccess, createAccessRequest, listMyAccessRequests } from '$lib/api/access-requests';
  import { parseRequestSentence } from '$lib/utils/request-sentence';
  import { getPublicSettings } from '$lib/api/admin-advanced-settings';
  import { listStorageRootsContext, type StorageRootContext } from '$lib/api/storage-roots';
  import { reportUiError } from '$lib/errors';
  import { toast } from '$lib/stores/toast';

  /**
   * New access request in three steps: the folders (a cart, one level per folder, a tree by zone, file server
   * or DFS root), who and for how long, then a review. Opened from a folder (?root=), the folder is set and locked.
   * The express entry fills the three steps from one sentence (lib/utils/request-sentence.ts).
   */
  type Level = 'READ' | 'WRITE';
  type GroupBy = 'zone' | 'server' | 'dfs';
  type Root = { id: number; name: string; path: string; zone: string; server: string; dfsPath: string; dfsRoot: string };
  type Check = { state: 'checking' | 'ok' | 'blocked' | 'elevation'; message: string };

  const PAGE = 40;
  // Durations, permanent access, longest access and reason: Advanced settings › Governance (core-service checks them too)
  let policy = { durations: [7, 30, 90], allowPermanent: true, maxDays: 365, minReasonLength: 10 };
  $: DURATIONS = [
    ...policy.durations.map((days) => ({ key: String(days), days, label: () => t('{count} days', { count: days }) })),
    ...(policy.allowPermanent ? [{ key: 'permanent', days: 0, label: () => t('Permanent') }] : [])
  ];
  $: if (duration !== 'date' && DURATIONS.length && !DURATIONS.some((option) => option.key === duration)) duration = DURATIONS[Math.min(1, DURATIONS.length - 1)].key;
  $: maxDate = new Date(Date.now() + policy.maxDays * 86_400_000).toISOString().slice(0, 10);

  let roots: Root[] = [];
  let loading = true;
  let loadError = '';
  let step = 1;
  let query = '';
  let zoneFilter = '';
  let shown = PAGE;
  let closed = new Set<string>();
  const GROUP_KEY = 'b2s.newRequest.groupBy';
  let groupBy: GroupBy = 'zone';
  let recent: Root[] = [];
  let express = '';
  let expressNote = '';
  let cart = new Map<number, Level>();
  let checks: Record<number, Check> = {};
  let lockedRootId: number | null = null;

  let forOther = false;
  let principals: any[] = [];
  let showBrowser = false;
  let duration = '30';
  let customDate = '';
  let justification = '';
  let submitting = false;

  const text = (v: unknown) => String(v ?? '').trim();
  const toRoot = (row: StorageRootContext & Record<string, any>): Root => ({
    id: Number(row.storage_root_id ?? row.id ?? 0),
    name: text(row.storage_root_name ?? row.name) || `#${row.id}`,
    path: text(row.root_path ?? row.path),
    zone: text(row.zone_name ?? row.zone_code) || t('Unassigned zone'),
    server: text(row.storage_endpoint_name ?? row.endpoint_name) || t('Unknown server'),
    dfsPath: text(row.dfs_path),
    // \\domain\namespace: the DFS root the folder is published under
    dfsRoot: text(row.dfs_path).match(/^\\\\[^\\]+\\[^\\]+/)?.[0] ?? ''
  });

  onMount(async () => {
    getPublicSettings(fetch).then((settings) => { if (settings?.requests) policy = settings.requests; }).catch(() => null);
    try {
      roots = ((await listStorageRootsContext(fetch)) as any[]).map(toRoot).filter((root) => root.id > 0);
    } catch (error) {
      loadError = error instanceof Error ? error.message : t('Unable to load the folders.');
    } finally {
      loading = false;
    }
    const rootParam = Number($page.url.searchParams.get('root') ?? 0);
    const level = String($page.url.searchParams.get('permission') ?? '').toUpperCase().includes('W') ? 'WRITE' : 'READ';
    // ⌘K palette: ?principal_dn=…&principal_username=…&principal_name=…&principal_source=…
    const dn = text($page.url.searchParams.get('principal_dn'));
    if (dn) {
      forOther = true;
      principals = [{
        id: dn, type: 'user', dn, auth_source: 'ad',
        username: $page.url.searchParams.get('principal_username'),
        display_name: $page.url.searchParams.get('principal_name'),
        identity_source_id: Number($page.url.searchParams.get('principal_source') ?? 0) || null
      }];
    }
    if (rootParam > 0 && roots.some((root) => root.id === rootParam)) {
      lockedRootId = rootParam;
      add(rootParam, level);
    }
    try {
      const saved = localStorage.getItem(GROUP_KEY);
      if (saved === 'zone' || saved === 'server' || saved === 'dfs') groupBy = saved;
    } catch {
      // the default grouping is fine
    }
    if (!lockedRootId) void loadRecent();
  });

  // The folders of the user's last requests, newest first
  async function loadRecent() {
    try {
      const rows = await listMyAccessRequests(fetch);
      const ids = [...rows]
        .sort((a, b) => String(b.created_at ?? '').localeCompare(String(a.created_at ?? '')))
        .map((row) => Number(row.storage_root_id ?? 0));
      recent = [...new Set(ids)].map((id) => roots.find((root) => root.id === id)).filter(Boolean).slice(0, 6) as Root[];
    } catch {
      recent = [];
    }
  }
  function setGroupBy(key: string) {
    groupBy = key as GroupBy;
    closed = new Set();
    try {
      localStorage.setItem(GROUP_KEY, groupBy);
    } catch {
      // kept for this visit only
    }
  }

  // ---- folders ----------------------------------------------------------------
  $: zones = [...new Set(roots.map((root) => root.zone))].sort((a, b) => a.localeCompare(b, 'fr'));
  $: needle = query.trim().toLowerCase();
  const outsideDfs = () => t('Outside DFS');
  // Two levels for each grouping: zone → server, server alone, DFS root alone (folders outside DFS last)
  const groupKeys = (root: Root, by: GroupBy): [string, string] =>
    by === 'zone' ? [root.zone, root.server] : by === 'server' ? [root.server, ''] : [root.dfsRoot || outsideDfs(), ''];
  const sortKey = (root: Root, by: GroupBy) => (by === 'dfs' && !root.dfsRoot ? '\uffff' : '') + groupKeys(root, by).join('|');
  $: visible = roots
    .filter((root) => !zoneFilter || root.zone === zoneFilter)
    .filter((root) => !needle || `${root.name} ${root.path} ${root.dfsPath}`.toLowerCase().includes(needle))
    .sort((a, b) => sortKey(a, groupBy).localeCompare(sortKey(b, groupBy), 'fr') || a.name.localeCompare(b.name, 'fr', { numeric: true }));
  $: if (query || zoneFilter || groupBy) shown = PAGE;
  type Sub = { key: string; label: string; count: number; rows: Root[] };
  $: tree = (() => {
    const out: Array<{ key: string; label: string; count: number; subs: Sub[] }> = [];
    let budget = shown;
    for (const root of visible) {
      const [first, second] = groupKeys(root, groupBy);
      let group = out.find((entry) => entry.label === first);
      if (!group) out.push((group = { key: `${groupBy}|${first}`, label: first, count: 0, subs: [] }));
      let sub = group.subs.find((entry) => entry.label === second);
      if (!sub) group.subs.push((sub = { key: `${group.key}|${second}`, label: second, count: 0, rows: [] }));
      group.count += 1;
      sub.count += 1;
      if (budget > 0) {
        sub.rows.push(root);
        budget -= 1;
      }
    }
    return out;
  })();
  $: groupOptions = [
    { key: 'zone', label: t('By zone') },
    { key: 'server', label: t('By file server') },
    ...(roots.some((root) => root.dfsRoot) ? [{ key: 'dfs', label: t('By DFS root') }] : [])
  ];
  $: hidden = Math.max(0, visible.length - shown);
  const isOpen = (key: string, searching: boolean) => searching || !closed.has(key);
  function toggleGroup(key: string) {
    if (closed.has(key)) closed.delete(key);
    else closed.add(key);
    closed = closed;
  }

  function add(id: number, level: Level = 'READ') {
    cart.set(id, level);
    cart = cart;
    void check(id);
  }
  function toggle(id: number) {
    if (lockedRootId) return;
    if (cart.has(id)) {
      cart.delete(id);
      cart = cart;
    } else add(id);
  }
  function setLevel(id: number, level: Level) {
    cart.set(id, level);
    cart = cart;
    void check(id);
  }

  const principalPayload = (principal: any) => ({
    id: String(principal?.id ?? ''),
    external_id: text(principal?.external_id ?? principal?.id) || null,
    dn: text(principal?.dn) || null,
    username: text(principal?.username ?? principal?.upn) || null,
    display_name: principal?.display_name ?? null,
    email: principal?.email ?? null,
    auth_source: principal?.auth_source ?? 'ad',
    type: String(principal?.type ?? 'user').toLowerCase(),
    identity_source_id: Number(principal?.identity_source_id ?? 0) || null
  });

  // Can this request be made (an access already in place blocks it, a higher level is an elevation)
  async function check(id: number) {
    const level = cart.get(id);
    if (!level) return;
    checks = { ...checks, [id]: { state: 'checking', message: '' } };
    try {
      const targets = forOther && principals.length ? principals : [null];
      for (const principal of targets) {
        // Never stuck on « Checking… »: past 15 s the folder goes on (the core checks again when the request is sent)
        const result: any = await Promise.race([
          checkExistingAccess(fetch, {
            storage_root_id: id,
            access_level: level,
            ...(principal ? { requested_principal: principalPayload(principal) } : {})
          } as any),
          new Promise((resolve) => setTimeout(() => resolve({ can_request: true, timed_out: true }), 15000))
        ]);
        if (result?.timed_out) {
          checks = { ...checks, [id]: { state: 'ok', message: t('Not checked in time: checked again when the request is sent.') } };
          return;
        }
        if (!result?.can_request) {
          checks = { ...checks, [id]: { state: 'blocked', message: String(result?.message ?? t('This request cannot be submitted.')) } };
          return;
        }
        if (result?.code === 'ELEVATION_ALLOWED' || result?.reason === 'ELEVATION_ALLOWED') {
          checks = { ...checks, [id]: { state: 'elevation', message: String(result?.message ?? '') } };
          return;
        }
      }
      checks = { ...checks, [id]: { state: 'ok', message: '' } };
    } catch {
      checks = { ...checks, [id]: { state: 'ok', message: '' } };
    }
  }
  $: cartRows = [...cart.entries()].map(([id, level]) => ({ root: roots.find((root) => root.id === id), level, check: checks[id] })).filter((row) => row.root) as Array<{ root: Root; level: Level; check?: Check }>;
  $: sendable = cartRows.filter((row) => row.check?.state !== 'blocked');
  $: anyChecking = cartRows.some((row) => row.check?.state === 'checking');

  // ---- who, how long, why -------------------------------------------------------
  function onSelectIdentity(payload: any) {
    principals = Array.isArray(payload?.selectedItems) ? payload.selectedItems.filter(Boolean) : [];
    showBrowser = false;
    for (const id of cart.keys()) void check(id);
  }
  function setForOther(value: boolean) {
    forOther = value;
    for (const id of cart.keys()) void check(id);
  }
  $: endDate = (() => {
    if (duration === 'date') return customDate ? new Date(`${customDate}T23:59:00`) : null;
    const days = DURATIONS.find((d) => d.key === duration)?.days ?? 0;
    return days ? new Date(Date.now() + days * 86_400_000) : null;
  })();
  const dayLabel = (date: Date | null) => (date ? date.toLocaleDateString() : t('no end'));
  const REASONS = [() => t('Monthly closing'), () => t('Replacing a colleague'), () => t('Audit in progress'), () => t('New project')];
  function useReason(label: string) {
    const current = justification.trim();
    if (!current.startsWith(label)) justification = current ? `${label} : ${current}` : `${label} : `;
    document.getElementById('nr-why')?.focus();
  }
  $: reasonShort = justification.trim().length < policy.minReasonLength;
  $: step2Ready = !reasonShort && (!forOther || principals.length > 0) && (duration !== 'date' || Boolean(customDate));
  $: requestCount = sendable.length * (forOther ? principals.length : 1);

  async function submit() {
    if (submitting || anyChecking || !sendable.length) return;
    submitting = true;
    let created = 0;
    const failed: string[] = [];
    const targets = forOther ? principals : [null];
    for (const row of sendable) {
      for (const principal of targets) {
        try {
          await createAccessRequest(fetch, {
            storage_root_id: row.root.id,
            permissions: [row.level],
            expires_at: endDate ? endDate.toISOString() : null,
            justification: justification.trim(),
            ...(principal ? { requested_principal: principalPayload(principal) } : {})
          } as any);
          created += 1;
        } catch (error) {
          failed.push(`${row.root.name} : ${error instanceof Error ? error.message : t('Failed to create request')}`);
        }
      }
    }
    submitting = false;
    if (created) toast.success(created > 1 ? t('{count} access requests created', { count: created }) : t('Access request created'));
    if (failed.length) {
      reportUiError(new Error(failed.join(' · ')), t('Some requests could not be created.'), 'access-requests.new');
      return;
    }
    await goto('/access-requests?status=pending', { invalidateAll: true });
  }

  const STEPS = [() => t('Folders'), () => t('Duration and reason'), () => t('Review')];
  $: canGo = (n: number) => n < step || (n === 2 && sendable.length > 0 && !anyChecking) || (n === 3 && sendable.length > 0 && !anyChecking && step2Ready);
  $: stepSummary = (n: number) =>
    n === 1 ? (cart.size ? t('{count} folder(s)', { count: cart.size }) : '') : n === 2 && justification.trim() ? dayLabel(endDate) : '';

  // ---- express entry ------------------------------------------------------------
  const isoDay = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
  $: parsed = express.trim() ? parseRequestSentence(express, roots) : null;
  $: parsedNames = parsed ? parsed.rootIds.map((id) => roots.find((root) => root.id === id)?.name).filter(Boolean).join(', ') : '';
  $: parsedDuration = !parsed?.duration
    ? ''
    : 'permanent' in parsed.duration
      ? t('Permanent')
      : 'days' in parsed.duration
        ? t('{count} days', { count: parsed.duration.days })
        : t('until {date}', { date: new Date(`${parsed.duration.date}T12:00:00`).toLocaleDateString() });
  function applyExpress() {
    if (!parsed) return;
    const result = parsed;
    for (const id of result.rootIds) add(id, result.level ?? 'READ');
    const found = result.duration;
    if (found && 'permanent' in found) duration = 'permanent';
    else if (found && 'days' in found) {
      const preset = DURATIONS.find((option) => option.days === found.days);
      if (preset) duration = preset.key;
      else {
        duration = 'date';
        customDate = isoDay(new Date(Date.now() + found.days * 86_400_000));
      }
    } else if (found && 'date' in found) {
      duration = 'date';
      customDate = found.date;
    }
    if (result.reason) justification = result.reason;
    const unclear = result.ambiguous[0];
    if (unclear) {
      query = unclear.term;
      expressNote = t('“{term}” names {count} folders: pick the right one in the list.', { term: unclear.term, count: unclear.ids.length });
    } else expressNote = '';
    express = '';
    if (!unclear && cart.size) step = result.reason && found ? 3 : 2;
  }
</script>

<svelte:head><title>{t('New access request')} · BornToShare</title></svelte:head>

<section class="nr">
  <header class="nr__top">
    <a class="nr__back" href="/access-requests"><i class="bi bi-chevron-left" aria-hidden="true"></i>{t('Requests')}</a>
    <div class="nr__title">
      <h1>{t('New access request')}</h1>
      <ol class="nr__steps">
        {#each STEPS as label, index}
          <li class:on={step === index + 1} class:done={step > index + 1}>
            <button type="button" disabled={step === index + 1 || !canGo(index + 1) || submitting} aria-current={step === index + 1 ? 'step' : undefined} on:click={() => (step = index + 1)}>
              <span>{step > index + 1 ? '✓' : index + 1}</span>{label()}{#if stepSummary(index + 1) && step !== index + 1}<small>{stepSummary(index + 1)}</small>{/if}
            </button>
          </li>
        {/each}
      </ol>
    </div>
  </header>

  {#if loading}
    <section class="nr__panel"><LoadingState skeleton="rows" rows={6}>{t('Loading…')}</LoadingState></section>
  {:else if loadError}
    <InlineAlert tone="error">{loadError}</InlineAlert>
  {:else}
    <div class="nr__layout">
      {#if step === 1}
        <section class="nr__panel" aria-label={t('Folders')}>
          {#if lockedRootId}
            <p class="nr__locked"><i class="bi bi-lock" aria-hidden="true"></i>{t('The folder comes from the folder page and cannot be changed here.')}</p>
          {:else}
            <form class="nr__express" on:submit|preventDefault={applyExpress}>
              <label for="nr-express"><i class="bi bi-lightning-charge" aria-hidden="true"></i>{t('Express entry')}</label>
              <div class="nr__expressrow">
                <input id="nr-express" class="b2s-input" bind:value={express} autocomplete="off" placeholder={t('E.g. read on Purchasing and Accounting for 30 days: November closing')} />
                <button type="submit" class="b2s-btn b2s-btn-secondary" disabled={!parsed || (!parsed.rootIds.length && !parsed.ambiguous.length)}>{t('Fill in')}</button>
              </div>
              {#if parsed}
                <div class="nr__slots">
                  <span class:miss={!parsed.level}><em>{t('Level')}</em>{parsed.level === 'WRITE' ? t('Modify') : parsed.level === 'READ' ? t('Read') : t('Read (default)')}</span>
                  <span class:miss={!parsedNames && !parsed.ambiguous.length}><em>{t('Folders')}</em>{parsedNames || (parsed.ambiguous.length ? t('to pick in the list') : t('name a folder or paste its path'))}</span>
                  <span class:miss={!parsed.duration}><em>{t('Duration')}</em>{parsedDuration || t('“for 30 days”, “until 31/12”, “permanent”')}</span>
                  <span class:miss={!parsed.reason}><em>{t('Reason')}</em>{parsed.reason || t('after a colon: “…: closing”')}</span>
                </div>
              {/if}
              {#if expressNote}<small class="nr__warn">{expressNote}</small>{/if}
            </form>
            <div class="nr__search">
              <label><i class="bi bi-search" aria-hidden="true"></i><input type="search" bind:value={query} placeholder={t('Which folder are you looking for?')} aria-label={t('Search a folder')} /></label>
              {#if zones.length > 1}
                <select class="b2s-input" bind:value={zoneFilter} aria-label={t('Zone')}>
                  <option value="">{t('All zones')}</option>
                  {#each zones as zone (zone)}<option value={zone}>{zone}</option>{/each}
                </select>
              {/if}
              <SegmentedFilter options={groupOptions} value={groupBy} ariaLabel={t('Group the folders')} onChange={setGroupBy} />
            </div>
            {#if recent.length && !needle}
              <div class="nr__recent">
                <span>{t('Recently requested')}</span>
                {#each recent as root (root.id)}
                  <button type="button" class:on={cart.has(root.id)} title={root.dfsPath || root.path} on:click={() => toggle(root.id)}>{cart.has(root.id) ? '✓' : '+'} {root.name}<small>{root.server}</small></button>
                {/each}
              </div>
            {/if}
            <div class="nr__tree">
              {#each tree as group (group.key)}
                {@const groupOpen = isOpen(group.key, Boolean(needle))}
                <button type="button" class="nr__zone" class:unc={groupBy === 'dfs' && group.label.startsWith('\\\\')} on:click={() => toggleGroup(group.key)}>
                  <span class="nr__car">{groupOpen ? '▾' : '▸'}</span>{group.label}<em>{t('{count} folder(s)', { count: group.count })}</em>
                </button>
                {#if groupOpen}
                  {#each group.subs as sub (sub.key)}
                    {@const subOpen = !sub.label || isOpen(sub.key, Boolean(needle))}
                    {#if sub.label}
                      <button type="button" class="nr__server" on:click={() => toggleGroup(sub.key)}>
                        <span class="nr__car">{subOpen ? '▾' : '▸'}</span>{sub.label}<em>{sub.count}</em>
                      </button>
                    {/if}
                    {#if subOpen}
                      {#each sub.rows as root (root.id)}
                        {@const shownPath = groupBy === 'server' ? root.path : root.dfsPath || root.path}
                        <button type="button" class="nr__item" class:flat={!sub.label} class:on={cart.has(root.id)} on:click={() => toggle(root.id)}>
                          <span class="nr__tick">{cart.has(root.id) ? '✓' : ''}</span>
                          <span class="nr__name"><b>{root.name}</b><small title={shownPath}>{shownPath}</small></span>
                        </button>
                      {/each}
                    {/if}
                  {/each}
                {/if}
              {:else}
                <p class="nr__muted nr__empty">{t('No folder matches this search.')}</p>
              {/each}
              {#if hidden}
                <ShowMore shown={0} total={hidden} page={PAGE} onMore={() => (shown += PAGE)} />
              {/if}
            </div>
          {/if}
        </section>
      {:else if step === 2}
        <section class="nr__panel nr__form" aria-label={t('Duration and reason')}>
          <div class="nr__q">
            <span class="nr__label">{t('For whom?')}</span>
            <div class="nr__chips">
              <button type="button" class:on={!forOther} on:click={() => setForOther(false)}>{t('For me')}</button>
              <button type="button" class:on={forOther} on:click={() => setForOther(true)}>{t('For someone else')}</button>
            </div>
            {#if forOther}
              <div class="nr__people">
                {#each principals as principal, index (index)}<span>{principal?.display_name ?? principal?.username ?? principal?.dn}</span>{/each}
                <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" on:click={() => (showBrowser = true)}>{principals.length ? t('Change') : t('Choose in the directory')}</button>
              </div>
            {/if}
          </div>
          <div class="nr__q">
            <span class="nr__label">{t('For how long?')}</span>
            <div class="nr__chips">
              {#each DURATIONS as option (option.key)}
                <button type="button" class:on={duration === option.key} on:click={() => (duration = option.key)}>{option.label()}<small>{option.days ? t('until {date}', { date: dayLabel(new Date(Date.now() + option.days * 86_400_000)) }) : t('no end')}</small></button>
              {/each}
              <button type="button" class:on={duration === 'date'} on:click={() => (duration = 'date')}>{t('A date…')}<small>{customDate ? dayLabel(endDate) : t('calendar')}</small></button>
            </div>
            {#if duration === 'date'}<input class="b2s-input nr__date" type="date" bind:value={customDate} min={new Date(Date.now() + 86_400_000).toISOString().slice(0, 10)} max={maxDate} />{/if}
          </div>
          <div class="nr__q">
            <label class="nr__label" for="nr-why">{t('Why?')}</label>
            <textarea id="nr-why" class="b2s-input" bind:value={justification} placeholder={t('E.g. monthly closing of November. The guardian reads it before deciding.')}></textarea>
            <div class="nr__reasons">
              <small class="nr__muted">{t('Frequent reasons:')}</small>
              {#each REASONS as reason}<button type="button" on:click={() => useReason(reason())}>{reason()}</button>{/each}
            </div>
            <small class="nr__muted">{t('At least {count} characters · seen by the guardian and in the history of the folder', { count: policy.minReasonLength })}</small>
          </div>
        </section>
      {:else}
        <section class="nr__panel" aria-label={t('Review')}>
          <div class="nr__review">
            <div><span>{t('For')}</span><b>{forOther ? principals.map((p) => p?.display_name ?? p?.username).join(', ') : t('You')}</b></div>
            <div><span>{t('Until')}</span><b>{dayLabel(endDate)}</b></div>
            <div class="wide"><span>{t('Reason')}</span><b>{justification}</b></div>
          </div>
          <ol class="nr__next">
            <li><b>{t('Sending')}</b><small>{requestCount > 1 ? t('{count} requests, one per folder', { count: requestCount }) : t('One request')}</small></li>
            <li><b>{t('Decision of the guardians')}</b><small>{t('Each guardian decides for their folders.')}</small></li>
            <li><b>{t('Access in place')}</b><small>{t('Added to the AD group of the folder by the worker, effective within minutes.')}</small></li>
            <li><b>{t('End')}</b><small>{endDate ? t('Removed automatically on {date}.', { date: dayLabel(endDate) }) : t('No end date.')}</small></li>
          </ol>
        </section>
      {/if}

      <aside class="nr__panel nr__cart" aria-label={t('Your request')}>
        <h2>{t('Your request')}<span>{cart.size}</span></h2>
        {#each cartRows as row (row.root.id)}
          <div class="nr__ci">
            <b title={row.root.path}>{row.root.name}</b>
            <span class="nr__lv">
              <button type="button" class:r={row.level === 'READ'} disabled={step === 3} on:click={() => setLevel(row.root.id, 'READ')}>{t('Read')}</button>
              <button type="button" class:w={row.level === 'WRITE'} disabled={step === 3} on:click={() => setLevel(row.root.id, 'WRITE')}>{t('Modify')}</button>
            </span>
            <small>
              {row.root.server}
              {#if row.check?.state === 'checking'} · {t('Checking…')}{/if}
              {#if !lockedRootId && step === 1} · <button type="button" class="nr__rm" on:click={() => toggle(row.root.id)}>{t('Remove')}</button>{/if}
            </small>
            {#if row.check?.state === 'blocked'}<small class="nr__bad">{row.check.message}</small>{/if}
            {#if row.check?.state === 'elevation'}<small class="nr__warn">{row.check.message || t('This request will be handled as an elevation.')}</small>{/if}
          </div>
        {:else}
          <p class="nr__cartempty">{t('Add folders from the list. You can ask for several at once.')}</p>
        {/each}
        {#if step === 1}
          <button type="button" class="b2s-btn b2s-btn-primary nr__wide" disabled={!sendable.length || anyChecking} on:click={() => (step = 2)}>{t('Continue')}</button>
        {:else if step === 2}
          <div class="nr__foot"><button type="button" class="b2s-btn b2s-btn-secondary" on:click={() => (step = 1)}>{t('Back')}</button><button type="button" class="b2s-btn b2s-btn-primary" disabled={!step2Ready || !sendable.length} on:click={() => (step = 3)}>{t('Review')}</button></div>
        {:else}
          <div class="nr__foot"><button type="button" class="b2s-btn b2s-btn-secondary" disabled={submitting} on:click={() => (step = 2)}>{t('Edit')}</button><button type="button" class="b2s-btn b2s-btn-primary" disabled={submitting || anyChecking || !sendable.length} on:click={submit}>{submitting ? t('Sending…') : requestCount > 1 ? t('Send {count} requests', { count: requestCount }) : t('Send the request')}</button></div>
        {/if}
      </aside>
    </div>
  {/if}
</section>

<IdentityBrowserModal
  open={showBrowser}
  onClose={() => (showBrowser = false)}
  onSelect={onSelectIdentity}
  identitySources={[]}
  initialSourceId={null}
  title={t('Browse Active Directory')}
  subtitle={t('Select users and groups receiving the request.')}
  mode="multiple"
  allowedPrincipalType="all"
  includeImportCandidates={true}
  confirmLabel={t('Confirm')}
  confirmBusyLabel={t('Confirming…')}
/>

<style>
  .nr { padding: var(--b2s-page-padding, 24px 28px); display: flex; flex-direction: column; gap: 18px; }
  .nr__back { display: inline-flex; align-items: center; gap: 4px; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); text-decoration: none; }
  .nr__title { display: flex; flex-wrap: wrap; align-items: center; gap: 16px; margin-top: 4px; }
  .nr__title h1 { margin: 0; font-size: var(--b2s-fs-page-title, 26px); font-weight: 600; letter-spacing: -0.01em; }
  .nr__steps { display: flex; gap: 6px; margin: 0; padding: 0; list-style: none; }
  .nr__steps li { display: contents; }
  .nr__steps button { display: flex; align-items: center; gap: 8px; padding: 4px 12px 4px 4px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-pill); background: var(--b2s-color-surface); color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); cursor: pointer; }
  .nr__steps button:disabled { cursor: default; }
  .nr__steps small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .nr__steps small::before { content: '· '; }
  .nr__steps span { display: grid; place-items: center; width: 22px; height: 22px; border-radius: 50%; background: var(--b2s-color-neutral-soft); font-weight: 600; font-size: 12px; }
  .nr__steps li.on button { border-color: var(--b2s-color-text); color: var(--b2s-color-text); }
  .nr__steps li.on button span { background: var(--b2s-color-text); color: #fff; }
  .nr__steps li.done button:hover { border-color: var(--b2s-color-text); color: var(--b2s-color-text); }
  .nr__steps li.done span { background: var(--b2s-color-success-soft); color: var(--b2s-color-success-strong); }
  .nr__layout { display: grid; grid-template-columns: minmax(0, 760px) 320px; gap: 18px; align-items: start; }
  .nr__panel { display: flex; flex-direction: column; gap: 12px; min-width: 0; padding: 18px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .nr__muted { margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .nr__locked { display: flex; align-items: center; gap: 8px; margin: 0; color: var(--b2s-color-text-muted); }
  .nr__search { display: flex; align-items: center; gap: 8px; }
  .nr__search label { flex: 1; display: flex; align-items: center; gap: 8px; height: 44px; padding: 0 14px; border: 1.5px solid var(--b2s-color-border-mid, var(--b2s-color-border)); border-radius: var(--b2s-radius-md); }
  .nr__search label:focus-within { border-color: var(--b2s-color-text); }
  .nr__search input { flex: 1; min-width: 0; border: 0; outline: 0; background: none; font: inherit; font-size: 15px; }
  .nr__search select { width: auto; }
  .nr__tree { display: flex; flex-direction: column; max-height: 460px; overflow: auto; }
  .nr__zone, .nr__server { position: sticky; display: flex; align-items: center; gap: 8px; width: 100%; border: 0; background: var(--b2s-color-surface); text-align: left; cursor: pointer; }
  .nr__zone { top: 0; z-index: 2; padding: 8px 4px; border-bottom: 1px solid var(--b2s-color-border); font-size: var(--b2s-fs-sm); font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; }
  .nr__server { top: 36px; z-index: 1; padding: 6px 4px 6px 18px; font-size: var(--b2s-fs-sm); font-weight: 600; }
  .nr__zone em, .nr__server em { margin-left: auto; color: var(--b2s-color-text-muted); font-style: normal; font-weight: 500; font-size: var(--b2s-fs-xs); text-transform: none; letter-spacing: 0; }
  .nr__zone.unc { font-family: var(--b2s-font-mono); text-transform: none; letter-spacing: 0; }
  .nr__car { width: 12px; color: var(--b2s-color-text-muted); font-size: 10px; }
  .nr__item { display: grid; grid-template-columns: 18px minmax(0, 1fr); gap: 10px; align-items: center; width: 100%; padding: 6px 10px 6px 34px; border: 1px solid transparent; border-radius: var(--b2s-radius-md); background: none; text-align: left; cursor: pointer; }
  .nr__item:hover { background: var(--b2s-color-surface-soft, #f6f7f9); }
  .nr__item.on { border-color: var(--b2s-color-success-border, #cfe99a); background: var(--b2s-accent-soft); }
  .nr__tick { display: grid; place-items: center; width: 18px; height: 18px; border: 1.5px solid var(--b2s-color-border-mid, #cdd2db); border-radius: 5px; font-size: 11px; color: #fff; }
  .nr__item.on .nr__tick { background: var(--b2s-color-text); border-color: var(--b2s-color-text); }
  .nr__name { display: flex; align-items: baseline; gap: 8px; min-width: 0; white-space: nowrap; overflow: hidden; }
  .nr__name b { font-weight: 500; font-size: var(--b2s-fs-sm); }
  .nr__name small { overflow: hidden; text-overflow: ellipsis; color: var(--b2s-color-text-muted); font-family: var(--b2s-font-mono); font-size: var(--b2s-fs-xs); }
  .nr__empty { padding: 20px; text-align: center; }
  .nr__form { gap: 20px; }
  .nr__q { display: flex; flex-direction: column; gap: 8px; }
  .nr__label { font-weight: 600; }
  .nr__chips { display: flex; flex-wrap: wrap; gap: 8px; }
  .nr__chips button { padding: 8px 14px; border: 1px solid var(--b2s-color-border-mid, var(--b2s-color-border)); border-radius: var(--b2s-radius-md); background: var(--b2s-color-surface); text-align: left; cursor: pointer; }
  .nr__chips button.on { border-color: var(--b2s-color-text); background: var(--b2s-color-text); color: #fff; }
  .nr__chips small { display: block; font-size: var(--b2s-fs-xs); opacity: 0.75; }
  .nr__date { width: auto; }
  .nr__people { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
  .nr__people span { padding: 2px 10px; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-neutral-soft); font-size: var(--b2s-fs-sm); }
  textarea.b2s-input { min-height: 90px; padding: 10px 12px; resize: vertical; }
  .nr__review { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .nr__review div { display: flex; flex-direction: column; gap: 2px; padding: 12px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-md); }
  .nr__review .wide { grid-column: 1 / -1; }
  .nr__review span { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
  .nr__review b { font-weight: 500; overflow-wrap: anywhere; }
  .nr__next { display: grid; gap: 8px; margin: 0; padding-left: 20px; }
  .nr__next small { display: block; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .nr__cart { position: sticky; top: 16px; }
  .nr__cart h2 { display: flex; align-items: center; gap: 8px; margin: 0; font-size: var(--b2s-fs-md); font-weight: 600; }
  .nr__cart h2 span { margin-left: auto; padding: 0 9px; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-text); color: #fff; font-size: var(--b2s-fs-xs); }
  .nr__ci { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 4px 8px; align-items: center; padding: 10px 0; border-top: 1px solid var(--b2s-color-border); }
  .nr__ci:first-of-type { border-top: 0; }
  .nr__ci b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: var(--b2s-fs-sm); font-weight: 600; }
  .nr__ci small { grid-column: 1 / -1; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .nr__lv { display: flex; padding: 2px; border-radius: var(--b2s-radius-sm); background: var(--b2s-color-neutral-soft); }
  .nr__lv button { padding: 2px 8px; border: 0; border-radius: 6px; background: none; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); cursor: pointer; }
  .nr__lv button.r { background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); font-weight: 600; }
  .nr__lv button.w { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); font-weight: 600; }
  .nr__rm { padding: 0; border: 0; background: none; color: var(--b2s-color-info-strong); font-size: inherit; cursor: pointer; }
  .nr__bad { color: var(--b2s-color-danger-strong) !important; }
  .nr__warn { color: var(--b2s-color-warning-strong) !important; }
  .nr__cartempty { margin: 0; padding: 16px; border: 1.5px dashed var(--b2s-color-border); border-radius: var(--b2s-radius-md); color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); text-align: center; }
  .nr__wide { width: 100%; justify-content: center; }
  .nr__express { display: grid; gap: 8px; padding: 12px; border: 1px dashed var(--b2s-color-border-mid, var(--b2s-color-border)); border-radius: var(--b2s-radius-md); }
  .nr__express label { display: flex; align-items: center; gap: 6px; font-weight: 600; font-size: var(--b2s-fs-sm); }
  .nr__expressrow { display: flex; gap: 8px; }
  .nr__expressrow input { flex: 1; }
  .nr__slots { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
  .nr__slots span { display: flex; flex-direction: column; gap: 2px; min-width: 0; padding: 8px 10px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-md); font-size: var(--b2s-fs-sm); font-weight: 500; overflow-wrap: anywhere; }
  .nr__slots span.miss { border-style: dashed; background: var(--b2s-color-surface-soft, #f6f7f9); color: var(--b2s-color-text-muted); font-weight: 400; }
  .nr__slots em { color: var(--b2s-color-text-muted); font-style: normal; font-size: var(--b2s-fs-xs); font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
  .nr__recent { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
  .nr__recent > span { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
  .nr__recent button { display: inline-flex; align-items: baseline; gap: 6px; padding: 4px 10px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-pill); background: var(--b2s-color-surface); font-size: var(--b2s-fs-sm); cursor: pointer; }
  .nr__recent button.on { border-color: var(--b2s-color-success-border, #cfe99a); background: var(--b2s-accent-soft); }
  .nr__recent small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .nr__item.flat { padding-left: 22px; }
  .nr__reasons { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
  .nr__reasons button { padding: 3px 10px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-sm); background: var(--b2s-color-surface); color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); cursor: pointer; }
  .nr__reasons button:hover { color: var(--b2s-color-text); border-color: var(--b2s-color-text); }
  .nr__foot { display: flex; justify-content: flex-end; gap: 8px; }
</style>
