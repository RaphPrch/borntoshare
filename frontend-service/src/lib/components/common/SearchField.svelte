<script lang="ts">
  export let value = "";
  export let placeholder = "Search";
  export let ariaLabel = "Search";
  export let wrapperClass = "";
  export let inputClass = "";
  export let disabled = false;
  export let onChange: ((next: string) => void) | null = null;
  export let onEnter: ((value: string) => void) | null = null;
</script>

<label class={`b2s-search-field ${wrapperClass}`.trim()}>
  <i class="bi bi-search" aria-hidden="true"></i>
  <input
    class={inputClass}
    type="text"
    {placeholder}
    aria-label={ariaLabel}
    {disabled}
    bind:value
    on:input={() => onChange?.(value)}
    on:keydown={(event) => {
      if (event.key === 'Enter') {
        onEnter?.(value);
      }
    }}
  />
</label>

<style>
  .b2s-search-field {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    border: 1px solid var(--b2s-search-border, var(--b2s-color-border, #d8e1ec));
    border-radius: var(--b2s-search-radius, 10px);
    padding: var(--b2s-search-padding, 0.5rem 0.65rem);
    background: var(--b2s-search-bg, #fff);
    color: var(--b2s-search-color, inherit);
  }

  .b2s-search-field i {
    color: var(--b2s-search-icon-color, var(--b2s-color-text-muted, #64748b));
    font-size: 0.92rem;
  }

  .b2s-search-field input {
    border: none;
    outline: none;
    width: 100%;
    min-width: 0;
    background: transparent;
    font: inherit;
    color: inherit;
  }

  .b2s-search-field input::placeholder {
    color: var(--b2s-search-placeholder, var(--b2s-color-text-muted, #64748b));
  }

  .b2s-search-field input:disabled {
    cursor: not-allowed;
    opacity: 0.72;
  }

  .b2s-search-field:focus-within {
    border-color: var(--b2s-search-focus-border, var(--b2s-color-primary, #2563eb));
    box-shadow: var(--b2s-search-focus-ring, 0 0 0 3px rgba(59, 130, 246, 0.12));
  }
</style>
