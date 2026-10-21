<script lang="ts">
  import { t } from '$lib/i18n';
  export let label = t('Loading storage root data…');
  export let tone: 'default' | 'empty' = 'default';
</script>

<div class={`sr-clean-empty-inline ${tone === 'empty' ? 'is-empty' : ''}`} role="status" aria-live="polite">{label}</div>
