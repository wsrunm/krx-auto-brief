import requests
import os
import datetime

def download_krx_brief_with_otp():
    # 1. 입장권(OTP)을 발급받는 주소
    otp_url = "https://www.krx.co.kr/contents/COM/GenerateOTP.jspx"
    
    # 사용자님이 찾으신 파라미터 정보 적용
    # seq 부분은 게시판의 최신 ID를 가져와야 하므로, 우선 사용자님이 확인한 최신값(2026041721)을 예시로 하되
    # 실제로는 게시판에서 이 숫자를 낚아채는 로직이 포함됩니다.
    otp_params = {
        'name': 'fileDown',
        'filetype': 'att',
        'url': 'MKD/01/0101/01010000/mkd01010000_03',
        'seq': '2026041721' # 이 숫자가 매일 바뀝니다.
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Referer': 'https://www.krx.co.kr/main/main.jsp'
    }

    try:
        print("1️⃣ 단계: 다운로드 OTP 입장권 발급 중...")
        # GET 방식으로 입장권 코드를 요청합니다.
        otp_res = requests.get(otp_url, params=otp_params, headers=headers)
        otp_code = otp_res.text # 여기서 받은 코드가 진짜 입장권입니다.
        
        if not otp_code:
            print("❌ OTP 발급 실패")
            return None
        
        print(f"✅ OTP 발급 성공: {otp_code}")

        # 2️⃣ 단계: 받은 OTP를 들고 실제 파일 다운로드 주소로 이동
        download_url = "https://www.krx.co.kr/contents/COM/fileDown.jspx"
        download_params = {
            'code': otp_code # 방금 받은 입장권을 제출합니다.
        }
        
        print("2️⃣ 단계: 실제 PDF 파일 다운로드 시작...")
        pdf_res = requests.get(download_url, params=download_params, headers=headers)
        
        if pdf_res.status_code == 200 and len(pdf_res.content) > 1000:
            file_name = f"KRX_Brief_{datetime.datetime.now().strftime('%Y%m%d')}.pdf"
            with open(file_name, 'wb') as f:
                f.write(pdf_res.content)
            print(f"🎉 최종 다운로드 성공: {file_name}")
            return file_name
        else:
            print("❌ 파일 다운로드 실패 (OTP가 만료되었거나 권한이 없습니다.)")
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
    brief_file = download_krx_brief_with_otp()
    if brief_file:
        send_to_telegram(brief_file)
