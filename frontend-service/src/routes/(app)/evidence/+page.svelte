<script lang="ts">
  /**
   * Evidence Center (administrators): the audit exports that already exist, in one place. Nothing is built here:
   * - the evidence pack of the platform or a zone (ZIP built by core-service, SHA-256 of each file);
   * - the evidence of each access review campaign (exported from its page);
   * - the evidence pack of one folder (its sheet in Storage Roots);
   * - the reports to print or save as PDF: listed once, by Insights & Recommendations (a link here).
   */
  import { onMount } from 'svelte';
  import { apiGetData } from '$lib/api/client';
  import EvidencePackDialog from '$lib/components/observability/EvidencePackDialog.svelte';
  import RelativeTime from '$lib/components/ui/RelativeTime.svelte';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import { t } from '$lib/i18n';
  import { governanceEnabled } from '$lib/utils/features';

  type Review = { id: number; name: string; status: 'open' | 'closed'; closed_at: string | null; created_at: string; total: number; decided: number };

  let packOpen = $state(false);
  let reviews = $state<Review[] | null>(null);

  onMount(async () => {
    const campaigns = $governanceEnabled ? await apiGetData<Review[]>(fetch, '/access-reviews').catch(() => [] as Review[]) : [];
    // Closed campaigns first: their export is final
    reviews = [...campaigns].sort((a, b) => Number(a.status === 'open') - Number(b.status === 'open') || String(b.closed_at ?? b.created_at).localeCompare(String(a.closed_at ?? a.created_at)));
  });
</script>

<svelte:head><title>Evidence Center · BornToShare</title></svelte:head>

<section class="v2 ev">
  <div class="v2-head">
    <div>
      <h1>Evidence Center</h1>
      <p>{t('The audit evidence of BornToShare: what was asked, decided and applied, exported with its fingerprints.')}</p>
    </div>
  </div>

  <div class="v2-cols2">
    <div class="v2-sec">
      <div class="v2-sh"><h2>{t('Audit evidence pack')}</h2></div>
      <p class="v2-hint">{t('A ZIP of CSV files with the SHA-256 of each file: audit log, requests, review decisions.')}</p>
      <div><button type="button" class="b2s-btn b2s-btn-primary" onclick={() => (packOpen = true)}>
        <i class="bi bi-file-earmark-zip" aria-hidden="true"></i>{t('Choose the period and the scope')}
      </button></div>
      <p class="v2-hint">{t('For one folder: its sheet in Storage Roots › … › Audit evidence pack.')} <a href="/storage-roots">Storage Roots</a></p>
    </div>

    <div class="v2-sec">
      <div class="v2-sh"><h2>{t('Reports to print')}</h2></div>
      <p class="v2-hint">{t('Storage, security, access and 5S reports, to print or save as PDF: they are listed with the recommendations.')}</p>
      <div><a class="b2s-btn b2s-btn-secondary" href="/reports#reports"><i class="bi bi-printer" aria-hidden="true"></i>{t('Open the reports')}</a></div>
    </div>

    {#if $governanceEnabled}
      <div class="v2-sec">
        <div class="v2-sh"><h2>{t('Access reviews')}</h2>{#if reviews?.length}<span class="v2-tag is-mut">{reviews.length}</span>{/if}
          <div class="v2-sh__r"><a href="/access-reviews">{t('See all')}</a></div></div>
        <p class="v2-hint">{t('The export of a campaign (who decided what, when, and the result) is its evidence: from its page.')}</p>
        {#if reviews === null}
          <LoadingState block skeleton="rows">{t('Loading…')}</LoadingState>
        {:else if reviews.length}
          <ul class="v2-feed">
            {#each reviews.slice(0, 10) as review (review.id)}
              <li><a class="v2-fi" href={`/access-reviews/${review.id}`}>
                <div class="v2-fi__t"><b>{review.name}</b><small>{t('{decided} decision(s) out of {total}', { decided: review.decided, total: review.total })}</small></div>
                <span class="v2-fi__r">
                  <span class={`v2-tag is-${review.status === 'closed' ? 'ok' : 'warn'}`}>{review.status === 'closed' ? t('Closed') : t('In progress')}</span>
                  <small><RelativeTime value={review.closed_at ?? review.created_at} /></small>
                </span>
              </a></li>
            {/each}
          </ul>
        {:else}
          <p class="v2-empty">{t('No review campaign yet.')}</p>
        {/if}
      </div>
    {/if}
  </div>
</section>

<EvidencePackDialog open={packOpen} onClose={() => (packOpen = false)} />
