#!/usr/bin/env node
/**
 * Taskflow prompt preparation script.
 *
 * Reads system.txt + style preset, assembles a complete user prompt,
 * and outputs both as JSON. This removes the need for the LLM to
 * manually read prompt files and assemble templates.
 *
 * Usage:
 *   node prep-prompt.mjs \
 *     --style default \
 *     --user-prompt '帮我实现一个需求管理的看板' \
 *     --data-file "<dataFile>" \
 *     --session-id '81d85db3-...' \
 *     --lang en
 *
 * Exit 0 + {"ok":true,"systemPrompt":"...","userPrompt":"..."}
 * Exit 1 + {"ok":false,"errors":["..."]}
 */

import { readFileSync } from 'node:fs';
import { dirname, isAbsolute, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const VALID_STYLES = new Set(['default', 'compact', 'topology', 'code-summary']);
const DEFAULT_SKILL_VERSION = '0.3.0';

// ---------------------------------------------------------------------------
// Arg parsing
// ---------------------------------------------------------------------------

function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i++) {
    const key = argv[i];
    const val = argv[i + 1];
    switch (key) {
      case '--style':
        args.style = val;
        i++;
        break;
      case '--user-prompt':
        args.userPrompt = val;
        i++;
        break;
      case '--data-file':
        args.dataFile = val;
        i++;
        break;
      case '--session-id':
        args.sessionId = val;
        i++;
        break;
      case '--lang':
        args.lang = val;
        i++;
        break;
      default:
        break;
    }
  }
  return args;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

function main() {
  const args = parseArgs(process.argv);
  const errors = [];

  // Validate required params
  const style = args.style || 'default';
  if (!VALID_STYLES.has(style)) {
    errors.push(`Invalid style "${style}". Must be one of: ${[...VALID_STYLES].join(', ')}`);
  }

  const userPrompt = args.userPrompt;
  if (!userPrompt) {
    errors.push('--user-prompt is required');
  }

  const sessionId = args.sessionId || '';
  const lang = args.lang?.trim();

  // Read skill version from SKILL.md metadata
  const skillDir = join(dirname(fileURLToPath(import.meta.url)), '..');
  let skillVersion = DEFAULT_SKILL_VERSION;
  try {
    const skillMd = readFileSync(join(skillDir, 'SKILL.md'), 'utf-8');
    const versionMatch = skillMd.match(/version:\s*'([^']+)'/);
    if (versionMatch) skillVersion = versionMatch[1];
  } catch {
    // fallback to default
  }

  // Parse context data from file (optional)
  let contextData = null;
  if (args.dataFile) {
    if (!isInsidePulseTempDir(args.dataFile)) {
      errors.push('--data-file must be under VERDENT_HOME/tmp/edit-pulse-style');
    } else {
      try {
        const raw = readFileSync(args.dataFile, 'utf-8');
        contextData = JSON.parse(raw);
      } catch (e) {
        errors.push(`--data-file error: ${e.message}`);
      }
    }
  }

  if (errors.length > 0) {
    console.log(JSON.stringify({ ok: false, errors }));
    process.exit(1);
  }

  // Resolve prompt file paths
  const systemPromptPath = join(skillDir, 'prompt', 'system.txt');
  const componentCatalogPath = join(skillDir, 'prompt', 'component-catalog.txt');
  const stylePresetPath = join(skillDir, 'prompt', 'styles', `${style}.txt`);

  // Read system prompt
  let systemPromptContent;
  try {
    systemPromptContent = readFileSync(systemPromptPath, 'utf-8');
  } catch (e) {
    console.log(JSON.stringify({ ok: false, errors: [`Failed to read system.txt: ${e.message}`] }));
    process.exit(1);
  }

  let componentCatalogContent;
  try {
    componentCatalogContent = readFileSync(componentCatalogPath, 'utf-8');
  } catch (e) {
    console.log(JSON.stringify({ ok: false, errors: [`Failed to read component catalog: ${e.message}`] }));
    process.exit(1);
  }

  // Read style preset
  let stylePresetContent;
  try {
    stylePresetContent = readFileSync(stylePresetPath, 'utf-8');
  } catch (e) {
    console.log(JSON.stringify({ ok: false, errors: [`Failed to read styles/${style}.txt: ${e.message}`] }));
    process.exit(1);
  }

  // Combine system prompt + style preset
  const fullSystemPrompt = [
    systemPromptContent.trimEnd(),
    componentCatalogContent.trim(),
    stylePresetContent.trim(),
  ].filter(Boolean).join('\n\n');

  // Format context data section
  let dataSection;
  if (!contextData) {
    dataSection = '(No additional data provided — generate based on user request only)';
  } else {
    dataSection = JSON.stringify(contextData, null, 2);
  }

  // Assemble user prompt
  const generatedAt = new Date().toISOString();
  const assembledUserPrompt = `## User Request
${userPrompt}

${lang ? `Language requirement: All UI copy must use ${lang}

` : ''}## Context Data
${dataSection}

## Parameters
- style: ${style}
- managerSessionId: ${sessionId}
- generatedAt: ${generatedAt}
- skillVersion: "${skillVersion}"`;

  console.log(JSON.stringify({
    ok: true,
    systemPrompt: fullSystemPrompt,
    userPrompt: assembledUserPrompt,
  }));
  process.exit(0);
}

main();

function isInsidePulseTempDir(filePath) {
  if (!process.env.VERDENT_HOME) return false;
  const tempDir = resolve(process.env.VERDENT_HOME, 'tmp', 'edit-pulse-style');
  const resolvedPath = resolve(filePath);
  const rel = relative(tempDir, resolvedPath);
  return rel === '' || (!rel.startsWith('..') && !isAbsolute(rel));
}
