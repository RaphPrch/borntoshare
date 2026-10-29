import { t } from '$lib/i18n';
import { provisioningErrorMessage } from '$lib/utils/request-decision-errors';
import { activityTemplates } from './templates';
import { badgeFromEvent, resolveBadgeLabel } from './severity';

function asPrimitiveStr(v: any): string | null {
  if (v == null) return null;
  if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') {
    const s = String(v).trim();
    return s ? s : null;
  }
  return null;
}

function asStr(v: any): string | null {
  const primitive = asPrimitiveStr(v);
  if (primitive) return primitive;

  if (v && typeof v === 'object') {
    const o = v as Record<string, unknown>;
    return (
      asPrimitiveStr(o.name) ??
      asPrimitiveStr(o.display_name) ??
      asPrimitiveStr(o.label) ??
      asPrimitiveStr(o.title) ??
      asPrimitiveStr(o.code) ??
      asPrimitiveStr(o.email) ??
      asPrimitiveStr(o.username) ??
      asPrimitiveStr(o.id)
    );
  }

  return null;
}

function varsFromEvent(ev: any) {
  const meta = ev?.context_json ?? ev?.metadata_json ?? ev?.context ?? {};
  const nestedContext = meta?.context_json && typeof meta?.context_json === 'object' ? meta.context_json : {};
  const ctx = {
    ...(typeof nestedContext === 'object' ? nestedContext : {}),
    ...(typeof meta === 'object' ? meta : {})
  } as Record<string, unknown>;

  const targetType = asStr(ev?.target_type) ?? asStr(ev?.entity_type);
  const targetDisplay = asStr(ev?.target_display) ?? asStr(ev?.target) ?? asStr(ev?.resource) ?? asStr(ev?.entity_id);

  const guardianIds = Array.isArray((ctx as any)?.guardian_ids) ? (ctx as any).guardian_ids : [];
  const ownersCount =
    Number((ctx as any)?.owners_count) > 0
      ? Number((ctx as any).owners_count)
      : Math.max(guardianIds.length, 0);

  const zoneIdRaw = asStr(ev?.zone_id) ?? asStr((ctx as any)?.zone_id) ?? asStr((ctx as any)?.zone?.id);
  const zoneLabel =
    asStr((ctx as any)?.zone_name) ??
    asStr((ctx as any)?.zone?.name) ??
    asStr((ctx as any)?.zone) ??
    asStr((ctx as any)?.before?.zone_name) ??
    asStr((ctx as any)?.after?.zone_name) ??
    asStr((ctx as any)?.before?.zone?.name) ??
    asStr((ctx as any)?.after?.zone?.name) ??
    asStr(ev?.zone_name) ??
    asStr(ev?.zone) ??
    (zoneIdRaw ? t('Zone #{zoneIdRaw}', { zoneIdRaw }) : t('Unknown'));
  const updatedFields = Array.isArray((ctx as any)?.updated_fields)
    ? (ctx as any).updated_fields
        .map((v: unknown) => String(v ?? '').trim())
        .filter(Boolean)
    : [];
  const changes = updatedFields.length
    ? t(' — updated fields: {value}', { value: (updatedFields.map((f: string) => f.replaceAll('_', ' ')).join(', ')) })
    : '';
  const actor =
    asStr(ev?.actor_display_name) ??
    asStr(ev?.actor_name) ??
    asStr(ev?.actor_username) ??
    asStr(ev?.actor_email) ??
    asStr((ctx as any)?.deleted_by) ??
    asStr((ctx as any)?.performed_by);

  const rootLabel =
    asStr((ctx as any)?.root) ??
    asStr((ctx as any)?.storage_root) ??
    (targetType === 'storage_root' ? targetDisplay : null) ??
    asStr(ev?.root_id) ??
    asStr(ev?.entity_id);

  const profileLabel =
    asStr((ctx as any)?.profile) ??
    asStr((ctx as any)?.profile_name) ??
    (targetType === 'access_profile' ? targetDisplay : null);

  const sourceLabel =
    asStr((ctx as any)?.source) ??
    asStr((ctx as any)?.identity_source) ??
    (targetType === 'identity_source' ? targetDisplay : null) ??
    asStr(ev?.entity_id);

  const tagLabel =
    asStr((ctx as any)?.tag) ??
    asStr((ctx as any)?.tag_name) ??
    (asStr((ctx as any)?.tag_id) ? `#${asStr((ctx as any)?.tag_id)}` : null) ??
    'tag';

  const identityLabel =
    asStr((ctx as any)?.identity) ??
    asStr((ctx as any)?.identity_name) ??
    asStr((ctx as any)?.identity_id) ??
    null;

  // Provisioning log entries keep their facts under metadata.details
  const details = ((ctx as any)?.details && typeof (ctx as any).details === 'object' ? (ctx as any).details : ctx) as Record<string, unknown>;

  return {
    action: asStr(ev?.action) ?? 'event',
    group: asStr(details?.group_name) ?? asStr((ctx as any)?.group_name) ?? t('the AD group'),
    ou: asStr(details?.target_ou_dn) ?? t('the zone organizational unit'),
    message: provisioningErrorMessage(details?.code) ?? asStr(details?.message) ?? '',
    zone: zoneLabel,
    root: rootLabel,
    endpoint:
      asStr((ctx as any)?.endpoint) ??
      targetDisplay ??
      asStr((ctx as any)?.after?.name) ??
      asStr((ctx as any)?.before?.name) ??
      asStr((ctx as any)?.after?.host) ??
      asStr((ctx as any)?.before?.host) ??
      asStr(ev?.endpoint_id) ??
      asStr(ev?.entity_id),
    // Levels arrive in English (« Read access ») and are translated here
    profile: profileLabel ? t(profileLabel) : profileLabel,
    user:
      asStr((ctx as any)?.user) ??
      asStr((ctx as any)?.username) ??
      asStr((ctx as any)?.subject) ??
      identityLabel ??
      actor,
    role: asStr((ctx as any)?.role),
    source: sourceLabel,
    target: targetDisplay,
    resource: targetDisplay,
    tag: tagLabel,
    owners_count: ownersCount,
    guardians_count: guardianIds.length,
    changes,
  };
}

type ActivityRender = {
  title: string;
  description: string;
  badge: { label: string; kind: 'info' | 'admin' | 'critical' };
  icon?: string;
};

function humanizeAction(value: string): string {
  const normalized = String(value ?? '').trim();
  if (!normalized) return t('Activity recorded');

  const known: Record<string, string> = {
    'storage_root.created': t('Storage root created'),
    'storage_root.updated': t('Storage root updated'),
    'storage_root.deleted': t('Storage root removed'),
    'storage_root.owners.replaced': t('Owners updated'),
    'storage_root.role.assigned': t('Owner assigned'),
    'storage_root.role.removed': t('Owner removed'),
    'storage_root.probe_rerun': t('Storage root probe run'),
    storage_root_created: t('Storage root created'),
    storage_root_updated: t('Storage root updated'),
    storage_root_deleted: t('Storage root removed')
  };

  if (known[normalized]) return known[normalized];

  return normalized
    .replace(/^[a-z0-9]+[._-]/i, '')
    .replace(/[._-]+/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export function renderActivity(ev: any): ActivityRender {
  const action = String(ev?.action ?? 'event');
  const tpl = activityTemplates[action];
  const vars = varsFromEvent(ev);

  const title = tpl ? t(tpl.titleKey, vars) : humanizeAction(action);
  const description = tpl
    ? t(tpl.descriptionKey, vars)
    : (vars.target ? `Activity recorded on ${vars.target}` : t('Activity recorded'));

  const badgeKind = badgeFromEvent(ev, tpl);
  const badgeLabel = resolveBadgeLabel(badgeKind);

  return {
    title,
    description,
    badge: { label: badgeLabel, kind: badgeKind },
    icon: tpl?.icon ?? 'activity'
  };
}
