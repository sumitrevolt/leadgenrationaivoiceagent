# Vobiz Carrier Support Ticket — FOLLOW-UP SENT ✅

**Status (2026-08-26 ~14:15 IST):** Follow-up message Vobiz Console Support ticket me POST kar diya gaya (ticket open, created 25/08/2026 13:26). Pehle Vobiz AI ne "trial number = lower pickup rate" bola tha; humara follow-up us excuse ko counter karta hai — 100% instant carrier rejection sab numbers pe = carrier route block.
**Account:** `MA_RVP4WSNO` · **CLI:** `+911171366938`

---

**Subject:** All outbound calls failing with hangup_cause 3010 (Busy Line) from Carrier since Aug 25 — account MA_RVP4WSNO

**Message:**

> Hi Vobiz Support,
>
> For Account `MA_RVP4WSNO` and CLI `+911171366938`, **all outbound calls since Aug 25 are failing with `hangup_cause_code: 3010 (Busy Line)` with `Source: Carrier`**, across ALL destination numbers — this is not a customer-side busy signal.
>
> Evidence:
> - Failing call UUID: `77c56f3b-2fcf-46aa-acbf-efafb47eca2c` (Aug 25, cause 3010 / Busy Line, Source: Carrier)
> - Working call UUID (same account/CLI): `54896446-4420-4e59-827f-34c192b9593a` (Aug 24, connected fine, 267s duration)
>
> Nothing changed on our side between Aug 24 evening and Aug 25 morning — same trunk, same CLI, same dial string format. This pattern points to a carrier-route block on your side.
>
> Please check and unblock the carrier route for this account/CLI. Happy to share CDRs or any additional detail you need.
>
> Thanks,
> LeadsGenAI (sumitrevolt23@gmail.com)

---

**Baad me evidence attach karna ho to:** VPS pe `docker exec leadgen_app python - <<'EOF'` se ya admin panel se call_attempts table ka Aug 24 vs Aug 25 dump le sakte ho — abhi VPS SSH meri taraf se timeout ho raha tha (ISP-level), site khud globally UP hai (check-host.net se 4 nodes se HTTP 200 verified).
