import numpy as np








class Quote:
    def __init__(self, _open, _high, _low, _close, _volume):
        self._open, self._high, self._low, self._close, self._volume = (
            _open, _high, _low, _close, _volume
        )
        self.nparr = np.array([_open, _high, _low, _close, _volume])
    
    def __str__(self):
        return f"open={self._open}, high={self._high}, low={self._low}, close={self._close}"