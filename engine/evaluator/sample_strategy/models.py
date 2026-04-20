from data.utils import hms_to_seconds




class SampleStrategy:
    def __init__(self, request_json: dict):
        
        self.symbol: str = request_json.get("symbol")
        self.timeframe: int = request_json.get("timeframe")
        
        self.entry_date: int = request_json.get("entry_date")
        self.entry_time: int = request_json.get("entry_time")
        self.exit_date: int = request_json.get("exit_date")
        self.exit_time: int = request_json.get("exit_time")

        if isinstance(self.entry_time, str) and self.entry_time.__contains__(":"):
            self.entry_time = hms_to_seconds(self.entry_time)
        if isinstance(self.exit_time, str) and self.exit_time.__contains__(":"):
            self.exit_time = hms_to_seconds(self.exit_time)
        
        


        
