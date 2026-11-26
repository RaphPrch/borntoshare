<script lang="ts">
  /**
   * Access Management › Explorer: what a person or a group reaches, and why. Two ways in (a user, a group); a folder
   * has its own Permissions tab (its sheet in Storage Roots), the Explorer does not repeat it. The
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

  type Mode = 'user' | 'group';
  type Suggestion = { id: number; label: string; detail: string | null; source: string | null };
  type Paged<T> = { items: T[]; total: number; offset: number; limit: number; broad_total?: number };
  type Reached = { storage_root_id: number; name: string; root_path: string; endpoint_name: string; grants: Grant[]; ntfs_rights: string | null;
    denied: boolean; paths: number; multiple_paths: boolean; inherited_only: boolean; inheritance_broken: boolean };

  const PAGE = 50;
  const MODES: Array<{ key: Mode; label: string }> = [
    { key: 'user', label: t('access_explorer.mode_user') },
    { key: 'group', label: t('access_explorer.mode_group') }
  ];
  const PLACEHOLDER: Record<Mode, string> = {
    user: t('Name, login or e-mail of a user'),
    group: t('Name of an AD group')
  };
  const KIND_LABEL: Record<string, string> = {
    direct: t('Own account'), group: t('Group'), nested: t('Nested group'), parent: t('Through a parent group'), broad: t('Whole company')
  };
  const STATE: Record<string, { label: string; variant: 'success' | 'error' | 'muted' | 'warning' }> = {
    enabled: { label: t('Enabled'), variant: 'success' }, disabled: { label: t('Disabled'), variant: 'error' },
    unknown: { label: t('State unknown'), variant: 'muted' }, not_in_directory: { label: t('Not in the directory'), variant: 'warning' }
  };
  const rightLabel = (rights: string | null | undefined) => (rights ? t(RIGHTS_LABEL[rights] ?? rights) : '—');
  const rightTone = (rights: string | null | undefined) => (rights === 'full' || rights === 'modify' ? 'warn' : rights ? 'ok' : 'mut');
  const kinds = (grants: Grant[]) => [...new Set(grants.map((g) => g.kind))];
  // The right in the sentence in the reader's language (« Modify » → « Modification »)
  const localized = (vars: Record<string, string>) => (vars.right ? { ...vars, right: t(vars.right) } : vars);

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
  let filter = $state('');
  let selected = $state<{ who: string; folder: string; folderId: number; grants: Grant[] } | null>(null);
  let timer: ReturnType<typeof setTimeout> | undefined;

  // The selection lives in the address: a link to an explanation can be shared
  let target = $derived({ mode: ($page.url.searchParams.get('mode') === 'group' ? 'group' : 'user') as Mode,
    id: Number($page.url.searchParams.get('id') || 0) });

  onMount(() => {
    mode = target.mode;
  });

  $effect(() => {
    const { mode: m, id } = target;
    void offset; void includeBroad;
    if (id) load(m, id);
    else detail = null;
  });

  async function load(m: Mode, id: number) {
    loading = true;
    error = '';
    try {
      const common = { offset, limit: PAGE, ...(filter.trim() ? { q: filter.trim() } : {}) };
      if (m === 'user') detail = await apiGetData(fetch, `/access-explorer/users/${id}`, { ...common, include_broad: includeBroad });
      else detail = await apiGetData(fetch, `/access-explorer/groups/${id}`, common);
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
    mode = m;
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

  function onEnter() {
    if (suggestions[0]) open(mode, suggestions[0].id);
  }

  let folders = $derived<Paged<Reached> | null>(detail?.folders ?? null);
  let pager = $derived(folders);
  let subject = $derived(detail?.user?.display_name ?? detail?.group?.name ?? '');
</script>

<svelte:head><title>Access Explorer · BornToShare</title></svelte:head>

<section class="v2 ax">
  <div class="v2-head">
    <div>
      <h1>Access Explorer</h1>
      <p>{t('Who reaches what, and why: from the last ACL read of the folders and the last reading of the directory.')}</p>
    </div>
  </div>

  <div class="v2-sec">
   <div class="ax__bar">
    <SegmentedFilter options={MODES} bind:value={mode} ariaLabel={t('Search by')} onChange={() => { suggestions = []; query = ''; }} />
    <div class="ax__field">
      <SearchField value={query} placeholder={PLACEHOLDER[mode]} ariaLabel={PLACEHOLDER[mode]} onChange={onType} onEnter={onEnter} />
      {#if suggestions.length || suggesting}
        <ul class="ax__suggest" role="listbox" aria-label={t('Suggestions')}>
          {#if suggesting && !suggestions.length}<li class="ax__hint"><LoadingState>{t('Searching…')}</LoadingState></li>{/if}
          {#each suggestions as item (item.id)}
            <li role="option" aria-selected="false">
              <button type="button" onclick={() => open(mode, item.id)} title={[item.label, item.detail, item.source].filter(Boolean).join(' · ')}>
                <b>{item.label}</b><small>{item.detail ?? ''}</small>{#if item.source}<span class="v2-tag is-mut">{item.source}</span>{/if}
              </button>
            </li>
          {/each}
          {#if suggestTotal > suggestions.length}<li class="ax__hint">{t('{n} more: refine the search', { n: suggestTotal - suggestions.length })}</li>{/if}
        </ul>
      {/if}
    </div>
   </div>
    {#if !detail && !loading && !error}
      <p class="v2-hint">{t('Search a user or a group to see what they reach, and why. For a folder: its Permissions tab in Storage Roots.')}</p>
    {/if}
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
            {#each detail.groups.direct as g (g.name)}<button type="button" class="ax__chip" onclick={() => open('group', g.group_id)} disabled={!g.group_id}>{g.name}</button>{:else}<p class="ax__none">{t('None')}</p>{/each}</div>
          <div><h3>{t('Nested groups')} <span class="v2-tag is-mut">{detail.groups.nested.length}</span></h3>
            {#each detail.groups.nested as g (g.name)}<button type="button" class="ax__chip" title={g.via.join(' › ')} onclick={() => open('group', g.group_id)} disabled={!g.group_id}>{g.name} <small>{t('via {group}', { group: g.via[0] })}</small></button>{:else}<p class="ax__none">{t('None')}</p>{/each}</div>
        </div>
      {:else if detail.group}
        <div class="v2-sh"><h2><i class="bi bi-people" aria-hidden="true"></i> {detail.group.name}</h2>{#if detail.group.broad}<span class="v2-tag is-bad">{t('Whole company')}</span>{/if}</div>
        {#if detail.group.description}<p class="v2-hint">{detail.group.description}</p>{/if}
        <!-- Its exposure in one line: a few figures do not need a card each -->
        <ul class="ax__figs">
          <li><b>{detail.exposure.effective_users ?? '—'}</b> {t('People (nested included)')}</li>
          {#if detail.exposure.disabled_users != null}<li class:is-bad={detail.exposure.disabled_users > 0}><b>{detail.exposure.disabled_users}</b> {t('Disabled accounts')}</li>{/if}
          <li><b>{detail.exposure.folders}</b> {t('Folders reached')}</li>
          <li><b>{detail.nested_total}</b> {t('Nested groups')}</li>
        </ul>
        <div class="ax__groups">
          <div><h3>{t('Direct members')} <span class="v2-tag is-mut">{detail.members.users_total}</span></h3>
            {#each detail.members.users as u (u.username)}<button type="button" class="ax__chip" onclick={() => open('user', u.user_id)} disabled={!u.user_id}>{u.display_name ?? u.username}{#if u.state === 'disabled'} <small class="ax__off">{t('disabled')}</small>{/if}</button>{:else}<p class="ax__none">{t('None')}</p>{/each}
            {#if detail.members.users_total > detail.members.users.length}<p class="v2-hint">{t('{n} more', { n: detail.members.users_total - detail.members.users.length })}</p>{/if}</div>
          <div><h3>{t('Nested groups')}</h3>
            {#each detail.nested_groups as g (g.name)}<button type="button" class="ax__chip" title={g.via.join(' › ')} onclick={() => open('group', g.group_id)} disabled={!g.group_id}>{g.name}{#if g.depth > 0} <small>{t('level {n}', { n: g.depth + 1 })}</small>{/if}</button>{:else}<p class="ax__none">{t('None')}</p>{/each}</div>
          <div><h3>{t('Member of')}</h3>
            {#each detail.parent_groups as g (g.name)}<button type="button" class="ax__chip" title={g.via.join(' › ')} onclick={() => open('group', g.group_id)} disabled={!g.group_id}>{g.name}</button>{:else}<p class="ax__none">{t('None')}</p>{/each}</div>
        </div>
      {/if}
      {#if detail.snapshot_at}
        <p class="v2-hint">{t('Directory read')} <RelativeTime value={detail.snapshot_at} /></p>
      {/if}
    </div>

    <!-- Folders reached -->
    <div class="v2-sec">
      <div class="v2-sh">
        <h2>{t('Folders reached')}</h2>{#if pager}<span class="v2-tag is-mut">{pager.total}</span>{/if}
        <div class="v2-sh__r ax__filters">
          {#if detail.user}
            <label class="ax__check"><input type="checkbox" bind:checked={includeBroad} onchange={() => (offset = 0)} /> {t('Include the entries open to everyone')}{folders?.broad_total ? ` (${folders.broad_total})` : ''}</label>
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
                <tr class="ax__row" onclick={() => (selected = { who: subject, folder: f.name, folderId: f.storage_root_id, grants: f.grants })}>
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
  {/if}
</section>

<Drawer open={Boolean(selected)} title={t('Why this access')} subtitle={selected ? `${selected.who} · ${selected.folder}` : ''} iconClass="bi-diagram-3" onClose={() => (selected = null)}>
  {#if selected}
    {#each selected.grants as grant, i (i)}
      <div class="ax__why">
        {#each explainGrant(selected.who, grant, selected.folder) as sentence, j (j)}<p>{t(sentence.key, localized(sentence.vars))}</p>{/each}
        <ol class="ax__chain" aria-label={t('Authorization path')}>
          {#each grantChain(selected.who, grant) as step, j (j)}<li><span class="v2-tag is-mut">{step}</span></li>{/each}
          <li><span class={`v2-tag is-${grant.deny ? 'bad' : rightTone(grant.rights)}`}>{grant.deny ? t('Denied') : t('Entry')}: {rightLabel(grant.rights)}</span></li>
          <li><span class="v2-tag is-info"><i class="bi bi-folder2" aria-hidden="true"></i> {selected.folder}</span></li>
        </ol>
      </div>
    {/each}
    {#if selected.grants.length > 1}<p class="v2-hint">{t('Several paths: removing one of them does not remove the access.')}</p>{/if}
    <p class="v2-hint">{t(LIMITS.ntfs_only)}</p>
    <a class="b2s-btn b2s-btn-secondary" href={`/storage-roots?selected=${selected.folderId}&tab=permissions`}><i class="bi bi-shield-lock" aria-hidden="true"></i>{t('Everyone who reaches this folder')}</a>
  {/if}
</Drawer>

<style>
  /* Mode then field on one line, left-aligned (the card is a column: the basis of the field is a width here) */
  .ax__bar { display: flex; flex-direction: row; flex-wrap: wrap; align-items: center; gap: 12px; }
  .ax__field { position: relative; flex: 0 1 560px; min-width: 320px; }
  .ax__suggest { position: absolute; z-index: 20; left: 0; right: 0; top: calc(100% + 4px); max-height: 360px; overflow-y: auto; margin: 0; padding: 4px; list-style: none;
    background: var(--b2s-color-surface); border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-md, 8px); box-shadow: var(--b2s-shadow-md); }
  .ax__suggest button { display: flex; width: 100%; align-items: center; gap: 8px; padding: 6px 8px; border: 0; background: none; text-align: left; border-radius: 6px; }
  .ax__suggest b, .ax__suggest small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ax__suggest b { flex: 0 1 auto; }
  .ax__suggest small { flex: 1 1 0; min-width: 0; }
  .ax__suggest .v2-tag { flex: none; }
  .ax__suggest button:hover, .ax__suggest button:focus-visible { background: var(--b2s-color-surface-muted); }
  .ax__suggest small { color: var(--b2s-color-text-muted); }
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
  .ax__none { margin: 0; color: var(--b2s-color-text-muted); font-size: 12px; }
  .ax__chip small, .ax__off { color: var(--b2s-color-text-muted); }
  .ax__table td small { display: block; color: var(--b2s-color-text-muted); }
  .ax__row { cursor: pointer; }
  .ax__filters { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
  .ax__check { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; }
  .ax__limits { margin: 0; padding-left: 18px; }
  .ax__why { padding: 10px 0; border-bottom: 1px solid var(--b2s-color-border); }
  .ax__why p { margin: 0 0 6px; }
  /* The authorization path as steps, top to bottom: the account, its groups, the entry, the folder */
  .ax__chain { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; margin: 8px 0 0; padding: 0; list-style: none; }
  .ax__chain li + li::before { content: '↓'; display: block; margin: 0 0 2px 12px; color: var(--b2s-color-text-muted); font-size: 12px; line-height: 1; }
  .ax__figs { display: flex; flex-wrap: wrap; gap: 6px 22px; margin: 0; padding: 0; list-style: none; color: var(--b2s-color-text-muted); font-size: 13px; }
  .ax__figs b { color: var(--b2s-color-heading); font-size: 18px; font-variant-numeric: tabular-nums; margin-right: 2px; }
  .ax__figs .is-bad b { color: var(--b2s-color-danger); }
</style>
