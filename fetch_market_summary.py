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
                    print("♻️ 기존 KIS 토큰 재사용")
                    return token
        except Exception as e:
            print(f"⚠️ 토큰 캐시 읽기 실패: {e}")

    print("🔑 KIS 신규 접근 토큰 발급...")
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
            print(f"❌ KIS 토큰 발급 거절: {data}")
            return None
    except Exception as e:
        print(f"❌ 토큰 발급 예외: {e}")
        return None

# ---------------------------------------------------------
# 2. 직전 영업일 날짜 산출 (안전 계산)
# ---------------------------------------------------------
def get_target_date_str():
    cur = datetime.now()
    # 주말인 경우 직전 금요일로 역산
    if cur.weekday() == 5:    # 토요일
        cur -= timedelta(days=1)
    elif cur.weekday() == 6:  # 일요일
        cur -= timedelta(days=2)
    return cur.strftime("%Y.%m.%d")

# ---------------------------------------------------------
# 3. 코스피 / 코스닥 지수 수치 조회
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
# 4. KIS 거래대금/등락률 상위 종목 수집
# ---------------------------------------------------------
def get_gainers_from_kis(token, app_key, app_secret, market_code, market_name):
    url = f"{BASE_URL}/uapi/domestic-stock/v1/ranking/fluctuation"
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "FHPST01700000",
        "custtype": "P"
    }
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_COND_SCR_DIV_CODE": "20170",
        "FID_INPUT_ISCD": market_code,
        "FID_RANK_SORT_CLS_CODE": "0",
        "FID_INPUT_CNT_1": "0",
        "FID_PRC_CLS_CODE": "1",
        "FID_INPUT_PRICE_1": "1000",
        "FID_INPUT_PRICE_2": "",
        "FID_VOL_CNT": "100000",
        "FID_TRGT_CLS_CODE": "0",
        "FID_TRGT_EXLS_CLS_CODE": "0"
    }
    
    result = []
    try:
        res = requests.get(url, headers=headers, params=params, timeout=10)
        data = res.json()
        if res.status_code == 200 and data.get("rt_cd") == "0":
            stocks = data.get("output", [])
            for s in stocks:
                name = s.get("hts_kor_isnm", "").strip()
                price_raw = str(s.get("stck_prpr", "0")).replace(",", "")
                rate_raw = str(s.get("prdy_cttr", "0.0")).replace(",", "")
                vol_raw = str(s.get("acml_vol", "0")).replace(",", "")
                
                price = int(price_raw) if price_raw.isdigit() else 0
                rate = float(rate_raw) if rate_raw else 0.0
                vol = int(vol_raw) if vol_raw.isdigit() else 0
                
                if any(x in name for x in ["스팩", "우", "1우", "2우B", "ETN", "리츠"]):
                    continue
                    
                result.append(f"- [{market_name}] {name}: 종가 {price:,}원 (등락률 +{rate:.2f}%, 거래량 {vol:,}주)")
                if len(result) >= 3:
                    break
    except Exception as e:
        print(f"⚠️ KIS {market_name} 급등주 예외: {e}")
        
    return result

def get_all_top_stocks(token, app_key, app_secret):
    kospi_stocks = get_gainers_from_kis(token, app_key, app_secret, "0001", "코스피")
    kosdaq_stocks = get_gainers_from_kis(token, app_key, app_secret, "1001", "코스닥")
    all_stocks = kospi_stocks + kosdaq_stocks
    
    if not all_stocks:
        return "휴장일로 인해 당일 체결된 급등주 목록이 없습니다. (직전 거래일 종가 지수 기준 마감)"
        
    return "\n".join(all_stocks)

# ---------------------------------------------------------
# 5. 전체 데이터 수집 파이프라인
# ---------------------------------------------------------
def get_verified_data():
    app_key = os.getenv("KIS_APP_KEY")
    app_secret = os.getenv("KIS_APP_SECRET")
    
    if not app_key or not app_secret:
        print("❌ KIS 환경변수 누락 (KIS_APP_KEY / KIS_APP_SECRET)")
        return None
        
    token = get_kis_access_token(app_key, app_secret)
    if not token:
        return None
        
    date_str = get_target_date_str()
    print(f"✅ 기준일: {date_str}. KIS 데이터 조회 시작...")
    
    kospi = get_market_index(token, app_key, app_secret, "0001")
    kosdaq = get_market_index(token, app_key, app_secret, "1001")
    stocks = get_all_top_stocks(token, app_key, app_secret)
    
    return {
        "date": date_str,
        "kospi": kospi,
        "kosdaq": kosdaq,
        "stocks": stocks
    }

# ---------------------------------------------------------
# 6. Gemini 브리프 생성 및 텔레그램 전송
# ---------------------------------------------------------
def generate_brief_report(data):
    if not data:
        return "⚠️ 증시 데이터 수신 오류가 발생했습니다."

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return f"📊 한국 증시 마감 지표\n\n- 코스피: {data['kospi']}\n- 코스닥: {data['kosdaq']}\n\n[주요 특징 종목]\n{data['stocks']}"

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    prompt = f"""
당신은 엄격한 증시 리서치 연구원입니다.
아래 데이터는 한국투자증권(KIS) 실전 OpenAPI에서 수집한 가장 최근 마감 확정 수치입니다.

[수집된 확정 데이터]
- 기준일: {data['date']}
- 코스피: {data['kospi']}
- 코스닥: {data['kosdaq']}
- 주요 특징 종목 현황:
{data['stocks']}

[수행 지침]
1. 위 [수집된 확정 데이터]의 지수 수치, 종목명, 종가, 등락률을 100% 그대로 인용하십시오. 절대 조작하거나 변경하지 마십시오.
2. 수집된 급등 종목이 있는 경우 각 종목별 상승 사유를 사실에 기반하여 1줄로 작성하십시오.
3. 휴장일로 인해 종목 데이터가 없는 경우, 무리하게 종목을 지어내지 말고 지수 마감 현황과 휴장 상태를 사실대로 2~3줄 요약하십시오.
4. 텔레그램 메시지 파싱 오류 방지를 위해 마크다운 기호(*, _, [ 등)는 절대 사용하지 말고 순수 텍스트로만 작성하십시오.

[출력 양식]
📊 한국 증시 마감 브리프 (최근 마감 기준)

■ 시장 마감 지수
- 코스피: {data['kospi']}
- 코스닥: {data['kosdaq']}

■ 주요 특징주 및 상승 배경
(수집된 목록 기반 1줄 요약)

■ 시장 핵심 코멘트
(2~3줄 요약)
"""
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"⚠️ Gemini 호출 에러: {e}")
        return f"📊 한국 증시 마감 지표\n\n- 코스피: {data['kospi']}\n- 코스닥: {data['kosdaq']}\n\n[주요 특징 종목]\n{data['stocks']}"

def send_telegram(text):
    bot_token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        print("❌ 텔레그램 환경변수 누락")
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code == 200:
            print("✅ 텔레그램 발송 완료")
        else:
            print(f"❌ 텔레그램 발송 실패: {res.text}")
    except Exception as e:
        print(f"❌ 텔레그램 통신 오류: {e}")

if __name__ == "__main__":
    market_data = get_verified_data()
    report = generate_brief_report(market_data)
    send_telegram(report)
