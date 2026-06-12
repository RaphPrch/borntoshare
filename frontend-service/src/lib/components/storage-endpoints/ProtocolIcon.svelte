<script lang="ts">
  export let type: string | null | undefined;
  export let size: number = 20;
  export let showLabel: boolean = false;

  const map: Record<string, string> = {
    smb: 'bi-display',
    nfs: 'bi-square-fill',
    s3: 'bi-hexagon-fill',
    azure_blob: 'bi-triangle-fill',
  };

  const labelMap: Record<string, string> = {
    smb: 'SMB',
    nfs: 'NFS',
    s3: 'S3',
    azure_blob: 'Azure Blob',
  };

  const iconClass = map[type ?? ''] ?? 'bi-question-circle';
  const label = labelMap[type ?? ''] ?? 'Unknown';
</script>

<span class="protocol-wrapper">
  <i
    class={`bi ${iconClass} protocol-icon protocol-${type ?? 'unknown'}`}
    style={`font-size: ${size}px`}
    aria-hidden="true"
  ></i>
  {#if showLabel}
    <span class="protocol-label">{label}</span>
  {/if}
</span>

<style>
  .protocol-wrapper {
    display: inline-flex;
    align-items: center;
    gap: 8px;
  }

  .protocol-icon {
    line-height: 1;
  }

  /* Colors */
  .protocol-smb { color: #2563eb; }          /* blue */
  .protocol-nfs { color: #059669; }          /* green */
  .protocol-s3 { color: #f59e0b; }           /* amber */
  .protocol-azure_blob { color: #0284c7; }   /* azure */
  .protocol-unknown { color: #9ca3af; }      /* gray */

  .protocol-label {
    font-size: 14px;
    font-weight: 700;
    color: #0f172a;
  }
</style>
