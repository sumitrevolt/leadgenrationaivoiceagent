**[CORRECTION] Window-gate fix ka shape — mera pichla suggestion galat tha**

Maine kaha tha: parse fail par `trai_window_ok` `False` return kare. **Wo galat fix hai.**

`trai_window_ok` `(bool, reason)` deta hai aur caller (`voice_followup.py:390`) sirf `ok_window` par branch karta hai. Malformed env par `False` return karne ka matlab hoga — har call hamesha ke liye block, chupchaap, aur reason string ek normal "window closed" jaisi padhegi. Yani fail-OPEN ko main fail-to-ZERO me badal deta: transactional callback path ka poora silent outage. Ye pehle wale bug se bhi bura hota.

**Sahi shape:** env values ko parse-time par validate karo, aur parse fail hone par **hardcoded conservative defaults** par gir jao — promo 10/19, txn 9/21 — plus ek `warn` event log karo taaki misconfig dikhe. Yani safe window par fail-closed, zero par nahi.

Baaki pichla message jaisa ka waisa: 09:03 IST wala run legal tha (transactional path, 09-21 window), aur `except` wala fail-open ab bhi latent misconfig risk hai.

**Owner next action badla nahi:** wahi do calls pending hain — (1) `LIFECYCLE_NURTURE` decision, (2) window-gate ko safe-default par fail-closed karne ki permission. Tab tak main compliance path par kuch edit nahi kar raha.
