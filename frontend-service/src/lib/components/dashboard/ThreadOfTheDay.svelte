<script lang="ts">
  import { t } from '$lib/i18n';
  import { formatActivityItem } from '$lib/activity/format';
  import { formatTime, timeAgo } from '$lib/utils/format';

  /**
   * « Thread of the day » of a dashboard: the latest events already chosen for the profile (administrator: the
   * problems of the platform; guardian: tasks and guarded folders; user: their access requests), newest first.
   */
  interface Props {
    events: Record<string, any>[];
    /** Where « See all » leads (nothing: no link) */
    seeAll?: string | null;
    empty: string;
    max?: number;
  }

  let { events, seeAll = null, empty, max = 10 }: Props = $props();

  let shown = $derived(events.slice(0, max));
  const clock = (value: unknown) => {
    const date = new Date(String(value ?? ''));
    if (Number.isNaN(date.getTime())) return '—';
    return date.toDateString() === new Date().toDateString() ? formatTime(date) : timeAgo(value as string);
  };
  const who = (event: Record<string, any>) =>
    String(event.actor_display_name ?? event.actor_display ?? (event.actor_type === 'system' ? t('System') : event.actor_id ?? '—'));
  const failed = (event: Record<string, any>) => /fail|error|denied|refus/i.test(String(event.outcome ?? '') + String(event.action ?? ''));
</script>

<h2 class="tod__h">{t('Thread of the day')}{#if seeAll}<a class="b2s-link-btn" href={seeAll}>{t('See all')}</a>{/if}</h2>
<ol class="tod">
  {#each shown as event, index (event.id ?? index)}
    {@const rendered = formatActivityItem(event as any)}
    <li class="tod__ev" class:is-bad={failed(event)}>
      <small>{clock(event.created_at)}</small>
      <span class="tod__txt" title={rendered.subtitle1 ?? undefined}><b>{rendered.title ?? t('Event')}</b> · {who(event)}{rendered.subtitle1 ? ` · ${rendered.subtitle1}` : ''}</span>
    </li>
  {:else}
    <li class="tod__ev tod__ev--empty"><span>{empty}</span></li>
  {/each}
</ol>

<style>
  .tod__h { display: flex; align-items: baseline; gap: 12px; margin: 0 0 10px; color: var(--b2s-color-heading); font-size: 18px; font-weight: 700; letter-spacing: -0.025em; }
  .tod__h :global(.b2s-link-btn) { margin-left: auto; font-size: 13px; letter-spacing: 0; }
  .tod { position: relative; display: flex; flex-direction: column; margin: 8px 0 0; padding: 0 0 0 22px; list-style: none; }
  .tod::before { content: ''; position: absolute; left: 5px; top: 6px; bottom: 6px; width: 1px; background: var(--b2s-color-border-soft); }
  .tod__ev { position: relative; padding: 0 0 16px; line-height: 1.45; }
  .tod__ev::before { content: ''; position: absolute; left: -21px; top: 6px; width: 9px; height: 9px; border: 2px solid var(--b2s-accent); border-radius: 50%; background: var(--b2s-color-surface); }
  .tod__ev.is-bad::before { border-color: var(--b2s-color-danger); background: var(--b2s-color-danger); }
  .tod__ev--empty::before { border-color: var(--b2s-color-border); }
  .tod__ev small { display: block; color: var(--b2s-color-text-muted); font-size: 12px; font-weight: 700; }
  .tod__ev b { font-weight: 600; }
  /* Raw error messages can be long: three lines, the whole text on hover */
  .tod__txt { display: -webkit-box; overflow: hidden; -webkit-box-orient: vertical; -webkit-line-clamp: 3; line-clamp: 3; overflow-wrap: anywhere; }
</style>
