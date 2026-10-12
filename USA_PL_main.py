import os
import json
import time
import urllib.request
import io
from datetime import datetime
import pandas as pd
import yfinance as yf
import requests # 차단 우회를 위해 추가
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

def screen_peter_lynch(tickers):
    results = []
    print(f"총 {len(tickers)}개 종목 분석 시작... (약 2~3분 소요)")

    # [추가됨] 야후 파이낸스 봇 차단 우회를 위한 세션 설정
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
    })

    for symbol in tickers:
        try:
            # yfinance 호출 시 위에서 만든 우회 세션을 주입
            ticker = yf.Ticker(symbol, session=session)
            info = ticker.info
            
            # 차단되었거나 빈 데이터가 오면 강제로 에러 발생
            if not info or len(info) <= 1:
                raise ValueError("야후 파이낸스 접근 차단됨 (데이터 비어있음)")

            peg = info.get('pegRatio')
            pe = info.get('trailingPE')
            debt_to_equity = info.get('debtToEquity')
            name = info.get('shortName', symbol)
            sector = info.get('sector', 'N/A')
            
            div_yield = info.get('dividendYield')
            roe = info.get('returnOnEquity')
            current_ratio = info.get('currentRatio')
            op_margin = info.get('operatingMargins')
            pbr = info.get('priceToBook')

            if peg is not None and pe is not None and debt_to_equity is not None:
                if 0 < peg <= 1.5 and pe <= 35 and debt_to_equity < 150:
                    results.append({
                        'Ticker': symbol,
                        'Name': name,
                        'Sector': sector,
                        'PER': round(pe, 2),
                        'PEG': round(peg, 2),
                        'Debt/Equity(%)': f"{debt_to_equity:.2f}%",
                        'Div Yield(%)': f"{div_yield * 100:.2f}%" if div_yield is not None else "0.00%",
                        'ROE(%)': f"{roe * 100:.2f}%" if roe is not None else 'N/A',
                        'Current Ratio': round(current_ratio, 2) if current_ratio is not None else 'N/A',
                        'Op Margin(%)': f"{op_margin * 100:.2f}%" if op_margin is not None else 'N/A',
                        'PBR': round(pbr, 2) if pbr is not None else 'N/A'
                    })
            time.sleep(0.5) # 야후 차단 방지를 위해 쉬는 시간을 약간 넉넉하게 조정
            
        except Exception as e:
            # [수정됨] 조용히 넘기지 않고 에러 내용을 깃허브 로그에 출력
            print(f"[{symbol}] 조회 실패: {e}")
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

    credentials_dict = json.loads(gcp_credentials_json)
    creds = service_account.Credentials.from_service_account_info(
        credentials_dict,
        scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    )
    gc = gspread.authorize(creds)

    try:
        doc = gc.open_by_key(sheet_id)
        worksheet = doc.sheet1

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

    result_df = screen_peter_lynch(sp500_tickers)

    if not result_df.empty:
        result_df = result_df.fillna('')

        today_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        result_df['Update_Time'] = today_str

        print(f"분석 완료. 총 {len(result_df)}개의 종목이 조건에 부합합니다.")
        
        update_google_sheet(result_df)
    else:
        print("조건을 만족하는 종목이 없습니다.")