<script lang="ts">
  import { fly, fade } from "svelte/transition";
  import { toasts } from "$lib/stores/toast";

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
  {#each $toasts as t (t.id)}
    <div
      class="toast show shadow-sm {cls(t.type)}"
      role="alert"
      in:fly={{ y: 10, duration: 150 }}
      out:fade={{ duration: 150 }}
    >
      <div class="d-flex align-items-start">
        <div class="toast-body d-flex align-items-center gap-2">
          <i class="bi {icon(t.type)}"></i>
          <span>{t.message}</span>
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
    border-radius: 10px;
  }

  /* Override bootstrap-ish toast variants for dark topbar context */
  :global(.b2s-toaster .toast.text-bg-danger) {
    background: #dc2626;
    color: #ffffff;
    border: 1px solid #991b1b;
  }

  :global(.b2s-toaster .toast.text-bg-danger .toast-body),
  :global(.b2s-toaster .toast.text-bg-danger i) {
    color: #ffffff;
  }

  :global(.b2s-toaster .toast.text-bg-warning) {
    background: #f59e0b;
    color: #111827;
    border: 1px solid #b45309;
  }

  :global(.b2s-toaster .toast.text-bg-success) {
    background: #16a34a;
    color: #ffffff;
    border: 1px solid #166534;
  }

  :global(.b2s-toaster .toast.text-bg-secondary) {
    background: #334155;
    color: #ffffff;
    border: 1px solid #1f2937;
  }
</style>
