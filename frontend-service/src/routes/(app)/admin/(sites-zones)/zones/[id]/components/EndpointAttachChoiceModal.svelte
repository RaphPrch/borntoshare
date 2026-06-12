<script lang="ts">
  import AppModal from '$lib/components/common/AppModal.svelte';

  type EndpointChoiceItem = {
    id: number;
    name: string;
    host?: string | null;
    zoneName?: string | null;
  };

  export let open = false;
  export let existingEndpoints: EndpointChoiceItem[] = [];
  export let loading = false;
  export let busyAttachId: number | null = null;

  export let onClose: () => void = () => {};
  export let onCreateNew: () => void = () => {};
  export let onAttachExisting: (endpointId: number) => void = () => {};
</script>

<AppModal
  {open}
  {onClose}
  ariaLabelledby="zone-endpoint-choice-title"
  showClose={true}
>
  <section class="z-ep-choice">
    <header class="z-ep-choice__head">
      <h2 id="zone-endpoint-choice-title">Add endpoint</h2>
      <p>Choose whether to create a new endpoint or attach an existing one to this zone.</p>
    </header>

    <div class="z-ep-choice__actions">
      <button type="button" class="zone-console__btn" on:click={onCreateNew}>
        <i class="bi bi-plus-lg"></i>
        Create new endpoint
      </button>
    </div>

    <div class="z-ep-choice__existing">
      <h3>Attach existing endpoint</h3>

      {#if loading}
        <div class="text-muted">Loading endpoints…</div>
      {:else if existingEndpoints.length === 0}
        <div class="text-muted">No existing endpoint available.</div>
      {:else}
        <ul class="z-ep-choice__list">
          {#each existingEndpoints as ep (ep.id)}
            <li>
              <div class="z-ep-choice__meta">
                <strong>{ep.name}</strong>
                <span>{ep.host ?? '—'}</span>
                <span>{ep.zoneName ? `Current zone: ${ep.zoneName}` : 'No zone'}</span>
              </div>
              <button
                type="button"
                class="zone-console__btn-ghost"
                on:click={() => onAttachExisting(ep.id)}
                disabled={busyAttachId === ep.id}
              >
                {busyAttachId === ep.id ? 'Attaching…' : 'Attach'}
              </button>
            </li>
          {/each}
        </ul>
      {/if}
    </div>
  </section>
</AppModal>

<style>
  .z-ep-choice {
    display: grid;
    gap: 14px;
  }

  .z-ep-choice__head h2 {
    margin: 0;
    font-size: 1.15rem;
  }

  .z-ep-choice__head p {
    margin: 6px 0 0;
    color: #64748b;
    font-size: 0.9rem;
  }

  .z-ep-choice__existing h3 {
    margin: 0 0 8px;
    font-size: 1rem;
  }

  .z-ep-choice__list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 8px;
    max-height: 280px;
    overflow: auto;
  }

  .z-ep-choice__list li {
    border: 1px solid #dbe5f2;
    border-radius: 10px;
    padding: 10px 12px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }

  .z-ep-choice__meta {
    display: grid;
    gap: 2px;
    min-width: 0;
  }

  .z-ep-choice__meta span {
    color: #64748b;
    font-size: 0.82rem;
  }
</style>
