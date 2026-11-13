<script lang="ts">
  import { invalidateAll } from '$app/navigation';
  import { updateIdentity, type PlatformAdmins } from '$lib/api/identity';
  import { reportUiError } from '$lib/errors';
  import { toast } from '$lib/stores/toast';
  import { t } from '$lib/i18n';

  
  interface Props {
    /**
   * Who administers BornToShare: each path to the role (local account, directory account, directory group) drawn
   * as a flow towards the role, the people it gives the role to, and the fixes to apply in one click (undo kept).
   */
    data: Record<string, any>;
  }

  let { data }: Props = $props();
  let admins = $derived((data.admins ?? { direct: [], groups: [], effective: 0, issues: [] }) as PlatformAdmins);
  // Nobody disables or demotes their own account (the server refuses it too)
  let meId = $derived(Number(data.user?.id ?? 0));

  type Path = { key: string; initials: string; name: string; sub: string; kind: 'local' | 'ad' | 'group'; off: boolean; href: string | null };
  const initials = (text: string) => text.split(/[ .\-_]/).filter(Boolean).slice(0, 2).map((part) => part[0].toUpperCase()).join('') || '?';
  let paths = $derived([
    ...admins.direct.map((person): Path => ({
      key: `u${person.id}`, initials: initials(person.name), name: person.name,
      sub: `${person.username} · ${person.source_name ?? (person.auth_source === 'local' ? 'Local' : '')}`,
      kind: person.auth_source === 'local' ? 'local' : 'ad', off: !person.is_active, href: `/admin/identity?selected=user:${person.id}`
    })),
    ...admins.groups.map((group): Path => ({
      key: `g${group.id}`, initials: initials(group.name), name: group.name,
      sub: `${group.source_name ?? ''} · ${group.members.length ? t('members: {names}', { names: group.members.map((m) => m.username).join(', ') }) : t('no member in BornToShare')}`,
      kind: 'group', off: false, href: null
    }))
  ]);
  const KIND = () => ({ local: { label: t('local account'), tone: 'is-local' }, ad: { label: t('direct role'), tone: 'is-direct' }, group: { label: t('directory group'), tone: 'is-group' } });

  let busy = $state(false);
  async function apply(change: () => Promise<unknown>, text: string, revert: () => Promise<unknown>) {
    if (busy) return;
    busy = true;
    try {
      await change();
      await invalidateAll();
      toast.success(text, { action: { label: t('Undo'), run: async () => { await revert(); await invalidateAll(); } } });
    } catch (error: unknown) {
      reportUiError(error, 'The change failed.', 'identity.admins.fix');
    } finally {
      busy = false;
    }
  }
  const removeDirect = (id: number, name: string) =>
    apply(() => updateIdentity(fetch, id, { application_role: 'user' }), t('Direct role of {name} removed.', { name }), () => updateIdentity(fetch, id, { application_role: 'platform_admin' }));
  const disableLocal = (id: number, name: string) =>
    apply(() => updateIdentity(fetch, id, { is_active: false }), t('{name} disabled.', { name }), () => updateIdentity(fetch, id, { is_active: true }));
</script>

<section class="ad">
  <header class="ad__top">
    <div>
      <a class="ad__back" href="/admin/identity"><i class="bi bi-chevron-left" aria-hidden="true"></i>{t('Identities')}</a>
      <h1>{t('Who administers BornToShare')}</h1>
      <p>{t('Each path to the administrator role, and who takes it.')}</p>
    </div>
  </header>

  <section class="ad__flow" aria-label={t('Paths to the role')}>
    <div class="ad__paths">
      {#each paths as path (path.key)}
        <div class="ad__row" class:is-off={path.off}>
          <span class={`ad__av is-${path.kind}`}>{path.initials}</span>
          <span class="ad__who">
            {#if path.href}<a href={path.href}><b>{path.name}</b></a>{:else}<b>{path.name}</b>{/if}
            <small class="mono">{path.sub}</small>
          </span>
          <span class="ad__line" aria-hidden="true"></span>
          <span class={`ad__path ${KIND()[path.kind].tone}`}>{KIND()[path.kind].label}</span>
          <span class="ad__line" aria-hidden="true"></span>
          <span class="ad__arrow" aria-hidden="true"></span>
        </div>
      {:else}
        <p class="ad__muted">{t('Nobody holds the role.')}</p>
      {/each}
    </div>
    <div class="ad__role">
      <span>{t('Role')}</span>
      <b>{t('Platform administrator')}</b>
      <strong>{admins.effective}</strong>
      <small>{t('distinct people, through {count} path(s)', { count: paths.filter((path) => !path.off).length })}</small>
    </div>
  </section>

  {#if admins.issues.length}
    <section class="ad__fixes" aria-label={t('To review')}>
      {#each admins.issues as issue (issue.code + (issue.identity_id ?? ''))}
        <article class="ad__fix">
          <span class="ad__tag">{t('to review')}</span>
          {#if issue.code === 'DIRECT_AND_GROUP'}
            <strong>{t('{name} is an administrator twice', { name: issue.name ?? '' })}</strong>
            <p>{t('Directly and through a directory group. The direct role would survive their leaving the group: remove it so that the directory decides alone.')}</p>
            {#if issue.identity_id !== meId}<button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" disabled={busy} onclick={() => issue.identity_id && removeDirect(issue.identity_id, issue.name ?? '')}>{t('Remove the direct role')}</button>{/if}
          {:else if issue.code === 'SEVERAL_LOCAL_ADMINS'}
            <strong>{t('{count} local administrator accounts', { count: issue.identities?.length ?? 0 })}</strong>
            <p>{t('A local account is the fallback when the directory no longer answers. Keep one, password in a vault, and disable the others.')}</p>
            <div class="ad__btns">
              {#each issue.identities ?? [] as person (person.id)}
                {#if person.id === meId}
                  <span class="ad__me">{t('{name} (you)', { name: person.name })}</span>
                {:else}
                  <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" disabled={busy} onclick={() => disableLocal(person.id, person.name)}>{t('Disable {name}', { name: person.name })}</button>
                {/if}
              {/each}
            </div>
          {/if}
        </article>
      {/each}
    </section>
  {:else}
    <p class="ad__ok"><i class="bi bi-check2-circle" aria-hidden="true"></i>{t('Nothing to review: each administrator holds the role once, and one local account remains for the fallback.')}</p>
  {/if}

  <p class="ad__muted">{t('Recommended: give the role through a directory group. Arrivals and departures are managed in the directory and read again at each synchronization; a local account stays for the fallback.')}</p>


</section>

<style>
  .ad { padding: var(--b2s-page-padding, 24px 28px); display: flex; flex-direction: column; gap: 18px; max-width: 1240px; }
  .ad__back { display: inline-flex; align-items: center; gap: 4px; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); text-decoration: none; }
  .ad__top h1 { margin: 0; font-size: var(--b2s-fs-overview-title, 38px); line-height: 1.05; font-weight: 600; letter-spacing: -0.03em; }
  .ad__top p { margin: 6px 0 0; color: var(--b2s-color-text-muted); font-size: 15px; }
  .ad__flow { display: grid; grid-template-columns: minmax(0, 1fr) 260px; gap: 28px; padding: 22px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .ad__paths { display: flex; flex-direction: column; gap: 12px; justify-content: center; }
  .ad__row { display: flex; align-items: center; gap: 12px; padding: 10px 12px; border: 1px solid var(--b2s-color-border); border-radius: 12px; transition: opacity 0.2s; }
  .ad__row.is-off { opacity: 0.45; }
  .ad__row.is-off .ad__line { border-top-style: dashed; border-color: var(--b2s-color-border-strong); }
  .ad__row.is-off b { text-decoration: line-through; }
  .ad__av { flex: 0 0 38px; height: 38px; display: grid; place-items: center; border-radius: 50%; font-size: 12px; font-weight: 700; }
  .ad__av.is-local { background: var(--b2s-color-neutral-soft); color: var(--b2s-color-text-muted); }
  .ad__av.is-ad { background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); }
  .ad__av.is-group { border-radius: 9px; background: #efe7fb; color: #6b3fc4; }
  .ad__who { display: flex; flex-direction: column; min-width: 170px; max-width: 320px; }
  .ad__who a { color: inherit; text-decoration: none; }
  .ad__who b { font-weight: 600; }
  .ad__who small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--b2s-color-text-muted); }
  .ad__line { flex: 1; min-width: 24px; border-top: 2px solid #8a93a3; }
  .ad__arrow { width: 0; height: 0; border-top: 6px solid transparent; border-bottom: 6px solid transparent; border-left: 8px solid #8a93a3; }
  .ad__path { padding: 3px 10px; border-radius: var(--b2s-radius-pill); font-size: var(--b2s-fs-xs); font-weight: 500; white-space: nowrap; }
  .ad__path.is-local { background: var(--b2s-color-neutral-soft); color: var(--b2s-color-text); }
  .ad__path.is-direct { background: var(--b2s-color-warning-soft, #fdefd9); color: var(--b2s-color-warning-strong, #9a5b00); }
  .ad__path.is-group { background: #e6f4f1; color: #0f766e; }
  .ad__role { display: flex; flex-direction: column; justify-content: center; gap: 8px; padding: 20px; border-radius: 16px; background: linear-gradient(160deg, #0e1218, #1f2a3a); color: #ffffff; }
  .ad__role span { color: #b6f24a; font-size: var(--b2s-fs-xs); letter-spacing: 0.05em; text-transform: uppercase; }
  .ad__role b { font-size: 20px; line-height: 1.2; }
  .ad__role strong { font-size: 34px; }
  .ad__role small { color: #c7cfdb; font-size: var(--b2s-fs-sm); }
  .ad__fixes { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 12px; }
  .ad__fix { display: flex; flex-direction: column; align-items: flex-start; gap: 8px; padding: 16px; border: 1px solid var(--b2s-color-warning-border, #f3d9a8); border-radius: var(--b2s-radius-lg); background: #fff8ea; }
  .ad__fix p { margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .ad__tag { padding: 2px 10px; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-warning-soft, #fdefd9); color: var(--b2s-color-warning-strong, #9a5b00); font-size: var(--b2s-fs-xs); }
  .ad__btns { display: flex; flex-wrap: wrap; gap: 8px; }
  .ad__me { display: inline-flex; align-items: center; padding: 6px 12px; border-radius: 10px; background: var(--b2s-color-neutral-soft); color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .ad__ok { display: flex; gap: 8px; margin: 0; padding: 12px 16px; border-radius: var(--b2s-radius-lg); background: var(--b2s-color-success-soft, #ddf5e9); color: var(--b2s-color-success-strong, #157a3c); }
  .ad__muted { margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .mono { font-family: var(--b2s-font-mono); font-size: var(--b2s-fs-xs); }
</style>
