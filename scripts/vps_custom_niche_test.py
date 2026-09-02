"""VPS smoke: custom niche add → flow → KB → resolve → cleanup (run on VPS)."""

from app.niches import NICHES, add_custom_niche, remove_custom_niche
from app.platform.agent_provisioner import resolve_niche_key
from app.voice_agent.flow_builder import build_flow_for_niche

key, cfg = add_custom_niche(
    name="EV Charging Installers",
    target_type="both",
    avg_ticket_inr="₹80K–5L",
    keywords=["ev charger installation", "ev charging station dealers"],
)
print("added:", key, "| tier:", cfg["tier"], "| pricing:", cfg["pricing_inr"]["qualified_lead"])
print("in NICHES:", key in NICHES)
print("flow builds:", build_flow_for_niche(key) is not None)
print("resolves from loose text:", resolve_niche_key("ev charging"))
removed = remove_custom_niche(key)
print("cleanup removed:", removed, "| still in NICHES:", key in NICHES)
