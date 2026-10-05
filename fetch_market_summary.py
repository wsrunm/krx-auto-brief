import os
import requests
import google.generativeai as genai

# ---------------------------------------------------------
# 1. 다음(Daum) 금융 API 활용 (GitHub 해외 IP 차단 없음, 휴장일 폴백 완벽 지원)
# ---------------------------------------------------------
def get_verified_market_data():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://finance.daum.net/'
    }
    
    # 1. 지수 데이터 수집 (코스피 / 코스닥)
    kospi_str = "확인불가"
    kosdaq_str = "확인불가"
    
    try:
        url_idx = "https://finance.daum.net/api/quotes/sectors?market=KOSPI"
        r = requests.get(url_idx, headers=headers, timeout=10).json()
        # 코스피 종합지수 추출
        for sec in r.get("data", []):
            if sec.get("sectorCode") == "001":  # 코스피 종합
                val = sec.get("tradePrice")
                chg = sec.get("changePrice")
                rate = sec.get("changeRate")
                sign = "+" if rate > 0 else ("-" if rate < 0 else "")
                kospi_str = f"{val:,.2f} ({sign}{chg:,.2f} / {sign}{rate*100:.2f}%)"
                break
    except Exception as e:
        print(f"코스피 수집 실패: {e}")

    try:
        url_idx_kd = "https://finance.daum.net/api/quotes/sectors?market=KOSDAQ"
        r_kd = requests.get(url_idx_kd, headers=headers, timeout=10).json()
        for sec in r_kd.get("data", []):
            if sec.get("sectorCode") == "001":  # 코스닥 종합
                val = sec.get("tradePrice")
                chg = sec.get("changePrice")
                rate = sec.get("changeRate")
                sign = "+" if rate > 0 else ("-" if rate < 0 else "")
                kosdaq_str = f"{val:,.2f} ({sign}{chg:,.2f} / {sign}{rate*100:.2f}%)"
                break
    except Exception as e:
        print(f"코스닥 수집 실패: {e}")

    # 2. 상승률 상위 종목 수집 (최근 거래일 기준 랭킹)
    top_stocks = []
    try:
        rank_url = "https://finance.daum.net/api/trend/price_fluctuations?market=KOSPI&page=1&perPage=15&type=RATE&order=DESC"
        r_rank = requests.get(rank_url, headers=headers, timeout=10).json()
        stocks = r_rank.get("data", [])
        
        count = 0
        for s in stocks:
            name = s.get("name", "")
            price = s.get("tradePrice", 0)
            rate = s.get("changeRate", 0) * 100
            vol = s.get("accTradeVolume", 0)
            
            # 우선주, 스팩, 관리종목 등 필터링
            if any(x in name for x in ["스팩", "우", "1우", "2우B", "ETN", "리츠"]):
                continue
                
            top_stocks.append(f"- {name}: 종가 {price:,.0f}원 (등락률 +{rate:.2f}%, 거래량 {vol:,}주)")
            count += 1
            if count >= 5:
                break
    except Exception as e:
        print(f"상승 종목 수집 실패: {e}")

    return {
        "kospi": kospi_str,
        "kosdaq": kosdaq_str,
        "stocks": "\n".join(top_stocks) if top_stocks else "직전 거래일 데이터 수집 결과 없음"
    }

# ---------------------------------------------------------
# 2. AI 팩트 요약
# ---------------------------------------------------------
def generate_brief_report(data):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return f"📊 한국 증시 마감 지표\n\n- 코스피: {data['kospi']}\n- 코스닥: {data['kosdaq']}\n\n[주요 급등 종목]\n{data['stocks']}"

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    prompt = f"""
당신은 엄격한 금융 데이터 검증관입니다.
아래 데이터는 시스템이 실제 증시 API에서 수집한 최근 거래일 확정 수치입니다.

[수집된 확정 수치]
- 코스피: {data['kospi']}
- 코스닥: {data['kosdaq']}
- 주요 급등 종목:
{data['stocks']}

[수행 지침]
1. 위 [수집된 확정 수치]의 숫자, 종목명, 등락률을 100% 그대로 유지하십시오. 절대로 다른 숫자로 바꾸지 마십시오.
2. 각 종목별로 공식적인 상승 사유/테마를 사실에 기반하여 1줄로 작성하십시오.
3. 텔레그램 특수문자 파싱 오류 방지를 위해 마크다운 기호(*, _, [ 등)를 사용하지 마십시오.

[출력 양식]
📊 한국 증시 마감 브리프 (최근 거래일 기준)

■ 시장 지수
- 코스피: {data['kospi']}
- 코스닥: {data['kosdaq']}

■ 주요 급등주 및 배경
(제공된 종목별로 등락률 및 사유 1줄 요약)

■ 핵심 테마 코멘트
(2~3줄 요약)
"""
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Gemini API 호출 실패: {e}")
        return f"📊 한국 증시 마감 지표\n\n- 코스피: {data['kospi']}\n- 코스닥: {data['kosdaq']}\n\n[주요 급등 종목]\n{data['stocks']}"

# ---------------------------------------------------------
# 3. 텔레그램 발송
# ---------------------------------------------------------
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
            print("✅ 텔레그램 발송 성공")
        else:
            print(f"❌ 텔레그램 발송 실패: {res.text}")
    except Exception as e:
        print(f"❌ 텔레그램 통신 에러: {e}")

if __name__ == "__main__":
    try:
        print("🔍 증시 데이터 수집 시작 (Daum Finance API)...")
        data = get_verified_market_data()
        print("📝 요약 생성 중...")
        report_text = generate_brief_report(data)
        print("🚀 텔레그램 발송 시도...")
        send_telegram(report_text)
    except Exception as e:
        print(f"⚠️ 실행 예외: {e}")
