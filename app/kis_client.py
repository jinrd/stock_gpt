import json
import os
import time
from threading import Lock
from typing import Any, Dict, List

import requests

from app.config import Settings


class KisApiError(Exception):
    """한국투자증권 API 호출 오류입니다."""


class KisClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._access_token = None
        self._token_expires_at = 0.0
        self._token_lock = Lock()

    def get_access_token(self) -> str:
        # 토큰 만료 1분 전까지 기존 토큰을 재사용합니다.
        if (
            self._access_token
            and time.time() < self._token_expires_at - 60
        ):
            return self._access_token

        # 동시에 여러 요청이 들어와도 토큰은 한 번만 발급합니다.
        with self._token_lock:
            if (
                self._access_token
                and time.time() < self._token_expires_at - 60
            ):
                return self._access_token

            token_file = ".kis_token.json"
            if os.path.exists(token_file):
                try:
                    with open(token_file, "r") as f:
                        data = json.load(f)
                        if time.time() < data.get("expires_at", 0) - 60:
                            self._access_token = data["access_token"]
                            self._token_expires_at = data["expires_at"]
                            return self._access_token
                except Exception:
                    pass

            url = f"{self.settings.kis_base_url}/oauth2/tokenP"

            response = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                json={
                    "grant_type": "client_credentials",
                    "appkey": self.settings.kis_app_key,
                    "appsecret": self.settings.kis_app_secret,
                },
                timeout=10,
            )

            if not response.ok:
                raise KisApiError(
                    f"토큰 발급 실패: HTTP {response.status_code} - {response.text}"
                )

            data: Dict[str, Any] = response.json()
            access_token = data.get("access_token")

            if not access_token:
                raise KisApiError("응답에 access_token이 없습니다.")

            # KIS 응답의 expires_in 값을 사용합니다.
            expires_in = int(data.get("expires_in", 3600))

            self._access_token = access_token
            self._token_expires_at = time.time() + expires_in

            try:
                with open(token_file, "w") as f:
                    json.dump({
                        "access_token": self._access_token,
                        "expires_at": self._token_expires_at
                    }, f)
            except Exception:
                pass

            return self._access_token

    def _get_headers(self, tr_id: str) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.get_access_token()}",
            "appkey": self.settings.kis_app_key,
            "appsecret": self.settings.kis_app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }

    def search_stocks(
        self,
        exchange: str,
        minimum_price: float,
        maximum_price: float,
        minimum_volume: int,
    ) -> List[Dict[str, Any]]:
        url = (
            f"{self.settings.kis_base_url}"
            "/uapi/overseas-price/v1/quotations/inquire-search"
        )

        params = {
            "AUTH": "",
            "KEYB": "",
            "EXCD": exchange,
            "CO_YN_VOLUME": "1",
            "CO_ST_VOLUME": str(minimum_volume),
            "CO_EN_VOLUME": "999999999999",
            "CO_YN_PRICECUR": "1",
            "CO_ST_PRICECUR": str(minimum_price),
            "CO_EN_PRICECUR": str(maximum_price),
        }

        response = requests.get(
            url,
            headers=self._get_headers("HHDFS76410000"),
            params=params,
            timeout=10,
        )

        if not response.ok:
            raise KisApiError(
                f"조건검색 실패: HTTP {response.status_code}"
            )

        data: Dict[str, Any] = response.json()

        if data.get("rt_cd") not in (None, "0"):
            message = data.get("msg1", "알 수 없는 API 오류")
            raise KisApiError(f"조건검색 실패: {message}")

        return data.get("output2") or data.get("output") or []

    def search_krx_stocks(
        self,
        minimum_price: float,
        maximum_price: float,
        minimum_volume: int,
    ) -> List[Dict[str, Any]]:
        url = f"{self.settings.kis_base_url}/uapi/domestic-stock/v1/quotations/volume-rank"
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_COND_SCR_DIV_CODE": "20171",
            "FID_INPUT_ISCD": "0000",
            "FID_DIV_CLS_CODE": "0",
            "FID_BLNG_CLS_CODE": "0",
            "FID_TRGT_CLS_CODE": "0",
            "FID_TRGT_EXLS_CLS_CODE": "1111111101",
            "FID_INPUT_PRICE_1": str(int(minimum_price)),
            "FID_INPUT_PRICE_2": str(int(maximum_price)),
            "FID_VOL_CNT": "",
            "FID_INPUT_DATE_1": ""
        }
        response = requests.get(
            url,
            headers=self._get_headers("FHPST01710000"),
            params=params,
            timeout=10,
        )
        if not response.ok:
            raise KisApiError(f"국내 거래량 순위 조회 실패: HTTP {response.status_code}")
            
        data: Dict[str, Any] = response.json()
        if data.get("rt_cd") not in (None, "0"):
            message = data.get("msg1", "알 수 없는 API 오류")
            raise KisApiError(f"국내 거래량 순위 조회 실패: {message}")

        items = data.get("output") or []
        filtered_items = []
        for item in items:
            price = float(item.get("stck_prpr", 0))
            volume = int(item.get("acml_vol", 0))
            
            if (minimum_price <= price <= maximum_price) and (volume >= minimum_volume):
                filtered_items.append({
                    "symb": item.get("mksc_shrn_iscd"),
                    "knam": item.get("hts_kor_isnm"),
                    "last": item.get("stck_prpr"),
                    "tvol": item.get("acml_vol"),
                    "tval": item.get("acml_tr_pbmn", "0"),
                })
        return filtered_items

    def get_daily_prices(
        self,
        exchange: str,
        symbol: str,
    ) -> List[Dict[str, Any]]:
        url = (
            f"{self.settings.kis_base_url}"
            "/uapi/overseas-price/v1/quotations/dailyprice"
        )

        params = {
            "AUTH": "",
            "EXCD": exchange,
            "SYMB": symbol.upper(),
            "GUBN": "0",
            "BYMD": "",
            "MODP": "1",
        }

        response = requests.get(
            url,
            headers=self._get_headers("HHDFS76240000"),
            params=params,
            timeout=10,
        )

        if not response.ok:
            raise KisApiError(
                f"일봉 조회 실패: HTTP {response.status_code}"
            )

        data: Dict[str, Any] = response.json()

        if data.get("rt_cd") not in (None, "0"):
            message = data.get("msg1", "알 수 없는 API 오류")
            raise KisApiError(f"일봉 조회 실패: {message}")

        return data.get("output2") or []

    def get_krx_daily_prices(
        self,
        symbol: str,
    ) -> List[Dict[str, Any]]:
        import datetime
        url = f"{self.settings.kis_base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        end_date = datetime.datetime.today().strftime('%Y%m%d')
        start_date = (datetime.datetime.today() - datetime.timedelta(days=150)).strftime('%Y%m%d')
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol.upper(),
            "FID_INPUT_DATE_1": start_date,
            "FID_INPUT_DATE_2": end_date,
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": "1"
        }
        response = requests.get(
            url,
            headers=self._get_headers("FHKST03010100"),
            params=params,
            timeout=10,
        )
        if not response.ok:
            error_msg = f"HTTP {response.status_code}"
            try:
                err_data = response.json()
                if "msg1" in err_data:
                    error_msg += f" - {err_data['msg1']}"
            except:
                pass
            raise KisApiError(f"국내 일봉 조회 실패: {error_msg}")
        
        data: Dict[str, Any] = response.json()
        if data.get("rt_cd") not in (None, "0"):
            message = data.get("msg1", "알 수 없는 API 오류")
            raise KisApiError(f"국내 일봉 조회 실패: {message}")

        # 해외 주식 응답 포맷으로 변환하여 기존 분석 로직 호환성 유지
        items = data.get("output2") or []
        mapped = []
        for item in items:
            mapped.append({
                "xymd": item.get("stck_bsop_date"),
                "open": item.get("stck_oprc"),
                "high": item.get("stck_hgpr"),
                "low": item.get("stck_lwpr"),
                "clos": item.get("stck_clpr"),
                "tvol": item.get("acml_vol"),
            })
        return mapped

    def get_krx_index_daily_prices(
        self,
        market_type: str = "KOSDAQ",
    ) -> List[Dict[str, Any]]:
        import datetime
        url = f"{self.settings.kis_base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice"
        end_date = datetime.datetime.today().strftime('%Y%m%d')
        start_date = (datetime.datetime.today() - datetime.timedelta(days=150)).strftime('%Y%m%d')
        
        iscd = "1001" if market_type.upper() == "KOSDAQ" else "0001"
        
        params = {
            "FID_COND_MRKT_DIV_CODE": "U",
            "FID_INPUT_ISCD": iscd,
            "FID_INPUT_DATE_1": start_date,
            "FID_INPUT_DATE_2": end_date,
            "FID_PERIOD_DIV_CODE": "D"
        }
        response = requests.get(
            url,
            headers=self._get_headers("FHKUP03500100"),
            params=params,
            timeout=10,
        )
        if not response.ok:
            return []
        
        data: Dict[str, Any] = response.json()
        items = data.get("output2") or []
        mapped = []
        for item in items:
            mapped.append({
                "xymd": item.get("stck_bsop_date"),
                "open": item.get("bstp_nmix_oprc"),
                "high": item.get("bstp_nmix_hgpr"),
                "low": item.get("bstp_nmix_lwpr"),
                "clos": item.get("bstp_nmix_prpr"),
                "tvol": item.get("acml_vol"),
            })
        return mapped

    def get_stock_name(self, exchange: str, symbol: str) -> str:
        """종목 코드로 종목명을 조회합니다. (KRX는 KIS API, 해외는 Yahoo Finance 활용)"""
        if exchange == "KRX":
            try:
                # search_krx_stocks 내부에서 부르는 거래량 순위 조회 API에 현재가격을 입력해 단일 종목처럼 검색
                # (가장 확실하게 'knam'을 얻어올 수 있음)
                items = self.search_krx_stocks(minimum_price=0, maximum_price=999999999, minimum_volume=0)
                for item in items:
                    if item.get("symb") == symbol:
                        return item.get("knam") or symbol
            except Exception:
                pass
            
            # 검색에서 못 찾았을 경우, Yahoo Finance 폴백 (.KS 코스피, .KQ 코스닥)
            try:
                for suffix in [".KS", ".KQ"]:
                    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={symbol}{suffix}"
                    headers = {"User-Agent": "Mozilla/5.0"}
                    res = requests.get(url, headers=headers, timeout=5)
                    if res.ok:
                        quotes = res.json().get('quotes', [])
                        if quotes:
                            name = quotes[0].get('shortname') or quotes[0].get('longname')
                            if name:
                                return name
            except Exception:
                pass
        else:
            # 해외 주식의 한글 종목명(예: 메타 플랫폼스(페이스북)) 조회를 위해 거래량 랭킹 API를 우선 활용
            try:
                items = self.search_stocks(exchange=exchange, minimum_price=0, maximum_price=999999999, minimum_volume=0)
                for item in items:
                    if item.get("symb") == symbol:
                        return item.get("name") or item.get("ename") or symbol
            except Exception:
                pass

            try:
                url = f"https://query2.finance.yahoo.com/v1/finance/search?q={symbol}"
                headers = {"User-Agent": "Mozilla/5.0"}
                res = requests.get(url, headers=headers, timeout=5)
                if res.ok:
                    quotes = res.json().get('quotes', [])
                    if quotes:
                        return quotes[0].get('shortname') or quotes[0].get('longname') or symbol
            except Exception:
                pass
        return symbol

    def resolve_symbol(self, exchange: str, symbol: str) -> str:
        """사용자가 입력한 기호(예: APPL, Apple)를 올바른 티커(AAPL)로 자동 교정합니다."""
        if exchange == "KRX":
            return symbol.upper()
        else:
            try:
                url = f"https://query2.finance.yahoo.com/v1/finance/search?q={symbol}"
                headers = {"User-Agent": "Mozilla/5.0"}
                res = requests.get(url, headers=headers, timeout=3)
                if res.ok:
                    quotes = res.json().get('quotes', [])
                    if quotes:
                        # 가장 정확한 매칭 결과의 실제 티커 리턴
                        return quotes[0].get('symbol').upper()
            except Exception:
                pass
            return symbol.upper()
    def get_fundamentals(self, exchange: str, symbol: str) -> Dict[str, Any]:
        """주식의 펀더멘털 지표(PER, PBR, EPS, 시가총액, 52주 고/저)를 조회합니다."""
        try:
            if exchange == "KRX":
                url = f"{self.settings.kis_base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
                params = {
                    "FID_COND_MRKT_DIV_CODE": "J",
                    "FID_INPUT_ISCD": symbol.upper(),
                }
                res = requests.get(url, headers=self._get_headers("FHKST01010100"), params=params, timeout=5)
                if res.ok and res.json().get("rt_cd") in (None, "0"):
                    data = res.json().get("output", {})
                    # hts_avls: 시가총액 (억 원 단위) -> 조 원, 억 원 포맷팅은 프론트에서 또는 여기서. 일단 float
                    mcap = float(data.get("hts_avls") or 0) * 100000000 # 원 단위
                    return {
                        "per": float(data.get("per") or 0),
                        "pbr": float(data.get("pbr") or 0),
                        "eps": float(data.get("eps") or 0),
                        "mcap": mcap,
                        "high52": float(data.get("w52_hgpr") or 0),
                        "low52": float(data.get("w52_lwpr") or 0),
                        "currency": "KRW"
                    }
            else:
                url = f"{self.settings.kis_base_url}/uapi/overseas-price/v1/quotations/price-detail"
                params = {
                    "AUTH": "",
                    "EXCD": exchange,
                    "SYMB": symbol.upper(),
                }
                res = requests.get(url, headers=self._get_headers("HHDFS76200200"), params=params, timeout=5)
                if res.ok and res.json().get("rt_cd") in (None, "0"):
                    data = res.json().get("output", {})
                    # tomv: 당일시가총액, mcap: 시가총액
                    # 보통 tomv가 더 정확한 경우가 많음, tomv는 천단위인지 확인 필요. 일단 mcap (백만 기준? 데이터 확인 필요)
                    return {
                        "per": float(data.get("perx") or 0),
                        "pbr": float(data.get("pbrx") or 0),
                        "eps": float(data.get("epsx") or 0),
                        "mcap": float(data.get("tomv") or data.get("mcap") or 0),
                        "high52": float(data.get("h52p") or 0),
                        "low52": float(data.get("l52p") or 0),
                        "currency": data.get("curr", "USD")
                    }
        except Exception as e:
            pass
        return {}

    def get_order_book(self, exchange: str, symbol: str) -> Dict[str, Any]:
        """실시간 호가창 데이터를 조회합니다."""
        try:
            if exchange == "KRX":
                url = f"{self.settings.kis_base_url}/uapi/domestic-stock/v1/quotations/inquire-asking-price-exp-ccn"
                params = {
                    "FID_COND_MRKT_DIV_CODE": "J",
                    "FID_INPUT_ISCD": symbol.upper(),
                }
                res = requests.get(url, headers=self._get_headers("FHKST01010200"), params=params, timeout=5)
                if res.ok and res.json().get("rt_cd") in (None, "0"):
                    data = res.json().get("output1", {})
                    asks = []
                    bids = []
                    for i in range(1, 11):
                        ap = float(data.get(f"askp{i}") or 0)
                        av = int(data.get(f"askp_rsqn{i}") or 0)
                        if ap > 0: asks.append({"price": ap, "volume": av})
                        
                        bp = float(data.get(f"bidp{i}") or 0)
                        bv = int(data.get(f"bidp_rsqn{i}") or 0)
                        if bp > 0: bids.append({"price": bp, "volume": bv})
                    
                    # 매도는 가격 내림차순 정렬 (높은 가격이 위)
                    asks = sorted(asks, key=lambda x: x["price"], reverse=True)
                    # 매수는 가격 내림차순 정렬 (높은 가격이 위)
                    bids = sorted(bids, key=lambda x: x["price"], reverse=True)
                    
                    return {"asks": asks, "bids": bids}
            else:
                url = f"{self.settings.kis_base_url}/uapi/overseas-price/v1/quotations/inquire-asking-price"
                params = {
                    "AUTH": "",
                    "EXCD": exchange,
                    "SYMB": symbol.upper(),
                }
                res = requests.get(url, headers=self._get_headers("HHDFS76200100"), params=params, timeout=5)
                if res.ok and res.json().get("rt_cd") in (None, "0"):
                    data = res.json().get("output2", {})
                    asks = []
                    bids = []
                    for i in range(1, 11):
                        ap = float(data.get(f"pask{i}") or 0)
                        av = int(data.get(f"vask{i}") or 0)
                        if ap > 0: asks.append({"price": ap, "volume": av})
                        
                        bp = float(data.get(f"pbid{i}") or 0)
                        bv = int(data.get(f"vbid{i}") or 0)
                        if bp > 0: bids.append({"price": bp, "volume": bv})
                    
                    asks = sorted(asks, key=lambda x: x["price"], reverse=True)
                    bids = sorted(bids, key=lambda x: x["price"], reverse=True)
                    
                    return {"asks": asks, "bids": bids}
        except Exception as e:
            pass
        return {"asks": [], "bids": []}

    def place_order(
        self,
        exchange: str,
        symbol: str,
        side: str,
        quantity: int,
        price: float,
        order_type: str = "limit"
    ) -> Dict[str, Any]:
        """주식을 매수/매도합니다."""
        is_krx = (exchange == "KRX")
        
        if is_krx:
            url = f"{self.settings.kis_base_url}/uapi/domestic-stock/v1/trading/order-cash"
            if self.settings.kis_is_paper:
                tr_id = "VTTC0802U" if side == "buy" else "VTTC0801U"
            else:
                tr_id = "TTTC0802U" if side == "buy" else "TTTC0801U"
                
            ord_dvsn = "00" if order_type == "limit" else "01"
            ord_unpr = str(int(price)) if order_type == "limit" else "0"
            
            data = {
                "CANO": self.settings.kis_account_no,
                "ACNT_PRDT_CD": self.settings.kis_account_product_code,
                "PDNO": symbol.upper(),
                "ORD_DVSN": ord_dvsn,
                "ORD_QTY": str(quantity),
                "ORD_UNPR": ord_unpr,
            }
        else:
            url = f"{self.settings.kis_base_url}/uapi/overseas-stock/v1/trading/order"
            if self.settings.kis_is_paper:
                tr_id = "VTTT1002U" if side == "buy" else "VTTT1001U"
            else:
                tr_id = "JTTT1002U" if side == "buy" else "JTTT1006U"
                
            ord_dvsn = "00"
            if order_type == "market":
                raise ValueError("해외 주식 시장가 주문은 현재 지정가로만 지원하거나 별도 TR_ID가 필요합니다.")
                
            data = {
                "CANO": self.settings.kis_account_no,
                "ACNT_PRDT_CD": self.settings.kis_account_product_code,
                "OVRS_EXCG_CD": exchange,
                "PDNO": symbol.upper(),
                "ORD_QTY": str(quantity),
                "OVRS_ORD_UNPR": str(price),
                "ORD_SVR_DVSN_CD": "0",
                "ORD_DVSN": ord_dvsn
            }
            
        headers = self._get_headers(tr_id)
        
        # POST 요청
        response = requests.post(url, headers=headers, json=data, timeout=10)
        
        try:
            result = response.json()
        except:
            raise KisApiError(f"주문 응답 파싱 실패: {response.text}")
            
        if not response.ok or result.get("rt_cd") != "0":
            msg = result.get("msg1", "알 수 없는 주문 오류")
            raise KisApiError(f"주문 실패: {msg}")
            
        return result

    def get_balance(self) -> Dict[str, Any]:
        """국내 주식 잔고를 조회합니다."""
        url = f"{self.settings.kis_base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
        tr_id = "VTTC8434R" if self.settings.kis_is_paper else "TTTC8434R"
        
        params = {
            "CANO": self.settings.kis_account_no,
            "ACNT_PRDT_CD": self.settings.kis_account_product_code,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": ""
        }
        
        headers = self._get_headers(tr_id)
        res = requests.get(url, headers=headers, params=params, timeout=10)
        if not res.ok:
            error_msg = f"HTTP {res.status_code}"
            try:
                err_data = res.json()
                if "msg1" in err_data:
                    error_msg += f" - {err_data['msg1']}"
            except:
                pass
            raise KisApiError(f"잔고 조회 실패: {error_msg}")
            
        data = res.json()
        if data.get("rt_cd") != "0":
            raise KisApiError(f"잔고 조회 실패: {data.get('msg1')}")
            
        # 총 평가금액 정보
        summary = data.get("output2", [{}])[0]
        # 보유 종목 목록
        stocks = data.get("output1", [])
        
        return {
            "total_evaluated_amount": float(summary.get("tot_evlu_amt", 0)),
            "total_purchased_amount": float(summary.get("pchs_amt_smtl_amt", 0)),
            "total_profit_loss": float(summary.get("evlu_pfls_smtl_amt", 0)),
            "total_profit_loss_rate": float(summary.get("evlu_pfls_rt", 0)),
            "orderable_cash": float(summary.get("prvs_rcdl_excc_amt", 0)), # D+2 예수금
            "stocks": [
                {
                    "symbol": s.get("pdno"),
                    "name": s.get("prdt_name"),
                    "quantity": int(s.get("hldg_qty", 0)),
                    "purchase_price": float(s.get("pchs_avg_pric", 0)),
                    "current_price": float(s.get("prpr", 0)),
                    "profit_loss": float(s.get("evlu_pfls_amt", 0)),
                    "profit_loss_rate": float(s.get("evlu_pfls_rt", 0)),
                }
                for s in stocks if int(s.get("hldg_qty", 0)) > 0
            ]
        }
