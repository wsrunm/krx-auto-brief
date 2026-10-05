import os
import requests
import google.generativeai as genai

def get_verified_market_data():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://finance.naver.com/'
    }
    
    # 1. 지수 데이터 수집 (네이버 모바일 API는 휴장일에도 직전 거래일 종가 반환)
    index_url = "https://m.stock.naver.com/api/index/KOSPI/basic"
    kosdaq_url = "https://m.stock.naver.com/api/index/KOSDAQ/basic"
    
    try:
        r_kospi = requests.get(index_url, headers=headers, timeout=10).json()
        k_val = r_kospi.get("nowValue", "확인불가")
        k_change = r_kospi.get("changeValue", "")
        k_rate = r_kospi.get("changeRate", "")
        k_dir = "+" if float(k_rate) > 0 else ("-" if float(k_rate) < 0 else "")
        kospi_str = f"{k_val} ({k_dir}{k_change} / {k_dir}{k_rate}%)"
    except Exception:
        kospi_str = "확인불가"

    try:
        r_kosdaq = requests.get(kosdaq_url, headers=headers, timeout=10).json()
        kd_val = r_kosdaq.get("nowValue", "확인불가")
        kd_change = r_kosdaq.get("changeValue", "")
        kd_rate = r_kosdaq.get("changeRate", "")
        kd_dir = "+" if float(kd_rate) > 0 else ("-" if float(kd_rate) < 0 else "")
        kosdaq_str = f"{kd_val} ({kd_dir}{kd_change} / {kd_dir}{kd_rate}%)"
    except Exception:
        kosdaq_str = "확인불가"

    # 2. 상승률 상위 종목 수집 (모바일 랭킹 API는 휴장일에도 직전 마감 랭킹 유지)
    ranking_url = "https://m.stock.naver.com/api/stocks/ranking/KOSPI?page=1&pageSize=20&rankingType=changeRate"
    top_stocks = []
    
    try:
        r_rank = requests.get(ranking_url, headers=headers, timeout=10).json()
        stocks = r_rank.get("stocks", [])
        
        count = 0
        for s in stocks:
            name = s.get("stockName", "")
            price = s.get("nowPrice", "")
            rate = s.get("changeRate", "")
            vol = s.get("accumulatedTradingVolume", "")
            
            # 우선주, 스팩, ETN 필터링
            if any(x in name for x in ["스팩", "우", "1우", "2우B", "ETN", "리츠"]):
                continue
                
            if name:
                top_stocks.append(f"- {name}: 종가 {price}원 (등락률 +{rate}%, 거래량 {vol}주)")
                count += 1
                if count >= 5:
                    break
    except Exception as e:
        print(f"상승 종목 수집 에러: {e}")

    return {
        "kospi": kospi_str,
        "kosdaq": kosdaq_str,
        "stocks": "\n".join(top_stocks) if top_stocks else "직전 거래일 데이터 확인 필요"
    }

def generate_brief_report(data):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return f"📊 한국 증시 마감 지표\n\n- 코스피: {data['kospi']}\n- 코스닥: {data['kosdaq']}\n\n[주요 급등 종목]\n{data['stocks']}"

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    prompt = f"""
당신은 엄격한 금융 데이터 검증관입니다.
아래 데이터는 시스템이 네이버 증시 API에서 수집한 가장 최근 거래일의 공식 확정 데이터입니다.

[수집된 확정 수치]
- 코스피: {data['kospi']}
- 코스닥: {data['kosdaq']}
- 주요 급등 종목:
{data['stocks']}

[수행 지침]
1. 위 [수집된 확정 수치]에 적힌 숫자, 종목명, 등락률을 100% 그대로 사용하십시오. 절대로 임의로 수정하거나 추정치를 적지 마십시오.
2. 각 종목별로 공식적인 상승 사유/테마를 사실에 기반하여 1줄로 작성하십시오.
3. 텔레그램 특수문자 오류 방지를 위해 마크다운 기호(*, _, [ 등)를 사용하지 마십시오.

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
        print(f"⚠️ Gemini API 호출 실패: {e}")
        return f"📊 한국 증시 마감 지표\n\n- 코스피: {data['kospi']}\n- 코스닥: {data['kosdaq']}\n\n[주요 급등 종목]\n{data['stocks']}"

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
        print(f"❌ 텔레그램 네트워크 오류: {e}")

if __name__ == "__main__":
    try:
        print("🔍 증시 데이터 수집 시작...")
        data = get_verified_market_data()
        print("📝 요약 생성 중...")
        report_text = generate_brief_report(data)
        print("🚀 텔레그램 발송 시도...")
        send_telegram(report_text)
    except Exception as e:
        print(f"⚠️ 실행 예외: {e}")
