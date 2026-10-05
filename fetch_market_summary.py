import os
import requests
import FinanceDataReader as fdr
import google.generativeai as genai

# ---------------------------------------------------------
# 1. 검증된 라이브러리로 최근 거래일 지수 및 시세 수집
# ---------------------------------------------------------
def get_verified_market_data():
    kospi_str = "확인불가"
    kosdaq_str = "확인불가"
    top_stocks = []

    try:
        # 코스피 최근 거래일 데이터 (휴장일이어도 최근 영업일 데이터 자동 수집)
        df_kospi = fdr.DataReader('KS11')
        if not df_kospi.empty:
            last_close = df_kospi['Close'].iloc[-1]
            prev_close = df_kospi['Close'].iloc[-2]
            chg = last_close - prev_close
            rate = (chg / prev_close) * 100
            sign = "+" if chg > 0 else ("-" if chg < 0 else "")
            kospi_str = f"{last_close:,.2f} ({sign}{abs(chg):,.2f} / {sign}{abs(rate):.2f}%)"
    except Exception as e:
        print(f"KOSPI 수집 실패: {e}")

    try:
        # 코스닥 최근 거래일 데이터
        df_kosdaq = fdr.DataReader('KQ11')
        if not df_kosdaq.empty:
            last_close = df_kosdaq['Close'].iloc[-1]
            prev_close = df_kosdaq['Close'].iloc[-2]
            chg = last_close - prev_close
            rate = (chg / prev_close) * 100
            sign = "+" if chg > 0 else ("-" if chg < 0 else "")
            kosdaq_str = f"{last_close:,.2f} ({sign}{abs(chg):,.2f} / {sign}{abs(rate):.2f}%)"
    except Exception as e:
        print(f"KOSDAQ 수집 실패: {e}")

    try:
        # KRX 전체 상장종목 최근 시세 수집
        df_krx = fdr.StockListing('KRX')
        if not df_krx.empty:
            # 우선주, 스팩, 관리 등 필터링
            df_filtered = df_krx[~df_krx['Name'].str.contains('스팩|우$|1우|2우B|ETN|리츠', na=False, regex=True)]
            
            # 등락률(ChagesRatio) 기준 내림차순 정렬 후 상위 5개 추출
            df_sorted = df_filtered.sort_values(by='ChagesRatio', ascending=False).head(5)
            
            for _, row in df_sorted.iterrows():
                name = row.get('Name', '')
                price = row.get('Close', 0)
                rate = row.get('ChagesRatio', 0.0)
                vol = row.get('Volume', 0)
                top_stocks.append(f"- {name}: 종가 {price:,.0f}원 (등락률 +{rate:.2f}%, 거래량 {vol:,}주)")
    except Exception as e:
        print(f"종목 수집 실패: {e}")

    return {
        "kospi": kospi_str,
        "kosdaq": kosdaq_str,
        "stocks": "\n".join(top_stocks) if top_stocks else "직전 거래일 종목 데이터 수집 결과 없음"
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
아래 데이터는 시스템이 실제 거래소 데이터베이스에서 추출한 최근 거래일 공식 수치입니다.

[수집된 확정 수치]
- 코스피: {data['kospi']}
- 코스닥: {data['kosdaq']}
- 주요 급등 종목:
{data['stocks']}

[수행 지침]
1. 위 [수집된 확정 수치]에 적힌 숫자, 종목명, 등락률을 100% 그대로 유지하십시오. 절대로 다른 숫자로 바꾸지 마십시오.
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
        print("🔍 증시 데이터 수집 시작 (FinanceDataReader)...")
        data = get_verified_market_data()
        print("📝 요약 생성 중...")
        report_text = generate_brief_report(data)
        print("🚀 텔레그램 발송 시도...")
        send_telegram(report_text)
    except Exception as e:
        print(f"⚠️ 실행 예외: {e}")
