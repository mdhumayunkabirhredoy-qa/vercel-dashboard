"""
/api/prices — fetch real-time crypto prices
Uses CoinGecko (free, no key) + Binance as fallback
Sync version for Vercel compatibility
"""
import json
import urllib.request
from http.server import BaseHTTPRequestHandler

COINGECKO = "https://api.coingecko.com/api/v3"
COIN_IDS = "bitcoin,ethereum,solana,dogecoin,ripple,binancecoin,cardano,avalanche-2,chainlink,polkadot,near,optimism,arbitrum,sui,toncoin,pepe,dogwifcoin"
SYMBOL_MAP = {
    "bitcoin": "BTCUSDT", "ethereum": "ETHUSDT", "solana": "SOLUSDT",
    "dogecoin": "DOGEUSDT", "ripple": "XRPUSDT", "binancecoin": "BNBUSDT",
    "cardano": "ADAUSDT", "avalanche-2": "AVAXUSDT", "chainlink": "LINKUSDT",
    "polkadot": "DOTUSDT", "near": "NEARUSDT", "optimism": "OPUSDT",
    "arbitrum": "ARBUSDT", "sui": "SUIUSDT", "toncoin": "TONUSDT",
    "pepe": "PEPEUSDT", "dogwifcoin": "WIFUSDT",
}


def fetch_prices():
    prices = {}

    # CoinGecko
    try:
        url = f"{COINGECKO}/coins/markets?vs_currency=usd&ids={COIN_IDS}&order=market_cap_desc&sparkline=false&price_change_percentage=24h"
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "CryptoCommandCenter/1.0"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode())
            if isinstance(data, list):
                for coin in data:
                    cid = coin.get("id", "")
                    sym = SYMBOL_MAP.get(cid)
                    if sym:
                        prices[sym] = {
                            "price": coin.get("current_price", 0),
                            "change": round(coin.get("price_change_percentage_24h", 0) or 0, 2),
                            "volume": coin.get("total_volume", 0),
                            "high": coin.get("high_24h", 0),
                            "low": coin.get("low_24h", 0),
                            "market_cap": coin.get("market_cap", 0),
                            "name": coin.get("name", ""),
                        }
    except Exception as e:
        prices["_error_cg"] = str(e)

    # Fallback: Binance
    if len([k for k in prices if not k.startswith("_")]) < 3:
        try:
            req = urllib.request.Request("https://api.binance.com/api/v3/ticker/24hr",
                                         headers={"User-Agent": "CryptoCommandCenter/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                syms = list(SYMBOL_MAP.values())
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            sym = item.get("symbol", "")
                            if sym in syms:
                                prices[sym] = {
                                    "price": float(item.get("lastPrice", 0)),
                                    "change": float(item.get("priceChangePercent", 0)),
                                    "volume": float(item.get("quoteVolume", 0)),
                                    "high": float(item.get("highPrice", 0)),
                                    "low": float(item.get("lowPrice", 0)),
                                }
        except Exception as e:
            prices["_error_bn"] = str(e)

    return prices


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        prices = fetch_prices()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "s-maxage=3, stale-while-revalidate=10")
        self.end_headers()
        self.wfile.write(json.dumps(prices).encode())
