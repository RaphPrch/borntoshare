<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { fly } from 'svelte/transition';
  import { t } from '$lib/i18n';
  import { recall, remember } from '$lib/utils/remember';
  import { downloadCsv } from '$lib/utils/csv';
  import { toast } from '$lib/stores/toast';
  import { dur, MOTION } from '$lib/utils/motion';
  import { askPilot, PILOT_EXAMPLES, type PilotAnswer, type PilotCell } from '$lib/components/pilot/pilot-engine';

  /**
   * Pilot: ask a question on the folders in plain French, get the answer as a list ready to export.
   * The answers are read from the data BornToShare already holds; nothing is changed from here.
   */
  let draft = $state('');
  let busy = $state(false);
  let answers = $state<PilotAnswer[]>([]);
  // The last questions, kept in this browser (asked again on a click: the data may have moved since)
  let history = $state<string[]>((recall('pilot', { history: [] as string[] }).history as string[]) ?? []);
  const PREVIEW = 12;
  let expanded = $state<Record<number, boolean>>({});

  async function ask(question: string) {
    const text = question.trim();
    if (!text || busy) return;
    busy = true;
    try {
      const answer = await askPilot(fetch, text);
      answers = [answer, ...answers].slice(0, 6);
      expanded = {};
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
    <h1>Pilot</h1>
    <p>{t('Ask a question on your folders, the people who reach them, their measures: the answer comes as a list, ready to export. Nothing is changed from here.')}</p>
    <form class="pl-ask" onsubmit={(event) => { event.preventDefault(); void ask(draft); }}>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="7"></circle><path d="m20 20-3.5-3.5"></path></svg>
      <input type="text" bind:value={draft} placeholder={t('Export all the users of the folder Finance…')} aria-label={t('Your question')} disabled={busy} />
      <button type="submit" class="b2s-btn b2s-btn-primary" disabled={busy || !draft.trim()}>{busy ? t('Searching…') : t('Ask')}</button>
    </form>
    <div class="pl-sugs">
      {#each PILOT_EXAMPLES as example (example)}<button type="button" class="pl-sug" onclick={() => ask(example)} disabled={busy}>{example}</button>{/each}
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
          {#each answer.rows.slice(0, expanded[index] ? answer.rows.length : PREVIEW) as row, r (r)}
            <div class="pl-row" role="row" style={`grid-template-columns: ${grid(answer.columns.length)}`}>
              {#each row as cell, c (c)}<span class:mono={cell.mono} class={cell.tone ? `v2-tag is-${cell.tone}` : ''}>{cell.text}</span>{/each}
            </div>
          {/each}
        </div>
        {#if answer.rows.length > PREVIEW && !expanded[index]}
          <button type="button" class="b2s-link-btn" onclick={() => (expanded = { ...expanded, [index]: true })}>{t('Show the {count} other line(s)', { count: answer.rows.length - PREVIEW })}</button>
        {/if}
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
  .pl { max-width: 1180px; }
  .pl-hero { display: flex; flex-direction: column; gap: 14px; padding: 28px; border-radius: 22px; background: var(--b2s-color-surface-soft); }
  .pl-kick { color: var(--b2s-accent-strong); font-size: 12px; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; }
  .pl-hero h1 { margin: 0; font-size: 52px; font-weight: 700; letter-spacing: -0.045em; line-height: 1; }
  .pl-hero p { margin: 0; max-width: 760px; color: var(--b2s-color-text-muted); font-size: 16px; line-height: 1.55; }
  .pl-ask { display: flex; align-items: center; gap: 10px; min-height: 58px; padding: 6px 6px 6px 18px; border: 1px solid var(--b2s-color-border-soft); border-radius: 16px; background: #fff; color: var(--b2s-color-text-muted); }
  .pl-ask:focus-within { border-color: var(--b2s-accent-strong); box-shadow: 0 0 0 3px rgba(14, 18, 24, 0.1); }
  .pl-ask input { flex: 1; border: 0; outline: 0; background: transparent; color: var(--b2s-color-text); font: inherit; font-size: 17px; }
  .pl-sugs { display: flex; flex-wrap: wrap; gap: 8px; }
  .pl-sug { display: inline-flex; align-items: center; gap: 6px; min-height: 34px; padding: 0 14px; border: 1px solid var(--b2s-color-border-soft); border-radius: 999px; background: #fff; color: var(--b2s-color-text); font: inherit; font-size: 13px; cursor: pointer; }
  .pl-sug:hover:not([disabled]) { border-color: var(--b2s-accent-strong); color: var(--b2s-accent-strong); }
  .pl-sug.is-hist { color: var(--b2s-color-text-muted); }
  .pl-ans { display: flex; flex-direction: column; gap: 12px; padding: 20px 22px; border: 1px solid var(--b2s-color-border-soft); border-radius: 20px; background: #fff; }
  .pl-ans.is-ko { background: var(--b2s-color-surface-soft); }
  .pl-ans__h { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
  .pl-ans__h b { font-size: 16px; }
  .pl-int { padding: 3px 9px; border-radius: 7px; background: #0e1218; color: #fff; font-family: var(--b2s-font-mono); font-size: 12px; }
  .pl-src { margin-left: auto; color: var(--b2s-color-text-muted); font-size: 12.5px; }
  .pl-ans p { margin: 0; color: #3f4755; line-height: 1.55; }
  .pl-table { overflow-x: auto; border: 1px solid var(--b2s-color-border-soft); border-radius: 14px; }
  .pl-row { display: grid; gap: 14px; align-items: center; min-width: 680px; padding: 9px 16px; border-bottom: 1px solid #f3f4f6; }
  .pl-row:last-child { border-bottom: 0; }
  .pl-row.is-head { background: #fafbfc; color: var(--b2s-color-text-muted); font-size: 11.5px; font-weight: 600; letter-spacing: 0.03em; text-transform: uppercase; }
  .pl-row span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .pl-row span.v2-tag { justify-self: start; }
  .mono { font-family: var(--b2s-font-mono); font-size: 12px; color: var(--b2s-color-text-muted); }
  .pl-acts { display: flex; flex-wrap: wrap; gap: 8px; }
</style>
