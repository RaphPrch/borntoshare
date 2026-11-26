<script lang="ts">
  /**
   * Insights & Recommendations › Recommendations: what the last measures, scans and ACL reads of the folders reveal,
   * each counted by the express search of Storage Roots that lists its folders (one click away).
   */
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { apiGetList } from '$lib/api/client';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import InsightCards from '$lib/components/insights/InsightCards.svelte';
  import { t } from '$lib/i18n';
  import { governanceEnabled } from '$lib/utils/features';
  import { INSIGHT_FIELDS, buildInsights } from '$lib/utils/insights';

  let roots = $state<Record<string, any>[] | null>(null);
  let isAdmin = $derived(($page.data as any)?.navigation?.canSeeAdmin === true);
  onMount(async () => {
    // Only the columns the recommendations read: the whole folder list weighs megabytes
    roots = await apiGetList<Record<string, any>>(fetch, '/storage-roots/context', { fields: INSIGHT_FIELDS }).catch(() => []);
  });
  let insights = $derived(roots ? buildInsights(roots, $governanceEnabled) : []);
</script>

<svelte:head><title>Recommendations · BornToShare</title></svelte:head>

<section class="v2">
  <div class="v2-head">
    <div>
      <h1>Recommendations</h1>
      <p>{t('What the last measures, scans and ACL reads of the folders you may see reveal, with the folders concerned.')}</p>
    </div>
  </div>
  <div class="v2-sec">
    <div class="v2-sh"><h2>{t('Recommendations')}</h2>{#if insights.length}<span class="v2-tag is-mut">{insights.length}</span>{/if}
      <div class="v2-sh__r"><span class="v2-hint">{t('Click: the folders concerned · right click: actions')}</span></div></div>
    {#if !roots}
      <LoadingState block skeleton="rows" rows={4} />
    {:else if insights.length}
      <InsightCards {insights} total={roots.length} {isAdmin} />
    {:else}
      <p class="v2-empty">{t('Nothing to recommend')} · {t('The folders are well kept, or not measured yet.')}</p>
    {/if}
  </div>
</section>
