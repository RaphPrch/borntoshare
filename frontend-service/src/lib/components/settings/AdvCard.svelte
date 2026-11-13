<script lang="ts">
  interface Props {
    title: string;
    subtitle?: string | undefined;
    icon?: string | undefined;
    tone?: 'default' | 'warning' | 'danger';
    headerActions?: import('svelte').Snippet;
    children?: import('svelte').Snippet;
  }

  let {
    title,
    subtitle = undefined,
    icon = undefined,
    tone = 'default',
    headerActions,
    children
  }: Props = $props();

  let toneClass = $derived(tone === 'warning' ? 'adv-tone-warning' : tone === 'danger' ? 'adv-tone-danger' : '');
</script>

<section class={['adv-card', toneClass].filter(Boolean).join(' ')}>
  <header class="adv-card-header">
    {#if icon}<i class={'bi ' + icon} aria-hidden="true"></i>{/if}
    <div>
      <h2>{title}</h2>
      {#if subtitle}<p class="muted">{subtitle}</p>{/if}
    </div>
    <div style="margin-left:auto;">{@render headerActions?.()}</div>
  </header>
  <div class="adv-card-body">
    {@render children?.()}
  </div>
</section>
