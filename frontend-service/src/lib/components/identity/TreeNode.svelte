<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { IdentityTreeNode } from '../../types/identityBrowser';

  export let node: IdentityTreeNode;
  export let level = 0;
  export let activeDn: string | null = null;
  export let expandedDns: Set<string> = new Set();
  export let loadingDns: Set<string> = new Set();

  const dispatch = createEventDispatcher<{
    toggle: { dn: string; expanded: boolean };
    select: { dn: string };
  }>();

  $: isExpanded = expandedDns.has(node.dn);
  $: isLoading = loadingDns.has(node.dn);
  $: isActive = activeDn === node.dn;
  $: isFolder = String(node?.type ?? 'ou').toLowerCase() !== 'group';

  function toggleNode() {
    if (!node?.dn) return;
    dispatch('toggle', { dn: node.dn, expanded: !isExpanded });
  }

  function selectNode() {
    if (!node?.dn) return;
    dispatch('select', { dn: node.dn });
  }
</script>

<div class="idb-tree-node-wrap">
  <div class={`idb-tree-node ${isActive ? 'is-active' : ''}`} style={`padding-left:${12 + level * 24}px;`}>
    {#if node.has_children}
      <button class="idb-tree-toggle" type="button" on:click={toggleNode} aria-label="Toggle node">
        {#if isLoading}
          <span class="spinner-border spinner-border-sm" aria-hidden="true"></span>
        {:else}
          <i class={`bi ${isExpanded ? 'bi-caret-down-fill' : 'bi-caret-right-fill'}`}></i>
        {/if}
      </button>
    {:else}
      <span class="idb-tree-leaf-dot"><i class="bi bi-caret-right-fill"></i></span>
    {/if}

    <button type="button" class="idb-tree-select" on:click={selectNode}>
      <i class={`bi ${isFolder ? (isExpanded ? 'bi-folder2-open' : 'bi-folder2') : 'bi-folder'}`}></i>
      <span class="idb-tree-label text-truncate">{node.name}</span>
    </button>
  </div>

  {#if isExpanded && Array.isArray(node.children) && node.children.length > 0}
    {#each node.children as child (child.dn)}
      <svelte:self
        node={child}
        level={level + 1}
        {activeDn}
        {expandedDns}
        {loadingDns}
        on:toggle
        on:select
      />
    {/each}
  {/if}
</div>

<style>
  .idb-tree-node-wrap + .idb-tree-node-wrap {
    border-top: 1px solid var(--idb-border, #e3e9f3);
  }

  .idb-tree-node {
    min-height: 34px;
    width: 100%;
    border: 0;
    background: transparent;
    color: var(--idb-text, #30435f);
    display: flex;
    align-items: center;
    gap: 10px;
    padding-right: 10px;
    font-size: 14px;
    text-align: left;
  }

  .idb-tree-node:hover {
    background: var(--idb-hover-bg, #f3f7fc);
  }

  .idb-tree-node.is-active {
    background: var(--idb-selected-bg, #eaf2fb);
  }

  .idb-tree-toggle {
    border: 0;
    background: transparent;
    color: var(--idb-text-muted, #6b7f98);
    padding: 0;
    width: 20px;
    height: 20px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex: 0 0 20px;
  }

  .idb-tree-leaf-dot {
    width: 20px;
    color: var(--idb-text-muted, #6b7f98);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex: 0 0 20px;
  }

  .idb-tree-label {
    font-size: 13px;
    font-weight: 500;
  }

  .idb-tree-select {
    border: 0;
    background: transparent;
    color: inherit;
    display: inline-flex;
    align-items: center;
    gap: 10px;
    padding: 0;
    margin: 0;
    width: 100%;
    min-width: 0;
    text-align: left;
    cursor: pointer;
  }

  .idb-tree-select:focus-visible {
    outline: none;
    box-shadow: var(--b2s-focus-ring, 0 0 0 4px rgba(37, 99, 235, 0.18));
    border-radius: 8px;
  }
</style>
