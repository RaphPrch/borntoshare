<script lang="ts">
  import { t } from '$lib/i18n';
  import { toast } from '$lib/stores/toast';
  import EntityActionGroup, { type EntityActionItem } from './EntityActionGroup.svelte';

  /**
   * Header of an entity page, as a card: icon, breadcrumb, name, one status pill, small chips
   * (code, directory…), an optional path to copy, and the actions.
   */
  type Tone = 'success' | 'warning' | 'danger' | 'neutral';
  export let icon = 'bi-box';
  export let iconTone: 'green' | 'blue' | 'neutral' = 'neutral';
  export let crumbs: string[] = [];
  export let title = '';
  export let statusLabel = '';
  export let statusTone: Tone = 'neutral';
  export let chips: Array<{ label: string; icon?: string; mono?: boolean; tone?: 'warning' }> = [];
  /** A person: initials in a round avatar instead of the icon; ringed while synchronized with the directory */
  export let avatar = '';
  export let avatarRing = false;
  export let avatarOff = false;
  /** Small text after the status (« updated 9 days ago ») */
  export let note = '';
  export let path = '';
  export let actions: EntityActionItem[] = [];
  export let actionsAriaLabel = t('Entity actions');

  async function copyPath() {
    try {
      await navigator.clipboard.writeText(path);
      toast.success(t('Path copied.'));
    } catch {
      toast.error(t('The path could not be copied.'));
    }
  }
</script>

<header class="ehc">
  {#if avatar}
    <span class="ehc__avatar" class:is-ring={avatarRing} class:is-off={avatarOff} aria-hidden="true">{avatar}</span>
  {:else}
    <span class={`ehc__icon is-${iconTone}`} aria-hidden="true"><i class={`bi ${icon}`}></i></span>
  {/if}
  <div class="ehc__main">
    {#if crumbs.length}
      <nav class="ehc__crumbs" aria-label={t('Location')}>
        {#each crumbs as crumb, index}{#if index}<i class="bi bi-chevron-right" aria-hidden="true"></i>{/if}<span>{crumb}</span>{/each}
      </nav>
    {/if}
    <div class="ehc__title">
      <h1>{title}</h1>
      {#if statusLabel}<span class={`ehc__pill is-${statusTone}`}><span aria-hidden="true"></span>{statusLabel}</span>{/if}
      {#if note || $$slots.note}<small class="ehc__note"><slot name="note">{note}</slot></small>{/if}
    </div>
  </div>
  <div class="ehc__actions">
    {#if $$slots.side}<div class="ehc__side"><slot name="side" /></div>{/if}
    <EntityActionGroup {actions} ariaLabel={actionsAriaLabel} />
  </div>
  {#if path || chips.length}
    <div class="ehc__meta">
      {#if path}
        <span class="ehc__path">
          <code title={path}>{path}</code>
          <button type="button" on:click={copyPath} aria-label={t('Copy the path')}><i class="bi bi-copy" aria-hidden="true"></i>{t('Copy')}</button>
        </span>
      {/if}
      {#each chips as chip (chip.label)}
        <span class="ehc__chip" class:mono={chip.mono} class:is-warning={chip.tone === 'warning'}>{#if chip.icon}<i class={`bi ${chip.icon}`} aria-hidden="true"></i>{/if}{chip.label}</span>
      {/each}
    </div>
  {/if}
</header>

<style>
  .ehc { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; grid-template-areas: "icon main actions" "icon meta meta"; gap: 4px 16px; align-items: center; padding: 18px 20px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); box-shadow: var(--b2s-shadow-sm); }
  .ehc__icon { grid-area: icon; align-self: start; display: grid; place-items: center; width: 48px; height: 48px; border-radius: 14px; background: var(--b2s-color-neutral-soft); color: var(--b2s-color-text-muted); font-size: 22px; }
  .ehc__icon.is-green { background: var(--b2s-accent-soft); color: var(--b2s-color-success-strong); }
  .ehc__icon.is-blue { background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); }
  .ehc__main { grid-area: main; display: flex; flex-direction: column; gap: 4px; min-width: 0; }
  .ehc__crumbs { display: flex; align-items: center; gap: 6px; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .ehc__crumbs i { font-size: 10px; }
  .ehc__title { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
  .ehc__title h1 { margin: 0; font-size: var(--b2s-fs-entity-title, 26px); font-weight: 600; letter-spacing: -0.01em; overflow-wrap: anywhere; }
  .ehc__pill { display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px; border-radius: var(--b2s-radius-pill); font-size: var(--b2s-fs-xs); font-weight: 500; background: var(--b2s-color-neutral-soft); color: var(--b2s-color-text-muted); }
  .ehc__pill span { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
  .ehc__pill.is-success { background: var(--b2s-color-success-soft); color: var(--b2s-color-success-strong); }
  .ehc__pill.is-warning { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .ehc__pill.is-danger { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger-strong); }
  .ehc__meta { grid-area: meta; display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; }
  .ehc__chip { display: inline-flex; align-items: center; gap: 5px; padding: 2px 8px; border-radius: var(--b2s-radius-sm); background: var(--b2s-color-neutral-soft); font-size: var(--b2s-fs-xs); }
  .ehc__chip.mono { font-family: var(--b2s-font-mono); }
  .ehc__path { display: inline-flex; align-items: center; gap: 6px; max-width: 100%; padding: 2px 4px 2px 9px; border-radius: var(--b2s-radius-sm); background: var(--b2s-color-neutral-soft); }
  .ehc__path code { min-width: 0; padding: 0; background: none; color: inherit; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: var(--b2s-font-mono); font-size: var(--b2s-fs-xs); }
  .ehc__path button { display: inline-flex; align-items: center; gap: 4px; flex: none; padding: 1px 8px; border: 0; border-radius: 6px; background: var(--b2s-color-surface); font-size: var(--b2s-fs-xs); cursor: pointer; }
  .ehc__actions { grid-area: actions; align-self: start; display: flex; flex-direction: column; align-items: flex-end; gap: 8px; }
  .ehc__side { display: flex; flex-direction: column; align-items: flex-end; gap: 6px; }
  .ehc__note { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .ehc__chip.is-warning { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .ehc__avatar { grid-area: icon; align-self: start; display: grid; place-items: center; width: 52px; height: 52px; border-radius: 50%; background: linear-gradient(135deg, var(--b2s-color-info-soft), #c9d9fb); color: var(--b2s-color-info-strong); font-size: 18px; font-weight: 700; }
  .ehc__avatar.is-off { background: var(--b2s-color-neutral-soft); color: var(--b2s-color-text-muted); }
  .ehc__avatar.is-ring { animation: ehc-ring 2.4s ease-in-out infinite; }
  @keyframes ehc-ring { 0%, 100% { box-shadow: 0 0 0 3px var(--b2s-color-surface), 0 0 0 5px #2f9e5b; } 50% { box-shadow: 0 0 0 3px var(--b2s-color-surface), 0 0 0 8px rgba(47, 158, 91, 0.25); } }
  @media (prefers-reduced-motion: reduce) { .ehc__avatar.is-ring { animation: none; box-shadow: 0 0 0 3px var(--b2s-color-surface), 0 0 0 5px #2f9e5b; } }
</style>
