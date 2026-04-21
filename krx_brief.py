import requests
import os
import datetime
import time
from pdf2image import convert_from_path
import google.generativeai as genai
from PIL import Image # 이미지 병합을 위해 필요

# 환경 변수 및 설정
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

genai.configure(api_key=GEMINI_API_KEY)

def stitch_images(image_paths, output_name="final_report.jpg"):
    """여러 장의 이미지를 세로로 길게 이어 붙입니다."""
    if not image_paths: return None
    
    print(f"🖼️ {len(image_paths)}장의 이미지 병합 시작...")
    images = [Image.open(x) for x in image_paths]
    
    # 가로 폭을 가장 넓은 이미지 기준으로 통일
    max_width = max(img.size[0] for img in images)
    total_height = sum(img.size[1] for img in images)
    
    # 새 캔버스 생성
    combined_img = Image.new('RGB', (max_width, total_height), (255, 255, 255))
    
    # 이미지 차례대로 붙이기
    current_y = 0
    for img in images:
        combined_img.paste(img, (0, current_y))
        current_y += img.size[1]
    
    combined_img.save(output_name, "JPEG", quality=85)
    return output_name

def summarize_deep_research(file_paths):
    """카페 리포트 스타일의 딥리서치 요약 생성"""
    if not file_paths: return "요약할 리포트가 없습니다."
    
    try:
        uploaded_files = [genai.upload_file(path=p) for p in file_paths]
        model = genai.GenerativeModel('models/gemini-2.5-flash')
        
        # 🎯 카페 스타일의 전문적인 프롬프트 구성
        prompt = """
        너는 20년 경력의 수석 주식 애널리스트야. 제공된 모든 리포트를 분석하여 '딥리서치 시장 요약'을 작성해줘.
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
        
        response = model.generate_content([prompt] + uploaded_files)
        return response.text
    except Exception as e:
        return f"요약 중 오류 발생: {str(e)}"

def download_krx_files():
    """오늘자 모든 리포트 다운로드 (POST 방식)"""
    session = requests.Session()
    today_str = datetime.datetime.now().strftime('%Y%m%d')
    downloaded = []
    
    for i in range(99, 0, -1):
        seq = f"{today_str}{i:02d}"
        try:
            otp_res = session.get("https://www.krx.co.kr/contents/COM/GenerateOTP.jspx", params={
                'name': 'fileDown', 'filetype': 'att', 'url': 'MKD/01/0101/01010000/mkd01010000_03', 'seq': seq
            }, timeout=3)
            otp = otp_res.text.strip()
            if len(otp) < 40: continue
            
            pdf_res = session.post("https://file.krx.co.kr/download.jspx", data={'code': otp}, timeout=10)
            if pdf_res.content.startswith(b'%PDF'):
                fname = f"KRX_{seq}.pdf"
                with open(fname, 'wb') as f: f.write(pdf_res.content)
                downloaded.append(fname)
                time.sleep(0.5)
        except: continue
    return downloaded

def send_to_telegram(text=None, image_path=None, file_path=None):
    if text: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={'chat_id': TELEGRAM_CHAT_ID, 'text': text})
    if image_path:
        with open(image_path, 'rb') as f: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto", data={'chat_id': TELEGRAM_CHAT_ID}, files={'photo': f})
    if file_path:
        with open(file_path, 'rb') as f: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument", data={'chat_id': TELEGRAM_CHAT_ID}, files={'document': f})

if __name__ == "__main__":
    pdfs = download_krx_files()
    
    if pdfs:
        # 1. 종합 딥리서치 요약 생성 및 전송
        research_text = summarize_deep_research(pdfs)
        send_to_telegram(text=research_text)
        
        # 2. 개별 PDF의 첫 페이지를 이미지로 변환
        image_list = []
        for pdf in pdfs:
            try:
                img_pages = convert_from_path(pdf, dpi=150) # 속도를 위해 DPI 약간 조절
                img_name = pdf.replace(".pdf", ".jpg")
                img_pages[0].save(img_name, "JPEG")
                image_list.append(img_name)
            except: continue
            
        # 3. 이미지 병합 (Stitching) 및 전송
        if image_list:
            final_img = stitch_images(image_list)
            send_to_telegram(image_path=final_img)
            
        # 4. 원본 PDF 전송
        for pdf in pdfs:
            send_to_telegram(file_path=pdf)
    else:
        print("📭 리포트 없음")
