<script lang="ts">
  import { t } from '$lib/i18n';
  interface Props {
    label?: any;
    tone?: 'default' | 'empty';
  }

  let { label = t('Loading storage root data…'), tone = 'default' }: Props = $props();
</script>

<div class={`sr-clean-empty-inline ${tone === 'empty' ? 'is-empty' : ''}`} role="status" aria-live="polite">{label}</div>
