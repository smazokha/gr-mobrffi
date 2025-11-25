from __future__ import annotations
import numpy as np
from config import *

class DecodedIQ:
    __slots__ = (
        "tsf", "I", "Q", "agc_gain", "rssi_half_db", "ch_idle",
        "demod", "tx_rf", "fcs_ok", "M"
    )
    def __init__(self, tsf: int, I, Q, agc_gain, rssi_half_db, ch_idle, demod, tx_rf, fcs_ok):
        self.tsf = tsf
        self.I = I
        self.Q = Q
        self.agc_gain = agc_gain
        self.rssi_half_db = rssi_half_db
        self.ch_idle = ch_idle
        self.demod = demod
        self.tx_rf = tx_rf
        self.fcs_ok = fcs_ok
        self.M = len(I)

def decode_openwifi_iq(iq_raw: bytes) -> DecodedIQ:
    """
    Decode a single OpenWiFi side-channel datagram (as forwarded inside NetSink's [iq] blob).
    Returns DecodedIQ with 1-D arrays of length M for I,Q, agc, rssi, flags.
    """
    if len(iq_raw) < 8 or (len(iq_raw) & 1) != 0:
        raise ValueError("bad IQ blob length")

    words = np.frombuffer(iq_raw, dtype="<u2")  # little-endian u16 view
    if words.size < 4:
        raise ValueError("IQ blob missing TSF words")

    # TSF (split across 4×u16, little-endian)
    w0, w1, w2, w3 = words[:4].astype(np.uint64)
    tsf = (w0 | (w1 << 16) | (w2 << 32) | (w3 << 48)).item()

    body = words[4:]
    if (body.size % 4) != 0:
        body = body[: (body.size // 4) * 4]

    if body.size == 0:
        # No symbols after TSF
        return DecodedIQ(tsf,
                         np.empty(0, np.int16), np.empty(0, np.int16),
                         np.empty(0, np.uint8), np.empty(0, np.uint16),
                         np.empty(0, np.uint8), np.empty(0, np.uint8),
                         np.empty(0, np.uint8), np.empty(0, np.uint8))

    sym = body.reshape(-1, 4)  # [I,Q,aux0,aux1] as u16

    I = sym[:, 0].astype(np.int16, copy=False)
    Q = sym[:, 1].astype(np.int16, copy=False)
    aux0 = sym[:, 2]
    aux1 = sym[:, 3]

    # Trim I and Q values to keep only the preamble
    if IQ_ENABLE_TRIMMING:
        I = I[IQ_TRIM_START : IQ_TRIM_START + IQ_TRIM_LENGTH]
        Q = Q[IQ_TRIM_START : IQ_TRIM_START + IQ_TRIM_LENGTH]

    agc_gain  = (aux0 & 0x00FF).astype(np.uint8,  copy=False)
    rssi_half_db = (aux1 & 0x07FF).astype(np.uint16, copy=False)
    ch_idle = ((aux0 & 0x8000) >> 15).astype(np.uint8, copy=False)
    demod = ((aux1 & 0x8000) >> 15).astype(np.uint8, copy=False)
    tx_rf = ((aux1 & 0x4000) >> 14).astype(np.uint8, copy=False)
    fcs_ok = ((aux1 & 0x2000) >> 13).astype(np.uint8, copy=False)

    return DecodedIQ(tsf, I, Q, agc_gain, rssi_half_db, ch_idle, demod, tx_rf, fcs_ok)
