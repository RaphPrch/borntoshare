<script lang="ts">
  import AppModal from '$lib/components/ui/AppModal.svelte';
  import WizardSteps, { type WizardStep } from '$lib/components/ui/WizardSteps.svelte';

  /**
   * Shell shared by every wizard: fixed-size modal (the size never changes between steps),
   * standard header, step indicator, scrolling body and a sticky footer.
   * Slots: default (current step), "footer-start" (hint / state), "footer" (Cancel, Back, Continue / Create).
   */
  export let open = false;
  export let onClose: () => void;
  export let title: string;
  export let subtitle: string | null = null;
  export let iconClass: string | null = null;
  export let steps: WizardStep[] = [];
  export let current = 1;
  export let ariaLabelledby = 'b2s-wizard-title';
  export let closeOnBackdrop = false;
  /** Body without padding nor global scroll: the step content lays out its own columns */
  export let flush = false;
</script>

<AppModal
  {open}
  {onClose}
  size="xl"
  {title}
  {subtitle}
  {iconClass}
  {ariaLabelledby}
  {closeOnBackdrop}
  modalClass="b2s-modal b2s-wizard"
  contentClass={`b2s-modal-content b2s-wizard__body${flush ? ' is-flush' : ''}`}
>
  {#if steps.length > 1}
    <div class="b2s-wizard__steps">
      <WizardSteps {steps} {current} />
    </div>
  {/if}
  <slot />

  <svelte:fragment slot="footer-start"><slot name="footer-start" /></svelte:fragment>
  <svelte:fragment slot="footer"><slot name="footer" /></svelte:fragment>
</AppModal>
