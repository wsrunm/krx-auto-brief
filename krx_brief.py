import requests
import os
import datetime
import re

def download_krx_brief():
    # 1. 실제 데이터 요청 주소 (KRX 내부 검색 엔진)
    api_url = "https://www.krx.co.kr/contents/COM/Search.jspx"
    
    # 2. "간행물 게시판의 목록을 달라"는 요청서 (핵심!)
    payload = {
        'id': 'SRCH02030100', # 간행물 게시판 고유 ID
        'pagePath': '/contents/SRCH/02/02030100/SRCH02030100.jsp',
        'code': '',
        'pageSize': '1',      # 딱 맨 위 1개만 가져옴
        'pageIndex': '1'
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.krx.co.kr/contents/SRCH/02/02030100/SRCH02030100.jsp'
    }

    try:
        # 데이터 목록 요청
        response = requests.post(api_url, data=payload, headers=headers)
        data = response.json() # KRX는 목록을 JSON 형식으로 줍니다.

        # 3. 목록에서 가장 첫 번째 게시물의 파일 ID 추출
        if not data.get('block1'):
            print("게시물을 찾을 수 없습니다.")
            return None
        
        # 최상단 게시물의 정보
        first_post = data['block1'][0]
        file_id = first_post['file_id'] # 파일 고유 번호
        title = first_post['title']     # 게시물 제목
        
        print(f"최신 간행물 발견: {title}")

        # 4. 실제 PDF 다운로드 경로 생성
        download_url = f"https://www.krx.co.kr/contents/COM/GeneratePDF.jspx?u={file_id}"
        
        file_name = f"KRX_Brief_{datetime.datetime.now().strftime('%Y%m%d')}.pdf"

        # 파일 저장
        pdf_res = requests.get(download_url, headers=headers)
        with open(file_name, 'wb') as f:
            f.write(pdf_res.content)
            
        print(f"다운로드 성공: {file_name}")
        return file_name

    except Exception as e:
        print(f"오류 발생: {e}")
        return None

# 텔레그램 발송 부분은 이전과 동일합니다.
def send_to_telegram(file_path):
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat_id: return
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    with open(file_path, 'rb') as f:
        requests.post(url, data={'chat_id': chat_id}, files={'document': f})

if __name__ == "__main__":
    brief_file = download_krx_brief()
    if brief_file:
        send_to_telegram(brief_file)
