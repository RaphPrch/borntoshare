<script lang="ts">
  import { t } from '$lib/i18n';
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';

  onMount(() => {
    goto('/dashboard');
  });
</script>

<div class="d-flex align-items-center justify-content-center" style="height: 100vh;">
  <div class="text-center">
    <div class="spinner-border text-primary mb-3"></div>
    <div class="text-muted">{t('Loading your workspace…')}</div>
  </div>
</div>
