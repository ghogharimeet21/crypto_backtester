from .models import SampleStrategy
from data.local import meta_data
import logging
from data.utils import seconds_to_hms

logger = logging.getLogger(__name__)




def excecute(strategy: SampleStrategy):



    quotes = meta_data.get_quotes_series(
        strategy.symbol,
        strategy.date_span[0],
        strategy.date_span[-1]
    )

    for quote in quotes:
        ...