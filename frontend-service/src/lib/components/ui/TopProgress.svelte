<script lang="ts">
  import { navigating } from '$app/stores';
</script>

{#if $navigating}
  <div class="b2s-top-progress" aria-hidden="true"></div>
{/if}

<style>
  .b2s-top-progress{
    position: fixed;
    top: 0;
    left: 0;
    height: 3px;
    width: 100%;
    z-index: 9998;
    background: linear-gradient(90deg, rgba(59,130,246,0.2), rgba(59,130,246,0.9), rgba(16,185,129,0.6));
    animation: b2sProgress 900ms ease-in-out infinite;
  }
  @keyframes b2sProgress {
    0% { filter: brightness(1); transform: translateX(-20%); }
    50% { filter: brightness(1.2); transform: translateX(0%); }
    100% { filter: brightness(1); transform: translateX(20%); }
  }
</style>
