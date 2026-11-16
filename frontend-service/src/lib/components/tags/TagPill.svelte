<script lang="ts">
  import { t } from '$lib/i18n';

  /**
   * TagPill: a tag as a pill (color from the backend, styled in app.css). A tag set by a policy carries a small
   * lightning and says which one, and whether it follows the condition (it goes when the folder no longer matches).
   */
  interface Props {
    label: string;
    color?: string | null;
    small?: boolean;
    policy?: string | null;
    automatic?: boolean;
  }

  let { label, color = null, small = false, policy = null, automatic = false }: Props = $props();
  let title = $derived(policy
    ? automatic
      ? t('Automatic: set by the policy « {name} », taken off when the folder no longer matches.', { name: policy })
      : t('Set by the policy « {name} »; removing it stays a human choice.', { name: policy })
    : undefined);
</script>

<span class={`b2s-tag-pill ${small ? 'sm' : ''}`} style={color ? `--tag-color: ${color}` : ''} {title}>
  {#if policy}<i class="bi bi-lightning-charge-fill b2s-tag-pill__auto" aria-hidden="true"></i><span class="b2s-visually-hidden">{title}</span>{/if}{label}
</span>

<style>
  .b2s-tag-pill__auto { margin-right: 3px; font-size: 0.85em; opacity: 0.75; }
</style>
