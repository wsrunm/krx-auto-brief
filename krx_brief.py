import requests
import os
import datetime
import re

def get_latest_seq():
    """게시판에서 최신 게시물의 고유번호(seq)를 추출합니다."""
    list_url = "https://www.krx.co.kr/contents/SRCH/02/02030100/SRCH02030100.jsp"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    }
    try:
        res = requests.get(list_url, headers=headers)
        # downFile('숫자', ...) 형태에서 숫자만 추출
        match = re.search(r"downFile\('(\d+)'", res.text)
        if match:
            return match.group(1)
        return "2026041721" # 실패 시 예비용 (금요일 번호)
    except:
        return "2026041721"

def download_krx_brief():
    session = requests.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Referer': 'https://www.krx.co.kr/'
    }
    session.headers.update(headers)

    try:
        # 1. 최신 seq 번호 자동 획득
        seq = get_latest_seq()
        print(f"🔍 최신 게시물 번호 확인: {seq}")

        # 2. OTP 발급 (www 서버)
        otp_url = "https://www.krx.co.kr/contents/COM/GenerateOTP.jspx"
        otp_params = {
            'name': 'fileDown',
            'filetype': 'att',
            'url': 'MKD/01/0101/01010000/mkd01010000_03',
            'seq': seq
        }
        otp_res = session.get(otp_url, params=otp_params)
        otp_code = otp_res.text.strip()
        
        if not otp_code:
            return None

        # 3. 실제 파일 다운로드 (사용자님이 찾으신 file 서버 타격)
        # fileDown.jspx 대신 download.jspx 사용
        download_url = "https://file.krx.co.kr/download.jspx"
        download_params = {'code': otp_code}
        
        print(f"📥 파일 서버 접속 중: {download_url}")
        pdf_res = session.get(download_url, params=download_params)
        content = pdf_res.content

        # 4. 진짜 PDF인지 최종 검증
        if content.startswith(b'%PDF'):
            file_name = f"KRX_Brief_{datetime.datetime.now().strftime('%Y%m%d')}.pdf"
            with open(file_name, 'wb') as f:
                f.write(content)
            print(f"✅ 다운로드 성공: {file_name} ({len(content)} bytes)")
            return file_name
        else:
            print("❌ 다운로드된 데이터가 PDF 형식이 아닙니다.")
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
    brief_file = download_krx_brief()
    if brief_file:
        send_to_telegram(brief_file)
