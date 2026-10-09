import os
import requests
import google.generativeai as genai

# ---------------------------------------------------------
# 1. 네이버 금융 공식 모바일 JSON API (휴일/주말에도 직전 거래일 유지)
# ---------------------------------------------------------
def get_verified_market_data():
    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1',
        'Referer': 'https://m.stock.naver.com/',
        'Accept': 'application/json, text/plain, */*'
    }
    
    kospi_str = "확인불가"
    kosdaq_str = "확인불가"
    
    # 1. 코스피 / 코스닥 지수 수집
    try:
        r_k = requests.get("https://m.stock.naver.com/api/index/KOSPI/basic", headers=headers, timeout=10).json()
        val = r_k.get("nowValue")
        chg = r_k.get("changeValue")
        rate = r_k.get("changeRate")
        sign = "+" if float(rate) > 0 else ("-" if float(rate) < 0 else "")
        kospi_str = f"{val} ({sign}{chg} / {sign}{rate}%)"
    except Exception as e:
        print(f"KOSPI 파싱 에러: {e}")

    try:
        r_q = requests.get("https://m.stock.naver.com/api/index/KOSDAQ/basic", headers=headers, timeout=10).json()
        val = r_q.get("nowValue")
        chg = r_q.get("changeValue")
        rate = r_q.get("changeRate")
        sign = "+" if float(rate) > 0 else ("-" if float(rate) < 0 else "")
        kosdaq_str = f"{val} ({sign}{chg} / {sign}{rate}%)"
    except Exception as e:
        print(f"KOSDAQ 파싱 에러: {e}")

    # 2. 거래대금 상위 종목 수집 (시장 주도주 파악)
    top_stocks = []
    try:
        url_trade = "https://m.stock.naver.com/api/stocks/ranking/KOSPI?page=1&pageSize=15&rankingType=tradeValue"
        stocks = requests.get(url_trade, headers=headers, timeout=10).json().get("stocks", [])
        
        count = 0
        for s in stocks:
            name = s.get("stockName", "")
            price = s.get("nowPrice", "")
            rate = s.get("changeRate", "")
            vol = s.get("accumulatedTradingVolume", "")
            
            # 우선주, 스팩, 리츠 제외
            if any(x in name for x in ["스팩", "우", "1우", "2우B", "ETN", "리츠"]):
                continue
                
            sign = "+" if float(rate) > 0 else ("-" if float(rate) < 0 else "")
            top_stocks.append(f"- {name}: 종가 {price}원 (등락률 {sign}{rate}%, 거래량 {vol}주)")
            count += 1
            if count >= 5:
                break
    except Exception as e:
        print(f"거래대금 상위 종목 에러: {e}")

    return {
        "kospi": kospi_str,
        "kosdaq": kosdaq_str,
        "stocks": "\n".join(top_stocks) if top_stocks else "직전 거래일 종목 데이터 확인 필요"
    }

# ---------------------------------------------------------
# 2. AI 팩트 기반 요약 (수치 임의 변경 절대 금지)
# ---------------------------------------------------------
def generate_brief_report(data):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return f"📊 한국 증시 마감 지표\n\n- 코스피: {data['kospi']}\n- 코스닥: {data['kosdaq']}\n\n[주요 종목]\n{data['stocks']}"

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    prompt = f"""
당신은 엄격한 금융 데이터 검증관입니다.
아래 데이터는 시스템이 실제 증시 API에서 수집한 가장 최근 거래일 공식 확정 수치입니다.

[수집된 확정 수치]
- 코스피: {data['kospi']}
- 코스닥: {data['kosdaq']}
- 시장 주도 종목 (거래대금 상위):
{data['stocks']}

[수행 지침]
1. 위 [수집된 확정 수치]에 적힌 숫자, 종목명, 등락률을 100% 그대로 사용하십시오. 절대로 다른 숫자로 바꾸지 마십시오.
2. 각 종목별로 공식적인 등
