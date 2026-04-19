import requests
import os
import datetime

def download_krx_main_publication():
    # 1. 실제 데이터 통로
    data_url = "https://www.krx.co.kr/contents/COM/Search.jspx"
    
    payload = {
        'id': 'SRCH02030100',
        'pageSize': '1',
        'pageIndex': '1'
    }
    
    # 브라우저인 척하기 위해 헤더를 더 보강합니다.
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Referer': 'https://www.krx.co.kr/main/main.jsp',
        'Origin': 'https://www.krx.co.kr',
        'X-Requested-With': 'XMLHttpRequest'
    }

    try:
        print("KRX 서버에 간행물 목록을 요청합니다...")
        response = requests.post(data_url, data=payload, headers=headers)
        result = response.json() 

        if 'block1' in result and len(result['block1']) > 0:
            latest_post = result['block1'][0]
            # KRX 간행물은 file_id를 사용하여 다운로드합니다.
            file_id = latest_post.get('file_id')
            title = latest_post.get('title')
            
            if not file_id:
                print(f"게시물은 찾았으나 파일 ID가 없습니다: {title}")
                return None
                
            print(f"최신 간행물 발견: {title} (ID: {file_id})")
        else:
            print("목록을 가져왔으나 게시물이 비어 있습니다.")
            return None

        # 2. 파일 다운로드 경로 (GeneratePDF 대신 실제 파일 다운로드 주소 사용 시도)
        download_url = f"https://www.krx.co.kr/contents/COM/GeneratePDF.jspx?u={file_id}"
        
        # 파일명을 날짜와 제목으로 깔끔하게 정합니다.
        file_name = f"KRX_Brief_{datetime.datetime.now().strftime('%Y%m%d')}.pdf"

        print(f"파일 다운로드를 시도합니다: {download_url}")
        pdf_res = requests.get(download_url, headers=headers)
        
        # 다운로드 성공 여부 확인
        if pdf_res.status_code == 200 and len(pdf_res.content) > 1000: # 최소 1KB 이상이어야 실제 파일
            with open(file_name, 'wb') as f:
                f.write(pdf_res.content)
            print(f"다운로드 완료! 저장된 파일명: {file_name} ({len(pdf_res.content)} bytes)")
            return file_name
        else:
            print(f"다운로드 실패. 상태 코드: {pdf_res.status_code}, 파일 크기: {len(pdf_res.content)}")
            return None

    except Exception as e:
        print(f"프로그램 실행 중 오류 발생: {e}")
        return None

def send_to_telegram(file_path):
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        print("텔레그램 토큰이나 ID가 설정되지 않았습니다.")
        return

    url = f"https://api.telegram.org/bot{token}/sendDocument"
    print("텔레그램으로 파일을 전송합니다...")
    with open(file_path, 'rb') as f:
        res = requests.post(url, data={'chat_id': chat_id}, files={'document': f})
        if res.status_code == 200:
            print("텔레그램 전송 성공!")
        else:
            print(f"텔레그램 전송 실패: {res.text}")

if __name__ == "__main__":
    brief_file = download_krx_main_publication()
    if brief_file:
        send_to_telegram(brief_file)
    else:
        print("전송할 파일이 없습니다.")
