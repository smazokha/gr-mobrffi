from __future__ import annotations
from typing import List, Tuple
import numpy as np
import h5py
import os
from config import *
from pathlib import Path

def write_h5(
    *,
    iq_rows: List[np.ndarray],
    agc_rows: List[np.ndarray],
    rssi_rows: List[np.ndarray],
    idle_rows: List[np.ndarray],
    demod_rows: List[np.ndarray],
    tx_rows: List[np.ndarray],
    fcs_rows: List[np.ndarray],
    tsf_rt: np.ndarray,
    tsf_iq: np.ndarray,
    mac_bytes: np.ndarray,
    mac_str: np.ndarray,
    seq: np.ndarray,
    rssi_dbm_arr: np.ndarray,
    meta_times: Tuple[float, float, float],
    output_h5_path: str
):
    if IQ_AS_COMPLEX64:
        iq = np.vstack([row[np.newaxis, :] for row in iq_rows]).astype(np.complex64)
    else:
        iq = np.stack(iq_rows, axis=0).astype(np.int16)

    agc  = np.stack(agc_rows,  axis=0).astype(np.uint8)
    rssi = np.stack(rssi_rows, axis=0).astype(np.uint16)
    idle = np.stack(idle_rows, axis=0).astype(np.uint8)
    dem  = np.stack(demod_rows,axis=0).astype(np.uint8)
    txrf = np.stack(tx_rows,   axis=0).astype(np.uint8)
    fcs  = np.stack(fcs_rows,  axis=0).astype(np.uint8)

    start_unix, end_unix, elapsed = meta_times

    out_path = Path(os.path.expandvars(os.path.expanduser(output_h5_path))).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with h5py.File(output_h5_path, "w") as f:
        # Primary datasets
        f.create_dataset("iq", data=iq, compression="gzip", compression_opts=4)
        f.create_dataset("tsf_rt", data=tsf_rt, compression="gzip", compression_opts=4)
        f.create_dataset("tsf_iq", data=tsf_iq, compression="gzip", compression_opts=4)
        f.create_dataset("mac", data=mac_bytes, compression="gzip", compression_opts=4)
        f.create_dataset("mac_str", data=mac_str, compression="gzip", compression_opts=4) 
        f.create_dataset("seq", data=seq, compression="gzip", compression_opts=4)
        f.create_dataset("rssi_dbm", data=rssi_dbm_arr.astype(np.int8), compression="gzip", compression_opts=4)

        # Side-channel per-sample datasets
        f.create_dataset("agc_gain", data=agc,  compression="gzip", compression_opts=4)
        f.create_dataset("rssi_half_db", data=rssi, compression="gzip", compression_opts=4)
        f.create_dataset("ch_idle", data=idle, compression="gzip", compression_opts=4)
        f.create_dataset("demod", data=dem,  compression="gzip", compression_opts=4)
        f.create_dataset("tx_rf", data=txrf, compression="gzip", compression_opts=4)
        f.create_dataset("fcs_ok", data=fcs,  compression="gzip", compression_opts=4)

        # Meta
        meta = f.create_group("meta")
        meta.attrs["mode"] = "CAPTURE"
        meta.attrs["iq_dtype"] = "complex64" if IQ_AS_COMPLEX64 else "int16_interleaved_pairs"
        meta.attrs["M"] = int(iq.shape[1]) if IQ_AS_COMPLEX64 else int(iq.shape[1])
        meta.attrs["N"] = int(iq.shape[0])
        meta.attrs["strict_iq_len"] = bool(STRICT_IQ_LEN)
        meta.attrs["iq_len_override_samples"] = (
            int(IQ_LEN_OVERRIDE_SAMPLES) if IQ_LEN_OVERRIDE_SAMPLES is not None else -1
        )
        meta.attrs["start_unix"] = float(start_unix)
        meta.attrs["end_unix"] = float(end_unix)
        meta.attrs["elapsed_seconds"] = float(elapsed)
        meta.attrs["rssi_dbm_missing_sentinel"] = int(RSSI_DBM_MISSING)
