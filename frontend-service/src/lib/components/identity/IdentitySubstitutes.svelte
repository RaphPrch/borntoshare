<script lang="ts">
  

  import { flip } from 'svelte/animate';
  import { dur, MOTION, pop } from '$lib/utils/motion';
  import { apiDeleteData, apiGetData, apiPostData } from '$lib/api/client';
  import { reportUiError } from '$lib/errors';
  import { t } from '$lib/i18n';
  import { toast } from '$lib/stores/toast';
  import { formatDate } from '$lib/utils/format';

  
  interface Props {
    /**
   * Backup guardians: during an absence, another person validates the requests of all the folders of this guardian,
   * sees them and receives their notices. Nothing is copied: the right ends by itself on the last day.
   */
    identityId?: number;
    /** The signed-in guardian sets their own backup (dashboard): /me routes, people found by a search */
    self?: boolean;
    isGuardian?: boolean;
    people?: Array<Record<string, any>>;
    onChanged?: () => void;
  }

  let {
    identityId = 0,
    self = false,
    isGuardian = false,
    people = [],
    onChanged = () => {}
  }: Props = $props();

  type Row = { id: number; identity_id: number; substitute_identity_id: number; starts_at: string; ends_at: string; reason: string | null;
    guardian_name: string; substitute_name: string; substitute_email: string | null; revoked_by?: string | null;
    state: 'active' | 'upcoming' | 'past' | 'revoked' };
  const base = () => (self ? '/me/substitutes' : `/identity/${identityId}/substitutes`);
  const endUrl = (id: number) => (self ? `/me/substitutes/${id}` : `/identity/substitutes/${id}`);
  // Self service: the guardian status comes with the list
  let selfGuardian = $state(false);
  let guardian = $derived(self ? selfGuardian : isGuardian);
  let forThem: Row[] = $state([]);
  let byThem: Row[] = $state([]);
  let loadedFor = $state(0);
  let open = $state(false);
  let busy = $state(false);
  const today = new Date().toISOString().slice(0, 10);
  let form = $state({ substitute: 0, starts: today, ends: today, reason: '' });

  async function load() {
    loadedFor = self ? -1 : identityId;
    const data = await apiGetData<{ for_them: Row[]; by_them: Row[]; is_guardian?: boolean }>(fetch, base()).catch(() => null);
    forThem = data?.for_them ?? [];
    byThem = data?.by_them ?? [];
    selfGuardian = Boolean(data?.is_guardian);
  }
  // Self service: the people are searched (a guardian does not get the whole directory)
  let search = $state('');
  let found = $state<Array<{ id: number; name: string; username: string | null; email: string | null }>>([]);
  let searchTimer: ReturnType<typeof setTimeout> | undefined;
  function onSearch(value: string) {
    search = value;
    clearTimeout(searchTimer);
    if (value.trim().length < 2) {
      found = [];
      return;
    }
    searchTimer = setTimeout(async () => {
      found = (await apiGetData<typeof found>(fetch, '/me/substitutes/candidates', { q: value.trim() }).catch(() => null)) ?? [];
    }, 250);
  }
  // The last day shown is the day before the end (the right ends at 00:00 the day after)
  const lastDay = (iso: string) => formatDate(new Date(new Date(iso).getTime() - 1000).toISOString());
  const STATE = () => ({ active: t('in progress'), upcoming: t('upcoming'), past: t('ended'), revoked: t('ended early') });

  async function save() {
    if (busy || !form.substitute) return;
    busy = true;
    try {
      await apiPostData(fetch, base(), { substitute_identity_id: form.substitute, starts_on: form.starts, ends_on: form.ends, reason: form.reason || null });
      toast.success(t('Backup guardian set.'));
      open = false;
      form = { substitute: 0, starts: today, ends: today, reason: '' };
      search = '';
      found = [];
      await load();
      onChanged();
    } catch (error: unknown) {
      reportUiError(error, t('Unable to set the backup guardian.'), 'identity.substitute');
    } finally {
      busy = false;
    }
  }
  async function end(row: Row) {
    busy = true;
    try {
      await apiDeleteData(fetch, endUrl(row.id));
      await load();
      onChanged();
      // Undo: the same period again (from today when it had started)
      toast.success(t('Backup of {name} ended.', { name: row.substitute_name }), {
        action: { label: t('Undo'), run: async () => {
          await apiPostData(fetch, base(), {
            substitute_identity_id: row.substitute_identity_id, starts_on: row.state === 'active' ? today : row.starts_at.slice(0, 10),
            ends_on: new Date(new Date(row.ends_at).getTime() - 1000).toISOString().slice(0, 10), reason: row.reason });
          await load();
          onChanged();
        } }
      });
    } catch (error: unknown) {
      reportUiError(error, t('Unable to end the backup.'), 'identity.substitute.end');
    } finally {
      busy = false;
    }
  }
  $effect.pre(() => {
    if (self ? loadedFor !== -1 : identityId && identityId !== loadedFor) load();
  });
  let candidates = $derived(people.filter((p) => String(p.type ?? 'user') !== 'group' && p.status !== 'inactive' && p.is_active !== false && Number(p.id) !== Number(identityId)));
  const live = (row: Row) => row.state === 'active' || row.state === 'upcoming';
  let current = $derived(forThem.filter(live));
  // The history of the year: periods ended or ended early, given and received
  let history = $derived([...forThem, ...byThem].filter((row) => !live(row)).sort((a, b) => b.starts_at.localeCompare(a.starts_at)));
</script>

{#if guardian || current.length || byThem.some(live) || (self && history.length)}
  <section class="su" aria-label={t('Backup guardian')}>
    <header>
      <h2>{t('Backup guardian')}</h2>
      {#if guardian && !open}<button type="button" class="b2s-link-btn" onclick={() => (open = true)}>{t('Set one for an absence')}</button>{/if}
    </header>

    {#each current as row (row.id)}
      <div class="su__row" class:is-on={row.state === 'active'} animate:flip={{ duration: dur(MOTION.base) }} in:pop={{ y: 4 }} out:pop={{ duration: MOTION.fast, y: 0 }}>
        <span class="su__badge">{STATE()[row.state]}</span>
        <span class="su__who"><b>{row.substitute_name}</b>
          <small>{t('from {start} to {end}', { start: formatDate(row.starts_at), end: lastDay(row.ends_at) })}{row.reason ? ` · ${row.reason}` : ''}{row.substitute_email ? '' : ` · ${t('no e-mail')}`}</small></span>
        <button type="button" class="b2s-link-btn" disabled={busy} onclick={() => end(row)}>{row.state === 'active' ? t('End now') : t('Cancel')}</button>
      </div>
    {:else}
      {#if guardian && !open}<p class="su__muted">{self ? t('Nobody stands in for you. During an absence, a backup validates the requests of all your folders.') : t('Nobody stands in for them. During an absence, a backup validates the requests of all their folders.')}</p>{/if}
    {/each}

    {#each byThem.filter(live) as row (row.id)}
      <div class="su__row is-by" animate:flip={{ duration: dur(MOTION.base) }} in:pop={{ y: 4 }} out:pop={{ duration: MOTION.fast, y: 0 }}>
        <span class="su__badge">{STATE()[row.state]}</span>
        <span class="su__who"><b>{t('Stands in for {name}', { name: row.guardian_name })}</b>
          <small>{t('from {start} to {end}', { start: formatDate(row.starts_at), end: lastDay(row.ends_at) })}</small></span>
      </div>
    {/each}

    {#if open}
      <div class="su__form">
        <label class="su__wide">{t('Backup')}
          {#if self}
            <input class="b2s-input" type="search" value={search} oninput={(event) => onSearch((event.currentTarget as HTMLInputElement).value)}
              placeholder={t('Name, login, e-mail…')} aria-label={t('Search a person')} />
            {#if found.length}
              <select class="b2s-input" bind:value={form.substitute} aria-label={t('Backup')}>
                <option value={0}>{t('Choose a person')}</option>
                {#each found as person (person.id)}<option value={person.id}>{person.name}{person.email ? ` · ${person.email}` : ` · ${t('no e-mail')}`}</option>{/each}
              </select>
            {:else if search.trim().length >= 2}<small class="su__muted">{t('Nobody matches.')}</small>{/if}
          {:else}
            <select class="b2s-input" bind:value={form.substitute}>
              <option value={0}>{t('Choose a person')}</option>
              {#each candidates as person (person.id)}<option value={Number(person.id)}>{person.display_name || person.username}{person.email ? '' : ` · ${t('no e-mail')}`}</option>{/each}
            </select>
          {/if}
        </label>
        <label>{t('From')}<input class="b2s-input" type="date" bind:value={form.starts} min={today} /></label>
        <label>{t('To (included)')}<input class="b2s-input" type="date" bind:value={form.ends} min={form.starts} /></label>
        <label class="su__wide">{t('Reason (optional)')}<input class="b2s-input" bind:value={form.reason} maxlength="300" placeholder={t('Holidays, training…')} /></label>
        <div class="su__btns">
          <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" onclick={() => (open = false)}>{t('Cancel')}</button>
          <button type="button" class="b2s-btn b2s-btn-primary b2s-btn-sm" disabled={busy || !form.substitute || form.ends < form.starts} onclick={save}>{t('Set the backup')}</button>
        </div>
      </div>
    {/if}

    {#if history.length}
      <details class="su__history">
        <summary>{t('History ({count})', { count: history.length })}</summary>
        {#each history as row (row.id)}
          <div class="su__past">
            <span>{forThem.includes(row) ? row.substitute_name : t('Stands in for {name}', { name: row.guardian_name })}</span>
            <small>{t('from {start} to {end}', { start: formatDate(row.starts_at), end: lastDay(row.ends_at) })} · {STATE()[row.state]}{row.state === 'revoked' && row.revoked_by ? ` (${row.revoked_by})` : ''}</small>
          </div>
        {/each}
      </details>
    {/if}
  </section>
{/if}

<style>
  .su { display: flex; flex-direction: column; gap: 10px; padding: 16px 18px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .su header { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
  .su h2 { margin: 0; font-size: var(--b2s-fs-md); font-weight: 600; }
  .su__muted { margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .su__row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; padding: 10px 12px; border: 1px solid var(--b2s-color-border); border-radius: 12px; }
  .su__row.is-on { border-color: var(--b2s-color-success-border); background: var(--b2s-color-success-soft); }
  .su__row.is-by { background: var(--b2s-color-info-soft); border-color: transparent; }
  .su__badge { flex: none; padding: 2px 10px; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-surface); border: 1px solid var(--b2s-color-border); font-size: var(--b2s-fs-xs); }
  .su__who { flex: 1 1 180px; display: flex; flex-direction: column; min-width: 0; }
  .su__row .b2s-link-btn { flex: none; white-space: nowrap; }
  .su__who b { font-weight: 600; }
  .su__who small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .su__form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; padding: 12px; border: 1px dashed var(--b2s-color-border-strong); border-radius: 12px; }
  .su__form label { display: flex; flex-direction: column; gap: 5px; font-size: var(--b2s-fs-sm); font-weight: 500; }
  .su__wide { grid-column: 1 / -1; }
  .su__btns { grid-column: 1 / -1; display: flex; justify-content: flex-end; gap: 8px; }
  .su__history summary { cursor: pointer; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .su__past { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 4px 12px; padding: 6px 2px; border-bottom: 1px solid var(--b2s-color-border-soft); font-size: var(--b2s-fs-sm); }
  .su__past small { color: var(--b2s-color-text-muted); }
</style>
