<script lang="ts">
  import { preventDefault } from 'svelte/legacy';

  import { t } from '$lib/i18n';
  import { recall, remember } from '$lib/utils/remember';
  import { toast } from '$lib/stores/toast';

  /**
   * Named views of a list (« My folders without guardian », « Critical alerts in Paris »): the filters of the moment,
   * saved under a name in this browser, applied again in one click.
   */
  type View = { name: string; state: Record<string, unknown> };
  
  interface Props {
    key: string;
    /** The filters of the moment (what a view saves) */
    current: Record<string, unknown>;
    apply: (state: Record<string, unknown>) => void;
  }

  let { key, current, apply }: Props = $props();

  // Read once: the key of a list does not change while it is shown
  // svelte-ignore state_referenced_locally
  let views: View[] = $state((recall(`views:${key}`, { views: [] as unknown[] }).views as View[]).filter((v) => v && typeof v.name === 'string'));
  let naming = $state(false);
  let name = $state('');
  let input: HTMLInputElement | null = $state(null);

  const same = (a: Record<string, unknown>, b: Record<string, unknown>) => JSON.stringify(a) === JSON.stringify(b);
  let active = $derived(views.find((view) => same(view.state, current))?.name ?? null);

  function persist() {
    remember(`views:${key}`, { views });
  }
  function save() {
    const clean = name.trim().slice(0, 40);
    if (!clean) return;
    views = [...views.filter((v) => v.name.toLowerCase() !== clean.toLowerCase()), { name: clean, state: { ...current } }];
    persist();
    naming = false;
    name = '';
    toast.success(t('View « {name} » saved.', { name: clean }));
  }
  function remove(view: View) {
    views = views.filter((v) => v !== view);
    persist();
  }
  async function startNaming() {
    naming = true;
    await Promise.resolve();
    input?.focus();
  }
</script>

<div class="sv" role="group" aria-label={t('Saved views')}>
  {#each views as view (view.name)}
    <span class="sv__chip" class:is-on={active === view.name}>
      <button type="button" onclick={() => apply({ ...view.state })} aria-pressed={active === view.name}><i class="bi bi-bookmark" aria-hidden="true"></i>{view.name}</button>
      <button type="button" class="sv__x" aria-label={t('Delete the view {name}', { name: view.name })} onclick={() => remove(view)}><i class="bi bi-x" aria-hidden="true"></i></button>
    </span>
  {/each}
  {#if naming}
    <form class="sv__form" onsubmit={preventDefault(save)}>
      <input bind:this={input} bind:value={name} class="b2s-input" maxlength="40" placeholder={t('Name of the view')} aria-label={t('Name of the view')}
        onkeydown={(event) => { if (event.key === 'Escape') { naming = false; name = ''; } }} />
      <button type="submit" class="b2s-btn b2s-btn-primary b2s-btn-sm" disabled={!name.trim()}>{t('Save')}</button>
    </form>
  {:else if !active}
    <button type="button" class="b2s-link-btn sv__add" onclick={startNaming}><i class="bi bi-bookmark-plus" aria-hidden="true"></i>{t('Save this view')}</button>
  {/if}
</div>

<style>
  .sv { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
  .sv__chip { display: inline-flex; align-items: center; border: 1px solid var(--b2s-color-border); border-radius: 999px; background: var(--b2s-color-surface); overflow: hidden; }
  .sv__chip.is-on { border-color: #111b3f; background: #111b3f; }
  .sv__chip.is-on button { color: #fff; }
  .sv__chip button { display: inline-flex; align-items: center; gap: 6px; border: 0; background: none; padding: 4px 4px 4px 10px; font: inherit; font-size: var(--b2s-fs-sm); color: var(--b2s-color-text); cursor: pointer; }
  .sv__chip .sv__x { padding: 4px 8px 4px 2px; color: var(--b2s-color-text-muted); }
  .sv__form { display: inline-flex; gap: 6px; align-items: center; }
  .sv__form input { height: 30px; width: 200px; }
  .sv__add { display: inline-flex; align-items: center; gap: 6px; font-size: var(--b2s-fs-sm); }
</style>
