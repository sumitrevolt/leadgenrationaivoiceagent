**[TRIAGE] 2 warn — dono heartbeat-wiring hain, agent failure nahi**

Warn rule: `scripts/buzz_staff_pulse.py:110-123` → `mins > 1440` = warn. Dono par `0e` aur state offline/stalled nahi (warna `fail` hota). So ye staleness flag hai, failure nahi. Par dono ki wajah alag hai — ek benign, ek asli gap.

**Raksha — 2.4d · BENIGN**
- `team.py:121`: Human Escalation Manager, schedule = "On-demand (live calls)", gated `CALL_TRANSFER`. Trigger sirf live-call escalation hai.
- 2.4d chup = koi gussa-customer / AI-unsure transfer nahi aaya. Ye achha signal hai, alarm nahi.
- Uska last `adv_step` bhi coordinator planner se aaya (`app/agents/coordinator.py:726`), uski asli duty se nahi.
- Ek gap: `EXPECTED_GAP_MIN` (`app/platform/automation_health.py:56-104`) me Raksha ka entry nahi → `CALL_TRANSFER` kabhi arm hua aur transfers fail hone lage to dead-man nahi pakdega. Low severity.

**Ira — 13.9d · ASLI WIRING GAP**
- Beat me Ira ka koi job nahi. `app/worker.py` ke poore `run_staff_job` args set (43 ids: growth, ops, call_kpi_digest, pipeline, email_followup …) me `ira` / journey / nurture koi nahi. `EXPECTED_GAP_MIN` me bhi nahi.
- `run_ira()` (`app/agents/staff.py:1387`) sirf on-demand dispatch map me hai — periodic koi nahi bulata, isliye `_log("ira", ...)` kabhi fire hi nahi hota. (Lekha fresh isliye hai kyunki uska `call_kpi_digest` beat me hai — `worker.py:506`.)
- Lekin uska KAAM shayad chal raha hai: `lifecycle_nurture.run_due()` `app/agents/growth_optimizer.py:200` se call hota hai (stage == "conversion" par), growth ki identity ke neeche. Yani attribution gap — journeys sweep ho rahe honge, Ira ka heartbeat blank.
- `resumed_by_admin` uska LATEST event hai → uske baad koi pause nahi hua (pause hota to `paused_by_admin`/warn dikhta).

**Dono par ek silent-path bug:** gate off hone par `run_ira`/`run_raksha` `_log()` ke bina early-return karte hain (`staff.py:1390`, `staff.py:1126`) — matlab gated-off manual run bhi zero heartbeat chhodta hai.

Scope: gates ki prod value maine read nahi ki. `_flag_on` (`staff.py:1030`) unset ko off maanta hai — bas itna hi claim kar sakta hoon.

**Meri AMBER recommendation (execute NAHI kiya):**
1. Gated early-return par `_log(member, job, "flag_off:<FLAG>", status="warn")` — silent stale ki jagah reasoned warn. `ok` nahi, warna false-green ban jayega.
2. Ira ko attribute karo: growth_optimizer ke nurture sweep par `_log("ira", ...)`, ya Ira ko apna beat + `EXPECTED_GAP_MIN` entry.
3. Event-driven members (Ira/Raksha) ke liye pulse me registered exemption — flat 1440-min rule inhe hamesha warn karta rahega.

ACTIVE_WORK me pehle se 3 stream hain (WS-MEM1 merge+deploy in flight, WS-GTM1, WS-AM1), isliye 4th mission nahi khol raha — ye WS-MEM1 ke peeche queue.

**Owner next action:** ek decision chahiye — `JOURNEY_ENGINE` arm karna hai ya off rakhna hai? Off rakhna hai to main sirf #1 (honest heartbeat) ka chhota patch queue karunga. Arm karna hai to Ira ko beat + dead-man ke saath wire karna padega. Flag main flip nahi karunga.
