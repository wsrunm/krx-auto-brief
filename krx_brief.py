import requests
import os
import datetime
from pdf2image import convert_from_path
from google import genai 

# 환경 변수 (GitHub Secrets에서 가져옴)
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

def download_krx_brief_direct():
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Referer': 'https://www.krx.co.kr/'
    })
    
    # 1. 오늘 날짜 구하기 (예: 20260421)
    today_str = datetime.datetime.now().strftime('%Y%m%d')
    print(f"🎯 타겟 날짜: {today_str} | 파일 탐색 시작...")

    # 2. 뒤의 2자리 숫자를 99부터 01까지 역순으로 모두 찔러봅니다.
    # 역순으로 하는 이유: 가장 마지막에 올라온(숫자가 큰) 파일이 최신 브리프일 확률이 높기 때문입니다.
    for i in range(99, 0, -1):
        test_seq = f"{today_str}{i:02d}" # 예: 2026042199, 2026042198 ...
        
        try:
            # OTP 발급 시도
            otp_res = session.get("https://www.krx.co.kr/contents/COM/GenerateOTP.jspx", params={
                'name': 'fileDown', 
                'filetype': 'att', 
                'url': 'MKD/01/0101/01010000/mkd01010000_03', 
                'seq': test_seq
            }, timeout=3) # 빠른 탐색을 위해 타임아웃을 짧게 줍니다.
            
            otp_code = otp_res.text.strip()
            
            # OTP 코드가 정상적으로 발급되지 않았으면 (없는 번호면) 다음 번호로 넘어갑니다.
            if not otp_code or len(otp_code) < 50:
                continue 
                
            # OTP 코드가 발급되었다면, 실제 파일 다운로드를 시도합니다.
            print(f"   > 후보 번호 발견: {test_seq} (다운로드 시도 중...)")
            pdf_res = session.get("https://file.krx.co.kr/download.jspx", params={'code': otp_code}, timeout=10)
            
            # 3. 진짜 PDF 파일이 맞는지 검증합니다. (HTML 에러 페이지 걸러내기)
            if pdf_res.status_code == 200 and pdf_res.content.startswith(b'%PDF'):
                file_name = f"KRX_Brief_{test_seq}.pdf"
                with open(file_name, 'wb') as f:
                    f.write(pdf_res.content)
                print(f"✅ 빙고! 오늘자 파일 다운로드 성공: {file_name} ({len(pdf_res.content):,} bytes)")
                return file_name
            else:
                print(f"   > {test_seq}는 가짜 파일(또는 에러 페이지)입니다. 계속 탐색합니다.")
                
        except Exception as e:
            # 네트워크 오류 등이 발생해도 멈추지 않고 다음 번호를 계속 탐색합니다.
            continue
            
    print(f"❌ 오늘({today_str}) 업로드된 파일을 찾지 못했습니다.")
    return None

def summarize_pdf(pdf_path):
    """Gemini 1.5 Flash 모델을 사용한 요약"""
    if not GEMINI_API_KEY: return "Gemini API 키가 설정되지 않았습니다."
    
    print("🤖 Gemini가 리포트를 분석 중입니다...")
    client = genai.Client(api_key=GEMINI_API_KEY)
    try:
        # 파일을 Google AI Studio에 업로드
        uploaded_file = client.files.upload(file=pdf_path)
        
        # 요약 요청
        response = client.models.generate_content(
            model='gemini-1.5-flash', 
            contents=[
                uploaded_file, 
                "이 증시 브리프 리포트의 핵심 내용을 투자 관점에서 3줄로 요약하고, 특이사항이 있다면 간략히 알려줘. 한국어로 응답해줘."
            ]
        )
        return response.text
    except Exception as e:
        print(f"❌ 요약 실패: {e}")
        return f"요약 중 에러가 발생했습니다: {str(e)}"

def convert_to_image(pdf_path):
    """PDF 첫 페이지를 이미지(JPG)로 변환"""
    try:
        images = convert_from_path(pdf_path, dpi=200)
        if images:
            img_path = pdf_path.replace(".pdf", ".jpg")
            images[0].save(img_path, "JPEG")
            return img_path
    except Exception as e:
        print(f"❌ 이미지 변환 실패: {e}")
    return None

def send_to_telegram(text=None, image_path=None, file_path=None):
    """텔레그램으로 텍스트, 이미지, 파일을 전송"""
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    if not token or not chat_id:
        print("⚠️ 텔레그램 토큰 또는 Chat ID가 설정되지 않았습니다.")
        return
        
    try:
        if text: 
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={'chat_id': chat_id, 'text': text})
        if image_path:
            with open(image_path, 'rb') as f: 
                requests.post(f"https://api.telegram.org/bot{token}/sendPhoto", data={'chat_id': chat_id}, files={'photo': f})
        if file_path:
            with open(file_path, 'rb') as f: 
                requests.post(f"https://api.telegram.org/bot{token}/sendDocument", data={'chat_id': chat_id}, files={'document': f})
    except Exception as e:
        print(f"❌ 텔레그램 전송 실패: {e}")

if __name__ == "__main__":
    # 1. 파일 다운로드 (무차별 대입 방식)
    pdf_file = download_krx_brief_direct()
    
    if pdf_file:
        # 2. 요약 생성 및 전송
        summary = summarize_pdf(pdf_file)
        send_to_telegram(text=f"📝 [오늘의 시황 요약]\n\n{summary}")
        
        # 3. 이미지 변환 및 전송
        img_file = convert_to_image(pdf_file)
        if img_file: 
            send_to_telegram(image_path=img_file)
            
        # 4. 원본 파일 전송
        send_to_telegram(file_path=pdf_file)
