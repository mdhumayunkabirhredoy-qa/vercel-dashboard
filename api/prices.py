"""
/api/prices — fetch real-time prices from Binance
"""
import json
import aiohttp
import asyncio
from http.server import BaseHTTPRequestHandler

BINANCE_FUTURES = "https://fapi.binance.com"
BINANCE_SPOT = "https://api.binance.com"

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT", "BNBUSDT",
           "WIFUSDT", "PEPEUSDT", "ARBUSDT", "OPUSDT", "AVAXUSDT", "LINKUSDT",
           "ADAUSDT", "NEARUSDT", "DOTUSDT", "SUIUSDT", "TONUSDT", "FETUSDT"]

async def fetch_prices():
    prices = {}
    try:
        async with aiohttp.ClientSession() as session:
            # Try futures first
            try:
                async with session.get(
                    f"{BINANCE_FUTURES}/fapi/v1/ticker/price",
                    timeout=aiohttp.ClientTimeout(total=8)
                ) as resp:
                    text = await resp.text()
                    data = json.loads(text)
                    if isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict):
                                sym = item.get("symbol", "")
                                if sym in SYMBOLS:
                                    prices[sym] = float(item.get("price", 0))
            except Exception:
                pass

            # Fallback to spot if futures empty
            if not prices:
                try:
                    async with session.get(
                        f"{BINANCE_SPOT}/api/v3/ticker/price",
                        timeout=aiohttp.ClientTimeout(total=8)
                    ) as resp:
                        text = await resp.text()
                        data = json.loads(text)
                        if isinstance(data, list):
                            for item in data:
                                if isinstance(item, dict):
                                    sym = item.get("symbol", "")
                                    if sym in SYMBOLS:
                                        prices[sym] = float(item.get("price", 0))
                except Exception:
                    pass

            # Add 24h change data
            if prices:
                try:
                    async with session.get(
                        f"{BINANCE_FUTURES}/fapi/v1/ticker/24hr",
                        timeout=aiohttp.ClientTimeout(total=8)
                    ) as resp:
                        text = await resp.text()
                        data = json.loads(text)
                        if isinstance(data, list):
                            for item in data:
                                if isinstance(item, dict):
                                    sym = item.get("symbol", "")
                                    if sym in prices:
                                        prices[sym] = {
                                            "price": prices[sym],
                                            "change": float(item.get("priceChangePercent", 0)),
                                            "volume": float(item.get("quoteVolume", 0)),
                                            "high": float(item.get("highPrice", 0)),
                                            "low": float(item.get("lowPrice", 0)),
                                        }
                except Exception:
                    # Keep simple prices if 24hr fails
                    prices = {k: {"price": v, "change": 0, "volume": 0} if isinstance(v, (int, float)) else v
                              for k, v in prices.items()}

    except Exception as e:
        prices["_error"] = str(e)
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
