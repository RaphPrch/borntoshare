<script lang="ts">
  import { t } from '$lib/i18n';
  import { initials, timeAgo } from '$lib/utils/format';
  import EntityActionButton from '$lib/components/entity/EntityActionButton.svelte';
  import StorageRootDrawerShell from '$lib/components/storage-roots/StorageRootDrawerShell.svelte';

  export let open = false;
  export let title = t('Users with Access');
  export let contextLabel = t('Storage • — • —');
  export let membersCount = 0;
  export let level: 'read' | 'write' = 'read';
  // Rows of effectiveAccessUsersByLevel (storage-root-detail.mapper); every field is optional
  export let users: Array<Record<string, unknown>> = [];
  export let onAddUser: () => void = () => {};
  export let onClose: () => void = () => {};

  const label = (u: any) => String(u?.display_name ?? u?.username ?? u?.email ?? u?.upn ?? t('Identity #{value}', { value: (u?.identity_id ?? '?') }));
  const mail = (u: any) => String(u?.email ?? u?.upn ?? '—');


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
    <div class="sr-ea-context">{t('{membersCount} members resolved in effective access ({toUpperCase})', { membersCount, toUpperCase: level.toUpperCase() })}</div>
    <div class="sr-ea-topline">
      <strong>{t('{membersCount} Members', { membersCount })}</strong>
      <span class="sr-ea-operational"><i class="bi bi-check-circle-fill"></i> {t('Operational')}</span>
    </div>
  </section>

  <section class="sr-ea-panel">
    <div class="sr-ea-panel-title">{t('{membersCount} Members', { membersCount })}</div>
    {#if users.length === 0}
      <div class="sr-ea-empty">{t('No resolved users.')}</div>
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
              <span>{timeAgo(String(u?.assigned_at ?? u?.created_at ?? '') || null) || '—'}</span>
            </div>
          </article>
        {/each}
      </div>
    {/if}
  </section>

  <svelte:fragment slot="footer">
    <div class="sr-modal-actions sr-ea-footer-actions">
      <EntityActionButton variant="secondary" label={t('Close')} onClick={onClose} />
      <EntityActionButton variant="primary" icon="bi-plus-lg" label={t('Add user')} onClick={onAddUser} />
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

  .sr-ea-footer-actions :global(.b2s-btn) {
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

    .sr-ea-footer-actions :global(.b2s-btn) {
      width: 100%;
    }
  }
</style>
