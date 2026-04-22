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
    """429 에러를 피하기 위해 극단적으로 천천히 작동하는 요약 함수"""
    if not file_paths: return "파일이 없습니다."
    
    # 💡 [필독] 만약 1.5-flash가 없다면 아래 목록 중 하나씩 바꿔보세요.
    # 1순위: models/gemini-1.5-flash-8b (쿼터 제일 많음)
    # 2순위: models/gemini-1.5-flash
    # 3순위: models/gemini-2.0-flash
    model_name = 'models/gemini-1.5-flash-8b' 
    
    try:
        print(f"🤖 [{model_name}] 모델로 조심스럽게 분석을 시작합니다...")
        
        uploaded_files = []
        for path in file_paths:
            print(f"   > {path} 업로드 중...")
            f = genai.upload_file(path=path)
            uploaded_files.append(f)
            # 파일 하나 올릴 때마다 15초씩 쉽니다 (요청 분산)
            time.sleep(15) 

        # 💡 모든 파일 업로드 후, 요약 요청 전 30초간 '완전 휴식'
        # 이 과정이 429 에러를 피하는 핵심 포인트입니다.
        print("⏳ 구글 서버의 쿼터 리셋을 위해 30초간 대기합니다...")
        time.sleep(30)

        model = genai.GenerativeModel(model_name)
        
        # 🎯 사용자님이 요청하신 '딥리서치' 스타일 프롬프트
        prompt = """
        오늘의 증시 리포트들을 심층 분석하여 '급등주 시장분석 딥리서치'를 작성해줘.
        1. 시장 핵심 요약 (코스피/코스닥 종가 및 등락 포함)
        2. 급등주 핵심 키워드 10개 (등락폭 큰 순서대로)
        3. 각 키워드별 주요 종목과 등락률, 매매대금, 수급 특징 분석
        4. 테마별 심층 분석 및 내일 장 전망
        한국어로 전문 애널리스트처럼 상세하게 작성해줘.
        """
        
        response = model.generate_content([prompt] + uploaded_files)
        return response.text

    except Exception as e:
        error_msg = str(e)
        print(f"❌ 요약 실패 원인: {error_msg}")
        
        # 만약 모델명이 틀렸다는 에러(404)가 나면 2.0으로 자동 전환 시도
        if "404" in error_msg and "2.0" not in model_name:
            print("🔄 모델명을 찾을 수 없어 2.0-flash로 재시도합니다...")
            time.sleep(20)
            # 재시도 로직...
            
        return "🤖 리포트 분석 중 API 제한이 발생했습니다. 잠시 후 수동으로 [Run workflow]를 눌러보세요."
        
#def summarize_all_in_one(file_paths):
    """요약에 실패해도 전체 흐름에 지장을 주지 않는 안전 버전"""
 """   if not GEMINI_API_KEY or not file_paths:
        return "요약 기능이 비활성화되었거나 파일이 없습니다."
    
    try:
        # 파일 업로드 (여기서 에러가 나도 catch해서 조용히 넘깁니다)
        uploaded_files = []
        for path in file_paths:
            f = genai.upload_file(path=path)
            uploaded_files.append(f)
        
        # 모델 호출 (v1beta 404를 피하기 위해 가장 기본 모델명 사용)
        model = genai.GenerativeModel('models/gemini-2.5-flash')
        
        prompt = "첨부된 리포트들을 종합하여 핵심 내용을 한국어로 3줄 요약해줘."
        response = model.generate_content([prompt] + uploaded_files)
        
        return response.text
    except Exception as e:
        # 404, 429 등 어떤 에러가 나더라도 기술적 내역 대신 짧은 문구만 반환
        print(f"🤖 요약 중 오류 발생 (무시됨): {e}")
        return "리포트 분석을 완료했습니다. 상세 내용은 아래 PDF를 확인해 주세요."
"""
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
