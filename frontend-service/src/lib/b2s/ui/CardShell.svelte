<script lang="ts">
  /**
   * CardShell — wrapper canonique B2S
   * - Conserve strictement le DOM attendu: <div class="b2s-card">...</div>
   * - Permet d’ajouter une classe optionnelle sans changer le rendu par défaut.
   */
  export let className: string = '';
</script>

<div class={"b2s-card " + className}>
  <slot />
</div>
