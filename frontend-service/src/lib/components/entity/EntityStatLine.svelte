<script context="module" lang="ts">
  export type EntityStatItem = {
    key: string;
    label: string;
    value: string | number;
    /** Large figure with its note next to it, instead of a medium value with a hint below */
    big?: boolean;
    note?: string;
    hint?: string;
    tone?: 'success' | 'warning' | 'danger' | 'muted';
    /** Read / modify bar */
    split?: { read: number; write: number } | null;
    href?: string;
    onClick?: () => void;
  };
</script>

<script lang="ts">
  /** The figures of an entity on one line, separated by rules instead of cards. */
  export let items: EntityStatItem[] = [];
  export let ariaLabel = '';
</script>

<section class="esl" aria-label={ariaLabel} style={`--esl-columns: ${items.length}`}>
  {#each items as item (item.key)}
    <svelte:element
      this={item.href ? 'a' : item.onClick ? 'button' : 'div'}
      href={item.href}
      type={item.onClick && !item.href ? 'button' : undefined}
      class="esl__item"
      class:is-link={Boolean(item.href || item.onClick)}
      on:click={item.onClick}
      role={undefined}
    >
      <span class="esl__label">{item.label}</span>
      {#if item.big}
        <span class="esl__value"><strong class="is-big">{item.value}</strong>{#if item.note}<small>{item.note}</small>{/if}</span>
      {:else}
        <strong class={item.tone ? `is-${item.tone}` : ''}>{item.value}</strong>
      {/if}
      {#if item.split && item.split.read + item.split.write > 0}
        <span class="esl__split" aria-hidden="true"><span class="is-read" style={`flex: ${item.split.read}`}></span><span class="is-write" style={`flex: ${item.split.write}`}></span></span>
      {/if}
      {#if item.hint}<small>{item.hint}</small>{/if}
    </svelte:element>
  {/each}
</section>

<style>
  .esl {
    display: grid;
    grid-template-columns: repeat(var(--esl-columns), minmax(0, 1fr));
    border-top: 1px solid var(--b2s-color-border-soft);
    border-bottom: 1px solid var(--b2s-color-border-soft);
  }

  .esl__item {
    display: grid;
    align-content: start;
    gap: 6px;
    min-width: 0;
    padding: 14px 18px;
    border: 0;
    border-left: 1px solid var(--b2s-color-border-soft);
    background: none;
    color: var(--b2s-color-text);
    font: inherit;
    text-align: left;
    text-decoration: none;
  }

  .esl__item:first-child {
    padding-left: 0;
    border-left: 0;
  }

  .esl__item.is-link {
    cursor: pointer;
  }

  .esl__item.is-link:hover strong {
    color: var(--b2s-color-info-strong);
  }

  .esl__label,
  .esl__item small {
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
  }

  .esl__item strong {
    font-size: var(--b2s-fs-lg);
    font-weight: 600;
  }

  .esl__item strong.is-big {
    font-size: var(--b2s-fs-2xl);
    font-weight: 700;
  }

  .esl__value {
    display: flex;
    align-items: baseline;
    gap: 10px;
  }

  .esl__value small {
    color: var(--b2s-color-text-soft);
  }

  .esl__split {
    display: flex;
    gap: 2px;
    height: 4px;
    max-width: 220px;
    overflow: hidden;
    border-radius: var(--b2s-radius-pill);
  }

  .esl__split .is-read { background: var(--b2s-color-info); }
  .esl__split .is-write { background: var(--b2s-color-warning); }

  strong.is-success { color: var(--b2s-color-success-strong); }
  strong.is-warning { color: var(--b2s-color-warning-strong); }
  strong.is-danger { color: var(--b2s-color-danger-strong); }
  strong.is-muted { color: var(--b2s-color-text-muted); }

  @media (max-width: 1100px) {
    .esl {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .esl__item:nth-child(odd) {
      padding-left: 0;
      border-left: 0;
    }
  }
</style>
