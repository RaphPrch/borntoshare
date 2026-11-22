<script lang="ts">
  interface Props {
    iconClass?: string;
    kind?: 'user' | 'group' | 'neutral';
    size?: 'sm' | 'md';
    className?: string;
  }

  let {
    iconClass = 'bi-person',
    kind = 'neutral',
    size = 'md',
    className = ''
  }: Props = $props();
</script>

<span class={`b2s-icon-tile is-${kind} is-${size} ${className}`.trim()} aria-hidden="true">
  <i class={`bi ${iconClass}`}></i>
</span>

<style>
  .b2s-icon-tile {
    border-radius: var(--b2s-radius-lg);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex: 0 0 auto;
  }

  .b2s-icon-tile.is-md {
    width: 44px;
    height: 44px;
    font-size: 22px;
  }

  .b2s-icon-tile.is-sm {
    width: 34px;
    height: 34px;
    border-radius: var(--b2s-radius-md);
    font-size: 17px;
  }

  .b2s-icon-tile.is-user {
    color: var(--b2s-accent-strong);
    background: var(--b2s-accent-soft);
  }

  .b2s-icon-tile.is-group {
    color: var(--b2s-color-info-strong);
    background: var(--b2s-color-info-soft);
  }

  .b2s-icon-tile.is-neutral {
    color: var(--b2s-color-text-muted);
    background: var(--b2s-color-surface-muted);
  }
</style>

