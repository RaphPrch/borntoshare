<script lang="ts">
  export let title: string;
  export let subtitle: string | undefined = undefined;
  export let icon: string | undefined = undefined;
  export let tone: 'default' | 'warning' | 'danger' = 'default';

  $: toneClass = tone === 'warning' ? 'adv-tone-warning' : tone === 'danger' ? 'adv-tone-danger' : '';
</script>

<section class={['adv-card', toneClass].filter(Boolean).join(' ')}>
  <header class="adv-card-header">
    {#if icon}<i class={'bi ' + icon} aria-hidden="true"></i>{/if}
    <div>
      <h2>{title}</h2>
      {#if subtitle}<p class="muted">{subtitle}</p>{/if}
    </div>
    <div style="margin-left:auto;"><slot name="header-actions" /></div>
  </header>
  <div class="adv-card-body">
    <slot />
  </div>
</section>
