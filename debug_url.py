from app.config import settings
url = settings.database_url
print('original:', repr(url))
sync = url.replace('+asyncpg', '').replace('postgresql://', 'postgresql+psycopg2://')
print('after pg:', repr(sync))
if sync.startswith('sqlite+aiosqlite://'):
    sync = sync.replace('sqlite+aiosqlite://', 'sqlite:///')
print('after sqlite:', repr(sync))
import os
rel_path = sync[len('sqlite:///'):]
print('rel_path:', repr(rel_path))
abs_path = os.path.abspath(rel_path)
print('abs_path:', repr(abs_path))
print('final:', f'sqlite:///{abs_path}')