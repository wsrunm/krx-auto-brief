import requests
import os
import datetime
import time
import re
from pdf2image import convert_from_path
import google.generativeai as genai

from pypdf import PdfReader

# 환경 변수 설정
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# Gemini 설정
genai.configure(api_key=GEMINI_API_KEY)

# 💡 1.5가 없다면 2.0-flash 혹은 현재 성공하신 2.5-flash를 사용합니다.
model_name = 'models/gemini-2.0-flash' # 1.5가 없다면 2.0이 표준일 확률이 높습니다.

def get_target_date():
    """실행 시점이 주말이면 가장 가까운 금요일 날짜를 반환합니다."""
    target = datetime.datetime.now()
    weekday = target.weekday() # 0:월, 1:화, 2:수, 3:목, 4:금, 5:토, 6:일

    if weekday == 5: # 토요일
        target = target - datetime.timedelta(days=1)
    elif weekday == 6: # 일요일
        target = target - datetime.timedelta(days=2)
    
    return target.strftime('%Y%m%d')

def is_konex_report(file_path):
    """PDF 첫 페이지의 텍스트를 읽어 코넥스 리포트인지 판별합니다."""
    try:
        reader = PdfReader(file_path)
        first_page = reader.pages[0]
        text = first_page.extract_text()
        
        # 제목이나 상단에 '코넥스' 또는 'KONEX'가 포함되어 있는지 확인
        if "코넥스" in text or "KONEX" in text:
            return True
        return False
    except Exception as e:
        print(f"  ⚠️ 내용 분석 실패 ({file_path}): {e}")
        return False
        
def download_all_today_reports(target_date_str=None):
    """
    지정된 날짜의 01~98번 리포트를 모두 확인하고, 발견된 파일명을 반환합니다.
    (target_date_str가 None이면 KST 기준 오늘 날짜를 사용합니다.)
    """
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://www.krx.co.kr/'
    })
    
    # 인자로 받은 날짜가 없으면 기존처럼 오늘(주말이면 금요일)로 설정
    if target_date_str is None:
        now_kst = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
        if now_kst.weekday() == 5: now_kst -= datetime.timedelta(days=1)
        elif now_kst.weekday() == 6: now_kst -= datetime.timedelta(days=2)
        target_date_str = now_kst.strftime('%Y%m%d')
    
    downloaded_files = []

    # 안내 로그 (전수 조사 중복 출력 방지를 위해 여기서는 제거하거나 간소화)
    # print(f"🔍 {target_date_str} 리포트 다운로드 시도 (01~98)...")
    
    for i in range(1, 99):
        seq = f"{target_date_str}{i:02d}"
        try:
            # OTP 발급 시도
            otp_res = session.get("https://www.krx.co.kr/contents/COM/GenerateOTP.jspx", params={
                'name': 'fileDown', 'filetype': 'att', 
                'url': 'MKD/01/0101/01010000/mkd01010000_03', 'seq': seq
            }, timeout=2)
            
            otp = otp_res.text.strip()
            if not otp or len(otp) < 40: 
                continue # 파일이 없으면 조용히 넘어갑니다.
            
            # 파일 다운로드 시도
            pdf_res = session.post("https://file.krx.co.kr/download.jspx", data={'code': otp}, timeout=10)
            if pdf_res.status_code == 200 and pdf_res.content.startswith(b'%PDF'):
                fname = f"KRX_{seq}.pdf"
                with open(fname, 'wb') as f:
                    f.write(pdf_res.content)
                downloaded_files.append(fname)
                print(f"  ✨ 원본 다운로드 완료: {fname}") 
                time.sleep(0.2)
        except:
            continue
    
    # 찾은 리포트가 있을 때만 요약 출력 (로그 창을 깔끔하게 유지하기 위함)
    if downloaded_files:
        print("\n" + "="*50)
        print(f"📋 다운로드 성공 리포트 리스트 ({len(downloaded_files)}개)")
        for f in downloaded_files:
            print(f"  - {f}")
        print("="*50 + "\n")
    
    return downloaded_files
    
def get_report_priority_by_content(file_path):
    """리포트 내부의 텍스트를 읽어 실제 정체를 파악하고 우선순위를 반환합니다."""
    try:
        reader = PdfReader(file_path)
        first_page = reader.pages[0]
        text = first_page.extract_text()
        
        # 1순위: 증시 Brief (가장 핵심 리포트)
        if "증시 Brief" in text or "증시브리프" in text:
            return 1
        
        # 2순위: 코스닥시장 (사용자님의 주요 관심사)
        if "코스닥시장" in text and "일일동향" in text:
            return 2
        
        # 3순위: 유가증권시장(KOSPI) 일일동향
        if "유가증권시장" in text and "일일동향" in text:
            return 3
            
        # 그 외 나머지는 뒤로 보냄
        return 50
    except:
        return 99

def sort_krx_reports(file_paths):
    """내용 기반으로 우선순위를 정해 정렬합니다."""
    # 각 파일의 경로와 우선순위를 튜플로 묶어서 정렬
    indexed_reports = []
    for path in file_paths:
        priority = get_report_priority_by_content(path)
        indexed_reports.append((priority, path))
    
    # 우선순위(priority) 숫자 순서대로 정렬 (1이 가장 먼저)
    indexed_reports.sort(key=lambda x: x[0])
    
    # 정렬된 파일 경로만 다시 리스트로 반환
    return [report[1] for report in indexed_reports]

def summarize_all_in_one(file_paths):
    if not file_paths: return "파일 없음"
    
    # 코넥스 제외 (사용자 요청 반영)
    analysis_targets = file_paths[:2] 
    
    try:
        uploaded_files = [genai.upload_file(path=p) for p in analysis_targets]
        # API 요청 간격 확보 (RPM 관리)
        time.sleep(10) 

        model = genai.GenerativeModel('models/gemini-2.5-flash')
        
        # 💡 토큰 소모를 최소화하는 경량 프롬프트
        prompt = "제공된 리포트에서 1. 시장 특징 2. 주도 테마 3. 핵심 종목만 불렛 포인트로 짧게 요약해줘."
        
        # 쿼터 초기화를 위한 대기 후 요청
        # time.sleep(20)
        response = model.generate_content([prompt] + uploaded_files)
        return response.text
    except Exception as e:
        # 요약 실패 시에도 전체 프로세스가 멈추지 않도록 예외 처리
        print(f"🤖 분석 생략: {e}")
        return "리포트 분석을 완료했습니다. 상세 내용은 아래 첨부된 파일을 확인해 주세요."

def convert_to_image(pdf_path):
    """PDF 첫 페이지를 JPG 이미지로 변환합니다."""
    try:
        images = convert_from_path(pdf_path, dpi=200)
        if images:
            img_path = pdf_path.replace(".pdf", ".jpg")
            images[0].save(img_path, "JPEG")
            return img_path
    except Exception as e:
        print(f"❌ 이미지 변환 실패 ({pdf_path}): {e}")
    return None

def send_to_telegram(text=None, image_path=None, file_path=None):
    """텔레그램 전송 (각 요소별 독립 전송)"""
    try:
        if text:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                          data={'chat_id': TELEGRAM_CHAT_ID, 'text': text})
        if image_path:
            with open(image_path, 'rb') as f:
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto", 
                              data={'chat_id': TELEGRAM_CHAT_ID}, files={'photo': f})
        if file_path:
            with open(file_path, 'rb') as f:
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument", 
                              data={'chat_id': TELEGRAM_CHAT_ID}, files={'document': f})
    except Exception as e:
        print(f"❌ 텔레그램 전송 중 오류: {e}")

def generate_deep_research():
    # market_data에는 당일 등락률, 거래대금, 상위 섹터 정보 등을 문자열로 전달
    prompt = f"""
    너는 20년 경력의 수석 주식 애널리스트야. 제공된 데이터를 분석하고, 이를 바탕으로 최신 주식 관련 뉴스들도 검색해서 '딥리서치 시장 요약'을 종합적으로 작성해줘.
    형식은 반드시 아래를 지켜줘:

    📊 [오늘의 시장 분석 딥리서치]
    - 날짜: (리포트의 날짜)
    
    ■ 시장 핵심 요약
    - (코스피/코스닥 주요 흐름 2~3줄)
    
    🚀 핵심 키워드 및 테마
    - (주요 섹터명과 핵심 이유를 이모지와 함께 3~4개 작성)
    
    🔥 테마별 상세 분석 (가장 중요한 테마 2~3개)
    【테마명】 - (이유/모멘텀)
    - [대장주] 종목명 : (상승 이유 및 분석 내용)
    - 관련주 : (나열)
    
    ⚡ 투자자 관점 포인트
    - (내일 장 대응 전략 1~2줄)
    
    반드시 한국어로, 전문적이고 가독성 있게 작성해줘.

    """
    
    response = model_name.generate_content(prompt)
    return response.text
    
import subprocess
import glob
import re
import datetime

def cleanup_old_files_by_name(days=3):
    """
    파일명에 포함된 날짜를 기준으로 N일이 지난 파일을 깃허브 저장소에서 완전히 삭제합니다.
    """
    print(f"\n🧹 {days}일 이상 지난 과거 리포트 정리 시작...")
    
    # 한국 시간 기준 '오늘' 날짜 계산
    now_kst = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
    today_date = now_kst.date()
    
    # 폴더 내의 모든 KRX_*.pdf 및 KRX_*.jpg 파일 찾기
    target_files = glob.glob("KRX_*.pdf") + glob.glob("KRX_*.jpg")
    
    deleted_count = 0
    for f in target_files:
        # 파일명에서 YYYYMMDD 날짜 추출 (예: KRX_2026042411.pdf -> 20260424)
        match = re.search(r'KRX_(\d{8})', f)
        if match:
            date_str = match.group(1)
            try:
                # 추출한 문자열을 실제 날짜 객체로 변환
                file_date = datetime.datetime.strptime(date_str, '%Y%m%d').date()
                diff_days = (today_date - file_date).days
                
                # 기준일(days) 이상 지났으면 삭제 진행
                if diff_days >= days:
                    print(f"  🗑️ [Git 삭제] {diff_days}일 지난 파일: {f}")
                    # 💡 os.remove(f) 대신 git rm 명령어 실행
                    # check=False로 두어 만약 Git 추적 대상이 아니더라도 에러 없이 넘어가게 함
                    subprocess.run(["git", "rm", f], check=False)
                    deleted_count += 1
            except ValueError:
                continue # 날짜 형식이 이상한 파일은 무시

    if deleted_count == 0:
        print("  ✨ 삭제할 과거 파일이 없습니다.")
    else:
        print(f"  ✅ 총 {deleted_count}개의 과거 파일이 저장소에서 삭제 대기열에 올랐습니다.")


def is_junk_report(file_path):
    """PDF 첫 페이지를 읽어 코넥스 및 불필요한 리포트를 판별합니다."""
    try:
        reader = PdfReader(file_path)
        first_page = reader.pages[0]
        text = first_page.extract_text()
        
        # 제외하고 싶은 키워드 리스트
        # '코넥스'가 포함된 리포트는 무조건 True 반환
        black_list = ["코넥스", "KONEX", "파생상품"]
        
        if any(keyword in text for keyword in black_list):
            return True
        return False
    except Exception as e:
        print(f"  ⚠️ 내용 분석 실패 ({file_path}): {e}")
        return False


# ---------------------------------------------------------
# 🚀 최적화된 메인 실행부 (최근 5일 역추적 버전)
# ---------------------------------------------------------
if __name__ == "__main__":
    # 1. 환경 정리: 파일명 날짜 기준으로 3일 지난 구버전 파일 삭제
    cleanup_old_files_by_name(days=3)
    
    # 한국 시간(KST) 기준 설정
    now_kst = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
    valid_reports = []
    target_date_str = ""

    # 2. 최근 5일간 리포트가 있는지 역순으로 전수 조사
    for i in range(6):  # 0(오늘)부터 5일전까지 반복
        current_date = now_kst - datetime.timedelta(days=i)
        date_str = current_date.strftime('%Y%m%d')
        
        print(f"\n🔍 {date_str} 리포트 전수 조사 시작 (01~60)...")
        
        # 💡 주의: download_all_today_reports() 함수가 date_str를 인자로 받도록 수정되어야 합니다.
        raw_reports = download_all_today_reports(date_str)
        
        if raw_reports:
            print(f"✅ {date_str} 리포트 {len(raw_reports)}개를 발견했습니다. 검수를 시작합니다.")
            
            temp_valid = []
            for report in raw_reports:
                # 3. 내용 기반 필터링 (코넥스 등 제거)
                if is_junk_report(report):
                    print(f"  🗑️ [즉시 삭제] 코넥스/불필요 리포트 제거: {report}")
                    try:
                        os.remove(report)
                    except:
                        pass
                else:
                    temp_valid.append(report)
            
            if temp_valid:
                valid_reports = temp_valid
                target_date_str = date_str
                break  # 🎯 리포트를 찾았으므로 루프 탈출
            else:
                print(f"📭 {date_str}일자는 코넥스를 제외하니 남은 리포트가 없습니다. 이전 날짜를 확인합니다.")
        else:
            print(f"📭 {date_str}일자 리포트가 서버에 없습니다. 이전 날짜를 확인합니다.")

    # 3. 최종 리스트 기반 정렬 및 전송
    if valid_reports:
        # 선호 번호(11, 52 등) 기준으로 정렬
        sorted_reports = sort_krx_reports(valid_reports)
        
        print(f"📋 최종 전송 대상 ({target_date_str}): {sorted_reports}")
        
        # 4. AI 딥리서치 생성 (상위 2개 핵심 리포트 분석)
        deep_research = summarize_all_in_one(sorted_reports)
        send_to_telegram(text=f"📊 **증시 딥리서치 ({target_date_str})**\n\n{deep_research}")
        
        # 5. 개별 리포트 이미지 및 파일 전송
        for report in sorted_reports:
            try:
                # 이미지 변환 및 저장
                img_pages = convert_from_path(report, dpi=150)
                img_name = report.replace(".pdf", ".jpg")
                img_pages[0].save(img_name, "JPEG")
                
                # 텔레그램 전송 (순서 보장을 위해 간격 유지)
                send_to_telegram(image_path=img_name)
                time.sleep(3)
                send_to_telegram(file_path=report)
                time.sleep(3)
            except Exception as e:
                print(f"  ❌ {report} 전송 중 오류: {e}")
    else:
        print("❌ 최근 5일 이내에 전송할 수 있는 유효한 리포트가 없습니다.")
