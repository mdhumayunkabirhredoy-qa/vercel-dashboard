"""
/api/analyze — AI market analysis via Anthropic Claude, sync version
"""
import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler
from datetime import datetime


def gather_data():
    prices = {}
    funding = {}

    # Prices from CoinGecko
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids=bitcoin,ethereum,solana,dogecoin,ripple,binancecoin&order=market_cap_desc&sparkline=false&price_change_percentage=24h"
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "CCC/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            sym_map = {"bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL",
                       "dogecoin": "DOGE", "ripple": "XRP", "binancecoin": "BNB"}
            for coin in data:
                sym = sym_map.get(coin.get("id", ""))
                if sym:
                    prices[sym] = {
                        "price": coin.get("current_price", 0),
                        "change_24h": round(coin.get("price_change_percentage_24h", 0) or 0, 2),
                        "volume": coin.get("total_volume", 0),
                        "market_cap": coin.get("market_cap", 0),
                    }
    except Exception:
        pass

    # Funding from Binance
    try:
        req = urllib.request.Request("https://fapi.binance.com/fapi/v1/premiumIndex",
                                     headers={"User-Agent": "CCC/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            target = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
            for item in data:
                sym = item.get("symbol", "")
                if sym in target:
                    funding[sym] = {
                        "rate": float(item.get("lastFundingRate", 0)),
                        "mark": float(item.get("markPrice", 0)),
                    }
    except Exception:
        pass

    return {"prices": prices, "funding": funding}


def ai_analyze(market_data):
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")

    if not api_key:
        return {"error": "ANTHROPIC_API_KEY not configured", "market_data": market_data}

    prompt = f"""You are an elite crypto market analyst. Analyze this real-time data.
Current time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}

MARKET DATA:
{json.dumps(market_data, indent=2)}

Respond ONLY with valid JSON (no markdown):
{{
    "market_sentiment": "bullish" or "bearish" or "neutral",
    "sentiment_score": -100 to 100,
    "confidence": 0 to 100,
    "trading_signals": [
        {{
            "symbol": "BTC",
            "action": "LONG" or "SHORT" or "WAIT",
            "confidence": 0-100,
            "entry": price_number,
            "stop_loss": price_number,
            "take_profit": price_number,
            "risk_reward": float,
            "reasoning": "brief reason"
        }}
    ],
    "funding_recommendations": [
        {{"symbol": "...", "strategy": "...", "expected_daily_return": "..."}}
    ],
    "risk_warnings": ["warning1", "warning2"],
    "summary": "3-4 sentence market overview in Russian"
}}"""

    try:
        body = json.dumps({
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 2500,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()

        req = urllib.request.Request(
            f"{base_url}/v1/messages",
            data=body,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=55) as resp:
            data = json.loads(resp.read().decode())
            text = data.get("content", [{}])[0].get("text", "")
            # Extract JSON from response
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
            return {"error": "Could not parse AI response", "raw": text[:300]}

    except Exception as e:
        return {"error": str(e)}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        market_data = gather_data()
        analysis = ai_analyze(market_data)
        analysis["_market_data"] = market_data

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "s-maxage=120, stale-while-revalidate=300")
        self.end_headers()
        self.wfile.write(json.dumps(analysis).encode())
