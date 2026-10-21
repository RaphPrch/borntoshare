<script lang="ts">
  import { setLocale, type Locale } from '$lib/i18n';

  export let data: { locale: Locale };

  // Runs before any child renders (server and browser), so t() uses the request locale
  $: setLocale(data.locale);
  setLocale(data.locale);
</script>

<slot />
