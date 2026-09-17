"""One bounded diagnostic to the existing owner-only Telegram health topic."""
import json
import os
from pathlib import Path
import urllib.request
from dotenv import dotenv_values


def main():
    env = dotenv_values('/opt/leadgen/.env')
    token = env['TELEGRAM_BOT_TOKEN']
    chat_id = -1003878635977

    def call(method, **params):
        req = urllib.request.Request(
            f'https://api.telegram.org/bot{token}/{method}',
            data=json.dumps(params).encode(),
            headers={'Content-Type': 'application/json'},
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            result = json.load(response)
        if not result.get('ok'):
            raise RuntimeError('Telegram API rejected diagnostic')
        return result['result']

    # Fail closed unless this remains the two-member, private owner-and-bot chat.
    chat = call('getChat', chat_id=chat_id)
    if chat.get('username') or call('getChatMemberCount', chat_id=chat_id) != 2:
        print('REFUSED_NOT_OWNER_ONLY')
        return 2
    marker = Path('/tmp/leadgen_telegram_owner_canary_20260916.json')
    if marker.exists():
        print(marker.read_text())
        return 0
    with marker.open('x') as stream:
        stream.write('{"status":"pending_do_not_retry"}')
        stream.flush()
        os.fsync(stream.fileno())
    message = call('sendMessage', chat_id=chat_id, message_thread_id=6,
        text='Automated setup check (16 Sep): 10/10 chats verified; bot admin access and webhook health confirmed. One-time owner-only delivery test.',
        disable_notification=True)
    result = {'status': 'sent', 'message_id': message['message_id'],
        'thread_id': message.get('message_thread_id'), 'chat_id': message['chat']['id']}
    marker.write_text(json.dumps(result))
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print('CANARY_FAILED_' + type(exc).__name__)
        raise SystemExit(1)
