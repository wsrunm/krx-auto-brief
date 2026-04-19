import requests
import os
import datetime
import re
import json
from pdf2image import convert_from_path
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# 1. 환경 설정
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
GDRIVE_JSON = os.environ.get('GDRIVE_SERVICE_ACCOUNT')
# 구글 드라이브 폴더 ID (폴더 주소창 마지막 문자열)
GDRIVE_FOLDER_ID = "1RTldCqq_DfDwuxESYzzbqqgF--mBqxSF" 

# Gemini 설정
genai.configure(api_key=GEMINI_API_KEY)

def summarize_pdf(pdf_path):
    """Gemini API를 사용하여 PDF 요약 생성"""
    print("🤖 Gemini가 리포트를 분석 중입니다...")
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    # PDF 파일 업로드 및 분석
    sample_file = genai.upload_file(path=pdf_path, display_name="KRX Brief")
    response = model.generate_content([sample_file, "이 증시 브리프 리포트의 핵심 내용을 3줄로 요약하고, 투자자가 주의 깊게 봐야 할 지표를 알려줘. 한국어로 응답해줘."])
    return response.text

def upload_to_gdrive(file_path):
    """구글 드라이브에 파일 업로드 (NotebookLM 연동용)"""
    if not GDRIVE_JSON: return
    
    print("☁️ 구글 드라이브 업로드 중...")
    info = json.loads(GDRIVE_JSON)
    creds = service_account.Credentials.from_service_account_info(info)
    service = build('drive', 'v3', credentials=creds)

    file_metadata = {
        'name': os.path.basename(file_path),
        'parents': [GDRIVE_FOLDER_ID]
    }
    media = MediaFileUpload(file_path, mimetype='application/pdf')
    service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    print("✅ 구글 드라이브 업로드 완료")

# ... (이전에 작성한 get_latest_seq, download_krx_brief, convert_to_image 함수 유지) ...

def send_to_telegram(text=None, image_path=None, file_path=None):
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    if text:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, data={'chat_id': chat_id, 'text': text})
    
    if image_path:
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        with open(image_path, 'rb') as f:
            requests.post(url, data={'chat_id': chat_id}, files={'photo': f})

    if file_path:
        url = f"https://api.telegram.org/bot{token}/sendDocument"
        with open(file_path, 'rb') as f:
            requests.post(url, data={'chat_id': chat_id}, files={'document': f})

if __name__ == "__main__":
    pdf_file = download_krx_brief()
    if pdf_file:
        # 1. Gemini 요약 생성 및 전송
        try:
            summary = summarize_pdf(pdf_file)
            send_to_telegram(text=f"📝 [Gemini 요약]\n\n{summary}")
        except Exception as e:
            print(f"요약 실패: {e}")

        # 2. 이미지 변환 및 전송
        img_file = convert_to_image(pdf_file)
        if img_file:
            send_to_telegram(image_path=img_file)
        
        # 3. 원본 PDF 전송
        send_to_telegram(file_path=pdf_file)

        # 4. 구글 드라이브 업로드 (NotebookLM용)
        try:
            upload_to_gdrive(pdf_file)
        except Exception as e:
            print(f"드라이브 업로드 실패: {e}")

