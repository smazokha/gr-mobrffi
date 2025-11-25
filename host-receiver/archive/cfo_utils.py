import numpy as np
from scipy import signal
from fractions import Fraction

def _cfo_estimate_hz(x: np.ndarray, D: int, fs: float) -> float:
    # r = sum_{n} conj(x[n]) * x[n+D]
    r = np.vdot(x[:-D], x[D:])   # vdot conjugates the first arg
    return float(np.angle(r) * fs / (2*np.pi*D))

def coarse_cfo_estimate(stf: np.ndarray, fs: float) -> float:
    fft_len = 64
    M = fft_len // 4         # 16
    GI = fft_len // 4        # 16
    offset = int(round(0.75 * GI))
    use_len = min(M*9, len(stf) - offset)   # use 9 repeats max
    use = stf[offset:offset + use_len]
    return _cfo_estimate_hz(use, M, fs)

def fine_cfo_estimate(ltf: np.ndarray, fs: float) -> float:
    fft_len = 64
    M = fft_len              # 64
    GI = fft_len // 2        # 32
    offset = int(round(0.75 * GI))
    use_len = min(2*M, len(ltf) - offset)
    use = ltf[offset:offset + use_len]
    return _cfo_estimate_hz(use, M, fs)

def extract_preamble_cfo(preamble: np.ndarray, fs_in: float, show: bool=False):
    fs_ref = 20e6
    # Resample to 20 Msps only for estimation; CFO result is in Hz
    if not np.isclose(fs_in, fs_ref):
        # Rational resample
        frac = Fraction(fs_ref / fs_in).limit_denominator()
        pre  = signal.resample_poly(preamble, frac.numerator, frac.denominator)
    else:
        pre = preamble

    # L-STF is first 160 samples; L-LTF is next 160 (at 20 Msps)
    stf = pre[:160]
    cfo_coarse = coarse_cfo_estimate(stf, fs_ref)

    # Coarse derotation before fine estimate
    n = np.arange(len(pre), dtype=np.float64)
    pre_corr = pre * np.exp(-1j * 2*np.pi * cfo_coarse * n / fs_ref)

    ltf = pre_corr[160:320]
    cfo_fine = fine_cfo_estimate(ltf, fs_ref)

    total = cfo_coarse + cfo_fine
    if show:
        print(f"CFO coarse: {cfo_coarse/1e3:.2f} kHz, fine: {cfo_fine/1e3:.2f} kHz, total: {total/1e3:.2f} kHz")
    return cfo_coarse, cfo_fine, total

def extract_data_cfo(data: np.ndarray, fs_in: float):
    M = data.shape[0]
    out = np.zeros((M, 2), dtype=np.float64)
    for i in range(M):
        c0, c1, _ = extract_preamble_cfo(data[i], fs_in, show=False)
        out[i, 0] = c0
        out[i, 1] = c1
    return out

def compensate_cfo(data: np.ndarray, cfo_hz, fs: float):
    cfo_hz = np.asarray(cfo_hz)
    if cfo_hz.ndim == 2:
        cfo_hz = cfo_hz.sum(axis=1)  # coarse + fine

    M, N = data.shape
    n = np.arange(N, dtype=np.float64)[None, :]          # (1, N)
    phi = 2*np.pi * (cfo_hz[:, None] / fs) * n           # (M, N)
    return data * np.exp(-1j * phi)
