<script lang="ts">
  export let infoText: string | null = null;
  export let showInfoDot = false;
  export let align = 'between';
  export let className = '';
</script>

<div class={`b2s-action-footer ${align === 'end' ? 'is-end' : ''} ${className}`.trim()}>
  <div class="b2s-action-footer__info" aria-live="polite">
    {#if infoText}
      {#if showInfoDot}
        <span class="b2s-action-footer__dot" aria-hidden="true"></span>
      {/if}
      <span>{infoText}</span>
    {/if}
  </div>

  <div class="b2s-action-footer__actions">
    <slot />
  </div>
</div>

<style>
  .b2s-action-footer {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }

  .b2s-action-footer.is-end {
    justify-content: flex-end;
  }

  .b2s-action-footer__info {
    min-height: 20px;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    color: #9a6a05;
    font-size: 13px;
    font-weight: 600;
  }

  .b2s-action-footer__dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #d8a439;
  }

  .b2s-action-footer__actions {
    margin-left: auto;
    display: inline-flex;
    align-items: center;
    gap: 10px;
  }

  @media (max-width: 760px) {
    .b2s-action-footer {
      flex-direction: column;
      align-items: stretch;
    }

    .b2s-action-footer__actions {
      margin-left: 0;
      width: 100%;
      display: grid;
      grid-template-columns: 1fr 1fr;
    }
  }
</style>

