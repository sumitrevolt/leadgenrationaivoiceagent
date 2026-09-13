/* Shared formatting + class helpers for the admin dashboard.
 * Dependency-light: only `clsx` (already a project dependency). */
import { clsx } from 'clsx';
import type { ClassValue } from 'clsx';

/** Join conditional class names. */
export function cn(...inputs: ClassValue[]): string {
  return clsx(inputs);
}

const numberFmt = new Intl.NumberFormat('en-IN');

/** 12345 -> "12,345" (Indian digit grouping). */
export function formatNumber(value: number): string {
  return numberFmt.format(Number.isFinite(value) ? value : 0);
}

/** 12.5 -> "12.5%" (values are already 0-100, never multiplied by 100). */
export function formatPercent(value: number, digits = 1): string {
  const n = Number.isFinite(value) ? value : 0;
  return `${n.toFixed(digits).replace(/\.0+$/, '')}%`;
}

/** Indian Rupee currency formatter, used across the UI as `inr.format(n)`. */
export const inr = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 0,
});

const dateTimeFmt = new Intl.DateTimeFormat('en-IN', {
  day: '2-digit',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

function toDate(input: string | number | Date | null | undefined): Date | null {
  if (input === null || input === undefined || input === '') return null;
  const d = input instanceof Date ? input : new Date(input);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** ISO/epoch -> "12 Sep 2026, 05:30 pm". Em dash for missing/invalid input. */
export function formatDateTime(input: string | number | Date | null | undefined): string {
  const d = toDate(input);
  return d ? dateTimeFmt.format(d) : '\u2014';
}

const RELATIVE_UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 365 * 24 * 60 * 60 * 1000],
  ['month', 30 * 24 * 60 * 60 * 1000],
  ['day', 24 * 60 * 60 * 1000],
  ['hour', 60 * 60 * 1000],
  ['minute', 60 * 1000],
];

const relativeFmt = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });

/** ISO/epoch -> "just now" / "5 minutes ago" / "3 days ago". Em dash if unknown. */
export function formatRelative(input: string | number | Date | null | undefined): string {
  const d = toDate(input);
  if (!d) return '\u2014';
  const diff = d.getTime() - Date.now();
  const abs = Math.abs(diff);
  if (abs < 45 * 1000) return 'just now';
  for (const [unit, ms] of RELATIVE_UNITS) {
    if (abs >= ms) return relativeFmt.format(Math.round(diff / ms), unit);
  }
  return relativeFmt.format(Math.round(diff / 1000), 'second');
}

/** Seconds -> "45s" / "3m 12s" / "1h 04m". */
export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.round(Number.isFinite(seconds) ? seconds : 0));
  if (total < 60) return `${total}s`;
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  if (mins < 60) return `${mins}m ${String(secs).padStart(2, '0')}s`;
  const hours = Math.floor(mins / 60);
  return `${hours}h ${String(mins % 60).padStart(2, '0')}m`;
}

/** Best-effort Indian phone formatting; returns the input unchanged if unrecognised. */
export function formatPhone(raw: string): string {
  if (!raw) return '';
  const digits = raw.replace(/\D/g, '');
  const ten = digits.length > 10 ? digits.slice(-10) : digits;
  if (ten.length === 10) return `+91 ${ten.slice(0, 5)} ${ten.slice(5)}`;
  return raw;
}

/** "real_estate" / "real-estate" -> "Real Estate". */
export function titleCase(input: string): string {
  return String(input ?? '')
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .split(' ')
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

function csvCell(value: unknown): string {
  if (value === null || value === undefined) return '';
  const s = typeof value === 'object' ? JSON.stringify(value) : String(value);
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/** Download rows as a CSV file in the browser (union of keys as headers). */
export function downloadCsv(filename: string, rows: Record<string, unknown>[]): void {
  const list = Array.isArray(rows) ? rows : [];
  const headers: string[] = [];
  for (const row of list) {
    for (const key of Object.keys(row)) if (!headers.includes(key)) headers.push(key);
  }
  const lines = [headers.join(',')];
  for (const row of list) lines.push(headers.map((h) => csvCell(row[h])).join(','));
  const blob = new Blob([lines.join('\r\n')], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** Promise-based sleep helper used by the mock API client. */
export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
