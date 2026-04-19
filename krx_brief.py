import requests
import os
import datetime

def download_krx_main_publication():
    # 1. 메인페이지가 데이터를 요청하는 실제 '데이터 통로'
    data_url = "https://www.krx.co.kr/contents/COM/Search.jspx"
    
    # 2. 메인페이지 '간행물' 섹션에 표시될 데이터를 달라는 요청서
    payload = {
        'id': 'SRCH02030100', # 간행물 게시판 고유 식별값
        'pageSize': '1',      # 맨 위 1개만 필요함
        'pageIndex': '1'
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.krx.co.kr/main/main.jsp' # 메인페이지에서 온 것처럼 위장
    }

    try:
        # 데이터 목록 요청 (POST 방식)
        response = requests.post(data_url, data=payload, headers=headers)
        # KRX는 목록을 JSON(데이터 덩어리)으로 줍니다.
        result = response.json() 

        # 3. 데이터 덩어리에서 파일 ID 추출
        # 'block1'이라는 주머니 안에 게시물 리스트가 들어있습니다.
        if 'block1' in result and len(result['block1']) > 0:
            latest_post = result['block1'][0]
            file_id = latest_post['file_id']
            title = latest_post['title']
            print(f"최신 간행물 확인: {title}")
        else:
            print("간행물을 찾을 수 없습니다.")
            return None

        # 4. 파일 ID를 이용해 실제 PDF 다운로드
        download_url = f"https://www.krx.co.kr/contents/COM/GeneratePDF.jspx?u={file_id}"
        file_name = f"KRX_Brief_{datetime.datetime.now().strftime('%Y%m%d')}.pdf"

        pdf_res = requests.get(download_url, headers=headers)
        
        # 파일 저장
        with open(file_name, 'wb') as f:
            f.write(pdf_res.content)
            
        print(f"성공: {file_name} 다운로드 완료")
        return file_name

    except Exception as e:
        print(f"오류 발생: {e}")
        return None

def send_to_telegram(file_path):
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        print("텔레그램 설정이 되어 있지 않습니다.")
        return

    url = f"https://api.telegram.org/bot{token}/sendDocument"
    with open(file_path, 'rb') as f:
        requests.post(url, data={'chat_id': chat_id}, files={'document': f})
        print("텔레그램 전송 완료")

if __name__ == "__main__":
    brief_file = download_krx_main_publication()
    if brief_file:
        send_to_telegram(brief_file)
