<script lang="ts">
  import { untrack } from 'svelte';

  import { setLocale, type Locale } from '$lib/i18n';

  interface Props {
    data: { locale: Locale };
    children?: import('svelte').Snippet;
  }

  let { data, children }: Props = $props();

  // Runs before any child renders (server and browser), so t() uses the request locale
  $effect.pre(() => {
    const locale = data.locale;
    untrack(() => setLocale(locale));
  });
  // svelte-ignore state_referenced_locally (an initial value, read once as before)
  setLocale(data.locale);
</script>

{@render children?.()}
