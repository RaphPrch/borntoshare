<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import megaConfig, { type MegaMenuKey } from '$lib/components/mega-config.ts';


  export let activeMega: MegaMenuKey | null = null;
  export let permissions: {
    canSeeStorageRoots?: boolean;
    canSeeObservability?: boolean;
    canSeeAdmin?: boolean;
  } | null = null;
  export let close: () => void;

  // Items du menu courant
  $: items = activeMega
    ? (megaConfig[activeMega] || []).filter((item) => {
        if (activeMega === 'storageRoots') return permissions?.canSeeStorageRoots === true;
        if (activeMega === 'observability') return permissions?.canSeeObservability === true;
        if (activeMega === 'admin') return permissions?.canSeeAdmin === true;
        return true;
      })
    : [];

  /* ---------------- Keyboard (ESC) ---------------- */
  function onKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape' && activeMega) {
      close();
    }
  }

onMount(() => {
  if (typeof window !== 'undefined') {
    window.addEventListener('keydown', onKeydown);
  }
});

onDestroy(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener('keydown', onKeydown);
  }
});


  /* ---------------- Titles / subtitles ---------------- */
  const titles: Record<MegaMenuKey, { title: string; subtitle: string }> = {
    storageRoots: {
      title: 'Storage Roots',
      subtitle: 'Manage governed storage roots inventory.'
    },
    observability: {
      title: 'Observability',
      subtitle: 'Capsules, jobs and platform monitoring.'
    },
    admin: {
      title: 'Administration',
      subtitle: 'Identity, sources and advanced settings.'
    }
  };
</script>

{#if activeMega}
  <!-- Overlay -->
  <div
    class="mega-overlay animate-overlay"
    role="button"
    tabindex="0"
    aria-label="Close menu"
    on:click={close}
    on:keydown={(e) =>
      (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), close())
    }
  ></div>

  <!-- Mega panel -->
  <div
    class="mega-panel animate-panel"
    role="dialog"
    aria-modal="true"
    tabindex="-1"
    aria-label={titles[activeMega]?.title ?? activeMega}
  >
    <div class="mega-inner">
      <header class="mega-header">
        <h2>{titles[activeMega]?.title ?? activeMega}</h2>
        <p>{titles[activeMega]?.subtitle ?? 'Navigate your workspace.'}</p>
      </header>

      <div class="mega-grid">
        {#each items as item, i (item.href)}
          <a
            href={item.href}
            class="mega-card animate-card"
            style={`--delay: ${i * 30}ms`}
            on:click={close}
          >
            {#if item.icon}
              <div class="mega-icon">
                <i class={`bi ${item.icon}`} aria-hidden="true"></i>
              </div>
            {/if}

            <div class="mega-content">
              <strong>{item.title}</strong>
              <span>{item.description}</span>
            </div>
          </a>
        {/each}
      </div>
    </div>
  </div>
{/if}

<style>
  /* ===============================
     OVERLAY
     =============================== */
  .mega-overlay {
    position: fixed;
    inset: 0;
    background: rgba(2, 6, 23, 0.55);
    backdrop-filter: blur(2px);
    z-index: 90;
  }

  /* ===============================
     PANEL
     =============================== */
  .mega-panel {
    position: fixed;
    top: 64px; /* hauteur topbar */
    left: 0;
    right: 0;
    background: linear-gradient(
      180deg,
      #020617 0%,
      #020617 60%,
      #020617ee 100%
    );
    color: #e5e7eb;
    z-index: 100;
    box-shadow: 0 30px 60px rgba(0, 0, 0, 0.45);
  }

  .mega-inner {
    max-width: 1400px;
    margin: 0 auto;
    padding: 2.25rem 3rem 2.75rem;
  }

  /* ===============================
     HEADER
     =============================== */
  .mega-header h2 {
    margin: 0;
    font-size: 1.6rem;
    font-weight: 700;
    letter-spacing: -0.02em;
  }

  .mega-header p {
    margin-top: 0.35rem;
    font-size: 0.95rem;
    opacity: 0.75;
  }

  /* ===============================
     GRID
     =============================== */
  .mega-grid {
    margin-top: 2.25rem;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 1.25rem;
  }

  /* ===============================
     CARDS
     =============================== */
  .mega-card {
    display: flex;
    gap: 1rem;
    padding: 1.25rem 1.35rem;
    border-radius: 14px;
    text-decoration: none;
    color: inherit;
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(148, 163, 184, 0.15);
    transition:
      background 0.2s ease,
      transform 0.15s ease,
      box-shadow 0.15s ease;
  }

  .mega-card:hover {
    background: rgba(37, 99, 235, 0.25);
    transform: translateY(-2px);
    box-shadow: 0 12px 30px rgba(0, 0, 0, 0.35);
  }

  .mega-icon {
    width: 42px;
    height: 42px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(37, 99, 235, 0.15);
    flex-shrink: 0;
  }

  .mega-icon i {
    font-size: 1.35rem;
    color: #93c5fd;
  }

  .mega-content strong {
    display: block;
    font-size: 0.95rem;
    font-weight: 600;
  }

  .mega-content span {
    display: block;
    margin-top: 0.2rem;
    font-size: 0.82rem;
    opacity: 0.75;
    line-height: 1.25;
  }

  /* ===============================
     ANIMATIONS
     =============================== */
  .animate-overlay {
    animation: overlayFadeIn 160ms ease-out forwards;
  }

  @keyframes overlayFadeIn {
    from {
      opacity: 0;
    }
    to {
      opacity: 1;
    }
  }

  .animate-panel {
    animation: panelSlideIn 220ms cubic-bezier(0.16, 1, 0.3, 1) forwards;
    transform-origin: top center;
  }

  @keyframes panelSlideIn {
    from {
      opacity: 0;
      transform: translateY(-14px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .animate-card {
    opacity: 0;
    transform: translateY(6px);
    animation: cardFadeUp 220ms ease-out forwards;
    animation-delay: var(--delay, 0ms);
  }

  @keyframes cardFadeUp {
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  /* ===============================
     ACCESSIBILITY
     =============================== */
  @media (prefers-reduced-motion: reduce) {
    .animate-overlay,
    .animate-panel,
    .animate-card {
      animation: none !important;
      opacity: 1 !important;
      transform: none !important;
    }
  }
</style>
