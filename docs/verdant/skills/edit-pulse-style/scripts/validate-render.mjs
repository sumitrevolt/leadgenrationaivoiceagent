#!/usr/bin/env node
/**
 * Taskflow render.json validator.
 *
 * Usage:
 *   node validate-render.mjs <file.json>
 *   cat file.json | node validate-render.mjs
 *
 * Exit 0 + {"valid":true}                    — envelope is valid
 * Exit 1 + {"valid":false,"errors":[...]}    — envelope is invalid
 */

import { readFileSync } from 'node:fs';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ALLOWED_TYPES = new Set([
  'Board',
  'Column',
  'Row',
  'Card',
  'Badge',
  'Tag',
  'TagList',
  'ActionBar',
  'Text',
  'List',
  'EmptyState',
  'Topology',
  'DataTable',
  'BarChart',
  'DonutChart',
  'ProgressBar',
  'TabGroup',
  'TabPanel',
  'StatCard',
  'Timeline',
  'Callout',
  'Accordion',
  'Divider',
  'CodeBlock',
  'LineChart',
  'StackedBar',
  'KeyValue',
  'Gauge',
  'Iframe',
  'Image',
  'Link',
]);

const LEAF_TYPES = new Set([
  'Badge',
  'Tag',
  'TagList',
  'ActionBar',
  'Text',
  'List',
  'EmptyState',
  'DataTable',
  'BarChart',
  'DonutChart',
  'ProgressBar',
  'StatCard',
  'Timeline',
  'Callout',
  'Accordion',
  'Divider',
  'CodeBlock',
  'LineChart',
  'StackedBar',
  'KeyValue',
  'Gauge',
  'Iframe',
  'Image',
  'Link',
]);

const VALID_LAYOUTS = new Set(['masonry', 'column', 'list']);
const VALID_STATUSES = new Set(['todo', 'in_progress', 'done']);
const VALID_ROW_ALIGN = new Set(['start', 'center', 'end', 'stretch']);
const VALID_ROW_JUSTIFY = new Set(['start', 'center', 'end', 'between', 'around']);
const VALID_ACTION_TYPES = new Set(['view', 'execute', 'navigate', 'prompt']);
const VALID_BUTTON_VARIANTS = new Set(['primary', 'secondary', 'ghost', 'danger']);
const VALID_PREVIEW_TASK_SCRIPT_TYPES = new Set([
  'navigate_project',
  'navigate_session',
  'browser',
  'brower',
]);
const CANONICAL_PREVIEW_TASK_SCRIPT_TYPES = ['navigate_project', 'navigate_session', 'browser'];
const ALLOWED_BASH_EXECUTABLES = new Set([
  'verdent-manager',
  'git',
  'awk',
  'cat',
  'cut',
  'head',
  'tail',
  'ls',
  'wc',
  'grep',
  'find',
  'date',
  'echo',
  'pwd',
  'jq',
  'sed',
  'sort',
  'which',
  'stat',
  'uniq',
  'xargs',
]);
const READ_ONLY_GIT_SUBCOMMANDS = new Set([
  'status',
  'log',
  'diff',
  'branch',
  'show',
  'rev-parse',
  'tag',
  'describe',
  'shortlog',
  'ls-files',
  'ls-tree',
  'cat-file',
  'name-rev',
  'for-each-ref',
  'remote',
  'config',
  'blame',
  'reflog',
]);
const FORBIDDEN_COMMAND_PATTERNS = [
  { pattern: /\$\([^)]*\)/, label: 'subshell' },
  { pattern: /`/, label: 'backticks' },
  { pattern: /<\(|>\(/, label: 'process substitution' },
  { pattern: /<</, label: 'here document' },
  { pattern: /(^|[^\w./-])&\s*$/, label: 'background execution' },
];
const VALID_ICONS = new Set(['task', 'search', 'filter']);
const VALID_BADGE_VARIANTS = new Set(['info', 'success', 'warning', 'error', 'neutral']);
const VALID_TEXT_VARIANTS = new Set(['heading', 'body', 'caption', 'code']);
const VALID_CHART_COLORS = new Set(['info', 'success', 'warning', 'error', 'neutral']);
const VALID_TABLE_ALIGNS = new Set(['left', 'center', 'right']);
const SEMVERISH_VERSION_RE = /^\d+(\.\d+(\.\d+)?)?$/;
const VALID_IMAGE_OBJECT_FIT = new Set(['cover', 'contain']);
const VALID_CARD_PADDING = new Set(['none', 'sm', 'md', 'lg']);
const VALID_CARD_GAPS = new Set(['none', 'sm', 'md', 'lg']);
const VALID_BUTTON_SIZES = new Set(['sm', 'md']);

function isValidChartColor(color) {
  return VALID_CHART_COLORS.has(color) || /^#[0-9a-fA-F]{6}$/.test(color);
}
const VALID_RICH_CELL_VARIANTS = new Set(['success', 'warning', 'error', 'info', 'muted']);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function isNonEmptyString(v) {
  return typeof v === 'string' && v.length > 0;
}

function isExpressionObject(value) {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
  return '$item' in value || '$state' in value || '$index' in value
    || '$bindState' in value || '$bindItem' in value
    || '$cond' in value || '$computed' in value || '$template' in value;
}

function isObject(v) {
  return v !== null && typeof v === 'object' && !Array.isArray(v);
}

function isArrayOfStrings(v) {
  return Array.isArray(v) && v.every(item => typeof item === 'string');
}

function isValidRepeatItems(v) {
  return Array.isArray(v);
}

function isValidStatePath(v) {
  return typeof v === 'string' && /^(?:\$item\.)?[A-Za-z0-9_.[\]-]+$/.test(v);
}

function validatePreviewTaskScript(script, path, errors) {
  if (!isObject(script)) {
    errors.push(`${path} must be an object`);
    return;
  }
  if (!isExpressionObject(script.type) && !isNonEmptyString(script.type)) {
    errors.push(`${path}.type must be a non-empty string`);
  } else if (!isExpressionObject(script.type) && !VALID_PREVIEW_TASK_SCRIPT_TYPES.has(script.type)) {
    errors.push(`${path}.type must be one of: ${CANONICAL_PREVIEW_TASK_SCRIPT_TYPES.join(', ')} (legacy "brower" also accepted)`);
  }
  if (!isExpressionObject(script.description) && !isNonEmptyString(script.description)) {
    errors.push(`${path}.description must be a non-empty string`);
  }
  if (!isNonEmptyString(script.type)) {
    return;
  }
  if (script.type === 'navigate_project' && !isExpressionObject(script.projectName) && !isNonEmptyString(script.projectName)) {
    errors.push(`${path}.projectName must be a non-empty string for navigate_project`);
  }
  if (
    script.type === 'navigate_session' &&
    !isExpressionObject(script.sessionId) &&
    !isNonEmptyString(script.sessionId)
  ) {
    errors.push(`${path}.sessionId must be a non-empty string for ${script.type}`);
  }
  if ((script.type === 'browser' || script.type === 'brower') && !isExpressionObject(script.url) && !isNonEmptyString(script.url)) {
    errors.push(`${path}.url must be a non-empty string for ${script.type}`);
  }
}

function splitPipeline(command) {
  const segments = [];
  let current = '';
  let quote = null;
  for (let i = 0; i < command.length; i++) {
    const char = command[i];
    const prev = command[i - 1];
    if ((char === '"' || char === "'") && prev !== '\\') {
      if (quote === char) {
        quote = null;
      } else if (!quote) {
        quote = char;
      }
      current += char;
      continue;
    }
    if (char === '|' && !quote) {
      if (command[i + 1] === '|') {
        current += '||';
        i++;
        continue;
      }
      segments.push(current.trim());
      current = '';
      continue;
    }
    current += char;
  }
  if (current.trim()) {
    segments.push(current.trim());
  }
  return segments;
}

function tokenizeCommand(command) {
  const tokens = [];
  let current = '';
  let quote = null;
  for (let i = 0; i < command.length; i++) {
    const char = command[i];
    const prev = command[i - 1];
    if ((char === '"' || char === "'") && prev !== '\\') {
      if (quote === char) {
        quote = null;
      } else if (!quote) {
        quote = char;
      }
      continue;
    }
    if (!quote && /\s/.test(char)) {
      if (current) {
        tokens.push(current);
        current = '';
      }
      continue;
    }
    current += char;
  }
  if (current) {
    tokens.push(current);
  }
  return tokens;
}

function hasUnquotedOutputRedirect(command) {
  let quote = null;
  for (let i = 0; i < command.length; i++) {
    const char = command[i];
    const prev = command[i - 1];
    if ((char === '"' || char === "'") && prev !== '\\') {
      if (quote === char) {
        quote = null;
      } else if (!quote) {
        quote = char;
      }
      continue;
    }
    if (quote) {
      continue;
    }
    if (char === '>') {
      return true;
    }
  }
  return false;
}

function validateCommandPathTokens(tokens, path, errors) {
  for (const token of tokens) {
    if (token === '--') {
      continue;
    }
    if (token.includes('../') || token === '..') {
      errors.push(`${path}: path traversal outside allowed directories is not allowed`);
      return;
    }
  }
}

function validateBashCommand(command, path, errors) {
  if (!isNonEmptyString(command)) {
    errors.push(`${path} must be a non-empty string`);
    return;
  }

  if (hasUnquotedOutputRedirect(command)) {
    errors.push(`${path}: forbidden output redirect`);
  }

  for (const rule of FORBIDDEN_COMMAND_PATTERNS) {
    if (rule.pattern.test(command)) {
      errors.push(`${path}: forbidden ${rule.label}`);
    }
  }

  const pipeline = splitPipeline(command);
  if (pipeline.length === 0) {
    errors.push(`${path}: command must contain at least one executable`);
    return;
  }

  for (let i = 0; i < pipeline.length; i++) {
    const segment = pipeline[i];
    const tokens = tokenizeCommand(segment);
    if (tokens.length === 0) {
      errors.push(`${path}: pipeline segment ${i} is empty`);
      continue;
    }
    const executable = tokens[0];
    if (!ALLOWED_BASH_EXECUTABLES.has(executable)) {
      errors.push(`${path}: executable "${executable}" is not in the allowlist`);
      continue;
    }

    validateCommandPathTokens(tokens.slice(1), path, errors);

    if (executable === 'find') {
      const forbiddenFindFlag = tokens.find(token => ['-exec', '-execdir', '-delete', '-ok'].includes(token));
      if (forbiddenFindFlag) {
        errors.push(`${path}: find flag "${forbiddenFindFlag}" is not allowed`);
      }
    }

    if (executable === 'git') {
      const subcommand = tokens.slice(1).find(token => !token.startsWith('-'));
      if (!subcommand || !READ_ONLY_GIT_SUBCOMMANDS.has(subcommand)) {
        errors.push(`${path}: git subcommand must be read-only`);
      }
    }
  }
}

function validateSubscription(sub, index, errors) {
  const path = `subscriptions[${index}]`;
  const validSubTypes = new Set(['bash-once', 'file-watch', 'file-hash', 'ipc-event']);
  if (!isNonEmptyString(sub.type) || !validSubTypes.has(sub.type)) {
    errors.push(`${path}: type must be one of ${[...validSubTypes].join(', ')}`);
  }
  if (!isObject(sub.config)) {
    errors.push(`${path}: config must be an object`);
    return;
  }
  if (!isObject(sub.action) || sub.action.type !== 'llm-update') {
    errors.push(`${path}: action.type must be "llm-update"`);
  }

  if (sub.type === 'bash-once') {
    validateBashCommand(sub.config.command, `${path}.config.command`, errors);
    if (sub.config.cwd !== undefined && !isNonEmptyString(sub.config.cwd)) {
      errors.push(`${path}.config.cwd must be a non-empty string when provided`);
    }
    validateCommandPathTokens([sub.config.cwd].filter(Boolean), `${path}.config.cwd`, errors);
  }

  if (sub.type === 'file-watch' || sub.type === 'file-hash') {
    if (!Array.isArray(sub.config.paths) || sub.config.paths.length === 0 || !isArrayOfStrings(sub.config.paths)) {
      errors.push(`${path}.config.paths must be a non-empty string array`);
    } else {
      validateCommandPathTokens(sub.config.paths, `${path}.config.paths`, errors);
    }
  }

  if (sub.type === 'ipc-event') {
    if (!Array.isArray(sub.config.events) || sub.config.events.length === 0 || !isArrayOfStrings(sub.config.events)) {
      errors.push(`${path}.config.events must be a non-empty string array`);
    }
  }
}

// ---------------------------------------------------------------------------
// Per-component props validators
// ---------------------------------------------------------------------------

function validateBoardProps(props, id, errors) {
  if (!isExpressionObject(props.title) && !isNonEmptyString(props.title)) {
    errors.push(`${id}: Board.title must be a non-empty string`);
  }
  if (props.layout !== undefined && !isExpressionObject(props.layout) && !VALID_LAYOUTS.has(props.layout)) {
    errors.push(`${id}: Board.layout must be one of: masonry, column, list`);
  }
}

function validateColumnProps(props, id, errors) {
  if (props.title !== undefined && !isNonEmptyString(props.title)) {
    errors.push(`${id}: Column.title must be a non-empty string when provided`);
  }
}

function validateRowProps(props, id, errors) {
  if (props.gap !== undefined && !isExpressionObject(props.gap) && typeof props.gap !== 'number') {
    errors.push(`${id}: Row.gap must be a number`);
  }
  if (props.align !== undefined && !isExpressionObject(props.align) && !VALID_ROW_ALIGN.has(props.align)) {
    errors.push(`${id}: Row.align must be one of: start, center, end, stretch`);
  }
  if (props.justify !== undefined && !isExpressionObject(props.justify) && !VALID_ROW_JUSTIFY.has(props.justify)) {
    errors.push(`${id}: Row.justify must be one of: start, center, end, between, around`);
  }
  if (props.widths !== undefined && !isExpressionObject(props.widths)) {
    if (!Array.isArray(props.widths)) {
      errors.push(`${id}: Row.widths must be a string array`);
    } else if (props.widths.some(width => typeof width !== 'string')) {
      errors.push(`${id}: Row.widths must contain only strings`);
    }
  }
  if (props.wrap !== undefined && !isExpressionObject(props.wrap) && typeof props.wrap !== 'boolean') {
    errors.push(`${id}: Row.wrap must be boolean`);
  }
}

function validateCardProps(props, id, errors) {
  if (props.id !== undefined && !isNonEmptyString(props.id)) {
    errors.push(`${id}: Card.id must be a non-empty string when provided`);
  }
  if (props.title !== undefined && !isExpressionObject(props.title) && !isNonEmptyString(props.title)) {
    errors.push(`${id}: Card.title must be a non-empty string when provided`);
  }
  if (props.status !== undefined && !isExpressionObject(props.status) && !VALID_STATUSES.has(props.status)) {
    errors.push(`${id}: Card.status must be one of: todo, in_progress, done`);
  }
  if (props.subtitle !== undefined && !isExpressionObject(props.subtitle) && typeof props.subtitle !== 'string') {
    errors.push(`${id}: Card.subtitle must be a string`);
  }
  if (props.dependsOn !== undefined) {
    errors.push(`${id}: Card.dependsOn is deprecated; use Topology.props.edges instead`);
  }
  if (props.icon !== undefined && !isExpressionObject(props.icon) && typeof props.icon !== 'string') {
    errors.push(`${id}: Card.icon must be a string`);
  }
  if (
    props.footer !== undefined &&
    !isExpressionObject(props.footer) &&
    typeof props.footer !== 'string' &&
    !Array.isArray(props.footer)
  ) {
    errors.push(`${id}: Card.footer must be a string or children array`);
  }
  if (props.headerExtra !== undefined && !isExpressionObject(props.headerExtra) && !Array.isArray(props.headerExtra)) {
    errors.push(`${id}: Card.headerExtra must be a children array`);
  }
  if (props.gap !== undefined && !isExpressionObject(props.gap) && !VALID_CARD_GAPS.has(props.gap)) {
    errors.push(`${id}: Card.gap must be one of: none, sm, md, lg`);
  }
  if (props.padding !== undefined && !isExpressionObject(props.padding) && !VALID_CARD_PADDING.has(props.padding)) {
    errors.push(`${id}: Card.padding must be one of: none, sm, md, lg`);
  }
}

function validateBadgeProps(props, id, errors) {
  if (!isExpressionObject(props.label) && !isNonEmptyString(props.label)) {
    errors.push(`${id}: Badge.label must be a non-empty string`);
  }
  if (props.variant !== undefined && !isExpressionObject(props.variant) && !VALID_BADGE_VARIANTS.has(props.variant)) {
    errors.push(`${id}: Badge.variant must be one of: info, success, warning, error, neutral`);
  }
}

function validateTagProps(props, id, errors) {
  if (!isExpressionObject(props.label) && !isNonEmptyString(props.label)) {
    errors.push(`${id}: Tag.label must be a non-empty string`);
  }
  if (props.script !== undefined) {
    validatePreviewTaskScript(props.script, `${id}: Tag.script`, errors);
  }
  if (props.description !== undefined && typeof props.description !== 'string') {
    errors.push(`${id}: Tag.description must be a string`);
  }
}

function validateTagListProps(props, id, errors) {
  if (isExpressionObject(props.tags)) {
    return;
  }
  if (!Array.isArray(props.tags)) {
    errors.push(`${id}: TagList.tags must be an array`);
    return;
  }

  for (let i = 0; i < props.tags.length; i++) {
    const tag = props.tags[i];
    if (typeof tag === 'string') {
      continue;
    }
    if (!isObject(tag)) {
      errors.push(`${id}: TagList.tags[${i}] must be a string or object`);
      continue;
    }
    if (!isExpressionObject(tag.key) && !isNonEmptyString(tag.key)) {
      errors.push(`${id}: TagList.tags[${i}].key must be a non-empty string`);
    }
    if (!isExpressionObject(tag.label) && !isNonEmptyString(tag.label)) {
      errors.push(`${id}: TagList.tags[${i}].label must be a non-empty string`);
    }
    if (tag.script !== undefined) {
      validatePreviewTaskScript(tag.script, `${id}: TagList.tags[${i}].script`, errors);
    }
  }
}

function validateButtonProps(props, id, errors) {
  if (!isExpressionObject(props.label) && !isNonEmptyString(props.label)) {
    errors.push(`${id}: Button.label must be a non-empty string`);
  }
  if (props.metadata !== undefined) {
    validatePreviewTaskScript(props.metadata, `${id}: Button.metadata`, errors);
  }
  if (props.disabled !== undefined && !isExpressionObject(props.disabled) && typeof props.disabled !== 'boolean') {
    errors.push(`${id}: Button.disabled must be boolean`);
  }
  if (props.variant !== undefined && !isExpressionObject(props.variant) && !VALID_BUTTON_VARIANTS.has(props.variant)) {
    errors.push(`${id}: Button.variant must be one of: primary, secondary, ghost, danger`);
  }
  if (props.size !== undefined && !isExpressionObject(props.size) && !VALID_BUTTON_SIZES.has(props.size)) {
    errors.push(`${id}: Button.size must be one of: sm, md`);
  }
}

function validateActionBarProps(props, id, errors) {
  if (!Array.isArray(props.actions)) {
    errors.push(`${id}: ActionBar.actions must be an array`);
    return;
  }

  for (let i = 0; i < props.actions.length; i++) {
    const action = props.actions[i];
    if (!isObject(action)) {
      errors.push(`${id}: ActionBar.actions[${i}] must be an object`);
      continue;
    }
    if (!isExpressionObject(action.label) && !isNonEmptyString(action.label)) {
      errors.push(`${id}: ActionBar.actions[${i}].label must be a non-empty string`);
    }
    if (
      action.actionType !== undefined &&
      !isExpressionObject(action.actionType) &&
      !VALID_ACTION_TYPES.has(action.actionType)
    ) {
      errors.push(`${id}: ActionBar.actions[${i}].actionType "${action.actionType}" is not valid`);
    }
    if (action.metadata !== undefined) {
      validatePreviewTaskScript(
        action.metadata,
        `${id}: ActionBar.actions[${i}].metadata`,
        errors
      );
    }
    if (action.disabled !== undefined && !isExpressionObject(action.disabled) && typeof action.disabled !== "boolean") {
      errors.push(`${id}: ActionBar.actions[${i}].disabled must be a boolean`);
    }
  }
}

function validateTextProps(props, id, errors) {
  if (!isExpressionObject(props.content) && !isNonEmptyString(props.content)) {
    errors.push(`${id}: Text.content must be a non-empty string`);
  }
  if (props.variant !== undefined && !isExpressionObject(props.variant) && !VALID_TEXT_VARIANTS.has(props.variant)) {
    errors.push(`${id}: Text.variant must be one of: heading, body, caption, code`);
  }
  if (props.level !== undefined) {
    if (typeof props.level !== 'number' || ![2, 3, 4, 5].includes(props.level)) {
      errors.push(`${id}: Text.level must be one of: 2, 3, 4, 5`);
    }
    if (props.variant !== 'heading') {
      errors.push(`${id}: Text.level is only valid when variant is "heading"`);
    }
  }
  if (props.size !== undefined && !isExpressionObject(props.size) && !new Set(['lg', 'md', 'sm', 'xs']).has(props.size)) {
    errors.push(`${id}: Text.size must be one of: lg, md, sm, xs`);
  }
  if (props.weight !== undefined && !isExpressionObject(props.weight) && !new Set(['bold', 'semibold', 'medium']).has(props.weight)) {
    errors.push(`${id}: Text.weight must be one of: bold, semibold, medium`);
  }
  if (props.divider !== undefined && typeof props.divider !== 'boolean') {
    errors.push(`${id}: Text.divider must be boolean`);
  }
}

function validateListProps(props, id, errors) {
  if (!Array.isArray(props.items)) {
    errors.push(`${id}: List.items must be an array`);
    return;
  }
  for (let i = 0; i < props.items.length; i++) {
    const item = props.items[i];
    if (!isObject(item)) {
      errors.push(`${id}: List.items[${i}] must be an object`);
      continue;
    }
    if (!isExpressionObject(item.label) && !isNonEmptyString(item.label)) {
      errors.push(`${id}: List.items[${i}].label must be a non-empty string`);
    }
    if (item.description !== undefined && typeof item.description !== 'string') {
      errors.push(`${id}: List.items[${i}].description must be a string`);
    }
    if (item.status !== undefined && !isExpressionObject(item.status) && !VALID_STATUSES.has(item.status)) {
      errors.push(`${id}: List.items[${i}].status must be one of: todo, in_progress, done`);
    }
  }
}

function validateEmptyStateProps(props, id, errors) {
  if (props.message !== undefined && typeof props.message !== 'string') {
    errors.push(`${id}: EmptyState.message must be a string`);
  }
  if (props.icon !== undefined && !VALID_ICONS.has(props.icon)) {
    errors.push(`${id}: EmptyState.icon must be one of: task, search, filter`);
  }
}

function validateTopologyProps(props, id, errors) {
  if (props.visible !== undefined && typeof props.visible !== 'boolean') {
    errors.push(`${id}: Topology.visible must be boolean`);
  }
  if (props.nodeWidth !== undefined && (typeof props.nodeWidth !== 'number' || props.nodeWidth <= 0)) {
    errors.push(`${id}: Topology.nodeWidth must be a positive number`);
  }
  if (props.items !== undefined) {
    errors.push(`${id}: Topology.items is runtime-provided and must not be generated`);
  }
  if (props.nodes !== undefined) {
    errors.push(`${id}: Topology.nodes must not be generated`);
  }
  if (props.edges !== undefined) {
    if (!Array.isArray(props.edges)) {
      errors.push(`${id}: Topology.edges must be an array`);
    } else {
      for (let i = 0; i < props.edges.length; i++) {
        const edge = props.edges[i];
        if (!isObject(edge)) {
          errors.push(`${id}: Topology.edges[${i}] must be an object`);
          continue;
        }
        if (!isNonEmptyString(edge.id)) {
          errors.push(`${id}: Topology.edges[${i}].id must be a non-empty string`);
        }
        if (!isNonEmptyString(edge.source)) {
          errors.push(`${id}: Topology.edges[${i}].source must be a non-empty string`);
        }
        if (!isNonEmptyString(edge.target)) {
          errors.push(`${id}: Topology.edges[${i}].target must be a non-empty string`);
        }
        if (edge.label !== undefined && typeof edge.label !== 'string') {
          errors.push(`${id}: Topology.edges[${i}].label must be a string`);
        }
        if (
          edge.variant !== undefined &&
          edge.variant !== 'default' &&
          edge.variant !== 'dashed' &&
          edge.variant !== 'bold'
        ) {
          errors.push(`${id}: Topology.edges[${i}].variant must be one of: default, dashed, bold`);
        }
        if (edge.animated !== undefined && typeof edge.animated !== 'boolean') {
          errors.push(`${id}: Topology.edges[${i}].animated must be boolean`);
        }
      }
    }
  }
}

function validateDataTableProps(props, id, errors) {
  if (!Array.isArray(props.columns)) {
    errors.push(`${id}: DataTable.columns must be an array`);
    return;
  }
  for (let i = 0; i < props.columns.length; i++) {
    const col = props.columns[i];
    if (!isObject(col)) {
      errors.push(`${id}: DataTable.columns[${i}] must be an object`);
      continue;
    }
    if (!isExpressionObject(col.key) && !isNonEmptyString(col.key)) {
      errors.push(`${id}: DataTable.columns[${i}].key must be a non-empty string`);
    }
    if (!isExpressionObject(col.label) && !isNonEmptyString(col.label)) {
      errors.push(`${id}: DataTable.columns[${i}].label must be a non-empty string`);
    }
    if (col.align !== undefined && !isExpressionObject(col.align) && !VALID_TABLE_ALIGNS.has(col.align)) {
      errors.push(`${id}: DataTable.columns[${i}].align must be one of: left, center, right`);
    }
  }
  if (!Array.isArray(props.rows)) {
    errors.push(`${id}: DataTable.rows must be an array`);
  } else {
    for (let i = 0; i < props.rows.length; i++) {
      const row = props.rows[i];
      if (!isObject(row)) {
        errors.push(`${id}: DataTable.rows[${i}] must be an object`);
        continue;
      }
      for (const [cellKey, cellValue] of Object.entries(row)) {
        const isPrimitiveCell =
          typeof cellValue === 'string' || typeof cellValue === 'number';
        if (isPrimitiveCell) {
          continue;
        }
        if (!isObject(cellValue)) {
          errors.push(`${id}: DataTable.rows[${i}].${cellKey} must be a string, number, or rich cell object`);
          continue;
        }
        if (!isExpressionObject(cellValue.text) && !isNonEmptyString(cellValue.text)) {
          errors.push(`${id}: DataTable.rows[${i}].${cellKey}.text must be a non-empty string`);
        }
        if (
          cellValue.variant !== undefined &&
          !isExpressionObject(cellValue.variant) &&
          !VALID_RICH_CELL_VARIANTS.has(cellValue.variant)
        ) {
          errors.push(`${id}: DataTable.rows[${i}].${cellKey}.variant must be one of: success, warning, error, info, muted`);
        }
      }
    }
  }
  if (props.caption !== undefined && typeof props.caption !== 'string') {
    errors.push(`${id}: DataTable.caption must be a string`);
  }
  if (props.compact !== undefined && typeof props.compact !== 'boolean') {
    errors.push(`${id}: DataTable.compact must be boolean`);
  }
  if (props.columnWidth !== undefined) {
    if (!isObject(props.columnWidth)) {
      errors.push(`${id}: DataTable.columnWidth must be an object mapping column keys to width strings`);
    } else if (Object.values(props.columnWidth).some(width => typeof width !== 'string')) {
      errors.push(`${id}: DataTable.columnWidth values must be strings`);
    }
  }
  if (props.emptyMessage !== undefined && typeof props.emptyMessage !== 'string') {
    errors.push(`${id}: DataTable.emptyMessage must be a string`);
  }
}

function validateBarChartProps(props, id, errors) {
  if (!Array.isArray(props.items)) {
    errors.push(`${id}: BarChart.items must be an array`);
    return;
  }
  for (let i = 0; i < props.items.length; i++) {
    const item = props.items[i];
    if (!isObject(item)) {
      errors.push(`${id}: BarChart.items[${i}] must be an object`);
      continue;
    }
    if (!isExpressionObject(item.label) && !isNonEmptyString(item.label)) {
      errors.push(`${id}: BarChart.items[${i}].label must be a non-empty string`);
    }
    if (typeof item.value !== 'number') {
      errors.push(`${id}: BarChart.items[${i}].value must be a number`);
    }
    if (item.color !== undefined && !isExpressionObject(item.color) && !isValidChartColor(item.color)) {
      errors.push(`${id}: BarChart.items[${i}].color must be one of: info, success, warning, error, neutral, or a #RRGGBB color`);
    }
  }
  if (props.title !== undefined && typeof props.title !== 'string') {
    errors.push(`${id}: BarChart.title must be a string`);
  }
  if (props.maxValue !== undefined && typeof props.maxValue !== 'number') {
    errors.push(`${id}: BarChart.maxValue must be a number`);
  }
  if (props.showValues !== undefined && typeof props.showValues !== 'boolean') {
    errors.push(`${id}: BarChart.showValues must be boolean`);
  }
}

function validateDonutChartProps(props, id, errors) {
  if (!Array.isArray(props.segments)) {
    errors.push(`${id}: DonutChart.segments must be an array`);
    return;
  }
  for (let i = 0; i < props.segments.length; i++) {
    const seg = props.segments[i];
    if (!isObject(seg)) {
      errors.push(`${id}: DonutChart.segments[${i}] must be an object`);
      continue;
    }
    if (!isExpressionObject(seg.label) && !isNonEmptyString(seg.label)) {
      errors.push(`${id}: DonutChart.segments[${i}].label must be a non-empty string`);
    }
    if (typeof seg.value !== 'number') {
      errors.push(`${id}: DonutChart.segments[${i}].value must be a number`);
    }
    if (seg.color !== undefined && !isExpressionObject(seg.color) && !isValidChartColor(seg.color)) {
      errors.push(`${id}: DonutChart.segments[${i}].color must be one of: info, success, warning, error, neutral, or a #RRGGBB color`);
    }
  }
  if (props.title !== undefined && typeof props.title !== 'string') {
    errors.push(`${id}: DonutChart.title must be a string`);
  }
  if (props.size !== undefined && typeof props.size !== 'number') {
    errors.push(`${id}: DonutChart.size must be a number`);
  }
  if (props.showLegend !== undefined && typeof props.showLegend !== 'boolean') {
    errors.push(`${id}: DonutChart.showLegend must be boolean`);
  }
}

function validateTabGroupProps(props, id, errors) {
  if (props.defaultIndex !== undefined && typeof props.defaultIndex !== 'number') {
    errors.push(`${id}: TabGroup.defaultIndex must be a number`);
  }
}

function validateTabPanelProps(props, id, errors) {
  if (!isExpressionObject(props.label) && !isNonEmptyString(props.label)) {
    errors.push(`${id}: TabPanel.label must be a non-empty string`);
  }
}

function validateProgressBarProps(props, id, errors) {
  if (typeof props.value !== 'number') {
    errors.push(`${id}: ProgressBar.value must be a number`);
  }
  if (props.max !== undefined && typeof props.max !== 'number') {
    errors.push(`${id}: ProgressBar.max must be a number`);
  }
  if (typeof props.value === 'number' && typeof (props.max ?? 100) === 'number') {
    const max = props.max ?? 100;
    if (props.value > max) {
      errors.push(`${id}: ProgressBar.value (${props.value}) must not exceed max (${max})`);
    }
    if (props.value < 0) {
      errors.push(`${id}: ProgressBar.value (${props.value}) must not be negative`);
    }
  }
  if (props.label !== undefined && typeof props.label !== 'string') {
    errors.push(`${id}: ProgressBar.label must be a string`);
  }
  if (
    props.color !== undefined &&
    !isExpressionObject(props.color) &&
    !new Set(['info', 'success', 'warning', 'error']).has(props.color)
  ) {
    errors.push(`${id}: ProgressBar.color must be one of: info, success, warning, error`);
  }
  if (props.showValue !== undefined && typeof props.showValue !== 'boolean') {
    errors.push(`${id}: ProgressBar.showValue must be boolean`);
  }
}

function validateStatCardProps(props, id, errors) {
  if (!isExpressionObject(props.label) && !isNonEmptyString(props.label)) {
    errors.push(`${id}: StatCard.label must be a non-empty string`);
  }
  if (props.value === undefined || (typeof props.value !== 'string' && typeof props.value !== 'number')) {
    errors.push(`${id}: StatCard.value must be a string or number`);
  }
  if (props.trend !== undefined && !isExpressionObject(props.trend) && !new Set(['up', 'down', 'flat']).has(props.trend)) {
    errors.push(`${id}: StatCard.trend must be one of: up, down, flat`);
  }
  if (props.trendLabel !== undefined && typeof props.trendLabel !== 'string') {
    errors.push(`${id}: StatCard.trendLabel must be a string`);
  }
  if (props.icon !== undefined && typeof props.icon !== 'string') {
    errors.push(`${id}: StatCard.icon must be a string`);
  }
}

function validateTimelineProps(props, id, errors) {
  if (!Array.isArray(props.events)) {
    errors.push(`${id}: Timeline.events must be an array`);
    return;
  }
  for (let i = 0; i < props.events.length; i++) {
    const event = props.events[i];
    if (!isObject(event)) {
      errors.push(`${id}: Timeline.events[${i}] must be an object`);
      continue;
    }
    if (!isExpressionObject(event.title) && !isNonEmptyString(event.title)) {
      errors.push(`${id}: Timeline.events[${i}].title must be a non-empty string`);
    }
    if (event.description !== undefined && typeof event.description !== 'string') {
      errors.push(`${id}: Timeline.events[${i}].description must be a string`);
    }
    if (event.timestamp !== undefined && typeof event.timestamp !== 'string') {
      errors.push(`${id}: Timeline.events[${i}].timestamp must be a string`);
    }
    if (event.status !== undefined && !isExpressionObject(event.status) && !VALID_STATUSES.has(event.status)) {
      errors.push(`${id}: Timeline.events[${i}].status must be one of: todo, in_progress, done`);
    }
  }
}

function validateCalloutProps(props, id, errors) {
  if (!isExpressionObject(props.content) && !isNonEmptyString(props.content)) {
    errors.push(`${id}: Callout.content must be a non-empty string`);
  }
  const VALID_CALLOUT_VARIANTS = new Set(['info', 'warning', 'error', 'success']);
  if (props.variant !== undefined && !isExpressionObject(props.variant) && !VALID_CALLOUT_VARIANTS.has(props.variant)) {
    errors.push(`${id}: Callout.variant must be one of: info, warning, error, success`);
  }
  if (props.title !== undefined && typeof props.title !== 'string') {
    errors.push(`${id}: Callout.title must be a string`);
  }
}

function validateAccordionProps(props, id, errors) {
  if (!Array.isArray(props.items)) {
    errors.push(`${id}: Accordion.items must be an array`);
    return;
  }
  for (let i = 0; i < props.items.length; i++) {
    const item = props.items[i];
    if (!isObject(item)) {
      errors.push(`${id}: Accordion.items[${i}] must be an object`);
      continue;
    }
    if (!isExpressionObject(item.title) && !isNonEmptyString(item.title)) {
      errors.push(`${id}: Accordion.items[${i}].title must be a non-empty string`);
    }
    if (!isExpressionObject(item.content) && !isNonEmptyString(item.content)) {
      errors.push(`${id}: Accordion.items[${i}].content must be a non-empty string`);
    }
  }
  if (props.defaultOpen !== undefined && typeof props.defaultOpen !== 'number') {
    errors.push(`${id}: Accordion.defaultOpen must be a number`);
  }
}

function validateDividerProps(props, id, errors) {
  if (props.label !== undefined && typeof props.label !== 'string') {
    errors.push(`${id}: Divider.label must be a string`);
  }
}

function validateCodeBlockProps(props, id, errors) {
  if (!isExpressionObject(props.code) && !isNonEmptyString(props.code)) {
    errors.push(`${id}: CodeBlock.code must be a non-empty string`);
  }
  if (props.language !== undefined && typeof props.language !== 'string') {
    errors.push(`${id}: CodeBlock.language must be a string`);
  }
  if (props.title !== undefined && typeof props.title !== 'string') {
    errors.push(`${id}: CodeBlock.title must be a string`);
  }
}

function validateLineChartProps(props, id, errors) {
  if (!Array.isArray(props.series)) {
    errors.push(`${id}: LineChart.series must be an array`);
    return;
  }
  if (!Array.isArray(props.labels)) {
    errors.push(`${id}: LineChart.labels must be an array`);
    return;
  }
  for (let i = 0; i < props.series.length; i++) {
    const s = props.series[i];
    if (!isObject(s)) {
      errors.push(`${id}: LineChart.series[${i}] must be an object`);
      continue;
    }
    if (!isExpressionObject(s.label) && !isNonEmptyString(s.label)) {
      errors.push(`${id}: LineChart.series[${i}].label must be a non-empty string`);
    }
    if (!Array.isArray(s.data)) {
      errors.push(`${id}: LineChart.series[${i}].data must be a number array`);
    } else {
      if (s.data.length !== props.labels.length) {
        errors.push(`${id}: LineChart.series[${i}].data.length must equal labels.length`);
      }
      if (s.data.some(v => typeof v !== 'number')) {
        errors.push(`${id}: LineChart.series[${i}].data must contain only numbers`);
      }
    }
    if (s.color !== undefined && !isExpressionObject(s.color) && !isValidChartColor(s.color)) {
      errors.push(`${id}: LineChart.series[${i}].color must be one of: info, success, warning, error, neutral, or a #RRGGBB color`);
    }
  }
  if (props.title !== undefined && typeof props.title !== 'string') {
    errors.push(`${id}: LineChart.title must be a string`);
  }
  if (props.showDots !== undefined && typeof props.showDots !== 'boolean') {
    errors.push(`${id}: LineChart.showDots must be boolean`);
  }
  if (props.height !== undefined && typeof props.height !== 'number') {
    errors.push(`${id}: LineChart.height must be a number`);
  }
}

function validateStackedBarProps(props, id, errors) {
  if (!Array.isArray(props.categories)) {
    errors.push(`${id}: StackedBar.categories must be an array`);
    return;
  }
  if (!Array.isArray(props.series)) {
    errors.push(`${id}: StackedBar.series must be an array`);
    return;
  }
  for (let i = 0; i < props.series.length; i++) {
    const s = props.series[i];
    if (!isObject(s)) {
      errors.push(`${id}: StackedBar.series[${i}] must be an object`);
      continue;
    }
    if (!isExpressionObject(s.label) && !isNonEmptyString(s.label)) {
      errors.push(`${id}: StackedBar.series[${i}].label must be a non-empty string`);
    }
    if (!Array.isArray(s.values)) {
      errors.push(`${id}: StackedBar.series[${i}].values must be a number array`);
    } else {
      if (s.values.length !== props.categories.length) {
        errors.push(`${id}: StackedBar.series[${i}].values.length must equal categories.length`);
      }
      if (s.values.some(v => typeof v !== 'number')) {
        errors.push(`${id}: StackedBar.series[${i}].values must contain only numbers`);
      }
    }
    if (s.color !== undefined && !isExpressionObject(s.color) && !isValidChartColor(s.color)) {
      errors.push(`${id}: StackedBar.series[${i}].color must be one of: info, success, warning, error, neutral, or a #RRGGBB color`);
    }
  }
  if (props.title !== undefined && typeof props.title !== 'string') {
    errors.push(`${id}: StackedBar.title must be a string`);
  }
  if (props.showValues !== undefined && typeof props.showValues !== 'boolean') {
    errors.push(`${id}: StackedBar.showValues must be boolean`);
  }
  if (props.showLegend !== undefined && typeof props.showLegend !== 'boolean') {
    errors.push(`${id}: StackedBar.showLegend must be boolean`);
  }
}

function validateKeyValueProps(props, id, errors) {
  if (!Array.isArray(props.items)) {
    errors.push(`${id}: KeyValue.items must be an array`);
    return;
  }
  for (let i = 0; i < props.items.length; i++) {
    const item = props.items[i];
    if (!isObject(item)) {
      errors.push(`${id}: KeyValue.items[${i}] must be an object`);
      continue;
    }
    if (!isExpressionObject(item.key) && !isNonEmptyString(item.key)) {
      errors.push(`${id}: KeyValue.items[${i}].key must be a non-empty string`);
    }
    if (typeof item.value !== 'string') {
      errors.push(`${id}: KeyValue.items[${i}].value must be a string`);
    }
  }
  if (props.layout !== undefined && !isExpressionObject(props.layout) && !new Set(['vertical', 'inline']).has(props.layout)) {
    errors.push(`${id}: KeyValue.layout must be one of: vertical, inline`);
  }
}

function validateGaugeProps(props, id, errors) {
  if (typeof props.value !== 'number') {
    errors.push(`${id}: Gauge.value must be a number`);
  }
  if (props.max !== undefined && typeof props.max !== 'number') {
    errors.push(`${id}: Gauge.max must be a number`);
  }
  if (typeof props.value === 'number' && typeof (props.max ?? 100) === 'number') {
    const max = props.max ?? 100;
    if (props.value > max) {
      errors.push(`${id}: Gauge.value (${props.value}) must not exceed max (${max})`);
    }
    if (props.value < 0) {
      errors.push(`${id}: Gauge.value (${props.value}) must not be negative`);
    }
  }
  if (props.target !== undefined && typeof props.target !== 'number') {
    errors.push(`${id}: Gauge.target must be a number`);
  }
  if (props.label !== undefined && typeof props.label !== 'string') {
    errors.push(`${id}: Gauge.label must be a string`);
  }
  if (
    props.color !== undefined &&
    !isExpressionObject(props.color) &&
    !new Set(['info', 'success', 'warning', 'error']).has(props.color)
  ) {
    errors.push(`${id}: Gauge.color must be one of: info, success, warning, error`);
  }
  if (props.size !== undefined && typeof props.size !== 'number') {
    errors.push(`${id}: Gauge.size must be a number`);
  }
}

function validateImageProps(props, id, errors) {
  if (!isExpressionObject(props.src) && !isNonEmptyString(props.src)) {
    errors.push(`${id}: Image.src must be a non-empty string`);
  }
  if (props.alt !== undefined && typeof props.alt !== 'string') {
    errors.push(`${id}: Image.alt must be a string`);
  }
  if (props.caption !== undefined && typeof props.caption !== 'string') {
    errors.push(`${id}: Image.caption must be a string`);
  }
  if (props.maxHeight !== undefined && typeof props.maxHeight !== 'number') {
    errors.push(`${id}: Image.maxHeight must be a number`);
  }
  if (props.objectFit !== undefined && !isExpressionObject(props.objectFit) && !VALID_IMAGE_OBJECT_FIT.has(props.objectFit)) {
    errors.push(`${id}: Image.objectFit must be one of: cover, contain`);
  }
  if (props.borderRadius !== undefined && typeof props.borderRadius !== 'number') {
    errors.push(`${id}: Image.borderRadius must be a number`);
  }
}

function validateLinkProps(props, id, errors) {
  if (!isExpressionObject(props.href) && !isNonEmptyString(props.href)) {
    errors.push(`${id}: Link.href must be a non-empty string`);
  } else if (!isExpressionObject(props.href) && !/^(https?:\/\/|mailto:|tel:|#)/.test(props.href)) {
    errors.push(`${id}: Link.href must start with http://, https://, mailto:, tel:, or #`);
  }
  if (props.text !== undefined && typeof props.text !== 'string') {
    errors.push(`${id}: Link.text must be a string`);
  }
  if (props.target !== undefined && typeof props.target !== 'string') {
    errors.push(`${id}: Link.target must be a string`);
  }
}

function validateIframeProps(props, id, errors) {
  if (!isExpressionObject(props.src) && !isNonEmptyString(props.src)) {
    errors.push(`${id}: Iframe.src must be a non-empty string (HTML content or URL)`);
  }
  if (props.height !== undefined && typeof props.height !== 'number') {
    errors.push(`${id}: Iframe.height must be a number`);
  }
  if (props.title !== undefined && typeof props.title !== 'string') {
    errors.push(`${id}: Iframe.title must be a string`);
  }
  if (props.device !== undefined && props.device !== 'mobile' && props.device !== 'tablet') {
    errors.push(`${id}: Iframe.device must be 'mobile' or 'tablet'`);
  }
}

const PROPS_VALIDATORS = {
  Board: validateBoardProps,
  Column: validateColumnProps,
  Row: validateRowProps,
  Card: validateCardProps,
  Badge: validateBadgeProps,
  Tag: validateTagProps,
  TagList: validateTagListProps,
  Button: validateButtonProps,
  ActionBar: validateActionBarProps,
  Text: validateTextProps,
  List: validateListProps,
  EmptyState: validateEmptyStateProps,
  Topology: validateTopologyProps,
  DataTable: validateDataTableProps,
  BarChart: validateBarChartProps,
  DonutChart: validateDonutChartProps,
  TabGroup: validateTabGroupProps,
  TabPanel: validateTabPanelProps,
  ProgressBar: validateProgressBarProps,
  StatCard: validateStatCardProps,
  Timeline: validateTimelineProps,
  Callout: validateCalloutProps,
  Accordion: validateAccordionProps,
  Divider: validateDividerProps,
  CodeBlock: validateCodeBlockProps,
  LineChart: validateLineChartProps,
  StackedBar: validateStackedBarProps,
  KeyValue: validateKeyValueProps,
  Gauge: validateGaugeProps,
  Iframe: validateIframeProps,
  Image: validateImageProps,
  Link: validateLinkProps,
};

// ---------------------------------------------------------------------------
// Cycle detection
// ---------------------------------------------------------------------------

function detectCycles(elements) {
  const errors = [];
  const visited = new Set();
  const stack = new Set();

  function dfs(id) {
    if (stack.has(id)) {
      errors.push(`Cycle detected involving element "${id}"`);
      return true;
    }
    if (visited.has(id)) return false;
    visited.add(id);
    stack.add(id);

    const el = elements[id];
    if (el && Array.isArray(el.children)) {
      for (const childId of el.children) {
        if (dfs(childId)) return true;
      }
    }
    stack.delete(id);
    return false;
  }

  for (const id of Object.keys(elements)) {
    dfs(id);
  }
  return errors;
}

// ---------------------------------------------------------------------------
// Main validation
// ---------------------------------------------------------------------------

function validate(data) {
  const errors = [];

  // 1. Top-level structure
  if (!isObject(data)) {
    return { valid: false, errors: ['Root must be a JSON object'] };
  }

  if (!isNonEmptyString(data.version) || !SEMVERISH_VERSION_RE.test(data.version)) {
    errors.push(`version must be a numeric semver string like "1", "1.0.0", or "1.0.1", got: ${JSON.stringify(data.version)}`);
  }
  if (data.target !== 'taskflow') {
    errors.push(`target must be "taskflow", got: ${JSON.stringify(data.target)}`);
  }
  if (!isNonEmptyString(data.style)) {
    errors.push('style must be a non-empty string');
  }

  // 2. spec
  if (!isObject(data.spec)) {
    errors.push('spec must be an object');
    return { valid: false, errors };
  }
  const spec = data.spec;

  if (!isNonEmptyString(spec.root)) {
    errors.push('spec.root must be a non-empty string');
  }

  if (!isObject(spec.elements)) {
    errors.push('spec.elements must be an object');
    return { valid: false, errors };
  }
  const elements = spec.elements;

  // Verify root exists
  if (isNonEmptyString(spec.root) && !(spec.root in elements)) {
    errors.push(`spec.root "${spec.root}" not found in spec.elements`);
  }

  // 3. Validate each element
  for (const [id, raw] of Object.entries(elements)) {
    if (!isObject(raw)) {
      errors.push(`Element "${id}" must be an object`);
      continue;
    }
    const el = raw;

    // type check
    if (!isNonEmptyString(el.type) || !ALLOWED_TYPES.has(el.type)) {
      errors.push(`Element "${id}": type "${el.type}" is not one of the ${ALLOWED_TYPES.size} allowed component types`);
      continue;
    }

    if (el.repeat !== undefined) {
      if (!isObject(el.repeat)) {
        errors.push(`Element "${id}": repeat must be an object`);
      } else {
        const hasItems = el.repeat.items !== undefined;
        const hasStatePath = el.repeat.statePath !== undefined;

        if (!hasItems && !hasStatePath) {
          errors.push(`Element "${id}": repeat must include either items or statePath`);
        }

        if (hasItems && !isValidRepeatItems(el.repeat.items)) {
          errors.push(`Element "${id}": repeat.items must be an array`);
        }

        if (hasStatePath && !isValidStatePath(el.repeat.statePath)) {
          errors.push(`Element "${id}": repeat.statePath must be a non-empty path string`);
        }
      }
    }

    // children check
    if (el.children !== undefined) {
      if (!Array.isArray(el.children)) {
        errors.push(`Element "${id}": children must be an array`);
      } else {
        if (LEAF_TYPES.has(el.type)) {
          errors.push(`Element "${id}": leaf component "${el.type}" must not have children`);
        }
        for (const childId of el.children) {
          if (typeof childId !== 'string') {
            errors.push(`Element "${id}": children must contain only strings`);
          } else if (!(childId in elements)) {
            errors.push(`Element "${id}": child "${childId}" not found in spec.elements`);
          }
        }
        if (el.type === 'Topology') {
          for (const childId of el.children) {
            if (typeof childId !== 'string' || !(childId in elements)) {
              continue;
            }
            const child = elements[childId];
            if (!isObject(child) || child.type !== 'Card') {
              errors.push(`Element "${id}": Topology children must be Card elements`);
            }
          }
        }
        if (el.type === 'TabGroup') {
          for (const childId of el.children) {
            if (typeof childId !== 'string' || !(childId in elements)) {
              continue;
            }
            const child = elements[childId];
            if (!isObject(child) || child.type !== 'TabPanel') {
              errors.push(`Element "${id}": TabGroup children must be TabPanel elements`);
            }
          }
        }
      }
    }

    // props check
    const props = isObject(el.props) ? el.props : {};
    const validator = PROPS_VALIDATORS[el.type];
    if (validator) {
      validator(props, id, errors);
    }
  }

  // 4. Cycle detection
  const cycleErrors = detectCycles(elements);
  errors.push(...cycleErrors);

  // 5. canvas (optional)
  const canvas = data.spec?.canvas ?? data.canvas;
  if (canvas !== undefined && canvas !== null) {
    if (!isObject(canvas)) {
      errors.push('canvas must be an object');
    } else {
      if (canvas.backgroundImage !== undefined && typeof canvas.backgroundImage !== 'string') {
        errors.push('canvas.backgroundImage must be a string (base64 data URI or URL)');
      }
      if (canvas.fontColor !== undefined && typeof canvas.fontColor !== 'string') {
        errors.push('canvas.fontColor must be a string (CSS color value)');
      }
    }
  }

  // 6. subscriptions (optional array)
  if (data.subscriptions !== undefined && data.subscriptions !== null) {
    if (!Array.isArray(data.subscriptions)) {
      errors.push('subscriptions must be an array');
    } else {
      for (let i = 0; i < data.subscriptions.length; i++) {
        const sub = data.subscriptions[i];
        if (!isObject(sub)) {
          errors.push(`subscriptions[${i}]: must be an object`);
          continue;
        }
        if (!isNonEmptyString(sub.id)) {
          errors.push(`subscriptions[${i}]: id must be a non-empty string`);
        }
        validateSubscription(sub, i, errors);
      }
    }
  }

  // 7. meta
  if (!isObject(data.meta)) {
    errors.push('meta must be an object');
  } else {
    const meta = data.meta;
    if (!isNonEmptyString(meta.managerSessionId)) {
      errors.push('meta.managerSessionId must be a non-empty string');
    }
    if (!isNonEmptyString(meta.generatedAt)) {
      errors.push('meta.generatedAt must be a non-empty string');
    }
    if (!isNonEmptyString(meta.skillVersion)) {
      errors.push('meta.skillVersion must be a non-empty string');
    }
  }

  return { valid: errors.length === 0, errors };
}

// ---------------------------------------------------------------------------
// CLI entry
// ---------------------------------------------------------------------------

function main() {
  let input;

  const filePath = process.argv[2];
  if (filePath) {
    try {
      input = readFileSync(filePath, 'utf-8');
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      console.log(JSON.stringify({ valid: false, errors: [`Failed to read file: ${msg}`] }));
      process.exit(1);
    }
  } else {
    // Read from stdin
    try {
      input = readFileSync(0, 'utf-8');
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      console.log(JSON.stringify({ valid: false, errors: [`Failed to read stdin: ${msg}`] }));
      process.exit(1);
    }
  }

  let data;
  try {
    data = JSON.parse(input);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    console.log(JSON.stringify({ valid: false, errors: [`Invalid JSON: ${msg}`] }));
    process.exit(1);
  }

  const result = validate(data);
  console.log(JSON.stringify(result));
  process.exit(result.valid ? 0 : 1);
}

main();
