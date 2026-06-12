import { t } from '$lib/i18n';
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
    (zoneIdRaw ? `Zone #${zoneIdRaw}` : 'Unknown');
  const updatedFields = Array.isArray((ctx as any)?.updated_fields)
    ? (ctx as any).updated_fields
        .map((v: unknown) => String(v ?? '').trim())
        .filter(Boolean)
    : [];
  const changes = updatedFields.length
    ? ` — updated fields: ${updatedFields.map((f: string) => f.replaceAll('_', ' ')).join(', ')}`
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

  return {
    action: asStr(ev?.action) ?? 'event',
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
    profile: profileLabel,
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

export type ActivityRender = {
  title: string;
  description: string;
  badge: { label: string; kind: 'info' | 'admin' | 'critical' };
  icon?: string;
};

function humanizeAction(value: string): string {
  const normalized = String(value ?? '').trim();
  if (!normalized) return 'Activity recorded';

  const known: Record<string, string> = {
    'storage_root.created': 'Storage root created',
    'storage_root.updated': 'Storage root updated',
    'storage_root.deleted': 'Storage root removed',
    'storage_root.owners.replaced': 'Owners updated',
    'storage_root.role.assigned': 'Owner assigned',
    'storage_root.role.removed': 'Owner removed',
    'storage_root.probe_rerun': 'Storage root probe run',
    storage_root_created: 'Storage root created',
    storage_root_updated: 'Storage root updated',
    storage_root_deleted: 'Storage root removed'
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

  // Activity labels must be rendered in English regardless of browser locale.
  const title = tpl ? t(tpl.titleKey, vars, 'en') : humanizeAction(action);
  const description = tpl
    ? t(tpl.descriptionKey, vars, 'en')
    : (vars.target ? `Activity recorded on ${vars.target}` : 'Activity recorded');

  const badgeKind = badgeFromEvent(ev, tpl);
  const badgeLabel = resolveBadgeLabel(badgeKind);

  return {
    title,
    description,
    badge: { label: badgeLabel, kind: badgeKind },
    icon: tpl?.icon ?? 'activity'
  };
}
