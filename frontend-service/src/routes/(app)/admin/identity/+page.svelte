<script lang="ts">
  
  import { browser } from '$app/environment';
  import { goto, invalidateAll } from '$app/navigation';
  import { page } from '$app/stores';
  import { deleteIdentity, updateIdentity } from '$lib/api/identity';
  import EntityWorkspace from '$lib/components/entity/EntityWorkspace.svelte';
  import IdentitiesSidebar from '$lib/components/identity/IdentitiesSidebar.svelte';
  import IdentityAddModal from '$lib/components/identity/IdentityAddModal.svelte';
  import IdentityGroupWorkspace from '$lib/components/identity/IdentityGroupWorkspace.svelte';
  import IdentityLeaveDialog from '$lib/components/identity/IdentityLeaveDialog.svelte';
  import IdentityWorkspace from '$lib/components/identity/IdentityWorkspace.svelte';
  import ConfirmDeleteDialog from '$lib/components/ui/ConfirmDeleteDialog.svelte';
  import EmptyState from '$lib/components/ui/EmptyState.svelte';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import { reportUiError } from '$lib/errors';
  import { t } from '$lib/i18n';
  import { toast } from '$lib/stores/toast';
  import { normalizeText } from '$lib/utils/values';
  import EditIdentityModal from './components/EditIdentityModal.svelte';

  
  interface Props {
    /**
   * Identities: the people and directory groups that have a place in BornToShare. List by what they do on the left,
   * the selected one on the right (same grammar as Servers, Folders and Directories).
   */
    data: Record<string, any>;
  }

  let { data }: Props = $props();

  let items = $derived((data.items ?? []) as Array<Record<string, any>>);
  let guardians = $derived(Object.fromEntries(((data.guardians ?? []) as Array<{ identity_id: number; folders: number; sole: number }>).map((row) => [row.identity_id, row])));
  const isGroup = (item: Record<string, any> | null) => String(item?.type ?? '').toLowerCase() === 'group';
  const keyOf = (item: Record<string, any>) => `${isGroup(item) ? 'group' : 'user'}:${item.id}`;

  let selectedKey: string | null = $state(null);
  let query = $state('');
  let busy = $state(false);
  let showAdd = $state(false);
  let editTarget: Record<string, any> | null = $state(null);
  let deleteTarget: Record<string, any> | null = $state(null);
  let deleteBusy = $state(false);
  // Deleting or disabling a person goes through the handover of the folders they would leave alone
  let leave: { item: Record<string, any>; mode: 'delete' | 'disable' } | null = $state(null);
  let workspace: IdentityWorkspace | null = $state(null);

  // The page opens on ?selected=, else on the first guardian who needs a look, else the first person
  $effect.pre(() => {
    if (browser && items.length && (!selectedKey || !items.some((item) => keyOf(item) === selectedKey))) {
      const wanted = $page.url.searchParams.get('selected');
      const toReview = items.find((item) => !isGroup(item) && (guardians[Number(item.id)]?.folders ?? 0) > 0 && !String(item.email ?? '').trim());
      const first = items.find((item) => keyOf(item) === wanted) ?? toReview ?? items[0];
      selectedKey = keyOf(first);
    }
  });
  $effect.pre(() => {
    if (browser && selectedKey && $page.url.searchParams.get('selected') !== selectedKey) {
      const next = new URL($page.url);
      next.searchParams.set('selected', selectedKey);
      goto(`${next.pathname}${next.search}`, { replaceState: true, noScroll: true, keepFocus: true });
    }
  });
  let selected = $derived(items.find((item) => keyOf(item) === selectedKey) ?? null);

  // The default local administrator (provisioned by the system) can be neither deleted nor disabled
  const isDefaultAdmin = (item: Record<string, any> | null) =>
    !!item && !isGroup(item) && normalizeText(item.auth_source) === 'local' && normalizeText(item.provisioning_source) === 'system' && normalizeText(item.username) === 'admin';

  async function setRole(item: Record<string, any>, role: 'user' | 'platform_admin'): Promise<boolean> {
    busy = true;
    try {
      await updateIdentity(fetch, item.id, { identity_type: isGroup(item) ? 'group' : 'user', application_role: role });
      await invalidateAll();
      return true;
    } catch (error: unknown) {
      reportUiError(error, 'Unable to change the role.', 'identity.role');
      return false;
    } finally {
      busy = false;
    }
  }
  async function toggleActive(item: Record<string, any>) {
    if (isDefaultAdmin(item)) {
      toast.warning(t('Default local admin is protected.'));
      return;
    }
    const next = String(item.status ?? 'active') === 'inactive';
    if (!next) {
      leave = { item, mode: 'disable' };
      return;
    }
    await setActive(item, true);
  }
  async function setActive(item: Record<string, any>, next: boolean) {
    busy = true;
    try {
      await updateIdentity(fetch, item.id, { identity_type: 'user', is_active: next });
      const who = item.display_name || item.username;
      if (next) toast.success(t('{name} enabled.', { name: who }));
      else toast.success(t('{name} disabled.', { name: who }), { action: { label: t('Undo'), run: () => setActive(item, true) } });
      await invalidateAll();
      workspace?.reload();
    } catch (error: unknown) {
      reportUiError(error, 'Unable to update the identity.', 'identity.toggle');
    } finally {
      busy = false;
    }
  }
  async function confirmDelete() {
    const item = deleteTarget;
    if (!item || isDefaultAdmin(item)) return;
    deleteBusy = true;
    try {
      await deleteIdentity(fetch, item.id, isGroup(item) ? 'group' : 'user');
      toast.success(t('Identity deleted.'));
      deleteTarget = null;
      selectedKey = null;
      await invalidateAll();
    } catch (error: unknown) {
      reportUiError(error, 'Unable to delete identity.', 'identity.delete');
    } finally {
      deleteBusy = false;
    }
  }
</script>

{#if !items.length}
  <section class="b2s-page b2s-page--admin">
    <EmptyState page iconClass="bi bi-people" title={t('No identity yet')} description={t('Add the people and directory groups that use BornToShare.')}
      ctaLabel={t('Add an identity')} onCta={() => (showAdd = true)} />
  </section>
{:else}
  <EntityWorkspace title={t('Identities')} contentKey={selectedKey}>
    {#snippet list()}
      
        <IdentitiesSidebar {items} {guardians} {selectedKey} {query}
          onQueryChange={(value) => (query = value)}
          onSelect={(key) => (selectedKey = key)}
          onAdd={() => (showAdd = true)}
          onOpenAdmins={() => goto('/admin/identity/admins')} />
      
      {/snippet}


    {#if selected && isGroup(selected)}
      <IdentityGroupWorkspace item={selected} {busy}
        onSetRole={(role) => setRole(selected, role)}
        onDelete={() => (deleteTarget = selected)} />
    {:else if selected}
      <IdentityWorkspace bind:this={workspace} item={selected} {busy} canDelete={!isDefaultAdmin(selected)} isSelf={Number(selected.id) === Number(data.user?.id ?? 0)} people={items}
        onSetRole={(role) => setRole(selected, role)}
        onToggleActive={() => toggleActive(selected)}
        onEdit={() => (editTarget = selected)}
        onDelete={() => (leave = { item: selected, mode: 'delete' })} />
    {:else}
      <LoadingState block skeleton="detail" />
    {/if}
  </EntityWorkspace>
{/if}

<IdentityAddModal open={showAdd} existing={items} onClose={() => (showAdd = false)}
  onDone={async (id) => { await invalidateAll(); if (id) selectedKey = `user:${id}`; }} />

<EditIdentityModal open={editTarget !== null} identity={editTarget} onClose={() => (editTarget = null)}
  on:done={async () => { editTarget = null; await invalidateAll(); workspace?.reload(); }} />

<IdentityLeaveDialog open={leave !== null} identity={leave?.item ?? null} mode={leave?.mode ?? 'delete'} candidates={items}
  onClose={() => (leave = null)}
  onConfirm={async () => {
    const current = leave;
    if (!current) return;
    if (current.mode === 'delete') {
      deleteTarget = current.item;
      await confirmDelete();
    } else {
      await setActive(current.item, false);
    }
    leave = null;
  }} />

<ConfirmDeleteDialog open={deleteTarget !== null && isGroup(deleteTarget)} onClose={() => (deleteTarget = null)} onConfirm={confirmDelete} busy={deleteBusy}
  title={isGroup(deleteTarget) ? t('Remove the role of this group') : t('Delete the identity')}
  description={String(deleteTarget?.display_name || deleteTarget?.username || '')}
  impactItems={isGroup(deleteTarget)
    ? [t('Its members lose the role it gave them.')]
    : [t('They can no longer sign in to BornToShare.'), t('The folders they guard keep their other guardians.')]} />
