import os
import logging
import numpy as np
from gnuradio import gr
from scipy import signal

try:
    import onnxruntime as ort
except Exception as e:
    raise ImportError("onnxruntime is required: `pip install onnxruntime-gpu`")

class ChannelIndSpectrogram():
    def __init__(self,):
        pass
    
    def _normalization(self, data):
        data_normalized = np.zeros(data.shape, dtype=complex)
        for i in range(data.shape[0]):
            data_normalized[i] = data[i] / np.sqrt(np.mean(np.abs(data[i])**2))
        return data_normalized        

    def _channel_ind_spectrogram_single(self, frame, win_len, overlap, enable_ind=True):
        _, t, spec = signal.stft(frame, window = 'boxcar', 
                                nperseg = win_len, noverlap = overlap, 
                                nfft = win_len, return_onesided = False, 
                                padded = False, boundary = None)
        spec = np.fft.fftshift(spec, axes=0)

        # If enabled, produce channel-independent spectrogram
        if enable_ind:
            spec = spec[:, 1:] / spec[:, :-1]

        # Return logarithm of the spectrogram magnitude
        spec = np.log10(np.abs(spec)**2)

        # Apply standardization to obtain more spectrogram consistency
        spec = self._standardization(spec)

        return t, spec

    def _standardization(self, spec):
        mean = spec.mean()
        std = spec.std()
        spec = (spec - mean) / std
        return spec

    def channel_ind_spectrogram(self, data, row, enable_ind, overlap_coef = 0.9, remove_subcarriers=True, return_spec_t=False):
        # Normalize IQ samples
        data = self._normalization(data)

        overlap = row * overlap_coef

        # Produce spectrogram once to dynamically determine input array dimensions
        t, test_run = self._channel_ind_spectrogram_single(data[0], win_len=row, overlap=overlap, enable_ind=enable_ind)

        # Convert each packet (IQ samples) to a channel independent spectrogram.
        data_spectrograms = np.zeros([data.shape[0], test_run.shape[0], test_run.shape[1], 1], dtype=np.float32)

        # Run STFT for each frame separately
        for i in np.arange(data.shape[0]):
            _, spec = self._channel_ind_spectrogram_single(data[i], win_len=row, overlap=overlap, enable_ind=enable_ind)
            data_spectrograms[i,:,:,0] = spec.astype(np.float32)

        if remove_subcarriers:
            guards = list(range(0, 14)) + [40] + list(range(67, 80))
            data_spectrograms = np.delete(data_spectrograms, guards, axis=1)

        if return_spec_t: return data_spectrograms, t
        else: return data_spectrograms

class get_fingerprint(gr.sync_block):
    """
    docstring for block get_fingerprint
    """
    def __init__(self,
                 vectorLength=400,
                 embeddingLength=768,
                 specWidth=80,
                 modelPath='/path/to/model.onnx',
                 computeMode='CPU'):
        gr.sync_block.__init__(
            self,
            name="MobRFFI Fingerprint Extractor",
            in_sig=[(np.complex64, int(vectorLength))],
            out_sig=[(np.float32, int(embeddingLength))]
        )

        # Parameters
        self.vectorLength = int(vectorLength)
        self.embeddingLength = int(embeddingLength)
        self.specWidth = int(specWidth)
        self.modelPath = str(modelPath)
        self.computeMode = str(computeMode).upper().strip()

        # Logging
        self._log = logging.getLogger("mobrffi.extractor")
        if not self._log.handlers:
            h = logging.StreamHandler()
            h.setFormatter(logging.Formatter("[%(name)s] %(levelname)s: %(message)s"))
            self._log.addHandler(h)
        self._log.setLevel(logging.INFO)

        # Validation
        if self.vectorLength < 320: raise ValueError("vectorLength must be at least 320 IQ samples long.")
        if self.embeddingLength < 512: raise ValueError("embeddingLength must be at least 512 values long.")
        if self.specWidth <= 0: raise ValueError("specWidth has to be a positive integer.")
        if not os.path.isfile(self.modelPath): raise FileNotFoundError(f"ONNX model isn't found here: {self.modelPath}")

        # ONNX runtime session
        providers = ["CPUExecutionProvider"]
        if self.computeMode == "GPU" and "CUDAExecutionProvider" in ort.get_available_providers():
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
            self._log.info("Using GPU provider for ONNX Runtime.")
        else:
            self._log.info("Using CPU provider for ONNX Runtime.")
        self._session = ort.InferenceSession(self.modelPath, providers=providers)
        self._in_name = self._session.get_inputs()[0].name
        self._out_name = self._session.get_outputs()[0].name

        # Initialize channel-independent spectrogram generator
        self._ch_ind_spec_generator = ChannelIndSpectrogram()

    def work(self, input_items, output_items):
        in_mat = input_items[0]
        out_mat = output_items[0]

        if in_mat.shape[1] != self.vectorLength:
            self._log.error(f"Incorrect input vector: received {in_mat.shape[1]}, expected {self.vectorLength}.")
            return 0
        
        produced = 0
        for i in range(in_mat.shape[0]):
            iq = in_mat[i].reshape(1, -1).astype(np.complex64)   

            try:
                spec = self._ch_ind_spec_generator.channel_ind_spectrogram(data=iq, row=self.specWidth, enable_ind=True)
                spec = spec.astype(np.float32, copy=False)
            except Exception as e:
                self._log.error(f"Failed to produce a channel-independent spectrogram: {e}")
                continue

            try:
                out = self._session.run([self._out_name], {self._in_name: spec})[0]
                embedding = np.asarray(out).reshape(-1)
            except Exception as e:
                self._log.error(f"ONNX inference failed: {e}")
                continue

            if embedding.shape[0] != self.embeddingLength:
                self._log.error(f"Model output has incorrect size: {embedding.shape}")
            else:
                out_mat[i, :] = embedding.astype(np.float32)
            
            produced += 1

        return produced
