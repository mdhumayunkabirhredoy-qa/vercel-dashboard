"""
/api/prices — fetch real-time prices from Binance
"""
import json
import aiohttp
import asyncio
from http.server import BaseHTTPRequestHandler

BINANCE_FUTURES = "https://fapi.binance.com"

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT", "BNBUSDT",
           "WIFUSDT", "PEPEUSDT", "ARBUSDT", "OPUSDT", "AVAXUSDT", "LINKUSDT"]

async def fetch_prices():
    prices = {}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{BINANCE_FUTURES}/fapi/v1/ticker/price",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                data = await resp.json()
                for item in data:
                    sym = item.get("symbol", "")
                    if sym in SYMBOLS:
                        prices[sym] = float(item["price"])
    except Exception as e:
        prices["error"] = str(e)
    return prices

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        prices = asyncio.run(fetch_prices())
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "s-maxage=2, stale-while-revalidate=5")
        self.end_headers()
        self.wfile.write(json.dumps(prices).encode())
