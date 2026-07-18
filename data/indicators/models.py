from data.indicators.enums import SOURCE


class SmaSetting:
    def __init__(self, sma_lengths: list = [14], source: SOURCE = SOURCE.CLOSE):
        self.sma_lengths = sma_lengths
        self.source = source

    def __str__(self):
        return f"EmaSetting(length={self.sma_lengths})"




class EmaSetting:
    def __init__(self, ema_lengths: list = [14], source: SOURCE = SOURCE.CLOSE):
        self.ema_lengths = ema_lengths
        self.source = source

    def __str__(self):
        return f"EmaSetting(length={self.ema_lengths}  source={self.source})"

















class IndicatorSettings:
    def __init__(
        self,
        sma_setting: SmaSetting = None,
        ema_setting: EmaSetting = None,
    ):
        self.sma_setting: SmaSetting = sma_setting
        self.ema_setting: EmaSetting = ema_setting




