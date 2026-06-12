<script lang="ts">
  import type { ProvisioningPreviewModel } from './provisioning-policy.types';

  export let model: ProvisioningPreviewModel;

  const statusClass = () => `provisioning-status-badge provisioning-status-badge--${model.status}`;
</script>

<article class="provisioning-card">
  <header class="provisioning-card__header">
    <h2 class="provisioning-card__title">Provisioning Preview</h2>
  </header>

  <div class="provisioning-card__body">
    <div class={statusClass()}>{model.statusLabel}</div>

    <div class="provisioning-preview-table" role="table" aria-label="Provisioning preview values">
      <div class="provisioning-preview-row" role="row">
        <span class="provisioning-preview-key" role="cell">Root code:</span>
        <span class="provisioning-preview-value" role="cell"><strong>{model.rootCode}</strong></span>
      </div>
      <div class="provisioning-preview-row" role="row">
        <span class="provisioning-preview-key" role="cell">READ group:</span>
        <span class="provisioning-preview-value" role="cell"><strong>{model.readGroup}</strong></span>
      </div>
      <div class="provisioning-preview-row" role="row">
        <span class="provisioning-preview-key" role="cell">WRITE group:</span>
        <span class="provisioning-preview-value" role="cell"><strong>{model.writeGroup}</strong></span>
      </div>
    </div>
  </div>
</article>
