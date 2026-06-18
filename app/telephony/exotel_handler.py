"""Deprecated — Exotel removed 2026-06-18. Provider is now Vobiz.

This module is a tombstone: nothing imports ExotelHandler anymore. Telephony
flows through app.telephony.vobiz_handler.VobizClient (and TwilioHandler for the
international path). Kept as an empty stub only so any stale .pyc / accidental
import fails loudly rather than silently resurrecting dead Exotel code.
"""
