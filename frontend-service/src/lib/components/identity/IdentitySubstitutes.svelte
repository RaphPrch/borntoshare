<script lang="ts">
  import { flip } from 'svelte/animate';
  import { dur, MOTION, pop } from '$lib/utils/motion';
  import { apiDeleteData, apiGetData, apiPostData } from '$lib/api/client';
  import { reportUiError } from '$lib/errors';
  import { t } from '$lib/i18n';
  import { toast } from '$lib/stores/toast';
  import { formatDate } from '$lib/utils/format';

  /**
   * Backup guardians: during an absence, another person validates the requests of all the folders of this guardian,
   * sees them and receives their notices. Nothing is copied: the right ends by itself on the last day.
   */
  export let identityId: number;
  export let isGuardian = false;
  export let people: Array<Record<string, any>> = [];
  export let onChanged: () => void = () => {};

  type Row = { id: number; identity_id: number; substitute_identity_id: number; starts_at: string; ends_at: string; reason: string | null;
    guardian_name: string; substitute_name: string; substitute_email: string | null; state: 'active' | 'upcoming' | 'past' };
  let forThem: Row[] = [];
  let byThem: Row[] = [];
  let loadedFor = 0;
  let open = false;
  let busy = false;
  const today = new Date().toISOString().slice(0, 10);
  let form = { substitute: 0, starts: today, ends: today, reason: '' };

  $: if (identityId && identityId !== loadedFor) load();
  async function load() {
    loadedFor = identityId;
    const data = await apiGetData<{ for_them: Row[]; by_them: Row[] }>(fetch, `/identity/${identityId}/substitutes`).catch(() => null);
    forThem = data?.for_them ?? [];
    byThem = data?.by_them ?? [];
  }
  $: candidates = people.filter((p) => String(p.type ?? 'user') !== 'group' && p.status !== 'inactive' && p.is_active !== false && Number(p.id) !== Number(identityId));
  // The last day shown is the day before the end (the right ends at 00:00 the day after)
  const lastDay = (iso: string) => formatDate(new Date(new Date(iso).getTime() - 1000).toISOString());
  const STATE = () => ({ active: t('in progress'), upcoming: t('upcoming'), past: t('ended') });

  async function save() {
    if (busy || !form.substitute) return;
    busy = true;
    try {
      await apiPostData(fetch, `/identity/${identityId}/substitutes`, { substitute_identity_id: form.substitute, starts_on: form.starts, ends_on: form.ends, reason: form.reason || null });
      toast.success(t('Backup guardian set.'));
      open = false;
      form = { substitute: 0, starts: today, ends: today, reason: '' };
      await load();
      onChanged();
    } catch (error: unknown) {
      reportUiError(error, 'Unable to set the backup guardian.', 'identity.substitute');
    } finally {
      busy = false;
    }
  }
  async function end(row: Row) {
    busy = true;
    try {
      await apiDeleteData(fetch, `/identity/substitutes/${row.id}`);
      await load();
      onChanged();
      // Undo: the same period again (from today when it had started)
      toast.success(t('Backup of {name} ended.', { name: row.substitute_name }), {
        action: { label: t('Undo'), run: async () => {
          await apiPostData(fetch, `/identity/${identityId}/substitutes`, {
            substitute_identity_id: row.substitute_identity_id, starts_on: row.state === 'active' ? today : row.starts_at.slice(0, 10),
            ends_on: new Date(new Date(row.ends_at).getTime() - 1000).toISOString().slice(0, 10), reason: row.reason });
          await load();
          onChanged();
        } }
      });
    } catch (error: unknown) {
      reportUiError(error, 'Unable to end the backup.', 'identity.substitute.end');
    } finally {
      busy = false;
    }
  }
  $: current = forThem.filter((row) => row.state !== 'past');
</script>

{#if isGuardian || current.length || byThem.some((row) => row.state !== 'past')}
  <section class="su" aria-label={t('Backup guardian')}>
    <header>
      <h2>{t('Backup guardian')}</h2>
      {#if isGuardian && !open}<button type="button" class="b2s-link-btn" on:click={() => (open = true)}>{t('Set one for an absence')}</button>{/if}
    </header>

    {#each current as row (row.id)}
      <div class="su__row" class:is-on={row.state === 'active'} animate:flip={{ duration: dur(MOTION.base) }} in:pop={{ y: 4 }} out:pop={{ duration: MOTION.fast, y: 0 }}>
        <span class="su__badge">{STATE()[row.state]}</span>
        <span class="su__who"><b>{row.substitute_name}</b>
          <small>{t('from {start} to {end}', { start: formatDate(row.starts_at), end: lastDay(row.ends_at) })}{row.reason ? ` · ${row.reason}` : ''}{row.substitute_email ? '' : ` · ${t('no e-mail')}`}</small></span>
        <button type="button" class="b2s-link-btn" disabled={busy} on:click={() => end(row)}>{row.state === 'active' ? t('End now') : t('Cancel')}</button>
      </div>
    {:else}
      {#if isGuardian && !open}<p class="su__muted">{t('Nobody stands in for them. During an absence, a backup validates the requests of all their folders.')}</p>{/if}
    {/each}

    {#each byThem.filter((row) => row.state !== 'past') as row (row.id)}
      <div class="su__row is-by" animate:flip={{ duration: dur(MOTION.base) }} in:pop={{ y: 4 }} out:pop={{ duration: MOTION.fast, y: 0 }}>
        <span class="su__badge">{STATE()[row.state]}</span>
        <span class="su__who"><b>{t('Stands in for {name}', { name: row.guardian_name })}</b>
          <small>{t('from {start} to {end}', { start: formatDate(row.starts_at), end: lastDay(row.ends_at) })}</small></span>
      </div>
    {/each}

    {#if open}
      <div class="su__form">
        <label class="su__wide">{t('Backup')}
          <select class="b2s-input" bind:value={form.substitute}>
            <option value={0}>{t('Choose a person')}</option>
            {#each candidates as person (person.id)}<option value={Number(person.id)}>{person.display_name || person.username}{person.email ? '' : ` · ${t('no e-mail')}`}</option>{/each}
          </select>
        </label>
        <label>{t('From')}<input class="b2s-input" type="date" bind:value={form.starts} min={today} /></label>
        <label>{t('To (included)')}<input class="b2s-input" type="date" bind:value={form.ends} min={form.starts} /></label>
        <label class="su__wide">{t('Reason (optional)')}<input class="b2s-input" bind:value={form.reason} maxlength="300" placeholder={t('Holidays, training…')} /></label>
        <div class="su__btns">
          <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" on:click={() => (open = false)}>{t('Cancel')}</button>
          <button type="button" class="b2s-btn b2s-btn-primary b2s-btn-sm" disabled={busy || !form.substitute || form.ends < form.starts} on:click={save}>{t('Set the backup')}</button>
        </div>
      </div>
    {/if}
  </section>
{/if}

<style>
  .su { display: flex; flex-direction: column; gap: 10px; padding: 16px 18px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .su header { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
  .su h2 { margin: 0; font-size: var(--b2s-fs-md); font-weight: 600; }
  .su__muted { margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .su__row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; padding: 10px 12px; border: 1px solid var(--b2s-color-border); border-radius: 12px; }
  .su__row.is-on { border-color: var(--b2s-color-success-border, #cfe9d9); background: var(--b2s-color-success-soft, #f3fbf6); }
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
</style>
