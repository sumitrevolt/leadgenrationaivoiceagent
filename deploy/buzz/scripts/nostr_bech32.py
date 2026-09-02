#!/usr/bin/env python3
"""Nostr NIP-19 bech32 encoding for nsec/npub (pure python, no deps).

Usage:
    python3 nostr_bech32.py nsec <hex-secret-key>    # -> nsec1...
    python3 nostr_bech32.py npub <hex-public-key>    # -> npub1...

Used by buzz-keys.sh so identities work in the Buzz web/desktop app (which
accepts nsec/npub) and in buzz-cli (BUZZ_PRIVATE_KEY=nsec1...).
"""

import sys

CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"  # pragma: allowlist secret
CHARSET_REV = {c: i for i, c in enumerate(CHARSET)}


def bech32_polymod(values):
    GEN = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for v in values:
        b = chk >> 25
        chk = (chk & 0x1FFFFFF) << 5 ^ v
        for i in range(5):
            chk ^= GEN[i] if ((b >> i) & 1) else 0
    return chk


def bech32_hrp_expand(hrp):
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def bech32_encode(hrp, data):
    combined = data + [0] * 6
    pm = bech32_polymod(bech32_hrp_expand(hrp) + combined) ^ 1
    checksum = [(pm >> 5 * (5 - i)) & 31 for i in range(6)]
    return hrp + "1" + "".join(CHARSET[d] for d in data + checksum)


def convertbits(data, frombits, tobits, pad=True):
    acc = 0
    bits = 0
    ret = []
    maxv = (1 << tobits) - 1
    max_acc = (1 << (frombits + tobits - 1)) - 1
    for value in data:
        if value < 0 or (value >> frombits):
            raise ValueError("invalid data range")
        acc = ((acc << frombits) | value) & max_acc
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad and bits:
        ret.append((acc << (tobits - bits)) & maxv)
    elif not pad and bits >= frombits:
        raise ValueError("invalid padding")
    return ret


def encode(hrp, raw_bytes):
    data = convertbits(list(raw_bytes), 8, 5)
    return bech32_encode(hrp, data)


def main():
    if len(sys.argv) != 3:
        print(__doc__.strip())
        sys.exit(1)
    kind, hexkey = sys.argv[1], sys.argv[2]
    try:
        raw = bytes.fromhex(hexkey)
    except ValueError:
        print(f"invalid hex: {hexkey}", file=sys.stderr)
        sys.exit(1)
    if kind == "nsec":
        print(encode("nsec", raw))
    elif kind == "npub":
        print(encode("npub", raw))
    else:
        print(f"unknown kind {kind}; use nsec|npub", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
