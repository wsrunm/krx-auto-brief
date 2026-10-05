import os
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai

# ---------------------------------------------------------
# 1. 100% 실측 데이터 스크래핑 (네이버 증시 마감 데이터)
# ---------------------------------------------------------
def get_verified_market_data():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    # 지수 수집
    sise_url = "https://finance.naver.com/sise/"
    res_sise = requests.get(sise_url, headers=headers)
    soup_sise = BeautifulSoup(res_sise.text, 'html.parser')
    
    kospi_now = soup_sise.select_one("#KOSPI_now").text.strip()
    kospi_change = soup_sise.select_one("#KOSPI_change").text.strip().replace("\n", " ")
    
    kosdaq_now = soup_sise.select_one("#KOSDAQ_now").text.strip()
    kosdaq_change = soup_sise.select_one("#KOSDAQ_change").text.strip().replace("\n", " ")
    
    # 코스피 상승 상위 5종목 수집 (우선주/스팩 필터링)
    rise_url = "https://finance.naver.com/sise/sise_rise.naver?sosok=0"
    res_rise = requests.get(rise_url, headers=headers)
    soup_rise = BeautifulSoup(res_rise.text, 'html.parser')
    
    top_stocks = []
    rows = soup_rise.select("table.type_2 tr")[2:]
    for row in rows:
        cols = row.find_all("td")
        if len(cols) > 5:
            name = cols[1].text.strip()
            price = cols[2].text.strip()
            rate = cols[4].text.strip().replace("\n", "").replace("\t", "")
            volume = cols[5].text.strip()
            
            # 우선주, 스팩, 관리종목 등 잡주 1차 필터링
            if any(x in name for x in ["스팩", "우", "1우", "2우B"]):
                continue
                
            if name:
                top_stocks.append(f"- {name}: 종가 {price}원 (등락률 {rate}, 거래량 {volume}주)")
                
        if len(top_stocks) >= 5:
            break

    return {
        "kospi": f"{kospi_now} ({kospi_change})",
        "kosdaq": f"{kosdaq_now} ({kosdaq_change})",
        "stocks": "\n".join(top_stocks)
    }

# ---------------------------------------------------------
# 2. AI 팩트 기반 요약 (수치 왜곡 방지 프롬프트 주입)
# ---------------------------------------------------------
def generate_brief_report(data):
    api_key = os.getenv("GEMINI_API_KEY")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    prompt = f"""
당신은 엄격한 금융 데이터 검증관입니다.
아래에 제공된 [실제 마감 수치]는 네이버 증시에서 방금 파싱한 100% 확정 데이터입니다.

[실제 마감 수치]
- 코스피: {data['kospi']}
- 코스닥: {data['kosdaq']}
- 주요 급등 종목:
{data['stocks']}

[수행 지침 - 엄격 준수]
1. 위 [실제 마감 수치]에 적힌 숫자, 종목명, 등락률, 지수 포인트를 단 1자도 임의로 수정하거나 추정치로 바꾸지 마십시오.
2. 각 급등 종목별로 오늘 장중에 알려진 공식 상승 배경(실적, 수주 공시, 산업 이슈 등)을 사실 기반으로 1줄씩 간결하게 작성하십시오.
3. 최종 텔레그램 메시지 규격에 맞춰 아래 형식으로 출력하십시오. 마크다운 기호를 과하게 쓰지 마십시오.

[출력 양식 예시]
📊 **한국 증시 데일리 마감 브리프**

🔹 **시장 마감 지수**
- 코스피: {data['kospi']}
- 코스닥: {data['kosdaq']}

🔥 **당일 주요 급등주 및 상승 배경**
(제공된 종목 리스트를 바탕으로 각각 종목명 / 등락률 / 상승 사유 1줄 요약)

💡 **시장 핵심 테마 코멘트**
(상승 종목들의 공통 테마 2~3줄 요약)
"""
    response = model.generate_content(prompt)
    return response.text

# ---------------------------------------------------------
# 3. 텔레그램 메시지 발송
# ---------------------------------------------------------
def send_telegram(text):
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    res = requests.post(url, json=payload, timeout=10)
    if res.status_code == 200:
        print("✅ 텔레그램 리포트 발송 완료!")
    else:
        print(f"❌ 발송 실패: {res.text}")

if __name__ == "__main__":
    print("🔍 네이버 증시 실시간 마감 데이터 수집 시작...")
    data = get_verified_market_data()
    print("📝 Gemini 기반 테마 요약 생성 중...")
    report_text = generate_brief_report(data)
    print("🚀 텔레그램 전송 중...")
    send_telegram(report_text)
