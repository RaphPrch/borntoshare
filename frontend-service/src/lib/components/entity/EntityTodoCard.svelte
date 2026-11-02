<script context="module" lang="ts">
  export type EntityTodoStep = {
    key: string;
    tone: 'bad' | 'warn' | 'info';
    icon: string;
    title: string;
    detail?: string;
    label: string;
    busy?: boolean;
    run: () => void;
  };
</script>

<script lang="ts">
  /** « To do on this … »: one line per problem, each with the action that settles it; hidden when empty. */
  export let title: string;
  export let steps: EntityTodoStep[] = [];
</script>

{#if steps.length}
  <section class="todo" aria-label={title}>
    <h2><i class="bi bi-exclamation-triangle-fill" aria-hidden="true"></i>{title} · {steps.length}</h2>
    {#each steps as step (step.key)}
      <div class="todo__row">
        <span class={`todo__icon is-${step.tone}`} aria-hidden="true"><i class={`bi ${step.icon}`}></i></span>
        <span class="todo__text"><strong>{step.title}</strong>{#if step.detail}<small>{step.detail}</small>{/if}</span>
        <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" disabled={step.busy} on:click={step.run}>{step.label}</button>
      </div>
    {/each}
  </section>
{/if}

<style>
  .todo { overflow: hidden; border: 1px solid var(--b2s-color-warning-border, #f3d9ad); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .todo h2 { display: flex; align-items: center; gap: 8px; margin: 0; padding: 11px 16px; background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); font-size: var(--b2s-fs-sm); font-weight: 600; }
  .todo__row { display: grid; grid-template-columns: 28px minmax(0, 1fr) auto; gap: 12px; align-items: center; padding: 10px 16px; border-top: 1px solid var(--b2s-color-border); }
  .todo h2 + .todo__row { border-top: 0; }
  .todo__icon { display: grid; place-items: center; width: 28px; height: 28px; border-radius: 8px; font-size: 13px; }
  .todo__icon.is-bad { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger-strong); }
  .todo__icon.is-warn { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .todo__icon.is-info { background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); }
  .todo__text { display: flex; flex-direction: column; min-width: 0; }
  .todo__text strong { font-weight: 600; font-size: var(--b2s-fs-sm); }
  .todo__text small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); overflow-wrap: anywhere; }
</style>
