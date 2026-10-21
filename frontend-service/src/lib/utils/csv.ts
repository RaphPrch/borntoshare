// CSV export of the rows currently shown in a list (filters applied, every page).

export type CsvColumn<T> = { header: string; value: (row: T) => unknown };

const escapeCell = (value: unknown): string => {
  const text = value === null || value === undefined ? '' : String(value);
  // Neutralise spreadsheet formulas (=, +, -, @) and quote when needed
  const safe = /^[=+\-@]/.test(text) ? `'${text}` : text;
  return /[";\n\r]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
};

export const toCsv = <T>(columns: CsvColumn<T>[], rows: T[]): string => {
  const lines = [columns.map((c) => escapeCell(c.header)).join(';')];
  for (const row of rows) lines.push(columns.map((c) => escapeCell(c.value(row))).join(';'));
  return lines.join('\r\n');
};

/** Triggers a browser download; the BOM keeps accents readable when opened in Excel. */
export const downloadCsv = <T>(filename: string, columns: CsvColumn<T>[], rows: T[]): void => {
  const blob = new Blob(['﻿', toCsv(columns, rows)], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
};

export const csvFilename = (base: string): string => `${base}-${new Date().toISOString().slice(0, 10)}.csv`;
