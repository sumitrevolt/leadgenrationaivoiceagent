# Agnes 3.0 Flash in Cline (OpenAI-Compatible)

Agnes docs ke hisaab se model OpenAI-compatible Chat Completions deta hai,
isliye Cline me custom provider ki zaroorat nahi — **OpenAI Compatible**
option hi use hota hai.

## Cline Desktop App steps (cline-app.exe)

Tumhara `cline-app.exe` already running hai, to direct app me karo:

1. **Cline Desktop app kholo** (taskbar / `C:\Users\Ratanshila\AppData\Local\Cline\cline-app.exe`).
2. Top-right ya sidebar me **⚙️ Settings** kholo.
3. **Providers / Model Provider** section me **API Provider = `OpenAI Compatible`** select karo.
4. Ye values dalo:

| Field | Value |
|---|---|
| Base URL | `https://apihub.agnes-ai.com/v1` |
| API Key | Agnes dashboard wali key (`sk-...`) |
| Model | `agnes-3.0-flash` |

5. **Model Configuration:** Context `512000`, Max Output `65536`.
6. **Verify / Test Connection** dabao — success aaye to chat me
   `agnes-3.0-flash` select karke use karo.

> Note: Desktop app key ko apne secure storage me rakhta hai
> (`C:\Users\Ratanshila\.cline\data` + OS keychain), repo ke `.env` me
> dalne ki zaroorat nahi.


## Verify via curl (key terminal me hi rakho, file me mat likho)

```bash
curl https://apihub.agnes-ai.com/v1/chat/completions \
  -H "Authorization: Bearer $AGNES_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-3.0-flash",
    "messages": [{"role": "user", "content": "Say ok"}],
    "max_tokens": 16
  }'
```

## Notes

- Key Cline ke VS Code **SecretStorage / globalStorage** me rehti hai
  (`saoudrizwan.claude-dev` globalStorage), repo ke `.env` me mat dalo.
  `.env` sirf project backend secrets ke liye hai.
- Chat me jo key paste hui hai wo ab **public/unsafe** hai — Agnes dashboard
  se usko **revoke/rotate** karke nayi key Cline me dalo.
- Fail ho to check karo: Base URL me `/v1` included ho,
  Model ID exact `agnes-3.0-flash` ho, key me extra space/newline na ho.
