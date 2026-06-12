<script lang="ts">
  export let open = false;
  export let title = "Preview changes";
  export let items: string[] = [];
  export let onClose: (() => void) | null = null;
</script>

{#if open}
  <div class="modal d-block" tabindex="-1" role="dialog" aria-modal="true">
    <div class="modal-dialog modal-lg modal-dialog-centered" role="document">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title">{title}</h5>
          <button type="button" class="btn-close" aria-label="Close" on:click={() => onClose?.()}></button>
        </div>
        <div class="modal-body">
          <p class="text-muted mb-3">Plan/Apply preview skeleton (V2-ready)</p>
          <ul class="mb-0">
            {#if items.length === 0}
              <li>No staged changes.</li>
            {:else}
              {#each items as item}
                <li>{item}</li>
              {/each}
            {/if}
          </ul>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-outline-secondary" on:click={() => onClose?.()}>Close</button>
        </div>
      </div>
    </div>
  </div>
  <div class="modal-backdrop show"></div>
{/if}

