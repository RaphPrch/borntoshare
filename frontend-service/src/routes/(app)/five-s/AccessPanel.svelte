<script lang="ts">
  import { untrack } from 'svelte';
  import { ntfsLevelLabel } from '$lib/components/storage-roots/permissions/permissions-format';
  import { t } from '$lib/i18n';
  import { apiGetData } from '$lib/api/client';
  import { formatDate } from '$lib/utils/format';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';

  /**
   * Who reaches one sub-folder and why (Permission Intelligence): its entries resolved by the core with its directory
   * (groups and their nested members, accounts, system, the whole company, orphan SIDs), the people and every path to
   * their level, what looks excessive, and what the folder changes from its parent.
   */
  interface Props {
    rootId: number;
    path: string;
  }

  let { rootId, path }: Props = $props();

  // ---- who reaches the folder chosen and why (Permission Intelligence: resolved by the core with its directory) ----
  type Via = { kind: 'group' | 'direct'; group?: string; account?: string; nested?: boolean; rights: string; deny: boolean; inherited: boolean };
  type AccessPerson = { username: string | null; display_name: string | null; rights: string | null; denied: boolean; via: Via[] };
  type Principal = { who: string; kind: string; rights: string; deny: boolean; inherited: boolean; members: number | null };
  type AccessData = { read: boolean; entries_total?: number; entries_cut?: boolean; inheritance_broken?: boolean | null;
    analysis?: { principals: Principal[]; people: AccessPerson[]; people_total: number; findings: Array<{ code: string; who: string; rights: string }>; snapshot_at: string | null };
    drift?: { added: Array<{ who: string; level: string }>; removed: Array<{ who: string; level: string }>; parent_known: boolean } };
  let access = $state<AccessData | null>(null);
  let accessFor = $state<string | null>(null);
  let accessState = $state<'idle' | 'loading' | 'ok' | 'failed'>('idle');
  let accessAll = $state(false);
  let accessQuery = $state('');
  async function loadAccess(wanted: string) {
    accessFor = wanted;
    accessState = 'loading';
    accessAll = false;
    accessQuery = '';
    try {
      const data = await apiGetData<AccessData>(fetch, `/modules/fives/storage-roots/${rootId}/folders/access`, wanted ? { path: wanted } : undefined);
      if (accessFor !== wanted) return;
      access = data;
      accessState = 'ok';
    } catch {
      if (accessFor === wanted) accessState = 'failed';
    }
  }
  $effect.pre(() => {
    if (path !== accessFor) {
      const wanted = path;
      untrack(() => void loadAccess(wanted));
    }
  });
  const RIGHTS = (): Record<string, string> => ({ read: t('Read'), modify: t('Modify'), full: t('Full control') });
  const KIND = (): Record<string, string> => ({ group: t('Group'), user: t('Account'), system: t('System'), broad: t('Everyone'), orphan: t('Orphan SID'), unknown: t('Unknown') });
  const FINDING = (): Record<string, string> => ({
    BROAD_WRITE: t('Open to the whole company in writing'), BROAD_READ: t('Readable by the whole company'),
    USER_ACE: t('Account added by hand (not through a group)'), FULL_CONTROL: t('Full control outside the administrators'),
    ORPHAN_SID: t('Account deleted from the directory still has rights'), UNKNOWN_ACCOUNT: t('Account unknown to the directory (local or other domain)'),
    DENY_ENTRY: t('A deny entry: hard to read, check it')
  });
  const SEVERE = new Set(['BROAD_WRITE', 'FULL_CONTROL', 'ORPHAN_SID']);
  let accessPeople = $derived((access?.analysis?.people ?? []).filter((person) => !accessQuery.trim()
    || `${person.display_name ?? ''} ${person.username ?? ''}`.toLowerCase().includes(accessQuery.trim().toLowerCase())));
  const viaText = (via: Via) => via.kind === 'direct' ? t('directly') : via.nested ? t('through {group} (nested group)', { group: via.group ?? '' }) : t('through {group}', { group: via.group ?? '' });

</script>

{#if accessState === 'loading'}
  <LoadingState>{t('Resolving the groups with the directory…')}</LoadingState>
{:else if accessState === 'failed'}
  <p class="ap__hint">{t('The rights of this folder could not be analysed now.')}</p>
{:else if access && !access.read}
  <p class="ap__hint">{t('Read at the next full measure of the folder.')}</p>
{:else if access?.analysis}
  {#each access.analysis.findings as finding (finding.code + finding.who)}
    <p class={`ap__finding ${SEVERE.has(finding.code) ? 'is-bad' : 'is-warn'}`}><i class="bi bi-exclamation-triangle" aria-hidden="true"></i>
      <span><b>{FINDING()[finding.code] ?? finding.code}</b><small>{finding.who} · {RIGHTS()[finding.rights] ?? finding.rights}</small></span></p>
  {/each}
  {#if access.drift?.added.length || access.drift?.removed.length}
    <div class="ap__drift">
      <small>{t('Compared with its parent folder')}</small>
      {#each access.drift.added as entry (entry.who + entry.level)}<span class="is-add">+ {entry.who} · {ntfsLevelLabel(entry.level)}</span>{/each}
      {#each access.drift.removed as entry (entry.who + entry.level)}<span class="is-del">− {entry.who} · {ntfsLevelLabel(entry.level)}</span>{/each}
    </div>
  {/if}
  <ul class="ap__princ">
    {#each access.analysis.principals.filter((p) => p.kind !== 'system') as principal (principal.who + principal.rights + principal.deny)}
      <li><span><b>{principal.who}</b><small>{KIND()[principal.kind] ?? principal.kind}{principal.members != null ? ` · ${t('{count} member(s), nested groups included', { count: principal.members })}` : ''}</small></span>
        <em>{principal.deny ? `${t('Denied')} · ` : ''}{RIGHTS()[principal.rights] ?? principal.rights}</em></li>
    {/each}
  </ul>
  {#if access.analysis.people_total}
    <div class="ap__people-head"><b>{t('{count} person(s)', { count: access.analysis.people_total })}</b>
      {#if access.analysis.people_total > 8}<input class="b2s-input" placeholder={t('Find a person…')} bind:value={accessQuery} aria-label={t('Find a person')} />{/if}</div>
    <ul class="ap__people">
      {#each accessPeople.slice(0, accessAll || accessQuery ? 200 : 8) as person (person.username ?? person.display_name)}
        <li class:is-denied={person.denied}><span><b>{person.display_name}</b><small>{person.via.map(viaText).join(' · ')}</small></span>
          <em>{person.denied ? t('Denied') : RIGHTS()[person.rights ?? ''] ?? '—'}</em></li>
      {/each}
    </ul>
    {#if !accessAll && !accessQuery && accessPeople.length > 8}<button type="button" class="b2s-link-btn" onclick={() => (accessAll = true)}>{t('Show the {count} others', { count: accessPeople.length - 8 })}</button>{/if}
  {/if}
  <p class="ap__hint">{t('Rights of the last measure; groups resolved with the directory as of {date}.', { date: access.analysis.snapshot_at ? formatDate(access.analysis.snapshot_at) : '—' })}
    {#if access.entries_cut} {t('Only part of the entries could be kept.')}{/if}</p>
{/if}

<style>
  .ap__finding { display: flex; gap: 8px; align-items: flex-start; margin: 0; padding: 6px 10px; border-radius: 8px; font-size: var(--b2s-fs-sm); }
  .ap__finding span { display: grid; }
  .ap__finding small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); overflow-wrap: anywhere; }
  .ap__finding.is-bad { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger-strong); }
  .ap__finding.is-warn { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .ap__drift { display: grid; gap: 2px; font-size: var(--b2s-fs-xs); }
  .ap__drift small { color: var(--b2s-color-text-muted); }
  .ap__drift .is-add { color: var(--b2s-color-warning-strong); }
  .ap__drift .is-del { color: var(--b2s-accent); }
  .ap__princ, .ap__people { display: grid; gap: 6px; margin: 0; padding: 0; list-style: none; font-size: var(--b2s-fs-sm); }
  .ap__princ li, .ap__people li { display: flex; justify-content: space-between; gap: 8px; align-items: center; }
  .ap__princ li span, .ap__people li span { display: grid; min-width: 0; }
  .ap__princ b, .ap__people b { font-weight: 500; overflow-wrap: anywhere; }
  .ap__princ small, .ap__people small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .ap__princ em, .ap__people em { font-style: normal; font-size: var(--b2s-fs-xs); font-weight: 600; white-space: nowrap; }
  .ap__people li.is-denied b { text-decoration: line-through; }
  .ap__people-head { display: flex; justify-content: space-between; gap: 8px; align-items: center; }
  .ap__people-head .b2s-input { width: 160px; height: 30px; }
</style>
