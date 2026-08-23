#!/usr/bin/env node

import { createHash } from 'node:crypto'
import { globSync, readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { parseArgs } from 'node:util'

const { values } = parseArgs({
  options: {
    root: { type: 'string' },
    cordis: { type: 'string' },
    binary: { type: 'string' },
    output: { type: 'string' },
  },
})

if (!values.root || !values.cordis) {
  throw new Error('usage: verify_runtime.mjs --root <deployed-closure> --cordis <config> [--binary <exe>] [--output <json>]')
}

const root = resolve(values.root)
const cordisPath = resolve(values.cordis)
const manifest = JSON.parse(readFileSync(resolve(root, 'package.json'), 'utf8'))
const packageFiles = globSync('**/package.json', { cwd: root })
  .filter(isPackageRoot)
  .sort()
const packages = packageFiles.map((relative) => {
  const data = JSON.parse(readFileSync(resolve(root, relative), 'utf8'))
  return {
    name: String(data.name ?? ''),
    version: String(data.version ?? ''),
    license: normalizeLicense(data.license),
  }
}).filter(entry => entry.name)

const forbidden = packages
  .map(entry => entry.name)
  .filter(isForbiddenPackage)
  .sort()
if (forbidden.length) {
  throw new Error(`forbidden runtime packages: ${forbidden.join(', ')}`)
}

const duplicateNames = [...new Set(packages.map(entry => entry.name)
  .filter((name, index, names) => names.indexOf(name) !== index))].sort()
const duplicateWorkspaceNames = duplicateNames
  .filter(name => name.startsWith('@deepseek-ai/'))
if (duplicateWorkspaceNames.length) {
  throw new Error(`duplicate workspace package identities in closure: ${duplicateWorkspaceNames.join(', ')}`)
}
const externalDuplicates = duplicateNames
  .filter(name => !name.startsWith('@deepseek-ai/'))
  .map(name => ({
    name,
    versions: [...new Set(packages
      .filter(entry => entry.name === name)
      .map(entry => entry.version))].sort(),
  }))

const missingLicenses = packages
  .filter(entry => !entry.license || /unknown|unlicensed|see license/i.test(entry.license))
  .map(entry => entry.name)
  .sort()
if (missingLicenses.length) {
  throw new Error(`packages without machine-readable licences: ${missingLicenses.join(', ')}`)
}

const requiredWorkspace = [
  '@deepseek-ai/dsh-agent',
  '@deepseek-ai/dsh-agent-loop',
  '@deepseek-ai/dsh-llm',
  '@deepseek-ai/dsh-llm-pi-ai',
  '@deepseek-ai/dsh-llm-retry',
  '@deepseek-ai/dsh-mcp-client',
  '@deepseek-ai/dsh-sdk-jsonrpc-server',
  '@deepseek-ai/dsh-sdk-protocol',
  '@deepseek-ai/dsh-session',
  '@deepseek-ai/dsh-tools',
]
const names = new Set(packages.map(entry => entry.name))
const missingRequired = requiredWorkspace.filter(name => !names.has(name))
if (missingRequired.length) {
  throw new Error(`required runtime packages missing: ${missingRequired.join(', ')}`)
}

const cordis = readFileSync(cordisPath, 'utf8')
const plugins = [...cordis.matchAll(/^\s*name:\s*['"]([^'"]+)['"]\s*$/gm)]
  .map(match => match[1])
const allowedPlugins = new Set([
  '@deepseek-ai/dsh-agent',
  '@deepseek-ai/dsh-agent-loop',
  '@deepseek-ai/dsh-invariants',
  '@deepseek-ai/dsh-llm',
  '@deepseek-ai/dsh-llm-pi-ai',
  '@deepseek-ai/dsh-llm-retry',
  '@deepseek-ai/dsh-mcp-client',
  '@deepseek-ai/dsh-sdk-jsonrpc-server',
  '@deepseek-ai/dsh-session',
  '@deepseek-ai/dsh-session-persistence',
  '@deepseek-ai/dsh-system-prompt',
  '@deepseek-ai/dsh-timeout',
  '@deepseek-ai/dsh-tools',
  '@deepseek-ai/dsh-user-approval',
])
const unexpectedPlugins = plugins.filter(name => !allowedPlugins.has(name))
if (unexpectedPlugins.length) {
  throw new Error(`unexpected Cordis plugins: ${unexpectedPlugins.join(', ')}`)
}
for (const required of allowedPlugins) {
  if (!plugins.includes(required)) throw new Error(`required Cordis plugin missing: ${required}`)
}

const proof = {
  schema_version: 1,
  binary_sha256: values.binary ? sha256File(resolve(values.binary)) : null,
  cordis_sha256: sha256File(cordisPath),
  closure_manifest_sha256: sha256File(resolve(root, 'package.json')),
  package_count: packages.length,
  workspace_packages: packages.filter(entry => entry.name.startsWith('@deepseek-ai/')),
  external_duplicate_packages: externalDuplicates,
  licences: [...new Set(packages.map(entry => entry.license))].sort(),
  forbidden_packages: forbidden,
  cordis_plugins: plugins,
}

const rendered = `${JSON.stringify(proof, null, 2)}\n`
if (values.output) writeFileSync(resolve(values.output), rendered)
else process.stdout.write(rendered)

function normalizeLicense(value) {
  if (typeof value === 'string') return value.trim()
  if (value && typeof value === 'object' && typeof value.type === 'string') return value.type.trim()
  return ''
}

function isPackageRoot(relative) {
  if (relative === 'package.json') return true
  const segments = relative.split('/')
  const nodeModules = segments.lastIndexOf('node_modules')
  if (nodeModules < 0) return false
  const tail = segments.slice(nodeModules + 1)
  if (tail.length === 2) return tail[1] === 'package.json'
  return tail.length === 3 && tail[0].startsWith('@') && tail[2] === 'package.json'
}

function isForbiddenPackage(name) {
  if (name === 'node-pty') return true
  if (/^@deepseek-ai\/dsh-llm-/.test(name)
    && !['@deepseek-ai/dsh-llm-pi-ai', '@deepseek-ai/dsh-llm-retry'].includes(name)) return true
  return /^@deepseek-ai\/dsh-(?:bash|browser|fs-local|fs-sandbox|jobs|scheduler|session-telemetry|skill|subagent|terminal|tool-bash|tool-fs|tool-jobs|tool-skill|tool-subagent|tool-web|web(?:-|$))/.test(name)
}

function sha256File(path) {
  return createHash('sha256').update(readFileSync(path)).digest('hex')
}
