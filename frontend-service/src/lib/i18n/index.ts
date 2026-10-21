/**
 * Interface translations (French / English).
 *
 *   t('Save changes')                   source text is the key (gettext style)
 *   t('Showing {count} items', { count })
 *   t('activity.zone.created.title')    dotted keys of the nested catalogs (activity feed)
 *
 * Source texts are mostly English: fr.json translates them. Source texts still written
 * in French are translated by en.json. A missing entry falls back to the source text.
 *
 * The locale is chosen per request (cookie `b2s_lang`, else Accept-Language) by
 * hooks.server.ts, stamped on <html lang> and set by the root layout before rendering.
 * Changing the language reloads the page, so t() needs no reactivity.
 */
import en from './locales/en.json';
import fr from './locales/fr.json';

export type Locale = 'en' | 'fr';

export const LOCALES: Locale[] = ['fr', 'en'];
export const LOCALE_COOKIE = 'b2s_lang';
export const DEFAULT_LOCALE: Locale = 'fr';

type Catalog = { [key: string]: string | Catalog };
const catalogs: Record<Locale, Catalog> = { en, fr };

export const isLocale = (value: unknown): value is Locale => value === 'en' || value === 'fr';

// Browser: the locale the server stamped on <html lang>. Server and tests: the source
// language until the root layout sets the request locale.
const initialLocale = (): Locale => {
  if (typeof document === 'undefined') return 'en';
  const lang = document.documentElement.lang;
  return isLocale(lang) ? lang : DEFAULT_LOCALE;
};

let currentLocale: Locale = initialLocale();

export function setLocale(locale: Locale): void {
  currentLocale = locale;
}

export function getLocale(): Locale {
  return currentLocale;
}

/** BCP 47 tag for Intl / toLocaleString */
export function intlLocale(): string {
  return currentLocale === 'fr' ? 'fr-FR' : 'en-GB';
}

/** Pick the locale from an Accept-Language header value */
export function localeFromAcceptLanguage(header: string | null | undefined): Locale {
  for (const part of String(header ?? '').split(',')) {
    const tag = part.split(';')[0].trim().toLowerCase();
    if (tag.startsWith('fr')) return 'fr';
    if (tag.startsWith('en')) return 'en';
  }
  return DEFAULT_LOCALE;
}

function lookup(catalog: Catalog, key: string): string | null {
  const flat = catalog[key];
  if (typeof flat === 'string') return flat;
  if (!key.includes('.') || key.includes(' ')) return null;
  let node: string | Catalog | undefined = catalog;
  for (const part of key.split('.')) {
    if (!node || typeof node === 'string') return null;
    node = node[part];
  }
  return typeof node === 'string' ? node : null;
}

function interpolate(template: string, vars: Record<string, unknown>): string {
  return template.replace(/\{([^{}]+)\}/g, (_, name) => {
    const value = vars[String(name).trim()];
    return value == null ? '' : String(value);
  });
}

export function t(key: string, vars: Record<string, unknown> = {}, locale: Locale = currentLocale): string {
  // A sentence missing from the catalog is shown as written; only dotted keys fall back to English
  const isDottedKey = /^[a-z_]+(\.[a-z_]+)+$/i.test(key);
  const text = lookup(catalogs[locale], key) ?? (isDottedKey ? lookup(catalogs.en, key) : null) ?? key;
  // Without variables the text is returned as is (it may contain literal braces, e.g. {PREFIX})
  return Object.keys(vars).length > 0 ? interpolate(text, vars) : text;
}
