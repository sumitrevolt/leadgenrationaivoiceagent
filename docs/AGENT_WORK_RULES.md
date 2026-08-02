# AGENT_WORK_RULES.md — anti-mistake rules (derived from real misses, not theory)

> Har rule ek ACTUAL galti se aaya hai jo is repo pe hui. Theory nahi — postmortem.
> Read this before any debugging, any "root cause" claim, any merge, any deploy.
> Ye `CLAUDE.md` §0/§6/§8 ko replace nahi karta — usko sharp karta hai.

---

## R1. Primitive evidence pehle, hypothesis baad me

**Galti (2026-08-02):** `test_video_approval_principal.py` 4 red the. Status code `409` dekh kar maine
inhe "approval governance surface / launch blocker" keh diya aur ADR-142 semantics padhna shuru kar diya.
Asli body thi `insufficient_disk_headroom` — dev box 6.12% free tha. Code me bug tha hi nahi.
Maine ~15 minute galat jagah khodi kyunki maine **status code se guess kiya, body nahi padhi.**

**Rule:** Kisi failure ko naam dene se PEHLE uska sabse primitive artifact nikalo —
response **body**, exception **type + message**, exact **return dict**. Agar wo test se nahi dikh raha
to 10-line throwaway probe likho jo use print kare, phir probe delete karo.
`assert 409 == 200` diagnosis NAHI hai. `{"message":"insufficient_disk_headroom"}` diagnosis hai.

**Checkpoint:** "Main jo cause bol raha hoon, wo maine kis line of output me PADHA?" Answer na ho → mat bolo.

---

## R2. Apni hypothesis ko falsify karne ki koshish karo, confirm karne ki nahi

**Galti (2026-08-02):** `test_email_channel_fail_closed_without_smtp` working tree me fail, HEAD worktree me pass.
Maine turant likh diya "WIP ne fail-closed gate regress kiya" — ek §5 compliance alarm. Galat tha.
Jab maine SAARI changed app files HEAD worktree me copy ki, wo **phir bhi pass** hui → hypothesis dead.
Asli farq `.env` tha (real SMTP creds), code nahi.

**Rule:** Hypothesis banne ke baad agla step use *todne* ka experiment hai, *sajaane* ka nahi.
"Agar main galat hoon to kya dikhega?" — wahi run karo.
Cause ka elaan tabhi jab falsification attempt **fail** ho jaye.

**Yeh CLAUDE.md ke causal-claim landmine ka hi extension hai:** absence of errors ≠ your fix worked.

---

## R3. A/B compare karo to environment barabar karo — warna A/B hai hi nahi

**Galti (2026-08-02):** Maine clean `git worktree` @ HEAD banaya aur usse working tree se compare kiya.
Worktree me `data/` khali tha aur `.env` tha hi nahi. Do alag environments the — comparison invalid,
aur usi se galat "regression" claim nikla.

**Rule:** Do trees compare karne se pehle likh ke check karo ki kya-kya alag hai:
`.env` · `data/` · installed venv · env vars · cwd · OS state (disk, ports).
Ek waqt me **ek** variable badlo. Bisect: pehle code copy karo, phir data, phir env — aur har step pe re-run.

---

## R4. Test ko believe karne se pehle uski PRECONDITION check karo

**Galti (2026-08-02):** Do test mile jo apni precondition **enforce nahi** karte the, sirf assume karte the:
- "no SMTP creds ⇒ FAILED" — par creds ambient `.env` se aa rahe the → real machine pe LIVE send attempt.
- "approval identity" tests — par host disk free% pe depend kar rahe the → 15 test red.

Dono CI pe green the **sirf sanyog se** (CI pe `.env` nahi, disk khali hai).

**Rule:** Jo test kisi cheez ki *absence* ya *limit* assert karta hai, use wo absence/limit KHUD set karni chahiye
(`monkeypatch.setattr(settings, ...)` / `monkeypatch.setenv(...)`).
Green test jo apni precondition control nahi karta = **false safety**, red test se zyada khatarnak.

**Checkpoint:** "Ye test kisi doosri machine pe alag result dega?" Haan → hermetic karo.

---

## R5. Test selection saaf rakho — `-k` broad filters jhooth bolte hain

**Galti (2026-08-02):** `-k "autopilot or admin or ..."` chalaya — cross-file order-dependent results mile,
jisne diagnosis ko aur ulta kiya.

**Rule:** Diagnosis ke liye hamesha **poori file** chalao, phir **akela test**. Order-dependence suspect ho to
dono karo aur dono likho. Broad `-k` sirf smoke ke liye, evidence ke liye kabhi nahi.

---

## R6. "Done" = exit code, prose nahi

**Rule:** Har claim ke saath machine-readable proof: `EXIT=0`, `ALL CHECKS PASSED`, `/health` ka `version`.
Pipe se exit code chhup jata hai (`| Select-Object` / `| tail`) → exit code alag se capture karo.
Bina exit code ke "tests pass ho gaye" mat likho.

---

## R7. Parallel agents = shared files. Edit se pehle Read, hamesha

**Galti (2026-08-02):** OpenCode/Cursor usi file ko edit kar rahe the; ek Edit "file modified since read" pe fail hua.
Ek `_FakeRedis` fix unhone daala jo galat tha (`lambda: _FakeRedis()` — har call pe naya store).

**Rule:** Edit se turant pehle Read. `git add -A` kabhi nahi — files **naam se** stage karo.
Doosre agent ka kaam mile to use **verify** karo, blindly trust nahi — aur uske uncommitted kaam ko apne commit me mat kheencho.

---

## R8. Compliance gate / frozen surface = merge se pehle human "haan"

**Rule:** Ye surfaces kabhi chup-chaap merge/deploy nahi hote, chahe tests green hon:
TRAI calling window · DND fail-closed · consent/opt-out · DLT · billing/pricing (`packages.py`) ·
Swara/voice script (FROZEN) · kill switches · WhatsApp auto-send.
Green tests permission nahi hai. Inpe explicitly owner se poocho, aur diff dikha ke pooncho.

---

## R9. Scratch cleanup commit se pehle

**Rule:** Probe files, `*.log`, temp worktrees — sab delete/remove, phir `git status` padho.
Commit se pehle `git status --porcelain` me sirf intended files honi chahiye.
Temp worktree: `git worktree remove --force`.

---

## R10. Deploy = repo ka canonical script, apne haath ke docker commands nahi

**Rule:** `scripts/deploy_vps.sh` hi canonical hai (APP_VERSION mandatory, saare 5 app-image services,
pipefail, `/health.version == sha` verify). Manual `docker compose` = skew + `:latest` provenance loss.
VPS pe har compose command me `-f docker-compose.vps.yml` explicit.
Deploy ke baad `/health` **direct HTTPS** se probe karo, browser se nahi.

---

## Pre-flight checklist (har coding task se pehle 30 second)

1. Sabse primitive error artifact mere paas hai? (R1)
2. Meri hypothesis todne ka experiment kya hai? (R2)
3. Compare kar raha hoon to dono side ka env barabar hai? (R3)
4. Jis test pe bharosa kar raha hoon, wo apni precondition set karta hai? (R4)
5. Poori file + akela test dono chalaye? (R5)
6. Mere paas exit code hai? (R6)
7. Edit se pehle Read kiya? Files naam se stage ki? (R7)
8. Koi compliance/frozen surface chhu raha hoon? → rukо, poocho. (R8)
9. Scratch saaf hai? `git status` clean? (R9)
10. Deploy canonical script se + `/health` verify? (R10)
