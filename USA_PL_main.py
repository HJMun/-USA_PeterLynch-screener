import os
import json
import time
import urllib.request
from datetime import datetime
import pandas as pd
import yfinance as yf
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ==========================================
# 1. 주식 데이터 수집 및 현대판 피터 린치 필터링
# ==========================================
def get_sp500_tickers():
    """위키피디아에서 S&P 500 티커 목록을 가져옵니다."""
    print("S&P 500 티커 목록을 가져오는 중...")
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    
    # 위키피디아 403 에러 방지를 위해 브라우저 헤더(User-Agent) 추가
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    html = urllib.request.urlopen(req).read()
    
    tables = pd.read_html(html)
    df = tables[0]
    tickers = df['Symbol'].str.replace('.', '-', regex=False).tolist()
    return tickers

def screen_peter_lynch(tickers, sample_size=30):
    """현대화된 피터 린치 조건으로 종목을 필터링합니다."""
    results = []
    # 테스트를 위해 우선 30개만 검사합니다. 
    target_tickers = tickers[:sample_size] 
    
    print(f"총 {len(target_tickers)}개 종목 분석 시작...")
    
    for symbol in target_tickers:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            peg = info.get('pegRatio')
            pe = info.get('trailingPE')
            debt_to_equity = info.get('debtToEquity')
            name = info.get('shortName', symbol)
            sector = info.get('sector', 'N/A')
            
            # 현대화된 피터 린치 조건: PEG 1.5 이하, PER 35 이하, 부채비율 150% 미만
            if peg is not None and pe is not None and debt_to_equity is not None:
                if 0 < peg <= 1.5 and pe <= 35 and debt_to_equity < 150:
                    results.append({
                        'Ticker': symbol,
                        'Name': name,
                        'Sector': sector,
                        'PER': round(pe, 2),
                        'PEG': round(peg, 2),
                        'Debt/Equity(%)': round(debt_to_equity, 2)
                    })
            time.sleep(0.2) # 접속 차단 방지용 딜레이
        except Exception:
            continue
            
    return pd.DataFrame(results)

# ==========================================
# 2. 구글 드라이브 업로드 로직
# ==========================================
def upload_to_drive(file_path, file_name):
    """생성된 파일을 구글 드라이브에 업로드합니다."""
    print("구글 드라이브 업로드 시작...")
    
    # 깃허브에 등록할 비밀번호(환경변수)를 불러옵니다.
    gcp_credentials_json = os.environ.get('GCP_CREDENTIALS')
    folder_id = os.environ.get('DRIVE_FOLDER_ID')
    
    if not gcp_credentials_json or not folder_id:
        print("경고: 구글 드라이브 비밀번호(환경변수)가 설정되지 않았습니다.")
        return

    # 구글 드라이브 로그인 및 업로드
    credentials_dict = json.loads(gcp_credentials_json)
    creds = service_account.Credentials.from_service_account_info(
        credentials_dict, 
        scopes=['https://www.googleapis.com/auth/drive.file']
    )
    
    service = build('drive', 'v3', credentials=creds)
    file_metadata = {'name': file_name, 'parents': [folder_id]}
    media = MediaFileUpload(file_path, mimetype='text/csv', resumable=True)
    
    try:
        service.files().create(body=file_metadata, media_body=media).execute()
        print("✅ 구글 드라이브 업로드 완료!")
    except Exception as e:
        print(f"❌ 구글 드라이브 업로드 실패: {e}")

# ==========================================
# 3. 메인 실행 부분
# ==========================================
if __name__ == "__main__":
    sp500_tickers = get_sp500_tickers()
    
    # 분석 시작
    result_df = screen_peter_lynch(sp500_tickers, sample_size=30) 
    
    today_str = datetime.now().strftime("%Y%m%d")
    local_file_name = f"peter_lynch_stocks_{today_str}.csv"
    
    if not result_df.empty:
        result_df.to_csv(local_file_name, index=False, encoding='utf-8-sig')
        print(f"분석 완료. 파일 생성됨: {local_file_name}")
        print(result_df)
        
        upload_to_drive(local_file_name, local_file_name)
    else:
        print("조건을 만족하는 종목이 없습니다.")