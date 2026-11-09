<script lang="ts">
  import { listIdentityGroupMembers, type IdentityGroupMember } from '$lib/api/identity';
  import EntityActionGroup, { type EntityActionItem } from '$lib/components/entity/EntityActionGroup.svelte';
  import EmptyStateInline from '$lib/components/ui/EmptyStateInline.svelte';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import { t } from '$lib/i18n';

  /** A directory group with a role in BornToShare: every member gets it, the directory decides who is in. */
  export let item: Record<string, any>;
  export let busy = false;
  export let onSetRole: (role: 'user' | 'platform_admin') => Promise<boolean> = async () => false;
  export let onDelete: () => void = () => {};

  let members: IdentityGroupMember[] | null = null;
  let loadedFor = '';
  $: key = String(item?.id ?? '');
  $: if (key && key !== loadedFor) load();
  async function load() {
    loadedFor = key;
    members = null;
    members = await listIdentityGroupMembers(fetch, item.id).catch(() => []);
  }
  $: isAdmin = Array.isArray(item?.roles) && item.roles.includes('platform_admin');
  $: actions = [{ key: 'delete', label: t('Remove the role'), icon: 'bi-trash', variant: 'danger', overflow: true, onClick: onDelete }] as EntityActionItem[];
</script>

<div class="gw">
  <header class="gw__hero">
    <span class="gw__icon" aria-hidden="true"><i class="bi bi-people"></i></span>
    <div class="gw__main">
      <span class="gw__crumbs">{t('Identities')} › {t('Directory groups')} › {item?.source_name ?? ''}</span>
      <h1>{item?.display_name || item?.username}</h1>
      {#if item?.dn}<span class="gw__chip mono">{item.dn}</span>{/if}
    </div>
    <div class="gw__side">
      <div class="gw__seg" role="radiogroup" aria-label={t('Role of its members')}>
        <button type="button" role="radio" aria-checked={!isAdmin} class:is-on={!isAdmin} disabled={busy} on:click={() => isAdmin && onSetRole('user')}>{t('User')}</button>
        <button type="button" role="radio" aria-checked={isAdmin} class:is-on={isAdmin} disabled={busy} on:click={() => !isAdmin && onSetRole('platform_admin')}>{t('Administrator')}</button>
      </div>
      <EntityActionGroup {actions} ariaLabel={t('Group actions')} />
    </div>
  </header>
  <p class="gw__note">{t('Every member of this group gets the role. Arrivals and departures are managed in the directory and read again at each synchronization.')}</p>
  <section class="gw__card" aria-label={t('Members')}>
    <header><h2>{t('Members')}</h2>{#if members}<small>{t('{count} member(s)', { count: members.length })}</small>{/if}</header>
    {#if members === null}
      <LoadingState skeleton="rows" rows={3} />
    {:else if members.length}
      {#each members as member (member.id ?? member.username)}
        <div class="gw__row">
          <b>{member.display_name || member.username}</b>
          <span class="mono">{member.username}</span>
          <span class:is-warn={!member.email}>{member.email || t('no e-mail')}</span>
        </div>
      {/each}
    {:else}
      <EmptyStateInline message={t('No member in the last reading of the directory.')} />
    {/if}
  </section>
</div>

<style>
  .gw { display: flex; flex-direction: column; gap: 16px; }
  .gw__hero { display: flex; gap: 18px; align-items: flex-start; padding: 22px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .gw__icon { flex: 0 0 56px; height: 56px; display: grid; place-items: center; border-radius: 14px; background: #efe7fb; color: #6b3fc4; font-size: 22px; }
  .gw__main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 8px; }
  .gw__crumbs { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .gw__main h1 { margin: 0; font-size: 26px; font-weight: 700; letter-spacing: -0.02em; }
  .gw__chip { align-self: flex-start; max-width: 100%; padding: 5px 10px; border: 1px solid var(--b2s-color-border); border-radius: 8px; background: var(--b2s-color-surface-soft, #f5f7fa); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .gw__side { display: flex; flex-direction: column; align-items: flex-end; gap: 8px; }
  .gw__seg { display: flex; gap: 2px; padding: 3px; border-radius: 12px; background: var(--b2s-color-neutral-soft); }
  .gw__seg button { padding: 8px 14px; border: 0; border-radius: 10px; background: transparent; color: var(--b2s-color-text-muted); font: inherit; font-size: var(--b2s-fs-sm); font-weight: 600; cursor: pointer; }
  .gw__seg button.is-on { background: var(--b2s-color-surface); color: var(--b2s-color-text); box-shadow: 0 1px 3px rgba(14, 18, 24, 0.12); }
  .gw__note { margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .gw__card { display: flex; flex-direction: column; gap: 4px; padding: 16px 18px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .gw__card header { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 6px; }
  .gw__card h2 { margin: 0; font-size: var(--b2s-fs-md); font-weight: 600; }
  .gw__card small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .gw__row { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1.2fr); gap: 12px; padding: 9px 0; border-top: 1px solid var(--b2s-color-border); font-size: var(--b2s-fs-sm); }
  .gw__row b { font-weight: 500; }
  .is-warn { color: var(--b2s-color-warning-strong, #9a5b00); }
  .mono { font-family: var(--b2s-font-mono); font-size: var(--b2s-fs-xs); }
</style>
