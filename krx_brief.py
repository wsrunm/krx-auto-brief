import requests
from bs4 import BeautifulSoup
import os
import datetime

def download_latest_krx_brief():
    target_url = "https://kind.krx.co.kr/marketnews/mktbrief.do?method=searchMktBriefList"
    
    # 최근 30일간의 데이터를 검색하여 목록이 비어있지 않게 합니다.
    payload = {
        'method': 'searchMktBriefList',
        'currentPageSize': '15',
        'pageIndex': '1',
        'orderMode': '0',
        'orderStat': 'D',
        'fromDate': (datetime.datetime.now() - datetime.timedelta(days=30)).strftime("%Y-%m-%d"),
        'toDate': datetime.datetime.now().strftime("%Y-%m-%d")
    }
    
    try:
        response = requests.post(target_url, data=payload)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 게시판에서 가장 첫 번째 행을 찾습니다.
        first_row = soup.select_one('.tb_type01 tbody tr')
        if not first_row or "조회 결과가 없습니다" in first_row.text:
            print("게시물 없음: 최신 브리프를 찾을 수 없습니다.")
            return None

        # onclick 이벤트에서 docid 추출
        anchor = first_row.select_one('a')
        onclick_attr = anchor['onclick']
        doc_id = onclick_attr.split("'")[1]
        
        # 파일명 생성 (오늘 날짜가 아니라 게시물의 제목이나 ID를 활용)
        file_name = f"KRX_Latest_Brief_{doc_id}.pdf"
        
        # 실제 다운로드 링크
        download_url = f"https://kind.krx.co.kr/common/disclsDocDownload.do?method=download&docid={doc_id}"
        
        file_res = requests.get(download_url)
        with open(file_name, 'wb') as f:
            f.write(file_res.content)
            
        print(f"다운로드 성공: {file_name}")
        return file_name

    except Exception as e:
        print(f"오류 발생: {e}")
        return None

def send_to_telegram(file_path):
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        print("텔레그램 설정이 없습니다.")
        return

    url = f"https://api.telegram.org/bot{token}/sendDocument"
    with open(file_path, 'rb') as f:
        res = requests.post(url, data={'chat_id': chat_id}, files={'document': f})
        print(f"텔레그램 전송 결과: {res.status_code}")

if __name__ == "__main__":
    brief_file = download_latest_krx_brief()
    if brief_file:
        send_to_telegram(brief_file)
