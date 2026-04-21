import requests
import os
import datetime
from pdf2image import convert_from_path
from google import genai 
import time

# 환경 변수
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

def download_all_today_reports():
    """POST 방식을 사용하여 오늘 날짜의 모든 리포트를 탐색하고 다운로드합니다."""
    session = requests.Session()
    
    # 브라우저 로그에서 추출한 정보를 바탕으로 헤더 구성
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Referer': 'https://www.krx.co.kr/contents/SRCH/02/02030100/SRCH02030100.jsp',
        'Origin': 'https://www.krx.co.kr',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache'
    })
    
    today_str = datetime.datetime.now().strftime('%Y%m%d')
    print(f"🚀 [타겟 날짜: {today_str}] 전수 조사를 시작합니다...")

    downloaded_files = []

    # 99부터 01까지 역순으로 조사 (최신 순)
    for i in range(99, 0, -1):
        test_seq = f"{today_str}{i:02d}"
        
        try:
            # 1. OTP 발급 (GET)
            otp_res = session.get("https://www.krx.co.kr/contents/COM/GenerateOTP.jspx", params={
                'name': 'fileDown',
                'filetype': 'att',
                'url': 'MKD/01/0101/01010000/mkd01010000_03',
                'seq': test_seq
            }, timeout=5)
            
            otp_code = otp_res.text.strip()
            if not otp_code or len(otp_code) < 40: # 유효하지 않은 OTP 건너뜀
                continue
                
            # 2. 실제 파일 다운로드 (사용자 정보 반영: POST 방식)
            # 서버가 요구하는 code 값을 data(body)에 실어서 보냅니다.
            pdf_res = session.post(
                "https://file.krx.co.kr/download.jspx", 
                data={'code': otp_code}, 
                timeout=15
            )
            
            # 3. 응답이 PDF인지 확인
            if pdf_res.status_code == 200 and pdf_res.content.startswith(b'%PDF'):
                # 서버 제안 파일명이 있다면 사용, 없으면 시퀀스 번호 사용
                file_name = f"KRX_{test_seq}.pdf"
                with open(file_name, 'wb') as f:
                    f.write(pdf_res.content)
                
                print(f"  ✅ 발견 및 다운로드 성공: {file_name}")
                downloaded_files.append(file_name)
                
                # 연속 요청으로 인한 차단 방지
                time.sleep(0.5)
                
        except Exception as e:
            print(f"  ⚠️ {test_seq} 탐색 중 오류 발생 (무시하고 계속): {e}")
            continue
            
    print(f"🏁 탐색 종료. 총 {len(downloaded_files)}개의 파일을 확보했습니다.")
    return downloaded_files

def summarize_pdf(pdf_path):
    """Gemini 요약 에러(404) 해결 버전"""
    if not GEMINI_API_KEY: return "Gemini 키 미설정"
    
    print(f"🤖 {pdf_path} 분석 및 요약 중...")
    
    # 2026년 최신 SDK에서는 명시적으로 Client를 생성합니다.
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    try:
        # 1. 파일 업로드
        uploaded_file = client.files.upload(file=pdf_path)
        
        # 2. 요약 요청 (모델명에서 'models/'를 제외한 'gemini-1.5-flash'만 사용)
        # 만약 1.5-flash가 계속 404라면 'gemini-2.0-flash'로 변경해 보세요.
        response = client.models.generate_content(
            model='gemini-1.5-flash', 
            contents=[
                uploaded_file, 
                "이 리포트의 핵심 내용을 PM의 관점에서 3줄 요약하고, 투자자가 주목해야 할 수치나 종목이 있다면 알려줘. 한국어로 응답해줘."
            ]
        )
        
        # 응답 텍스트 반환
        if response and response.text:
            return response.text
        else:
            return "요약 결과가 비어 있습니다."

    except Exception as e:
        # 에러 메시지 분석 및 출력
        error_str = str(e)
        print(f"❌ 요약 실패 상세: {error_str}")
        
        # 404 에러 발생 시 모델명을 'gemini-2.0-flash'로 자동 전환 시도 (Fallback)
        if "404" in error_str:
            print("🔄 404 에러 감지: 2.0 모델로 재시도합니다...")
            try:
                response = client.models.generate_content(
                    model='gemini-2.0-flash',
                    contents=[uploaded_file, "이 리포트를 3줄 요약해줘."]
                )
                return response.text
            except:
                return f"모델을 찾을 수 없습니다. (API 설정 확인 필요): {error_str}"
        
        return f"분석 에러: {error_str}"

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
        with open(image_path, 'rb') as f: 
            requests.post(f"https://api.telegram.org/bot{token}/sendPhoto", data={'chat_id': chat_id}, files={'photo': f})
    if file_path:
        with open(file_path, 'rb') as f: 
            requests.post(f"https://api.telegram.org/bot{token}/sendDocument", data={'chat_id': chat_id}, files={'document': f})

if __name__ == "__main__":
    # 1. 오늘자 모든 리포트 긁어오기
    reports = download_all_today_reports()
    
    if reports:
        for report in reports:
            # 2. 요약 및 전송
            summary = summarize_pdf(report)
            send_to_telegram(text=f"📊 [신규 리포트 감지: {report}]\n\n{summary}")
            
            # 3. 첫 페이지 이미지 전송
            img = convert_to_image(report)
            if img: send_to_telegram(image_path=img)
            
            # 4. 원본 파일 전송
            send_to_telegram(file_path=report)
    else:
        print("📭 오늘 날짜로 생성된 리포트가 없습니다.")
