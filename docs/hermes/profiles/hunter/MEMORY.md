On Windows with Hermes Desktop: execute_code runs inside a Linux Singularity/Apptainer container, NOT on the Windows host. There are TWO hermes configs: container ~/.hermes/config.yaml and Windows host %LOCALAPPDATA%\hermes\config.yaml. If execute_code fails with "Neither apptainer nor singularity found in PATH", the fix is in the container's config (terminal.backend → local). Subagents also run inside the container. read_preview shows empty text for file:// URLs - cannot read file content that way.
§
Project: C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent, Hermes project name 'leadgenrationaivoiceagent'. Owner runs Hermes Desktop natively on Windows (NOT WSL). execute_code sandbox runs in a LINUX singularity container (separate from Windows host). Critical: Windows config at %LOCALAPPDATA%\hermes\config.yaml is DIFFERENT from container config at container ~/.hermes/config.yaml.
§
execute_code is broken: container's ~/.hermes/config.yaml has terminal.backend: singularity, but singularity is not in container PATH. Fix: change to terminal.backend: local in container config.
§
User operates autonomously: self-repair before escalation, 19-point structured recovery protocol, clear escalation criteria (SECRET_REQUIRED, HIGH_RISK_IRREVERSIBLE, BUSINESS_DECISION, ACCESS_REQUIRED only). Prefers Kanban over scattered tasks. Bot creation: core-first (Atlas/Forge/Sentinel/Relay), specialist later.
§
User communicates in Hinglish (terse, mixed Hindi/English). Shortcuts: 'omniroute' = project-local OmniRoute gateway. Uses explicit recovery ladder: local terminal → file tools → GitHub API → browser → Docker → SSH → escalate only if all fail.
§
User wants chat replies Telegram-styled: short punchy lines, emojis, casual Hinglish (Roman), minimal heavy markdown (no big headers/tables in normal chat). Status reports bhi isi style me — evidence line ke saath.