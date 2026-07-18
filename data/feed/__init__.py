from data.feed.spot.binance import Binance


from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from data import MetaData



class MetaDataLoader:
    def __init__(self, meta: "MetaData"):
        self._meta = meta
        self.spot_feed = Binance(meta)
    

