#!/usr/bin/env python3
import sqlite3
import json

db_path = '/root/.omniroute/storage.sqlite'
conn = sqlite3.connect(db_path)
c = conn.cursor()

c.execute("SELECT provider, name, is_active, api_key, access_token FROM provider_connections WHERE is_active=1")
rows = c.fetchall()

print(f"Total active provider connections: {len(rows)}")
for p, name, is_active, api_key, access_token in rows:
    has_key = bool(api_key and len(api_key.strip()) > 0)
    has_tok = bool(access_token and len(access_token.strip()) > 0)
    key_preview = api_key[:8] + "..." if has_key else "NONE"
    print(f"  Provider: {p:<18} | Name: {str(name):<24} | Key: {key_preview:<12} | Token: {'YES' if has_tok else 'NO'}")
