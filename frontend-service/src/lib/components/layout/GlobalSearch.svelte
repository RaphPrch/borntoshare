<script lang="ts">
  import { goto } from '$app/navigation';
  import { tick } from 'svelte';
  import { t } from '$lib/i18n';
  import AppModal from '$lib/components/ui/AppModal.svelte';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import searchPages from './search-pages';
  import { listStorageRootsContext } from '$lib/api/storage-roots';
  import { listZones } from '$lib/api/zones';
  import { listStorageEndpoints } from '$lib/api/storage-endpoints';
  import { normalizeText } from '$lib/utils/values';
  import { searchPeople, type PersonSearchResult } from '$lib/api/storage-root-permissions';

  /** Ctrl+K / ⌘K palette: jump to a page, storage root, zone or storage endpoint, or to a person and the folders they reach. */
  export let canSeeAdmin = false;
  export let canSeeStorageRoots = false;
  export let canSeeObservability = false;

  type Result = { group: string; label: string; detail: string; href: string; icon: string };

  let open = false;
  let query = '';
  let loading = false;
  let loaded = false;
  let entities: Result[] = [];
  let activeIndex = 0;
  let inputEl: HTMLInputElement | null = null;

  // Pages are translated when read
  $: pages = [
    { title: 'Dashboard', href: '/dashboard', icon: 'bi-speedometer2', show: true },
    { title: 'Access requests', href: '/access-requests', icon: 'bi-clipboard-check', show: true },
    ...searchPages.storageRoots.map((item) => ({ ...item, show: canSeeStorageRoots })),
    { title: 'Observability', href: '/observability', icon: 'bi-activity', show: canSeeObservability },
    { title: 'Alerts', href: '/observability?tab=alerts', icon: 'bi-exclamation-triangle', show: canSeeObservability },
    { title: 'Events', href: '/observability?tab=events', icon: 'bi-list-ul', show: canSeeObservability },
    { title: 'Jobs', href: '/observability?tab=jobs', icon: 'bi-gear-wide-connected', show: canSeeObservability },
    ...searchPages.admin.map((item) => ({ ...item, show: canSeeAdmin }))
  ]
    .filter((page) => page.show)
    .map((page): Result => ({ group: t('Pages'), label: t(page.title), detail: '', href: page.href, icon: page.icon ?? 'bi-file-earmark' }));

  async function loadEntities() {
    if (loaded || loading) return;
    loading = true;
    const results: Result[] = [];
    const [roots, zones, endpoints] = await Promise.all([
      canSeeStorageRoots ? listStorageRootsContext(fetch).catch(() => []) : Promise.resolve([]),
      canSeeAdmin ? listZones(fetch).catch(() => []) : Promise.resolve([]),
      canSeeAdmin ? listStorageEndpoints(fetch).catch(() => []) : Promise.resolve([])
    ]);
    for (const root of roots) {
      results.push({
        group: t('Storage roots'),
        label: String(root.storage_root_name ?? root.name ?? root.storage_root_id),
        detail: String(root.normalized_root_path ?? root.root_path ?? root.path ?? ''),
        href: `/storage-roots?selected=${root.storage_root_id}`,
        icon: 'bi-folder2-open'
      });
    }
    for (const zone of zones) {
      results.push({ group: t('Zones'), label: zone.name, detail: zone.code ?? '', href: `/admin/zones/${zone.id}`, icon: 'bi-diagram-2' });
    }
    for (const endpoint of endpoints as any[]) {
      results.push({
        group: t('Storage endpoints'),
        label: String(endpoint.name ?? endpoint.id),
        detail: String(endpoint.host ?? endpoint.hostname ?? ''),
        href: `/admin/storage-endpoints/${endpoint.id}`,
        icon: 'bi-hdd-network'
      });
    }
    entities = results;
    loaded = true;
    loading = false;
  }

  async function show() {
    open = true;
    query = '';
    activeIndex = 0;
    void loadEntities();
    await tick();
    inputEl?.focus();
  }

  function close() {
    open = false;
  }

  function select(result: Result | undefined) {
    if (!result) return;
    close();
    void goto(result.href);
  }

  // People of the directory, searched on the server (2 characters or more)
  let people: PersonSearchResult[] = [];
  let peopleTimer: ReturnType<typeof setTimeout> | null = null;
  let peopleSeq = 0;
  $: schedulePeople(query);
  function schedulePeople(value: string) {
    if (peopleTimer) clearTimeout(peopleTimer);
    const text = value.trim();
    if (!canSeeStorageRoots || text.length < 2) {
      people = [];
      return;
    }
    peopleTimer = setTimeout(async () => {
      const seq = ++peopleSeq;
      const found = await searchPeople(fetch, text).catch(() => [] as PersonSearchResult[]);
      if (seq === peopleSeq) people = found;
    }, 250);
  }

  const levelWord = (level: string) => (level === 'write' ? t('modify') : t('read'));
  const explainHref = (rootId: number, username: string) =>
    `/storage-roots?selected=${rootId}&explain=${encodeURIComponent(username)}`;
  function requestHref(person: PersonSearchResult): string {
    const params = new URLSearchParams({ create: '1' });
    if (person.dn) {
      params.set('principal_dn', person.dn);
      params.set('principal_username', person.username);
      params.set('principal_name', person.name);
      if (person.identity_source_id) params.set('principal_source', String(person.identity_source_id));
    }
    return `/access-requests?${params}`;
  }

  $: personResults = people.flatMap((person): Result[] => [
    {
      group: t('People'),
      label: person.name,
      detail: person.roots.length
        ? t('reaches {count} folder(s): {list}', {
            count: person.roots.length,
            list: person.roots.slice(0, 3).map((r) => `${r.name} (${levelWord(r.level)})`).join(', ')
          })
        : t('{login} · no folder', { login: person.username }),
      href: person.roots.length ? explainHref(person.roots[0].storage_root_id, person.username) : requestHref(person),
      icon: 'bi-person'
    }
  ]);
  // Actions on the first person found: the palette acts, not only navigates
  $: actionResults = people.length
    ? [
        { group: t('Actions'), label: t('Request access for {name}…', { name: people[0].name }), detail: '', href: requestHref(people[0]), icon: 'bi-plus-lg' },
        ...people[0].roots.slice(0, 4).map((root) => ({
          group: t('Actions'),
          label: t('Why {name} reaches {folder}', { name: people[0].name, folder: root.name }),
          detail: levelWord(root.level),
          href: explainHref(root.storage_root_id, people[0].username),
          icon: 'bi-diagram-3'
        }))
      ]
    : [];

  $: q = normalizeText(query);
  $: results = (q
    ? [...personResults, ...actionResults, ...[...pages, ...entities].filter((r) => normalizeText(`${r.label} ${r.detail}`).includes(q))]
    : pages
  ).slice(0, 30);
  $: if (activeIndex >= results.length) activeIndex = Math.max(0, results.length - 1);

  function onWindowKeydown(event: KeyboardEvent) {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      open ? close() : void show();
    }
  }

  function onInputKeydown(event: KeyboardEvent) {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      activeIndex = Math.min(results.length - 1, activeIndex + 1);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      activeIndex = Math.max(0, activeIndex - 1);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      select(results[activeIndex]);
    }
  }
</script>

<svelte:window on:keydown={onWindowKeydown} />

<button type="button" class="global-search-trigger" on:click={show} aria-label={t('Search (Ctrl+K)')}>
  <i class="bi bi-search" aria-hidden="true"></i>
  <span>{t('Search')}</span>
</button>

<AppModal {open} onClose={close} size="lg" showClose={false} ariaLabelledby="global-search-label" contentClass="global-search">
  <label class="global-search__field">
    <span id="global-search-label" class="visually-hidden">{t('Search people, pages, storage roots, zones and endpoints')}</span>
    <i class="bi bi-search" aria-hidden="true"></i>
    <input
      bind:this={inputEl}
      bind:value={query}
      on:keydown={onInputKeydown}
      type="text"
      placeholder={t('Search a person, a storage root, a page…')}
      role="combobox"
      aria-expanded="true"
      aria-controls="global-search-results"
      aria-activedescendant={results.length ? `global-search-item-${activeIndex}` : undefined}
      autocomplete="off"
    />
    <kbd>Esc</kbd>
  </label>

  <ul id="global-search-results" class="global-search__results" role="listbox">
    {#each results as result, index}
      {#if index === 0 || results[index - 1].group !== result.group}
        <li class="global-search__group" role="presentation">{result.group}</li>
      {/if}
      <li
        id={`global-search-item-${index}`}
        role="option"
        aria-selected={index === activeIndex}
        class:is-active={index === activeIndex}
        on:mousemove={() => (activeIndex = index)}
        on:click={() => select(result)}
        on:keydown={() => {}}
      >
        <i class={`bi ${result.icon}`} aria-hidden="true"></i>
        <span class="global-search__label">{result.label}</span>
        {#if result.detail}<span class="global-search__detail">{result.detail}</span>{/if}
      </li>
    {:else}
      <li class="global-search__empty" role="presentation">{t('No result for “{query}”.', { query })}</li>
    {/each}
    {#if loading && q}
      <li class="global-search__empty" role="presentation"><LoadingState>{t('Loading…')}</LoadingState></li>
    {/if}
  </ul>
</AppModal>

<style>
  /* Item of the navigation rail */
  .global-search-trigger {
    width: 74px;
    min-height: 50px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 2px;
    border: 0;
    border-radius: 12px;
    background: transparent;
    color: var(--b2s-color-text-muted);
    font: inherit;
    font-size: 11px;
    cursor: pointer;
  }

  .global-search-trigger i {
    font-size: 18px;
    line-height: 1;
  }

  .global-search-trigger:hover {
    background: var(--b2s-color-neutral-soft);
    color: var(--b2s-color-text);
  }

  kbd {
    padding: 1px 6px;
    border: 1px solid currentColor;
    border-radius: 6px;
    background: transparent;
    color: inherit;
    font-family: var(--b2s-font-sans);
    font-size: var(--b2s-fs-xs);
    opacity: 0.7;
  }

  :global(.global-search) {
    padding: 0;
  }

  .global-search__field {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 14px 18px;
    border-bottom: 1px solid #e8edf6;
    color: var(--b2s-color-text-muted);
  }

  .global-search__field input {
    flex: 1;
    border: none;
    outline: none;
    background: transparent;
    color: var(--b2s-color-text);
    font-size: var(--b2s-fs-lg);
  }

  .global-search__results {
    max-height: min(60vh, 460px);
    overflow: auto;
    margin: 0;
    padding: 8px;
    list-style: none;
  }

  .global-search__group {
    padding: 10px 10px 4px;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  [role='option'] {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 9px 10px;
    border-radius: var(--b2s-radius-sm);
    color: var(--b2s-color-text);
    font-size: var(--b2s-fs-md);
    cursor: pointer;
  }

  [role='option'].is-active {
    background: #eef4ff;
  }

  [role='option'] i {
    color: var(--b2s-color-text-muted);
  }

  .global-search__label {
    flex: 0 1 auto;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .global-search__detail {
    margin-left: auto;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 50%;
  }

  .global-search__empty {
    padding: 16px 10px;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-sm);
  }

</style>
