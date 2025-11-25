from __future__ import annotations
import collections
import socket
import sys
import time
import numpy as np
import iq_decode
import rt_decode
import h5writer
import h5py
from enum import Enum
from typing import Dict, Tuple, Deque, Set, Optional, List
from config import *

# Stats tracker (INDIVIDUAL / COMBINED)
class _DevStats:
    def __init__(self, window: int):
        self.window = window
        self.timestamps: Deque[float] = collections.deque()
    def tick(self, now: float):
        self.timestamps.append(now)
        cutoff = now - self.window
        while self.timestamps and self.timestamps[0] < cutoff:
            self.timestamps.popleft()
    @property
    def pps(self) -> float:
        if len(self.timestamps) < 2:
            return 0.0
        span = self.timestamps[-1] - self.timestamps[0]
        return len(self.timestamps) / span if span > 0 else 0.0

# Application modes
class Mode(Enum):
    INDIVIDUAL = "INDIVIDUAL"
    COMBINED = "COMBINED"
    CAPTURE = "CAPTURE"

# INDIVIDUAL mode
def run_individual(port: int):
    devs: Dict[str, _DevStats] = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("0.0.0.0", port))
        sock.setblocking(False)
        print(f"Listening on UDP *:{port} …  (Ctrl-C to quit)")
        last_flush = time.time()
        while True:
            now = time.time()
            try:
                while True:
                    data, (ip, _) = sock.recvfrom(BUF_SIZE)
                    if len(data) < 8:
                        continue
                    rt_decode.parse_packet(data)  # sanity only
                    devs.setdefault(ip, _DevStats(SLIDING_WINDOW)).tick(now)
            except BlockingIOError:
                pass
            if now - last_flush >= REFRESH_EVERY:
                _render_individual(devs)
                last_flush = now
            time.sleep(0.01)

def _render_individual(devs: Dict[str, _DevStats]):
    sys.stdout.write("\x1b[2J\x1b[H")
    sys.stdout.write(f"Per-device packet rate ({SLIDING_WINDOW}s window)\n")
    sys.stdout.write("┌──────────────────────────┬─────────────┐\n")
    sys.stdout.write("│ Source IP                │  pkt/s      │\n")
    sys.stdout.write("├──────────────────────────┼─────────────┤\n")
    for ip in sorted(devs):
        sys.stdout.write(f"│ {ip:<24} │ {devs[ip].pps:9.2f} │\n")
    sys.stdout.write("└──────────────────────────┴─────────────┘\n")
    sys.stdout.flush()

# COMBINED mode
def run_combined(port: int):
    dev_stats: Dict[str, _DevStats] = {}
    combined_stats = _DevStats(SLIDING_WINDOW)
    in_flight: Dict[Tuple[str, int], Set[str]] = {}

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("0.0.0.0", port))
        sock.setblocking(False)
        print(f"Listening on UDP:{port} (COMBINED) (CTRL+C to quit)")

        last_flush = time.time()
        while True:
            now = time.time()
            try:
                while True:
                    raw, (ip, _) = sock.recvfrom(BUF_SIZE)
                    if len(raw) < 8:
                        continue

                    dev_stats.setdefault(ip, _DevStats(SLIDING_WINDOW)).tick(now)

                    _, _, _, _, rt_raw, _ = rt_decode.parse_packet(raw)
                    ext = rt_decode.extract_mac_seq(rt_raw)
                    if ext is None:
                        continue
                    _, mac_str, seq_num = ext
                    key = (mac_str, seq_num)

                    seen = in_flight.setdefault(key, set())
                    seen.add(ip)

                    if len(seen) == EXPECTED_DEVICES:
                        combined_stats.tick(now)
                        del in_flight[key]

            except BlockingIOError:
                pass

            if now - last_flush >= REFRESH_EVERY:
                _render_combined(dev_stats, combined_stats)
                last_flush = now

            time.sleep(0.01)

def _render_combined(devs: Dict[str, _DevStats], combo: _DevStats):
    sys.stdout.write("\x1b[2J\x1b[H")
    sys.stdout.write(f"Expected SDRs: {EXPECTED_DEVICES}"
                     f"Window: {SLIDING_WINDOW}s\n")
    sys.stdout.write("┌──────────────────────────┬─────────────┐\n")
    sys.stdout.write("│ Source IP (individual)   │  pkt/s      │\n")
    sys.stdout.write("├──────────────────────────┼─────────────┤\n")
    for ip in sorted(devs):
        sys.stdout.write(f"│ {ip:<24} │ {devs[ip].pps:9.2f} │\n")
    sys.stdout.write("├──────────────────────────┴─────────────┤\n")
    sys.stdout.write(f"│ COMBINED matched rate     {combo.pps:9.2f} │\n")
    sys.stdout.write("└─────────────────────────────────────────┘\n")
    sys.stdout.flush()

# CAPTURE mode: decode & store IQ + side info (+ Radiotap RSSI)
def run_capture(port: int, tx_name: str, output_h5_path: str):
    """
    Accumulate frames until CAPTURE_FRAMES_TARGET is reached or CTRL+C
    """
    tsf_rt_list: List[int] = []
    tsf_iq_list: List[int] = []
    mac_bytes_list: List[np.ndarray] = []
    mac_str_list: List[str] = []
    seq_list: List[int] = []
    rssi_dbm_list: List[int] = []

    iq_rows: List[np.ndarray] = []
    agc_rows: List[np.ndarray] = []
    rssi_rows: List[np.ndarray] = []
    idle_rows: List[np.ndarray] = []
    demod_rows: List[np.ndarray] = []
    tx_rows: List[np.ndarray] = []
    fcs_rows: List[np.ndarray] = []

    fixed_M: Optional[int] = IQ_LEN_OVERRIDE_SAMPLES
    received_total = 0

    start_unix = time.time()
    last_flush = start_unix

    def pad_or_trim(arr: np.ndarray, M: int, dtype) -> np.ndarray:
        """Pad with zeros or trim to exactly length M."""
        if arr.size == M:
            return arr.astype(dtype, copy=False)
        out = np.zeros(M, dtype=dtype)
        n = min(M, arr.size)
        out[:n] = arr[:n].astype(dtype, copy=False)
        return out

    def flush_to_h5():
        end_unix = time.time()
        elapsed = end_unix - start_unix
        N = received_total
        if N == 0:
            print("No frames captured; skipping HDF5 write.")
            return

        # Prepare arrays
        tsf_rt = np.asarray(tsf_rt_list, dtype=np.uint64)
        tsf_iq = np.asarray(tsf_iq_list, dtype=np.uint64)
        mac_bytes = np.vstack(mac_bytes_list).astype(np.uint8)  # (N,6)
        mac_str = np.array(mac_str_list, dtype=h5py.string_dtype(encoding="ascii"))
        seq = np.asarray(seq_list, dtype=np.uint16)
        rssi_dbm_arr = np.asarray(rssi_dbm_list, dtype=np.int8)

        h5writer.write_h5(
            iq_rows=iq_rows,
            agc_rows=agc_rows,
            rssi_rows=rssi_rows,
            idle_rows=idle_rows,
            demod_rows=demod_rows,
            tx_rows=tx_rows,
            fcs_rows=fcs_rows,
            tsf_rt=tsf_rt,
            tsf_iq=tsf_iq,
            mac_bytes=mac_bytes,
            mac_str=mac_str,
            seq=seq,
            rssi_dbm_arr=rssi_dbm_arr,
            meta_times=(start_unix, end_unix, elapsed),
            output_h5_path=output_h5_path
        )

        print(f"\nSaved {N} frames (elapsed {elapsed:.3f}s).")

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(("0.0.0.0", port))
            sock.setblocking(False)
            print(f"Listening on UDP *:{port} (CAPTURE) (CTRL+C to exit)")

            while True:
                try:
                    while True:
                        raw, _ = sock.recvfrom(BUF_SIZE)
                        if len(raw) < 8:
                            continue

                        tsf_rt, tsf_iq_hdr, _, _, rt_raw, iq_raw = rt_decode.parse_packet(raw)

                        # Extract MAC/SEQ (fallback to zeros if parse fails)
                        ext = rt_decode.extract_mac_seq(rt_raw)
                        if ext is None:
                            mac_bytes = bytes([0, 0, 0, 0, 0, 0])
                            mac_str = "00:00:00:00:00:00"
                            seq_num = 0
                        else:
                            mac_bytes, mac_str, seq_num = ext

                        # Radiotap RSSI (dBm), sentinel if missing
                        rssi_dbm = rt_decode.parse_radiotap_rssi_dbm(rt_raw)
                        rssi_dbm_list.append(int(rssi_dbm) if rssi_dbm is not None else RSSI_DBM_MISSING)

                        # Decode OpenWiFi IQ payload
                        try:
                            dec = iq_decode.decode_openwifi_iq(iq_raw)
                        except Exception as e:
                            if STRICT_IQ_LEN:
                                print(f"drop frame: decode error: {e}")
                            continue

                        # Infer/validate M
                        if fixed_M is None:
                            fixed_M = dec.M
                        elif STRICT_IQ_LEN and dec.M != fixed_M:
                            continue
                        M = fixed_M if fixed_M is not None else dec.M

                        # Build per-frame arrays, pad/trim to M
                        if IQ_AS_COMPLEX64:
                            iq_vec = (dec.I.astype(np.float32) + 1j * dec.Q.astype(np.float32))
                            iq_vec = pad_or_trim(iq_vec, M, np.complex64)
                        else:
                            iq_vec = np.empty((M, 2), dtype=np.int16)
                            n = min(M, dec.M)
                            iq_vec[:n, 0] = dec.I[:n]
                            iq_vec[:n, 1] = dec.Q[:n]
                            if n < M:
                                iq_vec[n:, :] = 0

                        agc_vec  = pad_or_trim(dec.agc_gain,     M, np.uint8)
                        rssi_vec = pad_or_trim(dec.rssi_half_db, M, np.uint16)
                        idle_vec = pad_or_trim(dec.ch_idle,      M, np.uint8)
                        dem_vec  = pad_or_trim(dec.demod,        M, np.uint8)
                        tx_vec   = pad_or_trim(dec.tx_rf,        M, np.uint8)
                        fcs_vec  = pad_or_trim(dec.fcs_ok,       M, np.uint8)

                        # Accumulate
                        tsf_rt_list.append(tsf_rt)
                        tsf_iq_list.append(tsf_iq_hdr)  # keep NetSink-sent TSF
                        mac_bytes_list.append(np.frombuffer(mac_bytes, dtype=np.uint8).copy())
                        mac_str_list.append(mac_str)
                        seq_list.append(seq_num)

                        iq_rows.append(iq_vec)
                        agc_rows.append(agc_vec)
                        rssi_rows.append(rssi_vec)
                        idle_rows.append(idle_vec)
                        demod_rows.append(dem_vec)
                        tx_rows.append(tx_vec)
                        fcs_rows.append(fcs_vec)

                        received_total += 1

                except BlockingIOError:
                    pass

                now = time.time()
                if now - last_flush >= REFRESH_EVERY:
                    elapsed = now - start_unix
                    _render_capture_progress(received_total, fixed_M, elapsed, tx_name)
                    last_flush = now

                if received_total >= CAPTURE_FRAMES_TARGET:
                    flush_to_h5()
                    if EXIT_AFTER_SAVE:
                        return
                    # rollover
                    tsf_rt_list.clear(); tsf_iq_list.clear()
                    mac_bytes_list.clear(); mac_str_list.clear(); seq_list.clear()
                    iq_rows.clear(); agc_rows.clear(); rssi_rows.clear()
                    idle_rows.clear(); demod_rows.clear(); tx_rows.clear(); fcs_rows.clear()
                    rssi_dbm_list.clear()
                    received_total = 0
                    start_unix = time.time()
                    last_flush = start_unix

                time.sleep(0.002)

    except KeyboardInterrupt:
        try:
            if received_total > 0:
                print("\nCtrl-C: writing partial capture…")
        finally:
            locals()["flush_to_h5"]()

def _render_capture_progress(n: int, fixed_M: Optional[int], elapsed_s: float, tx_name: str):
    sys.stdout.write("\x1b[2J\x1b[H")
    sys.stdout.write("CAPTURE mode: accumulating frames\n")
    sys.stdout.write(f"Target frames: {CAPTURE_FRAMES_TARGET}\n")
    sys.stdout.write(f"Received so far: {n}\n")
    sys.stdout.write(f"Elapsed: {elapsed_s:.3f}s since start\n")
    sys.stdout.write(f"Per-frame samples (M): {fixed_M if fixed_M is not None else '— (inferring)'}\n")
    sys.stdout.write(f"Output file: {tx_name}\n")
    sys.stdout.flush()

def main(port, mode, tx_name, output_h5_path):
    try:
        mode_enum = Mode(mode.upper())
    except ValueError:
        print(f"Unknown mode '{mode}'. Choose from {[m.value for m in Mode]}")
        sys.exit(1)

    if mode_enum is Mode.INDIVIDUAL:
        run_individual(port)
    elif mode_enum is Mode.COMBINED:
        run_combined(port)
    elif mode_enum is Mode.CAPTURE:
        run_capture(port, tx_name, output_h5_path)

if __name__ == "__main__":
    if len(sys.argv) >= 1 and 'alfa_' in sys.argv[1]:
        tx_name = sys.argv[1]
        output_h5_path = f"~/Desktop/probe_captures/{tx_name}.h5"
        try:
            main(DEFAULT_PORT, DEFAULT_MODE, tx_name, output_h5_path)
        except KeyboardInterrupt:
            print("\nInterrupted.")
    else:
        print('No device name specified.')
