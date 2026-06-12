<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import IdentityBrowserModal from '$lib/components/identity/IdentityBrowserModal.svelte';
  import { importIdentityAdBatch, listIdentityOverview } from '$lib/api/identity';
  import { sameOwnerIdSet } from '$lib/utils/storage-root-governance';
  import {
    buildOwnersBrowserConfirmPayload,
    extractImportedIdentityId,
    mergeOwnersSelectionWithDraft,
    normalizeOwnerBrowserSelection,
    principalIdentityId,
    principalPreviewLabel,
    resolveOwnersSelectionMetadata,
    type IdentityImportBatchResult,
    type IdentityOverviewPayload,
    type OwnerBrowserPrincipal
  } from './storage-root-owners.browser';
  import { toast } from '$lib/utils/toast';

  export let open = false;
  export let storageRootId: number | null = null;
  export let initialSourceId: number | null = null;
  export let initialGuardianIds: number[] = [];
  export let defaultAssignedRole: 'guardian' = 'guardian';
  export let onClose: () => void = () => {};

  type IdentityBrowserSelectionEvent = {
    selectedItems?: OwnerBrowserPrincipal[];
    sourceId?: number | null;
  };

  const dispatch = createEventDispatcher<{
    close: void;
    activity: {
      action: string;
      outcome: 'success' | 'failed' | 'warning';
      severity: 'info' | 'admin' | 'critical';
      message: string;
      context?: Record<string, unknown>;
    };
    save: {
      storageRootId: number;
      guardianIds: number[];
      assignedRole?: 'guardian';
      metadataByIdentityId?: Record<number, Record<string, unknown>>;
      unresolvedPrincipalLabels?: string[];
    };
  }>();

  let saving = false;
  let importing = false;
  let selectedSourceId: number | null = null;
  let initialSelectedKeys: string[] = [];
  let initialRoleByKey: Record<string, { guardian?: boolean }> = {};

  const keyFromId = (id: number) => `id:${id}`;

  function emitActivity(payload: {
    action: string;
    outcome: 'success' | 'failed' | 'warning';
    severity: 'info' | 'admin' | 'critical';
    message: string;
    context?: Record<string, unknown>;
  }) {
    dispatch('activity', payload);
  }

  $: initialSelectedKeys = [
    ...initialGuardianIds.map((id) => keyFromId(id))
  ];

  $: initialRoleByKey = Object.fromEntries(
    Array.from(new Set(initialSelectedKeys)).map((key) => [
      key,
      {
        guardian: initialGuardianIds.some((id) => key === keyFromId(id)),
      }
    ])
  );

  async function onConfirm(event: CustomEvent<IdentityBrowserSelectionEvent>) {
    if (saving) return;
    if (!storageRootId || storageRootId <= 0) {
      emitActivity({
        action: 'storage_root.guardian_selection_failed',
        outcome: 'warning',
        severity: 'critical',
        message: 'Storage root not found'
      });
      toast.warning('Storage root not found');
      return;
    }

    saving = true;
    try {
      const { selectedItems = [], sourceId = null } = event.detail ?? {};
      selectedSourceId = Number(sourceId ?? 0) > 0 ? Number(sourceId) : null;

      if (!selectedSourceId) {
        emitActivity({
          action: 'storage_root.guardian_selection_failed',
          outcome: 'warning',
          severity: 'critical',
          message: 'AD source is required'
        });
        toast.warning('AD source is required');
        return;
      }

      const initialGuardianIdsSnapshot = [...(initialGuardianIds ?? [])];
      const metadataByIdentityId: Record<number, Record<string, unknown>> = {};
      const unresolvedKeys: string[] = [];

      const setIdentityMetadata = (
        identityId: number,
        principal?: OwnerBrowserPrincipal,
        extra?: Record<string, unknown>
      ) => {
        if (!Number.isFinite(identityId) || identityId <= 0) return;
        const principalType = String(principal?.type ?? extra?.identity_type ?? 'user').trim().toLowerCase() || 'user';
        const current = metadataByIdentityId[identityId] ?? {};
        metadataByIdentityId[identityId] = {
          identity_id: identityId,
          display_name:
            String(
              principal?.display_name ??
              principal?.username ??
              principal?.upn ??
              principal?.email ??
              current?.display_name ??
              `Identity #${identityId}`
            ).trim() || `Identity #${identityId}`,
          username: String(principal?.username ?? current?.username ?? '').trim() || null,
          upn: String(principal?.upn ?? current?.upn ?? '').trim() || null,
          email: String(principal?.email ?? current?.email ?? '').trim() || null,
          identity_type: principalType,
          ...current,
          ...(extra ?? {})
        };
      };

      importing = true;
      const normalizedSelected = Array.isArray(selectedItems) ? (selectedItems as OwnerBrowserPrincipal[]) : [];

      const {
        principalSelections,
        selectedPrincipalItems,
        ignoredUnsupportedCount: ignoredNonUserCount
      } = normalizeOwnerBrowserSelection(normalizedSelected);
      if (selectedPrincipalItems.length === 0) {
        emitActivity({
          action: 'storage_root.guardian_selection_failed',
          outcome: 'warning',
          severity: 'critical',
          message: 'No user/group entries selected.'
        });
        toast.warning('No user/group entries selected.');
        return;
      }

      const resolvedIdentityIdsForRole = new Set<number>();
      const resolvedIdentityBySelection = new Map<number, number>();

      // Search results may already expose a resolved application identity_id.
      // Trust it first, then fallback to batch resolve/import only for unresolved rows.
      const toImport = principalSelections.filter(({ item, selectionIndex }) => {
        const directIdentityId = principalIdentityId(item);
        if (!directIdentityId) return true;
        resolvedIdentityIdsForRole.add(directIdentityId);
        resolvedIdentityBySelection.set(selectionIndex, directIdentityId);
        setIdentityMetadata(directIdentityId, item);
        return false;
      });

      if (toImport.length > 0) {
        let pendingIdentityResolution: Array<{ item: OwnerBrowserPrincipal; selectionIndex: number }> = [];
        try {
          const imported = (await importIdentityAdBatch(fetch, {
            identity_source_id: selectedSourceId,
            snapshot_source: 'ui-storage-root-owners-import',
            items: toImport.map(({ item }) => ({
              principal: {
                type: String(item?.type ?? 'user').trim().toLowerCase() === 'group' ? 'group' : 'user',
                external_id: item?.dn ?? item?.external_id ?? item?.id ?? null,
                dn: item?.dn ?? null,
                username: null,
                display_name: item?.display_name ?? null,
                email: null
              }
            }))
          })) as IdentityImportBatchResult;

          const importedRows = Array.isArray(imported?.items)
            ? imported.items
            : Array.isArray(imported?.results)
              ? imported.results
              : [];
          const resolvedImportIndexes = new Set<number>();

          for (const row of importedRows as Array<Record<string, unknown>>) {
            const importIndex = Number(row?.index);
            const importedIdentityId = extractImportedIdentityId(row);
            if (importedIdentityId) {
              if (Number.isFinite(importIndex) && importIndex >= 0) {
                resolvedImportIndexes.add(importIndex);
              }
              resolvedIdentityIdsForRole.add(importedIdentityId);
              if (Number.isFinite(importIndex) && importIndex >= 0 && importIndex < toImport.length) {
                const candidate = toImport[importIndex];
                setIdentityMetadata(importedIdentityId, candidate.item);
                resolvedIdentityBySelection.set(candidate.selectionIndex, importedIdentityId);
              } else {
                setIdentityMetadata(importedIdentityId);
              }
            }
          }

          const failedRows = Array.isArray(imported?.errors)
            ? imported.errors
            : Array.isArray(imported?.failures)
              ? imported.failures
              : [];
          const failedIndexes = new Set<number>(
            failedRows
              .map((e) => Number(e?.index))
              .filter((n: number) => Number.isFinite(n) && n >= 0)
          );

          toImport.forEach((entry, idx) => {
            if (failedIndexes.has(idx)) {
              pendingIdentityResolution.push(entry);
              return;
            }
            if (!resolvedImportIndexes.has(idx)) {
              pendingIdentityResolution.push(entry);
            }
          });
        } catch {
          pendingIdentityResolution = [...toImport];
        }

        if (pendingIdentityResolution.length > 0) {
          let resolvedFromOverview = resolveOwnersSelectionMetadata(
            pendingIdentityResolution.map((entry) => entry.item),
            null
          );
          try {
            const overview = (await listIdentityOverview(fetch)) as IdentityOverviewPayload;
            resolvedFromOverview = resolveOwnersSelectionMetadata(
              pendingIdentityResolution.map((entry) => entry.item),
              overview
            );
          } catch {
            resolvedFromOverview = resolveOwnersSelectionMetadata(
              pendingIdentityResolution.map((entry) => entry.item),
              null
            );
          }

          for (const resolvedMatch of resolvedFromOverview.resolvedMatches) {
            const pending = pendingIdentityResolution[resolvedMatch.principalIndex];
            if (!pending) continue;
            const resolvedId = Number(resolvedMatch.identityId ?? 0);
            if (!Number.isFinite(resolvedId) || resolvedId <= 0) continue;
            resolvedIdentityIdsForRole.add(resolvedId);
            resolvedIdentityBySelection.set(pending.selectionIndex, resolvedId);
            setIdentityMetadata(resolvedId, pending.item, resolvedFromOverview.metadataByIdentityId[resolvedId] ?? {});
          }
          unresolvedKeys.push(...resolvedFromOverview.unresolved);
        }
      }

      importing = false;

      for (const { item, selectionIndex } of principalSelections) {
        if (resolvedIdentityBySelection.has(selectionIndex)) continue;
        unresolvedKeys.push(principalPreviewLabel(item));
      }

      const mergedSelection = mergeOwnersSelectionWithDraft({
        initialGuardianIds: initialGuardianIdsSnapshot,
        assignedRole: 'guardian',
        resolvedIdentityIds: [...resolvedIdentityIdsForRole]
      });

      const guardianIds = mergedSelection.guardianIds;
      const addedCount = mergedSelection.addedCount;
      const resolvedCount = mergedSelection.resolvedCount;
      const alreadyAssignedCount = mergedSelection.alreadyAssignedCount;
      const payloadPreview = buildOwnersBrowserConfirmPayload({
        storageRootId,
        assignedRole: 'guardian',
        guardianIds,
        metadataByIdentityId,
        unresolvedLabels: unresolvedKeys
      });
      const unresolvedPrincipalLabels = payloadPreview.unresolvedPrincipalLabels;
      const unresolvedCount = principalSelections.filter(({ selectionIndex }) => !resolvedIdentityBySelection.has(selectionIndex)).length;

      if (ignoredNonUserCount > 0) {
        emitActivity({
          action: 'storage_root.guardian_selection_warning',
          outcome: 'warning',
          severity: 'critical',
          message:
            ignoredNonUserCount === 1
              ? '1 unsupported entry ignored'
              : `${ignoredNonUserCount} unsupported entries ignored`,
          context: {
            ignored_count: ignoredNonUserCount
          }
        });
        toast.warning(
          ignoredNonUserCount === 1
            ? '1 unsupported entry ignored'
            : `${ignoredNonUserCount} unsupported entries ignored`
        );
      }

      const guardianChanged = !sameOwnerIdSet(guardianIds, initialGuardianIdsSnapshot);

      if (addedCount > 0 && unresolvedCount > 0) {
        emitActivity({
          action: 'storage_root.guardian_selection_warning',
          outcome: 'warning',
          severity: 'critical',
          message: `${addedCount} entries added, ${unresolvedCount} could not be resolved.`,
          context: {
            added_count: addedCount,
            unresolved_count: unresolvedCount
          }
        });
        toast.warning(`${addedCount} entries added, ${unresolvedCount} could not be resolved.`);
      }

      if (!guardianChanged) {
        if (resolvedCount > 0 && unresolvedCount === 0) {
          emitActivity({
            action: 'storage_root.guardian_selection_warning',
            outcome: 'warning',
            severity: 'info',
            message: 'Selected entries are already assigned.',
            context: {
              resolved_count: resolvedCount,
              already_assigned_count: alreadyAssignedCount
            }
          });
          toast.info('Selected entries are already assigned.');
        } else if (resolvedCount === 0 && unresolvedCount > 0) {
          emitActivity({
            action: 'storage_root.guardian_selection_failed',
            outcome: 'failed',
            severity: 'critical',
            message: 'The selected entries could not be added to the governance draft.',
            context: {
              resolved_count: resolvedCount,
              unresolved_count: unresolvedCount,
              unresolved_principal_labels: unresolvedPrincipalLabels
            }
          });
          toast.error('The selected entries could not be added to the governance draft.');
        } else if (resolvedCount > 0 && unresolvedCount > 0) {
          emitActivity({
            action: 'storage_root.guardian_selection_warning',
            outcome: 'warning',
            severity: 'critical',
            message: `${alreadyAssignedCount} entries already assigned, ${unresolvedCount} could not be resolved.`,
            context: {
              resolved_count: resolvedCount,
              unresolved_count: unresolvedCount,
              already_assigned_count: alreadyAssignedCount,
              unresolved_principal_labels: unresolvedPrincipalLabels
            }
          });
          toast.warning(`${alreadyAssignedCount} entries already assigned, ${unresolvedCount} could not be resolved.`);
        } else {
          emitActivity({
            action: 'storage_root.guardian_selection_failed',
            outcome: 'warning',
            severity: 'critical',
            message: 'No entries added.'
          });
          toast.warning('No entries added.');
        }
        return;
      }

      dispatch('save', payloadPreview);
      handleClose();
    } finally {
      importing = false;
      saving = false;
    }
  }

  function handleClose() {
    dispatch('close');
    onClose();
  }
</script>

<IdentityBrowserModal
  bind:open
  {storageRootId}
  onClose={handleClose}
  identitySources={[]}
  {initialSourceId}
  title="Browse Active Directory"
  subtitle={
    'Select users or groups to add as guardians.'
  }
  mode="multiple"
  allowRoleAssignment={false}
  defaultAssignedRole="guardian"
  allowedPrincipalType="all"
  includeImportCandidates={true}
  initialSelectedKeys={initialSelectedKeys}
  initialRoleByKey={initialRoleByKey}
  busy={saving || importing}
  on:confirm={onConfirm}
/>
