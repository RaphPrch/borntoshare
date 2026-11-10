<script lang="ts">
  import { onMount } from 'svelte';
  import { invalidateAll } from '$app/navigation';
  import FivesModuleSetup from '$lib/components/settings/FivesModuleSetup.svelte';
  import { apiDeleteData, apiGetData, apiPostData, apiPutData } from '$lib/api/client';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import { reportUiError } from '$lib/errors';
  import { t } from '$lib/i18n';
  import { toast } from '$lib/stores/toast';
  import { formatDate } from '$lib/utils/format';

  /**
   * Advanced settings › Features: the optional modules of BornToShare (5S…). A signed license key opens them
   * (checked offline, without any connection), then an administrator switches each one on or off. Switched off,
   * a module keeps its data; its menu and its pages disappear. Shared by Advanced settings › Features and the
   * step « Features » of the first setup.
   */
  /** In the first setup: a lighter header, and what to do next */
  export let inSetup = false;
  type Feature = { key: string; label: string; description: string; icon: string; licensed: boolean; enabled: boolean; switched_on: boolean;
    expires_on: string | null; updated_by: string | null };
  type License = { id: number; license_id: string; customer: string; key_hint: string; features: string[]; issued_on: string | null;
    expires_on: string | null; expired: boolean; activated_at: string | null; activated_by: string | null };
  type State = { features: Feature[]; licenses: License[] };

  let state: State | null = null;
  let key = '';
  let busy = false;
  onMount(async () => {
    state = await apiGetData<State>(fetch, '/features').catch(() => ({ features: [], licenses: [] }));
  });
  const name = (featureKey: string) => state?.features.find((feature) => feature.key === featureKey)?.label ?? featureKey;

  async function run(work: () => Promise<State>, done: string, context: string) {
    if (busy) return;
    busy = true;
    try {
      state = await work();
      if (done) toast.success(done);
      await invalidateAll(); // the menu follows
    } catch (error: unknown) {
      reportUiError(error, 'Unable to change the features.', context);
    } finally {
      busy = false;
    }
  }
  const activate = () => run(async () => {
    const next = await apiPostData<State>(fetch, '/admin/advanced-settings/license', { key: key.trim() });
    key = '';
    return next;
  }, t('License key accepted.'), 'features.license');
  const remove = (license: License) => run(() => apiDeleteData<State>(fetch, `/admin/advanced-settings/license/${license.id}`), t('License removed.'), 'features.remove');
  const toggle = (feature: Feature) => run(() => apiPutData<State>(fetch, `/admin/advanced-settings/features/${feature.key}`, { enabled: !feature.switched_on }),
    feature.switched_on ? t('{name} switched off.', { name: feature.label }) : t('{name} switched on.', { name: feature.label }), 'features.switch');
</script>

{#if !state}
  <LoadingState block skeleton="rows" rows={3} />
{:else}
  <div class="ft" class:is-setup={inSetup}>
    <section class="ft__card" aria-label={t('Features')}>
      <header><h2>{t('Modules')}</h2></header>
      {#each state.features as feature (feature.key)}
        <div class="ft__feature" class:is-on={feature.enabled}>
          <span class="ft__icon"><i class={`bi ${feature.icon}`} aria-hidden="true"></i></span>
          <div class="ft__what">
            <b>{feature.label}</b>
            <small>{feature.description}</small>
            <span class="ft__state">
              {#if !feature.licensed}<span class="ft__pill">{t('No license')}</span>
              {:else}<span class="ft__pill is-ok">{t('Licensed')}{feature.expires_on ? ` · ${t('until {date}', { date: formatDate(feature.expires_on) })}` : ` · ${t('no end date')}`}</span>{/if}
              {#if feature.enabled}<span class="ft__pill is-on">{t('On')}</span>{/if}
            </span>
          </div>
          <label class="ft__switch" title={feature.licensed ? '' : t('Enter a license key that opens it first')}>
            <input type="checkbox" role="switch" checked={feature.enabled} disabled={busy || !feature.licensed} on:change={() => toggle(feature)} />
            <span aria-hidden="true"></span>
            <span class="b2s-visually-hidden">{feature.label}</span>
          </label>
        </div>
      {/each}
    </section>

    {#if state.features.find((feature) => feature.key === 'fives')?.licensed}
      <FivesModuleSetup enabled={Boolean(state.features.find((feature) => feature.key === 'fives')?.enabled)} />
    {/if}

    <section class="ft__card" aria-label={t('License key')}>
      <header><h2>{t('License key')}</h2><small>{t('Checked here, without any connection: nothing leaves BornToShare.')}</small></header>
      <form class="ft__key" on:submit|preventDefault={activate}>
        <textarea class="b2s-input" rows="3" bind:value={key} spellcheck="false" autocomplete="off" placeholder="B2S-AAAAA-BBBBB-…"
          aria-label={t('License key')}></textarea>
        <button type="submit" class="b2s-btn b2s-btn-primary" disabled={busy || key.trim().length < 20}><i class="bi bi-key" aria-hidden="true"></i>{t('Activate')}</button>
      </form>
      {#if state.licenses.length}
        <ul class="ft__licenses">
          {#each state.licenses as license (license.id)}
            <li class:is-expired={license.expired}>
              <div>
                <b>{license.customer}</b> <code>{license.key_hint}</code>
                <small>{license.features.map(name).join(', ')} · {license.expires_on ? (license.expired ? t('expired on {date}', { date: formatDate(license.expires_on) }) : t('until {date}', { date: formatDate(license.expires_on) })) : t('no end date')}
                  · {t('activated by {who}', { who: license.activated_by ?? '—' })} {license.activated_at ? formatDate(license.activated_at) : ''}</small>
              </div>
              {#if !inSetup}<button type="button" class="b2s-link-btn" disabled={busy} on:click={() => remove(license)}>{t('Remove the license')}</button>{/if}
            </li>
          {/each}
        </ul>
      {/if}
    </section>
  </div>
{/if}

<style>
  .ft { display: flex; flex-direction: column; gap: 16px; }
  /* In the first setup the panel sits in the step: lighter frames */
  .ft.is-setup .ft__card { padding: 12px 0 0; border: 0; border-top: 1px solid var(--b2s-color-border); border-radius: 0; background: transparent; }
  .ft__card { display: flex; flex-direction: column; gap: 10px; padding: 16px 18px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .ft__card header { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
  .ft__card h2 { margin: 0; font-size: var(--b2s-fs-md); font-weight: 600; }
  .ft__card header small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .ft__feature { display: grid; grid-template-columns: 44px minmax(0, 1fr) auto; gap: 14px; align-items: center; padding: 14px; border: 1px solid var(--b2s-color-border); border-radius: 14px; transition: border-color var(--b2s-motion-base), background-color var(--b2s-motion-base); }
  .ft__feature.is-on { border-color: var(--b2s-color-success-border, #cfe9d9); background: var(--b2s-color-success-soft, #f3fbf6); }
  .ft__icon { display: grid; place-items: center; width: 44px; height: 44px; border-radius: 12px; background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); font-size: 20px; }
  .ft__what { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
  .ft__what small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .ft__state { display: flex; gap: 6px; margin-top: 4px; }
  .ft__pill { padding: 1px 10px; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-neutral-soft); font-size: var(--b2s-fs-xs); font-weight: 600; }
  .ft__pill.is-ok { background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); }
  .ft__pill.is-on { background: var(--b2s-color-success-soft, #eaf7ee); color: var(--b2s-color-success-strong, #1a7f37); }
  .ft__switch { position: relative; display: inline-flex; width: 46px; height: 26px; cursor: pointer; }
  .ft__switch input { position: absolute; inset: 0; opacity: 0; margin: 0; cursor: inherit; }
  .ft__switch span[aria-hidden] { position: absolute; inset: 0; border-radius: 999px; background: var(--b2s-color-border-strong, #cfd6e0); transition: background-color var(--b2s-motion-base); }
  .ft__switch span[aria-hidden]::after { content: ''; position: absolute; top: 3px; left: 3px; width: 20px; height: 20px; border-radius: 50%; background: #fff; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2); transition: transform var(--b2s-motion-base) var(--b2s-ease-out); }
  .ft__switch input:checked + span[aria-hidden] { background: var(--b2s-color-success-strong, #1a7f37); }
  .ft__switch input:checked + span[aria-hidden]::after { transform: translateX(20px); }
  .ft__switch input:disabled + span[aria-hidden] { opacity: 0.5; }
  .ft__switch input:focus-visible + span[aria-hidden] { box-shadow: var(--b2s-focus-ring); }
  .ft__key { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; align-items: end; }
  .ft__key textarea { font-family: var(--b2s-font-mono); font-size: var(--b2s-fs-xs); resize: vertical; }
  .ft__key .b2s-btn i { margin-right: 6px; }
  .ft__licenses { display: flex; flex-direction: column; margin: 0; padding: 0; list-style: none; }
  .ft__licenses li { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 10px 0; border-top: 1px solid var(--b2s-color-border); font-size: var(--b2s-fs-sm); }
  .ft__licenses li div { display: flex; flex-direction: column; gap: 2px; }
  .ft__licenses code { font-family: var(--b2s-font-mono); font-size: var(--b2s-fs-xs); color: var(--b2s-color-text-muted); }
  .ft__licenses small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .ft__licenses li.is-expired b { text-decoration: line-through; }
</style>
