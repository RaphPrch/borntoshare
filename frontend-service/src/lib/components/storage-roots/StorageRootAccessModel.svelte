<script lang="ts">
  import EntityActionButton from '$lib/components/common/EntityActionButton.svelte';

  type AccessModelRow = {
    level: 'read' | 'write';
    code: string;
    label: string;
    icon: string;
    tone: 'read' | 'write';
    users: number;
    adGroup: string;
    adGroupTone: 'success' | 'pending' | 'warning';
    groupName?: string | null;
    aclAlignment?: string | null;
    aclPrincipal?: string | null;
  };

  export let rows: AccessModelRow[] = [];
  export let onOpenEffectiveAccess: (level: 'read' | 'write') => void = () => {};
  export let onConfigureAccessProfile: () => void = () => {};

  const alignmentLabel = (profile: AccessModelRow): string => {
    const alignment = String(profile.aclAlignment ?? '').trim().toLowerCase();
    if (alignment === 'present') return 'ACL aligned';
    if (alignment === 'missing') return 'ACL missing';
    return 'No ACL scan';
  };

  const alignmentTone = (profile: AccessModelRow): 'success' | 'warning' | 'pending' => {
    const alignment = String(profile.aclAlignment ?? '').trim().toLowerCase();
    if (alignment === 'present') return 'success';
    if (alignment === 'missing') return 'warning';
    return 'pending';
  };
</script>

<div class="storage-root-access-model">
  {#each rows as profile (profile.level)}
    <div class="storage-root-access-row">
      <div class="storage-root-access-profile">
        <span class={`storage-root-access-icon is-${profile.tone}`}><i class={profile.icon}></i></span>
        <div>
          <strong>{profile.code}</strong>
          <small>{profile.label}</small>
        </div>
      </div>

      <div class="storage-root-access-cell">
        <span>Members</span>
        <strong>{profile.users} {profile.users === 1 ? 'user' : 'users'}</strong>
      </div>

      <div class="storage-root-access-cell">
        <span>Access</span>
        <strong><i class="bi bi-diagram-3" aria-hidden="true"></i> {profile.groupName ?? profile.adGroup}</strong>
      </div>

      <div class="storage-root-access-actions">
        <EntityActionButton
          variant="secondary"
          icon="bi-people"
          label="Review members"
          onClick={() => onOpenEffectiveAccess(profile.level)}
        />
      </div>
    </div>
  {/each}
</div>

<style>
  .storage-root-access-model {
    max-width: 100%;
    min-width: 0;
    display: grid;
    gap: 0;
  }

  .storage-root-access-row {
    box-sizing: border-box;
    width: 100%;
    min-width: 0;
    min-height: 74px;
    display: grid;
    grid-template-columns: minmax(170px, 1fr) minmax(88px, 0.4fr) minmax(150px, 0.8fr) minmax(140px, 0.55fr);
    align-items: center;
    gap: 14px;
    border: 1px solid #edf1f7;
    padding: 12px 14px;
    background: #fff;
  }

  .storage-root-access-row:first-child {
    border-radius: 8px 8px 0 0;
  }

  .storage-root-access-row:last-child {
    border-radius: 0 0 8px 8px;
  }

  .storage-root-access-row + .storage-root-access-row {
    border-top: 0;
  }

  .storage-root-access-profile {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
  }

  .storage-root-access-profile strong {
    display: block;
    color: var(--b2s-color-text, #1f2a44);
    font-size: 14px;
    font-weight: 700;
  }

  .storage-root-access-profile small {
    display: block;
    color: var(--b2s-color-text-muted, #667085);
    font-size: 13px;
  }

  .storage-root-access-icon {
    width: 38px;
    height: 38px;
    border-radius: 8px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 18px;
    flex: 0 0 auto;
  }

  .storage-root-access-icon.is-read {
    color: #3168d4;
    background: #e8effd;
  }

  .storage-root-access-icon.is-write {
    color: #bf7a1a;
    background: #fff0dc;
  }

  .storage-root-access-cell {
    min-width: 0;
    display: grid;
    gap: 3px;
  }

  .storage-root-access-cell span {
    color: #64748b;
    font-size: 13px;
    font-weight: 650;
  }

  .storage-root-access-cell strong {
    color: #10203f;
    font-size: 12px;
    font-weight: 650;
    min-width: 0;
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }

  .storage-root-access-cell strong.is-success {
    color: #087b3a;
  }

  .storage-root-access-cell strong.is-warning {
    color: #a65300;
  }

  .storage-root-access-cell strong.is-pending {
    color: #607087;
  }

  .storage-root-access-actions {
    min-width: 0;
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: 8px;
    width: 100%;
  }

  .storage-root-access-row :global(.sed-btn) {
    min-height: 36px;
    padding: 7px 11px;
    font-size: 12px;
    min-width: 0;
    white-space: normal;
    flex: 1 1 100%;
    max-width: 100%;
    justify-content: center;
  }

  .storage-root-access-row :global(.sed-btn--secondary) {
    border-color: #ccd8ea;
    color: #233f66;
    background: #fff;
  }

  @media (max-width: 760px) {
    .storage-root-access-row {
      grid-template-columns: minmax(0, 1fr);
      align-items: start;
    }
  }
</style>
