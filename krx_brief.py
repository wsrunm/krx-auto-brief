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
    """여러 파일을 종합하여 한 번에 요약합니다."""
    if not file_paths: return "요약할 파일이 없습니다."
    
    try:
        print(f"🤖 {len(file_paths)}개 파일 종합 분석 중...")
        uploaded_files = []
        for path in file_paths:
            f = genai.upload_file(path=path)
            uploaded_files.append(f)
        
        # 사용자님이 성공하신 2.5-flash 모델 사용
        model = genai.GenerativeModel('models/gemini-2.5-flash')
        prompt = "제공된 리포트들을 종합하여 핵심 내용을 한국어로 3줄 요약해줘."
        
        response = model.generate_content([prompt] + uploaded_files)
        return response.text
    except Exception as e:
        return f"요약 중 오류 발생: {str(e)}"

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
