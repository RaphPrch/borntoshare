<script lang="ts">
  import { t } from '$lib/i18n';
  import EntityTodoCard, { type EntityTodoStep } from '$lib/components/entity/EntityTodoCard.svelte';
  import type { ZoneSummary } from './zone-summary';

  type Step = EntityTodoStep;

  
  interface Props {
    /** « To do on this zone »: each problem grouped, with the action that settles it. */
    summary: ZoneSummary;
    pendingRequests?: number;
    ouMissing?: boolean;
    rereadBusy?: boolean;
    onOpenServer?: (id: number) => void;
    onAddGuardians?: () => void;
    onReread?: () => void;
    onOpenRequests?: () => void;
    onOpenProvisioning?: () => void;
  }

  let {
    summary,
    pendingRequests = 0,
    ouMissing = false,
    rereadBusy = false,
    onOpenServer = () => {},
    onAddGuardians = () => {},
    onReread = () => {},
    onOpenRequests = () => {},
    onOpenProvisioning = () => {}
  }: Props = $props();

  let steps = $derived([
    ...summary.unreachable.map((server): Step => ({
      key: `down-${server.id}`,
      tone: 'bad',
      icon: 'bi-wifi-off',
      title: t('{name} is unreachable', { name: server.name }),
      detail: [server.host, server.roots ? t('{count} folder(s) blocked', { count: server.roots }) : ''].filter(Boolean).join(' · '),
      label: t('Edit the connection'),
      run: () => onOpenServer(server.id)
    })),
    ...(summary.noGuardian.length
      ? [{
          key: 'guardians',
          tone: 'warn' as const,
          icon: 'bi-person-plus',
          title: t('{count} folder(s) without guardian', { count: summary.noGuardian.length }),
          detail: t('Only the administrators can approve their requests'),
          label: t('Add guardians'),
          run: onAddGuardians
        }]
      : []),
    ...(summary.reread.length
      ? [{
          key: 'reread',
          tone: 'warn' as const,
          icon: 'bi-arrow-clockwise',
          title: t('{count} folder(s) to read again', { count: summary.reread.length }),
          detail: t('Failed test or gap in the ACL, on a server that answers'),
          label: rereadBusy ? t('Reading…') : t('Read the ACLs'),
          busy: rereadBusy,
          run: onReread
        }]
      : []),
    ...(pendingRequests
      ? [{
          key: 'requests',
          tone: 'info' as const,
          icon: 'bi-envelope',
          title: t('{count} pending request(s)', { count: pendingRequests }),
          detail: t('To decide by the guardians of the folders'),
          label: t('See the requests'),
          run: onOpenRequests
        }]
      : []),
    ...(ouMissing
      ? [{
          key: 'ou',
          tone: 'warn' as const,
          icon: 'bi-diagram-3',
          title: t('No OU set for the groups'),
          detail: t('The groups go to the default OU of the directory'),
          label: t('Set it'),
          run: onOpenProvisioning
        }]
      : [])
  ]);
</script>

<EntityTodoCard title={t('To do on this zone')} {steps} />
