<script lang="ts">
  import { goto, invalidateAll } from '$app/navigation';
  import { page } from '$app/stores';
  import { onDestroy } from 'svelte';
  import { normalizeMe } from '$lib/auth/me';
  import { bulkDecision, getAccessRequestDetails } from '$lib/api/access-requests';
  import NewAccessRequestModal from '$lib/components/access-requests/NewAccessRequestModal.svelte';
  import { toast } from '$lib/utils/toast';
  import { initialsFromLabel } from '$lib/utils/initials';
  import {
    mapAccessRequestDecisionError,
    mapAccessRequestDecisionErrorFromBulk
  } from '$lib/utils/request-decision-errors';
  import {
    accessRequestAccessLabel,
    accessRequestId,
    accessRequestRequesterName,
    accessRequestTargetLabel,
    accessRequestTargetPath
  } from '$lib/services/mappers/access-requests.mapper';

  export let data: {
    requests: any[];
    tabCounts?: Record<string, number>;
    statusFilter?: string;
    query?: string;
    me?: unknown;
    navigation?: {
      guardianRootIds?: number[];
    };
  };

  type ReviewTab = 'mine' | 'guardians';
  type QueueKey = 'mine' | 'guardians' | 'all' | 'todo' | 'waiting' | 'done';

  let selectedRequestId: number | null = null;
  let selectedRequestDetail: any | null = null;
  let detailLoading = false;
  let detailError = '';
  let detailLoadToken = 0;
  let decisionComment = '';
  let decisionRunning: 'approve' | 'reject' | null = null;
  let showCreateRequestModal = false;
  let createPrefillStorageRootId: number | null = null;
  let createPrefillAccessLevel: string | null = null;
  let requestParamId: number | null = null;
  let lastAutoSelectedRequestId: number | null = null;
  let searchTimer: ReturnType<typeof setTimeout> | null = null;
  let searchText = data.query ?? '';
  let activeTab: ReviewTab = data.statusFilter === 'pending' || !data.statusFilter ? 'mine' : 'mine';
  let activeQueue: QueueKey = data.statusFilter === 'all'
    ? 'all'
    : ['approved', 'enforced', 'rejected', 'revoked'].includes(data.statusFilter || '')
      ? 'done'
      : 'mine';

  $: requests = data.requests ?? [];
  $: me = normalizeMe(data.me);
  $: guardianRootIds = Array.isArray(data.navigation?.guardianRootIds)
    ? data.navigation?.guardianRootIds.map((value) => Number(value)).filter((value) => Number.isFinite(value) && value > 0)
    : [];
  $: canReviewAny = me?.is_admin === true || guardianRootIds.length > 0;
  $: tabCounts = data.tabCounts ?? {};
  $: pendingRequests = requests.filter((request) => isPending(request));
  $: visibleRequests = visibleRowsForQueue(requests, pendingRequests, activeQueue, activeTab).filter(matchesSearch);
  $: selectedRequest = selectedRequestId
    ? selectedRequestDetail ?? requests.find((request) => accessRequestId(request) === selectedRequestId) ?? null
    : null;
  $: pageRequests = visibleRequests.slice(0, 6);
  $: rangeLabel = visibleRequests.length === 0
    ? '0–0 sur 0'
    : `1–${Math.min(6, visibleRequests.length)} sur ${visibleRequests.length}`;
  $: sidebarCounts = buildSidebarCounts(requests, tabCounts);
  $: kpis = buildKpis(requests, tabCounts);
  $: canReviewSelectedRequest = Boolean(selectedRequest) && isReviewAllowed(selectedRequest);
  $: pageTitle = canReviewAny ? "Validation des requêtes d'accès" : "Mes demandes d'accès";
  $: pageSubtitle = canReviewAny
    ? "Examinez et décidez les demandes d'accès gouvernées."
    : "Consultez l'état et l'historique de vos demandes d'accès.";
  $: {
    const openCreate = String($page.url.searchParams.get('create') ?? '').toLowerCase();
    showCreateRequestModal = openCreate === '1' || openCreate === 'true';
    const prefillRootId = Number($page.url.searchParams.get('root') ?? 0);
    createPrefillStorageRootId = Number.isFinite(prefillRootId) && prefillRootId > 0 ? prefillRootId : null;
    const prefillAccessLevel = String($page.url.searchParams.get('permission') ?? '').trim();
    createPrefillAccessLevel = prefillAccessLevel || null;
    const targetRequestId = Number($page.url.searchParams.get('request') ?? 0);
    requestParamId = Number.isFinite(targetRequestId) && targetRequestId > 0 ? targetRequestId : null;
  }

  $: if (!requestParamId) {
    lastAutoSelectedRequestId = null;
  }

  $: if (
    requestParamId &&
    requestParamId !== lastAutoSelectedRequestId
  ) {
    const target = requests.find((request) => accessRequestId(request) === requestParamId);
    if (target) {
      lastAutoSelectedRequestId = requestParamId;
      selectRequest(target);
    } else {
      lastAutoSelectedRequestId = requestParamId;
      selectedRequestId = requestParamId;
      selectedRequestDetail = null;
      detailError = '';
      decisionComment = '';
      void loadRequestDetail(requestParamId);
    }
  }

  const norm = (value: unknown): string => String(value ?? '').trim().toLowerCase();
  const compactText = (value: unknown, fallback = '—'): string => String(value ?? '').trim() || fallback;

  function isPending(row: any): boolean {
    const status = norm(row?.status ?? row?.workflow_status ?? row?.decision_status);
    return !status || status.includes('pending') || status.includes('waiting') || status.includes('review');
  }

  function stageText(_row: any): string {
    return 'Guardian review';
  }

  function filterRequestsForTab(rows: any[], tab: ReviewTab): any[] {
    if (tab === 'guardians') return rows;
    return rows;
  }

  function visibleRowsForQueue(rows: any[], pendingRows: any[], queue: QueueKey, tab: ReviewTab): any[] {
    if (queue === 'all') return rows;
    if (queue === 'done') return rows.filter((row) => !isPending(row));
    return filterRequestsForTab(pendingRows, tab);
  }

  function matchesSearch(row: any): boolean {
    const q = norm(searchText);
    if (!q) return true;
    return [requesterName(row), requesterDepartment(row), resourceName(row), resourceZone(row), accessShort(row), stageText(row)]
      .map(norm)
      .join(' ')
      .includes(q);
  }

  function buildSidebarCounts(rows: any[], counts: Record<string, number>) {
    const pending = rows.filter(isPending);
    const guardian = pending.length;
    const approved = Number(counts.approved ?? 0) + Number(counts.enforced ?? 0);
    const rejected = Number(counts.rejected ?? 0) + Number(counts.revoked ?? 0);
    return {
      mine: pending.length || Number(counts.pending ?? 0),
      guardians: guardian,
      all: rows.length,
      todo: pending.length || Number(counts.pending ?? 0),
      waiting: 0,
      done: approved + rejected
    };
  }

  function buildKpis(rows: any[], counts: Record<string, number>) {
    const pending = rows.filter(isPending);
    const guardian = pending.length;
    return {
      guardian: guardian || Number(counts.pending ?? 0),
      approved: Number(counts.approved ?? 0) + Number(counts.enforced ?? 0)
    };
  }

  function isReviewAllowed(row: any): boolean {
    if (me?.is_admin === true) return true;
    const storageRootId = storageRootIdFromRow(row);
    return storageRootId != null && guardianRootIds.includes(storageRootId);
  }

  function requesterName(row: any): string {
    return accessRequestRequesterName(row);
  }

  function requesterDepartment(row: any): string {
    return compactText(
      row?.requested_for_department ??
        row?.requester_department ??
        row?.department ??
        row?.requested_principal_json?.department ??
        row?.requested_principal?.department,
      '—'
    );
  }

  function resourceName(row: any): string {
    return accessRequestTargetLabel(row);
  }

  function resourceZone(row: any): string {
    const zone = compactText(row?.zone_name ?? row?.zone_code ?? row?.storage_zone_name ?? row?.site_name, '');
    if (!zone) return '—';
    return zone.startsWith('Zone') ? zone : `Zone ${zone}`;
  }

  function resourcePath(row: any): string {
    const explicit = compactText(row?.root_path ?? row?.target_path ?? row?.resource_path, '');
    if (explicit && explicit !== '—') return explicit;
    const targetPath = accessRequestTargetPath(row);
    if (targetPath && targetPath !== '—') return targetPath;
    return '—';
  }

  function accessShort(row: any): string {
    const label = accessRequestAccessLabel(row);
    if (norm(label).includes('write')) return 'Écriture';
    if (norm(label).includes('contributor') || norm(label).includes('contribution')) return 'Contributeur';
    if (norm(label).includes('read')) return 'Lecture';
    return label;
  }

  function ttlDays(row: any): number {
    const direct = Number(row?.ttl_days ?? row?.duration_days ?? 0);
    if (Number.isFinite(direct) && direct > 0) return Math.round(direct);
    const expires = row?.expires_at ? new Date(String(row.expires_at)).getTime() : NaN;
    const created = row?.created_at ? new Date(String(row.created_at)).getTime() : Date.now();
    if (Number.isFinite(expires)) return Math.max(1, Math.ceil((expires - created) / 86400000));
    return 0;
  }

  function expiryLabel(row: any): string {
    const expires = row?.expires_at ? new Date(String(row.expires_at)) : null;
    if (expires && Number.isFinite(expires.getTime())) {
      return `${ttlDays(row)} jours (jusqu'au ${expires.toLocaleDateString('fr-FR')})`;
    }
    const ttl = ttlDays(row);
    return ttl > 0 ? `${ttl} jours` : '—';
  }

  function requestedAt(row: any): string {
    const raw = row?.created_at ?? row?.requested_at ?? row?.submitted_at;
    const date = raw ? new Date(String(raw)) : null;
    if (!date || !Number.isFinite(date.getTime())) return '—';
    return `${date.toLocaleDateString('fr-FR')} à ${date.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}`;
  }

  function requestedDateParts(row: any): { date: string; time: string } {
    const label = requestedAt(row);
    if (label === '—') return { date: '—', time: '' };
    const [date, timeRaw] = label.split(' à ');
    return { date: date || '—', time: timeRaw || '' };
  }

  function justification(row: any): string {
    return compactText(
      row?.justification ?? row?.business_justification ?? row?.reason,
      '—'
    );
  }

  function selectRequest(row: any): void {
    const id = accessRequestId(row);
    selectedRequestId = id;
    selectedRequestDetail = row;
    detailError = '';
    decisionComment = '';
    void loadRequestDetail(id);
  }

  async function loadRequestDetail(id: number): Promise<void> {
    if (!id) return;
    const token = ++detailLoadToken;
    detailLoading = true;
    try {
      const detail = await getAccessRequestDetails(fetch, id);
      if (token === detailLoadToken && selectedRequestId === id) {
        selectedRequestDetail = detail;
      }
    } catch {
      if (token === detailLoadToken) {
        detailError = "Le détail complet n'a pas pu être chargé.";
      }
    } finally {
      if (token === detailLoadToken) {
        detailLoading = false;
      }
    }
  }

  function openQueue(key: QueueKey): void {
    activeQueue = key;
    if (key === 'guardians') activeTab = 'guardians';
    if (key === 'mine' || key === 'todo') activeTab = 'mine';
    const statusByQueue: Partial<Record<QueueKey, string>> = {
      all: 'all',
      done: 'approved',
      mine: 'pending',
      todo: 'pending',
      guardians: 'pending',
      waiting: 'pending'
    };
    const params = new URLSearchParams($page.url.searchParams);
    params.set('status', statusByQueue[key] ?? 'pending');
    const qs = params.toString();
    goto(`/access-requests${qs ? `?${qs}` : ''}`, { replaceState: true, noScroll: true, keepFocus: true });
  }

  function switchTab(tab: ReviewTab): void {
    activeTab = tab;
    activeQueue = tab === 'mine' ? 'mine' : tab;
    const params = new URLSearchParams($page.url.searchParams);
    params.set('status', 'pending');
    const qs = params.toString();
    goto(`/access-requests${qs ? `?${qs}` : ''}`, { replaceState: true, noScroll: true, keepFocus: true });
  }

  function iconForAccess(row: any): string {
    const access = norm(accessShort(row));
    if (access.includes('écriture') || access.includes('write')) return 'bi-shield-check';
    if (access.includes('contrib')) return 'bi-person-gear';
    return 'bi-file-earmark-lock';
  }

  async function runDecision(decision: 'approve' | 'reject'): Promise<void> {
    if (!selectedRequest || decisionRunning) return;
    const id = accessRequestId(selectedRequest);
    if (!id) return;

    decisionRunning = decision;
    try {
      const comment = decisionComment.trim();
      const result = await bulkDecision(fetch, [id], decision, comment || undefined);
      const failed = Number(result?.failed_ids?.length ?? 0);
      if (failed > 0) {
        const mapped = decision === 'approve'
          ? mapAccessRequestDecisionErrorFromBulk(result, { fallbackStorageRootId: storageRootIdFromRow(selectedRequest) })
          : mapAccessRequestDecisionError({
              detail: result?.failed_details?.[id] ?? null,
              reason: result?.failed_reasons?.[id] ?? null,
              fallbackStorageRootId: storageRootIdFromRow(selectedRequest)
            });
        detailError = mapped.message;
        toast.error(mapped.message);
        if (mapped.hint) toast.info(mapped.hint);
        return;
      }

      detailError = '';
      toast.success(decision === 'approve' ? 'Requête approuvée.' : 'Requête refusée.');
      selectedRequestId = null;
      decisionComment = '';
      await invalidateAll();
    } catch {
      toast.error(decision === 'approve' ? "L'approbation a échoué." : 'Le refus a échoué.');
    } finally {
      decisionRunning = null;
    }
  }

  function storageRootIdFromRow(row: any): number | null {
    const direct = Number(row?.storage_root_id ?? row?.target_id ?? 0);
    if (Number.isFinite(direct) && direct > 0) return direct;
    return null;
  }

  function closeDetail(): void {
    selectedRequestId = null;
    selectedRequestDetail = null;
    detailError = '';
    detailLoading = false;
    decisionComment = '';
    detailLoadToken += 1;
  }

  async function closeCreateRequestModal(): Promise<void> {
    showCreateRequestModal = false;
    const params = new URLSearchParams($page.url.searchParams);
    params.delete('create');
    const qs = params.toString();
    await goto(`/access-requests${qs ? `?${qs}` : ''}`, { replaceState: true, noScroll: true, keepFocus: true });
  }

  async function handleAccessRequestCreated(): Promise<void> {
    await closeCreateRequestModal();
    await invalidateAll();
  }

  function timelineEvents(row: any): Array<{ label: string; meta: string; state: 'done' | 'current' | 'waiting' }> {
    const raw = Array.isArray(row?.timeline) ? row.timeline : [];
    if (raw.length > 0) {
      const validationEvents = raw.filter((event: any, index: number) => {
        const eventType = norm(event?.event_type ?? event?.type ?? event?.action);
        const message = typeof event?.message === 'string' ? event.message.trim() : '';
        const isTechnicalSubmit = index === 0 && eventType === 'event' && (message.startsWith('{') || message.startsWith("{'"));
        return !isTechnicalSubmit &&
          !eventType.includes('submit') &&
          !eventType.includes('enforce') &&
          !eventType.includes('provision');
      });
      return [
        {
          label: 'Soumise',
          meta: requestedAt(row),
          state: 'done'
        },
        ...validationEvents.map((event: any, index: number) => {
        const eventType = norm(event?.event_type ?? event?.type ?? event?.action);
        const label = eventType.includes('approve')
          ? 'Approuvée'
          : eventType.includes('reject')
            ? 'Refusée'
            : eventType.includes('revoke')
                ? 'Révoquée'
                : compactText(event?.label ?? event?.event_type ?? event?.action, 'Événement');
        const date = event?.created_at ? requestedAt({ created_at: event.created_at }) : '';
        return {
          label,
          meta: date,
          state: index === validationEvents.length - 1 && isPending(row) ? 'current' : 'done'
        };
      })
      ];
    }

    return [
      { label: 'Soumise', meta: `${requestedAt(row)} par ${requesterName(row)}`, state: 'done' },
      { label: 'Validation Guardian', meta: 'En cours', state: 'current' },
      { label: 'Provisioning capsule', meta: 'En attente', state: 'waiting' }
    ];
  }

  function onSearchInput(value: string): void {
    searchText = value;
    if (searchTimer) clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      const params = new URLSearchParams($page.url.searchParams);
      const q = value.trim();
      if (q) params.set('q', q);
      else params.delete('q');
      params.set('status', 'pending');
      const qs = params.toString();
      goto(`/access-requests${qs ? `?${qs}` : ''}`, { replaceState: true, noScroll: true, keepFocus: true });
    }, 250);
  }

  onDestroy(() => {
    if (searchTimer) clearTimeout(searchTimer);
  });

  async function openCreateRequestModal(): Promise<void> {
    const params = new URLSearchParams($page.url.searchParams);
    params.set('create', '1');
    const qs = params.toString();
    await goto(`/access-requests${qs ? `?${qs}` : ''}`, { replaceState: true, noScroll: true, keepFocus: true });
  }
</script>

<svelte:head>
  <title>Validation des requêtes d'accès · BornToShare</title>
</svelte:head>

<section class="ar-shell" class:has-detail={Boolean(selectedRequest)}>
  <aside class="ar-sidebar" aria-label="Navigation des requêtes">
    <label class="ar-search">
      <i class="bi bi-search" aria-hidden="true"></i>
      <input
        value={searchText}
        on:input={(event) => onSearchInput((event.currentTarget as HTMLInputElement).value)}
        placeholder="Rechercher..."
        aria-label="Rechercher"
      />
    </label>

    <nav class="ar-nav">
      <section class="ar-nav-section">
        <h2><i class="bi bi-clipboard-check" aria-hidden="true"></i>Demandes d'accès</h2>
        <button type="button" class:active={activeQueue === 'mine'} on:click={() => openQueue('mine')}>
          <span><i class="bi bi-file-earmark-lock" aria-hidden="true"></i>À valider par moi</span>
          <strong>{sidebarCounts.mine}</strong>
        </button>
        <button type="button" class:active={activeQueue === 'guardians'} on:click={() => openQueue('guardians')}>
          <span><i class="bi bi-person" aria-hidden="true"></i>Guardians</span>
          <strong>{sidebarCounts.guardians}</strong>
        </button>
        <button type="button" class:active={activeQueue === 'all'} on:click={() => openQueue('all')}>
          <span><i class="bi bi-file-earmark-text" aria-hidden="true"></i>Toutes les demandes</span>
          <strong>{sidebarCounts.all}</strong>
        </button>
      </section>

      <section class="ar-nav-section">
        <h2><i class="bi bi-people" aria-hidden="true"></i>Mes validations</h2>
        <button type="button" class:active={activeQueue === 'todo'} on:click={() => openQueue('todo')}>
          <span><i class="bi bi-hourglass-split" aria-hidden="true"></i>À traiter</span>
          <strong>{sidebarCounts.todo}</strong>
        </button>
        <button type="button" class:active={activeQueue === 'done'} on:click={() => openQueue('done')}>
          <span><i class="bi bi-check-circle" aria-hidden="true"></i>Terminées</span>
          <strong>{sidebarCounts.done}</strong>
        </button>
      </section>

    </nav>
  </aside>

  <main class="ar-main">
    <header class="ar-hero">
      <div class="ar-hero-copy">
        <h1>{pageTitle}</h1>
        <p>{pageSubtitle}</p>
      </div>
      <button type="button" class="ar-primary-action" on:click={openCreateRequestModal}>
        <i class="bi bi-plus-lg" aria-hidden="true"></i>
        <span>Create request</span>
      </button>
    </header>

    {#if canReviewAny}
      <div class="ar-tabs" role="tablist" aria-label="Files de validation">
        <button type="button" class:active={activeTab === 'mine'} on:click={() => switchTab('mine')}>À valider par moi</button>
        <button type="button" class:active={activeTab === 'guardians'} on:click={() => switchTab('guardians')}>Guardians</button>
      </div>
    {/if}

    <section class="ar-kpis" aria-label="Synthèse des validations">
      <article class="ar-kpi warning">
        <span><i class="bi bi-hourglass-split" aria-hidden="true"></i></span>
        <div><strong>{kpis.guardian}</strong><small>En attente<br />Guardian</small></div>
      </article>
      <article class="ar-kpi success">
        <span><i class="bi bi-check2-circle" aria-hidden="true"></i></span>
        <div><strong>{kpis.approved}</strong><small>Approuvées</small></div>
      </article>
    </section>

    <section class="ar-table-card">
      <header class="ar-table-head">
        <h2>{canReviewAny ? "Requêtes d'accès à valider" : "Requêtes d'accès"} ({visibleRequests.length})</h2>
        <button type="button"><i class="bi bi-funnel" aria-hidden="true"></i>Filtres</button>
      </header>

      <div class="ar-table-scroll">
        <table class="ar-table">
          <thead>
            <tr>
              <th>Demandeur</th>
              <th>Ressource</th>
              <th>Profil d'accès</th>
              <th>TTL</th>
              <th>Étape</th>
              <th>Demandé le <i class="bi bi-arrow-down-up" aria-hidden="true"></i></th>
            </tr>
          </thead>
          <tbody>
            {#if pageRequests.length === 0}
              <tr><td colspan="6" class="ar-empty">Aucune requête à valider.</td></tr>
            {:else}
              {#each pageRequests as request (accessRequestId(request))}
                {@const selected = selectedRequestId === accessRequestId(request)}
                {@const dateParts = requestedDateParts(request)}
                <tr class:selected on:click={() => selectRequest(request)} tabindex="0" on:keydown={(event) => event.key === 'Enter' && selectRequest(request)}>
                  <td>
                    <div class="ar-person">
                      <span>{initialsFromLabel(requesterName(request), '??')}</span>
                      <div><strong>{requesterName(request)}</strong><small>{requesterDepartment(request)}</small></div>
                    </div>
                  </td>
                  <td><strong>{resourceName(request)}</strong><small>{resourceZone(request)}</small></td>
                  <td><span class="access-icon"><i class={`bi ${iconForAccess(request)}`} aria-hidden="true"></i></span>{accessShort(request)}</td>
                  <td>{ttlDays(request) > 0 ? `${ttlDays(request)} j` : '—'}</td>
                  <td><span class="stage-pill">{stageText(request)}</span></td>
                  <td><strong>{dateParts.date}</strong><small>{dateParts.time}</small></td>
                </tr>
              {/each}
            {/if}
          </tbody>
        </table>
      </div>

      <footer class="ar-table-footer">
        <div class="ar-info"><i class="bi bi-info-circle-fill" aria-hidden="true"></i>Les approbations sont appliquées via des profils gouvernés et l'exécution de capsules.</div>
        <div class="ar-pager"><span>{rangeLabel}</span><button disabled><i class="bi bi-chevron-left"></i></button><button><i class="bi bi-chevron-right"></i></button></div>
      </footer>
    </section>
  </main>

  {#if selectedRequest}
    <aside class="ar-detail" aria-label="Détail de la requête">
      <header>
        <h2>Détail de la requête</h2>
        <button type="button" class="close-detail" aria-label="Fermer le détail" on:click={closeDetail}><i class="bi bi-x-lg" aria-hidden="true"></i></button>
      </header>

      <div class="status-pill"><i class="bi bi-hourglass-split" aria-hidden="true"></i>En attente — {stageText(selectedRequest)}</div>
      {#if detailLoading}
        <p class="detail-state">Chargement du détail complet...</p>
      {:else if detailError}
        <p class="detail-state error">{detailError}</p>
      {/if}

      <section class="detail-section summary">
        <h3>Résumé de la requête</h3>
        <dl>
          <div><dt>Demandeur</dt><dd>{requesterName(selectedRequest)} ({requesterDepartment(selectedRequest)})</dd></div>
          <div><dt>Ressource</dt><dd>{resourceName(selectedRequest)} ({resourceZone(selectedRequest)})</dd></div>
          <div><dt>Profil d'accès demandé</dt><dd>{accessShort(selectedRequest)}</dd></div>
          <div><dt>Demandé le</dt><dd>{requestedAt(selectedRequest)}</dd></div>
        </dl>
        <h4>Justification</h4>
        <p>{justification(selectedRequest)}</p>
      </section>

      <section class="detail-section effective">
        <h3>Aperçu de l'accès effectif</h3>
        <p class="folder"><i class="bi bi-folder-fill" aria-hidden="true"></i><strong>{resourceName(selectedRequest)}</strong> ({resourcePath(selectedRequest)})</p>
        <p>Accès en {accessShort(selectedRequest).toLowerCase()} aux fichiers et dossiers de la ressource.</p>
        {#if selectedRequest.group_name || selectedRequest.expected_group_name}
          <p class="group-line"><i class="bi bi-people-fill" aria-hidden="true"></i>{selectedRequest.group_name || selectedRequest.expected_group_name}</p>
        {/if}
      </section>

      <section class="detail-section ttl">
        <h3>Durée d'accès demandée (TTL)</h3>
        <p><i class="bi bi-calendar4-week" aria-hidden="true"></i><strong>{expiryLabel(selectedRequest)}</strong></p>
      </section>

      <section class="detail-section history">
        <h3>Historique de la requête</h3>
        <ol>
          {#each timelineEvents(selectedRequest) as event}
            <li class:done={event.state === 'done'} class:current={event.state === 'current'}>
              <span></span><strong>{event.label}</strong><small>{event.meta}</small>
            </li>
          {/each}
        </ol>
      </section>

      {#if canReviewSelectedRequest}
        <section class="decision-box">
          <label for="decision-comment">Commentaire de validation (optionnel)</label>
          <textarea id="decision-comment" bind:value={decisionComment} placeholder="Ajouter un commentaire..."></textarea>
        </section>

        <footer class="detail-actions">
          <button type="button" class="reject" disabled={Boolean(decisionRunning)} on:click={() => runDecision('reject')}>{decisionRunning === 'reject' ? 'Refus...' : 'Refuser'}</button>
          <button type="button" class="approve" disabled={Boolean(decisionRunning)} on:click={() => runDecision('approve')}>{decisionRunning === 'approve' ? 'Approbation...' : 'Approuver'}</button>
        </footer>
      {:else}
        <section class="detail-readonly-note" aria-label="Demande visible en lecture seule">
          <i class="bi bi-eye" aria-hidden="true"></i>
          <span>Visible en lecture seule. Cette demande est traitée par un guardian ou un administrateur de plateforme.</span>
        </section>
      {/if}
    </aside>
  {/if}
</section>

<NewAccessRequestModal
  open={showCreateRequestModal}
  prefillStorageRootId={createPrefillStorageRootId}
  prefillAccessLevel={createPrefillAccessLevel}
  onClose={closeCreateRequestModal}
  onCreated={handleAccessRequestCreated}
/>

<style>
  :global(.b2s-app-main) { background: #fff; }

  .ar-shell {
    --ink: #061849;
    --muted: #53638a;
    --line: #dfe6f2;
    --blue: #1155ff;
    min-height: calc(100vh - 70px);
    display: grid;
    grid-template-columns: 390px minmax(720px, 1fr);
    background: #fff;
    color: var(--ink);
    font-family: Inter, system-ui, -apple-system, "Segoe UI", sans-serif;
  }

  .ar-shell.has-detail { grid-template-columns: 390px minmax(0, 1fr) 400px; }
  .ar-sidebar { border-right: 1px solid #dfe5f0; background: #fbfcff; padding: 26px 16px 24px; min-width: 0; }
  .ar-search { height: 52px; border: 1px solid #d7dfef; border-radius: 11px; background: #fff; display: flex; align-items: center; gap: 13px; padding: 0 16px; color: #5f73a6; box-shadow: 0 8px 24px rgba(8, 20, 52, 0.03); }
  .ar-search input { border: 0; outline: 0; width: 100%; color: #172a58; font-weight: 500; font-size: 15px; background: transparent; }
  .ar-search input::placeholder { color: #6677a0; }
  .ar-nav { margin-top: 32px; display: grid; gap: 28px; }
  .ar-nav-section { display: grid; gap: 7px; padding: 0 0 26px; border-bottom: 1px solid #e5ebf4; }
  .ar-nav-section.reports { border-bottom: 0; }
  .ar-nav-section h2 { margin: 0 0 10px; display: flex; align-items: center; gap: 11px; font-size: 16px; font-weight: 750; color: var(--ink); }
  .ar-nav-section h2 i { font-size: 19px; color: #0c255d; }
  .ar-nav button { height: 50px; border: 1px solid transparent; border-radius: 9px; background: transparent; display: flex; align-items: center; justify-content: space-between; padding: 0 12px 0 28px; color: #102452; font-weight: 560; font-size: 14px; text-align: left; }
  .ar-nav button span { display: flex; align-items: center; gap: 14px; min-width: 0; }
  .ar-nav button i { font-size: 17px; color: #0b2a68; }
  .ar-nav button strong { min-width: 28px; height: 28px; border-radius: 999px; background: #f3f6fb; border: 1px solid #dbe3f0; display: inline-flex; align-items: center; justify-content: center; color: #0d45dd; font-size: 13px; }
  .ar-nav button.active { border-color: #2f66ff; background: #edf4ff; box-shadow: inset 0 0 0 1px rgba(47, 102, 255, 0.08); }
  .ar-main { padding: 24px 26px 30px 50px; min-width: 0; }
  .ar-hero { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
  .ar-hero-copy { min-width: 0; }
  .ar-hero h1 { margin: 0; font-size: 39px; line-height: 1.05; letter-spacing: 0; font-weight: 800; color: #061849; }
  .ar-hero p { margin: 10px 0 0; color: #4e5f8a; font-size: 16px; font-weight: 520; }
  .ar-primary-action {
    min-height: 44px;
    padding: 0 16px;
    border: 1px solid #061849;
    border-radius: 10px;
    background: #061849;
    color: #fff;
    display: inline-flex;
    align-items: center;
    gap: 9px;
    font-size: 14px;
    font-weight: 800;
    white-space: nowrap;
    box-shadow: 0 8px 18px rgba(6, 24, 73, 0.18);
  }
  .ar-tabs { margin-top: 28px; height: 45px; display: flex; gap: 44px; border-bottom: 1px solid #dfe6f2; }
  .ar-tabs button { border: 0; background: transparent; padding: 0 10px; color: #0c1f4d; font-size: 15px; font-weight: 650; position: relative; }
  .ar-tabs button.active { color: #0e50f5; }
  .ar-tabs button.active::after { content: ""; position: absolute; left: 0; right: 0; bottom: -1px; height: 3px; background: #1155ff; border-radius: 4px 4px 0 0; }
  .ar-kpis { margin-top: 26px; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 30px; }
  .ar-kpi { height: 126px; border: 1px solid #dfe5ef; border-radius: 11px; background: #fff; display: flex; align-items: center; gap: 24px; padding: 0 22px; box-shadow: 0 12px 32px rgba(6, 24, 73, 0.03); }
  .ar-kpi > span { width: 70px; height: 70px; border-radius: 999px; display: grid; place-items: center; font-size: 34px; }
  .ar-kpi.warning > span { color: #ff9500; background: #fff0d6; }
  .ar-kpi.success > span { color: #069a2e; background: #ddf5df; }
  .ar-kpi strong { display: block; font-size: 30px; line-height: 1; font-weight: 900; color: #081a4d; }
  .ar-kpi small { display: block; margin-top: 10px; color: #183064; font-size: 15px; font-weight: 500; line-height: 1.35; }
  .ar-table-card { margin-top: 22px; border: 1px solid #dfe5ef; border-radius: 13px; background: #fff; overflow: hidden; box-shadow: 0 16px 40px rgba(6, 24, 73, 0.04); }
  .ar-table-head { height: 55px; display: flex; align-items: center; justify-content: space-between; padding: 0 18px 0 21px; }
  .ar-table-head h2 { margin: 0; font-size: 20px; font-weight: 760; color: #061849; }
  .ar-table-head button { height: 38px; border: 1px solid #dfe6f3; border-radius: 9px; background: #fff; color: #132653; display: inline-flex; align-items: center; gap: 9px; padding: 0 18px; font-size: 14px; font-weight: 650; }
  .ar-table { width: 100%; border-collapse: collapse; table-layout: fixed; }
  .ar-table th { height: 47px; border-top: 1px solid #edf1f7; border-bottom: 2px solid #98b6ff; padding: 0 14px; text-align: left; color: #0c1f4d; font-size: 13px; font-weight: 700; }
  .ar-table th:nth-child(1) { width: 20%; } .ar-table th:nth-child(2) { width: 18%; } .ar-table th:nth-child(3) { width: 17%; } .ar-table th:nth-child(4) { width: 9%; } .ar-table th:nth-child(5) { width: 19%; } .ar-table th:nth-child(6) { width: 17%; }
  .ar-table td { height: 68px; border-bottom: 1px solid #e5e9f1; padding: 0 14px; color: #102452; font-size: 14px; font-weight: 500; vertical-align: middle; }
  .ar-table tbody tr { cursor: pointer; }
  .ar-table tbody tr:hover, .ar-table tbody tr.selected { background: #f8fbff; }
  .ar-table td strong { display: block; font-weight: 680; color: #081a4d; }
  .ar-table td small { display: block; margin-top: 3px; color: #243a70; font-size: 12px; font-weight: 450; }
  .ar-empty { text-align: center; color: #6677a0 !important; }
  .ar-person { display: flex; align-items: center; gap: 13px; }
  .ar-person > span { width: 39px; height: 39px; border-radius: 50%; background: #031951; color: #fff; display: grid; place-items: center; font-size: 15px; font-weight: 900; }
  .access-icon { width: 22px; color: #0f60ff; display: inline-flex; justify-content: center; margin-right: 12px; font-size: 18px; vertical-align: middle; }
  .stage-pill { min-height: 27px; border-radius: 999px; display: inline-flex; align-items: center; padding: 0 11px; border: 1px solid #cfe0ff; background: #eff5ff; color: #0f55ee; font-size: 12px; font-weight: 650; white-space: nowrap; }
  .ar-table-footer { min-height: 78px; display: flex; align-items: center; justify-content: space-between; padding: 15px 19px 20px; }
  .ar-info { min-height: 40px; border-radius: 8px; background: #f4f6fb; color: #24365f; display: inline-flex; align-items: center; gap: 12px; padding: 0 18px; font-size: 13px; font-weight: 550; }
  .ar-info i { color: #071f59; }
  .ar-pager { display: flex; align-items: center; gap: 12px; color: #43537c; font-size: 13px; font-weight: 650; }
  .ar-pager button { width: 35px; height: 35px; border-radius: 9px; border: 1px solid #dfe6f2; background: #fff; color: #0b1c4c; }
  .ar-pager button:disabled { opacity: .42; }
  .ar-detail { border-left: 1px solid #dfe5f0; background: #fff; padding: 20px 20px 18px; min-width: 0; }
  .ar-detail > header { height: 40px; display: flex; align-items: center; justify-content: space-between; }
  .ar-detail h2 { margin: 0; color: #061849; font-size: 20px; font-weight: 760; }
  .ar-detail header button { border: 0; background: transparent; color: #12306c; font-size: 16px; }
  .status-pill { width: max-content; margin: 18px auto 16px; height: 38px; border-radius: 999px; border: 1px solid #f2cc90; background: #fff4e2; color: #081a4d; display: flex; align-items: center; gap: 10px; padding: 0 18px; font-size: 14px; font-weight: 620; }
  .status-pill i { color: #f59a00; }
  .detail-state { margin: -4px 0 8px; color: #4e5f8a; font-size: 13px; font-weight: 700; text-align: center; }
  .detail-state.error { color: #c22323; }
  .detail-section { border-bottom: 1px solid #dfe5ef; padding: 14px 0 16px; }
  .detail-section h3 { margin: 0 0 14px; color: #071b4a; font-size: 15px; font-weight: 720; }
  .detail-section h4 { margin: 12px 0 5px; font-size: 13px; font-weight: 720; color: #071b4a; }
  .detail-section p { margin: 0; color: #0f2558; font-size: 14px; line-height: 1.45; font-weight: 450; }
  .summary dl { margin: 0; display: grid; gap: 11px; }
  .summary dl div { display: grid; grid-template-columns: 170px minmax(0, 1fr); gap: 12px; }
  .summary dt { color: #0f2558; font-size: 13px; font-weight: 500; }
  .summary dd { margin: 0; color: #071b4a; font-size: 13px; font-weight: 650; }
  .folder { display: flex; align-items: center; gap: 8px; }
  .folder i { color: #ffb22d; }
  .group-line { margin-top: 8px !important; display: flex; align-items: center; gap: 8px; color: #12306c !important; font-weight: 620 !important; }
  .ttl p { display: flex; align-items: center; gap: 10px; }
  .history ol { list-style: none; margin: 0; padding: 0 0 0 13px; display: grid; gap: 0; }
  .history li { position: relative; min-height: 46px; padding-left: 31px; color: #0b1d4f; }
  .history li::before { content: ""; position: absolute; left: 5px; top: 18px; bottom: -18px; width: 2px; background: #c5cfdf; }
  .history li:last-child::before { display: none; }
  .history li > span { position: absolute; left: 0; top: 1px; width: 13px; height: 13px; border-radius: 50%; border: 2px solid #9ba8bd; background: #fff; }
  .history li.done > span { background: #13a538; border-color: #13a538; }
  .history li.current > span { border-color: #ff9900; }
  .history strong, .history small { display: block; }
  .history strong { font-size: 13px; font-weight: 680; }
  .history small { margin-top: 3px; font-size: 12px; color: #162c63; font-weight: 450; }
  .decision-box { padding-top: 15px; }
  .decision-box label { display: block; margin-bottom: 9px; color: #061849; font-size: 13px; font-weight: 680; }
  .decision-box textarea { width: 100%; height: 65px; border: 1px solid #d8e0ec; border-radius: 9px; resize: vertical; padding: 13px; color: #132653; font-size: 13px; outline: none; }
  .decision-box textarea::placeholder { color: #63749b; }
  .detail-readonly-note { margin-top: 18px; min-height: 48px; border-radius: 10px; border: 1px solid #d9e3f3; background: #f7faff; color: #17305e; display: flex; align-items: center; gap: 10px; padding: 12px 14px; font-size: 13px; font-weight: 600; line-height: 1.4; }
  .detail-readonly-note i { color: #1155ff; font-size: 15px; }
  .detail-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 22px; }
  .detail-actions button { flex: 1 1 0; min-width: 0; width: auto; height: 46px; border-radius: 9px; font-size: 14px; font-weight: 900; }
  .detail-actions .reject { border: 1px solid #ff6f6f; background: #fff; color: #ff1f1f; }
  .detail-actions .approve { border: 1px solid #061849; background: #061849; color: #fff; box-shadow: 0 8px 18px rgba(6, 24, 73, 0.25); }

  @media (max-width: 1300px) {
    .ar-shell, .ar-shell.has-detail { grid-template-columns: 320px minmax(0, 1fr); }
    .ar-detail { grid-column: 2; border-left: 0; border-top: 1px solid #dfe5f0; }
  }

  @media (max-width: 760px) {
    .ar-hero {
      flex-direction: column;
      align-items: stretch;
    }

    .ar-primary-action {
      width: 100%;
      justify-content: center;
    }
  }
</style>
