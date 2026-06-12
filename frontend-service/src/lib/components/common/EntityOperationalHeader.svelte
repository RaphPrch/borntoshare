<script lang="ts">
  export type OperationalHeaderTone = 'success' | 'warning' | 'danger' | 'neutral' | 'info';

  export type OperationalHeaderMetaItem = {
    icon?: string;
    label: string;
    tone?: OperationalHeaderTone;
  };

  export let eyebrow = '';
  export let title = '';
  export let subtitle = '';
  export let metaItems: OperationalHeaderMetaItem[] = [];
  export let statusLabel = 'Unknown';
  export let statusTone: OperationalHeaderTone = 'neutral';
  export let statusIconClass: string | null = null;
  export let showAttention = false;
  export let attentionTitle = 'Attention required';
  export let attentionItems: string[] = [];
  export let attentionMeta: string | null = null;
  export let attentionIconClass = 'bi bi-exclamation-triangle-fill';
  export let maxAttentionItems = 2;
  export let containerClass = '';

  $: resolvedStatusIcon =
    statusIconClass ??
    (statusTone === 'success'
      ? 'bi bi-check-circle-fill'
      : statusTone === 'danger'
        ? 'bi bi-x-circle-fill'
        : statusTone === 'warning'
          ? 'bi bi-exclamation-triangle-fill'
          : 'bi bi-info-circle-fill');
  $: visibleAttentionItems = attentionItems.slice(0, Math.max(1, maxAttentionItems));
  $: hiddenAttentionCount = Math.max(0, attentionItems.length - visibleAttentionItems.length);
</script>

<section class={`b2s-operational-header is-${statusTone} ${showAttention ? 'has-attention' : ''} ${containerClass}`.trim()}>
  <div class="b2s-operational-header__main">
    <div class="b2s-operational-header__copy">
      {#if eyebrow}
        <div class="b2s-operational-header__eyebrow">{eyebrow}</div>
      {/if}

      <h1>{title}</h1>

      {#if subtitle}
        <p title={subtitle}>{subtitle}</p>
      {/if}

      {#if metaItems.length > 0}
        <div class="b2s-operational-header__meta" aria-label="Context">
          {#each metaItems as item, idx (idx)}
            <span class={`b2s-operational-header__chip is-${item.tone ?? 'neutral'}`}>
              {#if item.icon}
                <i class={`bi ${item.icon}`} aria-hidden="true"></i>
              {/if}
              {item.label}
            </span>
          {/each}
        </div>
      {/if}
    </div>

    <div class="b2s-operational-header__right">
      {#if statusLabel}
        <span class={`b2s-operational-header__status is-${statusTone}`}>
          {#if resolvedStatusIcon}
            <i class={resolvedStatusIcon} aria-hidden="true"></i>
          {/if}
          {statusLabel}
        </span>
      {/if}

      <div class="b2s-operational-header__actions">
        <slot name="actions" />
      </div>
    </div>
  </div>

  {#if showAttention && attentionItems.length > 0}
    <div class="b2s-operational-header__attention">
      <div class="b2s-operational-header__attention-icon" aria-hidden="true">
        <i class={attentionIconClass}></i>
      </div>

      <div class="b2s-operational-header__attention-copy">
        <div class="b2s-operational-header__attention-head">
          <strong>{attentionTitle}</strong>
          {#if attentionMeta}
            <span>{attentionMeta}</span>
          {/if}
        </div>

        <ul>
          {#each visibleAttentionItems as item}
            <li>{item}</li>
          {/each}
          {#if hiddenAttentionCount > 0}
            <li>{hiddenAttentionCount} more item{hiddenAttentionCount > 1 ? 's' : ''} to review.</li>
          {/if}
        </ul>
      </div>
    </div>
  {/if}
</section>

<style>
  .b2s-operational-header {
    position: relative;
    overflow: visible;
    z-index: 1;
    border: 1px solid #dde5f1;
    border-radius: 16px;
    background:
      linear-gradient(135deg, rgba(255, 255, 255, 0.96), rgba(248, 251, 255, 0.94)),
      #ffffff;
    box-shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
    padding: 18px;
    display: grid;
    gap: 14px;
  }

  .b2s-operational-header:focus-within {
    z-index: 40;
  }

  .b2s-operational-header.has-attention {
    border-color: #dbe3ef;
    background:
      linear-gradient(135deg, rgba(255, 255, 255, 0.98), rgba(248, 251, 255, 0.96)),
      #ffffff;
  }

  .b2s-operational-header.has-attention::before {
    content: "";
    position: absolute;
    inset: 0 auto 0 0;
    width: 5px;
    background: linear-gradient(180deg, #f59e0b 0%, #eab308 48%, #38bdf8 100%);
  }

  .b2s-operational-header__main,
  .b2s-operational-header__attention {
    position: relative;
    z-index: 1;
  }

  .b2s-operational-header__main {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 18px;
  }

  .b2s-operational-header__copy {
    min-width: 0;
    display: grid;
    gap: 6px;
  }

  .b2s-operational-header__eyebrow {
    color: #64748b;
    font-size: 12px;
    font-weight: 800;
    text-transform: uppercase;
  }

  .b2s-operational-header h1 {
    margin: 0;
    color: #10203f;
    font-size: 32px;
    line-height: 1.05;
    font-weight: 760;
  }

  .b2s-operational-header p {
    margin: 0;
    max-width: min(840px, 100%);
    overflow: hidden;
    text-overflow: ellipsis;
    color: #475569;
    font-size: 14px;
    font-weight: 600;
    white-space: nowrap;
  }

  .b2s-operational-header__meta {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 4px;
  }

  .b2s-operational-header__chip,
  .b2s-operational-header__status {
    min-height: 30px;
    border: 1px solid #d7dfec;
    border-radius: 999px;
    background: #f7faff;
    color: #304867;
    padding: 0 11px;
    display: inline-flex;
    align-items: center;
    gap: 7px;
    font-size: 13px;
    font-weight: 700;
    line-height: 1;
  }

  .b2s-operational-header__chip.is-success,
  .b2s-operational-header__status.is-success {
    border-color: #bce1ce;
    background: #e8f7ef;
    color: #1d7d52;
  }

  .b2s-operational-header__chip.is-warning,
  .b2s-operational-header__status.is-warning {
    border-color: #f0d49b;
    background: #fff5df;
    color: #996300;
  }

  .b2s-operational-header__chip.is-danger,
  .b2s-operational-header__status.is-danger {
    border-color: #f0c1c1;
    background: #fdecec;
    color: #9f2f2f;
  }

  .b2s-operational-header__chip.is-info,
  .b2s-operational-header__status.is-info {
    border-color: #c9d9f6;
    background: #edf4ff;
    color: #275aa6;
  }

  .b2s-operational-header__right {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 10px;
    min-width: min(100%, 460px);
  }

  .b2s-operational-header__actions {
    display: flex;
    justify-content: flex-end;
    width: 100%;
  }

  .b2s-operational-header__attention {
    border: 1px solid #dbe3ef;
    border-radius: 14px;
    background:
      linear-gradient(135deg, rgba(255, 255, 255, 0.98), rgba(248, 251, 255, 0.94)),
      #ffffff;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.82);
    padding: 12px;
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    align-items: flex-start;
    gap: 12px;
  }

  .b2s-operational-header__attention-icon {
    width: 38px;
    height: 38px;
    border: 1px solid #f1d69d;
    border-radius: 12px;
    background:
      radial-gradient(circle at 30% 24%, rgba(255, 255, 255, 0.88), transparent 34%),
      linear-gradient(180deg, #fff7e7 0%, #ffedd0 100%);
    color: #a15c00;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex: 0 0 auto;
  }

  .b2s-operational-header__attention-copy {
    min-width: 0;
    display: grid;
    gap: 8px;
  }

  .b2s-operational-header__attention-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
  }

  .b2s-operational-header__attention-head strong {
    color: #10203f;
    font-size: 14px;
    font-weight: 800;
  }

  .b2s-operational-header__attention-head span {
    color: #64748b;
    font-size: 13px;
    font-weight: 650;
  }

  .b2s-operational-header ul {
    margin: 0;
    padding: 0;
    list-style: none;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .b2s-operational-header li {
    border: 1px solid #d7dfec;
    border-radius: 999px;
    background: #f7faff;
    color: #334155;
    padding: 6px 10px;
    font-size: 13px;
    font-weight: 650;
  }

  @media (max-width: 900px) {
    .b2s-operational-header__main {
      flex-direction: column;
    }

    .b2s-operational-header__right,
    .b2s-operational-header__actions {
      width: 100%;
      align-items: stretch;
      justify-content: flex-start;
      min-width: 0;
    }

    .b2s-operational-header p {
      white-space: normal;
    }

    .b2s-operational-header h1 {
      font-size: 28px;
    }
  }

  @media (max-width: 620px) {
    .b2s-operational-header h1 {
      font-size: 24px;
    }

    .b2s-operational-header__attention {
      grid-template-columns: minmax(0, 1fr);
    }

    .b2s-operational-header__attention-icon {
      display: none;
    }
  }
</style>
