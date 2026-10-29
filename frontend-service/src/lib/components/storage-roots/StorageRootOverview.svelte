<script lang="ts">
  import TagPill from '$lib/components/tags/TagPill.svelte';
  import EntityProperties from '$lib/components/entity/EntityProperties.svelte';
  import EntityProperty from '$lib/components/entity/EntityProperty.svelte';
  import { t } from '$lib/i18n';
  import { formatDate, initials, timeAgo } from '$lib/utils/format';
  import { reportUiError } from '$lib/errors';
  import { toast } from '$lib/stores/toast';
  import { extendAccess, type PermissionPerson, type StorageRootPermissionsData } from '$lib/api/storage-root-permissions';
  import { expiryProgress } from './permissions/permissions-format';

  /**
   * Overview of a storage root on one surface: who reaches it, the next end dates,
   * and an inspector of its properties (guardians, tags, server, inheritance) edited in place.
   */
  type Tag = Record<string, unknown>;

  export let permissions: StorageRootPermissionsData | null = null;
  export let guardianNames: string[] = [];
  export let tags: Tag[] = [];
  export let tagId: (tag: Tag) => number = () => 0;
  export let tagLabel: (tag: Tag) => string = () => '';
  export let tagColor: (tag: Tag) => string | null = () => null;
  export let zoneLabel = '';
  export let endpointDisplay = '';
  export let endpointHref: string | null = null;
  export let contentSizeLabel = '—';
  export let isAdmin = false;
  export let onOpenPermissions: () => void = () => {};
  export let onOpenGuardians: () => void = () => {};
  export let onOpenTags: () => void = () => {};
  export let onToggleInheritance: () => void = () => {};
  export let onChanged: () => void = () => {};

  const requestOf = (p: PermissionPerson) =>
    p.via.find((v) => v.kind === 'request' && v.expires_at) as Extract<PermissionPerson['via'][number], { kind: 'request' }> | undefined;

  $: people = permissions?.people ?? [];
  $: faces = people.slice(0, 7);
  $: ends = people
    .filter((p) => p.expires_at)
    .sort((a, b) => String(a.expires_at).localeCompare(String(b.expires_at)))
    .slice(0, 4);
  $: inheritance = permissions?.inheritance;

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
</script>

<div class="ov">
  <div class="ov__main">
    <section class="ov__section" aria-label={t('Who reaches it')}>
      <div class="ov__head">
        <h2>{t('Who reaches it')}</h2>
        <button type="button" class="ov__link" on:click={onOpenPermissions}>{t('See the permissions')} →</button>
      </div>
      {#if people.length}
        <div class="ov__faces">
          <span class="ov__stack">
            {#each faces as person (person.key)}
              <span class={`ov__face is-${person.level}`} title={person.name}>{initials(person.name)}</span>
            {/each}
            {#if people.length > faces.length}<span class="ov__face is-more">+{people.length - faces.length}</span>{/if}
          </span>
          <span class="ov__muted">{t('through {count} AD group(s) managed by BornToShare', { count: permissions?.summary.groups ?? 0 })}</span>
        </div>
      {:else}
        <p class="ov__muted">{permissions?.acl_scanned_at ? t('Nobody reaches this folder through BornToShare yet.') : t('Read the ACL to see who reaches this folder.')}</p>
      {/if}
      {#if permissions?.groups.length}
        <ul class="ov__rows">
          {#each permissions.groups as group (group.name)}
            <li>
              <span class={`ov__level is-${group.level}`}>{group.level === 'write' ? t('Modify') : t('Read')}</span>
              <code>{group.name}</code>
              <span class="ov__muted ov__end">
                {t('{count} member(s)', { count: group.members_count })} ·
                {group.ace === 'ok' ? t('ACE in place') : group.ace === 'missing' ? t('ACE missing') : group.ace === 'mismatch' ? t('Unexpected rights') : t('ACL not read')}
              </span>
            </li>
          {/each}
        </ul>
      {/if}
    </section>

    {#if ends.length}
      <section class="ov__section" aria-label={t('Next end dates')}>
        <h2>{t('Next end dates')}</h2>
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
  </div>

  <EntityProperties title={t('Properties')}>
      <EntityProperty label={t('Guardians')} chips>
          {#each guardianNames as name}
            <span class="ov__chip"><span class="ov__face is-tiny">{initials(name)}</span>{name}</span>
          {:else}
            <span class="ov__warn">{t('None: requests cannot be approved')}</span>
          {/each}
          <button type="button" class="ov__add" aria-label={t('Manage the guardians')} on:click={onOpenGuardians}><i class="bi bi-plus" aria-hidden="true"></i></button>
        </EntityProperty>
      <EntityProperty label={t('Tags')} chips>
          {#each tags as tag (tagId(tag))}
            <TagPill label={tagLabel(tag)} color={tagColor(tag)} small={true} />
          {/each}
          <button type="button" class="ov__add" aria-label={t('Manage the tags')} on:click={onOpenTags}><i class="bi bi-plus" aria-hidden="true"></i></button>
        </EntityProperty>
      {#if zoneLabel}<EntityProperty label={t('Zone')}>{zoneLabel}</EntityProperty>{/if}
      <EntityProperty label={t('File server')}>{#if endpointHref}<a href={endpointHref}>{endpointDisplay}</a>{:else}{endpointDisplay}{/if}</EntityProperty>
      <EntityProperty label={t('Content')}>{contentSizeLabel === '—' ? t('Not measured') : contentSizeLabel}</EntityProperty>
      <EntityProperty label={t('Inheritance')} chips>
          {#if !inheritance?.known}
            <span class="ov__muted">{t('Known at the next ACL read')}</span>
          {:else if inheritance.broken}
            <span>{t('Broken: the folder keeps its own entries')}</span>
          {:else}
            <span>{t('Inherited from the parent folder')}</span>
          {/if}
          {#if isAdmin && inheritance?.known}
            <button type="button" class="ov__link" on:click={onToggleInheritance}>{inheritance.broken ? t('Restore') : t('Break')}</button>
          {/if}
        </EntityProperty>
      <EntityProperty label={t('Directory')}>{permissions?.snapshot_at ? t('Synchronised {ago}', { ago: timeAgo(permissions.snapshot_at) }) : '—'}</EntityProperty>
  </EntityProperties>
</div>

<style>
  .ov {
    display: flex;
    flex-wrap: wrap;
    gap: 40px;
    align-items: flex-start;
  }

  .ov__main {
    flex: 999 1 420px;
    min-width: 0;
    display: grid;
    gap: 28px;
  }

  .ov__section {
    display: grid;
    gap: 12px;
  }

  .ov__head {
    display: flex;
    align-items: baseline;
    gap: 12px;
  }

  h2 {
    margin: 0;
    font-size: var(--b2s-fs-md);
    font-weight: 600;
  }

  .ov__link {
    padding: 0;
    border: 0;
    background: none;
    color: var(--b2s-color-info-strong);
    font: inherit;
    font-size: var(--b2s-fs-sm);
    cursor: pointer;
  }

  .ov__muted {
    margin: 0;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-sm);
  }

  .ov__faces {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 14px;
  }

  .ov__stack {
    display: flex;
  }

  .ov__face {
    width: 34px;
    height: 34px;
    flex: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    margin-left: -8px;
    border: 2px solid var(--b2s-color-surface);
    border-radius: 50%;
    background: var(--b2s-color-info-soft);
    color: var(--b2s-color-info-strong);
    font-size: 11px;
    font-weight: 700;
  }

  .ov__stack .ov__face:first-child { margin-left: 0; }
  .ov__face.is-write { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .ov__face.is-more { background: var(--b2s-color-neutral-soft); color: var(--b2s-color-text-soft); }
  .ov__face.is-small { width: 28px; height: 28px; margin: 0; border: 0; }
  .ov__face.is-tiny { width: 22px; height: 22px; margin: 0; border: 0; font-size: 10px; }

  .ov__rows,
  .ov__ends {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .ov__rows li {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 12px;
    padding: 11px 0;
    border-top: 1px solid var(--b2s-color-border-soft);
  }

  .ov__rows li:last-child {
    border-bottom: 1px solid var(--b2s-color-border-soft);
  }

  .ov__rows code {
    font-family: var(--b2s-font-mono);
    font-size: var(--b2s-fs-xs);
    overflow-wrap: anywhere;
  }

  .ov__end {
    margin-left: auto;
    font-size: var(--b2s-fs-xs);
  }

  .ov__level {
    padding: 2px 8px;
    border-radius: 6px;
    font-size: var(--b2s-fs-xs);
    font-weight: 600;
  }

  .ov__level.is-read { background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); }
  .ov__level.is-write { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }

  .ov__ends {
    display: grid;
    gap: 10px;
  }

  .ov__ends li {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .ov__name {
    flex: 0 1 180px;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .ov__bar {
    flex: 1;
    height: 4px;
    overflow: hidden;
    border-radius: var(--b2s-radius-pill);
    background: var(--b2s-color-border-soft);
  }

  .ov__bar span {
    display: block;
    height: 4px;
    background: var(--b2s-color-info);
  }

  .ov__bar.is-soon span {
    background: var(--b2s-color-warning);
  }

  .ov__when {
    flex: 0 0 auto;
    color: var(--b2s-color-text-soft);
    font-size: var(--b2s-fs-sm);
    white-space: nowrap;
  }

  .ov__chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 2px 8px 2px 2px;
    border-radius: var(--b2s-radius-pill);
    background: var(--b2s-color-neutral-soft);
  }

  .ov__warn {
    color: var(--b2s-color-warning-strong);
  }

  .ov__add {
    width: 24px;
    height: 24px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border: 1px dashed var(--b2s-color-border-mid);
    border-radius: 6px;
    background: transparent;
    color: var(--b2s-color-text-muted);
    cursor: pointer;
  }

  .ov__add:hover {
    border-color: var(--b2s-color-info);
    color: var(--b2s-color-info-strong);
  }
</style>
