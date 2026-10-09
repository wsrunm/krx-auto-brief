import os
import json
import time
import requests
import google.generativeai as genai

BASE_URL = "https://openapi.koreainvestment.com:9443"
TOKEN_CACHE_FILE = "kis_token.json"

# ---------------------------------------------------------
# 1. KIS 접근 토큰 관리 (실패해도 프로세스 다운 방지)
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
                    print("♻️ 기존 KIS 토큰 재사용")
                    return token
        except Exception as e:
            print(f"⚠️ 토큰 캐시 읽기 실패: {e}")

    print("🔑 KIS 신규 토큰 발급 요청...")
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
            print("✅ KIS 토큰 발급 완료")
            return token
        else:
            print(f"⚠️ KIS 토큰 거절: {data}")
    except Exception as e:
        print(f"⚠️ KIS 토큰 통신 예외: {e}")
    return None

# ---------------------------------------------------------
# 2. 코스피 / 코스닥 지수 수치 조회
# ---------------------------------------------------------
def get_market_index(session, token, app_key, app_secret, iscd):
    if not token:
        return "확인불가"
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
        print(f"⚠️ 지수({iscd}) 조회 예외: {e}")
    return "확인불가"

# ---------------------------------------------------------
# 3. 원/달러 환율 조회
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
                    trade_amt = int(s.get("accumulatedTradingValue", "0")) // 100000000
                    results.append(f"{name}: {price}원 ({sign}{rate}%, {trade_amt:,}억)")
                else:
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

def build_list_text(items):
    if not items:
        return "데이터 없음"
    return "\n".join([f"{idx:02d}. {item}" for idx, item in enumerate(items, 1)])

# ---------------------------------------------------------
# 5. 시장 동향 및 특징 테마 AI 분석
# ---------------------------------------------------------
def generate_market_and_theme_analysis(kospi, kosdaq, usd_krw, top_data_summary):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "5. 시장 동향 분석\n데이터 기반 분석 대기\n\n6. 특징테마\n정보 없음"

    prompt = f"""
당신은 대한민국 최고 수준의 증시 리서치센터 연구원입니다.
아래 제공된 최신 지수 및 거래대금/수급 상위 데이터를 바탕으로 종합 브리프를 작성하십시오.

[수집 데이터]
- 코스피: {kospi}
- 코스닥: {kosdaq}
- 원/달러 환율: {usd_krw}
{top_data_summary}

[지침]
1. 제5항 [시장 동향 분석]: 지수 등락 원인, 거시경제 및 수급 흐름을 3~5줄로 분석하십시오.
2. 제6항 [특징테마 선정 및 주요 종목]:
   - 시장을 주도한 핵심 특징테마를 5개 이내로 선정하십시오.
   - 각 테마별로 실제 연관된 핵심 주식 5개씩과 테마 선정 사유를 1줄로 명시하십시오.
3. 텔레그램 오류 방지를 위해 마크다운 기호(*, _, [ 등)는 절대 사용하지 말고 순수 텍스트로만 작성하십시오.

[출력 양식]
5. 시장 동향 분석 (뉴스 및 수급 기반)
(3~5줄 분석)

6. 특징테마 및 주요 종목 (5개 이내)
■ 테마 1: [테마명]
- 주요 종목: 종목1, 종목2, 종목3, 종목4, 종목5
- 배경: 1줄 사유

■ 테마 2: [테마명]
- 주요 종목: 종목1, 종목2, 종목3, 종목4, 종목5
- 배경: 1줄 사유
"""
    try:
        genai.configure(api_key=api_key)
        # 안정성을 위해 fallback 모델 시도 포함
        for m_name in ["gemini-2.5-flash", "gemini-1.5-flash"]:
            try:
                model = genai.GenerativeModel(m_name)
                res = model.generate_content(prompt)
                if res and res.text:
                    return res.text.strip()
            except Exception:
                continue
    except Exception as e:
        print(f"⚠️ Gemini 예외: {e}")
        
    return "5. 시장 동향 분석\n지수 및 대형 거래대금 주도주 중심의 시장 장세입니다.\n\n6. 특징테마 및 주요 종목\n데이터 수집 완료 후 테마 분석이 진행됩니다."

# ---------------------------------------------------------
# 6. 텔레그램 발송
# ---------------------------------------------------------
def send_telegram(session, text):
    bot_token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        print("⚠️ 텔레그램 토큰 또는 챗ID 누락")
        return
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        res = session.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
        if res.status_code != 200:
            print(f"⚠️ 텔레그램 전송 실패: {res.text}")
    except Exception as e:
        print(f"⚠️ 텔레그램 발송 예외: {e}")

# ---------------------------------------------------------
# 메인 실행 파이프라인
# ---------------------------------------------------------
if __name__ == "__main__":
    app_key = os.getenv("KIS_APP_KEY")
    app_secret = os.getenv("KIS_APP_SECRET")
    
    session = requests.Session()
    
    # 1. KIS 인증 (실패해도 중단 없이 계속 진행)
    token = None
    if app_key and app_secret:
        token = get_kis_access_token(session, app_key, app_secret)
    else:
        print("⚠️ KIS 환경변수 미설정, 지수 조회 건너뜀")
    
    print("🚀 데이터 수집 시작...")
    
    # 1. 지수 및 환율
    kospi = get_market_index(session, token, app_key, app_secret, "0001")
    time.sleep(0.1)
    kosdaq = get_market_index(session, token, app_key, app_secret, "1001")
    usd_krw = get_usd_krw_rate(session)
    
    # 2. 거래대금 상위 1~15위
    kospi_trade = fetch_top15_stocks(session, "KOSPI", "tradeValue")
    kosdaq_trade = fetch_top15_stocks(session, "KOSDAQ", "tradeValue")
    
    # 3. 외국인 순매수 상위 1~15위
    kospi_frgn = fetch_top15_stocks(session, "KOSPI", "foreignNetBuy")
    kosdaq_frgn = fetch_top15_stocks(session, "KOSDAQ", "foreignNetBuy")
    
    # 4. 기관 순매수 상위 1~15위
    kospi_orgn = fetch_top15_stocks(session, "KOSPI", "institutionNetBuy")
    kosdaq_orgn = fetch_top15_stocks(session, "KOSDAQ", "institutionNetBuy")
    
    # 5~6. 시장 분석 및 테마 요약
    summary_data = f"""
[코스피 거래대금 상위]
{build_list_text(kospi_trade[:5])}
[코스닥 거래대금 상위]
{build_list_text(kosdaq_trade[:5])}
[외인 순매수 상위]
{build_list_text(kospi_frgn[:5])}
[기관 순매수 상위]
{build_list_text(kospi_orgn[:5])}
"""
    analysis_text = generate_market_and_theme_analysis(kospi, kosdaq, usd_krw, summary_data)
    
    # ==========================================
    # 메시지 1 발송
    # ==========================================
    try:
        msg1 = f"""📊 [1/3] 마감 지표 및 거래대금 순위

1. 코스피, 코스닥 지수 및 원달러 환율
- 코스피: {kospi}
- 코스닥: {kosdaq}
- 원/달러 환율: {usd_krw}

2. 거래대금(금액) 순위 1~15위
■ 코스피 거래대금 Top 15
{build_list_text(kospi_trade)}

■ 코스닥 거래대금 Top 15
{build_list_text(kosdaq_trade)}"""
        send_telegram(session, msg1)
        print("✅ 1번 메시지 발송 완료")
    except Exception as e:
        print(f"⚠️ 1번 메시지 발송 오류: {e}")
    time.sleep(1)

    # ==========================================
    # 메시지 2 발송
    # ==========================================
    try:
        msg2 = f"""📈 [2/3] 외국인 및 기관 순매수 순위

3. 외국인 순매수(금액) 순위 1~15위
■ 코스피 외국인 순매수 Top 15
{build_list_text(kospi_frgn)}

■ 코스닥 외국인 순매수 Top 15
{build_list_text(kosdaq_frgn)}

4. 기관 순매수(금액) 순위 1~15위
■ 코스피 기관 순매수 Top 15
{build_list_text(kospi_orgn)}

■ 코스닥 기관 순매수 Top 15
{build_list_text(kosdaq_orgn)}"""
        send_telegram(session, msg2)
        print("✅ 2번 메시지 발송 완료")
    except Exception as e:
        print(f"⚠️ 2번 메시지 발송 오류: {e}")
    time.sleep(1)

    # ==========================================
    # 메시지 3 발송
    # ==========================================
    try:
        msg3 = f"""📰 [3/3] 시장 종합 분석 및 특징테마

{analysis_text}"""
        send_telegram(session, msg3)
        print("✅ 3번 메시지 발송 완료")
    except Exception as e:
        print(f"⚠️ 3번 메시지 발송 오류: {e}")
