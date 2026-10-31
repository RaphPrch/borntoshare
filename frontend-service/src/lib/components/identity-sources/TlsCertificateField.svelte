<script lang="ts">
  import { t } from '$lib/i18n';
  import { toast } from '$lib/stores/toast';
  import { formatDate } from '$lib/utils/format';
  import ConfirmActionModal from '$lib/components/ui/ConfirmActionModal.svelte';
  import { runProbeWithPolling } from '$lib/jobs/probe-runner';

  /** Certificate authority or server certificate trusted for this directory (PEM) */
  export let pem = '';
  /** Name in the certificate: filled when the host is an IP address */
  export let serverName = '';
  export let host = '';
  export let port: number | string | null = 636;
  export let id = 'tls-certificate';
  export let inputClass = '';
  export let hintClass = '';
  export let onChange: () => void = () => {};

  type Found = {
    certificate_pem: string;
    is_authority: boolean;
    subject: string;
    issuer: string;
    not_after: string;
    sha256: string;
    server_names: string[];
  };

  let fetching = false;
  let found: Found | null = null;

  const isIpAddress = (value: string) => /^[0-9.]+$/.test(value) || value.includes(':');
  const fingerprint = (value: string) => (value.match(/.{2}/g) ?? []).join(':').toUpperCase();

  async function fetchCertificate() {
    if (!host.trim()) {
      toast.error(t('Enter the host first.'));
      return;
    }
    fetching = true;
    try {
      const result: any = await runProbeWithPolling({
        fetchFn: fetch,
        request: {
          kind: 'identity-source',
          protocol: 'tls-certificate',
          scope: 'read',
          target: { host: host.trim(), port: Number(port) || 636 },
          options: { timeout_sec: 10 },
          context: { ui_origin: 'admin' }
        },
        intervalMs: 800,
        maxAttempts: 30
      });
      const details = result.result?.details ?? {};
      if (result.ok && details.certificate_pem) found = details as Found;
      else toast.error(t(String(result.errorMessage ?? result.result?.message ?? 'Unable to read the certificate.')));
    } catch (error) {
      toast.error(error instanceof Error && error.message ? error.message : t('Unable to read the certificate.'));
    } finally {
      fetching = false;
    }
  }

  function keep() {
    if (!found) return;
    pem = found.certificate_pem;
    // By IP address, the name cannot be checked without the one of the certificate
    if (isIpAddress(host.trim()) && !serverName.trim()) serverName = found.server_names[0] ?? '';
    found = null;
    onChange();
    toast.success(t('Certificate kept. Test the directory to confirm.'));
  }

  $: expired = found ? new Date(found.not_after).getTime() < Date.now() : false;
</script>

<button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm tls-fetch" disabled={fetching} on:click={fetchCertificate}>
  <i class="bi bi-cloud-download" aria-hidden="true"></i>
  {fetching ? t('Reading…') : t('Fetch the certificate')}
</button>
<textarea {id} class={inputClass} rows="4" bind:value={pem} on:input={onChange} placeholder="-----BEGIN CERTIFICATE-----"></textarea>
<small class={hintClass}>{t('Fetch it from the server, or paste the public certificate of the authority that signed the domain controller.')}</small>

<ConfirmActionModal
  open={Boolean(found)}
  onClose={() => (found = null)}
  onConfirm={keep}
  severity="warning"
  modalClass="b2s-modal b2s-confirm-modal b2s-confirm-modal--warning tls-confirm"
  impactTitle={t('Certificate')}
  title={t('Keep this certificate?')}
  subtitle={t('Compare the fingerprint with the one of the server: from now on, only this certificate is trusted.')}
  impactItems={found
    ? [
        t('Name: {value}', { value: found.subject }),
        t('Issued by: {value}', { value: found.issuer }),
        t('Expires on: {value}', { value: formatDate(found.not_after) }),
        t('SHA-256 fingerprint: {value}', { value: fingerprint(found.sha256) }),
        found.is_authority
          ? t('This is the authority: it stays valid when the server certificate is renewed.')
          : t('This is the server certificate: at its renewal, the connection stops until the new one is accepted here.'),
        ...(expired ? [t('This certificate has expired.')] : [])
      ]
    : []}
  confirmLabel={t('Keep this certificate')}
/>

<style>
  .tls-fetch { align-self: flex-start; }
  /* The fingerprint has no space: it must wrap, it is what the administrator compares */
  :global(.tls-confirm li) { overflow-wrap: anywhere; }
  :global(.tls-confirm ul) { min-width: 0; }
</style>
