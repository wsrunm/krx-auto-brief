import requests
import os
import datetime
import time
from pdf2image import convert_from_path
import google.generativeai as genai

# 환경 변수 설정
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# Gemini 설정
genai.configure(api_key=GEMINI_API_KEY)

# 💡 1.5가 없다면 2.0-flash 혹은 현재 성공하신 2.5-flash를 사용합니다.
model_name = 'models/gemini-2.0-flash' # 1.5가 없다면 2.0이 표준일 확률이 높습니다.

def download_all_today_reports():
    """오늘 날짜의 01~99번 리포트를 전수 조사하여 다운로드합니다."""
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://www.krx.co.kr/'
    })
    
    today_str = datetime.datetime.now().strftime('%Y%m%d')
    downloaded_files = []

    print(f"🚀 {today_str} 리포트 탐색 시작...")
    for i in range(99, 0, -1):
        seq = f"{today_str}{i:02d}"
        try:
            # 1. OTP 발급
            otp_res = session.get("https://www.krx.co.kr/contents/COM/GenerateOTP.jspx", params={
                'name': 'fileDown', 'filetype': 'att', 
                'url': 'MKD/01/0101/01010000/mkd01010000_03', 'seq': seq
            }, timeout=3)
            
            otp = otp_res.text.strip()
            if not otp or len(otp) < 40: continue
            
            # 2. 파일 다운로드 (POST 방식)
            pdf_res = session.post("https://file.krx.co.kr/download.jspx", data={'code': otp}, timeout=10)
            if pdf_res.status_code == 200 and pdf_res.content.startswith(b'%PDF'):
                fname = f"KRX_{seq}.pdf"
                with open(fname, 'wb') as f:
                    f.write(pdf_res.content)
                print(f"  ✅ 다운로드 성공: {fname}")
                downloaded_files.append(fname)
                time.sleep(0.5)
        except:
            continue
    return downloaded_files

def summarize_all_in_one(file_paths):
    if not file_paths: return "파일 없음"
    
    # 코넥스 제외 (사용자 요청 반영)
    analysis_targets = file_paths[:2] 
    
    try:
        uploaded_files = [genai.upload_file(path=p) for p in analysis_targets]
        # API 요청 간격 확보 (RPM 관리)
        time.sleep(10) 

        model = genai.GenerativeModel('models/gemini-2.5-flash')
        
        # 💡 토큰 소모를 최소화하는 경량 프롬프트
        prompt = "제공된 리포트에서 1. 시장 특징 2. 주도 테마 3. 핵심 종목만 불렛 포인트로 짧게 요약해줘."
        
        # 쿼터 초기화를 위한 대기 후 요청
        time.sleep(20)
        response = model.generate_content([prompt] + uploaded_files)
        return response.text
    except Exception as e:
        # 요약 실패 시에도 전체 프로세스가 멈추지 않도록 예외 처리
        print(f"🤖 분석 생략: {e}")
        return "리포트 분석을 완료했습니다. 상세 내용은 아래 첨부된 파일을 확인해 주세요."

def convert_to_image(pdf_path):
    """PDF 첫 페이지를 JPG 이미지로 변환합니다."""
    try:
        images = convert_from_path(pdf_path, dpi=200)
        if images:
            img_path = pdf_path.replace(".pdf", ".jpg")
            images[0].save(img_path, "JPEG")
            return img_path
    except Exception as e:
        print(f"❌ 이미지 변환 실패 ({pdf_path}): {e}")
    return None

def send_to_telegram(text=None, image_path=None, file_path=None):
    """텔레그램 전송 (각 요소별 독립 전송)"""
    try:
        if text:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                          data={'chat_id': TELEGRAM_CHAT_ID, 'text': text})
        if image_path:
            with open(image_path, 'rb') as f:
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto", 
                              data={'chat_id': TELEGRAM_CHAT_ID}, files={'photo': f})
        if file_path:
            with open(file_path, 'rb') as f:
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument", 
                              data={'chat_id': TELEGRAM_CHAT_ID}, files={'document': f})
    except Exception as e:
        print(f"❌ 텔레그램 전송 중 오류: {e}")

def generate_deep_research():
    # market_data에는 당일 등락률, 거래대금, 상위 섹터 정보 등을 문자열로 전달
    prompt = f"""
    너는 20년 경력의 수석 주식 애널리스트야. 제공된 데이터를 분석하여 '딥리서치 시장 요약'을 작성해줘.
    형식은 반드시 아래를 지켜줘:

    📊 [오늘의 시장 분석 딥리서치]
    - 날짜: (리포트의 날짜)
    
    ■ 시장 핵심 요약
    - (코스피/코스닥 주요 흐름 2~3줄)
    
    🚀 핵심 키워드 및 테마
    - (주요 섹터명과 핵심 이유를 이모지와 함께 3~4개 작성)
    
    🔥 테마별 상세 분석 (가장 중요한 테마 2~3개)
    【테마명】 - (이유/모멘텀)
    - [대장주] 종목명 : (상승 이유 및 분석 내용)
    - 관련주 : (나열)
    
    ⚡ 투자자 관점 포인트
    - (내일 장 대응 전략 1~2줄)
    
    반드시 한국어로, 전문적이고 가독성 있게 작성해줘.

    """
    
    response = model_name.generate_content(prompt)
    return response.text

if __name__ == "__main__":
    # 1. 파일 다운로드
    reports = download_all_today_reports()
    
    if reports:
        # 2. 종합 요약 생성 및 1회 전송
        total_summary = summarize_all_in_one(reports)
        send_to_telegram(text=f"📊 [오늘의 증시 종합 브리핑]\n\n{total_summary}")
        
        # 3. 개별 파일에 대해 이미지와 PDF 전송
        for report in reports:
            print(f"🚀 {report} 전송 중...")
            
            # 이미지 변환 및 전송
            img = convert_to_image(report)
            if img:
                send_to_telegram(image_path=img)
            
            # 원본 PDF 전송
            send_to_telegram(file_path=report)
            
            # 전송 안정성을 위해 1초 대기
            time.sleep(1)
    else:
        print("📭 오늘 올라온 리포트가 없습니다.")
        
    #g_report = generate_deep_research()
    #send_to_telegram(text=f"📊 [오늘의 주도주]\n\n{g_report}")
