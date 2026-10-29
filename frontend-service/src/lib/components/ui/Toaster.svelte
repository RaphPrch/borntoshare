<script lang="ts">
  import { fly, fade } from "svelte/transition";
  import { toast } from "$lib/stores/toast";

  const icon = (type: string) => {
    switch (type) {
      case "success": return "bi-check-circle-fill";
      case "error": return "bi-x-circle-fill";
      case "warning": return "bi-exclamation-triangle-fill";
      default: return "bi-info-circle-fill";
    }
  };

  const cls = (type: string) => {
    switch (type) {
      case "success": return "text-bg-success";
      case "error": return "text-bg-danger";
      case "warning": return "text-bg-warning";
      default: return "text-bg-secondary";
    }
  };
</script>

<div class="b2s-toaster">
  {#each $toast as item (item.id)}
    <div
      class="toast show shadow-sm {cls(item.type)}"
      role="alert"
      in:fly={{ y: 10, duration: 150 }}
      out:fade={{ duration: 150 }}
    >
      <div class="d-flex align-items-start">
        <div class="toast-body d-flex align-items-center gap-2">
          <i class="bi {icon(item.type)}"></i>
          <span>{item.message}</span>
        </div>
      </div>
    </div>
  {/each}
</div>

<style>
  .b2s-toaster {
    position: fixed;
    top: 72px;
    right: 16px;
    z-index: 1080;
    display: flex;
    flex-direction: column;
    gap: 8px;
    max-width: 380px;
    pointer-events: none;
  }

  .toast {
    pointer-events: auto;
    border-radius: var(--b2s-radius-md);
  }

  /* Override bootstrap-ish toast variants for dark topbar context */
  :global(.b2s-toaster .toast.text-bg-danger) {
    background: var(--b2s-color-danger);
    color: #ffffff;
    border: 1px solid var(--b2s-color-danger-strong);
  }

  :global(.b2s-toaster .toast.text-bg-danger .toast-body),
  :global(.b2s-toaster .toast.text-bg-danger i) {
    color: #ffffff;
  }

  :global(.b2s-toaster .toast.text-bg-warning) {
    background: var(--b2s-color-warning);
    color: #111827;
    border: 1px solid var(--b2s-color-warning-strong);
  }

  :global(.b2s-toaster .toast.text-bg-success) {
    background: var(--b2s-color-success);
    color: #ffffff;
    border: 1px solid var(--b2s-color-success-strong);
  }

  :global(.b2s-toaster .toast.text-bg-secondary) {
    background: var(--b2s-color-text-strong);
    color: #ffffff;
    border: 1px solid #1f2937;
  }
</style>
