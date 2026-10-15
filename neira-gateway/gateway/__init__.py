"""Neira Gateway — relay tipis antara PC (otak) dan klien (HP/browser).

Adaptasi `brahma_connect/gateway/` (Brahma-Echo) yang disederhanakan:
protokol = PAIR_REQUEST → PAIR_APPROVED (+DEVICE_KEY) → AUTHENTICATE →
PING/PONG → relay COMMAND/LOG/STATUS/AUDIO.
"""
