<script lang="ts">
  /**
   * TagPill
   * -------
   * Normalized tag display component.
   *
   * Rules:
   * - Presentation only
   * - No business logic
   * - Color comes from backend
   * - Styled via `admin-entities.css`
   */

  export let label: string;
  export let color: string | null = null;
  export let small = false;
</script>

<span
  class={`b2s-tag-pill ${small ? 'sm' : ''}`}
  style={color ? `--tag-color: ${color}` : ""}
>
  {label}
</span>
