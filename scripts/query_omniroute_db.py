#!/usr/bin/env python3
"""Query OmniRoute database for providers, combos, connections"""

import sqlite3
import json

db_path = r"C:\Users\Ratanshila\.omniroute\storage.sqlite"

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")  # nosecurity
tables = cursor.fetchall()
print("=== TABLES ===")
for t in tables:
    print(f"  {t[0]}")

# Check providers
print("\n=== PROVIDERS ===")
try:
    cursor.execute("SELECT id, name, type, config FROM providers")  # nosecurity
    providers = cursor.fetchall()
    for p in providers:
        print(f"  ID: {p[0]}, Name: {p[1]}, Type: {p[2]}")
        if p[3]:
            print(f"    Config: {p[3][:200]}")
except Exception as e:
    print(f"  Error: {e}")

# Check combos
print("\n=== COMBOS ===")
try:
    cursor.execute("SELECT id, name, models, strategy FROM combos")  # nosecurity
    combos = cursor.fetchall()
    for c in combos:
        print(f"  ID: {c[0]}, Name: {c[1]}, Strategy: {c[3]}")
        if c[2]:
            models = json.loads(c[2])
            print(f"    Models ({len(models)}): {[m.get('model') for m in models[:5]]}...")
except Exception as e:
    print(f"  Error: {e}")

# Check connections
print("\n=== CONNECTIONS ===")
try:
    cursor.execute("SELECT id, providerId, name, status FROM connections")  # nosecurity
    conns = cursor.fetchall()
    for c in conns:
        print(f"  ID: {c[0]}, Provider: {c[1]}, Name: {c[2]}, Status: {c[3]}")
except Exception as e:
    print(f"  Error: {e}")

# Check api_keys
print("\n=== API KEYS ===")
try:
    cursor.execute("SELECT id, providerId, keyName, encryptedKey FROM api_keys")  # nosecurity
    keys = cursor.fetchall()
    for k in keys:
        print(f"  ID: {k[0]}, Provider: {k[1]}, Name: {k[2]}, Key: {k[3][:50] if k[3] else 'NULL'}...")
except Exception as e:
    print(f"  Error: {e}")

conn.close()