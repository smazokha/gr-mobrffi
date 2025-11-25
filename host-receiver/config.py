# GLOBAL CONFIGURATIONS
DEFAULT_PORT = 9000
DEFAULT_MODE = "CAPTURE" # INDIVIDUAL | COMBINED | CAPTURE
EXPECTED_DEVICES = 2 # for COMBINED
REFRESH_EVERY = 0.5 # seconds between screen updates (UI)
SLIDING_WINDOW = 10 # for INDIVIDUAL/COMBINED rate calc
BUF_SIZE = 65_535 # max UDP payload

# CAPTURE MODE settings
CAPTURE_FRAMES_TARGET = 1000 # stop-and-save after this many frames
EXIT_AFTER_SAVE = True # exit once H5 is written
STRICT_IQ_LEN = False # if True, drop frames whose M != fixed_M
IQ_LEN_OVERRIDE_SAMPLES = None # e.g, 128 to force M; else infer from first frame

# IQ decode: store as complex64 (I+1jQ) or raw int16 pairs
IQ_AS_COMPLEX64 = False # set to False for (N,M,2) int16 layout
IQ_ENABLE_TRIMMING = True
IQ_TRIM_START = 400
IQ_TRIM_LENGTH = 320

# Radiotap RSSI sentinel when missing
RSSI_DBM_MISSING = -128 # i8 sentinel