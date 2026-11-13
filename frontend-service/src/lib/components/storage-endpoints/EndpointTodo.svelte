<script lang="ts">
  

  import { t } from '$lib/i18n';
  import EntityTodoCard, { type EntityTodoStep } from '$lib/components/entity/EntityTodoCard.svelte';
  import type { ZoneSummary } from '$lib/components/zones/zone-summary';

  
  
  
  interface Props {
    /** « To do on this file server »: each problem with the action that settles it. */
    summary: ZoneSummary;
    health?: 'healthy' | 'degraded' | 'unhealthy' | 'unknown';
    hostMissing?: boolean;
    lastResult?: string;
    pendingRequests?: number;
    sharesNotManaged?: number;
    provisioningWarnings?: string[];
    rereadBusy?: boolean;
    testBusy?: boolean;
    onEditConnection?: () => void;
    /** The last test failed because the password of the account is no longer in the secret store */
    secretMissing?: boolean;
    /** The name of the server resolves to another address than the one it is declared with */
    movedTo?: string | null;
    onUseAddress?: (address: string) => void;
    onTest?: () => void;
    onAddGuardians?: () => void;
    onReread?: () => void;
    onOpenRequests?: () => void;
    onOpenShares?: () => void;
    onOpenProvisioning?: () => void;
  }

  let {
    summary,
    health = 'unknown',
    hostMissing = false,
    lastResult = '',
    pendingRequests = 0,
    sharesNotManaged = 0,
    provisioningWarnings = [],
    rereadBusy = false,
    testBusy = false,
    onEditConnection = () => {},
    secretMissing = false,
    movedTo = null,
    onUseAddress = () => {},
    onTest = () => {},
    onAddGuardians = () => {},
    onReread = () => {},
    onOpenRequests = () => {},
    onOpenShares = () => {},
    onOpenProvisioning = () => {}
  }: Props = $props();

  let steps: EntityTodoStep[] = $state([]);
  $effect.pre(() => {
    steps = [
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
        ? [{ key: 'guardians', tone: 'warn' as const, icon: 'bi-person-plus', title: t('{count} folder(s) without guardian', { count: summary.noGuardian.length }), detail: t('Only the administrators can approve their requests'), label: t('Add guardians'), run: onAddGuardians }]
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
  });
</script>

<EntityTodoCard title={t('To do on this server')} {steps} />
