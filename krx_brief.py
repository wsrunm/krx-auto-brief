import requests
import os
import datetime
import re
import json
from pdf2image import convert_from_path
from google import genai # 최신 SDK
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# 환경 변수 설정
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
GDRIVE_JSON = os.environ.get('GDRIVE_SERVICE_ACCOUNT')
# 사용자님의 구글 드라이브 폴더 ID를 여기에 입력하세요
GDRIVE_FOLDER_ID = "1RTldCqq_DfDwuxESYzzbqqgF--mBqxSF" 

def get_latest_seq():
    """게시판에서 최신 게시물 번호를 가져옵니다."""
    try:
        list_url = "https://www.krx.co.kr/contents/SRCH/02/02030100/SRCH02030100.jsp"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        res = requests.get(list_url, headers=headers, timeout=10)
        match = re.search(r"downFile\('(\d+)'", res.text)
        return match.group(1) if match else "2026041721"
    except:
        return "2026041721"

def download_krx_brief():
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Referer': 'https://www.krx.co.kr/'})
    try:
        seq = get_latest_seq()
        otp_res = session.get("https://www.krx.co.kr/contents/COM/GenerateOTP.jspx", params={'name': 'fileDown', 'filetype': 'att', 'url': 'MKD/01/0101/01010000/mkd01010000_03', 'seq': seq})
        pdf_res = session.get("https://file.krx.co.kr/download.jspx", params={'code': otp_res.text.strip()})
        if pdf_res.content.startswith(b'%PDF'):
            file_name = f"KRX_Brief_{datetime.datetime.now().strftime('%Y%m%d')}.pdf"
            with open(file_name, 'wb') as f:
                f.write(pdf_res.content)
            return file_name
    except Exception as e:
        print(f"❌ 다운로드 오류: {e}")
    return None

def summarize_pdf(pdf_path):
    """Gemini 요약 (문법 수정 완료)"""
    if not GEMINI_API_KEY: return "Gemini 키가 없습니다."
    print("🤖 Gemini 분석 중...")
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    # 수정 포인트: path= 대신 file= 사용
    uploaded_file = client.files.upload(file=pdf_path)
    
    response = client.models.generate_content(
        model='gemini-1.5-flash',
        contents=[uploaded_file, "이 증시 브리프 리포트의 핵심 내용을 3줄로 요약하고, 투자자가 주의 깊게 봐야 할 지표를 알려줘. 한국어로 응답해줘."]
    )
    return response.text

def convert_to_image(pdf_path):
    try:
        images = convert_from_path(pdf_path, dpi=200)
        if images:
            img_path = pdf_path.replace(".pdf", ".jpg")
            images[0].save(img_path, "JPEG")
            return img_path
    except Exception as e:
        print(f"❌ 이미지 변환 실패: {e}")
    return None

def upload_to_gdrive(file_path):
    """구글 드라이브 업로드 (데이터 체크 추가)"""
    if not GDRIVE_JSON or len(GDRIVE_JSON.strip()) < 10:
        raise ValueError("GDRIVE_SERVICE_ACCOUNT Secret이 비어있거나 너무 짧습니다.")
    
    print("☁️ 구글 드라이브 업로드 중...")
    info = json.loads(GDRIVE_JSON)
    creds = service_account.Credentials.from_service_account_info(info)
    service = build('drive', 'v3', credentials=creds)
    file_metadata = {'name': os.path.basename(file_path), 'parents': [GDRIVE_FOLDER_ID]}
    media = MediaFileUpload(file_path, mimetype='application/pdf')
    service.files().create(body=file_metadata, media_body=media, fields='id').execute()

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
        print(f"✅ 파일 준비 완료: {pdf_file}")
        try:
            summary = summarize_pdf(pdf_file)
            send_to_telegram(text=f"📝 [오늘의 시황 요약]\n\n{summary}")
            print("✅ 요약 전송 완료")
        except Exception as e: print(f"❌ 요약 실패 원인: {e}")
        
        img_file = convert_to_image(pdf_file)
        if img_file: 
            send_to_telegram(image_path=img_file)
            print("✅ 이미지 전송 완료")
            
        send_to_telegram(file_path=pdf_file)
        print("✅ 원본 전송 완료")
        
        try:
            upload_to_gdrive(pdf_file)
            print("✅ 구글 드라이브 업로드 완료")
        except Exception as e: print(f"❌ 드라이브 업로드 실패 원인: {e}")
