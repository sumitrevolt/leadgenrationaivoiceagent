"""Integrations Package"""

from app.integrations.google_sheets import GoogleSheetsIntegration
from app.integrations.hubspot import HubSpotIntegration
from app.integrations.whatsapp import WhatsAppIntegration

# __all__ pehle define hona ZAROORI hai (2026-08-22 fix): neeche wale try-block
# me `.extend()` hote hai — pehle ye line try ke BAAD thi -> NameError on import.
__all__ = [
    "WhatsAppIntegration",
    "GoogleSheetsIntegration",
    "HubSpotIntegration",
    "dsh_integration",
]

try:
    from app.integrations import dsh as dsh_integration
except ImportError:  # pragma: no cover
    dsh_integration = None
