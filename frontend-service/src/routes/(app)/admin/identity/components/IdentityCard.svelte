
<script lang="ts">
  import { initialsFromLabel } from '$lib/utils/initials';

  export let identity: any;
  export let onEdit: ((item: any) => void) | null = null;

  const statusIcon = (item: any) =>
    item?.status === "inactive" ? "bi-slash-circle" : "bi-check-circle-fill";

  const roleLabel = (item: any) => {
    if (item?.type === "group") return "Group";
    if (item?.role === "admin") return "Admin";
    if (item?.role === "audit") return "Audit";
    return "User";
  };

  const initials = (value?: string | null) => initialsFromLabel(value, '?');

  const isLocalUser = (item: any) =>
    item?.type === 'user' && String(item?.auth_source ?? item?.source ?? '').toLowerCase() === 'local';

  const sourceLabel = (item: any) => (item?.source === 'local' ? 'LOCAL · Local account' : 'AD · Directory-managed');
</script>

<div class="identity-card">
  <div class="identity-card__top">
    <span
      class="identity-avatar"
      aria-label={identity.display_name}
    >
      {initials(identity.display_name)}
    </span>
    <div class="identity-card__badges">
      <span class={`identity-pill identity-pill--source ${identity?.source === 'local' ? 'is-local' : 'is-ad'}`}>
        <i class={`bi ${identity?.source === 'local' ? 'bi-check-circle' : 'bi-shield'}`}></i>
        {sourceLabel(identity)}
      </span>
      <span class="identity-pill identity-pill--role">{roleLabel(identity)}</span>
    </div>
    <span class="identity-status" class:inactive={identity?.status === 'inactive'}>
      <i class={`bi ${statusIcon(identity)}`}></i>
    </span>
  </div>

  <h3 class="identity-card__title">{identity.display_name}</h3>

  <div class="identity-card__meta">
    <span class="meta-item"><i class="bi bi-clock"></i> Last sign-in: 2 days ago</span>
    {#if identity?.source === 'ad'}
      <span class="meta-item"><i class="bi bi-arrow-repeat"></i> Last AD sync: 2 days ago</span>
    {/if}
  </div>

  {#if isLocalUser(identity)}
    <div class="identity-card__actions">
      <button class="identity-btn primary" on:click={() => onEdit?.(identity)}>
        <i class="bi bi-pencil"></i>
        Edit account
      </button>
    </div>
  {/if}
</div>
