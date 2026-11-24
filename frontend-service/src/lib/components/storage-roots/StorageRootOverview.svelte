<script lang="ts">
  import { fivesEnabled, governanceEnabled } from '$lib/utils/features';
  

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
  let subTags: Array<{ path: string; tags: Array<{ id: number; name: string; color: string | null; policy?: string | null; automatic?: boolean }> }> = $state([]);
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
    /** v2: which part of the folder sheet (the tabs Overview, Storage · 5S, Sensitivity, Quota) */
    section?: 'overview' | 'storage' | 'sensitivity' | 'quota';
  }

  let {
    section = 'overview',
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
      void apiGetList<{ path: string; tags: Array<{ id: number; name: string; color: string | null; policy?: string | null; automatic?: boolean }> }>(fetch, `/storage-roots/${rootId}/folder-tags`)
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

{#if section === 'storage'}
  <div class="ov__one"><StorageRootContentCards {content} {rootId} {onMeasured} {isAdmin} /></div>
{:else if section === 'sensitivity'}
  <div class="ov__one"><StorageRootSensitivityCard {rootId} {sensitivity} {isAdmin} /></div>
{:else if section === 'quota'}
  <div class="ov__one"><StorageRootQuotaCard {rootId} {isAdmin} {isDfs} /></div>
{:else}
<div class="ov">
  <div class="ov__col">
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

  <section class="ov__card ov__side gv" aria-label={t('Governance')}>
    <header><h2>{$governanceEnabled ? t('Governance') : t('Details')}</h2></header>
    {#if $governanceEnabled}
      <div class="gv__block">
        <div class="gv__head">
          <span class="gv__label"><i class="bi bi-person-check" aria-hidden="true"></i>{t('Guardians')}</span>
          <button type="button" class="b2s-btn b2s-btn-ghost b2s-btn-sm" onclick={onOpenGuardians}>{guardianNames.length ? t('Manage') : t('Add')}</button>
        </div>
        {#if guardianNames.length}
          <ul class="gv__people">
            {#each guardianNames as name (name)}
              <li animate:flip={{ duration: dur(MOTION.base) }} in:pop={{ y: 4 }} out:pop={{ duration: MOTION.fast, y: 0 }}><span class="gv__face" aria-hidden="true">{initials(name)}</span><span>{name}</span></li>
            {/each}
          </ul>
          {#if guardiansMissing}<p class="gv__note is-warn"><i class="bi bi-exclamation-triangle" aria-hidden="true"></i>{t('Too few: name a second guardian for the absences.')}</p>{/if}
        {:else}
          <p class="gv__note is-warn"><i class="bi bi-exclamation-triangle" aria-hidden="true"></i>{t('None: only the administrators can approve the requests.')}</p>
        {/if}
      </div>
    {/if}
    <div class="gv__block">
      <div class="gv__head">
        <span class="gv__label"><i class="bi bi-tags" aria-hidden="true"></i>{t('Tags')}</span>
        <button type="button" class="b2s-btn b2s-btn-ghost b2s-btn-sm" onclick={onOpenTags}>{tags.length ? t('Manage') : t('Add')}</button>
      </div>
      {#if tags.length}
        <div class="gv__tags">
          {#each tags as tag (tagId(tag))}<span class="ov__pill" animate:flip={{ duration: dur(MOTION.base) }} in:pop={{ y: 4 }} out:pop={{ duration: MOTION.fast, y: 0 }}><TagPill label={tagLabel(tag)} color={tagColor(tag)} small={true} policy={(tag as any).policy ?? null} automatic={Boolean((tag as any).automatic)} /></span>{/each}
        </div>
      {:else}
        <p class="gv__note">{t('No tag yet.')}</p>
      {/if}
    </div>
    {#if subTags.length}
      <div class="gv__block">
        <div class="gv__head"><span class="gv__label"><i class="bi bi-folder2" aria-hidden="true"></i>{t('Tagged sub-folders')}</span></div>
        <div class="ov__subtags">
          {#each subTags.slice(0, subTagsAll ? subTags.length : 4) as row (row.path)}
            <span class="ov__subtag">{#if $fivesEnabled}<a class="ov__plain" href={`/five-s/explore/${rootId}`} title={row.path}><i class="bi bi-folder" aria-hidden="true"></i>{inner(row.path)}</a>{:else}<span class="ov__plain" title={row.path}><i class="bi bi-folder" aria-hidden="true"></i>{inner(row.path)}</span>{/if}
              {#each row.tags as tag (tag.id)}<TagPill small label={tag.name} color={tag.color ?? null} policy={tag.policy ?? null} automatic={Boolean(tag.automatic)} />{/each}</span>
          {/each}
          {#if subTags.length > 4 && !subTagsAll}<button type="button" class="b2s-link-btn" onclick={() => (subTagsAll = true)}>{t('Show the {count} others', { count: subTags.length - 4 })}</button>{/if}
        </div>
      </div>
    {/if}
    <dl class="gv__facts">
      {#if zoneLabel}<div><dt><i class="bi bi-geo-alt" aria-hidden="true"></i>{t('Zone')}</dt><dd>{zoneLabel}</dd></div>{/if}
      <div><dt><i class="bi bi-hdd-network" aria-hidden="true"></i>{t('File server')}</dt><dd>{#if endpointHref}<a class="ov__plain" href={endpointHref}>{endpointDisplay}</a>{:else}{endpointDisplay}{/if}</dd></div>
      {#if $governanceEnabled}
        <div>
          <dt><i class="bi bi-diagram-3" aria-hidden="true"></i>{t('Inheritance')}</dt>
          <dd>
            {#if !inheritance?.known}<span class="gv__muted">{t('Known at the next ACL read')}</span>
            {:else if inheritance.broken}<span>{t('Broken: the folder keeps its own entries')}</span>
            {:else}<span>{t('Inherited from the parent folder')}</span>{/if}
            {#if isAdmin && inheritance?.known}<button type="button" class="b2s-link-btn" onclick={onToggleInheritance}>{inheritance.broken ? t('Restore') : t('Break')}</button>{/if}
          </dd>
        </div>
        <div><dt><i class="bi bi-people" aria-hidden="true"></i>{t('Directory')}</dt><dd>{permissions?.snapshot_at ? t('Synchronised {ago}', { ago: timeAgo(permissions.snapshot_at) }) : '—'}</dd></div>
      {/if}
    </dl>
  </section>
</div>
{/if}

<style>
  .ov__one { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
  .ov__pill { display: inline-flex; }
  .ov { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(280px, 1fr); gap: 14px; align-items: start; }
  .ov__col { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
  .ov__card { display: flex; flex-direction: column; gap: 12px; min-width: 0; padding: 16px 18px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .ov__card header { display: flex; align-items: center; gap: 12px; }
  .ov__card h2 { margin: 0 auto 0 0; font-size: var(--b2s-fs-md); font-weight: 600; }
  .ov__face.is-small { margin: 0; border: 0; }
  .ov__ends { display: grid; gap: 10px; margin: 0; padding: 0; list-style: none; }
  .ov__ends li { display: flex; align-items: center; gap: 12px; }
  .ov__name { flex: 0 1 180px; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ov__bar { flex: 1; height: 4px; overflow: hidden; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-border-soft); }
  .ov__bar span { display: block; height: 4px; background: var(--b2s-color-info); }
  .ov__bar.is-soon span { background: var(--b2s-color-warning); }
  .ov__when { flex: none; color: var(--b2s-color-text-soft); font-size: var(--b2s-fs-xs); white-space: nowrap; }
  .ov__side { position: sticky; top: calc(var(--b2s-shell-top) + 16px); }
  /* The file server: a link that reads as plain text (underlined on hover only) */
  .ov__plain { color: inherit; text-decoration: none; font-weight: 500; }
  .ov__plain:hover { color: var(--b2s-color-primary); text-decoration: underline; }
  .ov__subtags { display: grid; gap: 6px; }
  .ov__subtag { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
  .ov__subtag a { display: inline-flex; align-items: center; gap: 6px; font-family: var(--b2s-font-mono); font-size: var(--b2s-fs-xs); }
  /* Governance card: blocks with a titled head and their action, then the facts of the folder */
  .gv { gap: 0; padding: 0; }
  .gv > header { padding: 16px 18px 6px; }
  .gv__block { display: flex; flex-direction: column; gap: 10px; padding: 12px 18px 14px; border-bottom: 1px solid var(--b2s-color-border-soft); }
  .gv__head { display: flex; align-items: center; justify-content: space-between; gap: 8px; min-height: 28px; }
  .gv__label { display: inline-flex; align-items: center; gap: 8px; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; }
  .gv__label i { color: var(--b2s-accent-vivid); font-size: 14px; }
  .gv__people { display: grid; gap: 6px; margin: 0; padding: 0; list-style: none; }
  .gv__people li { display: flex; align-items: center; gap: 10px; font-weight: 500; }
  .gv__face { display: grid; flex: none; place-items: center; width: 30px; height: 30px; border-radius: 50%; background: var(--b2s-accent-soft); color: var(--b2s-accent-strong); font-size: 11px; font-weight: 700; }
  .gv__tags { display: flex; flex-wrap: wrap; gap: 6px; }
  .gv__note { display: flex; align-items: flex-start; gap: 8px; margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); line-height: 1.45; }
  .gv__note.is-warn { padding: 8px 10px; border-radius: var(--b2s-radius-sm); background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .gv__muted { color: var(--b2s-color-text-muted); }
  .gv__facts { display: grid; gap: 0; margin: 0; padding: 4px 18px 10px; }
  .gv__facts div { display: grid; grid-template-columns: 112px minmax(0, 1fr); gap: 10px; align-items: baseline; padding: 9px 0; border-top: 1px solid var(--b2s-color-border-soft); font-size: var(--b2s-fs-sm); }
  .gv__facts div:first-child { border-top: 0; }
  .gv__facts dt { display: inline-flex; align-items: center; gap: 7px; color: var(--b2s-color-text-muted); }
  .gv__facts dt i { color: var(--b2s-color-text-faint); }
  .gv__facts dd { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 0; min-width: 0; overflow-wrap: anywhere; }
</style>
