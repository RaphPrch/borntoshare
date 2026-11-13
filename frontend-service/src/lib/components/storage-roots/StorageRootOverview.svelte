<script lang="ts">
  

  import { flip } from 'svelte/animate';
  import { apiGetList } from '$lib/api/client';
  import { dur, MOTION, pop } from '$lib/utils/motion';
  import StorageRootContentCards from '$lib/components/storage-roots/StorageRootContentCards.svelte';
  import StorageRootQuotaCard from '$lib/components/storage-roots/StorageRootQuotaCard.svelte';
  import StorageRootSensitivityCard from '$lib/components/storage-roots/StorageRootSensitivityCard.svelte';
  import TagPill from '$lib/components/tags/TagPill.svelte';
  import { t } from '$lib/i18n';
  import { formatDate, initials, timeAgo } from '$lib/utils/format';
  import RecentActivityCard from '$lib/components/activity/RecentActivityCard.svelte';
  import { reportUiError } from '$lib/errors';
  import { toast } from '$lib/stores/toast';
  import { extendAccess, type PermissionPerson, type StorageRootPermissionsData } from '$lib/api/storage-root-permissions';
  import { expiryProgress } from './permissions/permissions-format';

  /**
   * Overview of a storage root in cards: who reaches it (one card per level, with « who reaches it? »),
   * the next end dates, its governance (guardians, tags, server, inheritance) and its recent activity.
   */
  type Tag = Record<string, unknown>;

  
  // Sub-folders tagged by the policies « also on the sub-folders » (path from the share)
  let subTags: Array<{ path: string; tags: Array<{ id: number; name: string; color: string | null }> }> = $state([]);
  let subTagsAll = $state(false);
  let subTagsFor: number | null = $state(null);
  const inner = (path: string) => path;
  interface Props {
    permissions?: StorageRootPermissionsData | null;
    guardianNames?: string[];
    guardiansMissing?: boolean;
    tags?: Tag[];
    tagId?: (tag: Tag) => number;
    tagLabel?: (tag: Tag) => string;
    tagColor?: (tag: Tag) => string | null;
    zoneLabel?: string;
    endpointDisplay?: string;
    endpointHref?: string | null;
    /** Size, sub-folders, files of the folder (last check by the worker) */
    content?: any;
    sensitivity?: any;
    rootId?: number | null;
    onMeasured?: () => void;
    isAdmin?: boolean;
    isDfs?: boolean;
    activity?: Array<Record<string, unknown>>;
    onExplain?: (login: string) => void;
    onOpenGuardians?: () => void;
    onOpenTags?: () => void;
    onOpenActivity?: () => void;
    onToggleInheritance?: () => void;
    onChanged?: () => void;
  }

  let {
    permissions = null,
    guardianNames = [],
    guardiansMissing = false,
    tags = [],
    tagId = () => 0,
    tagLabel = () => '',
    tagColor = () => null,
    zoneLabel = '',
    endpointDisplay = '',
    endpointHref = null,
    content = null,
    sensitivity = null,
    rootId = null,
    onMeasured = () => {},
    isAdmin = false,
    isDfs = false,
    activity = [],
    onExplain = () => {},
    onOpenGuardians = () => {},
    onOpenTags = () => {},
    onOpenActivity = () => {},
    onToggleInheritance = () => {},
    onChanged = () => {}
  }: Props = $props();

  const requestOf = (p: PermissionPerson) =>
    p.via.find((v) => v.kind === 'request' && v.expires_at) as Extract<PermissionPerson['via'][number], { kind: 'request' }> | undefined;


  let login = '';
  function explain() {
    if (login.trim()) onExplain(login.trim());
  }

  let extending: string | null = $state(null);
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
  $effect.pre(() => {
    if (rootId && rootId !== subTagsFor) {
      subTagsFor = rootId;
      subTagsAll = false;
      void apiGetList<{ path: string; tags: Array<{ id: number; name: string; color: string | null }> }>(fetch, `/storage-roots/${rootId}/folder-tags`)
        .then((rows) => { if (subTagsFor === rootId) subTags = rows; })
        .catch(() => (subTags = []));
    }
  });
  let people = $derived(permissions?.people ?? []);
  let levels = $derived((['read', 'write'] as const).map((level) => ({
    level,
    groups: (permissions?.groups ?? []).filter((group) => group.level === level),
    people: people.filter((person) => person.level === level)
  })));
  let ends = $derived(people
    .filter((p) => p.expires_at)
    .sort((a, b) => String(a.expires_at).localeCompare(String(b.expires_at)))
    .slice(0, 4));
  let inheritance = $derived(permissions?.inheritance);
</script>

<div class="ov">
  <div class="ov__col">
    <StorageRootContentCards {content} {rootId} {onMeasured} {isAdmin} />
    <StorageRootQuotaCard {rootId} {isAdmin} {isDfs} />
    <StorageRootSensitivityCard {rootId} {sensitivity} {isAdmin} />
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
                <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" disabled={extending === person.key} onclick={() => extend(person)}>+30 j</button>
              {/if}
            </li>
          {/each}
        </ul>
      </section>
    {/if}

    <RecentActivityCard items={activity} emptyLabel={t('No activity found for this storage root.')} onOpenHistory={onOpenActivity} />
  </div>

  <section class="ov__card ov__side" aria-label={t('Governance')}>
    <header><h2>{t('Governance')}</h2></header>
    <dl>
      <div>
        <dt>{t('Guardians')}</dt>
        <dd>
          {#each guardianNames as name (name)}
            <span class="ov__chip" animate:flip={{ duration: dur(MOTION.base) }} in:pop={{ y: 4 }} out:pop={{ duration: MOTION.fast, y: 0 }}><span class="ov__face is-tiny">{initials(name)}</span>{name}</span>
          {:else}
            <span class="ov__warn">{t('None: only the administrators can approve the requests.')}</span>
          {/each}
          {#if guardiansMissing && guardianNames.length}<span class="ov__warn">{t('Too few')}</span>{/if}
          <button type="button" class="ov__add" onclick={onOpenGuardians}>{guardianNames.length ? t('Manage') : t('+ Add')}</button>
        </dd>
      </div>
      <div>
        <dt>{t('Tags')}</dt>
        <dd>
          {#each tags as tag (tagId(tag))}<span class="ov__pill" animate:flip={{ duration: dur(MOTION.base) }} in:pop={{ y: 4 }} out:pop={{ duration: MOTION.fast, y: 0 }}><TagPill label={tagLabel(tag)} color={tagColor(tag)} small={true} /></span>{/each}
          <button type="button" class="ov__add" onclick={onOpenTags}>{tags.length ? t('Manage') : t('+ Tag')}</button>
        </dd>
      </div>
      {#if subTags.length}
        <div>
          <dt>{t('Tagged sub-folders')}</dt>
          <dd class="ov__subtags">
            {#each subTags.slice(0, subTagsAll ? subTags.length : 4) as row (row.path)}
              <span class="ov__subtag"><a class="ov__plain" href={`/five-s/explore/${rootId}`} title={row.path}><i class="bi bi-folder" aria-hidden="true"></i>{inner(row.path)}</a>
                {#each row.tags as tag (tag.id)}<TagPill small label={tag.name} color={tag.color ?? null} />{/each}</span>
            {/each}
            {#if subTags.length > 4 && !subTagsAll}<button type="button" class="ov__add" onclick={() => (subTagsAll = true)}>{t('Show the {count} others', { count: subTags.length - 4 })}</button>{/if}
          </dd>
        </div>
      {/if}
      {#if zoneLabel}<div><dt>{t('Zone')}</dt><dd>{zoneLabel}</dd></div>{/if}
      <div><dt>{t('File server')}</dt><dd>{#if endpointHref}<a class="ov__plain" href={endpointHref}>{endpointDisplay}</a>{:else}{endpointDisplay}{/if}</dd></div>
      <div>
        <dt>{t('Inheritance')}</dt>
        <dd>
          {#if !inheritance?.known}<span class="ov__muted">{t('Known at the next ACL read')}</span>
          {:else if inheritance.broken}<span>{t('Broken: the folder keeps its own entries')}</span>
          {:else}<span>{t('Inherited from the parent folder')}</span>{/if}
          {#if isAdmin && inheritance?.known}<button type="button" class="b2s-link-btn" onclick={onToggleInheritance}>{inheritance.broken ? t('Restore') : t('Break')}</button>{/if}
        </dd>
      </div>
      <div><dt>{t('Directory')}</dt><dd>{permissions?.snapshot_at ? t('Synchronised {ago}', { ago: timeAgo(permissions.snapshot_at) }) : '—'}</dd></div>
    </dl>
  </section>
</div>

<style>
  .ov__pill { display: inline-flex; }
  .ov { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(280px, 1fr); gap: 14px; align-items: start; }
  .ov__col { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
  .ov__card { display: flex; flex-direction: column; gap: 12px; min-width: 0; padding: 16px 18px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .ov__card header { display: flex; align-items: center; gap: 12px; }
  .ov__card h2 { margin: 0 auto 0 0; font-size: var(--b2s-fs-md); font-weight: 600; }
  .ov__muted { margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .ov__face.is-small { margin: 0; border: 0; }
  .ov__face.is-tiny { width: 22px; height: 22px; margin: 0; border: 0; }
  .ov__ends { display: grid; gap: 10px; margin: 0; padding: 0; list-style: none; }
  .ov__ends li { display: flex; align-items: center; gap: 12px; }
  .ov__name { flex: 0 1 180px; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ov__bar { flex: 1; height: 4px; overflow: hidden; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-border-soft); }
  .ov__bar span { display: block; height: 4px; background: var(--b2s-color-info); }
  .ov__bar.is-soon span { background: var(--b2s-color-warning); }
  .ov__when { flex: none; color: var(--b2s-color-text-soft); font-size: var(--b2s-fs-xs); white-space: nowrap; }
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
  /* The file server: a link that reads as plain text (underlined on hover only) */
  .ov__plain { color: inherit; text-decoration: none; font-weight: 500; }
  .ov__plain:hover { color: var(--b2s-color-primary, #2563eb); text-decoration: underline; }
  .ov__subtags { display: grid; gap: 6px; }
  .ov__subtag { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
  .ov__subtag a { display: inline-flex; align-items: center; gap: 6px; font-family: var(--b2s-font-mono); font-size: var(--b2s-fs-xs); }
</style>
