/**
 * LeadGen Owner Copilot — OpenClaw tool plugin (inbound to LeadGen).
 *
 * Tool: leadgen_owner_command
 * Calls: POST {LEADGEN_OWNER_COPILOT_URL}/api/owner-copilot/command
 * Auth: Bearer OPENCLAW_API_TOKEN (LeadGen gateway token)
 *
 * Never executes shell/SQL. Never talks to Celery/DB directly.
 * Owner OS remains sole action authority inside LeadGen.
 *
 * Secrets via env only — not in this file.
 */

import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

const ALLOWED = new Set([
  "platform.status",
  "agents.list",
  "agent.status",
  "approvals.list",
  "delivery.status",
  "queues.status",
  "business.daily_summary",
  "owner.next_actions",
  "agent.pause",
  "agent.resume",
  "agent.drain",
  "agent.stop_claims",
  "agent.assign_mission",
  "approval.decide",
]);

const RED_BLOCK = new Set([
  "calling.enable",
  "platform_dial.enable",
  "deploy.production",
  "deployment.execute",
  "billing.activate",
  "billing.refund",
  "billing.mutate",
  "shell.execute",
  "sql.execute",
  "customer.bulk_outreach",
  "customer.delete",
  "secrets.rotate",
  "kill_switch.bypass",
]);

export default definePluginEntry({
  id: "leadgen-owner-copilot",
  name: "LeadGen Owner Copilot",
  description: "Typed commands to LeadGen Owner OS via Owner Copilot API",
  register(api) {
    api.registerTool({
      name: "leadgen_owner_command",
      description:
        "Send one allowlisted typed Owner Copilot command to LeadGen Owner OS. " +
        "GREEN reads execute; AMBER parks approval; RED is refused. No shell/SQL.",
      parameters: {
        type: "object",
        additionalProperties: false,
        required: ["command"],
        properties: {
          command: { type: "string", minLength: 3, maxLength: 80 },
          params: { type: "object", additionalProperties: true },
          confirm: { type: "boolean" },
          idempotency_key: { type: "string", maxLength: 80 },
          correlation_id: { type: "string", maxLength: 80 },
          text: { type: "string", maxLength: 2000 },
        },
      },
      async execute(_id, params) {
        const command = String(params.command || "").trim();
        if (RED_BLOCK.has(command) || !ALLOWED.has(command)) {
          return {
            content: [
              {
                type: "text",
                text: JSON.stringify({
                  ok: false,
                  status: "REJECTED",
                  safety_lane: "RED",
                  error: `command not permitted by OpenClaw tool allowlist: ${command}`,
                }),
              },
            ],
            details: { ok: false, command, rejected: true },
          };
        }
        const base = (process.env.LEADGEN_OWNER_COPILOT_URL || "http://127.0.0.1:8000").replace(
          /\/$/,
          "",
        );
        const token = (process.env.OPENCLAW_API_TOKEN || "").trim();
        if (!token) {
          return {
            content: [
              {
                type: "text",
                text: JSON.stringify({
                  ok: false,
                  error: "OPENCLAW_API_TOKEN unset — refuse (fail-closed)",
                }),
              },
            ],
            details: { ok: false, error: "missing_token" },
          };
        }
        const body = {
          command,
          params: params.params || {},
          confirm: Boolean(params.confirm),
          idempotency_key: params.idempotency_key || undefined,
          correlation_id: params.correlation_id || undefined,
          text: params.text || undefined,
        };
        const ctrl = new AbortController();
        const t = setTimeout(() => ctrl.abort(), 15000);
        try {
          const res = await fetch(`${base}/api/owner-copilot/command`, {
            method: "POST",
            headers: {
              Authorization: `Bearer ${token}`,
              "Content-Type": "application/json",
              "X-OpenClaw-Agent": "owner-copilot",
            },
            body: JSON.stringify(body),
            signal: ctrl.signal,
          });
          const json = await res.json().catch(() => ({ ok: false, error: "bad_json" }));
          const verified = Boolean(
            json &&
              (json.verified ||
                json.status === "SUCCEEDED" ||
                json.status === "APPROVAL_REQUIRED" ||
                json.status === "REJECTED"),
          );
          return {
            content: [
              {
                type: "text",
                text: JSON.stringify({
                  http: res.status,
                  ...json,
                  openclaw_verified_envelope: verified,
                }),
              },
            ],
            details: { http: res.status, leadgen: json, verified },
          };
        } catch (err) {
          return {
            content: [
              {
                type: "text",
                text: JSON.stringify({
                  ok: false,
                  error: err && err.name === "AbortError" ? "timeout" : "fetch_failed",
                  type: err && err.name,
                }),
              },
            ],
            details: { ok: false, error: String(err && err.name) },
          };
        } finally {
          clearTimeout(t);
        }
      },
    });
  },
});
