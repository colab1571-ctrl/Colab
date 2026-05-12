"""
UUIDv7 generator — time-ordered UUID with 48-bit Unix epoch milliseconds.

UUIDv7 layout (RFC 9562):
  Bits 0–47:   Unix timestamp in milliseconds
  Bits 48–51:  version (0111 = 7)
  Bits 52–63:  random (12 bits)
  Bits 64–65:  variant (10)
  Bits 66–127: random (62 bits)
"""

from __future__ import annotations

import os
import time
import uuid


def generate_uuidv7() -> uuid.UUID:
    """Generate a time-ordered UUIDv7."""
    ts_ms = int(time.time() * 1000)
    rand_a = int.from_bytes(os.urandom(2), "big") & 0x0FFF
    rand_b = int.from_bytes(os.urandom(8), "big") & 0x3FFFFFFFFFFFFFFF

    # Pack fields
    int_val = (
        (ts_ms << 80)
        | (0x7 << 76)      # version 7
        | (rand_a << 64)
        | (0b10 << 62)     # variant
        | rand_b
    )
    return uuid.UUID(int=int_val)
