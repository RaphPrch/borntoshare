<script lang="ts">
  import { t } from '$lib/i18n';
  import type { ZoneSummary } from './zone-summary';

  type Step = { key: string; tone: 'bad' | 'warn' | 'info'; icon: string; title: string; detail: string; label: string; run: () => void };

  /** « To do on this zone »: each problem grouped, with the action that settles it. */
  export let summary: ZoneSummary;
  export let pendingRequests = 0;
  export let ouMissing = false;
  export let rereadBusy = false;
  export let onOpenServer: (id: number) => void = () => {};
  export let onAddGuardians: () => void = () => {};
  export let onReread: () => void = () => {};
  export let onOpenRequests: () => void = () => {};
  export let onOpenProvisioning: () => void = () => {};

  $: steps = [
    ...summary.unreachable.map((server): Step => ({
      key: `down-${server.id}`,
      tone: 'bad',
      icon: 'bi-wifi-off',
      title: t('{name} is unreachable', { name: server.name }),
      detail: [server.host, server.roots ? t('{count} folder(s) blocked', { count: server.roots }) : ''].filter(Boolean).join(' · '),
      label: t('Edit the connection'),
      run: () => onOpenServer(server.id)
    })),
    ...(summary.noGuardian.length
      ? [{
          key: 'guardians',
          tone: 'warn' as const,
          icon: 'bi-person-plus',
          title: t('{count} folder(s) without enough guardians', { count: summary.noGuardian.length }),
          detail: t('Only the administrators can approve their requests'),
          label: t('Add guardians'),
          run: onAddGuardians
        }]
      : []),
    ...(summary.reread.length
      ? [{
          key: 'reread',
          tone: 'warn' as const,
          icon: 'bi-arrow-clockwise',
          title: t('{count} folder(s) to read again', { count: summary.reread.length }),
          detail: t('Failed test or gap in the ACL, on a server that answers'),
          label: rereadBusy ? t('Reading…') : t('Read the ACLs'),
          run: onReread
        }]
      : []),
    ...(pendingRequests
      ? [{
          key: 'requests',
          tone: 'info' as const,
          icon: 'bi-envelope',
          title: t('{count} pending request(s)', { count: pendingRequests }),
          detail: t('To decide by the guardians of the folders'),
          label: t('See the requests'),
          run: onOpenRequests
        }]
      : []),
    ...(ouMissing
      ? [{
          key: 'ou',
          tone: 'warn' as const,
          icon: 'bi-diagram-3',
          title: t('No OU set for the groups'),
          detail: t('The groups go to the default OU of the directory'),
          label: t('Set it'),
          run: onOpenProvisioning
        }]
      : [])
  ];
</script>

{#if steps.length}
  <section class="zd" aria-label={t('To do on this zone')}>
    <h2><i class="bi bi-exclamation-triangle-fill" aria-hidden="true"></i>{t('To do on this zone')} · {steps.length}</h2>
    {#each steps as step (step.key)}
      <div class="zd__row">
        <span class={`zd__icon is-${step.tone}`} aria-hidden="true"><i class={`bi ${step.icon}`}></i></span>
        <span class="zd__text"><strong>{step.title}</strong>{#if step.detail}<small>{step.detail}</small>{/if}</span>
        <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" disabled={step.key === 'reread' && rereadBusy} on:click={step.run}>{step.label}</button>
      </div>
    {/each}
  </section>
{/if}

<style>
  .zd { overflow: hidden; border: 1px solid var(--b2s-color-warning-border, #f3d9ad); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .zd h2 { display: flex; align-items: center; gap: 8px; margin: 0; padding: 11px 16px; background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); font-size: var(--b2s-fs-sm); font-weight: 600; }
  .zd__row { display: grid; grid-template-columns: 28px minmax(0, 1fr) auto; gap: 12px; align-items: center; padding: 10px 16px; border-top: 1px solid var(--b2s-color-border); }
  .zd h2 + .zd__row { border-top: 0; }
  .zd__icon { display: grid; place-items: center; width: 28px; height: 28px; border-radius: 8px; font-size: 13px; }
  .zd__icon.is-bad { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger-strong); }
  .zd__icon.is-warn { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .zd__icon.is-info { background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); }
  .zd__text { display: flex; flex-direction: column; min-width: 0; }
  .zd__text strong { font-weight: 600; font-size: var(--b2s-fs-sm); }
  .zd__text small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); overflow-wrap: anywhere; }
</style>
