"""
/api/analyze — AI market analysis via Anthropic Claude
"""
import json
import os
import aiohttp
import asyncio
from http.server import BaseHTTPRequestHandler
from datetime import datetime

BINANCE_FUTURES = "https://fapi.binance.com"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT", "BNBUSDT"]


async def gather_data():
    """Gather market data for AI analysis"""
    prices = {}
    funding = {}
    oi = {}
    ls_ratio = {}

    async with aiohttp.ClientSession() as session:
        # Prices
        try:
            async with session.get(f"{BINANCE_FUTURES}/fapi/v1/ticker/price",
                                   timeout=aiohttp.ClientTimeout(total=10)) as resp:
                for item in await resp.json():
                    sym = item.get("symbol", "")
                    if sym in SYMBOLS:
                        prices[sym] = float(item["price"])
        except Exception:
            pass

        # Funding
        try:
            async with session.get(f"{BINANCE_FUTURES}/fapi/v1/premiumIndex",
                                   timeout=aiohttp.ClientTimeout(total=10)) as resp:
                for item in await resp.json():
                    sym = item.get("symbol", "")
                    if sym in SYMBOLS:
                        funding[sym] = {
                            "rate": float(item.get("lastFundingRate", 0)),
                            "mark": float(item.get("markPrice", 0)),
                        }
        except Exception:
            pass

        # Open Interest + LS ratio
        for sym in SYMBOLS[:3]:
            try:
                async with session.get(f"{BINANCE_FUTURES}/fapi/v1/openInterest",
                                       params={"symbol": sym},
                                       timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    data = await resp.json()
                    oi[sym] = float(data.get("openInterest", 0))
            except Exception:
                pass
            try:
                async with session.get(
                    f"{BINANCE_FUTURES}/futures/data/topLongShortPositionRatio",
                    params={"symbol": sym, "period": "5m", "limit": 1},
                    timeout=aiohttp.ClientTimeout(total=8)
                ) as resp:
                    data = await resp.json()
                    if data:
                        ls_ratio[sym] = float(data[0].get("longShortRatio", 1))
            except Exception:
                pass

    return {"prices": prices, "funding": funding, "open_interest": oi, "ls_ratio": ls_ratio}


async def ai_analyze(market_data):
    """Send data to Claude for analysis"""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")

    if not api_key:
        return {"error": "ANTHROPIC_API_KEY not set"}

    prompt = f"""You are an elite crypto analyst. Analyze this real market data.
Current time (UTC): {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}

PRICES: {json.dumps(market_data['prices'], indent=2)}
FUNDING RATES: {json.dumps(market_data['funding'], indent=2)}
OPEN INTEREST: {json.dumps(market_data['open_interest'], indent=2)}
LONG/SHORT RATIO: {json.dumps(market_data['ls_ratio'], indent=2)}

Respond in JSON:
{{
    "market_sentiment": "bullish" | "bearish" | "neutral",
    "sentiment_score": -100 to 100,
    "confidence": 0 to 100,
    "trading_signals": [
        {{
            "symbol": "BTC/ETH/SOL",
            "action": "LONG" | "SHORT" | "WAIT",
            "confidence": 0-100,
            "entry": price,
            "stop_loss": price,
            "take_profit": price,
            "risk_reward": float,
            "reasoning": "why"
        }}
    ],
    "funding_recommendations": [
        {{"symbol": "...", "strategy": "...", "expected_daily_return": "..."}}
    ],
    "risk_warnings": ["..."],
    "summary": "3-4 sentence market overview"
}}"""

    try:
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
        body = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 3000,
            "messages": [{"role": "user", "content": prompt}],
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{base_url}/v1/messages",
                headers=headers,
                json=body,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                data = await resp.json()
                text = data.get("content", [{}])[0].get("text", "")
                start = text.find('{')
                end = text.rfind('}') + 1
                if start >= 0 and end > start:
                    return json.loads(text[start:end])
                return {"error": "Could not parse AI response", "raw": text[:500]}
    except Exception as e:
        return {"error": str(e)}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        market_data = asyncio.run(gather_data())
        analysis = asyncio.run(ai_analyze(market_data))
        analysis["market_data"] = market_data

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "s-maxage=120, stale-while-revalidate=300")
        self.end_headers()
        self.wfile.write(json.dumps(analysis).encode())
