#!/usr/bin/env python3
"""
🚚 API Unificada de Envíos - FedEx + DHL
=======================================

Sistema inteligente que:
1. Consulta tanto FedEx como DHL
2. Compara precios automáticamente
3. Selecciona la opción más económica
4. Maneja fallbacks y errores elegantemente
5. Normaliza respuestas en formato estándar

Uso:
    api = UnifiedShippingAPI()
    result = api.get_best_rate(weight_kg=2.0, origin="US", dest="AR")
    print(f"Mejor opción: {result['carrier']} - ${result['cost_usd']:.2f}")
"""

import os
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
import asyncio
import concurrent.futures

# Agregar path para imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from carriers_apis_conections.get_rates_fedex import FedExRatesAPI, FedExCredentials, FedExAPIError
    from carriers_apis_conections.fedex_config import get_fedex_credentials, FEDEX_DEFAULTS
    FEDEX_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ FedEx no disponible: {e}")
    FEDEX_AVAILABLE = False

try:
    from .get_rates_dhl import DHLRatesAPI
    from .dhl_config import get_dhl_credentials, DHL_DEFAULTS
    DHL_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ DHL no disponible: {e}")
    DHL_AVAILABLE = False


@dataclass
class ShippingQuote:
    """Cotización normalizada de envío"""
    carrier: str
    service_name: str
    cost_usd: float
    currency: str
    transit_days: Optional[int]
    success: bool
    error_message: Optional[str] = None
    raw_response: Optional[Dict] = None
    rate_type: str = "UNKNOWN"  # ACCOUNT, LIST, etc.


@dataclass
class ShippingRequest:
    """Request normalizado para cotización"""
    weight_kg: float
    origin_country: str
    origin_postal: str
    dest_country: str
    dest_postal: str
    currency: str = "USD"
    dimensions_cm: Optional[Dict[str, float]] = None


class UnifiedShippingAPI:
    """API unificada para consultas de envío multi-carrier"""
    
    def __init__(self, test_mode: bool = True, debug: bool = False):
        """
        Inicializar API unificada
        
        Args:
            test_mode: Usar sandbox/test environments
            debug: Habilitar logs detallados
        """
        self.test_mode = test_mode
        self.debug = debug
        self.fedex_client = None
        self.dhl_client = None
        
        # Inicializar FedEx
        if FEDEX_AVAILABLE:
            try:
                fedex_creds = get_fedex_credentials()
                self.fedex_client = FedExRatesAPI(FedExCredentials(
                    client_id=fedex_creds["client_id"],
                    client_secret=fedex_creds["client_secret"],
                    account_number=fedex_creds["account_number"],
                    test_mode=test_mode
                ))
                self._debug_log("✅ FedEx client initialized")
            except Exception as e:
                self._debug_log(f"❌ FedEx init failed: {e}")
        
        # Inicializar DHL
        if DHL_AVAILABLE:
            try:
                dhl_creds = get_dhl_credentials()
                self.dhl_client = DHLRatesAPI(
                    username=dhl_creds["username"],
                    password=dhl_creds["password"],
                    test_mode=test_mode
                )
                self._debug_log("✅ DHL client initialized")
            except Exception as e:
                self._debug_log(f"❌ DHL init failed: {e}")
    
    def _debug_log(self, message: str):
        """Log debug messages"""
        if self.debug:
            print(f"[UnifiedAPI] {message}")
    
    def _normalize_weight_to_kg(self, weight: float, unit: str) -> float:
        """Convertir peso a kilogramos"""
        unit = unit.upper()
        if unit in ["KG", "KILOGRAM", "KILOGRAMS"]:
            return weight
        elif unit in ["LB", "LBS", "POUND", "POUNDS"]:
            return weight * 0.453592
        else:
            self._debug_log(f"⚠️ Unknown weight unit: {unit}, assuming KG")
            return weight
    
    def _normalize_postal_code(self, postal_code: str, country_code: str) -> str:
        """Normalize postal codes for carrier requirements"""
        if not postal_code:
            return postal_code
            
        country_code = country_code.upper()
        
        # Argentina requires 4-digit numeric postal codes for DHL
        if country_code == "AR":
            # Remove any non-numeric characters
            numeric_only = ''.join(filter(str.isdigit, postal_code))
            if len(numeric_only) >= 4:
                return numeric_only[:4]  # Take first 4 digits
            elif len(numeric_only) > 0:
                return numeric_only.zfill(4)  # Pad with zeros
            else:
                return "1440"  # Default to working postal code
        
        # For other countries, return as-is
        return postal_code
    
    def get_fedex_quotes(self, request: ShippingRequest) -> List[ShippingQuote]:
        """Obtener cotizaciones de FedEx"""
        quotes = []
        
        if not self.fedex_client:
            return [ShippingQuote(
                carrier="FedEx",
                service_name="N/A",
                cost_usd=0.0,
                currency="USD",
                transit_days=None,
                success=False,
                error_message="FedEx client not available"
            )]
        
        try:
            self._debug_log(f"🚀 Querying FedEx for {request.weight_kg}kg")
            
            payload = self.fedex_client.build_rate_request(
                shipper_country=request.origin_country,
                shipper_postal=request.origin_postal,
                recipient_country=request.dest_country,
                recipient_postal=request.dest_postal,
                weight_value=request.weight_kg,
                weight_units="KG",
                currency=request.currency,
                return_transit_times=True
            )
            
            response = self.fedex_client.get_comprehensive_rates(payload)
            self._debug_log("✅ FedEx response received")
            
            # Parse FedEx response
            output = response.get("output") or response
            rate_reply = output.get("rateReplyDetails", [])
            
            for detail in rate_reply:
                service_type = detail.get("serviceType", "Unknown")
                service_name = detail.get("serviceName", "Unknown Service")
                
                # Extract transit info
                commit = detail.get("commit", {})
                transit_desc = commit.get("transitDays", {}).get("description", "N/A")
                try:
                    # Extract days from description like "2 Business Days"
                    transit_days = int(transit_desc.split()[0]) if transit_desc != "N/A" else None
                except:
                    transit_days = None
                
                # Process rates (prefer ACCOUNT over LIST)
                rated_details = detail.get("ratedShipmentDetails", [])
                for rate_detail in rated_details:
                    rate_type = rate_detail.get("rateType", "Unknown")
                    total_net = rate_detail.get("totalNetCharge")
                    currency = rate_detail.get("currency", "USD")
                    
                    if total_net is not None:
                        quotes.append(ShippingQuote(
                            carrier="FedEx",
                            service_name=f"{service_name} ({rate_type})",
                            cost_usd=float(total_net),
                            currency=currency,
                            transit_days=transit_days,
                            success=True,
                            rate_type=rate_type,
                            raw_response=detail
                        ))
            
            if not quotes:
                quotes.append(ShippingQuote(
                    carrier="FedEx",
                    service_name="N/A",
                    cost_usd=0.0,
                    currency="USD",
                    transit_days=None,
                    success=False,
                    error_message="No rates returned"
                ))
                
        except FedExAPIError as e:
            self._debug_log(f"❌ FedEx API error: {e}")
            quotes.append(ShippingQuote(
                carrier="FedEx",
                service_name="N/A",
                cost_usd=0.0,
                currency="USD",
                transit_days=None,
                success=False,
                error_message=str(e)
            ))
        except Exception as e:
            self._debug_log(f"❌ FedEx unexpected error: {e}")
            quotes.append(ShippingQuote(
                carrier="FedEx",
                service_name="N/A",
                cost_usd=0.0,
                currency="USD",
                transit_days=None,
                success=False,
                error_message=f"Unexpected error: {str(e)}"
            ))
        
        return quotes
    
    def get_dhl_quotes(self, request: ShippingRequest) -> List[ShippingQuote]:
        """Obtener cotizaciones de DHL"""
        quotes = []
        
        if not self.dhl_client:
            return [ShippingQuote(
                carrier="DHL",
                service_name="N/A",
                cost_usd=0.0,
                currency="USD",
                transit_days=None,
                success=False,
                error_message="DHL client not available"
            )]
        
        try:
            self._debug_log(f"🚀 Querying DHL for {request.weight_kg}kg")
            
            # Build DHL request
            dimensions = request.dimensions_cm or {"length": 25, "width": 35, "height": 15}
            
            tomorrow = datetime.now() + timedelta(days=1)
            shipping_date = tomorrow.strftime("%Y-%m-%dT%H:%M:%S GMT-03:00")
            
            # Normalize postal codes for DHL requirements
            origin_postal_normalized = self._normalize_postal_code(request.origin_postal, request.origin_country)
            dest_postal_normalized = self._normalize_postal_code(request.dest_postal, request.dest_country)
            
            rating_data = {
                "customerDetails": {
                    "shipperDetails": {
                        "postalCode": origin_postal_normalized,
                        "cityName": "SHENZHEN" if request.origin_country == "CN" else "ORIGIN_CITY",
                        "countryCode": request.origin_country,
                        "addressLine1": "addres1",  # DHL expects 'addres1' not 'address1'
                        "addressLine2": "addres2",
                        "addressLine3": "addres3"
                    },
                    "receiverDetails": {
                        "postalCode": dest_postal_normalized,
                        "cityName": "CAPITAL FEDERAL" if request.dest_country == "AR" else "DEST_CITY", 
                        "countryCode": request.dest_country,
                        "addressLine1": "addres1",  # DHL expects 'addres1' not 'address1'
                        "addressLine2": "addres2",
                        "addressLine3": "addres3"
                    }
                },
                "accounts": [{
                    "typeCode": "shipper",
                    "number": get_dhl_credentials()["account_number"]
                }],
                "productCode": "P",  # EXPRESS WORLDWIDE
                "plannedShippingDateAndTime": shipping_date,
                "unitOfMeasurement": "metric",
                "isCustomsDeclarable": request.origin_country.upper() != request.dest_country.upper(),
                "nextBusinessDay": True,  # Required field
                "monetaryAmount": [{
                    "typeCode": "declaredValue",
                    "value": 100,
                    "currency": "USD"  # DHL test might expect USD for international
                }],
                "packages": [{
                    "weight": request.weight_kg,
                    "dimensions": dimensions
                }]
            }
            
            response = self.dhl_client.get_rates(rating_data)
            self._debug_log("✅ DHL response received")
            
            if "error" in response:
                error_details = response.get("details", "Unknown error")
                self._debug_log(f"❌ DHL Error Details: {error_details}")
                quotes.append(ShippingQuote(
                    carrier="DHL",
                    service_name="N/A",
                    cost_usd=0.0,
                    currency="USD",
                    transit_days=None,
                    success=False,
                    error_message=f"{response['error']} - {error_details}"
                ))
            else:
                # Parse DHL response
                products = response.get("products", [])
                for product in products:
                    service_name = product.get("productName", "DHL Express")
                    
                    # Get delivery info
                    delivery_info = product.get("deliveryCapabilities", {})
                    transit_days = delivery_info.get("totalTransitDays")
                    
                    # Get pricing (prefer USD BILLC)
                    total_prices = product.get("totalPrice", [])
                    cost_usd = 0.0
                    
                    for price_info in total_prices:
                        if price_info.get("currencyType") == "BILLC" and price_info.get("priceCurrency") == "USD":
                            cost_usd = float(price_info.get("price", 0.0))
                            break
                    else:
                        # Fallback to first available price
                        if total_prices:
                            cost_usd = float(total_prices[0].get("price", 0.0))
                    
                    quotes.append(ShippingQuote(
                        carrier="DHL",
                        service_name=service_name,
                        cost_usd=cost_usd,
                        currency="USD",
                        transit_days=transit_days,
                        success=True,
                        rate_type="ACCOUNT",
                        raw_response=product
                    ))
                
                if not quotes:
                    quotes.append(ShippingQuote(
                        carrier="DHL",
                        service_name="N/A",
                        cost_usd=0.0,
                        currency="USD",
                        transit_days=None,
                        success=False,
                        error_message="No products returned"
                    ))
                    
        except Exception as e:
            self._debug_log(f"❌ DHL error: {e}")
            quotes.append(ShippingQuote(
                carrier="DHL",
                service_name="N/A",
                cost_usd=0.0,
                currency="USD",
                transit_days=None,
                success=False,
                error_message=str(e)
            ))
        
        return quotes
    
    def get_all_quotes(self, request: ShippingRequest) -> Dict[str, List[ShippingQuote]]:
        """Obtener todas las cotizaciones de todos los carriers disponibles"""
        all_quotes = {}
        
        # Get quotes in parallel for better performance
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = {}
            
            if self.fedex_client:
                futures["FedEx"] = executor.submit(self.get_fedex_quotes, request)
            
            if self.dhl_client:
                futures["DHL"] = executor.submit(self.get_dhl_quotes, request)
            
            # Collect results
            for carrier, future in futures.items():
                try:
                    all_quotes[carrier] = future.result(timeout=60)  # 60s timeout
                except concurrent.futures.TimeoutError:
                    self._debug_log(f"⏰ {carrier} timed out")
                    all_quotes[carrier] = [ShippingQuote(
                        carrier=carrier,
                        service_name="N/A",
                        cost_usd=0.0,
                        currency="USD",
                        transit_days=None,
                        success=False,
                        error_message="Request timed out"
                    )]
                except Exception as e:
                    self._debug_log(f"❌ {carrier} failed: {e}")
                    all_quotes[carrier] = [ShippingQuote(
                        carrier=carrier,
                        service_name="N/A",
                        cost_usd=0.0,
                        currency="USD",
                        transit_days=None,
                        success=False,
                        error_message=str(e)
                    )]
        
        return all_quotes
    
    def get_best_rate(self, 
                     weight: float,
                     weight_unit: str = "KG",
                     origin_country: str = "US",
                     origin_postal: str = "38125",
                     dest_country: str = "AR", 
                     dest_postal: str = "C1000",
                     currency: str = "USD",
                     dimensions_cm: Optional[Dict[str, float]] = None,
                     prefer_speed: bool = False) -> Dict[str, Any]:
        """
        Obtener la mejor tarifa comparando todos los carriers
        
        Args:
            weight: Peso del paquete
            weight_unit: Unidad de peso (KG/LB)
            origin_country: País origen
            origin_postal: Código postal origen
            dest_country: País destino
            dest_postal: Código postal destino
            currency: Moneda preferida
            dimensions_cm: Dimensiones en cm
            prefer_speed: Si priorizar velocidad sobre precio
            
        Returns:
            Dict con mejor opción y todas las alternativas
        """
        
        # Normalize request
        weight_kg = self._normalize_weight_to_kg(weight, weight_unit)
        
        request = ShippingRequest(
            weight_kg=weight_kg,
            origin_country=origin_country,
            origin_postal=origin_postal,
            dest_country=dest_country,
            dest_postal=dest_postal,
            currency=currency,
            dimensions_cm=dimensions_cm
        )
        
        self._debug_log(f"🔍 Finding best rate for {weight_kg}kg from {origin_country} to {dest_country}")
        
        # Get all quotes
        all_quotes = self.get_all_quotes(request)
        
        # Flatten and filter successful quotes
        valid_quotes = []
        for carrier, quotes in all_quotes.items():
            for quote in quotes:
                if quote.success and quote.cost_usd > 0:
                    valid_quotes.append(quote)
        
        if not valid_quotes:
            # Return error result
            error_messages = []
            for carrier, quotes in all_quotes.items():
                for quote in quotes:
                    if quote.error_message:
                        error_messages.append(f"{carrier}: {quote.error_message}")
            
            return {
                "success": False,
                "error": "No valid quotes available",
                "details": error_messages,
                "all_quotes": all_quotes,
                "best_quote": None
            }
        
        # Sort quotes by price (and optionally speed)
        if prefer_speed:
            # Sort by transit days first, then price
            valid_quotes.sort(key=lambda q: (q.transit_days or 999, q.cost_usd))
        else:
            # Sort by price first, then transit days
            valid_quotes.sort(key=lambda q: (q.cost_usd, q.transit_days or 999))
        
        best_quote = valid_quotes[0]
        
        self._debug_log(f"💰 Best rate: {best_quote.carrier} - ${best_quote.cost_usd:.2f}")
        
        return {
            "success": True,
            "best_quote": best_quote,
            "carrier": best_quote.carrier,
            "service_name": best_quote.service_name,
            "cost_usd": best_quote.cost_usd,
            "currency": best_quote.currency,
            "transit_days": best_quote.transit_days,
            "rate_type": best_quote.rate_type,
            "all_quotes": all_quotes,
            "alternatives": valid_quotes[1:5],  # Top 4 alternatives
            "request": request
        }


# Convenience functions for easy integration
def get_cheapest_shipping_rate(weight_kg: float,
                              origin_country: str = "US",
                              origin_postal: str = "38125", 
                              dest_country: str = "AR",
                              dest_postal: str = "C1000",
                              test_mode: bool = True,
                              debug: bool = False) -> Dict[str, Any]:
    """
    Función conveniente para obtener la tarifa más barata
    
    Returns:
        Dict con resultado del mejor carrier
    """
    api = UnifiedShippingAPI(test_mode=test_mode, debug=debug)
    return api.get_best_rate(
        weight=weight_kg,
        weight_unit="KG",
        origin_country=origin_country,
        origin_postal=origin_postal,
        dest_country=dest_country,
        dest_postal=dest_postal
    )


def compare_all_carriers(weight_kg: float,
                        origin_country: str = "US",
                        origin_postal: str = "38125",
                        dest_country: str = "AR", 
                        dest_postal: str = "C1000",
                        test_mode: bool = True,
                        debug: bool = False) -> Dict[str, List[ShippingQuote]]:
    """
    Función conveniente para comparar todos los carriers
    
    Returns:
        Dict con todas las cotizaciones organizadas por carrier
    """
    api = UnifiedShippingAPI(test_mode=test_mode, debug=debug)
    
    request = ShippingRequest(
        weight_kg=weight_kg,
        origin_country=origin_country,
        origin_postal=origin_postal,
        dest_country=dest_country,
        dest_postal=dest_postal
    )
    
    return api.get_all_quotes(request)


# CLI for testing
def main():
    """CLI para testing rápido"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Unified Shipping API Test")
    parser.add_argument("--weight", type=float, default=2.0, help="Weight in KG")
    parser.add_argument("--from-country", default="US", help="Origin country")
    parser.add_argument("--from-postal", default="38125", help="Origin postal code")
    parser.add_argument("--to-country", default="AR", help="Destination country")
    parser.add_argument("--to-postal", default="C1000", help="Destination postal code")
    parser.add_argument("--test-mode", action="store_true", default=True, help="Use test mode")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument("--prefer-speed", action="store_true", help="Prefer speed over price")
    
    args = parser.parse_args()
    
    print("🚚 Unified Shipping API Test")
    print("=" * 50)
    
    result = get_cheapest_shipping_rate(
        weight_kg=args.weight,
        origin_country=args.from_country,
        origin_postal=args.from_postal,
        dest_country=args.to_country,
        dest_postal=args.to_postal,
        test_mode=args.test_mode,
        debug=args.debug
    )
    
    if result["success"]:
        best = result["best_quote"]
        print(f"\n🏆 BEST OPTION:")
        print(f"   Carrier: {best.carrier}")
        print(f"   Service: {best.service_name}")
        print(f"   Cost: ${best.cost_usd:.2f} {best.currency}")
        print(f"   Transit: {best.transit_days or 'N/A'} days")
        
        print(f"\n📊 ALL OPTIONS:")
        for carrier, quotes in result["all_quotes"].items():
            print(f"\n{carrier}:")
            for quote in quotes:
                status = "✅" if quote.success else "❌"
                if quote.success:
                    print(f"  {status} {quote.service_name}: ${quote.cost_usd:.2f} ({quote.transit_days or 'N/A'} days)")
                else:
                    print(f"  {status} Error: {quote.error_message}")
    else:
        print(f"\n❌ ERROR: {result['error']}")
        for detail in result.get("details", []):
            print(f"   - {detail}")


if __name__ == "__main__":
    main()