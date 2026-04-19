import requests
import os
import datetime

def download_krx_brief_final():
    session = requests.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Referer': 'https://www.krx.co.kr/main/main.jsp'
    }
    session.headers.update(headers)

    try:
        # 1단계: OTP 발급
        print("1️⃣ 단계: 다운로드 OTP 입장권 발급 중...")
        otp_url = "https://www.krx.co.kr/contents/COM/GenerateOTP.jspx"
        otp_params = {
            'name': 'fileDown',
            'filetype': 'att',
            'url': 'MKD/01/0101/01010000/mkd01010000_03',
            'seq': '2026041721' 
        }
        
        otp_res = session.get(otp_url, params=otp_params)
        otp_code = otp_res.text.strip()
        
        if not otp_code:
            print("❌ OTP 발급 실패")
            return None
        
        # 2단계: 파일 다운로드
        print("2️⃣ 단계: 실제 PDF 다운로드 시작...")
        download_url = "https://www.krx.co.kr/contents/COM/fileDown.jspx"
        download_params = {'code': otp_code}
        
        pdf_res = session.get(download_url, params=download_params)
        
        # [핵심 수정] 404여도 데이터 크기가 50,000바이트(약 50KB) 이상이면 PDF로 간주합니다.
        data_size = len(pdf_res.content)
        if data_size > 50000:
            file_name = f"KRX_Brief_{datetime.datetime.now().strftime('%Y%m%d')}.pdf"
            with open(file_name, 'wb') as f:
                f.write(pdf_res.content)
            print(f"🎉 성공! 상태코드 {pdf_res.status_code}에도 불구하고 파일 저장 완료: {file_name} ({data_size} bytes)")
            return file_name
        else:
            print(f"❌ 다운로드 실패 (데이터 크기가 너무 작음: {data_size} bytes)")
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
        print("🚀 텔레그램 전송 완료!")

if __name__ == "__main__":
    brief_file = download_krx_brief_final()
    if brief_file:
        send_to_telegram(brief_file)
