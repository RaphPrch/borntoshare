<script lang="ts">
  import { t } from '$lib/i18n';

  type AccessModelRow = {
    level: 'read' | 'write';
    code: string;
    label: string;
    icon: string;
    tone: 'read' | 'write';
    users: number;
    adGroup: string;
    adGroupTone: 'success' | 'pending' | 'warning' | 'neutral';
    groupName?: string | null;
    aclAlignment?: string | null;
    aclPrincipal?: string | null;
  };

  export let rows: AccessModelRow[] = [];
  export let onOpenEffectiveAccess: (level: 'read' | 'write') => void = () => {};
</script>

<table class="b2s-table access-model">
  <thead>
    <tr>
      <th>{t('Profile')}</th>
      <th>{t('AD group')}</th>
      <th>{t('Members')}</th>
      <th><span class="visually-hidden">{t('Actions')}</span></th>
    </tr>
  </thead>
  <tbody>
    {#each rows as profile (profile.level)}
      <tr>
        <td>
          <span class={`access-model__profile is-${profile.tone}`}>
            <i class={profile.icon} aria-hidden="true"></i>
            {profile.label}
          </span>
        </td>
        <td class="access-model__group">{profile.groupName ?? profile.adGroup}</td>
        <td>{profile.users === 1 ? t('1 user') : t('{count} users', { count: profile.users })}</td>
        <td class="access-model__action">
          <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" on:click={() => onOpenEffectiveAccess(profile.level)}>
            {t('Review members')}
          </button>
        </td>
      </tr>
    {/each}
  </tbody>
</table>

<style>
  .access-model__profile {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: 24px;
    padding: 0 10px;
    border: 1px solid #bfdbfe;
    border-radius: var(--b2s-radius-pill);
    background: #eff6ff;
    color: #1d4ed8;
    font-size: var(--b2s-fs-xs);
    font-weight: 500;
    white-space: nowrap;
  }

  .access-model__profile.is-write {
    border-color: #fed7aa;
    background: #fff7ed;
    color: #c2410c;
  }

  .access-model__group {
    font-family: var(--b2s-font-mono);
    font-size: var(--b2s-fs-xs);
    overflow-wrap: anywhere;
  }

  .access-model__action {
    text-align: right;
    white-space: nowrap;
  }
</style>
