import os
import json
import time
import requests
import google.generativeai as genai

BASE_URL = "https://openapi.koreainvestment.com:9443"
TOKEN_CACHE_FILE = "kis_token.json"

# ---------------------------------------------------------
# 1. KIS 접근 토큰 관리 (캐시 파일 검증으로 API 호출 0~1회 최소화)
# ---------------------------------------------------------
def get_kis_access_token(session, app_key, app_secret):
    current_time = time.time()
    if os.path.exists(TOKEN_CACHE_FILE):
        try:
            with open(TOKEN_CACHE_FILE, "r", encoding="utf-8") as f:
                cached = json.load(f)
                token = cached.get("access_token")
                expires_at = cached.get("expires_at", 0)
                if token and (expires_at - current_time > 3600):
                    print("♻️ 유효한 기존 KIS 토큰 재사용 (호출 0회)")
                    return token
        except Exception:
            pass

    print("🔑 KIS 신규 토큰 발급 요청 (호출 1회)...")
    url = f"{BASE_URL}/oauth2/tokenP"
    headers = {"Content-Type": "application/json"}
    body = {
        "grant_type": "client_credentials",
        "appkey": app_key,
        "appsecret": app_secret
    }
    
    try:
        res = session.post(url, headers=headers, data=json.dumps(body), timeout=10)
        data = res.json()
        if res.status_code == 200 and "access_token" in data:
            token = data["access_token"]
            expires_in = int(data.get("expires_in", 86400))
            with open(TOKEN_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump({"access_token": token, "expires_at": current_time + expires_in}, f)
            print("✅ KIS 토큰 발급 및 캐시 저장 완료")
            return token
        else:
            print(f"❌ KIS 토큰 거절: {data}")
    except Exception as e:
        print(f"❌ KIS 토큰 통신 예외: {e}")
    return None

# ---------------------------------------------------------
# 2. 코스피 / 코스닥 지수 수치 조회 (KIS API 각 1회 호출)
# ---------------------------------------------------------
def get_market_index(session, token, app_key, app_secret, iscd):
    url = f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-index-price"
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "FHPUP02100000",
        "custtype": "P"
    }
    params = {"FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": iscd}
    
    try:
        res = session.get(url, headers=headers, params=params, timeout=10)
        data = res.json()
        if res.status_code == 200 and data.get("rt_cd") == "0":
            out = data.get("output", {})
            price_val = out.get("bstp_nmix_prpr") or out.get("bstp_nmix_prdy_clpr", "0")
            vrss_val = out.get("bstp_nmix_prdy_vrss", "0")
            rate_val = out.get("bstp_nmix_prdy_cttr", "0")
            sign = out.get("prdy_vrss_sign", "3")
            
            price = float(price_val)
            prdy_vrss = float(vrss_val)
            rate = float(rate_val) if rate_val else 0.0
            
            is_down = sign in ["4", "5"]
            signed_vrss = -abs(prdy_vrss) if is_down else abs(prdy_vrss)
            if rate == 0.0 and prdy_vrss != 0:
                prev_price = price - signed_vrss
                if prev_price > 0:
                    rate = abs((signed_vrss / prev_price) * 100)
            
            direction = "-" if is_down else ("+" if sign in ["1", "2"] else "")
            return f"{price:,.2f} ({direction}{abs(prdy_vrss):,.2f} / {direction}{rate:.2f}%)"
    except Exception as e:
        print(f"⚠️ 지수({iscd}) 파싱 예외: {e}")
    return "확인불가"

# ---------------------------------------------------------
# 3. 원/달러 환율 수치 조회
# ---------------------------------------------------------
def get_usd_krw_rate(session):
    url = "https://m.stock.naver.com/front-api/marketIndex/exchange/FX_USDKRW"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = session.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json().get("result", {})
            price = data.get("closePrice", "0")
            rate = data.get("fluctuationRate", "0.0")
            sign = "+" if float(rate) > 0 else ("-" if float(rate) < 0 else "")
            diff = data.get("fluctuationAmount", "0")
            return f"{price}원 ({sign}{diff} / {sign}{abs(float(rate)):.2f}%)"
    except Exception as e:
        print(f"⚠️ 환율 조회 예외: {e}")
    return "확인불가"

# ---------------------------------------------------------
# 4. 순위별 Top 15 수집 (거래대금, 외인/기관 순매수)
# ---------------------------------------------------------
def fetch_top15_stocks(session, market_type, ranking_type):
    url = f"https://m.stock.naver.com/api/stocks/ranking/{market_type}?page=1&pageSize=30&rankingType={ranking_type}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko)',
        'Referer': 'https://m.stock.naver.com/'
    }
    results = []
    try:
        res = session.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            for s in res.json().get("stocks", []):
                name = s.get("stockName", "").strip()
                if any(x in name for x in ["스팩", "우", "1우", "2우B", "ETN", "리츠"]):
                    continue
                
                price = s.get("nowPrice", "0")
                rate = s.get("changeRate", "0.0")
                sign = "+" if float(rate) > 0 else ""
                
                if ranking_type == "tradeValue":
                    # 거래대금: 억 원 단위 환산
                    trade_amt = int(s.get("accumulatedTradingValue", "0")) // 100000000
                    results.append(f"{name}: {price}원 ({sign}{rate}%, {trade_amt:,}억)")
                else:
                    # 외인/기관 순매수 수량 안전 변환
                    quant = s.get("quant", s.get("accumulatedTradingVolume", "0"))
                    q_str = str(quant).replace(",", "")
                    try:
                        q_val = int(q_str)
                        q_sign = "+" if q_val > 0 else ""
                        results.append(f"{name}: {price}원 ({sign}{rate}%, {q_sign}{q_val:,}주)")
                    except ValueError:
                        results.append(f"{name}: {price}원 ({sign}{rate}%, {quant}주)")
                    
                if len(results) >= 15:
                    break
    except Exception as e:
        print(f"⚠️ {market_type} {ranking_type} 파싱 예외: {e}")
    return results

def build
