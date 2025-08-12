#!/usr/bin/env python3
"""
Script para obtener tarifas de DHL usando la API MyDHL
Versión: 1.0
Autor: Generado para SunaSolutions AR
"""

import requests
import json
import base64
from datetime import datetime, timedelta
import os
import sys
from typing import Dict, Any, Optional

try:
    from .dhl_config import get_dhl_credentials, get_dhl_url, get_default_addresses, DHL_DEFAULTS
    CONFIG_AVAILABLE = True
except ImportError:
    CONFIG_AVAILABLE = False


class DHLRatesAPI:
    """Cliente para la API de Tarifas de DHL Express"""
    
    def __init__(self, username: str = None, password: str = None, test_mode: bool = None):
        """
        Inicializa el cliente de DHL
        
        Args:
            username: Usuario de DHL (None = usar configuración)
            password: Contraseña de DHL (None = usar configuración)
            test_mode: Si usar el ambiente de test (None = usar configuración)
        """
        # Usar configuración centralizada si está disponible
        if CONFIG_AVAILABLE:
            credentials = get_dhl_credentials()
            self.username = username or credentials["username"]
            self.password = password or credentials["password"]
            self.test_mode = test_mode if test_mode is not None else DHL_DEFAULTS["test_mode"]
        else:
            # Fallback a variables de entorno si no hay configuración
            import os
            self.username = username or os.getenv("DHL_USERNAME", "")
            self.password = password or os.getenv("DHL_PASSWORD", "")
            self.test_mode = test_mode if test_mode is not None else True
        
        # URLs de la API usando configuración centralizada
        if CONFIG_AVAILABLE:
            self.rates_endpoint = get_dhl_url(self.test_mode)
        else:
            # Fallback al método original
            if self.test_mode:
                self.base_url = "https://express.api.dhl.com/mydhlapi/test"
            else:
                self.base_url = "https://express.api.dhl.com/mydhlapi"
            self.rates_endpoint = f"{self.base_url}/rates"
        
        # Headers comunes
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # Configurar autenticación básica
        self._setup_auth()
    
    def _setup_auth(self):
        """Configura la autenticación básica HTTP"""
        # Crear string de autenticación en formato usuario:contraseña
        auth_string = f"{self.username}:{self.password}"
        # Codificar en base64
        auth_bytes = auth_string.encode('ascii')
        auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
        # Agregar header de autorización
        self.headers["Authorization"] = f"Basic {auth_b64}"
    
    def _get_account_number(self):
        """Obtener número de cuenta DHL desde configuración"""
        if CONFIG_AVAILABLE:
            credentials = get_dhl_credentials()
            return credentials.get("account_number", "")
        else:
            import os
            return os.getenv("DHL_ACCOUNT_NUMBER", "")
    
    def load_rating_template(self, filepath: str = "Rating.txt") -> Dict[str, Any]:
        """
        Carga el template de rating desde archivo
        
        Args:
            filepath: Ruta al archivo Rating.txt
            
        Returns:
            Diccionario con los datos del rating
        """
        try:
            # Obtener el directorio del script actual
            script_dir = os.path.dirname(os.path.abspath(__file__))
            full_path = os.path.join(script_dir, filepath)
            
            with open(full_path, 'r', encoding='utf-8') as file:
                return json.load(file)
        except FileNotFoundError:
            print(f"Error: No se encontró el archivo {filepath}")
            return self._get_default_rating_data()
        except json.JSONDecodeError:
            print(f"Error: El archivo {filepath} no contiene JSON válido")
            return self._get_default_rating_data()
    
    def _get_default_rating_data(self) -> Dict[str, Any]:
        """Retorna datos de rating por defecto"""
        # Usar configuración centralizada si está disponible
        if CONFIG_AVAILABLE:
            addresses = get_default_addresses()
            credentials = get_dhl_credentials()
            defaults = DHL_DEFAULTS
            
            # Fecha dinámica (mañana) en formato correcto
            tomorrow = datetime.now() + timedelta(days=1)
            shipping_date = tomorrow.strftime("%Y-%m-%dT%H:%M:%SGMT-03:00")
            
            return {
                "customerDetails": {
                    "shipperDetails": addresses["origin"],
                    "receiverDetails": addresses["destination"]
                },
                "accounts": [
                    {
                        "typeCode": "shipper",
                        "number": credentials["account_number"]
                    }
                ],
                "productCode": defaults["product_code"],
                "plannedShippingDateAndTime": shipping_date,
                "unitOfMeasurement": defaults["unit_of_measurement"],
                "isCustomsDeclarable": True,
                "monetaryAmount": [
                    {
                        "typeCode": "declaredValue",
                        "value": 100,
                        "currency": "GBP"  # Usar GBP como en Rating.txt que funciona
                    }
                ],
                "packages": [
                    {
                        "weight": 10.5,
                        "dimensions": {
                            "length": 25,
                            "width": 35,
                            "height": 15
                        }
                    }
                ]
            }
        else:
            # Fallback cuando no hay configuración centralizada
            tomorrow = datetime.now() + timedelta(days=1)
            shipping_date = tomorrow.strftime("%Y-%m-%dT%H:%M:%SGMT-03:00")
            
            return {
                "customerDetails": {
                    "shipperDetails": {
                        "postalCode": "518000",  # Shenzhen, China
                        "cityName": "SHENZHEN",
                        "countryCode": "CN",
                        "addressLine1": "addres1",
                        "addressLine2": "addres2",
                        "addressLine3": "addres3"
                    },
                    "receiverDetails": {
                        "postalCode": "1440",  # Código que funciona con DHL test
                        "cityName": "CAPITAL FEDERAL",
                        "countryCode": "AR",
                        "addressLine1": "addres1",
                        "addressLine2": "addres2",
                        "addressLine3": "addres3"
                    }
                },
                "accounts": [
                    {
                        "typeCode": "shipper",
                        "number": self._get_account_number()
                    }
                ],
                "productCode": "P",
                "plannedShippingDateAndTime": shipping_date,
                "unitOfMeasurement": "metric",
                "isCustomsDeclarable": True,
                "nextBusinessDay": True,
                "monetaryAmount": [
                    {
                        "typeCode": "declaredValue",
                        "value": 100,
                        "currency": "GBP"
                    }
                ],
                "packages": [
                    {
                        "weight": 10.5,
                        "dimensions": {
                            "length": 25,
                            "width": 35,
                            "height": 15
                        }
                    }
                ]
            }
    
    def get_rates(self, rating_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Obtiene las tarifas de DHL
        
        Args:
            rating_data: Datos para el cálculo de tarifas. Si es None, carga desde Rating.txt
            
        Returns:
            Respuesta de la API con las tarifas
        """
        if rating_data is None:
            rating_data = self.load_rating_template()
        
        try:
            print("🚀 Enviando solicitud a DHL...")
            print(f"URL: {self.rates_endpoint}")
            print(f"Modo: {'TEST' if self.test_mode else 'PRODUCCION'}")
            
            # Realizar la petición POST
            response = requests.post(
                url=self.rates_endpoint,
                headers=self.headers,
                json=rating_data,
                timeout=30
            )
            
            # Verificar código de estado
            print(f"Código de respuesta: {response.status_code}")
            
            if response.status_code == 200:
                print("✅ Solicitud exitosa")
                return response.json()
            elif response.status_code == 401:
                print("❌ Error de autenticación - Verificar credenciales")
                return {"error": "Credenciales inválidas", "status_code": 401}
            elif response.status_code == 400:
                print("❌ Error en los datos enviados")
                try:
                    error_data = response.json()
                    return {"error": "Datos inválidos", "details": error_data, "status_code": 400}
                except:
                    return {"error": "Datos inválidos", "details": response.text, "status_code": 400}
            else:
                print(f"❌ Error inesperado: {response.status_code}")
                return {
                    "error": f"Error HTTP {response.status_code}",
                    "details": response.text,
                    "status_code": response.status_code
                }
                
        except requests.exceptions.Timeout:
            print("❌ Timeout - La petición tardó demasiado")
            return {"error": "Timeout", "message": "La petición tardó demasiado tiempo"}
        except requests.exceptions.ConnectionError:
            print("❌ Error de conexión")
            return {"error": "ConnectionError", "message": "No se pudo conectar a la API de DHL"}
        except Exception as e:
            print(f"❌ Error inesperado: {str(e)}")
            return {"error": "UnexpectedError", "message": str(e)}
    
    def print_rates_summary(self, rates_response: Dict[str, Any]):
        """
        Imprime un resumen de las tarifas obtenidas
        
        Args:
            rates_response: Respuesta de la API con las tarifas
        """
        if "error" in rates_response:
            print(f"\n❌ Error: {rates_response['error']}")
            if "details" in rates_response:
                print(f"Detalles: {rates_response['details']}")
            return
        
        try:
            print("\n" + "="*50)
            print("📋 RESUMEN DE TARIFAS DHL")
            print("="*50)
            
            # Información general
            if "customerDetails" in rates_response:
                print(f"Origen: {rates_response.get('customerDetails', {}).get('shipperDetails', {}).get('cityName', 'N/A')}")
                print(f"Destino: {rates_response.get('customerDetails', {}).get('receiverDetails', {}).get('cityName', 'N/A')}")
            
            # Tarifas disponibles
            if "products" in rates_response:
                print(f"\n🎯 Servicios disponibles: {len(rates_response['products'])}")
                for i, product in enumerate(rates_response['products'], 1):
                    print(f"\n{i}. {product.get('productName', 'N/A')}")
                    print(f"   Código: {product.get('productCode', 'N/A')}")
                    
                    # Precio total
                    if "totalPrice" in product:
                        total_price = product['totalPrice'][0] if product['totalPrice'] else {}
                        print(f"   💰 Precio: {total_price.get('price', 'N/A')} {total_price.get('currency', 'N/A')}")
                    
                    # Tiempo de entrega
                    if "deliveryCapabilities" in product:
                        delivery = product['deliveryCapabilities']
                        print(f"   ⏰ Entrega: {delivery.get('deliveryTypeCode', 'N/A')}")
                        if "estimatedDeliveryDateAndTime" in delivery:
                            print(f"   📅 Fecha estimada: {delivery['estimatedDeliveryDateAndTime']}")
            
            print("\n" + "="*50)
            
        except Exception as e:
            print(f"\n❌ Error al procesar respuesta: {str(e)}")
            print("Respuesta completa:")
            print(json.dumps(rates_response, indent=2, ensure_ascii=False))


def main():
    """Función principal para testear el script"""
    
    print("🌟 Script de Tarifas DHL Express")
    print("=" * 40)
    
    # Crear cliente DHL usando configuración centralizada
    dhl_client = DHLRatesAPI(test_mode=True)
    
    # Obtener tarifas
    print("\n1️⃣ Obteniendo tarifas...")
    rates = dhl_client.get_rates()
    
    # Mostrar resumen
    print("\n2️⃣ Procesando respuesta...")
    dhl_client.print_rates_summary(rates)
    
    # Guardar respuesta completa
    output_file = "dhl_rates_response.json"
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(rates, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Respuesta completa guardada en: {output_file}")
    except Exception as e:
        print(f"\n❌ Error al guardar archivo: {str(e)}")
    
    print("\n✅ Proceso completado")
    
    return rates


if __name__ == "__main__":
    # Ejecutar el script principal
    result = main()
