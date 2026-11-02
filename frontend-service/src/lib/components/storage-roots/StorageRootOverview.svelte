<script lang="ts">
  import TagPill from '$lib/components/tags/TagPill.svelte';
  import { t } from '$lib/i18n';
  import { formatDate, initials, timeAgo } from '$lib/utils/format';
  import { formatActivityItem } from '$lib/activity/format';
  import { reportUiError } from '$lib/errors';
  import { toast } from '$lib/stores/toast';
  import { extendAccess, type PermissionPerson, type StorageRootPermissionsData } from '$lib/api/storage-root-permissions';
  import { expiryProgress } from './permissions/permissions-format';

  /**
   * Overview of a storage root in cards: who reaches it (one card per level, with « who reaches it? »),
   * the next end dates, its governance (guardians, tags, server, inheritance) and its recent activity.
   */
  type Tag = Record<string, unknown>;

  export let permissions: StorageRootPermissionsData | null = null;
  export let guardianNames: string[] = [];
  export let guardiansMissing = false;
  export let tags: Tag[] = [];
  export let tagId: (tag: Tag) => number = () => 0;
  export let tagLabel: (tag: Tag) => string = () => '';
  export let tagColor: (tag: Tag) => string | null = () => null;
  export let zoneLabel = '';
  export let endpointDisplay = '';
  export let endpointHref: string | null = null;
  export let contentSizeLabel = '—';
  export let isAdmin = false;
  export let activity: Array<Record<string, unknown>> = [];
  export let onOpenPermissions: () => void = () => {};
  export let onExplain: (login: string) => void = () => {};
  export let onOpenGuardians: () => void = () => {};
  export let onOpenTags: () => void = () => {};
  export let onOpenActivity: () => void = () => {};
  export let onToggleInheritance: () => void = () => {};
  export let onChanged: () => void = () => {};

  const requestOf = (p: PermissionPerson) =>
    p.via.find((v) => v.kind === 'request' && v.expires_at) as Extract<PermissionPerson['via'][number], { kind: 'request' }> | undefined;

  $: people = permissions?.people ?? [];
  $: levels = (['read', 'write'] as const).map((level) => ({
    level,
    groups: (permissions?.groups ?? []).filter((group) => group.level === level),
    people: people.filter((person) => person.level === level)
  }));
  $: ends = people
    .filter((p) => p.expires_at)
    .sort((a, b) => String(a.expires_at).localeCompare(String(b.expires_at)))
    .slice(0, 4);
  $: inheritance = permissions?.inheritance;
  $: recent = activity.slice(0, 5).map((entry) => ({ entry, item: formatActivityItem(entry as any) }));

  let login = '';
  function explain() {
    if (login.trim()) onExplain(login.trim());
  }

  let extending: string | null = null;
  async function extend(person: PermissionPerson) {
    const request = requestOf(person);
    if (!request) return;
    extending = person.key;
    try {
      const result = await extendAccess(fetch, request.request_id, 30);
      toast.success(t('Access extended until {date}.', { date: formatDate(result.expires_at ?? '') }));
      onChanged();
    } catch (error: unknown) {
      reportUiError(error, t('Unable to extend this access.'), 'storage-root.extend');
    } finally {
      extending = null;
    }
  }

  const ACE_LABEL: Record<string, () => string> = {
    ok: () => t('ACE in place'),
    missing: () => t('ACE missing'),
    mismatch: () => t('Unexpected rights')
  };
</script>

<div class="ov">
  <div class="ov__col">
    <section class="ov__card" aria-label={t('Who reaches it')}>
      <header><h2>{t('Who reaches it')}</h2><button type="button" class="ov__link" on:click={onOpenPermissions}>{t('All the permissions')} ›</button></header>
      <form class="ov__who" on:submit|preventDefault={explain}>
        <input class="b2s-input" bind:value={login} placeholder={t('Who reaches it? Type a login, e.g. paul.martin')} aria-label={t('Who reaches it?')} />
        <button type="submit" class="b2s-btn b2s-btn-secondary" disabled={!login.trim()}>{t('Check')}</button>
      </form>
      {#if permissions?.groups.length}
        {#each levels as entry (entry.level)}
          {#each entry.groups as group (group.name)}
            <div class="ov__level">
              <span class={`ov__badge is-${entry.level}`}>{entry.level === 'write' ? t('Modify') : t('Read')}</span>
              <span class="ov__group">
                <strong>{t('{count} person(s)', { count: entry.people.length })}</strong>
                <small><code>{group.name}</code> · {t('{count} member(s)', { count: group.members_count })} · {ACE_LABEL[group.ace]?.() ?? t('ACL not read')}</small>
              </span>
              <span class="ov__stack">
                {#each entry.people.slice(0, 5) as person (person.key)}
                  <span class={`ov__face is-${entry.level}`} title={person.name}>{initials(person.name)}</span>
                {/each}
                {#if entry.people.length > 5}<span class="ov__face is-more">+{entry.people.length - 5}</span>{/if}
              </span>
            </div>
          {/each}
        {/each}
      {:else}
        <p class="ov__muted">{permissions?.acl_scanned_at ? t('Nobody reaches this folder through BornToShare yet.') : t('Read the ACL to see who reaches this folder.')}</p>
      {/if}
    </section>

    {#if ends.length}
      <section class="ov__card" aria-label={t('Next end dates')}>
        <header><h2>{t('Next end dates')}</h2></header>
        <ul class="ov__ends">
          {#each ends as person (person.key)}
            {@const request = requestOf(person)}
            {@const progress = expiryProgress(request?.decided_at ?? null, person.expires_at)}
            <li>
              <span class="ov__face is-small">{initials(person.name)}</span>
              <span class="ov__name">{person.name}</span>
              <span class="ov__bar" class:is-soon={progress.soon} aria-hidden="true"><span style={`width: ${progress.percentLeft}%`}></span></span>
              <span class="ov__when" title={formatDate(person.expires_at)}>{t('in {days} d', { days: progress.daysLeft })}</span>
              {#if request}
                <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" disabled={extending === person.key} on:click={() => extend(person)}>+30 j</button>
              {/if}
            </li>
          {/each}
        </ul>
      </section>
    {/if}

    <section class="ov__card" aria-label={t('Recent activity')}>
      <header><h2>{t('Recent activity')}</h2><button type="button" class="ov__link" on:click={onOpenActivity}>{t('All the history')} ›</button></header>
      {#if recent.length}
        <ul class="ov__activity">
          {#each recent as { entry, item }, index (index)}
            <li>
              <span class={`ov__dot is-${item.variant}`} aria-hidden="true"></span>
              <span class="ov__act"><strong>{item.title}</strong>{#if item.subtitle1}<small>{item.subtitle1}</small>{/if}</span>
              <small class="ov__when">{timeAgo(String(entry?.created_at ?? entry?.occurred_at ?? ''))}</small>
            </li>
          {/each}
        </ul>
      {:else}
        <p class="ov__muted">{t('No activity found for this storage root.')}</p>
      {/if}
    </section>
  </div>

  <section class="ov__card ov__side" aria-label={t('Governance')}>
    <header><h2>{t('Governance')}</h2></header>
    <dl>
      <div>
        <dt>{t('Guardians')}</dt>
        <dd>
          {#each guardianNames as name}
            <span class="ov__chip"><span class="ov__face is-tiny">{initials(name)}</span>{name}</span>
          {:else}
            <span class="ov__warn">{t('None: only the administrators can approve the requests.')}</span>
          {/each}
          {#if guardiansMissing && guardianNames.length}<span class="ov__warn">{t('Too few')}</span>{/if}
          <button type="button" class="ov__add" on:click={onOpenGuardians}>{guardianNames.length ? t('Manage') : t('+ Add')}</button>
        </dd>
      </div>
      <div>
        <dt>{t('Tags')}</dt>
        <dd>
          {#each tags as tag (tagId(tag))}<TagPill label={tagLabel(tag)} color={tagColor(tag)} small={true} />{/each}
          <button type="button" class="ov__add" on:click={onOpenTags}>{tags.length ? t('Manage') : t('+ Tag')}</button>
        </dd>
      </div>
      {#if zoneLabel}<div><dt>{t('Zone')}</dt><dd>{zoneLabel}</dd></div>{/if}
      <div><dt>{t('File server')}</dt><dd>{#if endpointHref}<a href={endpointHref}>{endpointDisplay}</a>{:else}{endpointDisplay}{/if}</dd></div>
      <div><dt>{t('Content')}</dt><dd>{contentSizeLabel === '—' ? t('Not measured') : contentSizeLabel}</dd></div>
      <div>
        <dt>{t('Inheritance')}</dt>
        <dd>
          {#if !inheritance?.known}<span class="ov__muted">{t('Known at the next ACL read')}</span>
          {:else if inheritance.broken}<span>{t('Broken: the folder keeps its own entries')}</span>
          {:else}<span>{t('Inherited from the parent folder')}</span>{/if}
          {#if isAdmin && inheritance?.known}<button type="button" class="ov__link" on:click={onToggleInheritance}>{inheritance.broken ? t('Restore') : t('Break')}</button>{/if}
        </dd>
      </div>
      <div><dt>{t('Directory')}</dt><dd>{permissions?.snapshot_at ? t('Synchronised {ago}', { ago: timeAgo(permissions.snapshot_at) }) : '—'}</dd></div>
    </dl>
  </section>
</div>

<style>
  .ov { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(280px, 1fr); gap: 14px; align-items: start; }
  .ov__col { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
  .ov__card { display: flex; flex-direction: column; gap: 12px; min-width: 0; padding: 16px 18px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .ov__card header { display: flex; align-items: center; gap: 12px; }
  .ov__card h2 { margin: 0 auto 0 0; font-size: var(--b2s-fs-md); font-weight: 600; }
  .ov__link { padding: 0; border: 0; background: none; color: var(--b2s-color-info-strong); font: inherit; font-size: var(--b2s-fs-sm); cursor: pointer; }
  .ov__muted { margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .ov__who { display: flex; gap: 8px; }
  .ov__who .b2s-input { flex: 1; min-width: 0; }
  .ov__level { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 12px; align-items: center; padding: 12px 14px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-md); }
  .ov__badge { padding: 2px 9px; border-radius: var(--b2s-radius-pill); font-size: var(--b2s-fs-xs); font-weight: 600; }
  .ov__badge.is-read { background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); }
  .ov__badge.is-write { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .ov__group { display: flex; flex-direction: column; min-width: 0; }
  .ov__group strong { font-weight: 600; font-size: var(--b2s-fs-sm); }
  .ov__group small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); overflow-wrap: anywhere; }
  .ov__group code { font-family: var(--b2s-font-mono); color: inherit; background: none; padding: 0; }
  .ov__stack { display: flex; }
  .ov__face { display: inline-flex; align-items: center; justify-content: center; flex: none; width: 28px; height: 28px; margin-left: -7px; border: 2px solid var(--b2s-color-surface); border-radius: 50%; background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); font-size: 10px; font-weight: 700; }
  .ov__stack .ov__face:first-child { margin-left: 0; }
  .ov__face.is-write { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .ov__face.is-more { background: var(--b2s-color-neutral-soft); color: var(--b2s-color-text-soft); }
  .ov__face.is-small { margin: 0; border: 0; }
  .ov__face.is-tiny { width: 22px; height: 22px; margin: 0; border: 0; }
  .ov__ends, .ov__activity { display: grid; gap: 10px; margin: 0; padding: 0; list-style: none; }
  .ov__ends li { display: flex; align-items: center; gap: 12px; }
  .ov__name { flex: 0 1 180px; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ov__bar { flex: 1; height: 4px; overflow: hidden; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-border-soft); }
  .ov__bar span { display: block; height: 4px; background: var(--b2s-color-info); }
  .ov__bar.is-soon span { background: var(--b2s-color-warning); }
  .ov__when { flex: none; color: var(--b2s-color-text-soft); font-size: var(--b2s-fs-xs); white-space: nowrap; }
  .ov__activity li { display: grid; grid-template-columns: 10px minmax(0, 1fr) auto; gap: 10px; align-items: start; }
  .ov__dot { width: 9px; height: 9px; margin-top: 6px; border-radius: 50%; background: var(--b2s-color-border-mid, #cdd2db); }
  .ov__dot.is-ok { background: var(--b2s-color-success); }
  .ov__dot.is-warn { background: var(--b2s-color-warning); }
  .ov__act { display: flex; flex-direction: column; min-width: 0; }
  .ov__act strong { font-weight: 500; font-size: var(--b2s-fs-sm); }
  .ov__act small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); overflow-wrap: anywhere; }
  .ov__side { position: sticky; top: 16px; }
  .ov__side dl { margin: 0; }
  .ov__side dl div { display: grid; grid-template-columns: 96px minmax(0, 1fr); gap: 8px; padding: 9px 0; border-top: 1px solid var(--b2s-color-border); font-size: var(--b2s-fs-sm); }
  .ov__side dl div:first-child { border-top: 0; }
  .ov__side dt { color: var(--b2s-color-text-muted); }
  .ov__side dd { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 0; min-width: 0; overflow-wrap: anywhere; }
  .ov__chip { display: inline-flex; align-items: center; gap: 6px; padding: 2px 8px 2px 2px; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-neutral-soft); }
  .ov__warn { color: var(--b2s-color-warning-strong); }
  .ov__add { padding: 1px 8px; border: 1px dashed var(--b2s-color-border-mid); border-radius: 6px; background: transparent; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); cursor: pointer; }
  .ov__add:hover { border-color: var(--b2s-color-info); color: var(--b2s-color-info-strong); }
</style>
