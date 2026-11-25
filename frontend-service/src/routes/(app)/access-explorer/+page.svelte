<script lang="ts">
  /**
   * Access Explorer: who reaches what, and why. Four ways in (a user, a group, a folder path, a governed folder); the
   * answer comes from core-service (/access-explorer: the last ACL read of each folder and the active directory reading,
   * paged by the server, limited to the folders of a guardian). Each way in is explained in a sentence with its full
   * path, and what is not known (share permissions, sub-folders, account state…) is always said.
   */
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { apiGetData } from '$lib/api/client';
  import { t } from '$lib/i18n';
  import SegmentedFilter from '$lib/components/ui/SegmentedFilter.svelte';
  import SearchField from '$lib/components/ui/SearchField.svelte';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import EmptyStateInline from '$lib/components/ui/EmptyStateInline.svelte';
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import RelativeTime from '$lib/components/ui/RelativeTime.svelte';
  import Drawer from '$lib/components/ui/Drawer.svelte';
  import { LIMITS, RIGHTS_LABEL, explainGrant, grantChain, type Grant } from '$lib/utils/access-explain';

  type Mode = 'user' | 'group' | 'folder' | 'root';
  type Suggestion = { id: number; label: string; detail: string | null; source: string | null };
  type Paged<T> = { items: T[]; total: number; offset: number; limit: number; broad_total?: number };
  type Reached = { storage_root_id: number; name: string; root_path: string; endpoint_name: string; grants: Grant[]; ntfs_rights: string | null;
    denied: boolean; paths: number; multiple_paths: boolean; inherited_only: boolean; inheritance_broken: boolean };
  type Person = { user_id: number; username: string; display_name: string; state: string; grants: Grant[]; ntfs_rights: string | null; denied: boolean; multiple_paths: boolean };
  type GroupRef = { group_id: number | null; name: string; depth: number; via: string[] };

  const PAGE = 50;
  const MODES: Array<{ key: Mode; label: string }> = [
    { key: 'user', label: t('access_explorer.mode_user') },
    { key: 'group', label: t('access_explorer.mode_group') },
    { key: 'folder', label: t('access_explorer.mode_folder') },
    { key: 'root', label: t('access_explorer.mode_root') }
  ];
  const PLACEHOLDER: Record<Mode, string> = {
    user: t('Name, login or e-mail of a user'),
    group: t('Name of an AD group'),
    folder: t('Path of a folder (\\\\server\\share\\folder)'),
    root: t('Name of a governed folder')
  };
  const KIND_LABEL: Record<string, string> = {
    direct: t('Own account'), group: t('Group'), nested: t('Nested group'), parent: t('Through a parent group'), broad: t('Whole company'),
    user: t('User'), system: t('System'), orphan: t('Orphan SID'), unknown: t('Unknown account')
  };
  const STATE: Record<string, { label: string; variant: 'success' | 'error' | 'muted' | 'warning' }> = {
    enabled: { label: t('Enabled'), variant: 'success' }, disabled: { label: t('Disabled'), variant: 'error' },
    unknown: { label: t('State unknown'), variant: 'muted' }, not_in_directory: { label: t('Not in the directory'), variant: 'warning' }
  };
  const rightLabel = (rights: string | null | undefined) => (rights ? t(RIGHTS_LABEL[rights] ?? rights) : '—');
  const rightTone = (rights: string | null | undefined) => (rights === 'full' || rights === 'modify' ? 'warn' : rights ? 'ok' : 'mut');
  const kinds = (grants: Grant[]) => [...new Set(grants.map((g) => g.kind))];

  let mode = $state<Mode>('user');
  let query = $state('');
  let suggestions = $state<Suggestion[]>([]);
  let suggestTotal = $state(0);
  let suggesting = $state(false);
  let detail = $state<any>(null);
  let loading = $state(false);
  let error = $state('');
  let offset = $state(0);
  let includeBroad = $state(false);
  let level = $state('all');
  let filter = $state('');
  let resolvedBelow = $state<string | null>(null);
  let selected = $state<{ who: string; folder: string; grants: Grant[] } | null>(null);
  let timer: ReturnType<typeof setTimeout> | undefined;

  // The selection lives in the address: a link to an explanation can be shared
  let target = $derived({ mode: ($page.url.searchParams.get('mode') ?? 'user') as Mode, id: Number($page.url.searchParams.get('id') || 0) });

  onMount(() => {
    mode = target.mode;
  });

  $effect(() => {
    const { mode: m, id } = target;
    void offset; void includeBroad; void level;
    if (id) load(m, id);
    else detail = null;
  });

  async function load(m: Mode, id: number) {
    loading = true;
    error = '';
    try {
      const common = { offset, limit: PAGE, ...(filter.trim() ? { q: filter.trim() } : {}) };
      if (m === 'user') detail = await apiGetData(fetch, `/access-explorer/users/${id}`, { ...common, include_broad: includeBroad });
      else if (m === 'group') detail = await apiGetData(fetch, `/access-explorer/groups/${id}`, common);
      else detail = await apiGetData(fetch, `/access-explorer/folders/${id}`, { ...common, ...(level !== 'all' ? { level } : {}) });
    } catch (failure) {
      detail = null;
      error = failure instanceof Error ? failure.message : t('Unable to load the access of this entry.');
    } finally {
      loading = false;
    }
  }

  function open(m: Mode, id: number | null | undefined) {
    if (!id) return;
    offset = 0;
    filter = '';
    suggestions = [];
    mode = m === 'folder' ? 'folder' : m;
    void goto(`/access-explorer?mode=${m}&id=${id}`, { keepFocus: true, noScroll: true });
  }

  function onType(value: string) {
    query = value;
    clearTimeout(timer);
    if (value.trim().length < 2) {
      suggestions = [];
      return;
    }
    timer = setTimeout(async () => {
      suggesting = true;
      try {
        const found = await apiGetData<Paged<Suggestion>>(fetch, '/access-explorer/search', { mode, q: value.trim(), limit: 8 });
        suggestions = found.items;
        suggestTotal = found.total;
      } catch {
        suggestions = [];
      } finally {
        suggesting = false;
      }
    }, 200);
  }

  // A full path in Folder mode: the governed folder holding it
  async function onEnter(value: string) {
    if (mode === 'folder' && /[\\/]/.test(value)) {
      try {
        const found = await apiGetData<{ storage_root_id: number; below: boolean }>(fetch, '/access-explorer/resolve', { path: value.trim() });
        resolvedBelow = found.below ? value.trim() : null;
        open('folder', found.storage_root_id);
      } catch {
        error = t('No governed folder holds this path.');
      }
    } else if (suggestions[0]) {
      open(mode, suggestions[0].id);
    }
  }

  let folders = $derived<Paged<Reached> | null>(detail?.folders ?? null);
  let people = $derived<Paged<Person> | null>(detail?.people ?? null);
  let pager = $derived(folders ?? people);
  let subject = $derived(detail?.user?.display_name ?? detail?.group?.name ?? detail?.folder?.name ?? '');
</script>

<svelte:head><title>Access Explorer · BornToShare</title></svelte:head>

<section class="v2 ax">
  <div class="v2-head">
    <div>
      <h1>Access Explorer</h1>
      <p>{t('Who reaches what, and why: from the last ACL read of the folders and the last reading of the directory.')}</p>
    </div>
    <div class="v2-head__r"><a class="b2s-btn b2s-btn-secondary" href="/exposure"><i class="bi bi-globe2" aria-hidden="true"></i>{t('Exposure map')}</a></div>
  </div>

  <div class="v2-sec ax__search">
    <SegmentedFilter options={MODES} bind:value={mode} ariaLabel={t('Search by')} onChange={() => { suggestions = []; query = ''; }} />
    <div class="ax__field">
      <SearchField value={query} placeholder={PLACEHOLDER[mode]} ariaLabel={PLACEHOLDER[mode]} onChange={onType} onEnter={onEnter} />
      {#if suggestions.length || suggesting}
        <ul class="ax__suggest" role="listbox" aria-label={t('Suggestions')}>
          {#if suggesting && !suggestions.length}<li class="ax__hint"><LoadingState>{t('Searching…')}</LoadingState></li>{/if}
          {#each suggestions as item (item.id)}
            <li role="option" aria-selected="false">
              <button type="button" onclick={() => open(mode, item.id)}>
                <b>{item.label}</b>{#if item.detail}<small>{item.detail}</small>{/if}{#if item.source}<span class="v2-tag is-mut">{item.source}</span>{/if}
              </button>
            </li>
          {/each}
          {#if suggestTotal > suggestions.length}<li class="ax__hint">{t('{n} more: refine the search', { n: suggestTotal - suggestions.length })}</li>{/if}
        </ul>
      {/if}
    </div>
  </div>

  {#if error}<InlineAlert tone="error">{error}</InlineAlert>{/if}

  {#if loading && !detail}
    <LoadingState block skeleton="rows">{t('Loading…')}</LoadingState>
  {:else if detail}
    <!-- Who or what -->
    <div class="v2-sec">
      {#if detail.user}
        <div class="v2-sh"><h2><i class="bi bi-person" aria-hidden="true"></i> {detail.user.display_name}</h2>
          {#if STATE[detail.user.state]}<StatusBadge variant={STATE[detail.user.state].variant} label={STATE[detail.user.state].label} compact />{/if}</div>
        <dl class="ax__facts">
          <dt>{t('Login')}</dt><dd>{detail.user.username ?? '—'}</dd>
          <dt>UPN</dt><dd>{detail.user.upn ?? '—'}</dd>
          <dt>{t('Directory')}</dt><dd>{detail.user.source_name}</dd>
          <dt>DN</dt><dd class="ax__mono">{detail.user.dn ?? '—'}</dd>
        </dl>
        {#if detail.user.state === 'disabled'}<p class="v2-hint">{t('Account disabled in the directory: it cannot sign in, but the entries naming it or its groups stay on the folders.')}</p>{/if}
        <div class="ax__groups">
          <div><h3>{t('Direct groups')} <span class="v2-tag is-mut">{detail.groups.direct.length}</span></h3>
            {#each detail.groups.direct as g (g.name)}<button type="button" class="ax__chip" onclick={() => open('group', g.group_id)} disabled={!g.group_id}>{g.name}</button>{:else}<p class="v2-empty">{t('None')}</p>{/each}</div>
          <div><h3>{t('Nested groups')} <span class="v2-tag is-mut">{detail.groups.nested.length}</span></h3>
            {#each detail.groups.nested as g (g.name)}<button type="button" class="ax__chip" title={g.via.join(' › ')} onclick={() => open('group', g.group_id)} disabled={!g.group_id}>{g.name} <small>{t('via {group}', { group: g.via[0] })}</small></button>{:else}<p class="v2-empty">{t('None')}</p>{/each}</div>
        </div>
      {:else if detail.group}
        <div class="v2-sh"><h2><i class="bi bi-people" aria-hidden="true"></i> {detail.group.name}</h2>{#if detail.group.broad}<span class="v2-tag is-bad">{t('Whole company')}</span>{/if}</div>
        {#if detail.group.description}<p class="v2-hint">{detail.group.description}</p>{/if}
        <div class="v2-stats">
          <div class="v2-stat"><b>{detail.exposure.effective_users ?? '—'}</b><span>{t('People (nested included)')}</span></div>
          <div class="v2-stat"><b>{detail.exposure.disabled_users ?? '—'}</b><span>{t('Disabled accounts')}</span></div>
          <div class="v2-stat"><b>{detail.exposure.folders}</b><span>{t('Folders reached')}</span></div>
          <div class="v2-stat"><b>{detail.nested_total}</b><span>{t('Nested groups')}</span></div>
        </div>
        <div class="ax__groups">
          <div><h3>{t('Direct members')} <span class="v2-tag is-mut">{detail.members.users_total}</span></h3>
            {#each detail.members.users as u (u.username)}<button type="button" class="ax__chip" onclick={() => open('user', u.user_id)} disabled={!u.user_id}>{u.display_name ?? u.username}{#if u.state === 'disabled'} <small class="ax__off">{t('disabled')}</small>{/if}</button>{:else}<p class="v2-empty">{t('None')}</p>{/each}
            {#if detail.members.users_total > detail.members.users.length}<p class="v2-hint">{t('{n} more', { n: detail.members.users_total - detail.members.users.length })}</p>{/if}</div>
          <div><h3>{t('Nested groups')}</h3>
            {#each detail.nested_groups as g (g.name)}<button type="button" class="ax__chip" title={g.via.join(' › ')} onclick={() => open('group', g.group_id)} disabled={!g.group_id}>{g.name}{#if g.depth > 0} <small>{t('level {n}', { n: g.depth + 1 })}</small>{/if}</button>{:else}<p class="v2-empty">{t('None')}</p>{/each}</div>
          <div><h3>{t('Member of')}</h3>
            {#each detail.parent_groups as g (g.name)}<button type="button" class="ax__chip" title={g.via.join(' › ')} onclick={() => open('group', g.group_id)} disabled={!g.group_id}>{g.name}</button>{:else}<p class="v2-empty">{t('None')}</p>{/each}</div>
        </div>
      {:else if detail.folder}
        <div class="v2-sh"><h2><i class="bi bi-folder2" aria-hidden="true"></i> {detail.folder.name}</h2>
          <div class="v2-sh__r"><a href={`/storage-roots?selected=${detail.folder.storage_root_id}`}>{t('Open its sheet')}</a></div></div>
        <p class="v2-hint ax__mono">{detail.folder.root_path} · {detail.folder.endpoint_name} · {detail.folder.zone_name}</p>
        {#if resolvedBelow}<InlineAlert tone="info" compact>{t('{path} is inside this governed folder: the rights shown are the ones read on it.', { path: resolvedBelow })}</InlineAlert>{/if}
        <div class="v2-stats">
          <div class="v2-stat"><b>{detail.summary.explicit}</b><span>{t('Explicit entries')}</span></div>
          <div class="v2-stat"><b>{detail.summary.inherited}</b><span>{t('Inherited entries')}</span></div>
          <div class="v2-stat"><b>{detail.summary.people}</b><span>{t('People reached')}</span></div>
          <div class="v2-stat"><i class={`bi bi-globe2 ${detail.summary.broad ? 'is-bad' : ''}`} aria-hidden="true"></i><b>{detail.summary.broad}</b><span>{t('Entries open to everyone')}</span></div>
        </div>
        <table class="b2s-table ax__table">
          <thead><tr><th>{t('Account or group')}</th><th>{t('Kind')}</th><th>{t('Right')}</th><th>{t('Origin')}</th><th>{t('Members')}</th></tr></thead>
          <tbody>
            {#each detail.principals as p, i (i)}
              <tr>
                <td>{#if p.group_id}<button type="button" class="b2s-link-btn" onclick={() => open('group', p.group_id)}>{p.principal}</button>
                  {:else if p.user_id}<button type="button" class="b2s-link-btn" onclick={() => open('user', p.user_id)}>{p.principal}</button>{:else}{p.principal}{/if}</td>
                <td><span class={`v2-tag is-${p.kind === 'broad' || p.kind === 'orphan' ? 'bad' : p.kind === 'unknown' ? 'warn' : 'mut'}`}>{KIND_LABEL[p.kind] ?? p.kind}</span></td>
                <td>{#if p.deny}<span class="v2-tag is-bad">{t('Denied')}: {rightLabel(p.rights)}</span>{:else}<span class={`v2-tag is-${rightTone(p.rights)}`}>{rightLabel(p.rights)}</span>{/if}</td>
                <td>{p.inherited ? t('Inherited') : t('Explicit')}</td>
                <td>{p.members ?? ''}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
      {#if detail.snapshot_at || detail.folder?.acl_read_at}
        <p class="v2-hint">{#if detail.folder?.acl_read_at}{t('ACL read')} <RelativeTime value={detail.folder.acl_read_at} /> · {/if}{#if detail.snapshot_at}{t('Directory read')} <RelativeTime value={detail.snapshot_at} />{/if}</p>
      {/if}
    </div>

    <!-- Folders reached (user, group) or people (folder) -->
    <div class="v2-sec">
      <div class="v2-sh">
        <h2>{folders ? t('Folders reached') : t('People who reach it')}</h2>{#if pager}<span class="v2-tag is-mut">{pager.total}</span>{/if}
        <div class="v2-sh__r ax__filters">
          {#if people}
            <SegmentedFilter options={[{ key: 'all', label: t('All') }, { key: 'write', label: t('Modify') }, { key: 'read', label: t('Read') }]} bind:value={level} onChange={() => (offset = 0)} />
          {/if}
          {#if detail.user}
            <label class="ax__check"><input type="checkbox" bind:checked={includeBroad} onchange={() => (offset = 0)} /> {t('Include the entries open to everyone')}{#if folders?.broad_total} ({folders.broad_total}){/if}</label>
          {/if}
          <SearchField bind:value={filter} placeholder={t('Filter')} ariaLabel={t('Filter')} onEnter={() => { offset = 0; load(target.mode, target.id); }} />
        </div>
      </div>
      {#if loading}<LoadingState block skeleton="rows">{t('Loading…')}</LoadingState>
      {:else if folders}
        {#if folders.items.length}
          <table class="b2s-table ax__table">
            <thead><tr><th>{t('Folder')}</th><th>{t('NTFS right')}</th><th>{t('How')}</th><th>{t('Paths')}</th><th></th></tr></thead>
            <tbody>
              {#each folders.items as f (f.storage_root_id)}
                <tr class="ax__row" onclick={() => (selected = { who: subject, folder: f.name, grants: f.grants })}>
                  <td><b>{f.name}</b><small class="ax__mono">{f.root_path}</small></td>
                  <td><span class={`v2-tag is-${rightTone(f.ntfs_rights)}`}>{rightLabel(f.ntfs_rights)}</span>{#if f.denied} <span class="v2-tag is-bad">{t('Deny entry')}</span>{/if}</td>
                  <td>{#each kinds(f.grants) as k (k)}<span class="v2-tag is-mut">{KIND_LABEL[k]}</span> {/each}{#if f.inherited_only}<small>{t('inherited')}</small>{/if}</td>
                  <td>{f.paths}{#if f.multiple_paths} <span class="v2-tag is-info">{t('several')}</span>{/if}</td>
                  <td><button type="button" class="b2s-link-btn">{t('Why?')}</button></td>
                </tr>
              {/each}
            </tbody>
          </table>
        {:else}
          <EmptyStateInline message={folders.broad_total ? t('No folder names this account or its groups; {n} folder(s) are open to everyone.', { n: folders.broad_total }) : t('No folder reached according to the ACL read.')} />
        {/if}
      {:else if people}
        {#if people.items.length}
          <table class="b2s-table ax__table">
            <thead><tr><th>{t('Person')}</th><th>{t('Account')}</th><th>{t('NTFS right')}</th><th>{t('How')}</th><th></th></tr></thead>
            <tbody>
              {#each people.items as p (p.user_id)}
                <tr class="ax__row" onclick={() => (selected = { who: p.display_name ?? p.username, folder: subject, grants: p.grants })}>
                  <td><b>{p.display_name ?? p.username}</b><small>{p.username}</small></td>
                  <td>{#if STATE[p.state]}<StatusBadge variant={STATE[p.state].variant} label={STATE[p.state].label} compact />{/if}</td>
                  <td><span class={`v2-tag is-${rightTone(p.ntfs_rights)}`}>{rightLabel(p.ntfs_rights)}</span>{#if p.denied} <span class="v2-tag is-bad">{t('Deny entry')}</span>{/if}</td>
                  <td>{#each kinds(p.grants) as k (k)}<span class="v2-tag is-mut">{KIND_LABEL[k]}</span> {/each}{#if p.multiple_paths}<span class="v2-tag is-info">{t('several')}</span>{/if}</td>
                  <td><button type="button" class="b2s-link-btn" onclick={(event) => { event.stopPropagation(); open('user', p.user_id); }}>{t('Explore')}</button></td>
                </tr>
              {/each}
            </tbody>
          </table>
        {:else}
          <EmptyStateInline message={t('Nobody known reaches this folder through its groups or an account of their own.')} />
        {/if}
      {/if}
      {#if pager && pager.total > pager.limit}
        <div class="v2-pager">
          <span>{t('{from}–{to} of {total}', { from: pager.offset + 1, to: Math.min(pager.offset + pager.limit, pager.total), total: pager.total })}</span>
          <div class="v2-pager__r">
            <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" disabled={pager.offset === 0} onclick={() => (offset = Math.max(0, pager.offset - PAGE))}>{t('Previous')}</button>
            <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" disabled={pager.offset + pager.limit >= pager.total} onclick={() => (offset = pager.offset + PAGE)}>{t('Next')}</button>
          </div>
        </div>
      {/if}
    </div>

    <InlineAlert tone="info" title={t('Limits of this computation')}>
      <ul class="ax__limits">{#each detail.limits as code (code)}<li>{t(LIMITS[code] ?? code)}</li>{/each}</ul>
    </InlineAlert>
  {:else if !error}
    <div class="v2-sec"><p class="v2-empty">{t('Search a user, a group or a folder to see who reaches what, and why.')}</p></div>
  {/if}
</section>

<Drawer open={Boolean(selected)} title={t('Why this access')} subtitle={selected ? `${selected.who} · ${selected.folder}` : ''} iconClass="bi-diagram-3" onClose={() => (selected = null)}>
  {#if selected}
    {#each selected.grants as grant, i (i)}
      <div class="ax__why">
        {#each explainGrant(selected.who, grant, selected.folder) as sentence, j (j)}<p>{t(sentence.key, sentence.vars)}</p>{/each}
        <ol class="ax__chain" aria-label={t('Authorization path')}>
          {#each grantChain(selected.who, grant) as step, j (j)}<li><span class="v2-tag is-mut">{step}</span></li>{/each}
          <li><span class={`v2-tag is-${grant.deny ? 'bad' : rightTone(grant.rights)}`}>{grant.deny ? t('Denied') : t('Entry')}: {rightLabel(grant.rights)}</span></li>
          <li><span class="v2-tag is-info"><i class="bi bi-folder2" aria-hidden="true"></i> {selected.folder}</span></li>
        </ol>
      </div>
    {/each}
    {#if selected.grants.length > 1}<p class="v2-hint">{t('Several paths: removing one of them does not remove the access.')}</p>{/if}
    <p class="v2-hint">{t(LIMITS.ntfs_only)}</p>
  {/if}
</Drawer>

<style>
  .ax__search { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
  .ax__field { position: relative; flex: 1 1 420px; }
  .ax__suggest { position: absolute; z-index: 20; left: 0; right: 0; top: calc(100% + 4px); margin: 0; padding: 4px; list-style: none;
    background: var(--b2s-color-surface); border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-md, 8px); box-shadow: var(--b2s-shadow-md); }
  .ax__suggest button { display: flex; width: 100%; align-items: baseline; gap: 8px; padding: 6px 8px; border: 0; background: none; text-align: left; border-radius: 6px; }
  .ax__suggest button:hover, .ax__suggest button:focus-visible { background: var(--b2s-color-surface-muted); }
  .ax__suggest small { color: var(--b2s-color-text-muted); }
  .ax__suggest .v2-tag { margin-left: auto; }
  .ax__hint { padding: 6px 8px; color: var(--b2s-color-text-muted); font-size: 13px; }
  .ax__facts { display: grid; grid-template-columns: max-content 1fr; gap: 4px 16px; margin: 8px 0; font-size: 13px; }
  .ax__facts dt { color: var(--b2s-color-text-muted); }
  .ax__facts dd { margin: 0; }
  .ax__mono { font-family: var(--b2s-font-mono, monospace); font-size: 12px; overflow-wrap: anywhere; }
  .ax__groups { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; margin-top: 8px; }
  .ax__groups h3 { font-size: 13px; margin: 0 0 6px; }
  .ax__chip { display: inline-flex; gap: 4px; align-items: baseline; margin: 0 6px 6px 0; padding: 2px 8px; font-size: 12px;
    border: 1px solid var(--b2s-color-border); border-radius: 999px; background: var(--b2s-color-surface); }
  .ax__chip:disabled { cursor: default; }
  .ax__chip small, .ax__off { color: var(--b2s-color-text-muted); }
  .ax__table td small { display: block; color: var(--b2s-color-text-muted); }
  .ax__row { cursor: pointer; }
  .ax__filters { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
  .ax__check { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; }
  .ax__limits { margin: 0; padding-left: 18px; }
  .ax__why { padding: 10px 0; border-bottom: 1px solid var(--b2s-color-border); }
  .ax__why p { margin: 0 0 6px; }
  .ax__chain { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; margin: 6px 0 0; padding: 0; list-style: none; }
  .ax__chain li + li::before { content: '→'; margin-right: 4px; color: var(--b2s-color-text-muted); }
</style>
