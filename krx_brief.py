import requests
import os
import datetime
import time
from pdf2image import convert_from_path
import google.generativeai as genai  # 안정적인 라이브러리로 변경

# 환경 변수
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# Gemini 설정
genai.configure(api_key=GEMINI_API_KEY)

def download_all_today_reports():
    """오늘 날짜의 모든 PDF를 POST 방식으로 탐색하여 다운로드"""
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://www.krx.co.kr/contents/SRCH/02/02030100/SRCH02030100.jsp'
    })
    
    today_str = datetime.datetime.now().strftime('%Y%m%d')
    downloaded_files = []

    print(f"🚀 {today_str} 리포트 전수 조사 시작...")
    for i in range(99, 0, -1):
        seq = f"{today_str}{i:02d}"
        try:
            otp_res = session.get("https://www.krx.co.kr/contents/COM/GenerateOTP.jspx", params={
                'name': 'fileDown', 'filetype': 'att', 
                'url': 'MKD/01/0101/01010000/mkd01010000_03', 'seq': seq
            }, timeout=3)
            
            otp = otp_res.text.strip()
            if not otp or len(otp) < 40: continue
            
            pdf_res = session.post("https://file.krx.co.kr/download.jspx", data={'code': otp}, timeout=10)
            if pdf_res.status_code == 200 and pdf_res.content.startswith(b'%PDF'):
                fname = f"KRX_{seq}.pdf"
                with open(fname, 'wb') as f: f.write(pdf_res.content)
                print(f"  ✅ 다운로드 성공: {fname}")
                downloaded_files.append(fname)
                time.sleep(0.5)
        except: continue
    return downloaded_files

def summarize_all_in_one(file_paths):
    """여러 파일을 한꺼번에 업로드하여 단 하나의 종합 요약 생성"""
    if not file_paths: return "요약할 파일이 없습니다."
    
    try:
        print(f"🤖 {len(file_paths)}개 파일 종합 분석 중...")
        # 1. 파일 업로드
        uploaded_files = []
        for path in file_paths:
            print(f"   > {path} 업로드 중...")
            uploaded_files.append(genai.upload_file(path=path))
        
        # 2. 모델 설정 및 종합 요청 (v1 안정화 모델 사용)
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = (
            f"첨부된 {len(file_paths)}개의 증시 리포트를 읽고 종합 브리핑을 작성해줘.\n"
            "1. 오늘 시장의 핵심 키워드\n"
            "2. 리포트별 주요 핵심 내용 요약\n"
            "3. 투자자가 주의 깊게 봐야 할 포인트\n"
            "위 순서로 가독성 있게 한국어로 작성해줘."
        )
        
        response = model.generate_content([prompt] + uploaded_files)
        return response.text
    except Exception as e:
        return f"종합 분석 에러: {str(e)}"

def convert_to_image(pdf_path):
    try:
        images = convert_from_path(pdf_path, dpi=200)
        if images:
            img_path = pdf_path.replace(".pdf", ".jpg")
            images[0].save(img_path, "JPEG")
            return img_path
    except: return None

def send_to_telegram(text=None, image_path=None, file_path=None):
    if text: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={'chat_id': TELEGRAM_CHAT_ID, 'text': text})
    if image_path:
        with open(image_path, 'rb') as f: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto", data={'chat_id': TELEGRAM_CHAT_ID}, files={'photo': f})
    if file_path:
        with open(file_path, 'rb') as f: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument", data={'chat_id': TELEGRAM_CHAT_ID}, files={'document': f})

if __name__ == "__main__":
    reports = download_all_today_reports()
    
    if reports:
        # 🟢 요약은 여기서 딱 한 번만 수행!
        full_summary = summarize_all_in_one(reports)
        send_to_telegram(text=f"📊 [오늘의 증시 종합 리포트]\n\n{full_summary}")
        
        # 이미지와 파일은 각각 보냄
        for report in reports:
            img = convert_to_image(report)
            if img: send_to_telegram(image_path=img)
            send_to_telegram(file_path=report)
    else:
        print("📭 리포트 없음")
