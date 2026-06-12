<script lang="ts">
  export let iconClass = 'bi-person';
  export let kind: 'user' | 'group' | 'neutral' = 'neutral';
  export let size: 'sm' | 'md' = 'md';
  export let className = '';
</script>

<span class={`b2s-icon-tile is-${kind} is-${size} ${className}`.trim()} aria-hidden="true">
  <i class={`bi ${iconClass}`}></i>
</span>

<style>
  .b2s-icon-tile {
    border-radius: 14px;
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
    border-radius: 11px;
    font-size: 17px;
  }

  .b2s-icon-tile.is-user {
    color: #2f5ab8;
    background: #ebf2ff;
  }

  .b2s-icon-tile.is-group {
    color: #3f57c2;
    background: #edf0ff;
  }

  .b2s-icon-tile.is-neutral {
    color: #4d668d;
    background: #edf2f8;
  }
</style>

