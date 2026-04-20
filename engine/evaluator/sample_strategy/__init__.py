from .models import SampleStrategy
from data.storage import meta_data







def excecute(strategy: SampleStrategy):


    quote = meta_data.get_quote(strategy.symbol, strategy.entry_date, strategy.entry_time)
    

    print(quote)
    
    ...