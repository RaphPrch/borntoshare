<script lang="ts">
  export let label = 'Loading storage root data…';
  export let tone: 'default' | 'empty' = 'default';
</script>

<div class={`sr-clean-empty-inline ${tone === 'empty' ? 'is-empty' : ''}`} role="status" aria-live="polite">{label}</div>
