<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import EmptyState from '$lib/components/ui/EmptyState.svelte';
  import { t } from '$lib/i18n';

  /**
   * A 5S screen while the module is not usable: why (known on the server for an administrator), and for an
   * administrator the way to the modules and licenses. No call to the module is made behind it.
   */
  let { reason = 'unknown' }: { reason?: 'license' | 'switched_off' | 'unreachable' | 'unknown' | string } = $props();

  let admin = $derived(($page.data as { me?: { is_admin?: boolean } }).me?.is_admin === true);
  const REASONS: Record<string, () => string> = {
    license: () => t('No valid license opens it: add a license key, or renew the one that expired.'),
    switched_off: () => t('It is licensed but switched off.'),
    unreachable: () => t('It is switched on but does not answer: check that its container runs and that its databases were installed.'),
    unknown: () => t('An administrator opens it with a license key and switches it on.')
  };
</script>

<section class="fs-off">
  <EmptyState page iconClass="bi bi-stars" title={t('The 5S module is not active')}
    description={admin ? (REASONS[reason] ?? REASONS.unknown)() : t('Ask an administrator of BornToShare to switch it on.')}
    ctaLabel={admin ? t('Open the modules and licenses') : null}
    onCta={admin ? () => void goto('/admin/advanced-settings/features') : null} />
</section>

<style>
  .fs-off { padding: var(--b2s-page-padding); }
</style>
