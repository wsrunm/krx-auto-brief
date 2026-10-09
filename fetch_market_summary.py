import os
import json
import time
from datetime import datetime, timedelta
import requests
import google.generativeai as genai

BASE_URL = "https://openapi.koreainvestment.com:9443"
TOKEN_CACHE_FILE = "kis_token.json"

# ---------------------------------------------------------
# 1. KIS OAuth2 접근 토큰 관리
# ---------------------------------------------------------
def get_kis_access_token(app_key, app_secret):
    current_time = time.time()
    
    if os.path.exists(TOKEN_CACHE_FILE):
        try:
            with open(TOKEN_CACHE_FILE, "r", encoding="utf-8") as f:
                cached = json.load(f)
                token = cached.get("access_token")
                expires_at = cached.get("expires_at", 0)
                
                if token and (expires_at - current_time > 3600):
                    print("♻️ 유효한 기존 KIS 토큰을 재사용합니다.")
                    return token
        except Exception as e:
            print(f"⚠️ 토큰 캐시 파일 읽기 실패: {e}")

    print("🔑 KIS 신규 접근 토큰을 발급받습니다...")
    url = f"{BASE_URL}/oauth2/tokenP"
    headers = {"Content-Type": "application/json"}
    body = {
        "grant_type": "client_credentials",
        "appkey": app_key,
        "appsecret": app_secret
    }
    
    try:
        res = requests.post(url, headers=headers, data=json.dumps(body), timeout=10)
        data = res.json()
        
        if res.status_code == 200 and "access_token" in data:
            token = data["access_token"]
            expires_in = int(data.get("expires_in", 86400))
            
            cache_data = {
                "access_token": token,
                "expires_at": current_time + expires_in
            }
            with open(TOKEN_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(cache_data, f)
            print("✅ KIS 신규 토큰 발급 완료")
            return token
        else:
            print(f"❌ KIS 토큰 발급 실패: {data}")
            return None
    except Exception as e:
        print(f"❌ 토큰 발급 예외: {e}")
        return None

# ---------------------------------------------------------
# 2. 직전 영업일(최근 장 열린 날짜) 판별
# ---------------------------------------------------------
def get_last_business_day(token, app_key, app_secret):
    """
    국내휴장일조회 API (CTCA0903R)를 통해 직전 영업일 날짜 산출
    조회 실패 시 평일 기준 날짜로 안전 폴백
    """
    today = datetime.now()
    url = f"{BASE_URL}/uapi/domestic-stock/v1/quotations/chk-holiday"
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "CTCA0903R",
        "custtype": "P"
    }
    params = {
        "BASS_DT": today.strftime("%Y%m%d"),
        "CTX_AREA_NK": "",
        "CTX_AREA_FK": ""
    }
    
    try:
        res = requests.get(url, headers=headers, params=params, timeout=10)
        data = res.json()
        if res.status_code == 200 and data.get("rt_cd") == "0":
            holidays = data.get("output", [])
            # 오늘이 개장일인지 확인 (opnd_yn == 'Y')
            for day_info in holidays:
                dt_str = day_info.get("bass_dt")
                is_open = day_info.get("opnd_yn")
                if dt_str == today.strftime("%Y%m%d") and is_open == "Y":
                    return today.strftime("%Y%m%d")
    except Exception as e:
        print(f"⚠️ 휴장일 API 조회 예외: {e}")

    # 공휴일/주말인 경우 직전 평일 탐색 (단순 역산 폴백)
    cur = today
    # 이미 장 마감 시점이 지났거나 오늘이 휴일이면 전일부터 검사
    cur -= timedelta(days=1)
    while cur.weekday() >= 5:  # 토(5), 일(6) 건너뛰기
        cur -= timedelta(days=1)
    return cur.strftime("%Y%m%d")

# ---------------------------------------------------------
# 3. 코스피 / 코스닥 지수 수치 조회 (장마감 및 휴일 대응)
# ---------------------------------------------------------
def get_market_index(token, app_key, app_secret, iscd):
    url = f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-index-price"
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "FHPUP02100000",
        "custtype": "P"
    }
    params = {
        "FID_COND_MRKT_DIV_CODE": "U",
        "FID_INPUT_ISCD": iscd
    }
    
    try:
        res = requests.get(url, headers=headers, params=params, timeout=10)
        data = res.json()
        if res.status_code == 200 and data.get("rt_cd") == "0":
            out = data.get("output", {})
            
            price_val = out.get("bstp_nmix_prpr")
            if not price_val or float(price_val) == 0:
                price_val = out.get("bstp_nmix_prdy_clpr", "0")
            if not price_val or float(price_val) == 0:
                price_val = out.get("prdy_clpr", "0")
                
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
# 4. 급등 종목 조회 (휴장일/주말: MTS처럼 직전 거래일 마감 랭킹 복원)
# ---------------------------------------------------------
def get_gainers_from_kis(token, app_key, app_secret, market_code, market_name):
    """정규장 당일 등락률 순위 조회"""
    url = f"{BASE_URL}/uapi/domestic-stock/v1/ranking/fluctuation"
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": app_
