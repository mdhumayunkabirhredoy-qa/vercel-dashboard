"""
/api/liquidations — fetch recent liquidations from Binance
"""
import json
import aiohttp
import asyncio
from http.server import BaseHTTPRequestHandler

# We'll use Binance forced orders endpoint
# Note: Binance doesn't have a REST endpoint for liq history,
# so we'll fetch aggregated trade data as proxy
BINANCE_FUTURES = "https://fapi.binance.com"

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT", "BNBUSDT"]

async def fetch_liquidations():
    """Fetch open interest and top trader ratio as liquidation proxy data"""
    result = {
        "liquidations": [],  # No REST API for real-time liqs (need WebSocket)
        "open_interest": {},
        "long_short_ratio": {},
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            for sym in SYMBOLS:
                # Open Interest
                try:
                    async with session.get(
                        f"{BINANCE_FUTURES}/fapi/v1/openInterest",
                        params={"symbol": sym},
                        timeout=aiohttp.ClientTimeout(total=8)
                    ) as resp:
                        data = await resp.json()
                        result["open_interest"][sym] = float(data.get("openInterest", 0))
                except Exception:
                    pass

                # Long/Short ratio
                try:
                    async with session.get(
                        f"{BINANCE_FUTURES}/futures/data/topLongShortPositionRatio",
                        params={"symbol": sym, "period": "5m", "limit": 1},
                        timeout=aiohttp.ClientTimeout(total=8)
                    ) as resp:
                        data = await resp.json()
                        if data:
                            result["long_short_ratio"][sym] = {
                                "long": float(data[0].get("longAccount", 0)),
                                "short": float(data[0].get("shortAccount", 0)),
                                "ratio": float(data[0].get("longShortRatio", 1)),
                            }
                except Exception:
                    pass
    except Exception:
        pass
    
    return result


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        data = asyncio.run(fetch_liquidations())
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "s-maxage=5, stale-while-revalidate=10")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
