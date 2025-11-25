import math
import logging
import numpy as np
from gnuradio import gr
from PyQt5 import QtCore, QtGui, QtWidgets as QtW

GREEN = "#35c46a"
BLACK = "#000000"
GRAY  = "#6b6b6b"
TXT   = "#f0f0f0"

class _Tile(QtW.QFrame):
    def __init__(self, index):
        super().__init__()
        self.index = index
        self._assigned = False

        self.setFrameStyle(QtW.QFrame.Panel | QtW.QFrame.Raised)
        self.setLineWidth(2)
        self.setAutoFillBackground(True)

        self.title = QtW.QLabel("—")
        self.title.setAlignment(QtCore.Qt.AlignCenter)
        f = self.title.font()
        f.setPointSize(14)
        f.setBold(True)
        self.title.setFont(f)

        lay = QtW.QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(self.title)

        self.set_unassigned()

    def set_unassigned(self):
        self._assigned = False
        self.title.setText("—")
        self._set_colors(GRAY)

    def assign_label(self, label: int):
        self._assigned = True
        self.title.setText(str(label))
        self._set_colors(BLACK)

    def set_active(self, active: bool):
        if not self._assigned:
            self._set_colors(GRAY)
        else:
            self._set_colors(GREEN if active else BLACK)

    def _set_colors(self, bg):
        pal = self.palette()
        pal.setColor(self.backgroundRole(), QtGui.QColor(bg))
        pal.setColor(self.foregroundRole(), QtGui.QColor(TXT))
        self.setPalette(pal)
        self.title.setStyleSheet(f"color: {TXT};")

class LabelDemoWidget(QtW.QWidget):
    """Grid of tiles that lights up the currently active label."""
    signal_set_active = QtCore.pyqtSignal(int)
    signal_clear_all  = QtCore.pyqtSignal()

    def __init__(self, max_labels: int):
        super().__init__()
        self.max_labels = int(max_labels)
        self.label_to_tile = {}   # label -> tile index
        self.tiles = []

        # Create a frame to hold everything and give it a visible border
        main_frame = QtW.QFrame()
        main_frame.setFrameStyle(QtW.QFrame.Box | QtW.QFrame.Raised)
        main_frame.setLineWidth(2)
        
        # Create grid for tiles
        cols = max(1, int(math.ceil(math.sqrt(self.max_labels))))
        grid = QtW.QGridLayout()
        grid.setSpacing(8)
        
        for i in range(self.max_labels):
            t = _Tile(i)
            self.tiles.append(t)
            r, c = divmod(i, cols)
            grid.addWidget(t, r, c)
        
        # Assemble the frame layout
        frame_layout = QtW.QVBoxLayout(main_frame)
        frame_layout.addLayout(grid)
        frame_layout.setContentsMargins(10, 10, 10, 10)
        
        # Main widget layout
        main_layout = QtW.QVBoxLayout(self)
        main_layout.addWidget(main_frame)
        main_layout.setContentsMargins(5, 5, 5, 5)
        
        self.setMinimumSize(320, 240)
        self.resize(400, 300)  # Set a reasonable default size

        self.signal_set_active.connect(self._on_set_active)
        self.signal_clear_all.connect(self._on_clear_all)

    def _first_free_tile(self):
        for i, t in enumerate(self.tiles):
            if not t._assigned:
                return i
        return None

    @QtCore.pyqtSlot()
    def _on_clear_all(self):
        self.label_to_tile.clear()
        for t in self.tiles:
            t.set_unassigned()

    @QtCore.pyqtSlot(int)
    def _on_set_active(self, label: int):
        if label not in self.label_to_tile:
            idx = self._first_free_tile()
            if idx is None:
                return
            self.label_to_tile[label] = idx
            self.tiles[idx].assign_label(label)

        active_idx = self.label_to_tile[label]
        for i, t in enumerate(self.tiles):
            t.set_active(i == active_idx)

class label_demo(gr.sync_block):
    """
    Qt GUI block for MobRFFI label demonstration.
    Input : stream of int32 labels
            >=0 -> activate/show that label
            -1  -> clear all tiles (optional convenience)
    Param : maxLabelCount (int)
    GUI   : grid of tiles; first time a label is seen it is assigned to the first free tile.
    """
    def __init__(self, maxLabelCount=8, parent=None):
        super().__init__(
            name="MobRFFI Label Demo",
            in_sig=[np.int32],  
            out_sig=None,
        )
        self.maxLabelCount = int(maxLabelCount)
        
        self._log = logging.getLogger("mobrffi.label_demo")
        if not self._log.handlers:
            h = logging.StreamHandler()
            h.setFormatter(logging.Formatter("[%(name)s] %(levelname)s: %(message)s"))
            self._log.addHandler(h)
        self._log.setLevel(logging.DEBUG)  
        
        self._log.info(f"Initializing label_demo with maxLabelCount={maxLabelCount}")

        if self.maxLabelCount <= 0:
            raise ValueError("maxLabelCount must be > 0")

        # Create the widget
        self._widget = LabelDemoWidget(self.maxLabelCount)
        self._log.info(f"Widget created: {self._widget}")
        
        self._last_label = None  

    def work(self, input_items, output_items):
        labels = input_items[0]
        
        if len(labels) > 0:
            self._log.debug(f"Processing {len(labels)} labels: {labels[:min(10, len(labels))]}")

        if labels.ndim > 1:
            labels = labels.reshape(-1)

        for label in labels:
            try:
                iv = int(label)
            except Exception:
                continue

            if iv == -1:
                continue

            if iv >= 0 and iv != self._last_label:
                self._log.info(f"Activating label {iv}")
                self._widget.signal_set_active.emit(iv)
                self._last_label = iv

        return len(labels)

    def qwidget(self):
        """Return the Qt widget for GNU Radio to embed"""
        self._log.info(f"qwidget() called, returning {self._widget}")
        return self._widget

    def pyqwidget(self):
        """Alternative method name that some GNU Radio versions use"""
        self._log.info(f"pyqwidget() called, returning {self._widget}")
        return self._widget
    
    def set_gui_hint(self, hint=""):
        """Handle GUI positioning hint from GNU Radio"""
        self._log.info(f"set_gui_hint() called with hint: '{hint}'")
        self._gui_hint = hint