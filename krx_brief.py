import requests
import os
import datetime

def download_krx_brief_final():
    # 1. 연결 상태를 유지하는 세션 객체 생성
    session = requests.Session()
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Referer': 'https://www.krx.co.kr/main/main.jsp'
    }
    
    # 세션에 헤더 기본 적용
    session.headers.update(headers)

    try:
        # 단계 1: 입장권(OTP) 발급 요청
        print("1️⃣ 단계: 다운로드 OTP 입장권 발급 중...")
        otp_url = "https://www.krx.co.kr/contents/COM/GenerateOTP.jspx"
        otp_params = {
            'name': 'fileDown',
            'filetype': 'att',
            'url': 'MKD/01/0101/01010000/mkd01010000_03',
            'seq': '2026041721'  # 사용자님이 확인하신 최근 게시물 번호
        }
        
        otp_res = session.get(otp_url, params=otp_params)
        otp_code = otp_res.text.strip()
        
        if not otp_code:
            print("❌ OTP 발급 실패")
            return None
        
        print(f"✅ OTP 발급 성공: {otp_code[:20]}...")

        # 단계 2: 발급받은 세션 그대로 파일을 요청 (쿠키가 자동 전송됨)
        print("2️⃣ 단계: 동일 세션으로 실제 PDF 다운로드 시작...")
        download_url = "https://www.krx.co.kr/contents/COM/fileDown.jspx"
        download_params = {'code': otp_code}
        
        pdf_res = session.get(download_url, params=download_params)
        
        # 파일 크기 및 상태 확인
        if pdf_res.status_code == 200 and len(pdf_res.content) > 2000:
            file_name = f"KRX_Brief_{datetime.datetime.now().strftime('%Y%m%d')}.pdf"
            with open(file_name, 'wb') as f:
                f.write(pdf_res.content)
            print(f"🎉 성공! 파일 저장 완료: {file_name} ({len(pdf_res.content)} bytes)")
            return file_name
        else:
            print(f"❌ 다운로드 실패 (상태코드: {pdf_res.status_code}, 데이터 크기: {len(pdf_res.content)})")
            # 만약 실패했다면 서버가 보내준 응답이 무엇인지 출력해봅니다.
            if len(pdf_res.content) < 500:
                print(f"서버 응답 내용: {pdf_res.text}")
            return None

    except Exception as e:
        print(f"🚨 오류 발생: {e}")
        return None

def send_to_telegram(file_path):
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat_id: return
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    with open(file_path, 'rb') as f:
        requests.post(url, data={'chat_id': chat_id}, files={'document': f})
        print("🚀 텔레그램으로 브리프를 쐈습니다!")

if __name__ == "__main__":
    brief_file = download_krx_brief_final()
    if brief_file:
        send_to_telegram(brief_file)
