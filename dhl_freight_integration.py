#!/usr/bin/env python3
"""
🚢 Integración DHL Freight - Servicio Completo
==============================================

Servicio integrado que combina:
1. API real de DHL Express
2. Fallback a tarifas de archivo
3. Estimación básica como último recurso

Versión: 2.0 - Con debug completo y extracción mejorada de costos
"""

import os
import sys
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

# Agregar directorio padre para imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Imports de configuración DHL
try:
    from dhl_config import get_dhl_credentials, get_dhl_url, get_default_addresses, DHL_DEFAULTS
    DHL_CONFIG_AVAILABLE = True
except ImportError:
    DHL_CONFIG_AVAILABLE = False

# Imports de la integración DHL
try:
    from carriers_apis_conections.get_rates_dhl import DHLRatesAPI
    DHL_AVAILABLE = True
except ImportError:
    DHL_AVAILABLE = False

# Imports para fallback
try:
    from freight_estimation import load_freight_rates as fallback_load_rates, calculate_air_freight as fallback_air_freight
    FALLBACK_AVAILABLE = True
except ImportError:
    FALLBACK_AVAILABLE = False


class DHLFreightService:
    """Servicio integrado de flete DHL con fallbacks inteligentes y debug completo"""
    
    def __init__(self, 
                 test_mode: bool = None,
                 use_dhl_real: bool = True,
                 fallback_rates_file: Optional[str] = None,
                 custom_credentials: Optional[Dict] = None,
                 debug_callback = None):
        """
        Inicializar servicio de flete DHL integrado
        
        Args:
            test_mode: Usar ambiente de test de DHL (None = usar default)
            use_dhl_real: Si usar DHL real o fallback directo
            fallback_rates_file: Archivo de tarifas para fallback
            custom_credentials: Credenciales personalizadas (opcional)
            debug_callback: Función para registrar debug (opcional)
        """
        # Usar configuración centralizada
        credentials = custom_credentials or get_dhl_credentials()
        self.username = credentials["username"]
        self.password = credentials["password"]
        self.account_number = credentials["account_number"]
        
        self.test_mode = test_mode if test_mode is not None else DHL_DEFAULTS["test_mode"]
        self.use_dhl_real = use_dhl_real and DHL_AVAILABLE
        self.fallback_rates_file = fallback_rates_file
        self.debug_callback = debug_callback
        
        # Inicializar cliente DHL si está disponible
        self.dhl_client = None
        if self.use_dhl_real and DHL_AVAILABLE:
            try:
                self.dhl_client = DHLRatesAPI(
                    username=self.username,
                    password=self.password,
                    test_mode=self.test_mode
                )
                self._debug_log(f"✅ Cliente DHL inicializado en modo {'TEST' if self.test_mode else 'PRODUCCIÓN'}")
            except Exception as e:
                self._debug_log(f"❌ Error inicializando cliente DHL: {e}", level="ERROR")
                self.use_dhl_real = False
        
        # Cargar tarifas de fallback si están disponibles
        self.fallback_rates = None
        if FALLBACK_AVAILABLE and fallback_rates_file:
            try:
                self.fallback_rates = fallback_load_rates(fallback_rates_file)
                self._debug_log(f"✅ Tarifas de fallback cargadas desde {fallback_rates_file}")
            except Exception as e:
                self._debug_log(f"⚠️ Warning: No se pudieron cargar tarifas de fallback: {e}", level="WARNING")
    
    def _debug_log(self, message: str, level: str = "INFO", data: Any = None):
        """Registrar mensaje de debug si hay callback disponible"""
        if self.debug_callback:
            self.debug_callback(message, data, level)
        else:
            print(f"[DHL-{level}] {message}")
    
    def _build_dhl_rating_data(self, 
                              weight_kg: float,
                              dimensions_cm: Dict[str, float],
                              origin_details: Optional[Dict] = None,
                              destination_details: Optional[Dict] = None,
                              shipping_datetime: Optional[datetime] = None) -> Dict[str, Any]:
        """Construir datos de rating usando exactamente la estructura de Rating.txt que funciona"""
        
        # Direcciones por defecto: China -> Argentina (usando formato que funciona en test)
        default_origin = {
            "postalCode": "518000",  # Shenzhen, China
            "cityName": "SHENZHEN",
            "countryCode": "CN",
            "addressLine1": "addres1",  # Usar mismo formato que Rating.txt
            "addressLine2": "addres2",
            "addressLine3": "addres3"
        }
        
        default_destination = {
            "postalCode": "1440",  # Usar mismo código que funciona en Rating.txt
            "cityName": "CAPITAL FEDERAL",
            "countryCode": "AR",
            "addressLine1": "addres1",  # Usar mismo formato que Rating.txt
            "addressLine2": "addres2",
            "addressLine3": "addres3"
        }
        
        # Usar direcciones personalizadas si se proporcionan, sino usar por defecto
        origin = origin_details if origin_details else default_origin
        destination = destination_details if destination_details else default_destination
        
        # Usar fecha específica o fecha dinámica por defecto
        if shipping_datetime:
            shipping_date = shipping_datetime.strftime("%Y-%m-%dT%H:%M:%S GMT-03:00")
        else:
            # Fecha dinámica (mañana) en formato correcto
            tomorrow = datetime.now() + timedelta(days=1)
            shipping_date = tomorrow.strftime("%Y-%m-%dT%H:%M:%S GMT-03:00")
        
        # Usar exactamente la estructura de Rating.txt con direcciones modificables
        rating_data = {
            "customerDetails": {
                "shipperDetails": origin,
                "receiverDetails": destination
            },
            "accounts": [
                {
                    "typeCode": "shipper",
                    "number": self.account_number  # Número de cuenta desde configuración
                }
            ],
            "productCode": "P",
            "plannedShippingDateAndTime": shipping_date,  # Fecha específica o dinámica
            "unitOfMeasurement": "metric",
            "isCustomsDeclarable": True,
            "monetaryAmount": [
                {
                    "typeCode": "declaredValue",
                    "value": 100,  # Exacto como Rating.txt que funciona
                    "currency": "GBP"  # Exacto como en Rating.txt que funciona
                }
            ],
            "packages": [
                {
                    "weight": weight_kg,  # Solo cambiar el peso
                    "dimensions": {
                        "length": dimensions_cm.get('length', 25),
                        "width": dimensions_cm.get('width', 35),
                        "height": dimensions_cm.get('height', 15)
                    }
                }
            ]
        }
        
        self._debug_log(f"📦 Usando estructura DHL con fecha: {shipping_date}", data=rating_data)
        
        return rating_data
    
    def _try_multiple_dates(self, 
                           weight_kg: float,
                           dimensions_cm: Dict[str, float],
                           origin_details: Optional[Dict] = None,
                           destination_details: Optional[Dict] = None,
                           base_datetime: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Intenta cotización DHL con múltiples fechas hasta encontrar una que funcione
        
        Args:
            weight_kg: Peso en kg
            dimensions_cm: Dimensiones
            origin_details: Origen
            destination_details: Destino  
            base_datetime: Fecha base a partir de la cual probar
            
        Returns:
            Resultado de la cotización DHL o error
        """
        if not base_datetime:
            base_datetime = datetime.now() + timedelta(days=3)
        
        # Intentar múltiples fechas: la original y hasta 7 días después
        date_offsets = [0, 1, 2, 3, 4, 5, 6, 7]  # 0 = fecha original, luego +1, +2, etc. días
        
        last_error = None
        
        for offset in date_offsets:
            try_date = base_datetime + timedelta(days=offset)
            
            # Saltar fines de semana para DHL
            if try_date.weekday() >= 5:  # 5=sábado, 6=domingo
                continue
                
            self._debug_log(f"🗓️ Intentando fecha: {try_date.strftime('%d/%m/%Y %H:%M')}")
            
            try:
                # Crear datos de rating para esta fecha específica
                rating_data = self._build_dhl_rating_data(
                    weight_kg, dimensions_cm, origin_details, destination_details, try_date
                )
                
                # Realizar cotización DHL
                dhl_response = self.dhl_client.get_rates(rating_data)
                
                # Si la respuesta es exitosa, retornar inmediatamente
                if "error" not in dhl_response and "products" in dhl_response and len(dhl_response["products"]) > 0:
                    self._debug_log(f"✅ Fecha exitosa: {try_date.strftime('%d/%m/%Y %H:%M')}", level="SUCCESS")
                    return dhl_response
                else:
                    # Si hay error específico de fecha, continuar con siguiente fecha
                    error_detail = dhl_response.get('details', '')
                    if "pickup date" in str(error_detail).lower() or "date" in str(error_detail).lower():
                        self._debug_log(f"📅 Fecha {try_date.strftime('%d/%m/%Y')} no disponible, probando siguiente...")
                        last_error = dhl_response
                        continue
                    else:
                        # Error diferente a fecha, retornar error
                        return dhl_response
                        
            except Exception as e:
                self._debug_log(f"❌ Error con fecha {try_date.strftime('%d/%m/%Y')}: {e}")
                last_error = {"error": str(e)}
                continue
        
        # Si llegamos aquí, ninguna fecha funcionó
        self._debug_log("❌ Ninguna fecha funcionó en el rango de 7 días", level="ERROR")
        return last_error or {"error": "No se encontró fecha válida en el rango de 7 días"}
    
    def calculate_dhl_freight(self, 
                            weight_kg: float,
                            dimensions_cm: Dict[str, float],
                            origin_details: Optional[Dict] = None,
                            destination_details: Optional[Dict] = None,
                            shipping_datetime: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Calcular flete usando servicio real de DHL con retry inteligente de fechas
        
        Args:
            weight_kg: Peso total en kg
            dimensions_cm: Dimensiones en cm {length, width, height}
            origin_details: Detalles del origen (opcional)
            destination_details: Detalles del destino (opcional)
            shipping_datetime: Fecha/hora de envío planeada (opcional)
            
        Returns:
            Dict con resultado del cálculo incluyendo seguro e impuestos
        """
        if not self.dhl_client:
            return {
                "success": False,
                "error": "Cliente DHL no disponible",
                "cost_usd": 0.0,
                "method": "dhl_unavailable"
            }
        
        try:
            self._debug_log("📤 Iniciando cotización DHL con retry inteligente de fechas")
            
            # Usar el método de múltiples fechas para mayor robustez
            dhl_response = self._try_multiple_dates(
                weight_kg, dimensions_cm, origin_details, destination_details, shipping_datetime
            )
            
            # SIEMPRE registrar la respuesta completa en debug
            self._debug_log("📥 Respuesta completa de DHL API", data=dhl_response)
            
            # Registrar API call simplificado - solo si el callback es disponible
            if self.debug_callback:
                try:
                    # Intentar usar log_api_call directamente si está disponible en el contexto
                    import streamlit as st
                    if hasattr(st.session_state, 'api_responses'):
                        from streamlit_ai_comercio_exterior import log_api_call
                        log_api_call("DHL_API", {"weight": weight_kg, "dimensions": dimensions_cm}, dhl_response, "error" not in dhl_response)
                except Exception:
                    # Si falla, registrar manualmente
                    try:
                        import streamlit as st
                        if hasattr(st.session_state, 'api_responses'):
                            api_log = {
                                "timestamp": datetime.now().isoformat(),
                                "api_name": "DHL_API",
                                "success": "error" not in dhl_response,
                                "request": {"weight": weight_kg, "dimensions": dimensions_cm},
                                "response": dhl_response,
                                "step": getattr(st.session_state, 'current_step', 'DHL_FREIGHT')
                            }
                            key = f"DHL_API_{len(st.session_state.api_responses)}"
                            st.session_state.api_responses[key] = api_log
                    except Exception:
                        pass  # Si falla todo, continuar sin registro API
            
            if "error" in dhl_response:
                self._debug_log(f"❌ Error en DHL API después del retry: {dhl_response['error']}", level="ERROR", data=dhl_response)
                return {
                    "success": False,
                    "error": f"DHL API Error: {dhl_response['error']}",
                    "cost_usd": 0.0,
                    "method": "dhl_api_error",
                    "details": dhl_response.get('details'),
                    "raw_response": dhl_response
                }
            
            # Extraer costos detallados de la respuesta DHL
            cost_breakdown = self._extract_detailed_costs_from_dhl_response(dhl_response)
            
            return {
                "success": True,
                "cost_usd": cost_breakdown["total_cost"],
                "cost_breakdown": cost_breakdown,
                "method": "dhl_api_real",
                "currency": "USD",
                "service": cost_breakdown.get("service_name", "EXPRESS WORLDWIDE"),
                "transit_days": cost_breakdown.get("transit_days", 2),
                "raw_response": dhl_response,
                "test_mode": self.test_mode,
                "insurance_included": cost_breakdown.get("insurance_cost", 0) > 0,
                "taxes_included": cost_breakdown.get("argentina_taxes", 0) > 0
            }
            
        except Exception as e:
            error_msg = f"Error en DHL freight calculation: {str(e)}"
            self._debug_log(error_msg, level="ERROR")
            return {
                "success": False,
                "error": error_msg,
                "cost_usd": 0.0,
                "method": "dhl_exception"
            }
    
    def _extract_detailed_costs_from_dhl_response(self, dhl_response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extrae costos detallados de la respuesta de DHL, incluyendo seguro e impuestos argentinos,
        pero excluyendo GoGreen Plus según los requerimientos.
        """
        try:
            products = dhl_response.get('products', [])
            if not products:
                return {"total_cost": 0.0, "service_name": "N/A"}
            
            # Usar el primer producto (generalmente EXPRESS WORLDWIDE)
            product = products[0]
            service_name = product.get('productName', 'EXPRESS WORLDWIDE')
            
            # Obtener información de tiempos de tránsito
            delivery_info = product.get('deliveryCapabilities', {})
            transit_days = delivery_info.get('totalTransitDays', 2)
            
            cost_breakdown = {
                "service_name": service_name,
                "transit_days": transit_days,
                "base_service_cost": 0.0,
                "fuel_surcharge": 0.0,
                "insurance_cost": 0.0,
                "argentina_taxes": 0.0,
                "gogreen_cost": 0.0,  # Excluido del total según requerimientos
                "other_costs": 0.0,
                "total_cost": 0.0
            }
            
            # Buscar precio total en USD (BILLC = Billing Currency)
            total_prices = product.get('totalPrice', [])
            for price_info in total_prices:
                if price_info.get('currencyType') == 'BILLC' and price_info.get('priceCurrency') == 'USD':
                    total_cost_raw = float(price_info.get('price', 0.0))
                    break
            else:
                # Fallback: usar el primer precio disponible
                if total_prices:
                    total_cost_raw = float(total_prices[0].get('price', 0.0))
                else:
                    total_cost_raw = 0.0
            
            # Analizar desglose detallado si está disponible
            detailed_breakdown = product.get('detailedPriceBreakdown', [])
            gogreen_cost_to_exclude = 0.0
            
            for currency_breakdown in detailed_breakdown:
                if currency_breakdown.get('currencyType') == 'BILLC' and currency_breakdown.get('priceCurrency') == 'USD':
                    breakdown_items = currency_breakdown.get('breakdown', [])
                    
                    for item in breakdown_items:
                        item_name = item.get('name', '').upper()
                        item_cost = float(item.get('price', 0.0))
                        
                        # Categorizar costos
                        if 'EXPRESS WORLDWIDE' in item_name or 'SERVICE' in item_name:
                            cost_breakdown["base_service_cost"] = item_cost
                        elif 'FUEL' in item_name:
                            cost_breakdown["fuel_surcharge"] = item_cost
                        elif 'PROTECCION' in item_name or 'INSURANCE' in item_name or 'SEGURO' in item_name:
                            cost_breakdown["insurance_cost"] = item_cost
                        elif 'GOGREEN' in item_name or 'CARBON' in item_name:
                            # Registrar pero NO incluir en el total según requerimientos
                            cost_breakdown["gogreen_cost"] = item_cost
                            gogreen_cost_to_exclude = item_cost
                            self._debug_log(f"🌿 GoGreen Plus detectado y excluido: ${item_cost:.2f} USD")
                        elif 'INGBRC' in item_name or 'ARGENTINA' in item_name or any(tax in item_name for tax in ['IVA', 'GANANCIAS', 'BRUTOS']):
                            cost_breakdown["argentina_taxes"] += item_cost
                        else:
                            cost_breakdown["other_costs"] += item_cost
                    break
            
            # Calcular costo total excluyendo GoGreen Plus
            cost_breakdown["total_cost"] = total_cost_raw - gogreen_cost_to_exclude
            
            self._debug_log("💰 Desglose de costos DHL:", data=cost_breakdown)
            
            return cost_breakdown
            
        except Exception as e:
            self._debug_log(f"⚠️ Error extrayendo costos detallados de respuesta DHL: {e}", level="ERROR")
            return {"total_cost": 0.0, "service_name": "Error en procesamiento"}
    
    def calculate_freight_with_fallback(self, 
                                      weight_kg: float,
                                      dimensions_cm: Optional[Dict[str, float]] = None,
                                      origin_details: Optional[Dict] = None,
                                      destination_details: Optional[Dict] = None,
                                      shipping_datetime: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Calcular flete con fallback automático
        
        Args:
            weight_kg: Peso total en kg
            dimensions_cm: Dimensiones en cm (opcional)
            origin_details: Detalles del origen (opcional)
            destination_details: Detalles del destino (opcional)
            shipping_datetime: Fecha/hora de envío planeada (opcional)
            
        Returns:
            Dict con resultado del cálculo
        """
        
        # Dimensiones por defecto si no se proporcionan
        if not dimensions_cm:
            dimensions_cm = {"length": 25, "width": 35, "height": 15}
        
        # INTENTO 1: Usar DHL real si está disponible
        if self.use_dhl_real and self.dhl_client:
            self._debug_log(f"🚀 Intentando cotización DHL real para {weight_kg:.2f} kg...")
            
            dhl_result = self.calculate_dhl_freight(
                weight_kg, dimensions_cm, origin_details, destination_details, shipping_datetime
            )
            
            if dhl_result["success"]:
                self._debug_log(f"✅ DHL real exitoso: ${dhl_result['cost_usd']:.2f} USD")
                return dhl_result
            else:
                self._debug_log(f"⚠️ DHL falló: {dhl_result['error']}", level="WARNING")
        
        # INTENTO 2: Usar tarifas de fallback si están disponibles
        if FALLBACK_AVAILABLE and self.fallback_rates is not None:
            self._debug_log(f"🔄 Usando tarifas de fallback para {weight_kg:.2f} kg...")
            
            try:
                fallback_cost = fallback_air_freight(weight_kg, self.fallback_rates)
                
                return {
                    "success": True,
                    "cost_usd": fallback_cost,
                    "method": "fallback_rates",
                    "currency": "USD",
                    "service": "Estimado (DHL Zona 5)",
                    "transit_days": 2,
                    "note": "Calculado con tarifas de referencia (DHL no disponible)",
                    "insurance_included": False,
                    "taxes_included": False
                }
                
            except Exception as e:
                self._debug_log(f"⚠️ Error en fallback rates: {e}", level="WARNING")
        
        # INTENTO 3: Estimación básica por peso
        self._debug_log(f"📊 Usando estimación básica para {weight_kg:.2f} kg...")
        
        # Estimación conservadora basada en experiencia
        # Para Argentina -> USA vía courier aéreo
        if weight_kg <= 0.5:
            base_cost = 45.0
        elif weight_kg <= 1.0:
            base_cost = 65.0
        elif weight_kg <= 2.0:
            base_cost = 95.0
        elif weight_kg <= 5.0:
            base_cost = 150.0 + (weight_kg - 2.0) * 25.0
        elif weight_kg <= 10.0:
            base_cost = 225.0 + (weight_kg - 5.0) * 35.0
        elif weight_kg <= 20.0:
            base_cost = 400.0 + (weight_kg - 10.0) * 40.0
        else:
            base_cost = 800.0 + (weight_kg - 20.0) * 45.0
        
        return {
            "success": True,
            "cost_usd": base_cost,
            "method": "basic_estimation",
            "currency": "USD",
            "service": "Estimado (Courier Express)",
            "transit_days": 2,
            "note": "Estimación básica - DHL y fallbacks no disponibles",
            "insurance_included": False,
            "taxes_included": False
        }


# Funciones de compatibilidad simplificadas
def calculate_air_freight_dhl(weight_kg: float, 
                             dimensions_cm: Optional[Dict[str, float]] = None,
                             use_real_dhl: bool = True,
                             fallback_rates_file: Optional[str] = None) -> float:
    """Función compatible con la interfaz existente usando DHL real"""
    service = DHLFreightService(use_dhl_real=use_real_dhl, fallback_rates_file=fallback_rates_file)
    result = service.calculate_freight_with_fallback(weight_kg, dimensions_cm)
    return result["cost_usd"]


def get_dhl_service_instance(test_mode: bool = None, 
                           fallback_rates_file: Optional[str] = None) -> DHLFreightService:
    """Obtener instancia del servicio DHL"""
    return DHLFreightService(test_mode=test_mode, fallback_rates_file=fallback_rates_file)


# Función para testing simplificada
def test_dhl_integration():
    """Test rápido de la integración DHL"""
    print("🧪 Probando integración DHL...")
    service = DHLFreightService()
    
    for weight in [0.5, 2.0, 5.0, 10.0]:
        result = service.calculate_freight_with_fallback(weight)
        status = "✅" if result["success"] else "❌"
        print(f"📦 {weight} kg: {status} ${result['cost_usd']:.2f} USD ({result['method']})")
        if result.get("note"):
            print(f"   ℹ️ {result['note']}")


if __name__ == "__main__":
    test_dhl_integration() 