"""Deprecated — Exotel Voicebot stream removed 2026-06-18. Provider is now Vobiz.

Tombstone stub: the live bidirectional voice WS path is the Vobiz stream
(app.voice_agent.vobiz_stream) + Twilio. The ``/ws/exotel-voicebot`` endpoint in
main.py no longer imports ExotelVoicebotSession (it closes the socket gracefully).
Nothing imports this module anymore.
"""
