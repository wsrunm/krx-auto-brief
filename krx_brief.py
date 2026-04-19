import requests
from bs4 import BeautifulSoup
import os
import datetime

# 1. KIND 시장브리프 게시판 접속 및 최신 파일 링크 추출
def download_latest_krx_brief():
    target_url = "https://kind.krx.co.kr/marketnews/mktbrief.do?method=searchMktBriefList"
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    
    # 게시판 리스트 요청 (최근 5일치 검색)
    payload = {
        'method': 'searchMktBriefList',
        'currentPageSize': '15',
        'pageIndex': '1',
        'orderMode': '0',
        'orderStat': 'D',
        'searchCodeType': '',
        'searchCorpName': '',
        'repIsuSrtCd': '',
        'searchSpValue': '',
        'fromDate': (datetime.datetime.now() - datetime.timedelta(days=5)).strftime("%Y-%m-%d"),
        'toDate': today
    }
    
    response = requests.post(target_url, data=payload)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # 첫 번째 게시물의 PDF 다운로드 링크(JavaScript 함수 내 ID) 추출
    # KIND는 보통 onclick="openMarketBrief('ID')" 형태를 사용함
    try:
        first_row = soup.select_one('.tb_type01 tbody tr')
        onclick_attr = first_row.select_one('a')['onclick']
        doc_id = onclick_attr.split("'")[1]
        
        # 실제 PDF 다운로드 경로 (KIND 내부 로직에 따름)
        download_url = f"https://kind.krx.co.kr/common/disclsDocDownload.do?method=download&docid={doc_id}"
        
        # 파일 저장
        file_name = f"KRX_Brief_{today}.pdf"
        file_res = requests.get(download_url)
        with open(file_name, 'wb') as f:
            f.write(file_res.content)
            
        print(f"Success: {file_name} 다운로드 완료")
        return file_name
    except Exception as e:
        print(f"Error: 데이터를 찾을 수 없습니다. ({e})")
        return None

# 2. 텔레그램 전송 함수 (선택 사항)
def send_to_telegram(file_path):
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        return

    url = f"https://api.telegram.org/bot{token}/sendDocument"
    with open(file_path, 'rb') as f:
        requests.post(url, data={'chat_id': chat_id}, files={'document': f})

if __name__ == "__main__":
    brief_file = download_latest_krx_brief()
    if brief_file:
        send_to_telegram(brief_file)
