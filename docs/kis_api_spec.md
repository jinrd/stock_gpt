# 한국투자증권 해외주식 Open API 핵심 명세서

미국 주식 스크리너 개발에 필요한 10가지 핵심 API 규격입니다. (최신 공식 명세서 기준)

---

## 1. 거래량 급증 종목 조회
- **API 한글명**: 해외주식 거래량급증
- **용도**: 최근 분(N분전) 대비 거래량이 급증한 종목 랭킹 조회
- **HTTP 메서드**: GET
- **URI**: `/uapi/overseas-stock/v1/ranking/volume-surge`
- **실전투자 TR_ID**: `HHDFS76270000`
- **모의투자 지원 여부 및 모의투자 TR_ID**: 모의투자 미지원
- **필수 헤더**: `authorization`, `appkey`, `appsecret`, `tr_id`, `custtype`
- **필수 요청 파라미터와 예시값**:
  - `KEYB`: `""` (공백)
  - `AUTH`: `""` (공백)
  - `EXCD`: `"NAS"` (나스닥)
  - `MINX`: `"0"` (1분전, 0~9 범위)
  - `VOL_RANG`: `"3"` (1만주 이상)
- **응답에서 반드시 사용할 핵심 필드**: `symb`(종목코드), `knam`(종목명), `last`(현재가), `tvol`(거래량), `n_rate`(증가율), `n_diff`(증가량)
- **미국 NASDAQ·NYSE 조회 시 거래소 코드 또는 시장 구분값**: `EXCD`에 `NYS`(뉴욕), `NAS`(나스닥), `AMS`(아멕스)
- **호출 제한 또는 주의할 점**: `tr_cont`(연속조회)를 지원하지 않는 API입니다.
- **Python requests 호출 예시**:
```python
import requests
headers = {
    "authorization": "Bearer [ACCESS_TOKEN]",
    "appkey": "[APP_KEY]",
    "appsecret": "[APP_SECRET]",
    "tr_id": "HHDFS76270000",
    "custtype": "P",
}
params = {
    "KEYB": "", "AUTH": "", "EXCD": "NAS", "MINX": "0", "VOL_RANG": "3"
}
res = requests.get(url + "/uapi/overseas-stock/v1/ranking/volume-surge", headers=headers, params=params)
```

## 2. 거래량 순위 또는 거래대금 순위 조회
- **API 한글명**: 해외주식 거래량순위
- **용도**: 거래량(또는 거래대금)이 가장 많은 종목 랭킹 조회
- **HTTP 메서드**: GET
- **URI**: `/uapi/overseas-stock/v1/ranking/trade-vol`
- **실전투자 TR_ID**: `HHDFS76310010`
- **모의투자 지원 여부 및 모의투자 TR_ID**: 모의투자 미지원
- **필수 헤더**: `authorization`, `appkey`, `appsecret`, `tr_id`, `custtype`
- **필수 요청 파라미터와 예시값**:
  - `KEYB`: `""`, `AUTH`: `""`
  - `EXCD`: `"NAS"`
  - `NDAY`: `"0"` (당일)
  - `PRC1`: `"0"`, `PRC2`: `"100000"` (현재가 필터)
  - `VOL_RANG`: `"0"` (전체)
- **응답에서 반드시 사용할 핵심 필드**: `rank`(순위), `symb`(종목코드), `last`(현재가), `tvol`(거래량), `tamt`(거래대금), `rate`(등락율)
- **미국 NASDAQ·NYSE 조회 시 거래소 코드 또는 시장 구분값**: `EXCD`에 `NYS`, `NAS`, `AMS`
- **호출 제한 또는 주의할 점**: 연속조회(tr_cont) 불가. output2에 순위(`rank`) 정보가 포함되어 있습니다.
- **Python requests 호출 예시**:
```python
params = {
    "KEYB": "", "AUTH": "", "EXCD": "NAS", "NDAY": "0", 
    "PRC1": "0", "PRC2": "1000", "VOL_RANG": "0"
}
# 헤더의 tr_id를 HHDFS76310010으로 설정하여 GET 호출
```

## 3. 상승률·하락률 상위 종목 조회
- **API 한글명**: 해외주식 상승율_하락율
- **용도**: 상승률 또는 하락률 상위 종목 랭킹 조회
- **HTTP 메서드**: GET
- **URI**: `/uapi/overseas-stock/v1/ranking/updown-rate`
- **실전투자 TR_ID**: `HHDFS76290000`
- **모의투자 지원 여부 및 모의투자 TR_ID**: 모의투자 미지원
- **필수 헤더**: `authorization`, `appkey`, `appsecret`, `tr_id`, `custtype`
- **필수 요청 파라미터와 예시값**:
  - `KEYB`: `""`, `AUTH`: `""`
  - `EXCD`: `"NAS"`
  - `GUBN`: `"1"` (0: 하락율, 1: 상승율)
  - `NDAY`: `"0"` (당일)
  - `VOL_RANG`: `"3"` (1만주 이상)
- **응답에서 반드시 사용할 핵심 필드**: `symb`(종목코드), `rank`(순위), `last`(현재가), `rate`(등락율), `n_rate`(기준가격대비율)
- **미국 NASDAQ·NYSE 조회 시 거래소 코드 또는 시장 구분값**: `EXCD`에 `NYS`, `NAS`, `AMS`
- **호출 제한 또는 주의할 점**: 연속조회(tr_cont) 불가.
- **Python requests 호출 예시**:
```python
params = {
    "KEYB": "", "AUTH": "", "EXCD": "NAS", 
    "GUBN": "1", "NDAY": "0", "VOL_RANG": "3"
}
# 헤더의 tr_id를 HHDFS76290000으로 설정하여 GET 호출
```

## 4. 가격 급등락 종목 조회
- **API 한글명**: 해외주식 가격급등락
- **용도**: 단기간에 가격이 급등하거나 급락한 종목 조회
- **HTTP 메서드**: GET
- **URI**: `/uapi/overseas-stock/v1/ranking/price-fluct`
- **실전투자 TR_ID**: `HHDFS76260000`
- **모의투자 지원 여부 및 모의투자 TR_ID**: 모의투자 미지원
- **필수 헤더**: `authorization`, `appkey`, `appsecret`, `tr_id`, `custtype`
- **필수 요청 파라미터와 예시값**:
  - `EXCD`: `"NAS"`
  - `GUBN`: `"1"` (0: 급락, 1: 급등)
  - `MINX`: `"0"` (1분전)
  - `VOL_RANG`: `"0"` (전체)
- **응답에서 반드시 사용할 핵심 필드**: `symb`(종목코드), `last`(현재가), `rate`(등락율), `n_rate`(기준가격대비율)
- **미국 NASDAQ·NYSE 조회 시 거래소 코드 또는 시장 구분값**: `EXCD`에 `NYS`, `NAS`, `AMS`
- **호출 제한 또는 주의할 점**: 급등락은 특정 분 단위 기준이므로 MINX 파라미터 콤보값을 명확히 설정해야 합니다.
- **Python requests 호출 예시**:
```python
params = {"KEYB": "", "AUTH": "", "EXCD": "NAS", "GUBN": "1", "MINX": "0", "VOL_RANG": "0"}
# 헤더의 tr_id를 HHDFS76260000으로 설정하여 GET 호출
```

## 5. 신고가·신저가 종목 조회
- **API 한글명**: 해외주식 신고_신저가
- **용도**: N일간의 기간 내에서 신고가나 신저가를 갱신한 종목 조회
- **HTTP 메서드**: GET
- **URI**: `/uapi/overseas-stock/v1/ranking/new-highlow`
- **실전투자 TR_ID**: `HHDFS76300000`
- **모의투자 지원 여부 및 모의투자 TR_ID**: 모의투자 미지원
- **필수 헤더**: `authorization`, `appkey`, `appsecret`, `tr_id`, `custtype`
- **필수 요청 파라미터와 예시값**:
  - `EXCD`: `"NAS"`
  - `GUBN`: `"1"` (1: 신고, 0: 신저)
  - `GUBN2`: `"1"` (0: 일시돌파, 1: 돌파유지)
  - `NDAY`: `"7"` (0: 5일 ~ 6: 52주, 7: 1년)
  - `VOL_RANG`: `"0"`
- **응답에서 반드시 사용할 핵심 필드**: `symb`(종목코드), `last`(현재가), `n_base`(기준가), `n_rate`(기준가대비율)
- **미국 NASDAQ·NYSE 조회 시 거래소 코드 또는 시장 구분값**: `EXCD`에 `NYS`, `NAS`, `AMS`
- **호출 제한 또는 주의할 점**: 연속조회 불가.
- **Python requests 호출 예시**:
```python
params = {
    "KEYB": "", "AUTH": "", "EXCD": "NAS", 
    "GUBN": "1", "GUBN2": "1", "NDAY": "6", "VOL_RANG": "0"
}
# 헤더의 tr_id를 HHDFS76300000으로 설정하여 GET 호출
```

## 6. 해외주식조건검색
- **API 한글명**: 해외주식조건검색
- **용도**: 현재가, 등락율, 시가총액, 거래량, 거래대금, EPS, PER 등 복합 조건으로 종목 스크리닝
- **HTTP 메서드**: GET
- **URI**: `/uapi/overseas-price/v1/quotations/inquire-search`
- **실전투자 TR_ID**: `HHDFS76410000`
- **모의투자 지원 여부 및 모의투자 TR_ID**: **모의투자 지원 O** (`HHDFS76410000`)
- **필수 헤더**: `authorization`, `appkey`, `appsecret`, `tr_id`
- **필수 요청 파라미터와 예시값**:
  - `AUTH`: `""`
  - `EXCD`: `"NAS"`
  - 사용하려는 조건들의 `CO_YN_*(1)`, `CO_ST_*`, `CO_EN_*` 값. (예: `CO_YN_VOLUME`: `"1"`, `CO_ST_VOLUME`: `"10000"`, `CO_EN_VOLUME`: `"999999999"`) 사용하지 않는 항목은 공백.
- **응답에서 반드시 사용할 핵심 필드**: `symb`(종목코드), `last`(현재가), `tvol`(거래량), `rate`(등락율), `per`, `eps`, `valx`(시가총액)
- **미국 NASDAQ·NYSE 조회 시 거래소 코드 또는 시장 구분값**: `EXCD`에 `NYS`, `NAS`, `AMS`
- **호출 제한 또는 주의할 점**: 현재 최대 100개까지만 응답하며, 다음 조회(NEXT) 기능은 개선 검토 중입니다. 시세 형성이 안된 종목은 조회되지 않습니다. (모의 도메인: `openapivts.koreainvestment.com:29443`)
- **Python requests 호출 예시**:
```python
params = {
    "AUTH": "", "EXCD": "NAS", "KEYB": "",
    "CO_YN_VOLUME": "1", "CO_ST_VOLUME": "10000", "CO_EN_VOLUME": "999999",
    "CO_YN_PRICECUR": "1", "CO_ST_PRICECUR": "50", "CO_EN_PRICECUR": "200"
    # 다른 조건들은 공백
}
# 헤더의 tr_id를 HHDFS76410000으로 설정하여 GET 호출
```

## 7. 현재 체결가 및 현재가 상세 조회
- **API 한글명**: 해외주식 현재가상세
- **용도**: 단일 종목의 PER, PBR, EPS, 상장주수, 매매/호가단위 등 상세 지표 및 현재가 확인
- **HTTP 메서드**: GET
- **URI**: `/uapi/overseas-price/v1/quotations/price-detail`
- **실전투자 TR_ID**: `HHDFS76200200`
- **모의투자 지원 여부 및 모의투자 TR_ID**: 모의투자 미지원
- **필수 헤더**: `authorization`, `appkey`, `appsecret`, `tr_id`
- **필수 요청 파라미터와 예시값**:
  - `AUTH`: `""`
  - `EXCD`: `"NAS"`
  - `SYMB`: `"TSLA"`
- **응답에서 반드시 사용할 핵심 필드**: `last`(현재가), `open`(시가), `high`(고가), `low`(저가), `tvol`(거래량), `perx`, `pbrx`, `epsx`, `tomv`(시가총액)
- **미국 NASDAQ·NYSE 조회 시 거래소 코드 또는 시장 구분값**: `EXCD`에 `NYS`, `NAS`, `AMS`
- **호출 제한 또는 주의할 점**: 무료시세(미국 나스닥 토탈뷰 0분 지연) 기반으로 동작합니다.
- **Python requests 호출 예시**:
```python
params = {"AUTH": "", "EXCD": "NAS", "SYMB": "TSLA"}
# 헤더의 tr_id를 HHDFS76200200으로 설정하여 GET 호출
```

## 8. 일봉 데이터 조회
- **API 한글명**: 해외주식 기간별시세
- **용도**: 단일 종목의 일/주/월봉 데이터 조회 (보조지표 계산에 필수)
- **HTTP 메서드**: GET
- **URI**: `/uapi/overseas-price/v1/quotations/dailyprice`
- **실전투자 TR_ID**: `HHDFS76240000`
- **모의투자 지원 여부 및 모의투자 TR_ID**: **모의투자 지원 O** (`HHDFS76240000`)
- **필수 헤더**: `authorization`, `appkey`, `appsecret`, `tr_id`
- **필수 요청 파라미터와 예시값**:
  - `AUTH`: `""`
  - `EXCD`: `"NAS"`
  - `SYMB`: `"TSLA"`
  - `GUBN`: `"0"` (0:일, 1:주, 2:월)
  - `BYMD`: `""` (공란 시 오늘 날짜 기준)
  - `MODP`: `"1"` (1: 수정주가 반영, 0: 미반영)
- **응답에서 반드시 사용할 핵심 필드**: `output2` 배열 내부의 `xymd`(일자), `clos`(종가), `open`(시가), `high`(고가), `low`(저가), `tvol`(거래량)
- **미국 NASDAQ·NYSE 조회 시 거래소 코드 또는 시장 구분값**: `EXCD`에 `NYS`, `NAS`, `AMS`
- **호출 제한 또는 주의할 점**: 한 번 호출에 최대 100건까지 데이터를 반환합니다.
- **Python requests 호출 예시**:
```python
params = {"AUTH": "", "EXCD": "NAS", "SYMB": "TSLA", "GUBN": "0", "BYMD": "", "MODP": "1"}
# 헤더의 tr_id를 HHDFS76240000으로 설정하여 GET 호출
```

## 9. 상품 기본정보 조회
- **API 한글명**: 해외주식 상품기본정보
- **용도**: 거래정지 여부, 상장폐지 여부, 상품유형, 표준종목번호 등 기본 상태 확인
- **HTTP 메서드**: GET
- **URI**: `/uapi/overseas-price/v1/quotations/search-info`
- **실전투자 TR_ID**: `CTPF1702R`
- **모의투자 지원 여부 및 모의투자 TR_ID**: 모의투자 미지원
- **필수 헤더**: `authorization`, `appkey`, `appsecret`, `tr_id`
- **필수 요청 파라미터와 예시값**:
  - `PRDT_TYPE_CD`: `"512"` (512: 나스닥, 513: 뉴욕, 529: 아멕스)
  - `PDNO`: `"AAPL"` (상품번호/종목코드)
- **응답에서 반드시 사용할 핵심 필드**: `prdt_eng_name`(영문명), `ovrs_stck_tr_stop_dvsn_cd`(거래정지구분코드), `lstg_abol_item_yn`(상장폐지여부)
- **미국 NASDAQ·NYSE 조회 시 거래소 코드 또는 시장 구분값**: `PRDT_TYPE_CD`에 `513`(NYS), `512`(NAS), `529`(AMS)
- **호출 제한 또는 주의할 점**: 거래소 코드가 타 API(`EXCD`)와 달리 고유 `PRDT_TYPE_CD`(숫자)를 사용합니다.
- **Python requests 호출 예시**:
```python
params = {"PRDT_TYPE_CD": "512", "PDNO": "AAPL"}
# 헤더의 tr_id를 CTPF1702R로 설정하여 GET 호출
```

## 10. 복수종목 시세 조회
- **API 한글명**: 해외주식 복수종목 시세조회
- **용도**: 여러 종목의 최신 시세 및 거래량을 한 번의 호출로 확인
- **HTTP 메서드**: GET
- **URI**: `/uapi/overseas-price/v1/quotations/multprice`
- **실전투자 TR_ID**: `HHDFS76220000`
- **모의투자 지원 여부 및 모의투자 TR_ID**: 모의투자 미지원
- **필수 헤더**: `authorization`, `appkey`, `appsecret`, `tr_id`
- **필수 요청 파라미터와 예시값**:
  - `AUTH`: `""`
  - `NREC`: `"2"` (최대 10개)
  - `EXCD_01`: `"NAS"`, `SYMB_01`: `"AAPL"`
  - `EXCD_02`: `"NAS"`, `SYMB_02`: `"TSLA"`
- **응답에서 반드시 사용할 핵심 필드**: `output2` 배열의 `symb`(종목코드), `last`(현재가), `tvol`(거래량), `rate`(등락율)
- **미국 NASDAQ·NYSE 조회 시 거래소 코드 또는 시장 구분값**: `EXCD_0X`에 `NYS`, `NAS`, `AMS`
- **호출 제한 또는 주의할 점**: 한 번에 **최대 10개 종목**까지만 조회 가능하므로 초과하는 종목은 10개씩 분할 호출해야 합니다.
- **Python requests 호출 예시**:
```python
params = {
    "AUTH": "", "NREC": "2",
    "EXCD_01": "NAS", "SYMB_01": "AAPL",
    "EXCD_02": "NAS", "SYMB_02": "TSLA"
}
# 헤더의 tr_id를 HHDFS76220000으로 설정하여 GET 호출
```

---

## 💡 스크리너 개발 권장 호출 순서 제안

1. **순위·조건검색 API로 후보 30~50개 선정**
   - **`해외주식조건검색(HHDFS76410000)`** 또는 **`해외주식 거래량급증(HHDFS76270000)`** API를 사용하여 넓은 범위에서 당일의 1차 관심 종목 풀을 100개 이하로 가져옵니다. (이 API는 목록을 즉시 좁혀줍니다.)
2. **상세 시세와 일봉 조회로 10~20개 필터링**
   - 후보 종목들을 10개 단위로 묶어 **`복수종목 시세조회(HHDFS76220000)`**로 현재 상태(거래량 및 등락률)를 빠르게 체크한 뒤, **`상품기본정보(CTPF1702R)`**를 통해 거래정지/상장폐지 등 비정상 종목을 걸러냅니다. 
3. **RSI·이동평균·MACD 계산 대상 3~5개 확정**
   - 2단계를 통과한 최종 소수 종목에 대해서만 **`기간별시세(HHDFS76240000)`** API를 호출하여 최근 100일 치의 OHLCV(고저시종+거래량) 데이터를 가져옵니다. 이 데이터를 이용해 로컬에서 Pandas, TA-Lib 등을 활용해 보조지표를 연산하고 매수 대상을 최종 확정합니다.
