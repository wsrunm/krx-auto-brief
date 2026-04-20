import requests
import os
import datetime
import re
import json
from pdf2image import convert_from_path
from google import genai 
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# 환경 변수
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
GDRIVE_JSON = os.environ.get('GDRIVE_SERVICE_ACCOUNT')
GDRIVE_FOLDER_ID = "사용자님의_폴더_ID_입력" 

def get_latest_seq():
    """게시판에서 모든 번호를 찾아 그중 가장 큰(최신) 번호를 반환합니다."""
    try:
        list_url = "https://www.krx.co.kr/contents/SRCH/02/02030100/SRCH02030100.jsp"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache' # 서버 캐시 방지
        }
        res = requests.get(list_url, headers=headers, timeout=10)
        
        # 소스 내의 모든 downFile('숫자') 패턴 추출
        all_ids = re.findall(r"downFile\('(\d+)'", res.text)
        
        if all_ids:
            # 숫자 중 가장 큰 값이 최신 게시물임
            latest_id = max(all_ids)
            print(f"📊 발견된 최신 ID: {latest_id}")
            return latest_id
        return "2026041721" # 실패 시 금요일 데이터 fallback
    except Exception as e:
        print(f"ID 추출 실패: {e}")
        return "2026041721"

def download_krx_brief():
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://www.krx.co.kr/'
    })
    try:
        seq = get_latest_seq()
        today_str = datetime.datetime.now().strftime('%Y%m%d')
        
        # 오늘 날짜와 ID 비교 (검증용)
        if not seq.startswith(today_str):
            print(f"⚠️ 경고: 최신 ID({seq})가 오늘 날짜({today_str})와 일치하지 않습니다. 아직 업데이트 전일 수 있습니다.")
        
        otp_res = session.get("https://www.krx.co.kr/contents/COM/GenerateOTP.jspx", params={
            'name': 'fileDown', 'filetype': 'att', 
            'url': 'MKD/01/0101/01010000/mkd01010000_03', 'seq': seq
        })
        
        pdf_res = session.get("https://file.krx.co.kr/download.jspx", params={'code': otp_res.text.strip()})
        
        if pdf_res.content.startswith(b'%PDF'):
            # 파일명에 실제 게시물 ID를 포함하여 혼동 방지
            file_name = f"KRX_Brief_{today_str}_{seq}.pdf"
            with open(file_name, 'wb') as f:
                f.write(pdf_res.content)
            return file_name
    except Exception as e:
        print(f"❌ 다운로드 오류: {e}")
    return None

# ... (summarize_pdf, convert_to_image, upload_to_gdrive 함수는 이전과 동일) ...

def summarize_pdf(pdf_path):
    if not GEMINI_API_KEY: return "Gemini 키 미설정"
    client = genai.Client(api_key=GEMINI_API_KEY)
    try:
        uploaded_file = client.files.upload(file=pdf_path)
        response = client.models.generate_content(
            model='gemini-1.5-flash', 
            contents=[uploaded_file, "이 증시 브리프 리포트의 핵심 내용을 3줄로 요약하고 특이사항을 알려줘. 한국어로 응답해줘."]
        )
        return response.text
    except Exception as e: return f"요약 에러: {str(e)}"

def convert_to_image(pdf_path):
    try:
        images = convert_from_path(pdf_path, dpi=200)
        if images:
            img_path = pdf_path.replace(".pdf", ".jpg")
            images[0].save(img_path, "JPEG")
            return img_path
    except: return None

def send_to_telegram(text=None, image_path=None, file_path=None):
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if text: requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={'chat_id': chat_id, 'text': text})
    if image_path:
        with open(image_path, 'rb') as f: requests.post(f"https://api.telegram.org/bot{token}/sendPhoto", data={'chat_id': chat_id}, files={'photo': f})
    if file_path:
        with open(file_path, 'rb') as f: requests.post(f"https://api.telegram.org/bot{token}/sendDocument", data={'chat_id': chat_id}, files={'document': f})

if __name__ == "__main__":
    pdf_file = download_krx_brief()
    if pdf_file:
        # 요약 및 전송
        summary = summarize_pdf(pdf_file)
        send_to_telegram(text=f"📝 [오늘의 시황 요약]\n\n{summary}")
        
        img_file = convert_to_image(pdf_file)
        if img_file: send_to_telegram(image_path=img_file)
        send_to_telegram(file_path=pdf_file)
