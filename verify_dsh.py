"""Simple verification script for DSH integration."""

import os
import sys

# Add the current directory to the Python path
sys.path.insert(0, ".")

# Import the DSH integration module
try:
    from app.integrations import dsh as dsh_integration

    print("[OK] DSH integration module imported successfully")
except ImportError as e:
    print(f"[FAIL] Failed to import DSH integration: {e}")
    sys.exit(1)

# Test 1: DSH_RUNTIME_ENABLED flag check (default = False)
print("\n[Test 1] DSH_RUNTIME_ENABLED flag check (default)")
if "DSH_RUNTIME_ENABLED" in os.environ:
    del os.environ["DSH_RUNTIME_ENABLED"]
result = dsh_integration.is_dsh_runtime_enabled()
if result is False:
    print("[OK] DSH runtime is disabled by default")
else:
    print(f"[FAIL] DSH runtime should be disabled by default, got: {result}")
    sys.exit(1)

# Test 2: DSH_RUNTIME_ENABLED=1 enables runtime
print("\n[Test 2] DSH_RUNTIME_ENABLED=1")
os.environ["DSH_RUNTIME_ENABLED"] = "1"
result = dsh_integration.is_dsh_runtime_enabled()
if result is True:
    print("[OK] DSH runtime is enabled when DSH_RUNTIME_ENABLED=1")
else:
    print(f"[FAIL] DSH runtime should be enabled, got: {result}")
    sys.exit(1)

# Test 3: DSH_RUNTIME_ENABLED=0 disables runtime
print("\n[Test 3] DSH_RUNTIME_ENABLED=0")
os.environ["DSH_RUNTIME_ENABLED"] = "0"
result = dsh_integration.is_dsh_runtime_enabled()
if result is False:
    print("[OK] DSH runtime is disabled when DSH_RUNTIME_ENABLED=0")
else:
    print(f"[FAIL] DSH runtime should be disabled, got: {result}")
    sys.exit(1)

# Test 4: Shadow mode disabled by default
print("\n[Test 4] Shadow mode disabled by default")
if "DSH_SHADOW_ENABLED" in os.environ:
    del os.environ["DSH_SHADOW_ENABLED"]
result = dsh_integration.is_dsh_shadow_enabled()
if result is False:
    print("[OK] Shadow mode is disabled by default")
else:
    print(f"[FAIL] Shadow mode should be disabled by default, got: {result}")
    sys.exit(1)

# Test 5: Shadow mode disabled when DSH_SHADOW_ENABLED=0
print("\n[Test 5] Shadow mode disabled when DSH_SHADOW_ENABLED=0")
os.environ["DSH_SHADOW_ENABLED"] = "0"
result = dsh_integration.is_dsh_shadow_enabled()
if result is False:
    print("[OK] Shadow mode is disabled when DSH_SHADOW_ENABLED=0")
else:
    print(f"[FAIL] Shadow mode should be disabled, got: {result}")
    sys.exit(1)

# Test 6: Allowlist parsing (empty)
print("\n[Test 6] Allowlist parsing (empty)")
os.environ["DSH_ALLOWLIST_CSV"] = ""
result = dsh_integration.get_dsh_allowlist()
if result == set():
    print("[OK] Empty allowlist returns empty set")
else:
    print(f"[FAIL] Empty allowlist should return empty set, got: {result}")
    sys.exit(1)

# Test 7: Allowlist parsing (single agent)
print("\n[Test 7] Allowlist parsing (single agent)")
os.environ["DSH_ALLOWLIST_CSV"] = "agent1"
result = dsh_integration.get_dsh_allowlist()
if result == {"agent1"}:
    print("[OK] Single agent allowlist parsed correctly")
else:
    print(f"[FAIL] Single agent allowlist should be {{'agent1'}}, got: {result}")
    sys.exit(1)

# Test 8: Allowlist parsing (multiple agents)
print("\n[Test 8] Allowlist parsing (multiple agents)")
os.environ["DSH_ALLOWLIST_CSV"] = "agent1,agent2,agent3"
result = dsh_integration.get_dsh_allowlist()
if result == {"agent1", "agent2", "agent3"}:
    print("[OK] Multiple agents allowlist parsed correctly")
else:
    print(
        f"[FAIL] Multiple agents allowlist should be {{'agent1', 'agent2', 'agent3'}}, got: {result}"
    )
    sys.exit(1)

# Test 9: Allowlist check (agent in allowlist)
print("\n[Test 9] Allowlist check (agent in allowlist)")
os.environ["DSH_ALLOWLIST_CSV"] = "agent1,agent2"
result = dsh_integration.is_dsh_allowed(agent_id="agent1")
if result is True:
    print("[OK] Agent in allowlist is allowed")
else:
    print(f"[FAIL] Agent in allowlist should be allowed, got: {result}")
    sys.exit(1)

# Test 10: Allowlist check (agent not in allowlist)
print("\n[Test 10] Allowlist check (agent not in allowlist)")
os.environ["DSH_ALLOWLIST_CSV"] = "agent1"
result = dsh_integration.is_dsh_allowed(agent_id="agent2")
if result is False:
    print("[OK] Agent not in allowlist is denied")
else:
    print(f"[FAIL] Agent not in allowlist should be denied, got: {result}")
    sys.exit(1)

# Test 11: Health fields (default = all disabled)
print("\n[Test 11] Health fields (default = all disabled)")
os.environ.pop("DSH_RUNTIME_ENABLED", None)
os.environ.pop("DSH_SHADOW_ENABLED", None)
os.environ.pop("DSH_ALLOWLIST_CSV", None)
fields = dsh_integration.get_dsh_health_fields()
if fields["dsh_runtime_enabled"] is False:
    print("[OK] Health fields default to dsh_runtime_enabled=False")
else:
    print(f"[FAIL] Health fields should have dsh_runtime_enabled=False, got: {fields}")
    sys.exit(1)
if fields["dsh_shadow_enabled"] is False:
    print("[OK] Health fields default to dsh_shadow_enabled=False")
else:
    print(f"[FAIL] Health fields should have dsh_shadow_enabled=False, got: {fields}")
    sys.exit(1)
if fields["dsh_allowlist"] == []:
    print("[OK] Health fields default to dsh_allowlist=[]")
else:
    print(f"[FAIL] Health fields should have dsh_allowlist=[], got: {fields}")
    sys.exit(1)

print("\n[SUCCESS] All DSH integration tests passed!")
print("\nSummary:")
print("- DSH_RUNTIME_ENABLED flag check: WORKING")
print("- DSH_SHADOW_ENABLED flag check: WORKING")
print("- DSH_ALLOWLIST_CSV parsing: WORKING")
print("- Allowlist check: WORKING")
print("- Health fields: WORKING")
print("- Shadow mode dormant by default: CONFIRMED")
