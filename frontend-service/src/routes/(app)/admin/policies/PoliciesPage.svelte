<script lang="ts">
  import RelativeTime from '$lib/components/ui/RelativeTime.svelte';
  import { invalidateAll } from '$app/navigation';
  import { apiDeleteData, apiPostData, apiPutData } from '$lib/api/client';
  import { reportUiError } from '$lib/errors';
  import { t } from '$lib/i18n';
  import AppModal from '$lib/components/ui/AppModal.svelte';
  import ConfirmDeleteDialog from '$lib/components/ui/ConfirmDeleteDialog.svelte';
  import TagPill from '$lib/components/tags/TagPill.svelte';
  import FolderQueryAssist from '$lib/components/storage-roots/FolderQueryAssist.svelte';
  import { toast } from '$lib/stores/toast';

  /**
   * Smart policies: « if the folders match this condition, then do this ». The condition is the express search
   * of the folders; the actions are a tag, an alert in Monitoring and a notice to the guardians.
   */
  type Jobs = { kinds: Array<'check' | 'sensitivity'>; every_hours: number };
  type Actions = { add_tag: number | null; alert: { severity: string } | null; notify_guardians: boolean; jobs?: Jobs | null };
  type Policy = {
    id: number; name: string; description: string | null; enabled: boolean; condition: string; actions: Actions;
    matching: number; last_run_at: string | null; last_new: number | null; last_error: string | null;
  };
  type Draft = { id: number | null; name: string; description: string; enabled: boolean; condition: string; tagOn: boolean; tagId: number | null; alertOn: boolean; severity: string; notify: boolean;
    jobsOn: boolean; jobCheck: boolean; jobSensitivity: boolean; everyHours: number };

  export let data: Record<string, any>;

  $: policies = (data.policies ?? []) as Policy[];
  $: tags = (data.tags ?? []) as Array<Record<string, any>>;
  const tagOf = (id: number | null | undefined) => tags.find((tag) => Number(tag.id) === Number(id)) ?? null;
  const tagNamed = (name: string) => tags.find((tag) => String(tag.name).toLowerCase() === name.toLowerCase())?.id ?? null;
  const SEVERITIES = (): Array<[string, string]> => [['info', t('Information')], ['warning', t('Warning')], ['high', t('High')], ['critical', t('Critical')]];
  const severityLabel = (value: string) => SEVERITIES().find(([key]) => key === value)?.[1] ?? value;
  const FREQUENCIES = (): Array<[number, string]> => [[24, t('every day')], [168, t('every week')], [720, t('every month')]];
  const frequencyLabel = (hours: number) => FREQUENCIES().find(([value]) => value === Number(hours))?.[1] ?? t('every {hours} h', { hours });
  const JOB_LABEL = (): Record<string, string> => ({ check: t('reread the ACL and the content'), sensitivity: t('sensitivity scan') });

  // Starting points: the common needs, to adjust
  $: templates = [
    { name: t('Sensitive files'), description: t('Passwords, keys or vaults found by the sensitivity scan.'), condition: 'est:sensible', tagId: tagNamed('Critical'), severity: 'high', notify: true, icon: 'bi-shield-lock' },
    { name: t('Folder without guardian'), description: t('Nobody but the administrators can validate its requests.'), condition: 'est:sans-gardien', tagId: null, severity: 'warning', notify: false, icon: 'bi-person-x' },
    { name: t('Unreachable folder'), description: t('The worker can no longer open it.'), condition: 'est:injoignable', tagId: null, severity: 'high', notify: true, icon: 'bi-wifi-off' },
    { name: t('Weekly scan of the Finance folders'), description: t('Looks for passwords stored in the folders tagged Finance, every week.'), condition: 'tag:Finance', tagId: null, severity: 'warning', notify: false, icon: 'bi-calendar-week', jobs: { kinds: ['sensitivity'], every_hours: 168 } },
    { name: t('Large folder'), description: t('More than 50 GB: to check with its guardians.'), condition: 'taille>50Go', tagId: null, severity: 'info', notify: false, icon: 'bi-hdd' },
    { name: t('Broken inheritance without tag'), description: t('Permissions set apart, and nothing says why.'), condition: 'est:heritage-rompu est:sans-tag', tagId: null, severity: 'info', notify: false, icon: 'bi-scissors' }
  ];

  let draft: Draft | null = null;
  let saving = false;
  // A policy that would act on many folders at once is confirmed explicitly
  const POLICY_CONFIRM_FROM = 50;
  let wideConfirmed = false;
  $: if (!draft) wideConfirmed = false;
  let busyId: number | null = null;
  let toDelete: Policy | null = null;
  let preview: { count: number; unknown_states: string[]; sample: Array<{ id: number; name: string; path: string }> } | null = null;
  let previewTimer: ReturnType<typeof setTimeout> | null = null;

  function edit(policy: Policy | null, template: (typeof templates)[number] | null = null) {
    const source = policy
      ? { name: policy.name, description: policy.description ?? '', condition: policy.condition, tagId: policy.actions?.add_tag ?? null, severity: policy.actions?.alert?.severity ?? 'warning', notify: Boolean(policy.actions?.notify_guardians), alertOn: Boolean(policy.actions?.alert), enabled: policy.enabled, jobs: policy.actions?.jobs ?? null }
      : template
        ? { ...template, alertOn: !(template as any).jobs, enabled: true, jobs: (template as any).jobs ?? null }
        : { name: '', description: '', condition: '', tagId: null, severity: 'warning', notify: false, alertOn: true, enabled: true, jobs: null };
    draft = { id: policy?.id ?? null, name: source.name, description: source.description, enabled: source.enabled, condition: source.condition,
      tagOn: Boolean(source.tagId), tagId: source.tagId ?? null, alertOn: source.alertOn, severity: source.severity, notify: source.notify,
      jobsOn: Boolean(source.jobs?.kinds?.length), jobCheck: Boolean(source.jobs?.kinds?.includes('check')),
      jobSensitivity: Boolean(source.jobs?.kinds?.includes('sensitivity')), everyHours: Number(source.jobs?.every_hours ?? 168) };
    preview = null;
    if (draft.condition) schedulePreview(draft.condition);
  }

  function schedulePreview(condition: string) {
    if (previewTimer) clearTimeout(previewTimer);
    if (!condition.trim()) {
      preview = null;
      return;
    }
    previewTimer = setTimeout(async () => {
      try {
        preview = await apiPostData(fetch, '/policies/preview', { condition });
      } catch {
        preview = null;
      }
    }, 400);
  }
  function setCondition(value: string) {
    if (!draft) return;
    draft = { ...draft, condition: value };
    schedulePreview(value);
  }

  $: draftKinds = draft ? ([draft.jobCheck && 'check', draft.jobSensitivity && 'sensitivity'].filter(Boolean) as Array<'check' | 'sensitivity'>) : [];
  $: wide = Boolean(draft?.enabled && (preview?.count ?? 0) > POLICY_CONFIRM_FROM);
  $: canSave = Boolean(draft && draft.name.trim() && draft.condition.trim() && (draft.alertOn || draft.notify || (draft.tagOn && draft.tagId) || (draft.jobsOn && draftKinds.length)) && !(preview?.unknown_states?.length) && (!wide || wideConfirmed));

  async function save() {
    if (!draft || !canSave || saving) return;
    saving = true;
    const body = {
      name: draft.name.trim(), description: draft.description.trim() || null, enabled: draft.enabled, condition: draft.condition.trim(),
      actions: { add_tag: draft.tagOn ? draft.tagId : null, alert: draft.alertOn ? { severity: draft.severity } : null, notify_guardians: draft.notify,
        jobs: draft.jobsOn && draftKinds.length ? { kinds: draftKinds, every_hours: draft.everyHours } : null }
    };
    try {
      const result: any = draft.id ? await apiPutData(fetch, `/policies/${draft.id}`, body) : await apiPostData(fetch, '/policies', body);
      const run = result?.run?.results?.[0];
      toast.success(run ? t('Policy saved: {count} folder(s) match.', { count: run.matched }) + (run.jobs ? ' ' + t('{count} task(s) sent to the workers.', { count: run.jobs }) : '') : t('Policy saved.'));
      draft = null;
      await invalidateAll();
    } catch (error: unknown) {
      reportUiError(error, 'Unable to save the policy.', 'policies.save');
    } finally {
      saving = false;
    }
  }

  async function run(policy: Policy) {
    busyId = policy.id;
    try {
      const result: any = await apiPostData(fetch, `/policies/${policy.id}/run`, {});
      const outcome = result?.run?.results?.[0];
      toast.success(t('{matched} folder(s) match, {new} new.', { matched: outcome?.matched ?? 0, new: outcome?.new ?? 0 }) + (outcome?.jobs ? ' ' + t('{count} task(s) sent to the workers.', { count: outcome.jobs }) : ''));
      await invalidateAll();
    } catch (error: unknown) {
      reportUiError(error, 'Unable to run the policy.', 'policies.run');
    } finally {
      busyId = null;
    }
  }

  async function toggle(policy: Policy) {
    busyId = policy.id;
    try {
      const body = { name: policy.name, description: policy.description, condition: policy.condition, actions: policy.actions };
      await apiPutData(fetch, `/policies/${policy.id}`, { ...body, enabled: !policy.enabled });
      await invalidateAll();
      toast.success(policy.enabled ? t('Policy « {name} » disabled.', { name: policy.name }) : t('Policy « {name} » enabled.', { name: policy.name }), {
        action: { label: t('Undo'), run: async () => { await apiPutData(fetch, `/policies/${policy.id}`, { ...body, enabled: policy.enabled }); await invalidateAll(); } }
      });
    } catch (error: unknown) {
      reportUiError(error, 'Unable to update the policy.', 'policies.toggle');
    } finally {
      busyId = null;
    }
  }

  async function remove() {
    if (!toDelete) return;
    const policy = toDelete;
    busyId = policy.id;
    try {
      await apiDeleteData(fetch, `/policies/${policy.id}`);
      toast.success(t('Policy deleted.'));
      toDelete = null;
      await invalidateAll();
    } catch (error: unknown) {
      reportUiError(error, 'Unable to delete the policy.', 'policies.delete');
    } finally {
      busyId = null;
    }
  }
</script>

<section class="pl">
  <header class="pl__top">
    <div>
      <h1>{t('Policies')}</h1>
      <p>{t('When folders match a condition, BornToShare acts: tag, alert in Monitoring, notice to the guardians.')}</p>
    </div>
    <button type="button" class="b2s-btn b2s-btn-primary" on:click={() => edit(null)}><i class="bi bi-plus-lg" aria-hidden="true"></i>{t('New policy')}</button>
  </header>

  {#if policies.length}
    <div class="pl__list">
      {#each policies as policy (policy.id)}
        {@const tag = tagOf(policy.actions?.add_tag)}
        <article class="pc" class:is-off={!policy.enabled}>
          <div class="pc__main">
            <div class="pc__title">
              <h2>{policy.name}</h2>
              <span class="pc__state" class:is-on={policy.enabled}>{policy.enabled ? t('Active') : t('Disabled')}</span>
            </div>
            {#if policy.description}<p class="pc__desc">{policy.description}</p>{/if}
            <div class="pc__rule">
              <span class="pc__kw">{t('If')}</span><code>{policy.condition}</code>
              <span class="pc__kw">{t('then')}</span>
              {#if tag}<span class="pc__act"><i class="bi bi-tag" aria-hidden="true"></i>{t('tag')} <TagPill small label={String(tag.name)} color={tag.color ?? null} /></span>{/if}
              {#if policy.actions?.alert}<span class="pc__act"><i class="bi bi-bell" aria-hidden="true"></i>{t('alert {severity}', { severity: severityLabel(policy.actions.alert.severity).toLowerCase() })}</span>{/if}
              {#if policy.actions?.notify_guardians}<span class="pc__act"><i class="bi bi-envelope" aria-hidden="true"></i>{t('notice to the guardians')}</span>{/if}
              {#if policy.actions?.jobs?.kinds?.length}<span class="pc__act"><i class="bi bi-cpu" aria-hidden="true"></i>{policy.actions.jobs.kinds.map((kind) => JOB_LABEL()[kind]).join(' + ')} · {frequencyLabel(policy.actions.jobs.every_hours)}</span>{/if}
            </div>
          </div>
          <div class="pc__side">
            <a class="pc__count" href={`/storage-roots?q=${encodeURIComponent(policy.condition)}`} title={t('See the folders')}>
              <b>{policy.matching}</b><span>{t('folder(s) matching')}</span>
            </a>
            <small>
              {#if policy.last_error}<span class="pc__err">{policy.last_error}</span>
              {:else if policy.last_run_at}{t('evaluated')} <RelativeTime value={policy.last_run_at} />
              {:else}{t('Not evaluated yet')}{/if}
            </small>
            <div class="pc__btns">
              <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" disabled={busyId !== null || !policy.enabled} on:click={() => run(policy)}><i class="bi bi-play" aria-hidden="true"></i>{t('Run')}</button>
              <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" on:click={() => edit(policy)}>{t('Edit')}</button>
              <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" disabled={busyId !== null} on:click={() => toggle(policy)}>{policy.enabled ? t('Disable') : t('Enable')}</button>
              <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" aria-label={t('Delete')} title={t('Delete')} on:click={() => (toDelete = policy)}><i class="bi bi-trash" aria-hidden="true"></i></button>
            </div>
          </div>
        </article>
      {/each}
    </div>
  {/if}

  <section class="pl__tpl">
    <h2>{policies.length ? t('Add from a template') : t('Start from a template')}</h2>
    <div class="pl__tpls">
      {#each templates as template (template.condition)}
        <button type="button" class="tp" on:click={() => edit(null, template)}>
          <i class={`bi ${template.icon}`} aria-hidden="true"></i>
          <span><strong>{template.name}</strong><small>{template.description}</small><code>{template.condition}</code></span>
        </button>
      {/each}
    </div>
  </section>
</section>

<AppModal open={draft !== null} onClose={() => (draft = null)} size="lg" iconClass="bi bi-lightning-charge" closeOnBackdrop={false}
  title={draft?.id ? t('Edit the policy') : t('New policy')} subtitle={draft?.name || null}>
  {#if draft}
    <div class="pf">
      <label>{t('Name')}<input class="b2s-input" bind:value={draft.name} maxlength="120" placeholder={t('Sensitive files')} /></label>
      <label>{t('Description (optional)')}<input class="b2s-input" bind:value={draft.description} maxlength="500" placeholder={t('Shown in the alert and the notice')} /></label>

      <div class="pf__block">
        <span class="pf__label">{t('If the folder matches')}</span>
        <input class="b2s-input mono" value={draft.condition} maxlength="500" placeholder="est:sensible tag:Finance" aria-label={t('Condition')}
          on:input={(event) => setCondition(event.currentTarget.value)} />
        <FolderQueryAssist query={draft.condition} rows={data.folders ?? []} tags={tags.map((tag) => String(tag.name))} onQueryChange={setCondition} />
        {#if preview?.unknown_states?.length}
          <p class="pf__bad">{t('Unknown state: {states}', { states: preview.unknown_states.join(', ') })}</p>
        {:else if preview}
          <p class="pf__preview"><b>{t('{count} folder(s) match now', { count: preview.count })}</b>
            {#if preview.sample.length}<span>{preview.sample.map((item) => item.name).join(' · ')}{preview.count > preview.sample.length ? ' …' : ''}</span>{/if}
          </p>
        {/if}
      </div>

      <div class="pf__block">
        <span class="pf__label">{t('Then')}</span>
        <label class="pf__check"><input type="checkbox" bind:checked={draft.alertOn} />
          <span>{t('Open an alert in Monitoring')}<small>{t('It closes by itself when the folder no longer matches.')}</small></span>
          {#if draft.alertOn}
            <select class="b2s-input" bind:value={draft.severity} aria-label={t('Severity')}>
              {#each SEVERITIES() as [key, label] (key)}<option value={key}>{label}</option>{/each}
            </select>
          {/if}
        </label>
        <label class="pf__check"><input type="checkbox" bind:checked={draft.tagOn} />
          <span>{t('Add a tag')}<small>{t('Once, when the folder starts matching. Removing it stays a human choice.')}</small></span>
          {#if draft.tagOn}
            <select class="b2s-input" bind:value={draft.tagId} aria-label={t('Tag')}>
              <option value={null}>{t('Choose a tag')}</option>
              {#each tags as tag (tag.id)}<option value={Number(tag.id)}>{tag.name}</option>{/each}
            </select>
          {/if}
        </label>
        <label class="pf__check"><input type="checkbox" bind:checked={draft.notify} />
          <span>{t('Tell the guardians by e-mail')}<small>{t('Once per folder that starts matching (Settings › Notifications must be on).')}</small></span>
        </label>
        <label class="pf__check"><input type="checkbox" bind:checked={draft.jobsOn} />
          <span>{t('Run tasks on these folders')}<small>{t('Sent to the workers for each folder that matches, at most once per period; 50 folders per run, the next runs take the rest.')}</small></span>
          {#if draft.jobsOn}
            <select class="b2s-input" bind:value={draft.everyHours} aria-label={t('Frequency')}>
              {#each FREQUENCIES() as [value, label] (value)}<option value={value}>{label}</option>{/each}
            </select>
          {/if}
        </label>
        {#if draft.jobsOn}
          <div class="pf__jobs">
            <label><input type="checkbox" bind:checked={draft.jobCheck} />{t('Test the folder, reread its ACL and measure its content')}</label>
            <label><input type="checkbox" bind:checked={draft.jobSensitivity} />{t('Sensitivity scan (passwords, keys, vaults)')}</label>
          </div>
        {/if}
      </div>
      {#if wide}
        <label class="pf__wide"><input type="checkbox" bind:checked={wideConfirmed} />{t('I confirm: this policy acts at once on {count} folders', { count: preview?.count ?? 0 })}</label>
      {/if}
      <label class="pf__check"><input type="checkbox" bind:checked={draft.enabled} /><span>{t('Active')}<small>{t('Evaluated every 15 minutes, and right after a sensitivity scan.')}</small></span></label>
    </div>
  {/if}
  <svelte:fragment slot="footer">
    <button type="button" class="b2s-btn b2s-btn-secondary" on:click={() => (draft = null)}>{t('Cancel')}</button>
    <button type="button" class="b2s-btn b2s-btn-primary" disabled={!canSave || saving} on:click={save}>{draft?.id ? t('Save') : t('Create the policy')}</button>
  </svelte:fragment>
</AppModal>

<ConfirmDeleteDialog open={toDelete !== null} onClose={() => (toDelete = null)} onConfirm={remove} busy={busyId !== null}
  title={t('Delete the policy')} description={toDelete?.name ?? null}
  impactItems={[t('Its open alerts are closed.'), t('The tags it added stay on the folders.')]} />

<style>
  .pl { padding: var(--b2s-page-padding, 24px 28px); display: flex; flex-direction: column; gap: 20px; }
  .pl__top { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; }
  .pl__top h1 { margin: 0; font-size: var(--b2s-fs-overview-title, 38px); line-height: 1.05; font-weight: 600; letter-spacing: -0.03em; }
  .pl__top p { margin: 6px 0 0; color: var(--b2s-color-text-muted); font-size: 15px; }
  .pl__list { display: flex; flex-direction: column; gap: 10px; }
  .pc { display: grid; grid-template-columns: minmax(0, 1fr) 300px; gap: 20px; padding: 16px 18px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .pc.is-off { opacity: 0.7; }
  .pc__main { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
  .pc__title { display: flex; align-items: center; gap: 10px; }
  .pc h2 { margin: 0; font-size: var(--b2s-fs-md); font-weight: 600; }
  .pc__state { padding: 1px 8px; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-neutral-soft); color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .pc__state.is-on { background: var(--b2s-color-success-soft, #e7f6ec); color: var(--b2s-color-success-strong, #1a7f37); }
  .pc__desc { margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .pc__rule { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; font-size: var(--b2s-fs-sm); }
  .pc__kw { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }
  .pc__rule code { padding: 2px 8px; border-radius: var(--b2s-radius-sm, 6px); background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); font-family: var(--b2s-font-mono); font-size: var(--b2s-fs-xs); }
  .pc__act { display: inline-flex; align-items: center; gap: 6px; padding: 2px 8px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-pill); font-size: var(--b2s-fs-xs); }
  .pc__side { display: flex; flex-direction: column; align-items: flex-end; gap: 6px; }
  .pc__count { display: flex; align-items: baseline; gap: 6px; color: inherit; text-decoration: none; }
  .pc__count b { font-size: 24px; font-weight: 700; font-variant-numeric: tabular-nums; }
  .pc__count span { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .pc__count:hover span { text-decoration: underline; }
  .pc__side small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .pc__err { color: var(--b2s-color-danger-strong, #b42318); }
  .pc__btns { display: flex; gap: 6px; margin-top: auto; }
  .pl__tpl h2 { margin: 0 0 10px; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }
  .pl__tpls { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 10px; }
  .tp { display: grid; grid-template-columns: 34px minmax(0, 1fr); gap: 12px; padding: 14px; border: 1px dashed var(--b2s-color-border-strong); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); color: inherit; text-align: left; cursor: pointer; }
  .tp:hover { border-style: solid; background: var(--b2s-color-surface-soft, #f6f7f9); }
  .tp > i { display: grid; place-items: center; width: 34px; height: 34px; border-radius: var(--b2s-radius-md); background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); }
  .tp span { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
  .tp small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .tp code { align-self: flex-start; margin-top: 2px; color: var(--b2s-color-info-strong); font-family: var(--b2s-font-mono); font-size: var(--b2s-font-micro); }
  .pf { display: flex; flex-direction: column; gap: 14px; }
  .pf > label:not(.pf__check) { display: flex; flex-direction: column; gap: 4px; font-size: var(--b2s-fs-sm); font-weight: 500; }
  .pf__block { display: flex; flex-direction: column; gap: 8px; padding: 12px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-md); }
  .pf__label { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }
  .pf__preview, .pf__bad { display: flex; flex-direction: column; gap: 2px; margin: 0; font-size: var(--b2s-fs-sm); }
  .pf__preview span { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .pf__bad { color: var(--b2s-color-danger-strong, #b42318); }
  .pf__check { display: grid; grid-template-columns: 18px minmax(0, 1fr) auto; gap: 10px; align-items: start; font-size: var(--b2s-fs-sm); }
  .pf__check input[type='checkbox'] { margin-top: 3px; }
  .pf__check span { display: flex; flex-direction: column; gap: 2px; }
  .pf__check small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .pf__check select { min-width: 160px; }
  .pf__jobs { display: flex; flex-direction: column; gap: 6px; margin: -4px 0 0 28px; font-size: var(--b2s-fs-sm); }
  .pf__jobs label { display: flex; gap: 8px; align-items: center; }
  .pf__wide { display: flex; gap: 8px; align-items: center; padding: 10px 12px; border-radius: var(--b2s-radius-md); background: var(--b2s-color-warning-soft, #fdefd9); color: var(--b2s-color-warning-strong, #9a5b00); font-size: var(--b2s-fs-sm); font-weight: 600; }
  .mono { font-family: var(--b2s-font-mono); }
</style>
