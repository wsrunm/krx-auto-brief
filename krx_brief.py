import requests
import os
import datetime

def download_krx_brief():
    # 1. KRX 메인페이지 간행물 데이터 통로
    api_url = "https://www.krx.co.kr/contents/COM/Search.jspx"
    
    # 간행물 게시판(SRCH02030100) 데이터 요청
    payload = {
        'id': 'SRCH02030100', 
        'pageSize': '1',      
        'pageIndex': '1'
    }
    
    # "나 진짜 사람이야"라고 속이는 헤더 보강
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'Referer': 'https://www.krx.co.kr/main/main.jsp',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'X-Requested-With': 'XMLHttpRequest'
    }

    try:
        print("🔍 KRX 서버에서 최신 간행물 목록을 확인 중...")
        response = requests.post(api_url, data=payload, headers=headers)
        
        # 서버 응답 확인
        if response.status_code != 200:
            print(f"❌ 서버 접속 실패 (에러코드: {response.status_code})")
            return None
            
        result = response.json() 

        # 게시물 존재 여부 확인
        if 'block1' in result and len(result['block1']) > 0:
            item = result['block1'][0]
            file_id = item.get('file_id')
            title = item.get('title')
            print(f"✅ 최신 파일 발견: {title}")
        else:
            print("⚠️ 게시판에 올라온 파일이 하나도 없습니다.")
            return None

        # 2. PDF 생성 및 다운로드
        download_url = f"https://www.krx.co.kr/contents/COM/GeneratePDF.jspx?u={file_id}"
        print(f"📥 다운로드 시작: {download_url}")
        
        pdf_res = requests.get(download_url, headers=headers)
        
        if pdf_res.status_code == 200 and len(pdf_res.content) > 1000:
            file_name = f"KRX_Brief_{datetime.datetime.now().strftime('%Y%m%d')}.pdf"
            with open(file_name, 'wb') as f:
                f.write(pdf_res.content)
            print(f"🎉 다운로드 완료: {file_name} ({len(pdf_res.content)} bytes)")
            return file_name
        else:
            print(f"❌ 파일 다운로드 실패 (크기가 너무 작거나 오류 발생)")
            return None

    except Exception as e:
        print(f"🚨 예상치 못한 오류 발생: {e}")
        return None

def send_to_telegram(file_path):
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        print("❗ 텔레그램 설정(Token/ID)을 확인해주세요.")
        return
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    with open(file_path, 'rb') as f:
        res = requests.post(url, data={'chat_id': chat_id}, files={'document': f})
        if res.status_code == 200:
            print("🚀 텔레그램 전송 성공!")
        else:
            print(f"❌ 텔레그램 전송 실패: {res.text}")

if __name__ == "__main__":
    brief_file = download_krx_brief()
    if brief_file:
        send_to_telegram(brief_file)
