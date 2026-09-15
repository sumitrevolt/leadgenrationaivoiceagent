# PC Cleanup Audit — 2026-09-13

**Scope:** `C:\Users\Ratanshila` (poora user profile) + `D:\`
**Mode:** READ-ONLY. Is audit me **kuch bhi move / rename / delete nahi hua**.
**Status:** Phase 1 (scan) ✅ complete → Phase 2 (ye report) ✅ → Phase 3 (execution) ⏸ aapki approval pending

---

## 0. Ek line me

C: pe **27.7 GB free** hai (287.6 GB used). Profile me **~152 GB** pada hai. Isme se **~12.5 GB objectively junk** hai, **~5.2 GB duplicate/dead copy** hai, **~100 GB regenerable cache/dev-data** hai (isko blanket delete nahi kar sakte), aur **~5.7 GB aisa hai jo main kabhi touch nahi karunga** (credentials + WorkBuddy data).

---

## 1. Disk reality

| Drive | Used | Free | Total |
|---|---|---|---|
| C: | 287.6 GB | **27.7 GB** | ~315 GB |
| D: | 83.4 GB | 47.9 GB | ~131 GB |

**Problem C: hai, D: nahi.** D: pe 47.9 GB free already hai. Note: `D:\wsl` (54.7 GB) aur `D:\Ollama` (16.9 GB) already D: pe hain — inhe clean karne se C: ko koi fayda nahi hoga.

### Top 20 sabse bade items (C: profile me)

| # | Path | Size |
|---|---|---|
| 1 | `AppData\Local\Claude-3p` | 11,421 MB |
| 2 | `AppData\Roaming\Cursor` | 9,494 MB |
| 3 | `AppData\Local\Android` | 8,276 MB |
| 4 | `AppData\Local\Google` (Chrome) | 7,762 MB |
| 5 | `AppData\Local\Temp` | 5,974 MB |
| 6 | `AppData\Roaming\Code` (VS Code) | 5,836 MB |
| 7 | `.vscode\extensions` | 5,391 MB |
| 8 | `AppData\Roaming\npm` | 5,117 MB |
| 9 | `.codex` | 4,689 MB |
| 10 | `.workbuddy-ai` | 4,563 MB 🔒 PROTECTED |
| 11 | `.local\share\opencode` | 4,513 MB |
| 12 | `AppData\Local\Microsoft` | 3,934 MB |
| 13 | `AppData\Local\Programs\DockerDesktop` | 3,396 MB |
| 14 | `.rustup` | 3,300 MB |
| 15 | `AppData\Local\Packages` | 3,094 MB |
| 16 | `java_error_in_studio.hprof` | 2,901 MB |
| 17 | `AppData\Local\Programs\Ollama` | 2,830 MB |
| 18 | `AppData\Local\Programs\Python` | 2,414 MB |
| 19 | `AppData\Local\Unity` | 2,335 MB |
| 20 | `.cache` | 2,028 MB |

### Top items (D: drive)

| Path | Size |
|---|---|
| `D:\wsl\docker-data` | 54,732 MB |
| `D:\Ollama\Models` | 16,920 MB |
| `D:\Backup` (Google 7.3 GB + npm-cache 1.3 GB + scoop 661 MB + pip 350 MB) | 9,740 MB |
| `D:\test` (flash loan + flash loan.zip) | 3,342 MB |
| `D:\pagefile.sys` (system) | 2,944 MB |
| `D:\flash loan` | 2,710 MB |
| `D:\Downloads` | 1,573 MB |
| `D:\autmated trading` | 1,089 MB |
| `D:\rtr16C6.tmp` | 1,024 MB |
| `D:\leadgen-archive` | 680 MB |
| `D:\$RECYCLE.BIN` | 52 MB |
| `D:\Owner-PC-Quarantine` | 0 MB |

---

## 2. TIER A — Zero-risk junk (Recycle Bin me move karne layak)

Ye items **objectively junk** hain. Koi config, koi credential, koi source code nahi. Ye dobara generate ho jaate hain ya already useless hain.

| Item | Size | Kyu junk hai |
|---|---|---|
| `AppData\Local\Temp\*` | 5,974 MB | Temp folder. Isme ek **orphaned `swap.vhdx` (4,132 MB, 2026-09-11)** + VS installer payloads (Microsoft.Modernization.UpgradeAssistant.vsix 102 MB, dotnet-sdk-internal MSI 117 MB, VisualStudio.GitHub.Copilot.vsix 118 MB) + Docker Desktop Updater exe 135 MB. |
| `java_error_in_studio.hprof` | 2,901 MB | Android Studio ka Java heap dump, 2026-08-12. Crash debug artifact. Zero value. |
| `AppData\Local\pip` (cache) | 462 MB | pip download cache — `pip cache purge` se regenerate/reset. |
| `AppData\Local\npm-cache` | 365 MB | npm cache — regenerate ho jaata hai. |
| `AppData\Local\pnpm-cache` | 178 MB | pnpm cache. |
| `AppData\Local\uv` (cache) | 60 MB | uv cache. |
| `AppData\Local\Microsoft\Windows\WebCache` | 66 MB | Windows web cache. |
| `AppData\Local\D3DSCache` | 1.8 MB | DirectX shader cache. |
| `git-installer.exe` + `msys2-installer.exe` | 62.5 MB | Installer binaries — install ke baad useless. |
| `acli.e` | 13.9 MB | 2025-06-22 ka truncated/aborted download. |
| `D:\rtr16C6.tmp` | 1,024 MB | Random-named `.tmp` file, 1 GB. |
| `D:\Downloads\*` | 1,573 MB | `android-studio-quail3-patch1-windows.exe`, `Grok_Bot_0.16.0_Setup.exe`, `Unconfirmed 3570.crdownload` (partial download). |
| `C:\$Recycle.Bin` | 3.6 MB | Purana recycle bin content. |
| `D:\$RECYCLE.BIN` | 52 MB | Purana recycle bin content. |
| `AppData\Local\xyz.block.buzz.app.bak` | 59 MB | App data ka stale `.bak`. |
| Profile root ke ~380 loose files (logs/scripts) | ~44 MB | Neeche section 3 dekho. |

**Tier A subtotal ≈ 12.8 GB** → C: free 27.7 GB → **~40 GB**

---

## 3. Profile root ka bada mess (396 files, 3,008 MB)

`C:\Users\Ratanshila` ke root me **396 loose files** pade hain — poora debug session ka debris:

| Extension | Count | Size | Type |
|---|---|---|---|
| `.py` | 111 | 0.2 MB | `sf_*.py` (24 Smartflo probes), `wsl_*.py`, `check_*.py`, `fix_*.py`, `temp_*.py`, `bp_derive*.py`, `pinprobe*.py`, `wt_probe*.py` |
| `.sh` | 83 | 0.1 MB | `wsl_*.sh` (25), `rev2-9.sh`, `dryrun.sh`, `oom*.sh`, `verify.sh`, `gate.sh` |
| `.txt` | 69 | 0.1 MB | `ssh_probe.txt`, `portal_refs.txt`, `bench*_out.txt`, `fix*_out.txt`, `mt5_*_out.txt` |
| `.log` | 41 | 0.2 MB | `dep*.log` (10 deploy logs), `pc*.log`, `pytest_*.log`, `sup*.log`, `three*.log` |
| `.ps1` | 24 | 0 MB | `check_dash.ps1`, `final_verify.ps1`, `kill_nonessential.ps1` |
| `.md` | 14 | 0.1 MB | `pr148_body.md`, `p1body.md`–`p7body.md`, `adr.md` |
| `.png` | 11 | 1.1 MB | UAT screenshots |
| `.exe` | 2 | 62.5 MB | installers |
| garbage names | 4 | 0 MB | `10,}`, `FIXED`, `nul`, `nul` |

**Recommendation:** ye sab **delete karne layak** hai — par ye aapke debug evidence ho sakte hain. Isliye main inhe ek hi zip me archive karke `D:\Backup\profile-root-debris-2026-09-13.zip` me rakh sakta hoon, phir root se Recycle Bin me move. Aap bolein to seedha Recycle Bin bhi.

---

## 4. TIER B — Duplicates & dead copies

| Item | Size | Finding |
|---|---|---|
| `Documents\leadgenrationaivoiceagent\new-clone` | 49 MB | **Dead clone.** Same remote (`sumitrevolt/leadgenrationaivoiceagent`), branch `main`, aur git status me **4042 entries — sab `D` (deleted)**. Matlab working tree khaali hai, sirf `.git` bacha hai. Parent repo me `?? new-clone/` untracked hai — yaani aapke project ka `git status` isse pollute ho raha hai. **Merge karne ko kuch nahi hai.** |
| `.openclaw.backup` | 1,076 MB | Naam me hi `.backup` hai. OpenClaw ka purana copy. |
| `D:\test\flash loan` + `D:\test\flash loan.zip` | 3,342 MB | `D:\flash loan` (2,710 MB) ka **duplicate** — folder aur zip dono. |
| `D:\leadgen-archive` | 680 MB | `claude-backup-20260829-142134` + `leadgen_recovery_v2` — purane recovery archives. |
| `Documents\antigravity\wise-newton` | 0 MB | Git repo **bina kisi remote ke**, branch `master`, sirf "Initial commit", **0 tracked files**. Khaali shell. |
| `D:\Owner-PC-Quarantine` | 0 MB | `CCleaner-20260910` + `startup-backups-20260910` — khaali. |
| `.local\share\claude\versions` | ~700 MB | 3 purane versions (2.1.207, 2.1.220, 2.1.251) — sirf latest chahiye. |

**Tier B subtotal ≈ 5.2 GB**

---

## 5. TIER C — Regenerable caches (blanket delete NAHI, review chahiye)

Ye bade hain (~100 GB) par inme **aapki settings, bookmarks, sessions, aur local data** mix hai. Inhe poora delete karna galat hoga. Main item-by-item batata hoon ki kya safe hai:

| Item | Size | Kya safe hai | Kya NAHI |
|---|---|---|---|
| `AppData\Local\Claude-3p` | 11,421 MB | ⚠️ Unknown structure — pehle andar dekhna padega. Sabse bada single item. | Blind delete |
| `AppData\Roaming\Cursor` | 9,494 MB | `Cache`, `CachedData`, `Code Cache`, `GPUCache`, `logs` | `User\settings.json`, `User\snippets`, workspaceStorage |
| `AppData\Local\Android` | 8,276 MB | `AVD` (emulator images — bade hote hain), `cache` | `Sdk` (re-download 8 GB lagega) |
| `AppData\Local\Google` | 7,762 MB | `Chrome\User Data\Default\Cache`, `Code Cache`, `GPUCache`, `Service Worker` | ❗ **Bookmarks, passwords, history, extensions** — inhe chhoona nahi |
| `AppData\Roaming\Code` | 5,836 MB | `Cache`, `CachedData`, `Code Cache`, `logs`, `workspaceStorage` | `User\settings.json`, `User\keybindings.json`, snippets |
| `.vscode\extensions` | 5,391 MB | Duplicate binaries — `codex` (247 MB linux) + `codex.exe` (282 MB win) **do extensions me repeat** (`openai.chatgpt` + `.92dd216d`) | Extensions khud (re-install karne padenge) |
| `AppData\Roaming\npm` | 5,117 MB | Global npm packages — `npm ls -g` se dekh ke unused hatayein | Blind delete |
| `.codex` | 4,689 MB | Session/rollout logs | Config |
| `.local\share\opencode` | 4,513 MB | `opencode.db` **akela 4,353 MB** hai | Poora delete |
| `AppData\Local\Microsoft` | 3,934 MB | `Edge\User Data\Default\Cache`, `Windows\INetCache` | Edge profile |
| `.rustup` | 3,300 MB | Purane toolchains — `rustup toolchain list` | Active toolchain |
| `AppData\Local\Packages` | 3,094 MB | Store app caches | App state |
| `AppData\Local\Programs\*` | 13,496 MB | Installed apps: DockerDesktop 3,396 · Ollama 2,830 · Python 2,414 · Cherry Studio 1,281 · WorkBuddyAI 1,256 · VS Code 1,044 · Verdent 774 · Freebuff 502 | Ye apps aap use karte ho to uninstall hi option hai |
| `AppData\Local\Unity` | 2,335 MB | Unity cache | Projects |
| `.cache` | 2,028 MB | `huggingface` models, `hyperframes` chrome-headless-shell (202 MB) | — |
| `.cursor` | 1,962 MB | `ai-tracking\ai-code-tracking.db` (105 MB) | Config |
| `AppData\Local\pnpm` | 1,840 MB | pnpm store | — |
| `AppData\Local\ms-playwright` | 1,802 MB | Playwright browsers (re-download ho jaate hain) | — |
| `AppData\Local\Ollama` | 1,507 MB | Logs + partial blobs | `D:\Ollama\Models` alag hai |
| `AppData\Local\Resonix` | 1,507 MB | App cache | — |
| `.claude` | 1,464 MB | `projects\*` session history | Config |
| `.cargo` | 1,399 MB | `registry\cache` | — |
| `.gemini` | 1,176 MB | Cache | Auth |
| `.omniroute` | 1,138 MB | Logs/cache | **`.omniroute_key` chhoona nahi** |
| `.openclaw-autoclaw` | 956 MB | Cache | — |
| `.docker` | 935 MB | `cli-plugins` (docker-agent 112 MB, docker-scout 192 MB, wsl docker-scout 188 MB) | Docker config |
| `.openclaw` | 862 MB | Cache/logs | — |

**Realistic Tier C recovery (selective): 25–40 GB** — par ye item-by-item decisions hain, isliye iske liye alag approval chahiye.

### D: side ke bade opportunities (C: ko help nahi karenge)

- `D:\wsl\docker-data` (54.7 GB) → `docker system prune -a --volumes` + `wsl --shutdown` + compact vhdx. **Ye delete karne wali cheez nahi hai, prune karne wali hai.**
- `D:\Ollama\Models` (16.9 GB) → `ollama list` se unused models `ollama rm <model>`.

---

## 6. TIER E — PROTECTED (kabhi touch nahi hoga)

Ye list main **refuse** karta hoon — chahe aap insist karo:

**Credentials / auth:**
- `.ssh\` · `.aws\` · `.azure\` · `.kube\` · `.config\` · `.gnupg` (agar ho) · `.mcp-auth\` · `.workbuddy-key-fallback\` · `.safety\`
- `AppData\Local\CodeBuddyExtension\` · `AppData\Roaming\CodeBuddy*\`
- `.claude.json` + uske 2 backups · `.gitconfig` · `.omniroute_key` · `.claude_gateway.env`
- `NTUSER.DAT*` · `ntuser.ini` · `ntuser.dat.LOG1/2`

**WorkBuddy data (system rule):**
- `.workbuddy-ai\` (4,563 MB) — project data + memory. **Kabhi delete nahi.**

**Current project:**
- `Documents\leadgenrationaivoiceagent\` (1,726 MB) — aapka live production SaaS.

**System:**
- `C:\Windows\*`, `C:\Program Files\*`, `C:\ProgramData\*`, `pagefile.sys`, `hiberfil.sys`, `AppData\Local\Packages` ke andar ka app state

**Transparency note:** scan ke dauraan sandbox ne do paths pe permission maangi — `C:\Users\Ratanshila\.ssh` aur `AppData\Local\CodeBuddyExtension\...\auth`. Aapne deny kiya. Isliye main ne **poora-profile blanket walk chhod diya** aur sirf allow-listed paths scan kiye. Ye report usi narrower scan pe based hai. `.ssh` aur CodeBuddyExtension ka andar ka data **kabhi read nahi kiya gaya**.

---

## 7. SECURITY findings (ye important hai)

### 7.1 Plaintext secrets profile root me pade hain ⚠️

`C:\Users\Ratanshila\` root me — jahan 380 junk files pade hain — ye credential files **plaintext** me hain:

| File | Risk |
|---|---|
| `smartflo_creds.json` | Smartflo/Tata telephony credentials |
| `.omniroute_key` | OmniRoute gateway key |
| `.claude_gateway.env` | Gateway env (key ho sakti hai) |
| `smartflo_evidence.txt` | Telephony evidence (tokens ho sakte hain) |
| `.ssh_leadgen_check.sh` / `.ssh_leadgen_fix.sh` | SSH scripts |
| `hwid` | Hardware ID |
| `storage_inspect.sqlite` | DB inspection copy |

**Kyu risk:** ye folder ka koi access-control nahi hai. Koi bhi bulk operation (zip → Drive, bulk upload, screenshot share, ya accidental `git add -A`) inhe leak kar sakta hai. `smartflo_creds.json` specifically production telephony creds hai.

**Recommendation (aapki approval ke saath):** inhe move karein → `C:\Users\Ratanshila\.secrets\` (ya project ke bahar koi protected location), permissions restrict karein, aur jinko use nahi ho raha unhe rotate karke delete karein. **Ye main automatically nahi karunga** — rotation aapka decision hai.

### 7.2 Git secrets scan — CLEAN ✅

Sab 5 repos ka `git ls-files` scan kiya. **Koi real secret tracked nahi hai.** Jo matches aaye wo sab false positive the:

| Repo | Remote | Branch | Tracked | Dirty | Verdict |
|---|---|---|---|---|---|
| `leadgenrationaivoiceagent` | `sumitrevolt/leadgenrationaivoiceagent` | `fix/smartflo-stream-routing` | 5,355 | 24 | ✅ clean |
| `...\new-clone` | same | `main` | 4,762 | **4,042 (sab deleted)** | 🗑️ dead |
| `leadsgenai-brain` | `sumitrevolt/leadsgenai-brain` | `main` | 429 | 0 | ✅ clean, **0 unpushed commits** |
| `buzz` | **`block/buzz`** ⚠️ | `main` | 3,799 | 9 | ⚠️ third-party repo |
| `antigravity\wise-newton` | *(none)* | `master` | **0** | 0 | 🗑️ empty |

False positives: `.agents/skills/secrets-management/SKILL.md`, `app/utils/secrets.py`, `app/telephony/answer_token.py`, `.env.example`, `frontend/design-system/tokens/*.css` — ye **file-naam matches** hain, actual secrets nahi.

### 7.3 `buzz` repo ka issue ⚠️

`Documents\buzz` (122.6 MB) **aapka repo nahi hai** — remote `github.com/block/buzz.git` hai (Block Inc. ka open-source project). Isme **9 local modifications** hain:

```
 M docker-compose.yml
 M docs/formal/nip-pl/acceptance.py
 M docs/formal/nip-pl/delivery_mutation.py
 M docs/formal/nip-pl/fixed_payload_mutation.py
 M docs/formal/nip-pl/mutation_test.py
 M docs/formal/nip-rs-unread/exhaustive.py
 M docs/formal/nip-rs-unread/model.py
 M docs/formal/nip-rs-unread/mutation.py
 M scripts/desktop_release.py
```

**Aapki request "GitHub pe merge karke local se hatao" yahan apply NAHI hoti** — aap kisi aur ka repo push nahi kar sakte. Options: (a) as-is chhodo, (b) 9 modified files ko `D:\leadgen-archive\` me copy karo phir local clone Recycle Bin me, (c) poora clone Recycle Bin me (upstream se dobara clone ho jaayega).

---

## 8. RAM / "memory full" — ye ALAG problem hai

Aapne kaha "local memory aur RAM full". **RAM files se full nahi hoti** — running processes se hoti hai. Disk cleanup RAM fix nahi karega. Actual data:

| Process | RAM |
|---|---|
| `vmmemWSL` (WSL2 VM) | 1,682 MB |
| `Memory Compression` | 904 MB |
| `WorkBuddyAI` **× 6 instances** | 811 + 202 + 181 + 180 + 168 + 98 = **1,640 MB** |
| `MsMpEng` (Defender) | 419 MB |
| `Docker Desktop` + backend | 142 + 130 + 154 = **426 MB** |
| `OpenClaw.Tray.WinUI` + `AutoClaw` | 191 + 146 = 337 MB |
| `chrome` (2) + `msedge` + `msedgewebview2` | 289 + 139 + 115 + 124 = 667 MB |
| `Taskmgr` | 168 MB |
| `WhatsApp.Root` | 158 MB |
| `CompatTelRunner` | 142 MB |
| `python` | 131 MB |
| `OneDrive` + `M365Copilot` | 110 + 103 = 213 MB |
| `explorer` | 283 MB |

**Startup items (HKCU Run):**
```
Warp                 -> AppData\Local\Programs\Warp\warp.exe
WorkBuddy.WorkBuddyAI -> AppData\Local\Programs\WorkBuddyAI\WorkBuddyAI.exe
OpenClawTray         -> AppData\Local\OpenClawTray\OpenClaw.Tray.WinUI.exe
Docker Desktop       -> AppData\Local\Programs\DockerDesktop\Docker Desktop.exe
Teams                -> MSTeams_8wekyb3d8bbwe\ms-teams.exe
OneDrive             -> OneDrive.exe /background
MicrosoftEdgeAutoLaunch_* (×2, ek .disabled_by_admin)
GoogleChromeAutoLaunch_*
```

**Root causes:**
1. **6 WorkBuddyAI processes** = 1.64 GB. Ye app instances stuck hain.
2. **WSL2 + Docker** = ~2.1 GB (vmmemWSL + Docker processes). `D:\wsl\docker-data` 54.7 GB bhi isi se.
3. **Duplicate agent trays** — OpenClaw Tray + AutoClaw dono chal rahe hain.
4. **Auto-start pe 6+ apps** — boot pe hi RAM bhar jaati hai.

**Recommendation (approval chahiye — ye system changes hain):** stuck WorkBuddyAI instances kill, duplicate tray band, non-essential startup entries disable, WSL memory cap `~/.wslconfig` me.

---

## 9. Proposed execution plan (Phase 3)

Har step ke liye **alag explicit approval** chahiye.

**Step 1 — Tier A junk → Recycle Bin** (12.8 GB)
Backup pehle (agar aap chahein), phir 10-file batches me Recycle Bin. Fail pe turant stop.

**Step 2 — Profile root debris archive** (396 files, ~44 MB)
Option A: `D:\Backup\profile-root-debris-2026-09-13.zip` banao, phir root se hatao.
Option B: seedha Recycle Bin.

**Step 3 — Tier B duplicates → Recycle Bin** (5.2 GB)
`new-clone`, `.openclaw.backup`, `D:\test\flash loan*`, `D:\leadgen-archive`, `wise-newton`, purane claude versions.

**Step 4 — Secrets ko protected location me move** (§7.1)
Aapke decide kiye hue paths pe.

**Step 5 — Tier C selective cache cleaning** (25–40 GB)
Item-by-item approval. Main har subfolder list karunga, aap haan/nahi bolein.

**Step 6 — RAM / startup fixes** (§8)
System changes — alag approval.

**Step 7 — Google Drive offsite backup**
Aapne choose kiya: sirf **project ka existing rclone → Google Drive** backup. Personal files Drive pe **nahi** jaayenge. Ye step main alag se run karunga jab aap bolein.

---

## 10. ⚠️ CRITICAL — Recycle Bin space free NAHI karta

Aapne choose kiya "Recycle Bin me move" (permanent delete nahi). Ye **safety ke liye sahi** hai — par honestly bata dun:

> **Recycle Bin me move karne se 0 bytes free honge.** Space tab free hoga jab aap Recycle Bin **empty** karenge.

Isliye correct flow ye hai:
1. Main items Recycle Bin me move karunga (reversible — galat lagta hai to Restore)
2. Aap 1–2 din system use karke verify karein ki kuch toota nahi
3. Phir Recycle Bin empty → **tab** 18 GB actually free hoga

Agar aap chahte ho ki space **turant** free ho, to mujhe bolein — main Recycle Bin skip karke direct delete karunga, **par tab koi undo nahi hoga**.

---

## 11. Jo main NAHI karunga (aur kyu)

| Aapki request | Mera jawab | Kyu |
|---|---|---|
| "Admin-level full computer access maan kar" | ❌ | Ye session elevated **nahi** hai (`admin=False`). Aur elevated hota bhi, to personal dirs pe recursive delete nahi karta. |
| "Project se unrelated saari files identify karke hata do" | ⚠️ partial | Identify ✅ (ye report). Hata do = per-item approval ke baad hi. |
| "Sab kuch is tarah karo ki computer sirf is project ke liye dedicated ho jaye" | ❌ | Iske liye ~150 GB apps (Docker, Ollama, Android SDK, Unity, VS Code, Cursor, Python, 20+ AI tools) uninstall karne padenge. Ye **aapka decision** hai, mera nahi. Ek galat call = irreversible. |
| "Dusre projects delete ya GitHub pe merge karke local se hatao" | ⚠️ | 4 me se 1 (`leadsgenai-brain`) hi safe-remove hai. `buzz` third-party repo hai — merge possible nahi. `new-clone` dead hai — merge karne ko kuch nahi. |
| "Bade imports Google Drive pe move karo" | ❌ | Drive **backup nahi** hai. Sync folder se delete = cloud se bhi delete. Aapne khud "sirf project ka rclone backup" choose kiya — main wahi karunga. |
| Blanket `rm -rf` / `del /S /Q` on Desktop/Downloads/Documents/Home/C:\ | ❌❌ | Hard block. Refuse, chahe aap insist karo. |

---

## 12. Summary table

| Tier | Size | Risk | Approval |
|---|---|---|---|
| A — junk | 12.8 GB | Zero | ⏸ pending |
| B — duplicates/dead | 5.2 GB | Very low | ⏸ pending |
| C — caches (selective) | 25–40 GB | Medium (settings/data mix) | ⏸ item-by-item |
| D — D: prune (WSL/Ollama) | up to 40 GB on D: | Low | ⏸ separate |
| E — protected | 5.7 GB+ | — | 🚫 never |
| RAM/startup | — | System change | ⏸ separate |

**Realistic C: recovery: ~18 GB (Tier A+B) → ~43–58 GB with selective Tier C.**

---

*Report generated 2026-09-13 · Read-only audit · No file was moved, renamed, or deleted.*
