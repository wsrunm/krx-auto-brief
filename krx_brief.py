import requests
import os
import datetime
import re
from pdf2image import convert_from_path

def get_latest_seq():
    """게시판에서 최신 게시물 번호를 자동으로 가져옵니다."""
    try:
        list_url = "https://www.krx.co.kr/contents/SRCH/02/02030100/SRCH02030100.jsp"
        res = requests.get(list_url, timeout=10)
        match = re.search(r"downFile\('(\d+)'", res.text)
        return match.group(1) if match else "2026041721"
    except:
        return "2026041721"

def download_krx_brief():
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Referer': 'https://www.krx.co.kr/'
    })

    try:
        seq = get_latest_seq()
        # 1. OTP 발급
        otp_res = session.get("https://www.krx.co.kr/contents/COM/GenerateOTP.jspx", params={
            'name': 'fileDown', 'filetype': 'att', 
            'url': 'MKD/01/0101/01010000/mkd01010000_03', 'seq': seq
        })
        otp_code = otp_res.text.strip()

        # 2. 파일 다운로드
        pdf_res = session.get("https://file.krx.co.kr/download.jspx", params={'code': otp_code})
        
        if pdf_res.content.startswith(b'%PDF'):
            file_name = f"KRX_Brief_{datetime.datetime.now().strftime('%Y%m%d')}.pdf"
            with open(file_name, 'wb') as f:
                f.write(pdf_res.content)
            return file_name
    except Exception as e:
        print(f"다운로드 중 오류: {e}")
    return None

def convert_to_image(pdf_path):
    """PDF의 첫 페이지를 JPG로 변환합니다."""
    try:
        # DPI 200으로 설정하여 선명하게 변환
        images = convert_from_path(pdf_path, dpi=200)
        if images:
            img_path = pdf_path.replace(".pdf", ".jpg")
            images[0].save(img_path, "JPEG")
            return img_path
    except Exception as e:
        print(f"이미지 변환 실패: {e}")
    return None

def send_to_telegram(file_path, is_image=False):
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    # 이미지면 sendPhoto, 파일이면 sendDocument 사용
    method = "sendPhoto" if is_image else "sendDocument"
    url = f"https://api.telegram.org/bot{token}/{method}"
    
    with open(file_path, 'rb') as f:
        payload = {'chat_id': chat_id}
        if is_image:
            payload['caption'] = f"📊 오늘자 KRX 증시 브리프 ({datetime.datetime.now().strftime('%Y-%m-%d')})"
            files = {'photo': f}
        else:
            files = {'document': f}
        requests.post(url, data=payload, files=files)

if __name__ == "__main__":
    pdf_file = download_krx_brief()
    if pdf_file:
        # 1. 이미지로 변환해서 먼저 보내기 (채팅창에서 바로 보임)
        img_file = convert_to_image(pdf_file)
        if img_file:
            send_to_telegram(img_file, is_image=True)
        
        # 2. 원본 PDF 파일도 같이 보내기 (보관용)
        send_to_telegram(pdf_file, is_image=False)
