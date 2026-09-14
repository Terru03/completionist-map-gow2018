"""Pure helpers for the native object-checkpoint persistence key.

GoW.exe 1.0.13 (SHA-256 caebcb...) converts the GameObject pointer stored at a
subobject's +0x28 into an opaque Lua object token before indexing
``__PickleTable.__subobjs``.  The conversion at RVA 0x60B9C0 reads three fields
from that GameObject.  Keeping the bit layout here makes the disassembly claim
testable without pretending that the runtime token is a WAD GUID.
"""
from __future__ import annotations


def pack_object_token(flags_278: int, word_280: int, dword_284: int) -> int | None:
    """Reproduce RVA 0x60B9C0; return None when object has no valid ref bit."""
    if flags_278 & 1 == 0:
        return None
    bank = dword_284 & 0xFFFFF
    flavor = (flags_278 >> 3) & 1
    low = word_280 & 0xFFFF
    return (((bank << 1 | flavor) << 16 | low) << 1) | 1


def unpack_object_token(token: int) -> dict[str, int] | None:
    """Decode fields visible in the packed object token; reject non-object tags."""
    if token < 0 or token & 1 == 0:
        return None
    payload = token >> 1
    return {
        "word_280": payload & 0xFFFF,
        "flags_278_bit3": (payload >> 16) & 1,
        "dword_284_low20": (payload >> 17) & 0xFFFFF,
    }
