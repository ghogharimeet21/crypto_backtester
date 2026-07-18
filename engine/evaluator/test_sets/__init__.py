from data import meta_data
from data.indicators.enums import SOURCE





def execute():






    meta_data.indicators.compute_ema(
        "BTCUSDT", 60,  20260101, 20260103, SOURCE.CLOSE, 3
    )

    ...