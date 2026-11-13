<script lang="ts">
  /**
   * Product icon of an extension: the official mark from simple-icons (CC0) when the brand publishes one there,
   * otherwise a neutral monogram (Centreon and ServiceNow are not in simple-icons; syslog is a protocol).
   */
  import { siGrafana, siOpentelemetry, siSplunk } from 'simple-icons';

  interface Props {
    product: string;
    size?: number;
  }

  let { product, size = 40 }: Props = $props();

  const ICONS: Record<string, { path: string; hex: string; title: string }> = {
    splunk: siSplunk,
    grafana: siGrafana,
    otel: siOpentelemetry
  };
  const MONOGRAMS: Record<string, string> = { syslog: 'SL', centreon: 'CE', servicenow: 'SN' };
  let icon = $derived(ICONS[product]);
</script>

<span class="ext-icon" style="--ext-size:{size}px; --ext-color:{icon ? `#${icon.hex}` : 'var(--b2s-color-text)'}" aria-hidden="true">
  {#if icon}
    <svg viewBox="0 0 24 24" role="img"><path d={icon.path} /></svg>
  {:else if product === 'syslog'}
    <i class="bi bi-journal-code"></i>
  {:else}
    <b>{MONOGRAMS[product] ?? product.slice(0, 2).toUpperCase()}</b>
  {/if}
</span>

<style>
  .ext-icon { display: grid; place-items: center; flex: none; width: var(--ext-size); height: var(--ext-size); border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-md); background: var(--b2s-color-surface); color: var(--ext-color); }
  .ext-icon svg { width: 58%; height: 58%; fill: currentColor; }
  .ext-icon i { font-size: calc(var(--ext-size) * 0.45); }
  .ext-icon b { font-size: calc(var(--ext-size) * 0.3); font-weight: 700; letter-spacing: 0.02em; }
</style>
