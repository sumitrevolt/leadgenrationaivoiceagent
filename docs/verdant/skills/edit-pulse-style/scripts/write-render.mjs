#!/usr/bin/env node
/**
 * Taskflow render.json writer.
 *
 * Validates the input JSON then atomically writes it to the target path.
 * The target path is resolved from VERDENT_HOME, which must point to the current manager workspace.
 *
 * Usage:
 *   node write-render.mjs <file.json>
 *
 * Exit 0 + {"ok":true,"path":"..."}             — written successfully
 * Exit 1 + {"ok":false,"errors":[...]}           — validation failed
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, isAbsolute, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';

// ---------------------------------------------------------------------------
// Path resolution (mirrors getPreviewDirectory in shared)
// ---------------------------------------------------------------------------

function getVerdentDir() {
  if (!process.env.VERDENT_HOME) {
    throw new Error('VERDENT_HOME is required for manager skills');
  }
  return process.env.VERDENT_HOME;
}

function getTargetPath() {
  return join(getVerdentDir(), 'preview', 'taskflow.render.json');
}

function isInsidePulseTempDir(filePath) {
  const tempDir = resolve(getVerdentDir(), 'tmp', 'edit-pulse-style');
  const resolvedPath = resolve(filePath);
  const rel = relative(tempDir, resolvedPath);
  return rel === '' || (!rel.startsWith('..') && !isAbsolute(rel));
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

function main() {
  // 1. Read input
  let input;
  const filePath = process.argv[2];

  if (!filePath) {
    console.log(JSON.stringify({ ok: false, errors: ['Input file path is required'] }));
    process.exit(1);
  }
  if (!isInsidePulseTempDir(filePath)) {
    console.log(JSON.stringify({ ok: false, errors: ['Input file must be under VERDENT_HOME/tmp/edit-pulse-style'] }));
    process.exit(1);
  }
  try {
    input = readFileSync(filePath, 'utf-8');
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    console.log(JSON.stringify({ ok: false, errors: [`Failed to read file: ${msg}`] }));
    process.exit(1);
  }

  // 2. Parse JSON
  let data;
  try {
    data = JSON.parse(input);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    console.log(JSON.stringify({ ok: false, errors: [`Invalid JSON: ${msg}`] }));
    process.exit(1);
  }

  // 2.5. Normalize chart colors before validation.
  // The LLM can omit chart colors; writer assigns stable, unique category colors.
  normalizeChartColors(data);

  // 3. Validate via validate-render.mjs (co-located script)
  const validateScript = join(dirname(fileURLToPath(import.meta.url)), 'validate-render.mjs');
  try {
    execFileSync('node', [validateScript], {
      input: JSON.stringify(data),
      encoding: 'utf-8',
      timeout: 10000,
    });
  } catch (e) {
    // validate-render exits 1 on failure, stdout contains the error JSON
    const stdout = e.stdout || '';
    try {
      const result = JSON.parse(stdout);
      console.log(JSON.stringify({ ok: false, errors: result.errors || ['Validation failed'] }));
    } catch {
      console.log(JSON.stringify({ ok: false, errors: [stdout || 'Validation failed'] }));
    }
    process.exit(1);
  }

  // 3.5. Merge meta & bump version from existing file
  const targetPath = getTargetPath();
  if (existsSync(targetPath)) {
    try {
      const existing = JSON.parse(readFileSync(targetPath, 'utf-8'));

      // Merge meta: existing fields preserved, new fields override
      if (existing?.meta) {
        data.meta = { ...existing.meta, ...(data.meta || {}) };
      }

      // Auto-bump top-level version using semver patch increments.
      const baseVersion = toSemver(existing?.version);
      const nextVersion = bumpPatchVersion(baseVersion);
      data.version = nextVersion;
      if (data.meta?.revision !== undefined || existing?.meta?.revision !== undefined) {
        if (!data.meta) data.meta = {};
        data.meta.revision = nextVersion;
      }
    } catch {
      // existing file unreadable/invalid — skip merge
    }
  }

  // 4. Write to target path
  const targetDir = dirname(targetPath);

  if (!existsSync(targetDir)) {
    mkdirSync(targetDir, { recursive: true });
  }

  const content = JSON.stringify(data, null, 2) + '\n';
  writeFileSync(targetPath, content, 'utf-8');

  // 5. Verify write
  const readBack = readFileSync(targetPath, 'utf-8');
  if (readBack !== content) {
    console.log(JSON.stringify({ ok: false, errors: ['Write verification failed: file was clobbered'] }));
    process.exit(1);
  }

  console.log(JSON.stringify({ ok: true, path: targetPath }));
  process.exit(0);
}

function toSemver(version) {
  const parts = String(version ?? '').split('.').map(Number);
  if (parts.some(Number.isNaN)) return '1.0.0';
  while (parts.length < 3) parts.push(0);
  if (parts.length !== 3) return '1.0.0';
  return parts.join('.');
}

function bumpPatchVersion(version) {
  const parts = toSemver(version).split('.').map(Number);
  parts[2] += 1;
  return parts.join('.');
}

function normalizeChartColors(data) {
  const elements = data?.spec?.elements;
  if (!elements || typeof elements !== 'object') return;

  for (const element of Object.values(elements)) {
    if (!element || typeof element !== 'object') continue;
    const props = element.props;
    if (!props || typeof props !== 'object') continue;

    if (element.type === 'BarChart') {
      normalizeColorArray(props.items);
    } else if (element.type === 'DonutChart') {
      normalizeColorArray(props.segments);
    } else if (element.type === 'LineChart' || element.type === 'StackedBar') {
      normalizeColorArray(props.series);
    }
  }
}

function normalizeColorArray(items) {
  if (!Array.isArray(items)) return;

  const used = new Set();
  for (let i = 0; i < items.length; i++) {
    const item = items[i];
    if (!item || typeof item !== 'object') continue;

    const color = item.color;
    if (typeof color === 'string' && isValidGeneratedColor(color) && !used.has(color)) {
      used.add(color);
      continue;
    }

    const seed = String(item.label ?? item.id ?? i);
    item.color = generateUniqueChartColor(seed, i, used);
    used.add(item.color);
  }
}

function isValidGeneratedColor(color) {
  return /^(info|success|warning|error|neutral)$/.test(color) || /^#[0-9a-fA-F]{6}$/.test(color);
}

function generateUniqueChartColor(seed, index, used) {
  for (let attempt = 0; attempt < 256; attempt++) {
    const candidate = chartColorFromPalette(index + attempt);
    if (!used.has(candidate)) return candidate;
  }
  const hue = (hashString(seed) + Math.round(index * 137.508)) % 360;
  return hslToHex(hue, 68, 48);
}

function chartColorFromPalette(index) {
  const families = [
    { hue: 210, offsets: [0, -10, 10, -18, 18], saturation: 70 }, // info: blue/cyan
    { hue: 150, offsets: [0, 12, -12, 20, -20], saturation: 64 }, // success: green/teal
    { hue: 40, offsets: [0, -10, 10, -18, 18], saturation: 78 }, // warning: amber/orange
    { hue: 350, offsets: [0, 10, -10, 18, -18], saturation: 72 }, // error: red/rose
    { hue: 265, offsets: [0, -16, 16, -28, 28], saturation: 54 }, // neutral/accent: violet/slate
  ];
  const lightnessSteps = [48, 42, 56, 36, 62, 52, 44, 58, 40, 54, 46, 60];
  const family = families[index % families.length];
  const round = Math.floor(index / families.length);
  const hueOffset = family.offsets[round % family.offsets.length];
  const hueShift = Math.floor(round / family.offsets.length) * 7;
  const hue = normalizeHue(family.hue + hueOffset + hueShift);
  const lightness = lightnessSteps[round % lightnessSteps.length];
  const saturation = Math.max(42, Math.min(82, family.saturation - Math.floor(round / 12) * 3));

  return hslToHex(hue, saturation, lightness);
}

function normalizeHue(hue) {
  return ((hue % 360) + 360) % 360;
}

function hashString(input) {
  let hash = 2166136261;
  for (let i = 0; i < input.length; i++) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return Math.abs(hash >>> 0);
}

function hslToHex(h, s, l) {
  s /= 100;
  l /= 100;
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs((h / 60) % 2 - 1));
  const m = l - c / 2;
  let r = 0;
  let g = 0;
  let b = 0;

  if (h < 60) [r, g, b] = [c, x, 0];
  else if (h < 120) [r, g, b] = [x, c, 0];
  else if (h < 180) [r, g, b] = [0, c, x];
  else if (h < 240) [r, g, b] = [0, x, c];
  else if (h < 300) [r, g, b] = [x, 0, c];
  else [r, g, b] = [c, 0, x];

  return `#${[r, g, b]
    .map(v => Math.round((v + m) * 255).toString(16).padStart(2, '0'))
    .join('')}`;
}

main();
