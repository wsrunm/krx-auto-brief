import os
import json
import time
import requests
import google.generativeai as genai

BASE_URL = "https://openapi.koreainvestment.com:9443"
TOKEN_CACHE_FILE = "kis_token.json"

# ---------------------------------------------------------
# 1. KIS OAuth2 접근 토큰 관리 (캐시 파일 활용으로 중복 발급 방지)
# ---------------------------------------------------------
def get_kis_access_token(app_key, app_secret):
    current_time = time.time()
    
    # 1-1. 캐시 파일 검증 (유효시간 1시간 이상 남아있으면 재사용)
    if os.path.exists(TOKEN_CACHE_FILE):
        try:
            with open(TOKEN_CACHE_FILE, "r", encoding="utf-8") as f:
                cached = json.load(f)
                token = cached.get("access_token")
                expires_at = cached.get("expires_at", 0)
                
                if token and (expires_at - current_time > 3600):
                    print("♻️ 유효한 기존 KIS 토큰을 재사용합니다. (API 호출 건너뜀)")
                    return token
        except Exception as e:
            print(f"⚠️ 토큰 캐시 파일 읽기 실패, 신규 발급 진행: {e}")

    # 1-2. KIS 서버 신규 발급 요청
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
            print("✅ KIS 신규 토큰 발급 및 캐시 저장 완료")
            return token
        else:
            print(f"❌ KIS 토큰 발급 거절: {data}")
            return None
    except Exception as e:
        print(f"❌ 토큰 발급 통신 예외: {e}")
        return None

# ---------------------------------------------------------
# 2. 코스피(0001) / 코스닥(1001) 지수 수치 조회
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
            
            # 현재가 또는 전일종가 안전 파싱
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
            rate = float(rate_val)
            
            # 1: 상한, 2: 상승, 3: 보합, 4: 하한, 5: 하락
            direction = "+" if sign in ["1", "2"] else ("-" if sign in ["4", "5"] else "")
            return f"{price:,.2f} ({direction}{abs(prdy_vrss):,.2f} / {direction}{abs(rate):.2f}%)"
        else:
            print(f"⚠️ 지수({iscd}) 조회 에러 응답: {data.get('msg1', res.text)}")
    except Exception as e:
        print(f"⚠️ 지수({iscd}) 파싱 예외: {e}")
    return "확인불가"

# ---------------------------------------------------------
# 3. 코스피 / 코스닥 급등주 상위 조회
# ---------------------------------------------------------
def get_gainers_by_market(token, app_key, app_secret, market_code, market_name):
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
        "FID_INPUT_ISCD": market_code,     # 코스피: 0001, 코스닥: 1001
        "FID_RANK_SORT_CLS_CODE": "0",     # 0: 상승율순
        "FID_INPUT_CNT_1": "0",            # 0: 누적
        "FID_PRC_CLS_CODE": "1",           # 종가 기준
        "FID_INPUT_PRICE_1": "1000",       # 1,000원 이상
        "FID_INPUT_PRICE_2": "",
        "FID_VOL_CNT": "100000",           # 거래량 10만주 이상
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
                
                # 우선주, 스팩, ETN, 리츠 필터링
                if any(x in name for x in ["스팩", "우", "1우", "2우B", "ETN", "리츠"]):
                    continue
                    
                result.append(f"- [{market_name}] {name}: 종가 {price:,}원 (등락률 +{rate:.2f}%, 거래량 {vol:,}주)")
                if len(result) >= 3:
                    break
        else:
            print(f"⚠️ {market_name} 급등주 순위 에러 응답: {data.get('msg1', res.text)}")
    except Exception as e:
        print(f"⚠️ {market_name} 급등주 순위 파싱 예외: {e}")
        
    return result

def get_all_top_stocks(token, app_key, app_secret):
    kospi_stocks = get_gainers_by_market(token, app_key, app_secret, "0001", "코스피")
    kosdaq_stocks = get_gainers_by_market(token, app_key, app_secret, "1001", "코스닥")
    all_stocks = kospi_stocks + kosdaq_stocks
    return "\n".join(all_stocks) if all_stocks else "수집된 급등 종목 없음"

# ---------------------------------------------------------
# 4. 전체 파이프라인 수집
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
        
    print("✅ KIS 인증 완료. 실시간 데이터 조회 시작...")
    kospi = get_market_index(token, app_key, app_secret, "0001")
    kosdaq = get_market_index(token, app_key, app_secret, "1001")
    stocks = get_all_top_stocks(token, app_key, app_secret)
    
    return {
        "kospi": kospi,
        "kosdaq": kosdaq,
        "stocks": stocks
    }

# ---------------------------------------------------------
# 5. Gemini 브리프 생성 및 텔레그램 전송
# ---------------------------------------------------------
def generate_brief_report(data):
    if not data:
        return "⚠️ KIS 증권사 API 연동 오류로 데이터를 수신하지 못했습니다."

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return f"📊 한국 증시 마감 지표\n\n- 코스피: {data['kospi']}\n- 코스닥: {data['kosdaq']}\n\n[주요 급등 종목]\n{data['stocks']}"

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    prompt = f"""
당신은 엄격한 증시 리서치 연구원입니다.
아래 데이터는 한국투자증권(KIS) 실전 OpenAPI에서 직접 조회한 공식 확정 수치입니다.

[수집된 확정 데이터]
- 코스피: {data['kospi']}
- 코스닥: {data['kosdaq']}
- 주요 급등주 목록:
{data['stocks']}

[수행 지침]
1. 위 [수집된 확정 데이터]의 지수 수치, 종목명, 종가, 등락률은 단 1개도 변경하거나 조작하지 마십시오.
2. 각 종목별로 공식적인 급등 사유(공시, 실적, 테마, 관련 뉴스)를 사실에 근거하여 1줄로 명확히 작성하십시오.
3. 이 급등주들을 관통하는 시장 핵심 테마를 2~3줄로 분석하십시오.
4. 텔레그램 메시지 파싱 오류 방지를 위해 마크다운 기호(*, _, [ 등)는 절대 사용하지 말고 순수 텍스트로만 작성하십시오.

[출력 양식]
📊 한국 증시 마감 브리프 (공식 실측 기준)

■ 시장 마감 지수
- 코스피: {data['kospi']}
- 코스닥: {data['kosdaq']}

■ 주요 급등주 및 상승 배경
(제공된 종목별 종가, 등락률 및 상승 사유 1줄 요약)

■ 시장 핵심 테마 코멘트
(2~3줄 요약)
"""
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"⚠️ Gemini 호출 에러: {e}")
        return f"📊 한국 증시 마감 지표\n\n- 코스피: {data['kospi']}\n- 코스닥: {data['kosdaq']}\n\n[주요 급등 종목]\n{data['stocks']}"

def send_telegram(text):
    bot_token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        print("❌ 텔레그램 토큰 누락")
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
