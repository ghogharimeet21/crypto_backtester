import requests
import json

url = "https://api.binance.com/api/v3/exchangeInfo"
info = requests.get(url).json()

clean_data = [
    {
        "symbol": s["symbol"],
        "base": s["baseAsset"],
        "quote": s["quoteAsset"],
        "status": s["status"]
    }
    for s in info["symbols"]
]

with open("symbols.json", "w") as f:
    json.dump(clean_data, f, indent=4)