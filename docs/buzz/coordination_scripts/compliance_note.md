**[COMPLIANCE] 09:03 IST voice run = legal. Par window-check ek fail-OPEN path rakhta hai.**

Aaj 09:15 pulse me Swara ka `voice_followup_run` (~09:03 IST) dikha — 10-19 promotional window se pehle. Check kiya, **violation nahi hai**:

- `app/telephony/voice_followup.py:390` → `trai_window_ok(True)` — yaani **transactional**, promotional nahi. File ka line 4 khud kehta hai: "NOT platform_dial cold outbound", aur alag se `VOICE_FOLLOWUP=1` gated hai (default OFF).
- `app/telephony/campaign_compliance.py:30-36`: transactional window = `COMPLIANCE_TXN_START` (default 9) se `COMPLIANCE_TXN_END` (default 21). 09:03 iske andar hai aur TCCCPR ki legal 09:00-21:00 ceiling ke andar hai.
- 10-19 wala gate `COMPLIANCE_PROMO_START/END` hai — wo cold outbound (`platform_dial`) par lagta hai, is path par nahi. Do alag windows hain, dono sahi jagah lagi hain.

**Jo cheez report karne layak hai** — `trai_window_ok` ka bottom handler (`campaign_compliance.py:43-44`):

```python
except Exception as e:  # never blocks on our own bug
    return True, f"window-check skipped: {e}"
```

Ye compliance gate **fail-OPEN** karta hai. Realistic trigger: `COMPLIANCE_PROMO_START` / `_END` / `_TXN_*` me koi non-numeric value aa gayi to `int()` throw karega → gate `True` return karega → **saare calls ke liye window check band ho jayega**, bina kisi error ke. Aaj koi evidence nahi hai ki ye trigger hua — errors 0 hain aur maine prod env read nahi kiya. Ye latent misconfig risk hai, active incident nahi.

Meri raay: DND gate fail-closed hai, window gate ko bhi wahi posture chahiye — parse fail par `False` return ho, `True` nahi. Ye mere pichle heartbeat-honesty patch se alag aur usse zyada serious hai; isko main usme nahi chhupaunga.

Baaki 09:15 pulse saaf: 0 fail, 0 errors, 782 actions, 26 working. Wahi 2 warn (Ira 14.5d, Raksha 2.9d).

**Owner next action:** do alag calls chahiye — (1) `LIFECYCLE_NURTURE` wala pending decision, aur (2) window-gate ko fail-closed karne ki permission. (2) chhota patch hai par compliance path chhoota hai, isliye bina aapke haan ke main haath nahi lagaunga.
