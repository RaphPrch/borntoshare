<script lang="ts">
  import EntityActionButton from '$lib/components/common/EntityActionButton.svelte';
  import StorageRootDrawerShell from '$lib/components/storage-roots/StorageRootDrawerShell.svelte';
  import { timeAgo } from '$lib/utils/timeAgo';

  export let open = false;
  export let title = 'Users with Access';
  export let contextLabel = 'Storage • — • —';
  export let membersCount = 0;
  export let level: 'read' | 'write' = 'read';
  export let users: Array<{
    identity_id: number;
    display_name?: string | null;
    username?: string | null;
    email?: string | null;
    upn?: string | null;
    access_level?: 'read' | 'write' | string;
    created_at?: string | null;
    assigned_at?: string | null;
  }> = [];
  export let onAddUser: () => void = () => {};
  export let onClose: () => void = () => {};

  const label = (u: any) => String(u?.display_name ?? u?.username ?? u?.email ?? u?.upn ?? `Identity #${u?.identity_id ?? '?'}`);
  const mail = (u: any) => String(u?.email ?? u?.upn ?? '—');

  const initials = (value: string) =>
    value
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((p) => p[0]?.toUpperCase() ?? '')
      .join('') || 'U';

  const toneClass = (index: number) => ['indigo', 'violet', 'rose', 'orange', 'cyan'][index % 5];

</script>

<StorageRootDrawerShell
  open={open}
  onClose={onClose}
  title={title}
  subtitle={`${contextLabel} · ${level.toUpperCase()}`}
  ariaLabelledby="sr-effective-access-title"
  width="560px"
  topOffset="70px"
  showFooter={true}
>
  <section class="sr-ea-topbar">
    <div class="sr-ea-context">{membersCount} members resolved in effective access ({level.toUpperCase()})</div>
    <div class="sr-ea-topline">
      <strong>{membersCount} Members</strong>
      <span class="sr-ea-operational"><i class="bi bi-check-circle-fill"></i> Operational</span>
    </div>
  </section>

  <section class="sr-ea-panel">
    <div class="sr-ea-panel-title">{membersCount} Members</div>
    {#if users.length === 0}
      <div class="sr-ea-empty">No resolved users.</div>
    {:else}
      <div class="sr-ea-list">
        {#each users as u, idx}
          <article class="sr-ea-row">
            <span class={`sr-ea-avatar ${toneClass(idx)}`}>{initials(label(u))}</span>
            <div class="sr-ea-main">
              <strong>{label(u)}</strong>
              <small>{mail(u)}</small>
            </div>
            <div class="sr-ea-right">
              <span>{timeAgo(u?.assigned_at ?? u?.created_at ?? null) || '—'}</span>
              <button class="sr-ea-icon" type="button" aria-label="Remove" disabled>
                <i class="bi bi-trash"></i>
              </button>
            </div>
          </article>
        {/each}
      </div>
    {/if}
  </section>

  <svelte:fragment slot="footer">
    <div class="sr-modal-actions sr-ea-footer-actions">
      <EntityActionButton compact={true} variant="secondary" label="Close" onClick={onClose} />
      <EntityActionButton compact={true} variant="primary" icon="bi-plus-lg" label="Add user" onClick={onAddUser} />
    </div>
  </svelte:fragment>
</StorageRootDrawerShell>

<style>
  .sr-ea-panel,
  .sr-ea-topbar {
    margin: 0;
  }

  .sr-ea-topbar {
    padding: 0 0 14px;
    border-bottom: 1px solid #e3e8f2;
  }

  .sr-ea-context {
    color: #667085;
    font-size: 14px;
    font-weight: 500;
  }

  .sr-ea-topline {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 8px;
  }

  .sr-ea-topline strong {
    color: #1f2a44;
    font-size: 16px;
    font-weight: 700;
  }

  .sr-ea-operational {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    color: #157f57;
    font-size: 13px;
    font-weight: 600;
  }

  .sr-ea-operational i {
    color: #169b62;
  }

  .sr-ea-panel {
    margin-top: 14px;
    border: 1px solid #dfe6f2;
    border-radius: 12px;
    background: #fff;
  }

  .sr-ea-panel-title {
    padding: 12px 14px;
    border-bottom: 1px solid #e7edf7;
  }

  .sr-ea-panel-title {
    color: #2e436b;
    font-size: 14px;
    font-weight: 700;
  }

  .sr-ea-link {
    border: none;
    background: transparent;
    padding: 0;
    color: #255ac2;
    font-size: 13px;
    font-weight: 700;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    cursor: pointer;
  }

  .sr-ea-list {
    display: grid;
  }

  .sr-ea-row {
    display: grid;
    grid-template-columns: 42px 1fr auto;
    align-items: center;
    gap: 12px;
    padding: 10px 12px;
    border-top: 1px solid #e7ecf6;
  }

  .sr-ea-row:first-child {
    border-top: none;
  }

  .sr-ea-avatar {
    width: 36px;
    height: 36px;
    border-radius: 999px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: #fff;
    font-size: 12px;
    font-weight: 700;
  }

  .sr-ea-avatar.indigo {
    background: linear-gradient(180deg, #616ee3, #4d57bf);
  }

  .sr-ea-avatar.violet {
    background: linear-gradient(180deg, #c27ac5, #a860ab);
  }

  .sr-ea-avatar.rose {
    background: linear-gradient(180deg, #e0728f, #cf516f);
  }

  .sr-ea-avatar.orange {
    background: linear-gradient(180deg, #e08a5a, #cd6f43);
  }

  .sr-ea-avatar.cyan {
    background: linear-gradient(180deg, #30a9c0, #2b8ea2);
  }

  .sr-ea-main {
    min-width: 0;
    display: grid;
    gap: 2px;
  }

  .sr-ea-main strong {
    color: #1f3156;
    font-size: 14px;
    line-height: 1.2;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .sr-ea-main strong span {
    font-weight: 600;
    color: #304770;
  }

  .sr-ea-main small {
    color: #53698e;
    font-size: 12px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .sr-ea-right {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    color: #4a618c;
    font-size: 12px;
    white-space: nowrap;
  }

  .sr-ea-icon {
    width: 28px;
    height: 28px;
    border: none;
    border-radius: 8px;
    background: transparent;
    color: #5c6f93;
  }

  .sr-ea-empty {
    padding: 14px;
    color: #61759d;
    font-size: 13px;
    font-weight: 600;
  }

  .sr-ea-footer-actions {
    width: 100%;
    display: flex;
    justify-content: flex-end;
    gap: 10px;
  }

  .sr-ea-footer-actions :global(.sed-btn) {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    min-height: 38px;
  }

  @media (max-width: 760px) {
    .sr-ea-topline {
      flex-wrap: wrap;
    }

    .sr-ea-footer-actions {
      display: grid;
      grid-template-columns: 1fr;
    }

    .sr-ea-footer-actions :global(.sed-btn) {
      width: 100%;
    }
  }
</style>
