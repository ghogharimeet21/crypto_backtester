from .models import SampleStrategy
from data.local import meta_data
import logging


logger = logging.getLogger(__name__)




def excecute(strategy: SampleStrategy):

    logger.info("resamplling...")

    meta_data.resample_quotes(strategy.symbol, strategy.entry_date, strategy.exit_date, strategy.timeframe)

    logger.info("data resampled.")

    # data = meta_data.resampled_quotes[strategy.symbol]

    # print(data)

    print(strategy.timeframe)

    quote = meta_data.get_quote(strategy.symbol, strategy.entry_date, strategy.entry_time - 60, strategy.timeframe)
    

    print(quote)