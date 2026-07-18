from typing import Dict, List
from data.models import Quote
from data.indicators import Indicator
from logging import getLogger
from data.utils import MetaUtils
from data.feed import MetaDataLoader

logger = getLogger(__name__)


class MetaData:
    def __init__(self):
        # ── Spot ─────────────────────────────────────────────────────────────
        # symbol -> timeframe -> date -> time -> Quote
        self.quotes: Dict[str, Dict[int, Dict[int, Dict[int, Quote]]]] = {}

        self.indicators: Indicator = Indicator(self)

        self.data_loader = MetaDataLoader(self)

        self.meta_utils = MetaUtils(self)


meta_data = MetaData()
