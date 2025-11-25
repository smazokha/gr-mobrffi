from __future__ import annotations
import struct
from typing import Optional, Tuple
import numpy as np

# NetSink header: [u64 tsf_rt][u64 tsf_iq][u16 rt_len][u16 iq_len]
_FMT_HEADER = "<QQHH"
_HDR_SZ = struct.calcsize(_FMT_HEADER)

def parse_packet(data: bytes) -> Tuple[int, int, int, int, bytes, bytes]:
    """Parse NetSink framing, return (tsf_rt, tsf_iq, rt_len, iq_len, rt_raw, iq_raw)."""
    if len(data) < _HDR_SZ:
        raise ValueError("short NetSink packet")
    tsf_rt, tsf_iq, rt_len, iq_len = struct.unpack_from(_FMT_HEADER, data, 0)
    hdr_end = _HDR_SZ + rt_len
    iq_end = hdr_end + iq_len
    if iq_end > len(data):
        raise ValueError("truncated NetSink packet payloads")
    return tsf_rt, tsf_iq, rt_len, iq_len, data[_HDR_SZ:hdr_end], data[hdr_end:iq_end]

# 802.11 helpers (sequence/mac)

def extract_mac_seq(rt_raw: bytes) -> Optional[Tuple[bytes, str, int]]:
    """
    Return (mac_bytes(6), mac_str, seq_num) or None if parse fails.
    Radiotap: bytes 2-3 ⇒ little-endian header length.
    802.11 MAC header follows; Sequence-control at offset 22 in 24B MAC hdr.
    """
    if len(rt_raw) < 4:
        return None
    rt_len = int.from_bytes(rt_raw[2:4], "little")
    if len(rt_raw) < rt_len + 24:
        return None
    mac_hdr = rt_raw[rt_len:rt_len + 24]
    mac_bytes = mac_hdr[10:16]
    seq_ctrl = int.from_bytes(mac_hdr[22:24], "little")
    seq_num = seq_ctrl >> 4
    mac_str = ":".join(f"{b:02x}" for b in mac_bytes)
    return mac_bytes, mac_str, seq_num

# Radiotap RSSI (dBm) parser (bit 5)

def _rt_field_size_align(bit: int) -> Tuple[int, int]:
    """(size, alignment) for common Radiotap fields we may cross."""
    return {
        0: (8, 8),   # TSFT
        1: (1, 1),   # Flags
        2: (1, 1),   # Rate
        3: (4, 2),   # Channel
        4: (2, 1),   # FHSS
        5: (1, 1),   # dBm Antenna Signal (i8)
        6: (1, 1),   # dBm Antenna Noise (i8)
        7: (2, 2),   # Lock Quality
        8: (2, 2),   # TX Attenuation
        9: (2, 2),   # dB TX Attenuation
        10: (1, 1),  # dBm TX Power
        11: (1, 1),  # Antenna index
        12: (1, 1),  # dB Antenna Signal (u8)
        13: (1, 1),  # dB Antenna Noise (u8)
        14: (2, 2),  # RX flags
    }.get(bit, (0, 1))

def parse_radiotap_rssi_dbm(rt_raw: bytes) -> Optional[int]:
    """
    Returns RSSI in dBm (signed int8) if present (Radiotap bit 5), else None.
    Safely walks the Radiotap header using present bitmaps and alignment.
    """
    if len(rt_raw) < 8:
        return None

    rt_len = int.from_bytes(rt_raw[2:4], "little")
    hdr_limit = min(rt_len, len(rt_raw))

    off = 4
    present_words = []
    while True:
        if off + 4 > hdr_limit:
            return None
        pw = int.from_bytes(rt_raw[off:off+4], "little")
        present_words.append(pw)
        off += 4
        if (pw & 0x8000_0000) == 0:
            break  # no more present words

    data_off = off

    def bit_set(b: int) -> bool:
        idx, bit = divmod(b, 32)
        return idx < len(present_words) and ((present_words[idx] >> bit) & 1) != 0

    off = data_off
    for b in range(0, 64):
        if not bit_set(b):
            continue
        size, align = _rt_field_size_align(b)
        if size == 0:
            return None
        if align > 1:
            off = (off + (align - 1)) & ~(align - 1)
        if off + size > hdr_limit:
            return None
        if b == 5:
            return int(np.frombuffer(rt_raw[off:off+1], dtype=np.int8)[0])
        off += size
        if b > 5:
            break
    return None
