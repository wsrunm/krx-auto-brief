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

def summarize_all_pdfs(pdf_paths):
    """여러 개의 PDF를 한꺼번에 읽어 종합 요약 생성"""
    if not GEMINI_API_KEY: return "Gemini 키 미설정"
    if not pdf_paths: return "요약할 파일이 없습니다."
    
    print(f"🤖 총 {len(pdf_paths)}개의 리포트 종합 분석 중...")
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    try:
        # 1. 모든 파일을 업로드하여 리스트로 만듭니다.
        uploaded_files = []
        for path in pdf_paths:
            print(f"   > {path} 업로드 중...")
            uploaded_files.append(client.files.upload(file=path))
        
        # 2. 모든 파일 객체와 함께 종합 요약 프롬프트를 보냅니다.
        # contents 리스트에 업로드된 모든 파일과 질문을 한꺼번에 담습니다.
        prompt = (
            f"제공된 {len(pdf_paths)}개의 증시 리포트를 모두 읽고, "
            "전체적인 시장 상황을 관통하는 핵심 내용을 '종합 브리핑' 형태로 작성해줘. "
            "1. 시장 전체 요약, 2. 주요 종목 및 수치, 3. 투자자 대응 전략 순으로 "
            "가독성 좋게 한국어로 정리해줘."
        )
        
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=uploaded_files + [prompt]
        )
        
        return response.text

    except Exception as e:
        return f"종합 분석 에러: {str(e)}"

def summarize_pdf(pdf_path):
    """Gemini 1.5-flash 고정 및 429 에러 대응 버전"""
    if not GEMINI_API_KEY: return "Gemini 키 미설정"
    
    print(f"🤖 {pdf_path} 요약 시도 중...")
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    try:
        uploaded_file = client.files.upload(file=pdf_path)
        
        # 무료 티어에서 가장 안정적인 1.5-flash 사용
        response = client.models.generate_content(
            model='gemini-1.5-flash', 
            contents=[uploaded_file, "이 리포트를 3줄 요약하고 핵심 수치를 알려줘. 한국어로 응답해줘."]
        )
        return response.text

    except Exception as e:
        error_str = str(e)
        if "429" in error_str:
            return "⚠️ 요약 실패: 구글 API 요청 제한 초과 (잠시 후 다시 시도해 주세요)."
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
    reports = download_all_today_reports()
    
    if reports:
        for report in reports:
            # 1. 요약 전송
            summary = summarize_pdf(report)
            send_to_telegram(text=f"📊 [리포트 요약: {report}]\n\n{summary}")
            
            # 2. 이미지 및 파일 전송
            img = convert_to_image(report)
            if img: send_to_telegram(image_path=img)
            send_to_telegram(file_path=report)
            
            # 💡 [핵심] 다음 리포트 처리 전 10초간 휴식 (429 에러 방지)
            print(f"⏳ 다음 파일 처리를 위해 10초 대기 중...")
            time.sleep(10) 
    else:
        print("📭 오늘 날짜 리포트 없음")
