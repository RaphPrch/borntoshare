<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { t } from '$lib/i18n';
  import { apiGetData, apiPostData } from '$lib/api/client';
  import { formatDate, formatDateTime } from '$lib/utils/format';
  import { csvFilename, downloadCsv } from '$lib/utils/csv';
  import { reportUiError } from '$lib/errors';
  import { toast } from '$lib/stores/toast';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import ConfirmActionModal from '$lib/components/ui/ConfirmActionModal.svelte';
  import ContextMenu, { menuPositionFor, type ContextMenuItem } from '$lib/components/ui/ContextMenu.svelte';
  import { copyText } from '$lib/utils/clipboard';
  import { readParam, writeParams } from '$lib/utils/url-state';
  import { setCrumbs } from '$lib/stores/crumbs';

  /**
   * One access review, folder by folder: on the left the folders of the review and what is left to decide in each,
   * in the middle every person who reaches the chosen folder and how (request, AD group, right set outside
   * BornToShare), kept or removed with one click. « Summary and application » lists the removals: those a request
   * granted are revoked (the person leaves the AD group), the others are marked « to remove by hand ». The
   * administrator closes the review: its export is the evidence.
   */
  type Via = { kind?: string; group?: string | null; code?: string; nested?: boolean };
  type Item = { id: number; storage_root_id: number; root_name: string; root_path: string; username: string | null; display_name: string | null;
    level: string | null; via: Via[]; revocable: boolean; decision: 'keep' | 'revoke' | null; note: string | null; decided_by: string | null;
    decided_at: string | null; outcome: 'revoked' | 'manual' | 'failed' | null; outcome_detail: string | null };
  type Data = { review: { id: number; name: string; status: 'open' | 'closed'; due_at: string | null; created_at: string; created_by: string | null; closed_at: string | null }; items: Item[] };
  type Folder = { id: number; name: string; path: string; items: Item[]; left: number };

  let reviewId = $derived(Number($page.params.id));
  let isAdmin = $derived(Boolean(($page.data as any)?.me?.is_admin));
  let me = $derived(String(($page.data as any)?.me?.display_name ?? ($page.data as any)?.me?.username ?? ''));
  let data = $state<Data | null>(null);
  let error = $state('');
  let view = $state<'decide' | 'summary'>(readParam('view', 'decide', ['decide', 'summary'] as const));
  let show = $state<'todo' | 'all'>(readParam('show', 'todo', ['todo', 'all'] as const));
  let folderId = $state<number>(Number(readParam('folder', '0')) || 0);
  $effect(() => writeParams({ view: view === 'decide' ? null : view, show: show === 'todo' ? null : show, folder: folderId ? String(folderId) : null }));
  $effect(() => setCrumbs([{ label: t('Reviews'), href: '/access-reviews' }, { label: data?.review.name ?? '' }]));
  let query = $state('');
  let cursor = $state<number | null>(null);
  let menu = $state<{ item: Item; at: { x: number; y: number } } | null>(null);
  let busy = $state(false);
  let confirmApply = $state(false);
  let confirmClose = $state(false);

  async function load() {
    try {
      data = await apiGetData<Data>(fetch, `/access-reviews/${reviewId}`);
    } catch (failure) {
      error = failure instanceof Error ? failure.message : t('Unable to load the review.');
    }
  }
  onMount(load);

  /** Records a decision and changes the lines in place (the whole review is not read again: thousands of lines);
   * the toast offers to undo it for a few seconds. */
  async function decide(items: Item[], decision: 'keep' | 'revoke' | null, undoable = true) {
    const targets = items.filter((item) => !item.outcome);
    const ids = new Set(targets.map((item) => item.id));
    if (!ids.size || busy || !data) return;
    const before = new Map(targets.map((item) => [item.id, item.decision]));
    busy = true;
    try {
      await apiPostData(fetch, `/access-reviews/${reviewId}/decisions`, { item_ids: [...ids], decision });
      const now = new Date().toISOString();
      data = { ...data, items: data.items.map((item) => (ids.has(item.id) ? { ...item, decision, decided_by: decision ? me || item.decided_by : null, decided_at: decision ? now : null } : item)) };
      lastBefore = before;
      if (undoable && decision) {
        const label = decision === 'keep' ? t('{count} access(es) kept.', { count: ids.size }) : t('{count} access(es) to remove.', { count: ids.size });
        toast.success(label, { action: { label: t('Undo'), run: () => undo(before) } });
      }
    } catch (failure) {
      reportUiError(failure, t('Unable to record the decision.'), 'access-reviews.decide');
    } finally {
      busy = false;
    }
  }
  async function undo(before: Map<number, Item['decision']>) {
    for (const decision of ['keep', 'revoke', null] as const) {
      const ids = [...before].filter(([, value]) => value === decision).map(([id]) => id);
      if (ids.length) await decide((data?.items ?? []).filter((item) => ids.includes(item.id)), decision, false);
    }
  }
  let lastBefore: Map<number, Item['decision']> | null = null;
  const toggleDecision = (item: Item, decision: 'keep' | 'revoke') => decide([item], item.decision === decision ? null : decision, item.decision !== decision);

  // ---- folders of the review (left) and the people of the one chosen ----
  let open = $derived(data?.review.status === 'open');
  let needle = $derived(query.trim().toLowerCase());
  const matches = (item: Item) => !needle || `${item.display_name ?? ''} ${item.username ?? ''} ${item.root_name}`.toLowerCase().includes(needle);
  let folders = $derived.by(() => {
    const groups = new Map<number, Folder>();
    for (const item of data?.items ?? []) {
      if (!matches(item)) continue;
      let group = groups.get(item.storage_root_id);
      if (!group) groups.set(item.storage_root_id, (group = { id: item.storage_root_id, name: item.root_name, path: item.root_path, items: [], left: 0 }));
      group.items.push(item);
      if (!item.decision) group.left += 1;
    }
    return [...groups.values()].sort((a, b) => Number(b.left > 0) - Number(a.left > 0) || a.name.localeCompare(b.name));
  });
  let folder = $derived(folders.find((entry) => entry.id === folderId) ?? folders.find((entry) => entry.left > 0) ?? folders[0] ?? null);
  let people = $derived((folder?.items ?? []).filter((item) => show === 'all' || !item.decision || item.id === cursor)
    .sort((a, b) => Number(Boolean(a.decision)) - Number(Boolean(b.decision)) || String(a.display_name ?? '').localeCompare(String(b.display_name ?? ''))));
  function goFolder(step: 1 | -1) {
    const index = folders.findIndex((entry) => entry.id === folder?.id);
    const ahead = step === 1 ? [...folders.slice(index + 1), ...folders.slice(0, index)] : [...folders.slice(0, Math.max(0, index)).reverse()];
    const next = ahead.find((entry) => entry.left > 0) ?? (step === 1 ? null : ahead[0]);
    if (next) {
      folderId = next.id;
      cursor = null;
    }
  }

  // ---- what is said about a person: how the access comes, what to look at ----
  type Chip = { label: string; tone: 'ok' | 'grey' | 'bad' | 'warn' };
  const viaChips = (item: Item): Chip[] => item.via.map((via): Chip => via.kind === 'request' ? { label: t('request {code}', { code: via.code ?? '' }), tone: 'ok' }
    : via.kind === 'outside' ? { label: t('{group} (outside BornToShare)', { group: via.group ?? '' }), tone: 'bad' }
      : via.kind === 'ad_only' ? { label: t('{group} (added in the directory)', { group: via.group ?? '' }), tone: 'warn' }
        : { label: `${via.group ?? ''}${via.nested ? ` (${t('nested group')})` : ''}`, tone: 'grey' })
    .filter((chip, index, all) => chip.label && all.findIndex((other) => other.label === chip.label) === index);
  const signals = (item: Item): Chip[] => [
    ...(item.level === 'write' ? [{ label: t('Modify'), tone: 'warn' as const }] : []),
    ...(!item.username ? [{ label: t('Account unknown in the directory'), tone: 'bad' as const }] : [])
  ];
  const hint = (item: Item) => (!item.revocable && !item.decision ? t('Not granted by BornToShare: a removal is done by hand') : '');
  const initials = (item: Item) => String(item.display_name || item.username || '?').split(/\s+/).map((word) => word[0]).join('').slice(0, 2).toUpperCase();
  const OUTCOME = (): Record<string, string> => ({ revoked: t('Removed'), manual: t('To remove by hand'), failed: t('Removal failed') });

  // ---- keyboard: ↑ ↓ choose a person, G keep, R remove, → ← next / previous folder, Z undo ----
  function onKeys(event: KeyboardEvent) {
    const el = event.target as HTMLElement | null;
    if (!open || view !== 'decide' || menu || confirmApply || confirmClose || event.ctrlKey || event.metaKey || event.altKey
      || (el && (/^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName) || el.isContentEditable || el.closest('[role="dialog"]')))) return;
    const index = people.findIndex((item) => item.id === cursor);
    const current = index >= 0 ? people[index] : null;
    const key = event.key.toLowerCase();
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const next = people[Math.max(0, Math.min(people.length - 1, index + (event.key === 'ArrowDown' ? 1 : -1)))] ?? people[0];
      cursor = next?.id ?? null;
      document.getElementById(`rv-${cursor}`)?.scrollIntoView({ block: 'nearest' });
    } else if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
      event.preventDefault();
      goFolder(event.key === 'ArrowRight' ? 1 : -1);
    } else if ((key === 'g' || key === 'r') && current) {
      event.preventDefault();
      const following = people[index + 1]?.id ?? null;
      void decide([current], key === 'g' ? 'keep' : 'revoke').then(() => (cursor = following));
    } else if (key === 'z' && lastBefore) {
      event.preventDefault();
      void undo(lastBefore);
      lastBefore = null;
    }
  }

  // ---- right click on a person ----
  function menuItems(item: Item): ContextMenuItem[] {
    const done = Boolean(item.outcome) || !open;
    return [
      { key: 'keep', label: t('Keep the access'), icon: 'bi-check2', disabled: done || item.decision === 'keep' },
      { key: 'revoke', label: t('Remove the access'), icon: 'bi-x-lg', disabled: done || item.decision === 'revoke', danger: true },
      { key: 'reset', label: t('Back to « to review »'), icon: 'bi-arrow-counterclockwise', disabled: done || !item.decision },
      { key: 'person', label: t('See this person'), icon: 'bi-person', separated: true, disabled: !item.username },
      { key: 'folder', label: t('Open the folder'), icon: 'bi-folder2-open' },
      { key: 'copy', label: t('Copy the login'), icon: 'bi-clipboard', disabled: !item.username }
    ];
  }
  function pick(key: string) {
    const item = menu?.item;
    menu = null;
    if (!item) return;
    if (key === 'keep' || key === 'revoke') void decide([item], key);
    else if (key === 'reset') void decide([item], null, false);
    else if (key === 'person') window.location.assign(`/admin/identity?q=${encodeURIComponent(item.username ?? '')}`);
    else if (key === 'folder') window.location.assign(`/storage-roots?selected=${item.storage_root_id}`);
    else if (key === 'copy') void copyText(item.username ?? '').then((ok) => ok && toast.success(t('Login copied.')));
  }

  // ---- summary and application ----
  let counts = $derived.by(() => {
    const items = data?.items ?? [];
    const revoke = items.filter((item) => item.decision === 'revoke');
    return {
      total: items.length, todo: items.filter((item) => !item.decision).length, keep: items.filter((item) => item.decision === 'keep').length, revoke: revoke.length,
      pending: revoke.filter((item) => !item.outcome).length, auto: revoke.filter((item) => !item.outcome && item.revocable).length,
      manual: revoke.filter((item) => (!item.outcome && !item.revocable) || item.outcome === 'manual').length,
      done: revoke.filter((item) => item.outcome === 'revoked').length, failed: revoke.filter((item) => item.outcome === 'failed').length
    };
  });
  let removals = $derived((data?.items ?? []).filter((item) => item.decision === 'revoke'));
  const how = (item: Item) => item.revocable
    ? t('Leaves the group {group}', { group: item.via.find((via) => via.group)?.group ?? '—' })
    : t('By hand: remove the right in the properties of the folder');
  const pct = (part: number, whole: number) => (whole ? Math.round((part / whole) * 100) : 0);
  const due = (iso: string | null) => {
    if (!iso) return null;
    const days = Math.ceil((Date.parse(iso) - Date.now()) / 86400000);
    return days < 0 ? t('{count} day(s) late', { count: -days }) : days === 0 ? t('due today') : t('in {count} day(s)', { count: days });
  };

  async function applyRemovals() {
    confirmApply = false;
    busy = true;
    try {
      const result = await apiPostData<{ revoked: number; manual: number; failed: number }>(fetch, `/access-reviews/${reviewId}/apply`, {});
      toast.success(t('{revoked} access(es) removed, {manual} to remove by hand, {failed} failed.', { revoked: result?.revoked ?? 0, manual: result?.manual ?? 0, failed: result?.failed ?? 0 }));
      await load();
    } catch (failure) {
      reportUiError(failure, t('Unable to apply the removals.'), 'access-reviews.apply');
    } finally {
      busy = false;
    }
  }
  async function closeReview() {
    confirmClose = false;
    busy = true;
    try {
      await apiPostData(fetch, `/access-reviews/${reviewId}/close`, {});
      toast.success(t('Review closed.'));
      await load();
    } catch (failure) {
      reportUiError(failure, t('Unable to close the review.'), 'access-reviews.close');
    } finally {
      busy = false;
    }
  }

  const viaText = (item: Item) => viaChips(item).map((chip) => chip.label).join(' · ');
  const exportEvidence = () => downloadCsv(csvFilename(`revue-acces-${data?.review.name ?? reviewId}`), [
    { header: t('Folder'), value: (row: Item) => row.root_path }, { header: t('Person'), value: (row: Item) => row.display_name ?? '' },
    { header: t('Account'), value: (row: Item) => row.username ?? '' }, { header: t('Access'), value: (row: Item) => row.level ?? '' },
    { header: t('Through'), value: (row: Item) => viaText(row) }, { header: t('Decision'), value: (row: Item) => row.decision ?? '' },
    { header: t('Decided by'), value: (row: Item) => row.decided_by ?? '' }, { header: t('Date'), value: (row: Item) => row.decided_at ?? '' },
    { header: t('Result'), value: (row: Item) => (row.outcome ? OUTCOME()[row.outcome] : '') + (row.outcome_detail ? ` — ${row.outcome_detail}` : '') }
  ], data?.items ?? []);
</script>

<section class="v2 rv">
  {#if error}
    <p class="v2-empty">{error}</p>
  {:else if !data}
    <LoadingState />
  {:else}
    <header class="rv__card rv__head">
      <div class="rv__title">
        <h1>{data.review.name}</h1>
        <p>{t('Opened {date} by {who}', { date: formatDate(data.review.created_at), who: data.review.created_by ?? '—' })}
          · {t('{count} folder(s)', { count: folders.length })} · {t('{count} access(es)', { count: counts.total })}
          {#if open && data.review.due_at} · <b class="rv__due">{due(data.review.due_at)}</b>{/if}
          {#if !open && data.review.closed_at} · {t('closed {date}', { date: formatDate(data.review.closed_at) })}{/if}</p>
      </div>
      <div class="rv__acts">
        <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" onclick={exportEvidence}><i class="bi bi-download" aria-hidden="true"></i>{t('Export the evidence')}</button>
      </div>
      <div class="rv__progress">
        <div class="rv__bar" role="img" aria-label={t('{pct} % decided', { pct: pct(counts.keep + counts.revoke, counts.total) })}>
          <i class="is-keep" style={`width:${pct(counts.keep, counts.total)}%`}></i><i class="is-revoke" style={`width:${pct(counts.revoke, counts.total)}%`}></i>
        </div>
        <span><b>{pct(counts.keep + counts.revoke, counts.total)} %</b> {t('decided')} · <i class="rv__dot is-keep"></i>{t('{count} kept', { count: counts.keep })}
          · <i class="rv__dot is-revoke"></i>{t('{count} to remove', { count: counts.revoke })} · <i class="rv__dot"></i>{t('{count} to review', { count: counts.todo })}</span>
      </div>
      <nav class="v2-tabs rv__tabs" aria-label={t('Review')}>
        <button type="button" class:is-on={view === 'decide'} aria-current={view === 'decide' ? 'page' : undefined} onclick={() => (view = 'decide')}>{t('Decide')}{#if counts.todo}<b>{counts.todo}</b>{/if}</button>
        <button type="button" class:is-on={view === 'summary'} aria-current={view === 'summary' ? 'page' : undefined} onclick={() => (view = 'summary')}>{t('Summary and application')}{#if counts.pending}<b>{counts.pending}</b>{/if}</button>
      </nav>
    </header>

    {#if view === 'decide'}
      <div class="rv__work">
        <aside class="rv__card rv__rail" aria-label={t('Folders of the review')}>
          <label class="v2-search"><i class="bi bi-search" aria-hidden="true"></i><input type="search" bind:value={query} placeholder={t('Folder or person…')} aria-label={t('Find a folder or a person')} /></label>
          <span class="rv__railhead">{t('Folders · {count}', { count: folders.length })}</span>
          {#each folders as entry (entry.id)}
            {@const done = entry.items.length - entry.left}
            <button type="button" class="rv__folder" class:is-on={entry.id === folder?.id} aria-current={entry.id === folder?.id ? 'true' : undefined}
              onclick={() => { folderId = entry.id; cursor = null; }}>
              <span class="rv__fname"><span>{entry.name}</span><i class="rv__fbar"><i style={`width:${pct(done, entry.items.length)}%`}></i></i></span>
              {#if entry.left}<b class="rv__left">{entry.left}</b>{:else}<i class="bi bi-check2 rv__ok" aria-label={t('All decided')}></i>{/if}
            </button>
          {:else}
            <p class="rv__none">{t('No folder matches.')}</p>
          {/each}
        </aside>

        <div class="rv__main">
          {#if folder}
            <div class="rv__card rv__fhead">
              <div class="rv__ftitle"><h2>{folder.name}</h2><code>{folder.path}</code></div>
              <span class="rv__fsum">{folder.left ? t('{left} access(es) to review out of {count}', { left: folder.left, count: folder.items.length }) : t('Everything is decided here')}</span>
              <div class="v2-seg" role="group" aria-label={t('Show')}>
                <button type="button" class:is-on={show === 'todo'} onclick={() => (show = 'todo')}>{t('To review')}</button>
                <button type="button" class:is-on={show === 'all'} onclick={() => (show = 'all')}>{t('All')}</button>
              </div>
              {#if open && folder.left}
                <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" disabled={busy} onclick={() => decide(folder?.items.filter((item) => !item.decision) ?? [], 'keep')}>{t('Keep all the others')}</button>
              {/if}
              {#if open && !folder.left && folders.some((entry) => entry.left)}
                <button type="button" class="b2s-btn b2s-btn-primary b2s-btn-sm" onclick={() => goFolder(1)}>{t('Next folder')} <i class="bi bi-arrow-right" aria-hidden="true"></i></button>
              {/if}
            </div>

            {#each people as item (item.id)}
              <article id={`rv-${item.id}`} class="rv__card rv__person" class:is-keep={item.decision === 'keep'} class:is-revoke={item.decision === 'revoke'} class:is-cursor={cursor === item.id}
                oncontextmenu={(event) => { event.preventDefault(); menu = { item, at: menuPositionFor(event) }; }}>
                <span class="rv__avatar" aria-hidden="true">{initials(item)}</span>
                <div class="rv__who">
                  <span class="rv__name"><b>{item.display_name ?? item.username ?? '—'}</b><small>{item.username ?? t('account unknown')}</small></span>
                  <span class="rv__chips">
                    <span class={`rv__chip is-${item.level === 'write' ? 'dark' : 'grey'}`}>{item.level === 'write' ? t('Modify') : t('Read')}</span>
                    {#each viaChips(item) as chip (chip.label)}<span class={`rv__chip is-${chip.tone}`}>{chip.label}</span>{/each}
                    {#each signals(item).filter((chip) => chip.label !== t('Modify')) as chip (chip.label)}<span class={`rv__chip is-${chip.tone}`}>{chip.label}</span>{/each}
                  </span>
                  {#if item.outcome}<small class={`rv__note is-${item.outcome}`}>{OUTCOME()[item.outcome]}{item.outcome_detail ? ` — ${item.outcome_detail}` : ''}</small>
                  {:else if item.decision}<small class="rv__note">{item.decision === 'keep' ? t('Kept') : t('To remove')} · {item.decided_by ?? ''} {item.decided_at ? formatDateTime(item.decided_at) : ''}</small>
                  {:else if hint(item)}<small class="rv__note is-warn">{hint(item)}</small>{/if}
                </div>
                <div class="rv__choice" role="group" aria-label={t('Decision for {name}', { name: item.display_name ?? item.username ?? '' })}>
                  <button type="button" class="is-keep" class:is-on={item.decision === 'keep'} aria-pressed={item.decision === 'keep'} disabled={!open || Boolean(item.outcome) || busy}
                    onclick={() => toggleDecision(item, 'keep')}><i class="bi bi-check2" aria-hidden="true"></i>{t('Keep')}</button>
                  <button type="button" class="is-revoke" class:is-on={item.decision === 'revoke'} aria-pressed={item.decision === 'revoke'} disabled={!open || Boolean(item.outcome) || busy}
                    onclick={() => toggleDecision(item, 'revoke')}><i class="bi bi-x-lg" aria-hidden="true"></i>{t('Withdraw')}</button>
                </div>
              </article>
            {:else}
              <p class="v2-empty">{t('Everything is decided here.')} {#if folders.some((entry) => entry.left)}<button type="button" class="b2s-link-btn" onclick={() => goFolder(1)}>{t('Next folder')}</button>{/if}</p>
            {/each}
            {#if open}
              <p class="rv__keys"><kbd>↑</kbd><kbd>↓</kbd> {t('choose')} · <kbd>G</kbd> {t('keep')} · <kbd>R</kbd> {t('remove')} · <kbd>→</kbd> {t('next folder')} · <kbd>Z</kbd> {t('undo')} · {t('right click: every action')}</p>
            {/if}
          {:else}
            <p class="v2-empty">{t('Nothing to review in this review.')}</p>
          {/if}
        </div>
      </div>
    {:else}
      <div class="rv__stats">
        <div class="rv__card rv__stat"><span>{t('Removed automatically')}</span><b>{counts.auto + counts.done}</b><small>{counts.done ? t('{count} already removed', { count: counts.done }) : t('granted by a request: the person leaves the AD group of the folder')}</small></div>
        <div class="rv__card rv__stat is-warn"><span>{t('To remove by hand')}</span><b>{counts.manual}</b><small>{t('rights set outside BornToShare: the way to do it comes with each one')}</small></div>
        <div class="rv__card rv__stat"><span>{t('Still to decide')}</span><b>{counts.todo}</b><small>{t('the guardians are reminded by the notifications')}</small></div>
      </div>

      <section class="rv__card rv__list" aria-label={t('Accesses to remove')}>
        <div class="rv__lhead">
          <h2>{t('Accesses to remove')}</h2>
          <span>{t('{count} decision(s) « remove »', { count: counts.revoke })}</span>
          {#if open && counts.pending}
            <button type="button" class="b2s-btn b2s-btn-sm rv__apply" disabled={busy} onclick={() => (confirmApply = true)}>{t('Apply the {count} removal(s)', { count: counts.pending })}</button>
          {/if}
        </div>
        <div class="rv__row is-head"><span>{t('Person')}</span><span>{t('Folder')}</span><span>{t('How')}</span><span>{t('Result')}</span></div>
        {#each removals as item (item.id)}
          <div class="rv__row">
            <span><b>{item.display_name ?? item.username ?? '—'}</b> <small>{item.username ?? ''}</small></span>
            <span>{item.root_name}</span>
            <span class="rv__how">{how(item)}</span>
            <span class={`rv__res is-${item.outcome ?? (item.revocable ? 'pending' : 'manual')}`}>{item.outcome ? OUTCOME()[item.outcome] : item.revocable ? t('waiting') : t('To remove by hand')}</span>
          </div>
        {:else}
          <p class="v2-empty">{t('No access to remove so far.')}</p>
        {/each}
      </section>

      {#if open && isAdmin}
        <section class="rv__card rv__close">
          <div><h2>{t('Close the review')}</h2><p>{t('The review becomes read only; its export (who decided what, when, and the result) is the evidence for the audit.')}</p></div>
          <button type="button" class="b2s-btn b2s-btn-secondary" disabled={busy} onclick={() => (confirmClose = true)}>{t('Close the review')}</button>
        </section>
      {/if}
    {/if}
  {/if}
</section>

<svelte:window onkeydown={onKeys} />
<ContextMenu open={Boolean(menu)} title={menu?.item.display_name ?? ''} subtitle={menu?.item.root_name ?? ''} items={menu ? menuItems(menu.item) : []}
  at={menu?.at ?? { x: 0, y: 0 }} onClose={() => (menu = null)} onPick={pick} />
<ConfirmActionModal open={confirmApply} title={t('Apply the removals')}
  subtitle={t('{count} access(es) decided « remove »: those granted by a request are revoked now (the person leaves the AD group of the folder); the others are marked « to remove by hand ».', { count: counts.pending })}
  confirmLabel={t('Remove the accesses')} onConfirm={applyRemovals} onClose={() => (confirmApply = false)} />
<ConfirmActionModal open={confirmClose} title={t('Close the review')}
  subtitle={t('The review becomes read only; its export (who decided what, when, and the result) is the evidence for the audit.')}
  confirmLabel={t('Close the review')} onConfirm={closeReview} onClose={() => (confirmClose = false)} />

<style>
  .rv { display: grid; gap: 14px; }
  .rv__card { border: 1px solid var(--b2s-color-border-soft); border-radius: 16px; background: #fff; }
  .rv__head { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 12px 16px; padding: 16px 18px 0; }
  .rv__title h1 { margin: 0; font-size: 24px; font-weight: 600; letter-spacing: -0.02em; }
  .rv__title p { margin: 4px 0 0; color: var(--b2s-color-text-muted); font-size: 13px; }
  .rv__due { color: var(--b2s-color-warning-strong); }
  .rv__acts { display: flex; gap: 8px; align-items: flex-start; }
  .rv__progress { grid-column: 1 / -1; display: grid; gap: 6px; font-size: 12.5px; color: var(--b2s-color-text-soft); }
  .rv__bar { display: flex; height: 8px; border-radius: 999px; overflow: hidden; background: var(--b2s-color-surface-muted); }
  .rv__bar i, .rv__fbar i { display: block; height: 100%; }
  .is-keep.rv__dot, .rv__bar .is-keep { background: var(--b2s-accent); }
  .is-revoke.rv__dot, .rv__bar .is-revoke { background: var(--b2s-color-danger-strong); }
  .rv__dot { display: inline-block; width: 9px; height: 9px; margin: 0 4px -1px 2px; border-radius: 3px; background: var(--b2s-color-neutral-soft); }
  .rv__tabs { grid-column: 1 / -1; margin: 0 -18px; padding: 0 18px; border-bottom: 0; }
  .rv__tabs button { background: none; font: inherit; font-size: 14px; color: var(--b2s-color-text-muted); cursor: pointer; }
  .rv__work { display: grid; grid-template-columns: 290px minmax(0, 1fr); gap: 16px; align-items: start; }
  .rv__rail { position: sticky; top: calc(var(--b2s-shell-top) + 12px); display: grid; gap: 4px; max-height: calc(100vh - var(--b2s-shell-top) - 80px); overflow: auto; padding: 10px; }
  .rv__railhead { padding: 8px 6px 2px; color: var(--b2s-color-text-muted); font-size: 11px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; }
  .rv__folder { display: flex; align-items: center; gap: 10px; width: 100%; padding: 8px 10px; border: 0; border-radius: 10px; background: none; font: inherit; font-size: 13.5px; color: var(--b2s-color-text); text-align: left; cursor: pointer; }
  .rv__folder:hover { background: var(--b2s-color-surface-soft); }
  .rv__folder.is-on { background: var(--b2s-accent); color: #fff; }
  .rv__fname { flex: 1; min-width: 0; display: grid; gap: 6px; }
  .rv__fname > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; }
  .rv__fbar { display: block; height: 4px; border-radius: 999px; overflow: hidden; background: var(--b2s-color-surface-muted); }
  .rv__fbar i { background: var(--b2s-accent); }
  .rv__folder.is-on .rv__fbar { background: var(--b2s-color-text-soft); }
  .rv__folder.is-on .rv__fbar i { background: #fff; }
  .rv__left { flex: none; padding: 1px 8px; border-radius: 999px; background: var(--b2s-color-surface-muted); color: var(--b2s-color-text-soft); font-size: 12px; }
  .rv__folder.is-on .rv__left { background: #fff; color: var(--b2s-accent); }
  .rv__ok { color: var(--b2s-color-success-strong); }
  .rv__folder.is-on .rv__ok { color: #fff; }
  .rv__none { margin: 8px; color: var(--b2s-color-text-muted); font-size: 13px; }
  .rv__main { display: grid; gap: 10px; min-width: 0; }
  .rv__fhead { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 14px; padding: 14px 16px; }
  .rv__ftitle { flex: 1 1 280px; min-width: 0; display: grid; }
  .rv__ftitle h2 { margin: 0; font-size: 18px; font-weight: 600; }
  .rv__ftitle code { color: var(--b2s-color-text-muted); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .rv__fsum { color: var(--b2s-color-text-soft); font-size: 13px; }
  .rv__person { display: flex; flex-wrap: wrap; align-items: center; gap: 14px; padding: 14px 16px; }
  .rv__person.is-keep { border-color: var(--b2s-color-border); }
  .rv__person.is-revoke { border-color: var(--b2s-color-danger-border); background: var(--b2s-color-danger-soft); }
  .rv__person.is-cursor { box-shadow: inset 3px 0 0 var(--b2s-accent); }
  .rv__avatar { width: 40px; height: 40px; flex: none; display: flex; align-items: center; justify-content: center; border-radius: 50%; background: var(--b2s-color-surface-muted); font-size: 13px; font-weight: 700; }
  .rv__who { flex: 1 1 260px; min-width: 0; display: grid; gap: 6px; }
  .rv__name { display: flex; flex-wrap: wrap; gap: 8px; align-items: baseline; }
  .rv__name b { font-size: 15px; font-weight: 600; }
  .rv__name small { color: var(--b2s-color-text-muted); font-size: 12.5px; }
  .rv__chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .rv__chip { padding: 2px 9px; border-radius: 999px; font-size: 11.5px; font-weight: 600; }
  .rv__chip.is-dark { background: var(--b2s-topbar-bg); color: #fff; }
  .rv__chip.is-grey { background: var(--b2s-color-surface-muted); color: var(--b2s-color-text-soft); }
  .rv__chip.is-ok { background: var(--b2s-color-success-soft); color: var(--b2s-color-success-strong); }
  .rv__chip.is-warn { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .rv__chip.is-bad { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger-strong); }
  .rv__note { color: var(--b2s-color-text-muted); font-size: 12.5px; }
  .rv__note.is-warn, .rv__note.is-manual { color: var(--b2s-color-warning-strong); }
  .rv__note.is-revoked { color: var(--b2s-color-success-strong); }
  .rv__note.is-failed { color: var(--b2s-color-danger-strong); }
  .rv__choice { display: flex; gap: 3px; padding: 3px; border: 1px solid var(--b2s-color-border-soft); border-radius: 10px; background: var(--b2s-color-surface-soft); }
  .rv__choice button { display: inline-flex; align-items: center; gap: 6px; height: 34px; padding: 0 12px; border: 0; border-radius: 8px; background: none; font: inherit; font-size: 13px; font-weight: 600; color: var(--b2s-color-text-soft); cursor: pointer; }
  .rv__choice button:disabled { cursor: default; opacity: 0.6; }
  .rv__choice button.is-keep.is-on { background: var(--b2s-accent); color: #fff; opacity: 1; }
  .rv__choice button.is-revoke.is-on { background: var(--b2s-color-danger-strong); color: #fff; opacity: 1; }
  .rv__choice button:not(:disabled):not(.is-on):hover { background: #fff; }
  .rv__keys { margin: 4px 0 0; color: var(--b2s-color-text-muted); font-size: 12.5px; }
  .rv__keys kbd { margin: 0 2px; padding: 0 5px; border: 1px solid var(--b2s-color-border); border-radius: 5px; background: #fff; font-size: 11px; }
  .rv__stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
  .rv__stat { display: grid; gap: 6px; padding: 16px; }
  .rv__stat span { color: var(--b2s-color-text-muted); font-size: 12px; }
  .rv__stat b { font-size: 28px; font-weight: 600; }
  .rv__stat small { color: var(--b2s-color-text-soft); font-size: 13px; }
  .rv__stat.is-warn { border-color: var(--b2s-color-warning-border); }
  .rv__stat.is-warn span, .rv__stat.is-warn b { color: var(--b2s-color-warning-strong); }
  .rv__list { overflow: hidden; }
  .rv__lhead { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; padding: 12px 16px; border-bottom: 1px solid var(--b2s-color-border-soft); }
  .rv__lhead h2 { margin: 0; font-size: 15px; font-weight: 600; }
  .rv__lhead span { color: var(--b2s-color-text-muted); font-size: 13px; }
  .rv__apply { margin-left: auto; border: 0; background: var(--b2s-color-danger-strong); color: #fff; }
  .rv__apply:hover:not(:disabled) { background: var(--b2s-color-danger-strong); color: #fff; }
  .rv__row { display: grid; grid-template-columns: minmax(200px, 1.2fr) minmax(160px, 1fr) minmax(220px, 1.4fr) 160px; gap: 12px; align-items: center; min-height: 44px; padding: 0 16px;
    border-bottom: 1px solid var(--b2s-color-surface-soft); font-size: 13px; }
  .rv__row.is-head { min-height: 36px; color: var(--b2s-color-text-muted); font-size: 12px; font-weight: 500; }
  .rv__row small { color: var(--b2s-color-text-muted); }
  .rv__how { color: var(--b2s-color-text-soft); }
  .rv__res { justify-self: start; padding: 2px 9px; border-radius: 999px; font-size: 12px; font-weight: 600; background: var(--b2s-color-surface-muted); color: var(--b2s-color-text-soft); }
  .rv__res.is-revoked { background: var(--b2s-color-success-soft); color: var(--b2s-color-success-strong); }
  .rv__res.is-manual { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .rv__res.is-failed { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger-strong); }
  .rv__close { display: flex; flex-wrap: wrap; align-items: center; gap: 14px; padding: 16px; }
  .rv__close div { flex: 1 1 360px; }
  .rv__close h2 { margin: 0; font-size: 15px; font-weight: 600; }
  .rv__close p { margin: 4px 0 0; color: var(--b2s-color-text-muted); font-size: 13px; }
</style>
