"""Read-only Telegram wiring probe; never prints tokens or consumes updates.

DEPRECATED (2026-09-21): superseded by ``scripts/telegram_verify_setup.py``,
which works on both laptop and VPS (this one hardcodes the /opt/leadgen root)
and reports every credential slot, the real polling owner (non-consuming 409
probe), the polling lease and unwired coordination groups. Prefer that tool.
"""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml
from dotenv import dotenv_values


def main():
    root = Path('/opt/leadgen')
    if '--inbox-only' in sys.argv:
        inbox = root / 'data/telegram_inbox.jsonl'
        counts = {}
        topics = []
        for line in inbox.read_text().splitlines() if inbox.exists() else []:
            try:
                update = json.loads(line).get('update', {})
                for kind, value in update.items():
                    counts[kind] = counts.get(kind, 0) + 1
                    if isinstance(value, dict) and value.get('forum_topic_created'):
                        topics.append({'chat_id': value.get('chat', {}).get('id'),
                            'thread_id': value.get('message_thread_id') or value.get('message_id'),
                            'name': value['forum_topic_created'].get('name')})
            except (ValueError, AttributeError):
                continue
        print(json.dumps({'update_types': counts, 'topics': topics}))
        return 0
    env = dotenv_values(root / '.env')
    token = env.get('TELEGRAM_BOT_TOKEN', '')
    if not token:
        print('BOT_TOKEN_MISSING')
        return 2

    def call(method, **params):
        req = urllib.request.Request(
            f'https://api.telegram.org/bot{token}/{method}',
            data=json.dumps(params).encode(),
            headers={'Content-Type': 'application/json'},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            return json.loads(exc.read())
        except Exception as exc:
            return {'ok': False, 'description': type(exc).__name__}

    me = call('getMe')
    print(json.dumps({'bot_ok': me.get('ok'), 'username': me.get('result', {}).get('username')}))
    webhook = call('getWebhookInfo').get('result', {})
    print(json.dumps({'webhook': {k: webhook.get(k) for k in
        ('url', 'pending_update_count', 'last_error_date', 'last_error_message', 'allowed_updates')}}))
    spec = yaml.safe_load((root / 'config/telegram/setup_spec.yaml').read_text())
    groups = [g for p in spec['products'] for g in p['groups']] + spec['cross_product']
    for g in groups:
        chat = call('getChat', chat_id=g['chat_id'])
        details = chat.get('result', {})
        member = call('getChatMember', chat_id=g['chat_id'], user_id=me['result']['id'])
        print(json.dumps({'name': g['name'], 'chat_ok': chat.get('ok'),
            'error': chat.get('description'), 'id': details.get('id'),
            'title': details.get('title'), 'forum': details.get('is_forum'),
            'description_set': bool(details.get('description')),
            'pinned_message_id': details.get('pinned_message', {}).get('message_id'),
            'bot_status': member.get('result', {}).get('status')}))
    print(json.dumps({'webhook_secret_set': bool(env.get('TELEGRAM_WEBHOOK_SECRET'))}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
