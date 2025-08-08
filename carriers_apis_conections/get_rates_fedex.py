#!/usr/bin/env python3
"""
FedEx Rates & Service Availability client

Features
- OAuth2 client-credentials token management (sandbox/production)
- Comprehensive Rates endpoint: /rate/v1/comprehensiverates/quotes
- Service Availability (Transit Times): /availability/v1/transittimes
- Safe retries with backoff
- Simple CLI for quick testing

Env vars
- FEDEX_API_KEY
- FEDEX_SECRET_KEY
- FEDEX_ACCOUNT_NUMBER
- FEDEX_TEST_MODE ("true"/"false"; default: true)

Usage (CLI)
  python carriers_apis_conections/get_rates_fedex.py --from-country US --from-postal 38125 \
      --to-country AR --to-postal C1000 --weight 2.5 --unit KG --currency USD

Note
This module aims to be dev-friendly and mirrors the style used in DHL integration.
"""

from __future__ import annotations

import os
import sys
import time
import base64
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import requests
import backoff


@dataclass
class FedExCredentials:
    client_id: str
    client_secret: str
    account_number: str
    test_mode: bool = True


class FedExAPIError(Exception):
    pass


class FedExRatesAPI:
    """Client for FedEx OAuth + Rates + Service Availability APIs."""

    def __init__(self, credentials: Optional[FedExCredentials] = None):
        if credentials is None:
            credentials = FedExCredentials(
                client_id=os.getenv("FEDEX_API_KEY", ""),
                client_secret=os.getenv("FEDEX_SECRET_KEY", ""),
                account_number=os.getenv("FEDEX_ACCOUNT_NUMBER", ""),
                test_mode=os.getenv("FEDEX_TEST_MODE", "true").lower() in {"1", "true", "yes", "y"},
            )
        self.credentials = credentials

        if not self.credentials.client_id or not self.credentials.client_secret:
            raise FedExAPIError("Missing FEDEX_API_KEY/FEDEX_SECRET_KEY credentials")
        if not self.credentials.account_number:
            raise FedExAPIError("Missing FEDEX_ACCOUNT_NUMBER")

        # Safety: default to sandbox; block prod unless explicitly allowed
        if not self.credentials.test_mode:
            allow_prod = os.getenv("FEDEX_ALLOW_PROD", "false").lower() in {"1", "true", "yes", "y"}
            if not allow_prod:
                raise FedExAPIError(
                    "Production mode blocked. Set FEDEX_ALLOW_PROD=true to enable production calls."
                )

        self.base_url = "https://apis-sandbox.fedex.com" if self.credentials.test_mode else "https://apis.fedex.com"
        self.oauth_url = f"{self.base_url}/oauth/token"
        self.rate_endpoint = f"{self.base_url}/rate/v1/comprehensiverates/quotes"
        self.transit_endpoint = f"{self.base_url}/availability/v1/transittimes"

        self._access_token: Optional[str] = None
        self._token_expiry_epoch: float = 0.0

    # ----------------------- OAuth -----------------------
    def _basic_auth_header(self) -> str:
        basic = f"{self.credentials.client_id}:{self.credentials.client_secret}".encode("utf-8")
        return "Basic " + base64.b64encode(basic).decode("ascii")

    def _is_token_valid(self) -> bool:
        return bool(self._access_token) and time.time() < (self._token_expiry_epoch - 60)

    @backoff.on_exception(backoff.expo, (requests.RequestException,), max_tries=5, jitter=backoff.full_jitter)
    def _fetch_token(self) -> None:
        # Strategy 1: Basic auth header + grant_type only
        headers_basic = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": self._basic_auth_header(),
        }
        data_basic = {"grant_type": "client_credentials"}
        resp = requests.post(self.oauth_url, headers=headers_basic, data=data_basic, timeout=30)
        if resp.status_code == 200:
            payload = resp.json()
            self._access_token = payload.get("access_token")
            expires_in = int(payload.get("expires_in", 3500))
            self._token_expiry_epoch = time.time() + expires_in
            if not self._access_token:
                raise FedExAPIError("OAuth response missing access_token")
            return

        # Strategy 2: No Basic; send client_id/client_secret in body
        headers_body = {"Content-Type": "application/x-www-form-urlencoded"}
        data_body = {
            "grant_type": "client_credentials",
            "client_id": self.credentials.client_id,
            "client_secret": self.credentials.client_secret,
        }
        resp2 = requests.post(self.oauth_url, headers=headers_body, data=data_body, timeout=30)
        if resp2.status_code != 200:
            # Surface best error
            err_text = resp2.text or resp.text
            raise FedExAPIError(f"OAuth failed: {resp2.status_code} {err_text}")
        payload = resp2.json()
        self._access_token = payload.get("access_token")
        expires_in = int(payload.get("expires_in", 3500))
        self._token_expiry_epoch = time.time() + expires_in
        if not self._access_token:
            raise FedExAPIError("OAuth response missing access_token")

    def get_access_token(self) -> str:
        if not self._is_token_valid():
            self._fetch_token()
        assert self._access_token
        return self._access_token

    # ----------------------- Helpers -----------------------
    def _auth_headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        token = self.get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-locale": "en_US",
        }
        if extra:
            headers.update(extra)
        return headers

    # ----------------------- Public API -----------------------
    @backoff.on_exception(backoff.expo, (requests.RequestException,), max_tries=5, jitter=backoff.full_jitter)
    def get_comprehensive_rates(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = requests.post(self.rate_endpoint, headers=self._auth_headers(), json=payload, timeout=40)
        if resp.status_code != 200:
            raise FedExAPIError(f"Rates request failed: {resp.status_code} {resp.text}")
        return resp.json()

    @backoff.on_exception(backoff.expo, (requests.RequestException,), max_tries=5, jitter=backoff.full_jitter)
    def get_transit_times(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = requests.post(self.transit_endpoint, headers=self._auth_headers(), json=payload, timeout=40)
        if resp.status_code != 200:
            raise FedExAPIError(f"Transit request failed: {resp.status_code} {resp.text}")
        return resp.json()

    # ----------------------- Builders -----------------------
    def build_rate_request(
        self,
        shipper_country: str,
        shipper_postal: str,
        recipient_country: str,
        recipient_postal: str,
        weight_value: float,
        weight_units: str = "KG",
        currency: str = "USD",
        ship_date: Optional[datetime] = None,
        pickup_type: str = "USE_SCHEDULED_PICKUP",
        return_transit_times: bool = True,
    ) -> Dict[str, Any]:
        """Create a minimal valid payload for comprehensive rates.

        See comprehensive-rate.json components/schemas/FullSchema1 and RequestedShipment.
        """
        if ship_date is None:
            ship_date = datetime.utcnow() + timedelta(days=1)
        ship_date_str = ship_date.strftime("%Y-%m-%d")

        payload: Dict[str, Any] = {
            "accountNumber": {"value": self.credentials.account_number},
            "rateRequestControlParameters": {
                "returnTransitTimes": bool(return_transit_times)
            },
            "requestedShipment": {
                "shipper": {
                    "address": {
                        "postalCode": shipper_postal,
                        "countryCode": shipper_country,
                        # Optional extras
                        "residential": False,
                    }
                },
                "recipient": {
                    "address": {
                        "postalCode": recipient_postal,
                        "countryCode": recipient_country,
                        "residential": False,
                    }
                },
                "preferredCurrency": currency,
                "shipDateStamp": ship_date_str,
                "pickupType": pickup_type,
                "packagingType": "YOUR_PACKAGING",
                "totalPackageCount": 1,
                "rateRequestType": ["ACCOUNT", "LIST"],
                "shippingChargesPayment": {"paymentType": "SENDER"},
                "requestedPackageLineItems": [
                    {
                        "weight": {
                            "units": weight_units,
                            "value": float(weight_value),
                        }
                    }
                ],
            },
            # Optional filter by carrier(s)
            # "carrierCodes": ["FDXE", "FDXG"],
        }
        # For international shipments, include totalWeight as per schema guidance
        if shipper_country.upper() != recipient_country.upper():
            payload["requestedShipment"]["totalWeight"] = float(weight_value)
            payload["requestedShipment"]["documentShipment"] = False
            # Minimal customs clearance detail
            payload["requestedShipment"]["customsClearanceDetail"] = {
                "commercialInvoice": {
                    "shipmentPurpose": "SOLD"
                },
                "commodities": [
                    {
                        "description": "General goods",
                        "name": "General goods",
                        "quantity": 1,
                        "quantityUnits": "PCS",
                        "countryOfManufacture": shipper_country,
                        "weight": {"units": weight_units, "value": float(weight_value)},
                        "customsValue": {"amount": 100, "currency": currency}
                    }
                ]
            }
        return payload

    def build_transit_request(
        self,
        shipper_country: str,
        shipper_postal: str,
        recipient_country: str,
        recipient_postal: str,
        weight_value: float,
        weight_units: str = "KG",
        ship_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Create a payload for Transit Times.

        The exact schema in service-availability.json expects a shipment-like body.
        This builder aligns fields with typical minimal requirements.
        """
        if ship_date is None:
            ship_date = datetime.utcnow() + timedelta(days=1)
        ship_date_str = ship_date.strftime("%Y-%m-%d")

        payload: Dict[str, Any] = {
            "origin": {
                "address": {
                    "postalCode": shipper_postal,
                    "countryCode": shipper_country,
                    "residential": False,
                }
            },
            "destination": {
                "address": {
                    "postalCode": recipient_postal,
                    "countryCode": recipient_country,
                    "residential": False,
                }
            },
            "shipDate": ship_date_str,
            "packages": [
                {
                    "weight": {"units": weight_units, "value": float(weight_value)}
                }
            ],
        }
        return payload


def _print_rate_summary(rate_json: Dict[str, Any]) -> None:
    output = rate_json.get("output") or rate_json
    rate_reply = output.get("rateReplyDetails") if isinstance(output, dict) else None
    if not rate_reply:
        # Try other shapes before giving up
        print(json.dumps(rate_json, indent=2))
        return

    print("FedEx Rate Quote Results:")
    print("=" * 60)
    for i, detail in enumerate(rate_reply, 1):
        service = detail.get("serviceType", "Unknown")
        name = detail.get("serviceName", "Unknown Service")
        
        # Extract commit/transit info
        commit = detail.get("commit", {})
        transit_days = commit.get("transitDays", {}).get("description", "N/A")
        
        print(f"\n{i}. {service}")
        print(f"   Name: {name}")
        print(f"   Transit: {transit_days}")
        
        # Process rated details (account vs list rates)
        rated = detail.get("ratedShipmentDetails") or []
        if isinstance(rated, list) and rated:
            for rate_detail in rated:
                rate_type = rate_detail.get("rateType", "Unknown")
                total_net = rate_detail.get("totalNetCharge")
                currency = rate_detail.get("currency", "USD")
                
                if total_net is not None:
                    print(f"   {rate_type} Rate: {total_net} {currency}")
                    
                    # Show breakdown if available
                    shipment_rate = rate_detail.get("shipmentRateDetail", {})
                    base_charge = shipment_rate.get("totalBaseCharge")
                    surcharges = shipment_rate.get("totalSurcharges")
                    fuel_pct = shipment_rate.get("fuelSurchargePercent")
                    
                    if base_charge is not None:
                        print(f"     Base: {base_charge} {currency}")
                    if surcharges is not None:
                        print(f"     Surcharges: {surcharges} {currency}")
                    if fuel_pct is not None:
                        print(f"     Fuel %: {fuel_pct}%")
        else:
            print("   Rate: Not available")
    
    print("\n" + "=" * 60)


def _parse_bool(value: Optional[str], default: bool = True) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "y"}


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="FedEx Rates quick test")
    parser.add_argument("--from-country", required=False, default="US")
    parser.add_argument("--from-postal", required=False, default="38125")
    parser.add_argument("--to-country", required=False, default="AR")
    parser.add_argument("--to-postal", required=False, default="C1000")
    parser.add_argument("--weight", type=float, required=False, default=2.0)
    parser.add_argument("--unit", required=False, default="KG", choices=["KG", "LB"]) 
    parser.add_argument("--currency", required=False, default="USD")
    parser.add_argument("--transit-only", action="store_true")
    parser.add_argument("--test-mode", required=False, default=os.getenv("FEDEX_TEST_MODE", "true"))

    args = parser.parse_args(argv)

    creds = FedExCredentials(
        client_id=os.getenv("FEDEX_API_KEY", ""),
        client_secret=os.getenv("FEDEX_SECRET_KEY", ""),
        account_number=os.getenv("FEDEX_ACCOUNT_NUMBER", ""),
        test_mode=_parse_bool(str(args.test_mode)),
    )

    api = FedExRatesAPI(credentials=creds)

    if args.transit_only:
        payload = api.build_transit_request(
            shipper_country=args.from_country,
            shipper_postal=args.from_postal,
            recipient_country=args.to_country,
            recipient_postal=args.to_postal,
            weight_value=args.weight,
            weight_units=args.unit,
        )
        data = api.get_transit_times(payload)
        print(json.dumps(data, indent=2))
        return 0

    # Rates with transit
    payload = api.build_rate_request(
        shipper_country=args.from_country,
        shipper_postal=args.from_postal,
        recipient_country=args.to_country,
        recipient_postal=args.to_postal,
        weight_value=args.weight,
        weight_units=args.unit,
        currency=args.currency,
        return_transit_times=True,
    )
    data = api.get_comprehensive_rates(payload)
    _print_rate_summary(data)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FedExAPIError as exc:
        print(f"FedEx error: {exc}")
        raise SystemExit(2)
