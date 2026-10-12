import os
import json
import time
import urllib.request
import io
from datetime import datetime
import pandas as pd
import yfinance as yf
import gspread
from gspread_dataframe import set_with_dataframe
from google.oauth2 import service_account

# ==========================================
# 1. 주식 데이터 수집 및 현대판 피터 린치 필터링
# ==========================================
def get_sp500_tickers():
    print("S&P 500 티커 목록을 가져오는 중...")
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    html_bytes = urllib.request.urlopen(req).read()
    html_str = html_bytes.decode('utf-8')

    tables = pd.read_html(io.StringIO(html_str))
    df = tables[0]
    tickers = df['Symbol'].str.replace('.', '-', regex=False).tolist()
    return tickers

# sample_size 파라미터를 제거하여 500개 전체를 분석하도록 수정
def screen_peter_lynch(tickers):
    results = []
    
    print(f"총 {len(tickers)}개 종목 분석 시작... (약 2~3분 소요)")

    for symbol in tickers:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            # 기존 피터린치 지표
            peg = info.get('pegRatio')
            pe = info.get('trailingPE')
            debt_to_equity = info.get('debtToEquity')
            name = info.get('shortName', symbol)
            sector = info.get('sector', 'N/A')
            
            # 신규 추가 판단 지표
            div_yield = info.get('dividendYield')
            roe = info.get('returnOnEquity')
            current_ratio = info.get('currentRatio')
            op_margin = info.get('operatingMargins')
            pbr = info.get('priceToBook')

            # 현대화된 피터 린치 필터링 조건
            if peg is not None and pe is not None and debt_to_equity is not None:
                if 0 < peg <= 1.5 and pe <= 35 and debt_to_equity < 150:
                    results.append({
                        'Ticker': symbol,
                        'Name': name,
                        'Sector': sector,
                        'PER': round(pe, 2),
                        'PEG': round(peg, 2),
                        'Debt/Equity(%)': round(debt_to_equity, 2),
                        # 신규 지표들을 시트에 추가 (데이터가 없는 경우 N/A 또는 0 처리)
                        'Div Yield(%)': round(div_yield * 100, 2) if div_yield is not None else 0.0,
                        'ROE(%)': round(roe * 100, 2) if roe is not None else 'N/A',
                        'Current Ratio': round(current_ratio, 2) if current_ratio is not None else 'N/A',
                        'Op Margin(%)': round(op_margin * 100, 2) if op_margin is not None else 'N/A',
                        'PBR': round(pbr, 2) if pbr is not None else 'N/A'
                    })
            time.sleep(0.1) # 속도 향상을 위해 딜레이를 0.1초로 단축
        except Exception:
            continue

    return pd.DataFrame(results)

# ==========================================
# 2. 구글 스프레드시트 업데이트 로직
# ==========================================
def update_google_sheet(df):
    print("구글 시트 업데이트 시작...")
    gcp_credentials_json = os.environ.get('GCP_CREDENTIALS')
    sheet_id = os.environ.get('SHEET_ID')

    if not gcp_credentials_json or not sheet_id:
        print("경고: GCP_CREDENTIALS 또는 SHEET_ID 환경변수가 설정되지 않았습니다.")
        return

    # 구글 시트 API 인증
    credentials_dict = json.loads(gcp_credentials_json)
    creds = service_account.Credentials.from_service_account_info(
        credentials_dict,
        scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    )
    gc = gspread.authorize(creds)

    try:
        # 시트 열기 (첫 번째 탭)
        doc = gc.open_by_key(sheet_id)
        worksheet = doc.sheet1

        # 기존 데이터 지우기 및 새 데이터 덮어쓰기
        worksheet.clear()
        set_with_dataframe(worksheet, df)
        print("✅ 구글 시트 업데이트 완료!")
    except Exception as e:
        print(f"❌ 구글 시트 업데이트 실패: {e}")

# ==========================================
# 3. 메인 실행 부분
# ==========================================
if __name__ == "__main__":
    sp500_tickers = get_sp500_tickers()

    # 분석 시작 (전체 500여 개 종목 대상)
    result_df = screen_peter_lynch(sp500_tickers)

    if not result_df.empty:
        # 빈 값이 있으면 시트 업로드 시 에러가 날 수 있으므로 빈 문자열로 안전하게 처리
        result_df = result_df.fillna('')

        # 결과 확인을 위해 마지막 업데이트 시간 추가
        today_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        result_df['Update_Time'] = today_str

        print(f"분석 완료. 총 {len(result_df)}개의 종목이 조건에 부합합니다.")
        
        # 구글 시트로 전송
        update_google_sheet(result_df)
    else:
        print("조건을 만족하는 종목이 없습니다.")