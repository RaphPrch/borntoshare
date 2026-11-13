<script lang="ts">
  

  interface Props {
    /**
   * TagPill
   * -------
   * Normalized tag display component.
   *
   * Rules:
   * - Presentation only
   * - No business logic
   * - Color comes from backend
   * - Styled via `app.css`
   */
    label: string;
    color?: string | null;
    small?: boolean;
  }

  let { label, color = null, small = false }: Props = $props();
</script>

<span
  class={`b2s-tag-pill ${small ? 'sm' : ''}`}
  style={color ? `--tag-color: ${color}` : ""}
>
  {label}
</span>
