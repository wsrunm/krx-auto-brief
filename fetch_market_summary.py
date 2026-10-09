import os
import json
import time
from datetime import datetime, timedelta
import requests
import google.generativeai as genai

BASE_URL = "https://openapi.koreainvestment.com:9443"
TOKEN_CACHE_FILE = "kis_token.json"

# ---------------------------------------------------------
# 1. KIS OAuth2 접근 토큰 관리 (캐시 재사용)
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
                    print("♻️ 기존 KIS 토큰 재사용 (API 호출 생략)")
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
        res = session.post(url, headers=headers, data=json.dumps(body), timeout=10)
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
            print("✅ KIS 토큰 발급 및 캐시 저장 완료")
            return token
        else:
            print(f"❌ KIS 토큰 발급 거절: {data}")
            return None
    except Exception as e:
        print(f"❌ 토큰 발급 통신 예외: {e}")
        return None

# ---------------------------------------------------------
# 2. 직전 영업일 날짜 산출
# ---------------------------------------------------------
def get_target_date_str():
    cur = datetime.now()
    if cur.weekday() == 5:    # 토요일
        cur -= timedelta(days=1)
    elif cur.weekday() == 6:  # 일요일
        cur -= timedelta(days=2)
    return cur.strftime("%Y.%m.%d")

# ---------------------------------------------------------
# 3. 코스피 / 코스닥 지수 수치 조회 (각 1회 호출)
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
    params = {
        "FID_COND_MRKT_DIV_CODE": "U",
        "FID_INPUT_ISCD": iscd
    }
    
    try:
        res = session.get(url, headers=headers, params=params, timeout=10)
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
# 4. 거래대금 상위 Top 20 (단 1회 호출)
# ---------------------------------------------------------
def get_trade_value_top20(session, token, app_key, app_secret):
    url = f"{BASE_URL}/uapi/domestic-stock/v1/ranking/trade-value"
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "FHPST01710000",
        "custtype": "P"
    }
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_COND_SCR_DIV_CODE": "20171",
        "FID_INPUT_ISCD": "0001",          # 코스피 기준 주도주 상위
        "FID_DIV_CLS_CODE": "0",
        "FID_BLNG_CLS_CODE": "0",
        "FID_TRGT_CLS_CODE": "111111111",
        "FID_TRGT_EXLS_CLS_CODE": "0",
        "FID_INPUT_PRICE_1": "",
        "FID_INPUT_PRICE_2": "",
        "FID_VOL_CNT": "",
        "FID_INPUT_DATE_1": ""
    }
    
    results = []
    try:
        res = session.get(url, headers=headers, params=params, timeout=10)
        data = res.json()
        if res.status_code == 200 and data.get("rt_cd") == "0":
            for s in data.get("output", []):
                name = s.get("hts_kor_isnm", "").strip()
                if any(x in name for x in ["스팩", "우", "1우", "2우B", "ETN", "리츠"]):
                    continue
                price = int(str(s.get("stck_prpr", "0")).replace(",", ""))
                rate_str = str(s.get("prdy_cttr", s.get("prdy_vrss_rt", "0.0"))).replace(",", "")
                rate = float(rate_str) if rate_str.replace(".", "", 1).replace("-", "").isdigit() else 0.0
                vol = int(str(s.get("acml_vol", "0")).replace(",", ""))
                
                sign = "+" if rate > 0 else ("-" if rate < 0 else "")
                results.append(f"{name}: {price:,}원 ({sign}{abs(rate):.2f}%, {vol:,}주)")
                if len(results) >= 20:
                    break
    except Exception as e:
        print(f"⚠️ 거래대금 순위 조회 예외: {e}")
    return results

# ---------------------------------------------------------
# 5. 외인 / 기관 순매수 랭킹 API (각 1회 호출로 20개 일괄 수집)
# ---------------------------------------------------------
def get_investor_ranking(session, token, app_key, app_secret, trgt_type="2"):
    """
    국내주식 투자자별 매매상위 (FHPST01720000)
    trgt_type: '2' (외국인 순매수), '3' (기관 순매수)
    """
    url = f"{BASE_URL}/uapi/domestic-stock/v1/ranking/investor-buy-sell"
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "FHPST01720000",
        "custtype": "P"
    }
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_COND_SCR_DIV_CODE": "20172",
        "FID_INPUT_ISCD": "0001",          # 코스피
        "FID_DIV_CLS_CODE": "0",           # 0: 순매수
        "FID_RANK_SORT_CLS_CODE": trgt_type, # 2: 외인, 3: 기관
        "FID_INPUT_CNT_1": "0",
        "FID_TRGT_CLS_CODE": "0",
        "FID_TRGT_EXLS_CLS_CODE": "0",
        "FID_INPUT_PRICE_1": "",
        "FID_INPUT_PRICE_2": "",
        "FID_VOL_CNT": ""
    }
    
    results = []
    try:
        res = session.get(url, headers=headers, params=params, timeout=10)
        data = res.json()
        if res.status_code == 200 and data.get("rt_cd") == "0":
            for s in data.get("output", []):
                name = s.get("hts_kor_isnm", "").strip()
                if any(x in name for x in ["스팩", "우", "1우", "2우B", "ETN", "리츠"]):
                    continue
                qty_raw = str(s.get("ntby_qty", s.get("frgn_ntby_qty", "0"))).replace(",", "")
                qty = int(qty_raw) if qty_raw.replace("-", "").isdigit() else 0
                sign = "+" if qty > 0 else ""
                results.append(f"{name}: {sign}{qty:,}주")
                if len(results) >= 20:
                    break
    except Exception as e:
        print(f"⚠️ 수급 랭킹({trgt_type}) 조회 예외: {e}")
    return results

# ---------------------------------------------------------
# 6. 리포트 생성 및 텔레그램 전송
# ---------------------------------------------------------
def generate_part1_report(date_str, kospi, kosdaq, top_stocks):
    lines = [f"{idx:02d}. {item}" for idx, item in enumerate(top_stocks, 1)]
    stocks_text = "\n".join(lines) if lines else "수집된 거래대금 상위 종목 없음"
    
    api_key = os.getenv("GEMINI_API_KEY")
    ai_comment = "금일 마감 지수와 대형 거래대금 주도주 중심 장세입니다."
    if api_key:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = f"""
당신은 엄격한 증시 리서치 연구원입니다.
아래 거래대금 상위 20개 종목을 보고 시장 주도 테마와 핵심 흐름을 2~3줄로 깔끔하게 요약하십시오.
특수문자 마크다운(*, _, [ 등)은 절대 사용하지 마십시오.

[거래대금 상위 종목]
{stocks_text}
"""
        try:
            res = model.generate_content(prompt)
            ai_comment = res.text.strip()
        except Exception as e:
            print(f"Gemini 호출 에러: {e}")

    return f"""📊 [1/2] 한국 증시 마감 브리프 ({date_str})

■ 시장 마감 지수
- 코스피: {kospi}
- 코스닥: {kosdaq}

■ 거래대금 상위 Top 20
{stocks_text}

■ 시장 주도 테마 코멘트
{ai_comment}"""

def generate_part2_report(date_str, frgn_stocks, orgn_stocks):
    frgn_lines = [f"{idx:02d}. {item}" for idx, item in enumerate(frgn_stocks, 1)]
    orgn_lines = [f"{idx:02d}. {item}" for idx, item in enumerate(orgn_stocks, 1)]
    
    return f"""📈 [2/2] 외인 / 기관 수급 순위 ({date_str})

■ 외국인 순매수 Top 20
{chr(10).join(frgn_lines) if frgn_lines else "데이터 없음"}

■ 기관 순매수 Top 20
{chr(10).join(orgn_lines) if orgn_lines else "데이터 없음"}"""

def send_telegram(text):
    bot_token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)

# ---------------------------------------------------------
# 메인 실행
# ---------------------------------------------------------
if __name__ == "__main__":
    app_key = os.getenv("KIS_APP_KEY")
    app_secret = os.getenv("KIS_APP_SECRET")
    
    if not app_key or not app_secret:
        print("❌ KIS 환경변수 누락")
        exit(1)
        
    session = requests.Session()
    token = get_kis_access_token(session, app_key, app_secret)
    if not token:
        exit(1)
        
    date_str = get_target_date_str()
    print("🚀 최소 호출 파이프라인 가동 (총 5~6회 호출)...")
    
    # 1. 지수 (2회)
    kospi = get_market_index(session, token, app_key, app_secret, "0001")
    kosdaq = get_market_index(session, token, app_key, app_secret, "1001")
    time.sleep(0.1)
    
    # 2. 거래대금 상위 20위 (1회)
    trade_top20 = get_trade_value_top20(session, token, app_key, app_secret)
    time.sleep(0.1)
    
    # 3. 외인 순매수 상위 20위 (1회)
    frgn_top20 = get_investor_ranking(session, token, app_key, app_secret, trgt_type="2")
    time.sleep(0.1)
    
    # 4. 기관 순매수 상위 20위 (1회)
    orgn_top20 = get_investor_ranking(session, token, app_key, app_secret, trgt_type="3")
    
    # 1번 메시지 발송
    msg1 = generate_part1_report(date_str, kospi, kosdaq, trade_top20)
    send_telegram(msg1)
    print("✅ 1번 브리프 발송 완료")
    
    # 2번 메시지 발송
    msg2 = generate_part2_report(date_str, frgn_top20, orgn_top20)
    send_telegram(msg2)
    print("✅ 2번 수급 브리프 발송 완료")
