import os
import json
import time
import urllib.request
from datetime import datetime
import requests
import gspread
from google.oauth2 import service_account
from bs4 import BeautifulSoup

# ==========================================
# 1. 주식 데이터 수집 및 현대판 피터 린치 필터링
# ==========================================
def get_sp500_tickers():
    print("S&P 500 티커 목록을 가져오는 중...")
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    req = urllib.request.Request(url, headers=headers)
    html_bytes = urllib.request.urlopen(req).read()
    html_str = html_bytes.decode('utf-8')

    # pandas의 read_html 대신 순수 파이썬 라이브러리로 표 데이터 추출
    soup = BeautifulSoup(html_str, 'html.parser')
    table = soup.find('table', {'id': 'constituents'})
    
    tickers = []
    for row in table.find_all('tr')[1:]:
        cols = row.find_all('td')
        if cols:
            symbol = cols[0].text.strip().replace('.', '-')
            tickers.append(symbol)
            
    return tickers

def get_ticker_info(symbol):
    # yfinance 라이브러리 대신 야후 파이낸스 API를 직접 호출하여 가볍게 데이터 수집
    url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{symbol}?modules=defaultKeyStatistics,financialData,summaryDetail,price,summaryProfile"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        res = requests.get(url, headers=headers, timeout=5)
        data = res.json()
        result = data.get('quoteSummary', {}).get('result', [])
        if not result:
            return {}
        
        summary = result[0]
        info = {}
        
        def safe_get(module, key):
            return summary.get(module, {}).get(key, {}).get('raw')
        
        info['pegRatio'] = safe_get('defaultKeyStatistics', 'pegRatio')
        info['trailingPE'] = safe_get('summaryDetail', 'trailingPE')
        info['debtToEquity'] = safe_get('financialData', 'debtToEquity')
        info['shortName'] = summary.get('price', {}).get('shortName', symbol)
        info['sector'] = summary.get('summaryProfile', {}).get('sector', 'N/A')
        info['dividendYield'] = safe_get('summaryDetail', 'dividendYield')
        info['returnOnEquity'] = safe_get('financialData', 'returnOnEquity')
        info['currentRatio'] = safe_get('financialData', 'currentRatio')
        info['operatingMargins'] = safe_get('financialData', 'operatingMargins')
        info['priceToBook'] = safe_get('defaultKeyStatistics', 'priceToBook')
        
        return info
    except Exception:
        return {}

def screen_peter_lynch(tickers):
    results = []
    print(f"총 {len(tickers)}개 종목 분석 시작... (약 2~3분 소요)")

    for symbol in tickers:
        info = get_ticker_info(symbol)
        if not info:
            continue

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
        time.sleep(0.1) 

    return results

# ==========================================
# 2. 구글 스프레드시트 업데이트 로직
# ==========================================
def update_google_sheet(data_list):
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
        
        # DataFrame 대신 2차원 리스트 구조로 시트 업데이트
        if data_list:
            headers = list(data_list[0].keys())
            sheet_data = [headers]
            for row in data_list:
                sheet_data.append([row.get(h, '') for h in headers])
            
            worksheet.update(values=sheet_data, range_name='A1')
            print("✅ 구글 시트 업데이트 완료!")
    except Exception as e:
        print(f"❌ 구글 시트 업데이트 실패: {e}")

# ==========================================
# 3. 메인 실행 부분
# ==========================================
if __name__ == "__main__":
    sp500_tickers = get_sp500_tickers()
    result_list = screen_peter_lynch(sp500_tickers)

    if result_list:
        today_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        for row in result_list:
            row['Update_Time'] = today_str

        print(f"분석 완료. 총 {len(result_list)}개의 종목이 조건에 부합합니다.")
        update_google_sheet(result_list)
    else:
        print("조건을 만족하는 종목이 없습니다.")