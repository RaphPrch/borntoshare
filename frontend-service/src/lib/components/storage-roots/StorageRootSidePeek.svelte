<script lang="ts">
  import { t } from '$lib/i18n';
  import Drawer from '$lib/components/ui/Drawer.svelte';
  import { fivesEnabled, governanceEnabled } from '$lib/utils/features';
  import { formatBytes, timeAgo } from '$lib/utils/format';
  import type { StorageRootRow } from '$lib/utils/storage-roots';
  import type { FolderMenuExtra } from '$lib/components/storage-roots/StorageRootContextMenu.svelte';

  interface Props {
    /**
     * Preview of a folder on the side of the v2 list: what BornToShare knows of it at a glance (state, volume,
     * quota, 5S, sensitivity, guardians, tags) and its quick actions, without leaving the list.
     */
    row?: StorageRootRow | null;
    score?: number | null;
    isAdmin?: boolean;
    onClose?: () => void;
    onOpen?: (id: number) => void;
    onAnalysis?: ((kind: 'measure' | 'sensitivity', row: StorageRootRow) => void) | null;
    onExtra?: ((key: FolderMenuExtra, row: StorageRootRow) => void) | null;
  }

  let { row = null, score = null, isAdmin = false, onClose = () => {}, onOpen = () => {}, onAnalysis = null, onExtra = null }: Props = $props();

  type R = Record<string, any>;
  let r = $derived((row ?? {}) as R);
  const num = (value: unknown) => (Number.isFinite(Number(value)) ? Number(value) : 0);
  let id = $derived(num(r.storage_root_id));
  let size = $derived(r.content_size_bytes ?? r.estimated_size_bytes ?? null);
  let pct = $derived(r.quota_used_percent == null ? null : num(r.quota_used_percent));
  let tags = $derived((Array.isArray(r.tags) ? r.tags : []) as R[]);
  let guardians = $derived((Array.isArray(r.guardian_names) ? r.guardian_names : []) as string[]);
  let secrets = $derived(num(r.password_files) + num(r.key_files));
  const C = 2 * Math.PI * 42;
  const ringTone = (value: number | null) => (value == null ? '#d5dee6' : value >= 80 ? '#138a5c' : value >= 60 ? '#c27a12' : '#d0435a');
  let sensitivity = $derived(r.sensitive_files == null && !r.sensitivity_status ? t('Not scanned')
    : secrets ? t('{count} password or key file(s)', { count: secrets })
    : num(r.personal_files) ? t('{count} personal data', { count: num(r.personal_files) })
    : t('Nothing found'));
  const run = (key: FolderMenuExtra) => row && onExtra?.(key, row);
</script>

<Drawer open={row != null} {onClose} title={String(r.storage_root_name ?? r.storage_root_code ?? '')}
  subtitle={[r.zone_name, r.storage_endpoint_name].filter(Boolean).join(' › ')} iconClass="bi bi-folder2-open" showFooter={false}>
  {#if row}
    <div class="pk">
      <code class="pk__path">{r.dfs_path ?? r.root_path ?? ''}</code>

      <div class="pk__top">
        <div class="pk__ring" role="img" aria-label={t('5S score {value}', { value: score ?? '—' })}>
          <svg viewBox="0 0 100 100" aria-hidden="true"><circle cx="50" cy="50" r="42" fill="none" stroke="#eaeff3" stroke-width="11" />
            <circle cx="50" cy="50" r="42" fill="none" stroke={ringTone(score)} stroke-width="11" stroke-linecap="round" stroke-dasharray={`${((C * (score ?? 0)) / 100).toFixed(1)} ${C.toFixed(1)}`} /></svg>
          <span>{score ?? '—'}</span>
        </div>
        <dl class="pk__dl">
          <div><dt>{t('Volume')}</dt><dd>{size != null ? formatBytes(num(size)) : '—'}</dd></div>
          <div><dt>{t('Files')}</dt><dd>{r.content_files != null ? num(r.content_files).toLocaleString('fr-FR') : '—'}</dd></div>
          <div><dt>{t('Quota')}</dt><dd>{pct != null ? `${pct} % ${t('of')} ${formatBytes(num(r.quota_limit_bytes))}` : t('None')}</dd></div>
          <div><dt>{t('Measured')}</dt><dd>{r.content_updated_at ? timeAgo(r.content_updated_at) : '—'}</dd></div>
        </dl>
      </div>

      <section class="pk__sec">
        <h3>{t('Quick actions')}</h3>
        <div class="pk__acts">
          {#if isAdmin && onAnalysis}
            <button type="button" class="b2s-btn b2s-btn-primary b2s-btn-sm" onclick={() => row && onAnalysis?.('measure', row)}><i class="bi bi-rulers" aria-hidden="true"></i>{t('Measure')}</button>
            <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" onclick={() => row && onAnalysis?.('sensitivity', row)}><i class="bi bi-shield-lock" aria-hidden="true"></i>{t('Sensitivity')}</button>
          {/if}
          {#if $governanceEnabled}<button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" onclick={() => run('permissions')}><i class="bi bi-key" aria-hidden="true"></i>{t('Permissions')}</button>{/if}
          {#if $fivesEnabled}<a class="b2s-btn b2s-btn-secondary b2s-btn-sm" href={`/five-s/explore/${id}`}><i class="bi bi-columns-gap" aria-hidden="true"></i>{t('Explore')}</a>{/if}
          <button type="button" class="b2s-btn b2s-btn-dark b2s-btn-sm pk__open" onclick={() => onOpen(id)}>{t('Open the folder sheet')}</button>
        </div>
      </section>

      <section class="pk__sec">
        <h3>{t('State')}</h3>
        <ul class="v2-feed">
          <li class="v2-fi"><span class={`v2-dot ${secrets ? 'is-bad' : r.sensitive_files == null ? 'is-mut' : ''}`}></span>
            <span class="v2-fi__t"><b>{t('Sensitivity')}</b><small>{sensitivity}</small></span>
            <button type="button" class="b2s-link-btn v2-fi__r" onclick={() => onOpen(id)}>{t('See')}</button></li>
          <li class="v2-fi"><span class={`v2-dot ${pct != null && pct >= num(r.quota_warn_percent ?? 85) ? 'is-warn' : pct == null ? 'is-mut' : ''}`}></span>
            <span class="v2-fi__t"><b>{t('Quota')}</b><small>{pct != null ? `${pct} %` : t('None')}{num(r.quota_pending_requests) ? ` · ${t('{count} space request(s) waiting', { count: num(r.quota_pending_requests) })}` : ''}</small></span>
            <button type="button" class="b2s-link-btn v2-fi__r" onclick={() => run('quota')}>{t('Manage')}</button></li>
          {#if num(r.open_alerts_count)}
            <li class="v2-fi"><span class="v2-dot is-warn"></span><span class="v2-fi__t"><b>{t('{count} open alert(s)', { count: num(r.open_alerts_count) })}</b><small>{String(r.open_alert_types ?? '').replaceAll(',', ', ')}</small></span></li>
          {/if}
        </ul>
      </section>

      {#if $governanceEnabled}
        <section class="pk__sec">
          <h3>{t('Guardians')}</h3>
          <p class="pk__p">{guardians.length ? guardians.join(', ') : t('None: only the administrators can approve the requests.')}
            <button type="button" class="b2s-link-btn" onclick={() => run('guardians')}>{guardians.length ? t('Manage') : t('+ Add')}</button></p>
        </section>
      {/if}

      <section class="pk__sec">
        <h3>{t('Tags')}</h3>
        <div class="pk__tags">
          {#each tags as tag, index (index)}<span class="pk__tg">{tag.label ?? tag.name ?? tag.tag_name}</span>{/each}
          {#if Array.isArray(r.subfolder_tags)}{#each r.subfolder_tags as name, index (index)}<span class="pk__tg is-auto" title={t('Tags of its sub-folders, set by the policies')}>⚡ {name}</span>{/each}{/if}
          <button type="button" class="b2s-link-btn" onclick={() => run('tags')}>{tags.length ? t('Manage') : t('+ Tag')}</button>
        </div>
      </section>
    </div>
  {/if}
</Drawer>

<style>
  .pk { display: flex; flex-direction: column; gap: 20px; }
  .pk__path { padding: 6px 10px; border-radius: 8px; background: var(--b2s-color-surface-soft); color: var(--b2s-color-text-soft); font-family: var(--b2s-font-mono); font-size: 12px; overflow-wrap: anywhere; }
  .pk__top { display: flex; align-items: center; gap: 20px; }
  .pk__ring { position: relative; width: 100px; height: 100px; flex: none; }
  .pk__ring svg { width: 100%; height: 100%; transform: rotate(-90deg); }
  .pk__ring span { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; font-size: 24px; font-weight: 700; }
  .pk__dl { flex: 1; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px 18px; margin: 0; }
  .pk__dl div { display: flex; flex-direction: column; gap: 2px; padding-bottom: 8px; border-bottom: 1px solid var(--b2s-color-surface-muted); }
  .pk__dl dt { color: var(--b2s-color-text-muted); font-size: 12px; }
  .pk__dl dd { margin: 0; font-weight: 500; }
  .pk__sec { display: flex; flex-direction: column; gap: 8px; }
  .pk__sec h3 { margin: 0; color: var(--b2s-color-text-muted); font-size: 11px; font-weight: 600; letter-spacing: 0.09em; text-transform: uppercase; }
  .pk__acts { display: flex; flex-wrap: wrap; gap: 6px; }
  .pk__open { margin-left: auto; }
  .pk__p { margin: 0; }
  .pk__tags { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
  .pk__tg { padding: 2px 8px; border-radius: 6px; background: var(--b2s-color-surface-muted); color: var(--b2s-color-text-soft); font-size: 12px; font-weight: 600; }
  .pk__tg.is-auto { background: var(--b2s-accent-soft); color: var(--b2s-accent-strong); }
</style>
