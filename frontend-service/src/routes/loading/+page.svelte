<script lang="ts">
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import { t } from '$lib/i18n';
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';

  onMount(() => {
    goto('/dashboard');
  });
</script>

<div class="d-flex align-items-center justify-content-center" style="height: 100vh;">
  <div class="text-center">
    <LoadingState block>{t('Loading your workspace…')}</LoadingState>
  </div>
</div>
