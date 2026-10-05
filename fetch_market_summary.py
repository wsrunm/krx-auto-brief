import os
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai

def get_verified_market_data():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    # 1. 지수 수집
    sise_url = "https://finance.naver.com/sise/"
    res_sise = requests.get(sise_url, headers=headers, timeout=10)
    res_sise.encoding = 'cp949'  # 한글 깨짐 방지
    soup_sise = BeautifulSoup(res_sise.text, 'html.parser')
    
    kospi_elem = soup_sise.select_one("#KOSPI_now")
    kospi_change_elem = soup_sise.select_one("#KOSPI_change")
    kospi_now = kospi_elem.text.strip() if kospi_elem else "확인불가"
    kospi_change = kospi_change_elem.text.strip().replace("\n", " ") if kospi_change_elem else ""

    kosdaq_elem = soup_sise.select_one("#KOSDAQ_now")
    kosdaq_change_elem = soup_sise.select_one("#KOSDAQ_change")
    kosdaq_now = kosdaq_elem.text.strip() if kosdaq_elem else "확인불가"
    kosdaq_change = kosdaq_change_elem.text.strip().replace("\n", " ") if kosdaq_change_elem else ""
    
    # 2. 상승률 상위 종목 수집 (코스피)
    rise_url = "https://finance.naver.com/sise/sise_rise.naver?sosok=0"
    res_rise = requests.get(rise_url, headers=headers, timeout=10)
    res_rise.encoding = 'cp949'
    soup_rise = BeautifulSoup(res_rise.text, 'html.parser')
    
    top_stocks = []
    rows = soup_rise.select("table.type_2 tr")
    for row in rows:
        cols = row.find_all("td")
        if len(cols) > 5:
            name = cols[1].text.strip()
            price = cols[2].text.strip()
            rate = cols[4].text.strip().replace("\n", "").replace("\t", "")
            volume = cols[5].text.strip()
            
            # 잡주/우선주/스팩 필터링
            if any(x in name for x in ["스팩", "우", "1우", "2우B", "ETN", "리츠"]):
                continue
                
            if name:
                top_stocks.append(f"- {name}: 종가 {price}원 (등락률 {rate}, 거래량 {volume}주)")
                
        if len(top_stocks) >= 5:
            break

    return {
        "kospi": f"{kospi_now} ({kospi_change})",
        "kosdaq": f"{kosdaq_now} ({kosdaq_change})",
        "stocks": "\n".join(top_stocks) if top_stocks else "당일 상승 종목 수집 결과 없음"
    }

def generate_brief_report(data):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return f"[데이터 집계]\n코스피: {data['kospi']}\n코스닥: {data['kosdaq']}\n\n상위 종목:\n{data['stocks']}"

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    prompt = f"""
당신은 엄격한 금융 데이터 검증관입니다.
아래에 제공된 [실제 마감 수치]는 네이버 증시에서 방금 파싱한 확정 데이터입니다.

[실제 마감 수치]
- 코스피: {data['kospi']}
- 코스닥: {data['kosdaq']}
- 주요 급등 종목:
{data['stocks']}

[수행 지침]
1. 위 [실제 마감 수치]에 적힌 숫자, 종목명, 등락률을 절대로 임의로 변경하거나 다른 숫자를 지어내지 마십시오.
2. 각 종목별로 공식적인 상승 사유/테마를 사실에 기반하여 1줄로 작성하십시오.
3. 텔레그램 특수문자 오류를 방지하기 위해 마크다운 기호(*, _, [ 등)를 남발하지 마십시오.

[출력 양식]
📊 한국 증시 데일리 마감 브리프

■ 시장 마감 지수
- 코스피: {data['kospi']}
- 코스닥: {data['kosdaq']}

■ 당일 주요 급등주 및 배경
(종목별 등락률 및 사유 1줄 요약)

■ 시장 핵심 테마 코멘트
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
    
    # 마크다운 파싱 오류를 원천 차단하기 위해 기본 텍스트 모드로 안전 전송
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
        print("🔍 네이버 증시 마감 데이터 수집 시작...")
        data = get_verified_market_data()
        print("📝 요약 생성 중...")
        report_text = generate_brief_report(data)
        print("🚀 텔레그램 발송 시도...")
        send_telegram(report_text)
    except Exception as e:
        print(f"⚠️ 마켓 요약 스크립트 실행 중 예외 발생: {e}")
