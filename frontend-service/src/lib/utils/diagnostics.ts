// Sentences of the diagnostic (Observability › Health): the core gives a code, a result and values; what it means
// and what to do are written here, in the languages of the interface.
import { t } from '$lib/i18n';
import type { DiagnosticCheck, DiagnosticResult, DiagnosticSeverity } from '$lib/api/infrastructure';
import type { StatusVariant } from '$lib/utils/status';

type Values = Record<string, unknown>;
type Texts = { title: () => string; ok: (v: Values) => string; problem: (v: Values) => string; action: (v: Values) => string };

// The core names 10 at most: « … » when there are more
const names = (v: Values) => {
  const list = Array.isArray(v.names) ? (v.names as unknown[]).map(String) : [];
  const total = Number(v.down ?? v.count ?? list.length);
  return list.join(', ') + (total > list.length ? ', …' : '');
};

const TEXTS: Record<string, Texts> = {
  'config.internal_token': {
    title: () => t('Internal token of the services'),
    ok: (v) => t('{length} characters.', v),
    problem: (v) => t('{length} characters, {minimum} at least: the services trust each other with it.', v),
    action: (v) => t('Set a random INTERNAL_TOKEN of {minimum} characters or more in .env, then make deploy.', v)
  },
  'config.service_tokens': {
    title: () => t('Identity of the services'),
    ok: () => t('Each service has its own token and the person is signed: a service cannot pass for another, nor for someone.'),
    problem: (v) =>
      !v.key
        ? t('Tokens per service without the signing key: core-service refuses every person.')
        : Array.isArray(v.missing) && (v.missing as unknown[]).length < 4
          ? t('Tokens missing for: {names}.', { names: (v.missing as unknown[]).map(String).join(', ') })
          : t('Mode of before: the services share one token and core-service believes the identity they declare.'),
    action: () => t('Run make deploy: it creates the token of each service in .env and gives them to the services.')
  },
  'config.master_key': {
    title: () => t('Key of the stored passwords'),
    ok: () => t('Present: the passwords of directories and servers can be read.'),
    problem: () => t('Missing or unusable: no stored password can be read.'),
    action: () => t('Restore the secret b2s_master_key from a complete backup (make restore), then make deploy.')
  },
  'secrets.missing': {
    title: () => t('Stored passwords'),
    ok: () => t('Every password reference leads to a stored password.'),
    problem: (v) => t('{count} object(s) without their password: {names}.', { ...v, names: names(v) }),
    action: () => t('Enter the password again on each object (the Dashboard lists them).')
  },
  'database.application': {
    title: () => t('Application database'),
    ok: (v) => t('Answers in {latency_ms} ms ({message}).', v),
    problem: (v) => String(v.message ?? ''),
    action: () => t('Check that MariaDB runs and is reachable (DB_HOST, DB_PORT of .env) and its load.')
  },
  'database.audit': {
    title: () => t('Audit database'),
    ok: (v) => t('Answers in {latency_ms} ms ({message}).', v),
    problem: (v) => String(v.message ?? ''),
    action: () => t('Check that MariaDB runs and is reachable (DB_HOST, DB_PORT of .env) and its load.')
  },
  'queue.redis': {
    title: () => t('Job queue (Redis)'),
    ok: (v) => t('Answers in {latency_ms} ms.', v),
    problem: (v) => String(v.message ?? ''),
    action: () => t('Start Redis (podman start redis): the queued jobs resume.')
  },
  'database.tables': {
    title: () => t('Database schema'),
    ok: () => t('Every expected table is present.'),
    problem: (v) => t('{count} table(s) missing: {names}.', { ...v, names: names(v) }),
    action: () => t('Run make deploy: it replays the SQL packs.')
  },
  'database.schema_rights': {
    title: () => t('Rights of the application account'),
    ok: (v) => t('The account {user} cannot change the schema (least privilege).', v),
    problem: (v) => t('The account {user} can change the schema: more rights than it needs.', v),
    action: () => t('Keep the schema rights for the migration account only (the wizard creates both accounts).')
  },
  'disk.space': {
    title: () => t('Disk space'),
    ok: (v) => t('{percent}% used, {free_gb} GB free of {total_gb} GB.', v),
    problem: (v) => t('{percent}% used, {free_gb} GB free of {total_gb} GB.', v),
    action: () => t('Free space: unused images (podman image prune), old backups, logs.')
  },
  'jobs.queue': {
    title: () => t('Queued jobs'),
    ok: (v) => t('{waiting} job(s) waiting, none for more than {limit_seconds} s.', v),
    problem: (v) => t('{stuck} job(s) waiting for more than {limit_seconds} s: no worker takes them.', v),
    action: () => t('Check the workers and Redis; the watchdog republishes these jobs, then closes them as failed.')
  },
  'jobs.abandoned': {
    title: () => t('Running jobs'),
    ok: (v) => t('{running} job(s) running, none abandoned.', v),
    problem: (v) => t('{count} job(s) still running beyond the time limit of their worker.', v),
    action: () => t('The watchdog closes them as failed (JOB_ABANDONED); « Flush the stuck jobs » does it now.')
  },
  'workers.available': {
    title: () => t('Workers'),
    ok: (v) => t('{total} worker(s), all answering.', v),
    problem: (v) =>
      Number(v.total) === 0 ? t('No worker declared: no job can run.') : t('{down} of {total} worker(s) not answering: {names}.', { ...v, names: names(v) }),
    action: () => t('Check the worker (its container, its /health), then run a health check.')
  },
  'health.schedule': {
    title: () => t('Regular health check'),
    ok: (v) => t('Every {interval_minutes} min, last run {last_run_minutes} min ago.', v),
    problem: (v) => (v.enabled ? t('Not run for {last_run_minutes} min.', v) : t('Disabled: the components are no longer checked.')),
    action: () => t('Enable the task « health_check » in Advanced Settings › Infrastructure, and check the workers.')
  },
  'components.directories': {
    title: () => t('Directories (LDAP)'),
    ok: (v) => t('{total} directory(ies), all answering.', v),
    problem: (v) => t('{down} of {total} directory(ies) not answering: {names}.', { ...v, names: names(v) }),
    action: () => t('Test each directory from its page (address, certificate, service account).')
  },
  'components.group_ous': {
    title: () => t('Permissions in the group OUs'),
    ok: () => t('Access groups can be created in every OU in use.'),
    problem: (v) => t('{down} OU(s) where groups cannot be created: {names}.', { ...v, names: names(v) }),
    action: () => t('Give the provisioning account the right to create groups in these OUs.')
  },
  'components.file_servers': {
    title: () => t('File servers (SMB)'),
    ok: (v) => t('{total} server(s), all answering.', v),
    problem: (v) => t('{down} of {total} server(s) not answering: {names}.', { ...v, names: names(v) }),
    action: () => t('Check each server from its page (address, port 445, account).')
  },
  'components.sso': {
    title: () => t('Single sign-on (Keycloak)'),
    ok: (v) => t('{total} provider(s), all answering.', v),
    problem: (v) => t('{down} of {total} provider(s) not answering: {names}.', { ...v, names: names(v) }),
    action: () => t('Check the Keycloak address and certificate in Advanced Settings › Infrastructure.')
  },
  'module.fives': {
    title: () => t('5S module'),
    ok: () => t('Installed and answering.'),
    problem: () => t('Licensed and switched on, but fives-service does not answer: its screens are hidden.'),
    action: () => t('Start the module (make deploy), then check fives-service.')
  }
};

export type DiagnosticLine = { title: string; detail: string; action: string | null };

/** The sentences of one check; a code the interface does not know yet is shown by its code */
export function describeCheck(check: DiagnosticCheck): DiagnosticLine {
  const texts = TEXTS[check.code];
  if (!texts) return { title: check.code, detail: '', action: null };
  if (check.result === 'unknown') {
    return { title: texts.title(), detail: t('This check could not run (core log: DIAGNOSTIC_CHECK_FAILED).'), action: null };
  }
  return check.result === 'ok'
    ? { title: texts.title(), detail: texts.ok(check.values), action: null }
    : { title: texts.title(), detail: texts.problem(check.values), action: texts.action(check.values) };
}

export const knownChecks = (): string[] => Object.keys(TEXTS);

const RESULT_ORDER: Record<DiagnosticResult, number> = { error: 0, warning: 1, unknown: 2, ok: 3 };
const SEVERITY_ORDER: Record<DiagnosticSeverity, number> = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };

/** Problems first, the most severe at the top */
export function sortChecks(checks: DiagnosticCheck[]): DiagnosticCheck[] {
  return [...checks].sort((a, b) => RESULT_ORDER[a.result] - RESULT_ORDER[b.result] || SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]);
}

export const RESULT_VARIANT: Record<DiagnosticResult, StatusVariant> = { ok: 'success', warning: 'warning', error: 'error', unknown: 'muted' };

export function resultLabel(result: DiagnosticResult): string {
  return { ok: t('OK'), warning: t('Warning'), error: t('Failed'), unknown: t('Unknown') }[result];
}

export function severityLabel(severity: DiagnosticSeverity): string {
  return { critical: t('Critical'), high: t('High'), medium: t('Medium'), low: t('Low'), info: t('Info') }[severity];
}
