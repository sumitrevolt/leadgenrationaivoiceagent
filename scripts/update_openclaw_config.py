import json

with open('C:/Users/Ratanshila/.openclaw/openclaw.json', 'r', encoding='utf-8') as f:
    cfg = json.load(f)

token = cfg['gateway']['auth']['token']

# Add plugins section
cfg['plugins'] = {
    "load": {
        "paths": ["C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/config/openclaw/plugins/leadgen-owner-copilot"]
    },
    "entries": {
        "leadgen-owner-copilot": {"enabled": True}
    }
}

with open('C:/Users/Ratanshila/.openclaw/openclaw.json', 'w', encoding='utf-8') as f:
    json.dump(cfg, f, indent=2)

print(f'Plugins configured. Gateway token: {token[:15]}...')
print('OpenClaw gateway restart needed to load plugin')
