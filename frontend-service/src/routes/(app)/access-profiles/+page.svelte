  <script lang="ts">
  import type { AccessProfile } from '$lib/api/access-profiles';
  import SearchField from '$lib/components/common/SearchField.svelte';

  export let data: {
    profiles: AccessProfile[];
  };

  const asText = (value: unknown): string => String(value ?? '').trim();

  const ruleFromDb = (profile: AccessProfile): string =>
    asText(profile.access_level_code ?? profile.permission) || '—';

  const normalizedRule = (profile: AccessProfile): 'READ' | 'WRITE' | string => {
    const raw = asText(profile.access_level_code ?? profile.permission ?? ruleFromDb(profile)).toUpperCase();
    if (raw.includes('WRITE')) return 'WRITE';
    if (raw.includes('READ')) return 'READ';
    return raw || 'READ';
  };

  const ruleLabel = (profile: AccessProfile): string => {
    const rule = normalizedRule(profile);
    if (rule === 'READ') return 'Lecture';
    if (rule === 'WRITE') return 'Contribution';
    return rule;
  };

  const updatedAtFromDb = (profile: AccessProfile): string => asText(profile.updated_at) || '—';

  const profileName = (row: AccessProfile): string => {
    const value = asText(row.name ?? row.code);
    return value || `PROFILE_${row.id ?? 'N/A'}`;
  };

  const linksCount = (row: AccessProfile): number => {
    const value = Number(row.used_in_roots_count ?? row.members_count ?? 0);
    return Number.isFinite(value) ? value : 0;
  };

  const profileState = (row: AccessProfile): 'active' | 'inactive' => {
    const status = asText(row.status).toLowerCase();
    if (status) return status === 'active' ? 'active' : 'inactive';
    if (typeof row.is_active === 'boolean') return row.is_active ? 'active' : 'inactive';
    if (typeof row.active === 'boolean') return row.active ? 'active' : 'inactive';
    return 'inactive';
  };

  let search = '';
  let warningMsg = '';

  $: sourceRows = Array.isArray(data?.profiles) ? data.profiles : [];
  $: dedupedSourceRows = (() => {
    const map = new Map<string, AccessProfile>();
    const candidates = sourceRows.filter((row) => {
      const rule = normalizedRule(row);
      return rule === 'READ' || rule === 'WRITE';
    });

    for (const row of candidates) {
      const key = normalizedRule(row);
      const existing = map.get(key);
      if (!existing) {
        map.set(key, row);
        continue;
      }

      const existingActive = profileState(existing) === 'active' ? 1 : 0;
      const rowActive = profileState(row) === 'active' ? 1 : 0;
      if (rowActive > existingActive) {
        map.set(key, row);
        continue;
      }

      const existingTs = new Date(asText(existing.updated_at) || 0).getTime();
      const rowTs = new Date(asText(row.updated_at) || 0).getTime();
      if (rowTs > existingTs) map.set(key, row);
    }

    const keepIds = new Set(Array.from(map.values()).map((r) => Number(r.id ?? 0)));
    return sourceRows.filter((row) => {
      const rule = normalizedRule(row);
      if (rule !== 'READ' && rule !== 'WRITE') return false;
      const id = Number(row.id ?? 0);
      return keepIds.has(id);
    });
  })();

  $: duplicateRules = (() => {
    const counts = new Map<string, number>();
    for (const row of sourceRows) {
      const rule = normalizedRule(row);
      if (rule !== 'READ' && rule !== 'WRITE') continue;
      counts.set(rule, (counts.get(rule) ?? 0) + 1);
    }
    return Array.from(counts.entries()).filter(([, count]) => count > 1).map(([rule]) => rule);
  })();

  $: warningMsg = duplicateRules.length > 0
    ? `Duplicate profiles detected for rule(s): ${duplicateRules.join(', ')}. Only one profile per READ/WRITE is now displayed.`
    : '';

  $: q = search.trim().toLowerCase();
  $: rows = dedupedSourceRows.filter((row) => {
    if (!q) return true;
    return [
      profileName(row),
      ruleFromDb(row),
      asText(row.description),
      asText(row.status),
      asText(row.updated_at),
      asText(row.code)
    ]
      .join(' ')
      .toLowerCase()
      .includes(q);
  });

</script>

<section class="ap-shell" aria-labelledby="ap-main-title">
  <aside class="ap-sidebar">
    <h1>Access Profiles</h1>

    <SearchField
      wrapperClass="ap-side-search"
      inputClass="ap-side-search-input"
      placeholder="Search an access profile..."
      ariaLabel="Search in access profile menu"
      bind:value={search}
    />

    <nav aria-label="Access profiles side navigation">
      <a class="ap-side-item is-active" href="/access-profiles">
        <i class="bi bi-folder2-open" aria-hidden="true"></i>
        <span>Access Profiles</span>
      </a>
    </nav>
  </aside>

  <div class="ap-main">
    <header class="ap-head">
      <div style="display:flex; align-items:center; gap:.65rem;"></div>
    </header>

    <section class="ap-content" aria-label="Access profiles content">
      <h2 id="ap-main-title">Access Profiles</h2>
      <p>Profils V1 visibles : <strong>READ (Lecture)</strong> et <strong>WRITE (Contribution)</strong>.</p>

      {#if warningMsg}
        <div class="ap-alert ap-alert--warning">{warningMsg}</div>
      {/if}

      <div class="ap-toolbar">
        <SearchField
          wrapperClass="ap-search"
          inputClass="ap-search-input"
          placeholder="Search an access profile..."
          ariaLabel="Search access profiles"
          bind:value={search}
        />
      </div>

      <div class="ap-table-wrap">
        <table class="ap-table">
          <thead>
            <tr>
              <th>Profile</th>
              <th>Links</th>
              <th>Rules</th>
              <th>Last Updated</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {#if rows.length === 0}
              <tr>
                <td colspan="5" class="ap-empty">No READ/WRITE profile found.</td>
              </tr>
            {:else}
              {#each rows as row (row.id)}
                <tr>
                  <td>
                    <div class="ap-profile-cell">
                      <span class="ap-profile-pill">{profileName(row)}</span>
                      <span class="ap-permission-chip">{ruleLabel(row)}</span>
                    </div>
                  </td>
                  <td>
                    <div class="ap-links">
                      <i class="bi bi-link-45deg" aria-hidden="true"></i>
                      <strong>{linksCount(row)}</strong>
                    </div>
                  </td>
                  <td>{ruleLabel(row)}</td>
                  <td>{updatedAtFromDb(row)}</td>
                  <td>
                    <span class={`ap-status ${profileState(row) === 'active' ? 'is-active' : 'is-inactive'}`}>
                      {profileState(row) === 'active' ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                </tr>
              {/each}
            {/if}
          </tbody>
        </table>

        <footer class="ap-table-footer">
          <span>{rows.length} result(s)</span>
          <span class="ap-v1-note">Single-page V1 listing</span>
        </footer>
      </div>
    </section>
  </div>
</section>

<style>
  :global(.b2s-app-main) {
    background: #f5f7fd;
  }

  .ap-shell {
    display: grid;
    grid-template-columns: 312px minmax(0, 1fr);
    min-height: calc(100vh - 72px);
    background: #f5f7fd;
    color: #10204f;
  }

  .ap-sidebar {
    border-right: 1px solid #d8deed;
    padding: 1.25rem 1rem;
    background: linear-gradient(180deg, #f1f4fb 0%, #eef2fb 100%);
  }

  .ap-sidebar h1 {
    margin: 0 0 1rem;
    font-size: 2.1rem;
    line-height: 1.1;
    letter-spacing: -0.02em;
    font-weight: 700;
  }

  :global(.ap-side-search) {
    display: flex;
    align-items: center;
    gap: 0.625rem;
    padding: 0.7rem 0.8rem;
    border: 1px solid #d2d8e7;
    border-radius: 14px;
    background: #ffffff;
    color: #64739a;
    margin-bottom: 0.85rem;
  }

  :global(.ap-side-search input),
  :global(.ap-side-search-input) {
    border: none;
    outline: none;
    width: 100%;
    background: transparent;
    color: #13285f;
    font-size: 1rem;
  }

  .ap-side-item {
    display: flex;
    align-items: center;
    gap: 0.65rem;
    color: #2c3d6d;
    text-decoration: none;
    padding: 0.7rem 0.7rem;
    border-radius: 12px;
    font-size: 1.04rem;
    margin-bottom: 0.3rem;
    border: 1px solid transparent;
  }

  .ap-side-item.is-active {
    background: #dfe8ff;
    color: #2050cc;
    border-color: #c5d5ff;
  }

  .ap-main {
    padding: 1.35rem 1.4rem 2rem;
  }

  .ap-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid #d8deed;
    padding-bottom: 0.6rem;
    margin-bottom: 0.7rem;
  }

  .ap-new-btn {
    display: inline-flex;
    align-items: center;
    gap: 0.6rem;
    border: none;
    border-radius: 14px;
    background: var(--b2s-topbar-bg, #0b1530);
    color: #fff;
    font-weight: 700;
    padding: 0.8rem 1.4rem;
    font-size: 1.12rem;
  }

  .ap-new-btn:hover,
  .ap-new-btn:active,
  .ap-new-btn:focus-visible {
    background: var(--b2s-topbar-bg, #0b1530);
    color: #fff;
  }

  .ap-content h2 {
    margin: 0;
    font-size: 3rem;
    letter-spacing: -0.02em;
    font-weight: 700;
  }

  .ap-content > p {
    margin: 0.35rem 0 1rem;
    color: #42598f;
    font-size: 1.1rem;
  }

  .ap-alert {
    border-radius: 12px;
    border: 1px solid transparent;
    padding: 0.7rem 0.95rem;
    margin-bottom: 0.9rem;
    font-size: 1rem;
  }

  .ap-alert--error {
    color: #8f2030;
    background: #fdecef;
    border-color: #f7c9d1;
  }

  .ap-alert--success {
    color: #1f6b45;
    background: #e8f6ee;
    border-color: #bfe2cc;
  }

  .ap-alert--warning {
    color: #7a4b00;
    background: #fff5e5;
    border-color: #f2d4a1;
  }

  .ap-toolbar {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 0.8rem;
  }

  :global(.ap-search) {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 0.65rem;
    border: 1px solid #d5dcec;
    border-radius: 14px;
    background: #fff;
    padding: 0.7rem 0.9rem;
    color: #6576a3;
  }

  :global(.ap-search input),
  :global(.ap-search-input) {
    border: none;
    outline: none;
    width: 100%;
    font-size: 1.05rem;
    color: #11255f;
    background: transparent;
  }

  .ap-filter-btn {
    border: 1px solid #d4daea;
    border-radius: 12px;
    background: #f7f9fe;
    color: #1b2f67;
    padding: 0.68rem 1rem;
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    font-size: 1rem;
    font-weight: 600;
  }

  .ap-table-wrap {
    border: 1px solid #d5dcea;
    border-radius: 16px;
    background: #fff;
    overflow: hidden;
  }

  .ap-table {
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
  }

  .ap-table th,
  .ap-table td {
    padding: 1rem 1.1rem;
    border-bottom: 1px solid #e4e9f3;
    text-align: left;
    color: #1a2f66;
    font-size: 0.97rem;
    vertical-align: middle;
  }

  .ap-table th {
    font-weight: 700;
    color: #172d63;
  }

  .ap-profile-cell {
    display: flex;
    align-items: flex-start;
    flex-direction: column;
    gap: 0.5rem;
  }

  .ap-profile-pill {
    display: inline-flex;
    align-items: center;
    border-radius: 10px;
    border: 1px solid #a8bde8;
    background: #dce6fa;
    padding: 0.15rem 0.55rem;
    font-size: 1.05rem;
    font-weight: 700;
    color: #1a2d62;
  }

  .ap-permission-chip {
    display: inline-flex;
    align-items: center;
    border-radius: 999px;
    background: #e7ebf7;
    color: #62729d;
    font-size: 0.79rem;
    font-weight: 700;
    padding: 0.12rem 0.58rem;
    line-height: 1.1;
  }

  .ap-links {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
  }

  .ap-status {
    display: inline-flex;
    align-items: center;
    border-radius: 10px;
    border: 1px solid;
    padding: 0.12rem 0.58rem;
    font-size: 0.95rem;
    font-weight: 600;
  }

  .ap-status.is-active {
    color: #2c7a4d;
    border-color: #b9e2cb;
    background: #e7f6ee;
  }

  .ap-status.is-inactive {
    color: #7a4551;
    border-color: #e9c1cb;
    background: #f8e9ed;
  }

  .ap-empty {
    text-align: center;
    color: #63759f;
  }

  .ap-table-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.8rem 1rem;
    color: #2a3f75;
    font-size: 1.02rem;
    background: #fbfcff;
  }

  .ap-v1-note {
    font-size: 0.9rem;
    color: #6274a3;
  }

  @media (max-width: 1200px) {
    .ap-shell {
      grid-template-columns: 1fr;
    }

    .ap-sidebar {
      border-right: none;
      border-bottom: 1px solid #d8deed;
    }

    .ap-table {
      table-layout: auto;
    }
  }

  @media (max-width: 900px) {
    .ap-head {
      flex-direction: column;
      align-items: flex-start;
      gap: 0.6rem;
    }

    .ap-toolbar {
      flex-direction: column;
      align-items: stretch;
    }

    .ap-table-wrap {
      overflow-x: auto;
    }
  }

  .ap-create-overlay {
    position: fixed;
    inset: 0;
    background: rgba(13, 23, 54, 0.38);
    backdrop-filter: blur(1px);
    display: grid;
    place-items: center;
    z-index: 120;
    padding: 1rem;
  }

  .ap-create-modal {
    position: relative;
    width: min(1260px, 100%);
    max-height: calc(100vh - 2rem);
    overflow: auto;
    border: 1px solid #d7ddec;
    border-radius: 20px;
    background: #f4f6fc;
    box-shadow: 0 28px 80px rgba(16, 30, 72, 0.28);
    padding: 1.35rem 1.35rem 1.6rem;
  }

  .ap-create-close {
    position: absolute;
    top: 0.9rem;
    right: 0.9rem;
    width: 38px;
    height: 38px;
    border-radius: 10px;
    border: 1px solid #d5dced;
    background: #fff;
    color: #304474;
  }

  .ap-create-modal h2 {
    margin: 0;
    color: #11265d;
    font-weight: 700;
    font-size: 2.25rem;
    letter-spacing: -0.02em;
  }

  .ap-create-sub {
    margin: 0.32rem 0 1rem;
    color: #40568a;
    font-size: 1rem;
  }

  .ap-create-grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 375px;
    gap: 1rem;
    align-items: start;
  }

  .ap-create-card {
    border: 1px solid #d5dbea;
    border-radius: 16px;
    background: #fff;
    overflow: hidden;
  }

  .ap-create-error {
    margin: 0.9rem 1rem 0;
    border: 1px solid #efc2cb;
    background: #fdecef;
    color: #842432;
    border-radius: 10px;
    padding: 0.55rem 0.7rem;
    font-size: 0.93rem;
  }

  .ap-create-block {
    padding: 1.1rem 1.1rem 1rem;
  }

  .ap-create-block h3 {
    margin: 0 0 0.7rem;
    font-size: 1.35rem;
    color: #13275f;
  }

  .ap-create-block label {
    display: block;
    margin-bottom: 0.38rem;
    font-size: 1.05rem;
    color: #152a62;
    font-weight: 700;
  }

  .ap-create-block input,
  .ap-create-block select {
    width: 100%;
    height: 42px;
    border-radius: 11px;
    border: 1px solid #c8d2e6;
    background: #f9fbff;
    color: #2a3f73;
    padding: 0 0.9rem;
    font-size: 1.02rem;
    margin-bottom: 0.95rem;
    outline: none;
  }

  .ap-create-divider {
    border-top: 1px solid #dce2f0;
  }

  .ap-rule {
    width: 100%;
    border: none;
    border-top: 1px solid #dce2ef;
    background: transparent;
    display: flex;
    align-items: flex-start;
    gap: 0.8rem;
    text-align: left;
    padding: 0.8rem 0.1rem;
    color: #1f3265;
  }

  .ap-rule:first-of-type {
    border-top: none;
  }

  .ap-rule-check {
    width: 24px;
    height: 24px;
    border: 1px solid #afbddb;
    border-radius: 6px;
    display: inline-grid;
    place-items: center;
    color: transparent;
    flex-shrink: 0;
    margin-top: 0.08rem;
    background: #f4f7fd;
  }

  .ap-rule-check.is-on {
    background: #2f60d7;
    border-color: #2f60d7;
    color: #fff;
  }

  .ap-rule strong {
    display: block;
    font-size: 1.15rem;
    color: #152a61;
    margin-bottom: 0.2rem;
  }

  .ap-rule small {
    display: block;
    color: #445b8f;
    font-size: 1rem;
    line-height: 1.45;
  }

  .ap-rule.is-disabled {
    margin-top: 0.2rem;
    border: 1px solid #e0e5f1;
    border-radius: 10px;
    background: #f4f6fb;
    padding: 0.72rem 0.62rem;
    opacity: 0.78;
  }

  .ap-create-actions {
    border-top: 1px solid #dce2ef;
    display: flex;
    align-items: center;
    gap: 0.65rem;
    padding: 1rem 1.1rem;
  }

  .ap-create-btn,
  .ap-cancel-btn {
    height: 48px;
    border-radius: 12px;
    padding: 0 1.35rem;
    font-size: 1.05rem;
    font-weight: 600;
    border: 1px solid #c9d4e8;
  }

  .ap-create-btn {
    background: linear-gradient(180deg, #2d63df 0%, #2556c8 100%);
    color: #fff;
    border-color: #2b5fd7;
  }

  .ap-create-btn:disabled {
    opacity: 0.55;
  }

  .ap-cancel-btn {
    background: #f3f6fc;
    color: #273d73;
  }

  .ap-summary {
    border: 1px solid #d5dbea;
    border-radius: 16px;
    background: #fff;
    overflow: hidden;
  }

  .ap-summary-head {
    font-size: 1.25rem;
    color: #162a61;
    font-weight: 700;
    padding: 0.9rem 1rem;
    border-bottom: 1px solid #dde3f0;
  }

  .ap-summary-body {
    padding: 0.7rem 1rem;
    color: #33497d;
    font-size: 1rem;
    border-bottom: 1px solid #dde3f0;
  }

  .ap-summary-body p {
    margin: 0 0 0.44rem;
  }

  .ap-summary-body strong {
    color: #5d75ac;
    font-weight: 500;
  }

  .ap-summary-rules {
    padding: 0.8rem 1rem 1rem;
    color: #33497d;
  }

  .ap-summary-rules h4 {
    margin: 0 0 0.6rem;
    font-size: 1.15rem;
    color: #172b63;
  }

  .ap-summary-chip {
    display: inline-flex;
    align-items: center;
    border-radius: 11px;
    border: 1px solid #bdd0f5;
    background: #e4edff;
    color: #2f57b2;
    font-size: 0.9rem;
    font-weight: 700;
    padding: 0.2rem 0.75rem;
  }

  .ap-summary-rules ul {
    margin: 0.65rem 0 0;
    padding-left: 1.2rem;
  }

  .ap-summary-rules li {
    font-size: 0.98rem;
    color: #344b7f;
    line-height: 1.45;
  }

  @media (max-width: 1080px) {
    .ap-create-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
