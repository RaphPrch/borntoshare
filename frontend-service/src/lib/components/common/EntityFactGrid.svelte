<script lang="ts">
  export type EntityFactGridTone = 'neutral' | 'success' | 'warning' | 'danger' | 'info';

  export type EntityFactGridItem = {
    key: string;
    label: string;
    value?: string | number | null;
    title?: string | null;
    icon?: string | null;
    tone?: EntityFactGridTone;
    mono?: boolean;
    wide?: boolean;
  };

  export let items: EntityFactGridItem[] = [];
  export let columns: 'one' | 'two' = 'two';

  const displayValue = (value: EntityFactGridItem['value']) => {
    const text = String(value ?? '').trim();
    return text || '—';
  };
</script>

<dl class={`b2s-fact-grid is-${columns}`}>
  {#each items as item (item.key)}
    <div class={`b2s-fact-grid__item is-${item.tone ?? 'neutral'} ${item.wide ? 'is-wide' : ''}`.trim()}>
      <dt>
        {#if item.icon}
          <i class={`bi ${item.icon}`} aria-hidden="true"></i>
        {/if}
        {item.label}
      </dt>
      <dd class:has-mono={item.mono} title={item.title ?? displayValue(item.value)}>
        {displayValue(item.value)}
      </dd>
    </div>
  {/each}
</dl>

<style>
  .b2s-fact-grid {
    margin: 10px 0 0;
    display: grid;
    gap: 10px;
  }

  .b2s-fact-grid.is-two {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .b2s-fact-grid.is-one {
    grid-template-columns: minmax(0, 1fr);
  }

  .b2s-fact-grid__item {
    min-width: 0;
    border: 1px solid #eef2f7;
    border-radius: 10px;
    background: #fcfdff;
    padding: 10px 12px;
    display: grid;
    gap: 4px;
  }

  .b2s-fact-grid__item.is-wide {
    grid-column: 1 / -1;
  }

  .b2s-fact-grid__item.is-warning {
    border-color: #f2d8a7;
    background: #fffaf0;
  }

  .b2s-fact-grid__item.is-danger {
    border-color: #f3c2bd;
    background: #fff5f4;
  }

  .b2s-fact-grid__item.is-success {
    border-color: #bfe8d4;
    background: #f1fbf6;
  }

  .b2s-fact-grid__item.is-info {
    border-color: #cbdcf8;
    background: #f4f8ff;
  }

  .b2s-fact-grid dt {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    min-width: 0;
    color: var(--b2s-color-text-muted, #667085);
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
  }

  .b2s-fact-grid dt i {
    color: #6284c7;
  }

  .b2s-fact-grid dd {
    margin: 0;
    min-width: 0;
    color: var(--b2s-color-text, #1f2a44);
    font-size: 14px;
    font-weight: 720;
    overflow-wrap: anywhere;
  }

  .b2s-fact-grid dd.has-mono {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
    font-size: 13px;
    font-weight: 650;
  }

  @media (max-width: 720px) {
    .b2s-fact-grid.is-two {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
