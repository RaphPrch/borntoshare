<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { fly } from 'svelte/transition';
  import { t } from '$lib/i18n';
  import { recall, remember } from '$lib/utils/remember';
  import { downloadCsv } from '$lib/utils/csv';
  import { toast } from '$lib/stores/toast';
  import { dur, MOTION } from '$lib/utils/motion';
  import { applyPilotAction, askPilot, pilotExamples, type PilotAnswer, type PilotCell } from '$lib/components/pilot/pilot-engine';
  import { fivesEnabled } from '$lib/utils/features';

  /**
   * Raphaël (formerly Pilot): ask a question on the folders in plain French, get the answer as a list ready to export.
   * The answers are read from the data BornToShare already holds. A change (« ajoute le tag … ») is listed first and
   * applied only on « Appliquer », by an administrator.
   */
  const isAdmin = $derived(Boolean(($page.data as { me?: { is_admin?: boolean } }).me?.is_admin));
  // Per answer: the result of its action once applied
  let applied = $state<Record<number, { done: number; failed: string[] } | 'busy'>>({});
  let draft = $state('');
  let busy = $state(false);
  let answers = $state<PilotAnswer[]>([]);
  // The last questions, kept in this browser (asked again on a click: the data may have moved since)
  let history = $state<string[]>((recall('pilot', { history: [] as string[] }).history as string[]) ?? []);
  const PREVIEW = 12;
  // Shown at most once unfolded: a list of thousands of accesses stays readable, the export holds every line
  const SHOWN_MAX = 500;
  let examples = $derived(pilotExamples($fivesEnabled));
  let expanded = $state<Record<number, boolean>>({});

  async function ask(question: string) {
    const text = question.trim();
    if (!text || busy) return;
    busy = true;
    try {
      const answer = await askPilot(fetch, text, { fives: $fivesEnabled });
      answers = [answer, ...answers].slice(0, 6);
      expanded = {};
      applied = {};
      history = [text, ...history.filter((item) => item !== text)].slice(0, 8);
      remember('pilot', { history });
      draft = '';
    } catch (failure) {
      toast.error(failure instanceof Error ? failure.message : t('Unable to answer.'));
    } finally {
      busy = false;
    }
  }

  function exportCsv(answer: PilotAnswer) {
    if (!answer.file) return;
    downloadCsv(answer.file, answer.columns.map((header, index) => ({ header, value: (row: PilotCell[]) => row[index]?.text ?? '' })), answer.rows);
    toast.success(t('{file} downloaded: {count} line(s).', { file: answer.file, count: answer.rows.length }));
  }

  async function apply(answer: PilotAnswer, index: number) {
    if (!answer.action || applied[index]) return;
    applied = { ...applied, [index]: 'busy' };
    const result = await applyPilotAction(fetch, answer.action);
    applied = { ...applied, [index]: result };
    if (result.failed.length) toast.error(t('{done} folder(s) changed, {failed} refused: {reason}', { done: result.done, failed: result.failed.length, reason: result.failed[0] }));
    else toast.success(t('{count} folder(s) changed.', { count: result.done }));
  }

  async function copyRows(answer: PilotAnswer) {
    const lines = [answer.columns.join('\t'), ...answer.rows.map((row) => row.map((cell) => cell.text).join('\t'))];
    await navigator.clipboard?.writeText(lines.join('\n')).catch(() => null);
    toast.success(t('Copied: paste it in Excel or an e-mail.'));
  }

  // /pilot?q=… (from the dashboard): asked at once
  onMount(() => {
    const q = $page.url.searchParams.get('q');
    if (q) void ask(q);
  });
  const grid = (count: number) => `minmax(180px, 1.5fr) repeat(${Math.max(1, count - 1)}, minmax(0, 1fr))`;
</script>

<section class="v2 pl">
  <div class="pl-hero">
    <span class="pl-kick">Workspace</span>
    <h1>Raphaël</h1>
    <p>{t('Ask a question on your folders, the people who reach them, their measures: the answer comes as a list, ready to export. Ask for a tag to be put or taken off: the folders are listed first, nothing changes before « Apply ».')}</p>
    <form class="pl-ask" onsubmit={(event) => { event.preventDefault(); void ask(draft); }}>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="7"></circle><path d="m20 20-3.5-3.5"></path></svg>
      <input type="text" bind:value={draft} placeholder={t('Export all the users of the folder Finance…')} aria-label={t('Your question')} disabled={busy} />
      <button type="submit" class="b2s-btn b2s-btn-primary" disabled={busy || !draft.trim()}>{busy ? t('Searching…') : t('Ask')}</button>
    </form>
    <div class="pl-sugs">
      {#each examples as example (example)}<button type="button" class="pl-sug" onclick={() => ask(example)} disabled={busy}>{example}</button>{/each}
    </div>
  </div>

  {#each answers as answer, index (answer.question + index)}
    <article class="pl-ans" class:is-ko={!answer.ok} in:fly={{ y: 10, duration: dur(MOTION.base) }}>
      <header class="pl-ans__h">
        <b>{answer.question}</b>
        <span class="pl-int" title={t('How the question was understood')}>{answer.intent}</span>
        {#if answer.source}<span class="pl-src">{answer.source}</span>{/if}
      </header>
      <p>{answer.text}</p>
      {#if answer.rows.length}
        <div class="pl-table" role="table" aria-label={answer.question}>
          <div class="pl-row is-head" role="row" style={`grid-template-columns: ${grid(answer.columns.length)}`}>{#each answer.columns as column (column)}<span>{column}</span>{/each}</div>
          {#each answer.rows.slice(0, expanded[index] ? SHOWN_MAX : PREVIEW) as row, r (r)}
            <div class="pl-row" role="row" style={`grid-template-columns: ${grid(answer.columns.length)}`}>
              {#each row as cell, c (c)}<span class:mono={cell.mono} class={cell.tone ? `v2-tag is-${cell.tone}` : ''}>{cell.text}</span>{/each}
            </div>
          {/each}
        </div>
        {#if answer.rows.length > PREVIEW && !expanded[index]}
          <button type="button" class="b2s-link-btn" onclick={() => (expanded = { ...expanded, [index]: true })}>{t('Show the {count} other line(s)', { count: Math.min(answer.rows.length, SHOWN_MAX) - PREVIEW })}</button>
        {:else if expanded[index] && answer.rows.length > SHOWN_MAX}
          <p class="pl-more">{t('The first {shown} lines are shown; the export holds all {count}.', { shown: SHOWN_MAX, count: answer.rows.length })}</p>
        {/if}
      {/if}
      {#if answer.action}
        {@const state = applied[index]}
        <div class="pl-act" class:is-done={state && state !== 'busy'}>
          <i class={`bi ${answer.action.kind === 'tag-add' ? 'bi-tag' : 'bi-tag-fill'}`} aria-hidden="true"></i>
          {#if state && state !== 'busy'}
            <span>{t('Done: {done} folder(s) changed.', { done: state.done })}{state.failed.length ? ` ${t('{count} refused.', { count: state.failed.length })}` : ''}</span>
          {:else if isAdmin}
            <span>{answer.action.kind === 'tag-add' ? t('Put the tag « {tag} » on {count} folder(s)?', { tag: answer.action.tagName, count: answer.action.rootIds.length }) : t('Take the tag « {tag} » off {count} folder(s)?', { tag: answer.action.tagName, count: answer.action.rootIds.length })}</span>
            <button type="button" class="b2s-btn b2s-btn-primary b2s-btn-sm" onclick={() => apply(answer, index)} disabled={state === 'busy'}>{state === 'busy' ? t('Applying…') : t('Apply')}</button>
          {:else}
            <span>{t('Only an administrator can apply this change.')}</span>
          {/if}
        </div>
      {/if}
      <div class="pl-acts">
        {#if answer.file}
          <button type="button" class="b2s-btn b2s-btn-primary b2s-btn-sm" onclick={() => exportCsv(answer)}><i class="bi bi-download" aria-hidden="true"></i>{t('Export CSV ({count} lines)', { count: answer.rows.length })}</button>
          <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" onclick={() => copyRows(answer)}><i class="bi bi-clipboard" aria-hidden="true"></i>{t('Copy')}</button>
        {/if}
        {#each answer.links as link (link.href)}<a class="b2s-btn b2s-btn-secondary b2s-btn-sm" href={link.href}><i class="bi bi-folder2-open" aria-hidden="true"></i>{link.label}</a>{/each}
        <button type="button" class="b2s-btn b2s-btn-ghost b2s-btn-sm" onclick={() => ask(answer.question)} disabled={busy}><i class="bi bi-arrow-clockwise" aria-hidden="true"></i>{t('Ask the question again')}</button>
      </div>
    </article>
  {/each}

  {#if history.length}
    <div class="v2-sec">
      <div class="v2-sh"><h2>{t('Recent questions')}</h2><div class="v2-sh__r"><button type="button" class="b2s-link-btn" onclick={() => { history = []; remember('pilot', { history: [] }); }}>{t('Clear')}</button></div></div>
      <div class="pl-sugs">{#each history as item (item)}<button type="button" class="pl-sug is-hist" onclick={() => ask(item)} disabled={busy}><i class="bi bi-clock-history" aria-hidden="true"></i>{item}</button>{/each}</div>
    </div>
  {/if}
</section>

<style>
  .pl-hero { display: flex; flex-direction: column; gap: 14px; padding: 28px; border-radius: 22px; background: var(--b2s-color-surface-soft); }
  .pl-kick { color: var(--b2s-accent-strong); font-size: 12px; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; }
  .pl-hero h1 { margin: 0; font-size: 52px; font-weight: 700; letter-spacing: -0.045em; line-height: 1; }
  .pl-hero p { margin: 0; color: var(--b2s-color-text-muted); font-size: 16px; line-height: 1.55; }
  .pl-more { margin: 0; color: var(--b2s-color-text-muted); font-size: 13px; }
  .pl-ask { display: flex; align-items: center; gap: 10px; min-height: 58px; padding: 6px 6px 6px 18px; border: 1px solid var(--b2s-color-border-soft); border-radius: 16px; background: #fff; color: var(--b2s-color-text-muted); }
  .pl-ask:focus-within { border-color: var(--b2s-accent-strong); box-shadow: 0 0 0 3px rgba(18, 59, 73, 0.1); }
  .pl-ask input { flex: 1; border: 0; outline: 0; background: transparent; color: var(--b2s-color-text); font: inherit; font-size: 17px; }
  .pl-sugs { display: flex; flex-wrap: wrap; gap: 8px; }
  .pl-sug { display: inline-flex; align-items: center; gap: 6px; min-height: 34px; padding: 0 14px; border: 1px solid var(--b2s-color-border-soft); border-radius: 999px; background: #fff; color: var(--b2s-color-text); font: inherit; font-size: 13px; cursor: pointer; }
  .pl-sug:hover:not([disabled]) { border-color: var(--b2s-accent-strong); color: var(--b2s-accent-strong); }
  .pl-sug.is-hist { color: var(--b2s-color-text-muted); }
  .pl-ans { display: flex; flex-direction: column; gap: 12px; padding: 20px 22px; border: 1px solid var(--b2s-color-border-soft); border-radius: 20px; background: #fff; }
  .pl-ans.is-ko { background: var(--b2s-color-surface-soft); }
  .pl-ans__h { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
  .pl-ans__h b { font-size: 16px; }
  .pl-int { padding: 3px 9px; border-radius: 7px; background: var(--b2s-topbar-bg); color: #fff; font-family: var(--b2s-font-mono); font-size: 12px; }
  .pl-src { margin-left: auto; color: var(--b2s-color-text-muted); font-size: 12.5px; }
  .pl-ans p { margin: 0; color: var(--b2s-color-text-soft); line-height: 1.55; }
  .pl-table { overflow-x: auto; border: 1px solid var(--b2s-color-border-soft); border-radius: 14px; }
  .pl-row { display: grid; gap: 14px; align-items: center; min-width: 680px; padding: 9px 16px; border-bottom: 1px solid var(--b2s-color-surface-muted); }
  .pl-row:last-child { border-bottom: 0; }
  .pl-row.is-head { background: var(--b2s-color-surface-soft); color: var(--b2s-color-text-muted); font-size: 11.5px; font-weight: 600; letter-spacing: 0.03em; text-transform: uppercase; }
  .pl-row span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .pl-row span.v2-tag { justify-self: start; }
  .mono { font-family: var(--b2s-font-mono); font-size: 12px; color: var(--b2s-color-text-muted); }
  .pl-act { display: flex; align-items: center; gap: 12px; padding: 12px 16px; border: 1px solid var(--b2s-color-border-soft); border-radius: 14px; background: var(--b2s-accent-soft); }
  .pl-act span { flex: 1; font-weight: 500; }
  .pl-act.is-done { background: var(--b2s-color-success-soft); border-color: var(--b2s-color-success-border); }
  .pl-acts { display: flex; flex-wrap: wrap; gap: 8px; }
</style>
