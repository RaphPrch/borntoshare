<script module lang="ts">
  export type WizardStep = { label: string; hint?: string | null };
</script>

<script lang="ts">
  import { t } from '$lib/i18n';
  /** Step indicator shared by every wizard. `current` is 1-based. */
  export let steps: WizardStep[] = [];
  export let current = 1;
  export let ariaLabel = t('Wizard progress');
</script>

<ol class="b2s-steps" aria-label={ariaLabel} style={`--b2s-steps-count:${Math.max(1, steps.length)}`}>
  {#each steps as step, idx (idx)}
    <li class:active={current === idx + 1} class:done={current > idx + 1} aria-current={current === idx + 1 ? 'step' : undefined}>
      <span>
        {#if current > idx + 1}<i class="bi bi-check-lg" aria-hidden="true"></i>{:else}{idx + 1}{/if}
      </span>
      <div>
        <strong>{step.label}</strong>
        {#if step.hint}<small>{step.hint}</small>{/if}
      </div>
    </li>
  {/each}
</ol>

<style>
  .b2s-steps {
    list-style: none;
    margin: 0;
    padding: 0 0 24px;
    display: grid;
    grid-template-columns: repeat(var(--b2s-steps-count), 1fr);
    gap: 26px;
  }

  .b2s-steps li {
    position: relative;
    display: grid;
    grid-template-columns: 40px 1fr;
    align-items: center;
    gap: 12px;
    color: #2d4168;
  }

  .b2s-steps li:not(:last-child)::after {
    content: '';
    position: absolute;
    top: 20px;
    left: calc(100% + 2px);
    width: 24px;
    height: 1px;
    background: #cfd9eb;
  }

  .b2s-steps span {
    width: 40px;
    height: 40px;
    border: 1px solid #cdd8ec;
    border-radius: 999px;
    display: grid;
    place-items: center;
    color: #304a78;
    background: #fff;
    font-weight: 700;
  }

  .b2s-steps .active span,
  .b2s-steps .done span {
    border-color: #216be8;
    color: #fff;
    background: #216be8;
    box-shadow: 0 10px 22px rgba(33, 107, 232, 0.24);
  }

  .b2s-steps strong {
    display: block;
    font-size: 13px;
    font-weight: 700;
    color: #0d214f;
  }

  .b2s-steps small {
    display: block;
    margin-top: 2px;
    font-size: 12px;
    color: #52688f;
  }

  @media (max-width: 760px) {
    .b2s-steps {
      grid-template-columns: 1fr;
      gap: 10px;
    }

    .b2s-steps li:not(:last-child)::after {
      display: none;
    }
  }
</style>
