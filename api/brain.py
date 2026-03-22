import json
import urllib.request
import urllib.parse
import time
import os
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler
import hashlib

# ============================================================================
# CACHE SYSTEM (5-minute TTL)
# ============================================================================

CACHE = {}
CACHE_TTL = 300  # 5 minutes

def cache_get(key):
    """Get cached value if still valid"""
    if key in CACHE:
        value, timestamp = CACHE[key]
        if time.time() - timestamp < CACHE_TTL:
            return value
    return None

def cache_set(key, value):
    """Set cache with timestamp"""
    CACHE[key] = (value, time.time())

# ============================================================================
# DATA FETCHERS (All free APIs, no auth required except Anthropic)
# ============================================================================

def fetch_coingecko_prices():
    """Fetch top 30 coins from CoinGecko"""
    try:
        top_coins = [
            "bitcoin", "ethereum", "solana", "cardano", "polkadot",
            "dogecoin", "ripple", "litecoin", "avalanche-2", "polygon",
            "uniswap", "link", "chainlink", "aave", "arbitrum",
            "optimism", "near", "aptos", "sui", "helium",
            "bonk", "shiba-inu", "cosmos", "tron", "monero",
            "stellar", "filecoin", "iota", "internet-computer", "fetch-ai"
        ]
        
        url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids=" + \
              ",".join(top_coins) + "&order=market_cap_desc&per_page=30&sparkline=false&price_change_percentage=24h"
        
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            return {
                "coins": data,
                "count": len(data),
                "timestamp": datetime.utcnow().isoformat()
            }
    except Exception as e:
        return {"error": str(e), "coins": []}

def fetch_coingecko_global():
    """Fetch global market data (BTC dominance, market cap, etc)"""
    try:
        url = "https://api.coingecko.com/api/v3/global"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            return {
                "btc_dominance": data["data"]["btc_market_cap_percentage"],
                "total_market_cap": data["data"]["total_market_cap"]["usd"],
                "24h_volume": data["data"]["total_volume"]["usd"],
                "ethereum_dominance": data["data"]["eth_market_cap_percentage"]
            }
    except Exception as e:
        return {"error": str(e)}

def fetch_fear_greed():
    """Fetch Fear & Greed Index from alternative.me"""
    try:
        url = "https://api.alternative.me/fng/?limit=1"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            if data["data"]:
                return {
                    "value": int(data["data"][0]["value"]),
                    "classification": data["data"][0]["value_classification"],
                    "timestamp": data["data"][0]["timestamp"]
                }
            return {"value": 50, "classification": "Neutral"}
    except Exception as e:
        return {"error": str(e), "value": 50}

def fetch_binance_funding():
    """Fetch Binance funding rates for top perpetual futures"""
    try:
        url = "https://fapi.binance.com/fapi/v1/premiumIndex"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            # Filter top 20 by volume (represented by mark price)
            sorted_data = sorted(data, key=lambda x: float(x.get("markPrice", 0)), reverse=True)[:20]
            return {
                "exchange": "Binance",
                "pairs": [
                    {
                        "symbol": item["symbol"],
                        "funding_rate": float(item["lastFundingRate"]),
                        "mark_price": float(item["markPrice"])
                    } for item in sorted_data
                ]
            }
    except Exception as e:
        return {"error": str(e), "pairs": []}

def fetch_bybit_funding():
    """Fetch Bybit funding rates"""
    try:
        url = "https://api.bybit.com/v5/market/tickers?category=linear&limit=50"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            if data["result"]["list"]:
                pairs = []
                for item in data["result"]["list"][:20]:
                    if "fundingRate" in item:
                        pairs.append({
                            "symbol": item["symbol"],
                            "funding_rate": float(item.get("fundingRate", 0)),
                            "last_price": float(item.get("lastPrice", 0))
                        })
                return {
                    "exchange": "Bybit",
                    "pairs": pairs
                }
            return {"exchange": "Bybit", "pairs": []}
    except Exception as e:
        return {"error": str(e), "pairs": []}

def fetch_polymarket():
    """Fetch Polymarket prediction markets"""
    try:
        url = "https://gamma-api.polymarket.com/markets?limit=20&active=true&order=volume&ascending=false&closed=false"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            return {
                "markets": data[:10] if isinstance(data, list) else [],
                "count": len(data) if isinstance(data, list) else 0
            }
    except Exception as e:
        return {"error": str(e), "markets": []}

def scan_market_data():
    """Scan all market data and return comprehensive market analysis"""
    # Check cache first
    cached = cache_get("market_scan")
    if cached:
        return cached
    
    print("[BRAIN] Scanning market data...", flush=True)
    
    market_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "prices": fetch_coingecko_prices(),
        "global": fetch_coingecko_global(),
        "fear_greed": fetch_fear_greed(),
        "binance_funding": fetch_binance_funding(),
        "bybit_funding": fetch_bybit_funding(),
        "polymarket": fetch_polymarket()
    }
    
    cache_set("market_scan", market_data)
    return market_data

# ============================================================================
# AI ANALYSIS ENGINE (Claude Opus 4.6 via Anthropic API)
# ============================================================================

def build_ai_prompt(market_data):
    """Build comprehensive prompt for AI analysis in Russian"""
    
    # Format price data
    price_summary = "Цены топ-10 монет:\n"
    if market_data.get("prices", {}).get("coins"):
        for coin in market_data["prices"]["coins"][:10]:
            price_summary += f"- {coin['name']} ({coin['symbol'].upper()}): ${coin['current_price']:.2f} (24h: {coin['price_change_percentage_24h']:.2f}%)\n"
    
    # Format funding rates
    binance_funding = "Binance Funding (топ-5 по ставке):\n"
    if market_data.get("binance_funding", {}).get("pairs"):
        for pair in sorted(market_data["binance_funding"]["pairs"], key=lambda x: abs(x["funding_rate"]), reverse=True)[:5]:
            rate = pair["funding_rate"] * 100
            binance_funding += f"- {pair['symbol']}: {rate:.4f}% funding\n"
    
    bybit_funding = "Bybit Funding (топ-5 по ставке):\n"
    if market_data.get("bybit_funding", {}).get("pairs"):
        for pair in sorted(market_data["bybit_funding"]["pairs"], key=lambda x: abs(x["funding_rate"]), reverse=True)[:5]:
            rate = pair["funding_rate"] * 100
            bybit_funding += f"- {pair['symbol']}: {rate:.4f}% funding\n"
    
    global_data = market_data.get("global", {})
    btc_dom = global_data.get("btc_dominance", 0)
    market_cap = global_data.get("total_market_cap", 0)
    fear_greed = market_data.get("fear_greed", {}).get("value", 50)
    
    prompt = f"""Ты лучший квант-трейдер в мире, используешь Claude Opus 4.6. Ты анализируешь рынок крипто и находишь ПРИБЫЛЬНЫЕ стратегии.

ТЕКУЩИЕ ДАННЫЕ РЫНКА:
═══════════════════════

{price_summary}

{binance_funding}

{bybit_funding}

ГЛОБАЛЬНЫЕ МЕТРИКИ:
- BTC доминанс: {btc_dom:.2f}%
- Общая капитализация: ${market_cap:,.0f}
- Fear & Greed Index: {fear_greed}/100 ("{market_data.get("fear_greed", {}).get("classification", "Neutral")}")

ТВОЯ ЗАДАЧА (НАЙТИ ВСЕ ВОЗМОЖНОСТИ ЗАРАБОТКА):
═════════════════════════════════════════════════

1. FUNDING RATE ARBITRAGE
   - Найди высокие funding rates на Binance (шортирование)
   - Найди низкие funding rates на Bybit (лонгирование)
   - Рассчитай дневной доход от арбитража
   
2. CROSS-EXCHANGE SPREADS
   - Ищи монеты, где цена различается между биржами
   - Цель: куплю дешево, продам дорого

3. MEMECOIN PUMPS (РАННИЕ СИГНАЛЫ)
   - Какие монеты с малой капитализацией начинают расти?
   - Есть ли признаки whale накопления?

4. BASIS TRADING (SPOT vs PERP)
   - Ищи разницу между спотом и фьючерсами
   - Рассчитай сейф-базис для профита

5. LIQUIDATION CASCADES
   - На каких уровнях много ликвидаций?
   - Можно ли заработать на этом?

6. WHALE PATTERNS
   - Какие монеты покупают киты?
   - Какой объем на сбыт грядет?

ТРЕБОВАНИЯ К ОТВЕТУ (СТРУКТУРИРОВАННЫЙ JSON):
════════════════════════════════════════════════

Вернись с JSON в формате (ТОЧНО ЭТОТ ФОРМАТ):
{{
  "timestamp": "ISO datetime now",
  "market_overview": {{
    "sentiment": "bullish|bearish|neutral",
    "fear_greed": {fear_greed},
    "btc_dominance": {btc_dom:.1f},
    "total_market_cap": "{market_cap:,.0f}",
    "risk_level": "low|medium|high"
  }},
  "opportunities": [
    {{
      "type": "funding_arb|spread_arb|memecoin|prediction|basis|grid|dca|whale_copy",
      "symbol": "SYMBOL",
      "action": "краткое описание действия (на русском)",
      "expected_return": "0.5% daily or weekly",
      "risk": "low|medium|high",
      "confidence": 75,
      "exchanges": ["Binance", "Bybit"],
      "entry": 12345,
      "stop_loss": 12000,
      "take_profit": 13000,
      "reasoning": "Почему эта сделка работает"
    }}
  ],
  "active_strategies": [
    {{
      "name": "Strategy Name",
      "status": "active|standby",
      "pairs": ["BTC", "ETH"],
      "daily_yield": "0.3%",
      "capital_needed": "$500"
    }}
  ],
  "risk_warnings": ["предупреждение 1", "предупреждение 2"],
  "daily_plan": "План на день в русском (2-3 предложения)",
  "lessons_learned": ["Урок 1 из анализа рынка", "Урок 2"],
  "next_actions": ["Действие 1", "Действие 2", "Действие 3"]
}}

ВАЖНО:
- Дай КОНКРЕТНЫЕ сделки с entry/SL/TP
- Оцени confidence для каждой 0-100%
- Рассчитай expected_return (дневной)
- Укажи все риски
- Будь ТРЕЙДЕРСКИМ (практичным), не теоретическим
- Ответ ТОЛЬКО JSON, без доп текста

Начни анализ ТЕ-ЧАС! 🚀📈💰
"""
    
    return prompt

def call_anthropic_api(prompt):
    """Call Anthropic API with Claude Opus 4.6"""
    try:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://ai.externcashpn.cv")
        
        if not api_key:
            print("[BRAIN] No ANTHROPIC_API_KEY found", flush=True)
            return None
        
        url = f"{base_url}/v1/messages"
        
        payload = {
            "model": "claude-opus-4-20250514",
            "max_tokens": 4096,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "system": "Ты опытный квант-трейдер крипто. Всегда возвращай результаты ТОЛЬКО в формате JSON без дополнительного текста."
        }
        
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            },
            method='POST'
        )
        
        print("[BRAIN] Calling Anthropic API...", flush=True)
        
        with urllib.request.urlopen(req, timeout=55) as response:
            result = json.loads(response.read().decode())
            
            if "content" in result and len(result["content"]) > 0:
                text = result["content"][0]["text"]
                print(f"[BRAIN] AI Response received ({len(text)} chars)", flush=True)
                
                # Try to extract JSON from response
                try:
                    # Handle markdown code blocks
                    if "```json" in text:
                        json_text = text.split("```json")[1].split("```")[0].strip()
                    elif "```" in text:
                        json_text = text.split("```")[1].split("```")[0].strip()
                    else:
                        json_text = text
                    
                    analysis = json.loads(json_text)
                    return analysis
                except json.JSONDecodeError as e:
                    print(f"[BRAIN] JSON parse error: {e}", flush=True)
                    # Return partial analysis
                    return {
                        "timestamp": datetime.utcnow().isoformat(),
                        "raw_response": text[:500],
                        "parse_error": str(e)
                    }
            
            return None
            
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        print(f"[BRAIN] API Error ({e.code}): {error_body}", flush=True)
        return None
    except Exception as e:
        print(f"[BRAIN] Exception: {str(e)}", flush=True)
        return None

def analyze_market(market_data):
    """Run full AI analysis"""
    # Check cache
    cache_key = f"analysis_{hashlib.md5(json.dumps(market_data, sort_keys=True).encode()).hexdigest()}"
    cached = cache_get(cache_key)
    if cached:
        return cached
    
    print("[BRAIN] Building AI prompt...", flush=True)
    prompt = build_ai_prompt(market_data)
    
    print("[BRAIN] Sending to Claude Opus 4.6...", flush=True)
    analysis = call_anthropic_api(prompt)
    
    if analysis:
        cache_set(cache_key, analysis)
        return analysis
    
    # Fallback: return market scan without AI analysis
    return None

# ============================================================================
# HTTP HANDLER (Vercel Serverless)
# ============================================================================

class handler(BaseHTTPRequestHandler):
    """Vercel serverless handler"""
    
    def do_GET(self):
        """Handle GET requests"""
        try:
            print(f"[BRAIN] Request: {self.path}", flush=True)
            
            # Parse query params
            query_params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            
            # Determine response mode
            mode = query_params.get("mode", ["full"])[0]  # "full", "scan", "cache-only"
            
            # SCAN mode: just market data
            if mode == "scan":
                market_data = scan_market_data()
                response = {
                    "status": "ok",
                    "mode": "scan",
                    "data": market_data
                }
            
            # CACHE-ONLY mode: return cached if available
            elif mode == "cache-only":
                market_data = cache_get("market_scan")
                if market_data:
                    response = {
                        "status": "ok",
                        "mode": "cache-only",
                        "data": market_data,
                        "cached": True
                    }
                else:
                    response = {
                        "status": "no-cache",
                        "mode": "cache-only",
                        "message": "No cached data available"
                    }
            
            # FULL mode (default): scan + AI analysis
            else:
                market_data = scan_market_data()
                
                if market_data:
                    print("[BRAIN] Running AI analysis...", flush=True)
                    analysis = analyze_market(market_data)
                    
                    if analysis:
                        response = {
                            "status": "ok",
                            "mode": "full",
                            "timestamp": datetime.utcnow().isoformat(),
                            "market_data": market_data,
                            "ai_analysis": analysis
                        }
                    else:
                        # Fallback: return market data only
                        response = {
                            "status": "partial",
                            "mode": "full",
                            "timestamp": datetime.utcnow().isoformat(),
                            "market_data": market_data,
                            "message": "AI analysis failed, returning market data only"
                        }
                else:
                    response = {
                        "status": "error",
                        "message": "Failed to scan market data"
                    }
            
            # Send response with CORS headers
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Cache-Control", "public, max-age=300")
            self.end_headers()
            
            # Write response
            response_json = json.dumps(response, ensure_ascii=False, indent=2)
            self.wfile.write(response_json.encode('utf-8'))
            
            print(f"[BRAIN] Response sent ({len(response_json)} bytes)", flush=True)
            
        except Exception as e:
            print(f"[BRAIN] Handler error: {str(e)}", flush=True)
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            error_response = json.dumps({
                "status": "error",
                "message": str(e)
            })
            self.wfile.write(error_response.encode())
    
    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
    
    def log_message(self, format, *args):
        """Suppress default logging"""
        pass

# ============================================================================
# EXPORTED HANDLER FOR VERCEL
# ============================================================================

# Vercel expects a handler function or BaseHTTPRequestHandler subclass
# Export the handler class for Vercel to use
__all__ = ["handler"]
