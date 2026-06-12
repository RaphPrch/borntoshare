import en from './locales/en.json';
import fr from './locales/fr.json';

export type Locale = 'en' | 'fr';

const dictionaries: Record<Locale, any> = { en, fr };

function getNavigatorLocale(): Locale {
  if (typeof navigator === 'undefined') return 'en';
  const l = (navigator.language || 'en').toLowerCase();
  return l.startsWith('fr') ? 'fr' : 'en';
}

let currentLocale: Locale = getNavigatorLocale();

export function setLocale(locale: Locale) {
  currentLocale = locale;
}

export function getLocale(): Locale {
  return currentLocale;
}

function getByPath(obj: any, path: string): any {
  return path.split('.').reduce((acc, k) => (acc && acc[k] != null ? acc[k] : null), obj);
}

function interpolate(template: string, vars: Record<string, any>) {
  return template.replace(/\{([^}]+)\}/g, (_, key) => {
    const v = vars[key.trim()];
    return v == null ? '' : String(v);
  });
}

export function t(key: string, vars: Record<string, any> = {}, locale: Locale = currentLocale): string {
  const dict = dictionaries[locale] ?? dictionaries.en;
  const raw = getByPath(dict, key);
  if (typeof raw === 'string') return interpolate(raw, vars);
  return key;
}
