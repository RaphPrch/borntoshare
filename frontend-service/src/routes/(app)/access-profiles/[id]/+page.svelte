<script lang="ts">
  export let data: {
    user: any;
    console: import('$lib/types/access-profile-console').AccessProfileConsole;
  };
</script>

<div class="b2s-page">
  <h1>Access Profile</h1>

  <div class="b2s-card">
    <div class="b2s-card__title">{data.console.overview.name ?? data.console.overview.code}</div>
    <div class="b2s-card__subtitle">Code: {data.console.overview.code}</div>
    <div class="b2s-kpis">
      <div class="b2s-kpi">
        <div class="b2s-kpi__value">{data.console.kpis.used_in_roots_count}</div>
        <div class="b2s-kpi__label">Storage Roots</div>
      </div>
      <div class="b2s-kpi">
        <div class="b2s-kpi__value">{data.console.kpis.zones_count}</div>
        <div class="b2s-kpi__label">Zones</div>
      </div>
      <div class="b2s-kpi">
        <div class="b2s-kpi__value">{data.console.kpis.bindings_count}</div>
        <div class="b2s-kpi__label">Bindings</div>
      </div>
    </div>
  </div>

  <div class="b2s-card">
    <div class="b2s-card__title">Bindings</div>
    {#if data.console.bindings.length === 0}
      <p class="muted">No bindings.</p>
    {:else}
      <table class="b2s-table">
        <thead>
          <tr>
            <th>Resource</th>
            <th>Zone</th>
          </tr>
        </thead>
        <tbody>
          {#each data.console.bindings as b}
            <tr>
              <td>{b.resource_type} #{b.resource_id} {b.resource_name ? `· ${b.resource_name}` : ''}</td>
              <td>{b.zone_name ?? '-'}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </div>
</div>
