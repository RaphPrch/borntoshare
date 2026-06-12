export type EntityAlertTone = 'warning' | 'error';

export type EntityAlertStripItem = {
  key: string;
  title: string;
  subtitle?: string | null;
  tone?: EntityAlertTone;
};
