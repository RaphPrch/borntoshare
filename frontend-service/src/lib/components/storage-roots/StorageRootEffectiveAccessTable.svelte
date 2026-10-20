<script lang="ts">
  import { t } from '$lib/i18n';
  import { formatDate, initials } from '$lib/utils/format';
  import type {
    StorageRootEffectiveAccessUser,
    StorageRootProjectedAdGroup
  } from '$lib/types/storage-roots';

  export let users: StorageRootEffectiveAccessUser[] = [];
  export let projectedGroups: StorageRootProjectedAdGroup[] = [];
  export let aclFreshness: Record<string, unknown> | null = null;
  export let onRescanAcl: (() => void) | null = null;
  export let rescanBusy = false;

  let search = '';
  let sourceFilter = 'all';
  let accessFilter = 'all';
  let page = 1;
  let selectedGroupRow: StorageRootEffectiveAccessUser | null = null;

  const PAGE_SIZE = 8;

  const text = (value: unknown): string => String(value ?? '').trim();
  const norm = (value: unknown): string => text(value).toLowerCase();

  const displayName = (user: StorageRootEffectiveAccessUser): string =>
    text(user.display_name) || text(user.username) || text(user.upn) || text(user.principal) || t('Identity {value}', { value: (user.identity_id ?? 'unknown') });


  const accessLevel = (user: StorageRootEffectiveAccessUser): 'read' | 'write' | 'unknown' => {
    const level = norm(user.access_level);
    if (level === 'read' || level === 'write') return level;
    return 'unknown';
  };

  const rowKey = (user: StorageRootEffectiveAccessUser, index = 0): string =>
    text(user.row_id) || `${text(user.source ?? user.access_source)}:${text(user.principal)}:${text(user.identity_id)}:${index}`;

  const members = (user: StorageRootEffectiveAccessUser): StorageRootEffectiveAccessUser[] =>
    Array.isArray(user.members) ? user.members : [];

  const isGroupRow = (user: StorageRootEffectiveAccessUser): boolean => {
    const principalType = norm(user.principal_type);
    return sourceKey(user) === 'acl' && (
      Boolean(user.is_acl_group) ||
      principalType.includes('group') ||
      Array.isArray(user.members)
    );
  };

  const openMembersDrawer = (user: StorageRootEffectiveAccessUser) => {
    selectedGroupRow = user;
  };

  const closeMembersDrawer = () => {
    selectedGroupRow = null;
  };

  const sourceKey = (user: StorageRootEffectiveAccessUser): 'request' | 'inherited' | 'manual' | 'acl' | 'unknown' => {
    const key = norm(user.access_source ?? user.source);
    if (key === 'request') return 'request';
    if (key === 'inherited') return 'inherited';
    if (key === 'manual') return 'manual';
    if (key === 'acl') return 'acl';
    return 'unknown';
  };

  const sourceLabel = (source: string): string => {
    if (source === 'request') return t('Request');
    if (source === 'inherited') return t('AD group');
    if (source === 'manual') return t('Manual');
    if (source === 'acl') return 'ACL';
    return t('Unknown');
  };

  const accessLabel = (level: string): string => {
    if (level === 'read') return t('Read');
    if (level === 'write') return t('Write');
    return t('Unknown');
  };

  const grantedAtLabel = (user: StorageRootEffectiveAccessUser): string => {
    if (sourceKey(user) === 'inherited') return t('AD group membership');
    if (sourceKey(user) === 'acl') return t('Filesystem ACL');
    return formatDate(user.granted_at ?? user.assigned_at ?? user.created_at);
  };

  const grantedByLabel = (user: StorageRootEffectiveAccessUser): string =>
    text(user.granted_by_display_name) || text(user.granted_by) || '—';

  const memberLogin = (member: StorageRootEffectiveAccessUser): string =>
    text(member.username) || text(member.upn) || text(member.email) || text(member.principal) || '—';

  const memberSource = (member: StorageRootEffectiveAccessUser): string => {
    if (text(member.identity_source_name)) return text(member.identity_source_name);
    if (text(member.identity_source_id)) return t('AD source #{text}', { text: text(member.identity_source_id) });
    if (text(member.snapshot_id ?? member.directory_snapshot_id)) return t('AD snapshot #{text}', { text: text(member.snapshot_id ?? member.directory_snapshot_id) });
    return sourceLabel(sourceKey(member));
  };

  const groupPath = (member: StorageRootEffectiveAccessUser, group: StorageRootEffectiveAccessUser | null): string =>
    text(member.acl_parent_principal) || text(group?.principal) || text(group?.display_name) || '—';

  const matches = (user: StorageRootEffectiveAccessUser): boolean => {
    const haystack = [
      displayName(user),
      user.username,
      user.upn,
      user.email,
      user.principal,
      user.raw_acl,
      accessLabel(accessLevel(user)),
      sourceLabel(sourceKey(user))
    ]
      .map(norm)
      .join(' ');

    const q = norm(search);
    if (q && !haystack.includes(q)) return false;
    if (sourceFilter !== 'all' && sourceKey(user) !== sourceFilter) return false;
    if (accessFilter !== 'all' && accessLevel(user) !== accessFilter) return false;
    return true;
  };

  const normalizePrincipal = (value: unknown): string => {
    const raw = norm(value).replaceAll('/', '\\');
    const chunks = raw.split('\\').filter(Boolean);
    return chunks[chunks.length - 1] ?? raw;
  };

  const projectedGroupName = (group: StorageRootProjectedAdGroup): string => text(group.group_name);

  $: filteredUsers = users.filter(matches);
  $: pageCount = Math.max(1, Math.ceil(filteredUsers.length / PAGE_SIZE));
  $: if (page > pageCount) page = pageCount;
  $: if (page < 1) page = 1;
  $: visibleUsers = filteredUsers.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  $: startIndex = filteredUsers.length > 0 ? (page - 1) * PAGE_SIZE + 1 : 0;
  $: endIndex = Math.min(page * PAGE_SIZE, filteredUsers.length);
  $: aclRows = users.filter((user) => sourceKey(user) === 'acl');
  $: governedRows = users.filter((user) => sourceKey(user) === 'request' || sourceKey(user) === 'manual');
  $: inheritedRows = users.filter((user) => sourceKey(user) === 'inherited');
  $: governedGroupSet = new Set(
    projectedGroups
      .map(projectedGroupName)
      .map(normalizePrincipal)
      .filter(Boolean)
  );
  $: expandableAclGroups = aclRows.filter((user) => isGroupRow(user) && members(user).length > 0).length;
  $: unresolvedAclRows = aclRows.filter((user) => !isGroupRow(user) && !text(user.identity_id)).length;
  $: aclState = norm(aclFreshness?.state);
  $: aclScannedAtRaw = text(aclFreshness?.scanned_at ?? aclFreshness?.discovered_at);
  $: aclSnapshotId = text(aclFreshness?.active_snapshot_id);
</script>

<article class="sr-effective-access-table" aria-label={t('Effective access table')}>
  <div class={`sr-effective-access-table__freshness is-${aclState || 'unknown'}`}>
    {#if onRescanAcl}
      <button type="button" on:click={onRescanAcl} disabled={rescanBusy}>
        <i class={`bi ${rescanBusy ? 'bi-hourglass-split' : 'bi-arrow-repeat'}`} aria-hidden="true"></i>
        {rescanBusy ? t('Scanning...') : t('Rescan ACL')}
      </button>
    {/if}
  </div>

  <div class="sr-effective-access-table__toolbar">
    <label class="sr-effective-access-table__search">
      <i class="bi bi-search" aria-hidden="true"></i>
      <input bind:value={search} type="search" placeholder={t('Search users or teams...')} aria-label={t('Search users or teams')} />
    </label>

    <label class="sr-effective-access-table__select-label">
      {t('Source')}
      <select bind:value={sourceFilter} aria-label={t('Filter by source')}>
        <option value="all">{t('All sources')}</option>
        <option value="request">{t('Request')}</option>
        <option value="manual">{t('Manual')}</option>
        <option value="inherited">{t('AD group')}</option>
        <option value="acl">{t('Filesystem ACL')}</option>
        <option value="unknown">{t('Unknown')}</option>
      </select>
    </label>

    <label class="sr-effective-access-table__select-label">
      {t('Access level')}
      <select bind:value={accessFilter} aria-label={t('Filter by access level')}>
        <option value="all">{t('All levels')}</option>
        <option value="read">{t('Read')}</option>
        <option value="write">{t('Write')}</option>
        <option value="unknown">{t('Unknown')}</option>
      </select>
    </label>
  </div>

  <div class="sr-effective-access-table__frame">
    <table>
      <thead>
        <tr>
          <th>{t('Name')}</th>
          <th>{t('Access level')}</th>
          <th>{t('Source')}</th>
          <th>{t('Access granted')}</th>
          <th>{t('Granted by')}</th>
          <th class="is-actions">{t('Actions')}</th>
        </tr>
      </thead>
      <tbody>
        {#if visibleUsers.length === 0}
          <tr>
            <td colspan="6" class="sr-effective-access-table__empty">{t('No effective access found for this storage root.')}</td>
          </tr>
        {:else}
          {#each visibleUsers as user, index (rowKey(user, index))}
            {@const name = displayName(user)}
            {@const level = accessLevel(user)}
            {@const source = sourceKey(user)}
            <tr class:has-children={isGroupRow(user)}>
              <td>
                <div class="sr-effective-access-table__identity">
                  {#if isGroupRow(user)}
                    <button
                      type="button"
                      class="sr-effective-access-table__expand"
                      aria-label={t('Show members for {name}', { name })}
                      on:click={() => openMembersDrawer(user)}
                    >
                      <i class="bi bi-chevron-right" aria-hidden="true"></i>
                    </button>
                  {/if}
                  <span>{initials(name)}</span>
                  <div class="sr-effective-access-table__identity-text">
                    <strong>{name}</strong>
                    {#if source === 'acl' && text(user.principal)}
                      <small>{user.principal}</small>
                    {/if}
                  </div>
                </div>
              </td>
              <td>
                <span class={`sr-effective-access-table__pill is-access-${level}`}>{accessLabel(level)}</span>
              </td>
              <td>
                <span class={`sr-effective-access-table__pill is-source-${source}`}>{sourceLabel(source)}</span>
              </td>
              <td>{grantedAtLabel(user)}</td>
              <td>{grantedByLabel(user)}</td>
              <td class="is-actions">
                <button type="button" aria-label={t('More actions for {name}', { name })}>
                  <i class="bi bi-three-dots-vertical" aria-hidden="true"></i>
                </button>
              </td>
            </tr>
          {/each}
        {/if}
      </tbody>
    </table>
  </div>

  <footer class="sr-effective-access-table__footer">
      <span>{t('Showing {startIndex} to {endIndex} of {filteredUsersCount} entries', { startIndex, endIndex, filteredUsersCount: filteredUsers.length })}</span>
      <div class="sr-effective-access-table__pagination" aria-label={t('Effective access pagination')}>
        <button type="button" disabled={page <= 1} on:click={() => (page -= 1)} aria-label={t('Previous page')}>
          <i class="bi bi-chevron-left" aria-hidden="true"></i>
        </button>
        <strong>{page}</strong>
        <button type="button" disabled={page >= pageCount} on:click={() => (page += 1)} aria-label={t('Next page')}>
          <i class="bi bi-chevron-right" aria-hidden="true"></i>
        </button>
      </div>
    </footer>

  {#if selectedGroupRow}
    {@const groupMembers = members(selectedGroupRow)}
    {@const groupName = displayName(selectedGroupRow)}
    <div class="sr-effective-access-table__drawer-backdrop" role="presentation" on:click={closeMembersDrawer}></div>
    <aside class="sr-effective-access-table__drawer" aria-label={t('Members of {groupName}', { groupName })}>
      <header>
        <div>
          <span class="sr-effective-access-table__drawer-avatar"><i class="bi bi-people" aria-hidden="true"></i></span>
          <div>
            <h3>{groupName}</h3>
            <p>{text(selectedGroupRow.principal) || t('Directory group')} · {groupMembers.length} {groupMembers.length === 1 ? 'user' : 'users'}</p>
          </div>
        </div>
        <button type="button" aria-label={t('Close group members')} on:click={closeMembersDrawer}>
          <i class="bi bi-x-lg" aria-hidden="true"></i>
        </button>
      </header>

      {#if groupMembers.length === 0}
        <div class="sr-effective-access-table__drawer-empty">
          <i class="bi bi-person-x" aria-hidden="true"></i>
          <strong>{t('No effective users found')}</strong>
          <span>{t('This group has no resolved user members in the current snapshot data.')}</span>
        </div>
      {:else}
        <div class="sr-effective-access-table__drawer-list">
          {#each groupMembers as member, memberIndex (rowKey(member, memberIndex))}
            {@const memberName = displayName(member)}
            <article class="sr-effective-access-table__drawer-member">
              <span>{initials(memberName)}</span>
              <div>
                <strong>{memberName}</strong>
                <dl>
                  <div><dt>{t('Login')}</dt><dd>{memberLogin(member)}</dd></div>
                  <div><dt>{t('Type')}</dt><dd>{t('User')}</dd></div>
                  <div><dt>{t('Source')}</dt><dd>{memberSource(member)}</dd></div>
                  <div><dt>{t('Path')}</dt><dd>{groupPath(member, selectedGroupRow)}</dd></div>
                </dl>
              </div>
            </article>
          {/each}
        </div>
      {/if}
    </aside>
  {/if}
</article>

<style>
  .sr-effective-access-table {
    border: 1px solid #dde6f3;
    border-radius: var(--b2s-radius-md);
    background: #fff;
    box-shadow: 0 14px 34px rgba(15, 31, 61, 0.05);
    overflow: hidden;
  }

  .sr-effective-access-table__freshness {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 14px;
    padding: 12px 16px;
    border-bottom: 1px solid #e4ebf5;
    background: #f8fbff;
  }

  .sr-effective-access-table__freshness button {
    height: 34px;
    border: 1px solid #c9dcff;
    border-radius: var(--b2s-radius-sm);
    background: #fff;
    color: #0a5de8;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: var(--b2s-fs-xs);
    font-weight: 800;
    padding: 0 12px;
    white-space: nowrap;
  }

  .sr-effective-access-table__freshness button:disabled {
    cursor: not-allowed;
    opacity: 0.65;
  }

  .sr-effective-access-table__toolbar {
    display: grid;
    grid-template-columns: minmax(220px, 1fr) auto auto;
    gap: 12px;
    align-items: center;
    padding: 14px 16px;
    border-bottom: 1px solid #e4ebf5;
  }

  .sr-effective-access-table__search,
  .sr-effective-access-table__select-label select {
    height: 42px;
    border: 1px solid #dce5f2;
    border-radius: var(--b2s-radius-sm);
    background: #fff;
    color: #142747;
  }

  .sr-effective-access-table__search {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 0 13px;
  }

  .sr-effective-access-table__search i {
    color: #657895;
  }

  .sr-effective-access-table__search input {
    width: 100%;
    min-width: 0;
    border: 0;
    outline: 0;
    background: transparent;
    color: #142747;
    font-size: var(--b2s-fs-md);
  }

  .sr-effective-access-table__select-label {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    color: #415574;
    font-size: var(--b2s-fs-sm);
    font-weight: 700;
  }

  .sr-effective-access-table__select-label select {
    min-width: 126px;
    padding: 0 34px 0 13px;
    font-size: var(--b2s-fs-sm);
    font-weight: 600;
  }

  .sr-effective-access-table__frame {
    overflow-x: auto;
  }

  .sr-effective-access-table table {
    width: 100%;
    min-width: 820px;
    border-collapse: collapse;
  }

  .sr-effective-access-table th,
  .sr-effective-access-table td {
    padding: 13px 16px;
    border-bottom: 1px solid #e8eef7;
    color: #162747;
    font-size: var(--b2s-fs-sm);
    text-align: left;
    vertical-align: middle;
  }

  .sr-effective-access-table th {
    background: #fbfcff;
    color: #445878;
    font-size: var(--b2s-fs-xs);
    font-weight: 800;
  }

  .sr-effective-access-table tbody tr:hover {
    background: #f8fbff;
  }

  .sr-effective-access-table tbody tr.has-children {
    background: #fbfdff;
  }

  .sr-effective-access-table__identity {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
  }

  .sr-effective-access-table__expand {
    width: 26px;
    height: 26px;
    border: 1px solid #dbe5f2;
    border-radius: var(--b2s-radius-sm);
    background: #fff;
    color: #12345f;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex: 0 0 auto;
  }

  .sr-effective-access-table__expand:hover {
    background: #eef5ff;
  }

  .sr-effective-access-table__identity span {
    width: 30px;
    height: 30px;
    border-radius: var(--b2s-radius-pill);
    background: rgba(77, 163, 255, 0.12);
    color: var(--b2s-topbar-bg, #111b3f);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: var(--b2s-fs-xs);
    font-weight: 800;
    flex: 0 0 auto;
  }

  .sr-effective-access-table__identity strong {
    color: #102243;
    font-weight: 750;
  }

  .sr-effective-access-table__identity-text {
    min-width: 0;
    display: grid;
    gap: 2px;
  }

  .sr-effective-access-table__identity-text small {
    max-width: 260px;
    overflow: hidden;
    color: #657895;
    font-size: var(--b2s-fs-xs);
    font-weight: 600;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .sr-effective-access-table__pill {
    min-width: 64px;
    min-height: 24px;
    border-radius: var(--b2s-radius-sm);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0 10px;
    font-size: var(--b2s-fs-xs);
    font-weight: 800;
  }

  .sr-effective-access-table__pill.is-access-read,
  .sr-effective-access-table__pill.is-source-request {
    border: 1px solid #c9dcff;
    background: #edf4ff;
    color: #0a5de8;
  }

  .sr-effective-access-table__pill.is-access-write {
    border: 1px solid #bfebd3;
    background: #e7f8ee;
    color: #087b3a;
  }

  .sr-effective-access-table__pill.is-source-inherited {
    border: 1px solid #e0ccff;
    background: #f2eaff;
    color: #7838d8;
  }

  .sr-effective-access-table__pill.is-source-manual {
    border: 1px solid #cbd5e1;
    background: #f3f6fb;
    color: #475569;
  }

  .sr-effective-access-table__pill.is-source-acl {
    border: 1px solid #ffd5a8;
    background: #fff5e8;
    color: #a65300;
  }

  .sr-effective-access-table__pill.is-access-unknown,
  .sr-effective-access-table__pill.is-source-unknown {
    border: 1px solid #d8e0ec;
    background: #f7f9fc;
    color: #607087;
  }

  .sr-effective-access-table .is-actions {
    width: 76px;
    text-align: right;
  }

  .sr-effective-access-table .is-actions button {
    width: 32px;
    height: 32px;
    border: 0;
    border-radius: var(--b2s-radius-sm);
    background: transparent;
    color: #102243;
  }

  .sr-effective-access-table .is-actions button:hover {
    background: #eef4ff;
  }

  .sr-effective-access-table__drawer-backdrop {
    position: fixed;
    inset: 0;
    z-index: 60;
    background: rgba(10, 20, 40, 0.28);
  }

  .sr-effective-access-table__drawer {
    position: fixed;
    inset: 0 0 0 auto;
    z-index: 61;
    width: min(520px, 100vw);
    background: #fff;
    border-left: 1px solid #dce5f2;
    box-shadow: -18px 0 42px rgba(15, 31, 61, 0.18);
    display: grid;
    grid-template-rows: auto 1fr;
  }

  .sr-effective-access-table__drawer header {
    min-width: 0;
    border-bottom: 1px solid #e4ebf5;
    padding: 18px;
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
  }

  .sr-effective-access-table__drawer header > div {
    min-width: 0;
    display: flex;
    gap: 12px;
    align-items: flex-start;
  }

  .sr-effective-access-table__drawer h3 {
    margin: 0;
    color: #102243;
    font-size: var(--b2s-fs-xl);
    font-weight: 800;
  }

  .sr-effective-access-table__drawer p {
    margin: 4px 0 0;
    color: #607087;
    font-size: var(--b2s-fs-sm);
    font-weight: 650;
  }

  .sr-effective-access-table__drawer header button {
    width: 36px;
    height: 36px;
    border: 1px solid #dbe5f2;
    border-radius: var(--b2s-radius-sm);
    background: #fff;
    color: #12345f;
  }

  .sr-effective-access-table__drawer-avatar {
    width: 42px;
    height: 42px;
    border-radius: var(--b2s-radius-md);
    background: #eef5ff;
    color: #0a5de8;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex: 0 0 auto;
  }

  .sr-effective-access-table__drawer-list {
    min-height: 0;
    overflow: auto;
    padding: 14px 18px 18px;
    display: grid;
    gap: 10px;
    align-content: start;
  }

  .sr-effective-access-table__drawer-member {
    border: 1px solid #e4ebf5;
    border-radius: var(--b2s-radius-sm);
    background: #fff;
    display: flex;
    gap: 12px;
    align-items: flex-start;
    padding: 12px;
  }

  .sr-effective-access-table__drawer-member > span {
    width: 34px;
    height: 34px;
    border-radius: var(--b2s-radius-pill);
    background: #edf5ff;
    color: #17437a;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: var(--b2s-fs-xs);
    font-weight: 800;
    flex: 0 0 auto;
  }

  .sr-effective-access-table__drawer-member strong {
    color: #102243;
    font-size: var(--b2s-fs-sm);
    font-weight: 800;
  }

  .sr-effective-access-table__drawer-member dl {
    margin: 8px 0 0;
    display: grid;
    gap: 5px;
  }

  .sr-effective-access-table__drawer-member dl div {
    display: grid;
    grid-template-columns: 70px minmax(0, 1fr);
    gap: 8px;
  }

  .sr-effective-access-table__drawer-member dt {
    color: #607087;
    font-size: var(--b2s-fs-xs);
    font-weight: 750;
  }

  .sr-effective-access-table__drawer-member dd {
    margin: 0;
    min-width: 0;
    color: #162747;
    font-size: var(--b2s-fs-xs);
    font-weight: 650;
    overflow-wrap: anywhere;
  }

  .sr-effective-access-table__drawer-empty {
    margin: 28px 18px;
    border: 1px dashed #d6e2f2;
    border-radius: var(--b2s-radius-sm);
    min-height: 180px;
    display: grid;
    place-items: center;
    align-content: center;
    gap: 8px;
    color: #607087;
    text-align: center;
    padding: 24px;
  }

  .sr-effective-access-table__drawer-empty i {
    color: #8aa0bd;
    font-size: 26px;
  }

  .sr-effective-access-table__drawer-empty strong {
    color: #102243;
    font-size: var(--b2s-fs-md);
  }

  @media (max-width: 840px) {

    .sr-effective-access-table__freshness {
      align-items: stretch;
      flex-direction: column;
    }

    .sr-effective-access-table__toolbar {
      grid-template-columns: 1fr;
    }
  }

  .sr-effective-access-table__empty {
    height: 130px;
    color: #657895;
    text-align: center;
  }

  .sr-effective-access-table__footer {
    min-height: 58px;
    padding: 0 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    color: #526782;
    font-size: var(--b2s-fs-sm);
  }

  .sr-effective-access-table__pagination {
    display: inline-flex;
    align-items: center;
    gap: 8px;
  }

  .sr-effective-access-table__pagination button,
  .sr-effective-access-table__pagination strong {
    width: 36px;
    height: 36px;
    border: 1px solid #dbe5f2;
    border-radius: var(--b2s-radius-sm);
    background: #fff;
    color: #173259;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  .sr-effective-access-table__pagination strong {
    border-color: var(--b2s-topbar-accent, #4da3ff);
    background: #eef5ff;
    color: var(--b2s-topbar-bg, #111b3f);
  }

  .sr-effective-access-table__pagination button:disabled {
    opacity: 0.5;
  }

  @media (max-width: 1100px) {
    .sr-effective-access-table__toolbar {
      grid-template-columns: 1fr 1fr;
    }
  }
</style>
