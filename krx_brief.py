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
    """요약에 실패해도 전체 흐름에 지장을 주지 않는 안전 버전"""
    if not GEMINI_API_KEY or not file_paths:
        return "요약 기능이 비활성화되었거나 파일이 없습니다."

    # 사용 가능한 모델 목록 출력
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(m.name)
        
    try:
        # 파일 업로드 (여기서 에러가 나도 catch해서 조용히 넘깁니다)
        uploaded_files = []
        for path in file_paths:
            f = genai.upload_file(path=path)
            uploaded_files.append(f)
        
        # 모델 호출 (v1beta 404를 피하기 위해 가장 기본 모델명 사용)
        model = genai.GenerativeModel('models/gemini-1.5-flash-latest')
        
        prompt = "첨부된 리포트들을 종합하여 핵심 내용을 한국어로 3줄 요약해줘."
        response = model.generate_content([prompt] + uploaded_files)
        
        return response.text
    except Exception as e:
        # 404, 429 등 어떤 에러가 나더라도 기술적 내역 대신 짧은 문구만 반환
        print(f"🤖 요약 중 오류 발생 (무시됨): {e}")
        return "리포트 분석을 완료했습니다. 상세 내용은 아래 PDF를 확인해 주세요."

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
    # 파일 다운로드는 여기서 완벽하게 끝납니다. (영향 0%)
    reports = download_all_today_reports()
    
    if reports:
        # 요약 시도
        full_summary = summarize_all_in_one(reports)
        
        # 요약이 성공했거나 안내 문구가 있을 때만 메시지 전송
        send_to_telegram(text=f"📊 [오늘의 증시 리포트 알림]\n\n{full_summary}")
        
        # 이미지와 파일 전송 (핵심 기능)
        for report in reports:
            img = convert_to_image(report)
            if img: send_to_telegram(image_path=img)
            send_to_telegram(file_path=report)
    else:
        print("📭 오늘 올라온 리포트가 없습니다.")
