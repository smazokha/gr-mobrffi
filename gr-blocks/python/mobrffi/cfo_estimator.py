import logging
import numpy as np
from scipy import signal
from fractions import Fraction
from gnuradio import gr

_EPS = 1e-12

class cfo_estimator(gr.sync_block):
    """
    docstring for block cfo_estimator
    """
    def __init__(self,
                 vectorLength=400,
                 sampleRate=25e6,
                 lag=16):
        gr.sync_block.__init__(
            self,
            name="MobRFFI CFO Estimator",
            in_sig=[(np.complex64, int(vectorLength))],
            out_sig=[np.float32],
        )
        self.vectorLength = int(vectorLength)
        self.fs = float(sampleRate)
        self.lag = int(lag)

        # Logging
        self._log = logging.getLogger("mobrffi.cfo")
        if not self._log.handlers:
            h = logging.StreamHandler()
            h.setFormatter(logging.Formatter("[%(name)s] %(levelname)s: %(message)s"))
            self._log.addHandler(h)
        self._log.setLevel(logging.INFO)

        # Validation
        if self.vectorLength < 320: raise ValueError("vectorLength must be at least 320 IQ samples long.")
        if self.fs <= 0: raise ValueError("sampleRate must be a positive integer.")
        if self.lag <= 0: raise ValueError("lag must be a positive integer.")

    def work(self, input_items, output_items):
        in_mat = input_items[0]
        out_vec = output_items[0]

        if in_mat.shape[1] != self.vectorLength:
            self._log.error(f"Incorrect input vector: received {in_mat.shape[1]}, expected {self.vectorLength}.")
            return 0
        
        produced = 0
        for i in range(in_mat.shape[0]):
            iq = in_mat[i].astype(np.complex64, copy=False).ravel()

            _, _, cfo_total_hz = self.extract_preamble_cfo(iq, fs_in=self.fs)

            # self._log.info(f"IQ received. CFO: {cfo_total_hz} Hz")

            out_vec[i] = np.float32(cfo_total_hz)
            produced += 1

        return produced

    def _cfo_estimate_hz(self, x: np.ndarray, D: int, fs: float) -> float:
        """
        CFO from delayed self-correlation with lag D.
        Returns frequency in Hz.
        """
        r = np.vdot(x[:-D], x[D:])
        return float(np.angle(r) * fs / (2*np.pi*D))

    def coarse_cfo_estimate(self, stf: np.ndarray, fs: float) -> float:
        """
        Coarse CFO from L-STF (10 short symbols of 16 samples @ 20 Msps).
        """
        fft_len = 64
        M = fft_len // 4
        GI = fft_len // 4
        offset = int(round(0.75 * GI))
        use_len = min(M*9, len(stf) - offset)
        use = stf[offset:offset + use_len]
        return self._cfo_estimate_hz(use, M, fs)

    def fine_cfo_estimate(self, ltf: np.ndarray, fs: float) -> float:
        """
        Fine CFO from L-LTF (2 long symbols of 64 samples @ 20 Msps).
        """
        fft_len = 64
        M = fft_len
        GI = fft_len // 2
        offset = int(round(0.75 * GI))
        use_len = min(2*M, len(ltf) - offset)
        use = ltf[offset:offset + use_len]
        return self._cfo_estimate_hz(use, M, fs)

    def extract_preamble_cfo(self, preamble: np.ndarray, fs_in: float, show: bool=False):
        """
        Estimate coarse+fine CFO (Hz) from a preamble captured at fs_in.
        Internally resamples to 20 Msps for standard 802.11 preamble indexing.
        Returns (coarse_hz, fine_hz, total_hz).
        """
        fs_ref = 20e6
        # Resample to 20 Msps only for estimation; CFO result is in Hz
        if not np.isclose(fs_in, fs_ref):
            frac = Fraction(fs_ref / fs_in).limit_denominator()
            pre  = signal.resample_poly(preamble, frac.numerator, frac.denominator)
        else:
            pre = preamble

        # L-STF is first 160 samples; L-LTF is next 160 (at 20 Msps)
        stf = pre[:160]
        cfo_coarse = self.coarse_cfo_estimate(stf, fs_ref)

        # Coarse derotation before fine estimate
        n = np.arange(len(pre), dtype=np.float64)
        pre_corr = pre * np.exp(-1j * 2*np.pi * cfo_coarse * n / fs_ref)

        ltf = pre_corr[160:320]
        cfo_fine = self.fine_cfo_estimate(ltf, fs_ref)

        total = cfo_coarse + cfo_fine
        if show:
            self._log.info(f"CFO coarse: {cfo_coarse/1e3:.2f} kHz, fine: {cfo_fine/1e3:.2f} kHz, total: {total/1e3:.2f} kHz")
        return cfo_coarse, cfo_fine, total