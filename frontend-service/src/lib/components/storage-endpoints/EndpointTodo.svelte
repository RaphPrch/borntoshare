<script lang="ts">
  import { t } from '$lib/i18n';
  import EntityTodoCard, { type EntityTodoStep } from '$lib/components/entity/EntityTodoCard.svelte';
  import type { ZoneSummary } from '$lib/components/zones/zone-summary';

  /** « To do on this file server »: each problem with the action that settles it. */
  export let summary: ZoneSummary;
  export let health: 'healthy' | 'degraded' | 'unhealthy' | 'unknown' = 'unknown';
  export let hostMissing = false;
  export let lastResult = '';
  export let pendingRequests = 0;
  export let sharesNotManaged = 0;
  export let provisioningWarnings: string[] = [];
  export let rereadBusy = false;
  export let testBusy = false;
  export let onEditConnection: () => void = () => {};
  /** The last test failed because the password of the account is no longer in the secret store */
  export let secretMissing = false;
  /** The name of the server resolves to another address than the one it is declared with */
  export let movedTo: string | null = null;
  export let onUseAddress: (address: string) => void = () => {};
  export let onTest: () => void = () => {};
  export let onAddGuardians: () => void = () => {};
  export let onReread: () => void = () => {};
  export let onOpenRequests: () => void = () => {};
  export let onOpenShares: () => void = () => {};
  export let onOpenProvisioning: () => void = () => {};

  let steps: EntityTodoStep[] = [];
  $: steps = [
    ...(hostMissing
      ? [{ key: 'host', tone: 'bad' as const, icon: 'bi-hdd-network', title: t('No address for this server'), detail: t('Give its name or IP address.'), label: t('Edit the connection'), run: onEditConnection }]
      : secretMissing
        ? [{
            key: 'secret',
            tone: 'bad' as const,
            icon: 'bi-key',
            title: t('The password of the account is missing'),
            detail: t('It is no longer in the secret store: enter it again. {count} folder(s) blocked meanwhile.', { count: summary.roots.length }),
            label: t('Enter the password again'),
            run: onEditConnection
          }]
      : health === 'unhealthy'
        ? [movedTo
          ? {
              key: 'moved',
              tone: 'bad' as const,
              icon: 'bi-signpost-split',
              title: t('The server seems to have a new address'),
              detail: t('Its name now leads to {address}. {count} folder(s) blocked until the address is changed.', { address: movedTo, count: summary.roots.length }),
              label: t('Use {address}', { address: movedTo }),
              run: () => movedTo && onUseAddress(movedTo)
            }
          : {
            key: 'down',
            tone: 'bad' as const,
            icon: 'bi-wifi-off',
            title: t('The server does not answer'),
            detail: [lastResult, summary.roots.length ? t('{count} folder(s) blocked', { count: summary.roots.length }) : ''].filter(Boolean).join(' · '),
            label: t('Edit the connection'),
            run: onEditConnection
          }]
        : health === 'unknown'
          ? [{ key: 'untested', tone: 'warn' as const, icon: 'bi-activity', title: t('Never tested'), detail: t('Test the connection to know whether the server answers.'), label: testBusy ? t('Testing…') : t('Test the connection'), busy: testBusy, run: onTest }]
          : []),
    ...(summary.noGuardian.length
      ? [{ key: 'guardians', tone: 'warn' as const, icon: 'bi-person-plus', title: t('{count} folder(s) without enough guardians', { count: summary.noGuardian.length }), detail: t('Only the administrators can approve their requests'), label: t('Add guardians'), run: onAddGuardians }]
      : []),
    ...(summary.reread.length
      ? [{ key: 'reread', tone: 'warn' as const, icon: 'bi-arrow-clockwise', title: t('{count} folder(s) to read again', { count: summary.reread.length }), detail: t('Failed test or gap in the ACL'), label: rereadBusy ? t('Reading…') : t('Read the ACLs'), busy: rereadBusy, run: onReread }]
      : []),
    ...(pendingRequests
      ? [{ key: 'requests', tone: 'info' as const, icon: 'bi-envelope', title: t('{count} pending request(s)', { count: pendingRequests }), detail: t('To decide by the guardians of the folders'), label: t('See the requests'), run: onOpenRequests }]
      : []),
    ...(provisioningWarnings.length
      ? [{ key: 'provisioning', tone: 'warn' as const, icon: 'bi-shield-exclamation', title: t('Provisioning to complete'), detail: provisioningWarnings.join(' · '), label: t('See the provisioning'), run: onOpenProvisioning }]
      : []),
    ...(sharesNotManaged
      ? [{ key: 'shares', tone: 'info' as const, icon: 'bi-folder-plus', title: t('{count} share(s) not managed', { count: sharesNotManaged }), detail: t('Found on the server, not governed by BornToShare yet'), label: t('See the shares'), run: onOpenShares }]
      : [])
  ];
</script>

<EntityTodoCard title={t('To do on this server')} {steps} />
