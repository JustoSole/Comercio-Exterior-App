import os
import easypost
from easypost import EasyPostClient
from typing import List, Dict, Any, Optional
import json
from datetime import datetime

# Configuración de EasyPost
EASYPOST_API_KEY = "EZTK24b410af6b1140c4aec276146fde37ebrat43Q0KkGyLSkOBuLaOzA"

# Carrier Account IDs
CA_FEDEX = "ca_e1b44d1678404f72a2589328b58fec26"  # FedEx International Connect
CA_DHL = "ca_48996cf6b2ed4352841c252db513f415"    # DHL Express

class EasyPostService:
    """Servicio para integración con EasyPost API"""
    
    def __init__(self):
        """Inicializar cliente EasyPost"""
        os.environ["EASYPOST_API_KEY"] = EASYPOST_API_KEY
        self.client = EasyPostClient(EASYPOST_API_KEY)
    
    def get_shipping_rates_china_argentina(
        self, 
        weight_kg: float, 
        dimensions_cm: Dict[str, float] = None,
        product_description: str = "General merchandise",
        product_value: float = 10.0,
        quantity: int = 1,
        hs_code: str = "999999"
    ) -> Dict[str, Any]:
        """
        Obtener tarifas de envío desde China a Argentina
        
        Args:
            weight_kg: Peso en kilogramos
            dimensions_cm: Diccionario con length, width, height en cm
            product_description: Descripción del producto
            product_value: Valor unitario del producto en USD
            quantity: Cantidad de items
            hs_code: Código arancelario HS
        
        Returns:
            Diccionario con las tarifas y información del envío
        """
        try:
            # Configurar dimensiones por defecto si no se proporcionan
            if dimensions_cm is None:
                # Estimar dimensiones basadas en peso (caja estándar)
                if weight_kg <= 1:
                    dimensions_cm = {"length": 20, "width": 15, "height": 10}
                elif weight_kg <= 5:
                    dimensions_cm = {"length": 30, "width": 25, "height": 15}
                elif weight_kg <= 10:
                    dimensions_cm = {"length": 40, "width": 30, "height": 20}
                else:
                    dimensions_cm = {"length": 60, "width": 40, "height": 40}
            
            # Direcciones
            from_address = {
                "company": "Supplier China",
                "street1": "Huaqiang North Road 123",
                "city": "Shenzhen",
                "state": "GD",
                "zip": "518000",
                "country": "CN",
                "phone": "+86 755 1234 5678",
                "email": "supplier@example.com",
            }
            
            to_address = {
                "name": "Justo Soleno",
                "street1": "Av. Corrientes 1234",
                "city": "Ciudad Autónoma de Buenos Aires",
                "state": "CABA",
                "zip": "1001",
                "country": "AR",
                "phone": "+54 11 4444 5555",
                "email": "justo@example.com",
            }
            
            # Paquete (convertir peso a gramos)
            parcel = {
                "weight": int(weight_kg * 1000),  # convertir kg a gramos
                "length": dimensions_cm["length"],
                "width": dimensions_cm["width"],
                "height": dimensions_cm["height"],
            }
            
            # Información de aduana
            customs_items = [{
                "description": product_description,
                "quantity": quantity,
                "value": product_value,
                "weight": int((weight_kg * 1000) / quantity),  # peso por unidad en gramos
                "hs_tariff_number": hs_code,
                "origin_country": "CN",
            }]
            
            customs_info = {
                "customs_certify": True,
                "customs_signer": "Supplier Representative",
                "contents_type": "merchandise",
                "eel_pfc": "NOEEI_30_37_a",
                "non_delivery_option": "return",
                "restriction_type": "none",
                "customs_items": customs_items,
            }
            
            # Crear shipment con filtro de carriers específicos
            shipment = self.client.shipment.create(
                to_address=to_address,
                from_address=from_address,
                parcel=parcel,
                customs_info=customs_info,
                carrier_accounts=[CA_FEDEX, CA_DHL],
                options={
                    "currency": "USD",
                    "label_format": "PDF",
                }
            )
            
            # Procesar rates
            rates = shipment.rates or []
            
            result = {
                "shipment_id": shipment.id,
                "weight_kg": weight_kg,
                "dimensions_cm": dimensions_cm,
                "rates": [],
                "cheapest_rate": None,
                "fedex_rates": [],
                "dhl_rates": [],
                "timestamp": datetime.now().isoformat()
            }
            
            # Procesar todas las tarifas
            for rate in rates:
                rate_info = {
                    "carrier": rate.carrier,
                    "service": rate.service,
                    "rate": float(rate.rate),
                    "currency": rate.currency,
                    "delivery_days": getattr(rate, 'delivery_days', None),
                    "delivery_date": getattr(rate, 'delivery_date', None),
                    "rate_id": rate.id
                }
                result["rates"].append(rate_info)
                
                # Separar por carrier
                if rate.carrier.lower().startswith("fedex"):
                    result["fedex_rates"].append(rate_info)
                elif rate.carrier.lower().startswith("dhl"):
                    result["dhl_rates"].append(rate_info)
            
            # Encontrar la tarifa más barata
            if rates:
                cheapest = min(rates, key=lambda r: float(r.rate))
                result["cheapest_rate"] = {
                    "carrier": cheapest.carrier,
                    "service": cheapest.service,
                    "rate": float(cheapest.rate),
                    "currency": cheapest.currency,
                    "rate_id": cheapest.id
                }
            
            return result
            
        except Exception as e:
            return {
                "error": str(e),
                "weight_kg": weight_kg,
                "timestamp": datetime.now().isoformat()
            }
    
    def test_multiple_weights(self, weights_kg: List[float]) -> List[Dict[str, Any]]:
        """
        Testear múltiples pesos y comparar tarifas
        
        Args:
            weights_kg: Lista de pesos en kilogramos para testear
        
        Returns:
            Lista de resultados para cada peso
        """
        results = []
        
        for weight in weights_kg:
            print(f"\n🔍 Testeando peso: {weight} kg")
            result = self.get_shipping_rates_china_argentina(weight)
            results.append(result)
            
            if "error" in result:
                print(f"❌ Error para {weight} kg: {result['error']}")
            else:
                print(f"✅ Obtenidas {len(result['rates'])} tarifas para {weight} kg")
                if result["cheapest_rate"]:
                    cheapest = result["cheapest_rate"]
                    print(f"💰 Más barata: {cheapest['carrier']} - {cheapest['service']} - ${cheapest['rate']} {cheapest['currency']}")
        
        return results
    
    def format_rate_comparison(self, results: List[Dict[str, Any]]) -> str:
        """
        Formatear resultados para comparación visual
        
        Args:
            results: Lista de resultados de diferentes pesos
        
        Returns:
            String formateado con la comparación
        """
        output = []
        output.append("=" * 80)
        output.append("COMPARACIÓN DE TARIFAS CHINA → ARGENTINA")
        output.append("=" * 80)
        
        for result in results:
            if "error" in result:
                output.append(f"\n❌ PESO: {result['weight_kg']} kg - ERROR: {result['error']}")
                continue
            
            weight = result["weight_kg"]
            output.append(f"\n📦 PESO: {weight} kg")
            output.append("-" * 50)
            
            if not result["rates"]:
                output.append("⚠️  No se encontraron tarifas disponibles")
                continue
            
            # Mostrar todas las tarifas
            for rate in result["rates"]:
                days = f" ({rate['delivery_days']} días)" if rate['delivery_days'] else ""
                output.append(f"{rate['carrier']:15} | {rate['service']:35} | ${rate['rate']:>8.2f} {rate['currency']}{days}")
            
            # Mostrar la más barata
            if result["cheapest_rate"]:
                cheapest = result["cheapest_rate"]
                output.append(f"\n🏆 MÁS BARATA: {cheapest['carrier']} - {cheapest['service']} - ${cheapest['rate']:.2f} {cheapest['currency']}")
            
            # Estadísticas por carrier
            fedex_count = len(result["fedex_rates"])
            dhl_count = len(result["dhl_rates"])
            output.append(f"📊 FedEx: {fedex_count} opciones | DHL: {dhl_count} opciones")
        
        return "\n".join(output)
    
    def get_carrier_accounts_info(self) -> Dict[str, Any]:
        """
        Obtener información de las cuentas de carriers configuradas
        
        Returns:
            Información de las cuentas de carriers
        """
        try:
            # Obtener información de carrier accounts
            carrier_accounts = self.client.carrier_account.all()
            
            info = {
                "total_accounts": len(carrier_accounts),
                "accounts": [],
                "configured_carriers": []
            }
            
            for account in carrier_accounts:
                account_info = {
                    "id": account.id,
                    "type": account.type,
                    "description": getattr(account, 'description', 'N/A'),
                    "readable": getattr(account, 'readable', 'N/A')
                }
                info["accounts"].append(account_info)
                info["configured_carriers"].append(account.type)
            
            return info
            
        except Exception as e:
            return {"error": str(e)}


def generate_summary_report(results: List[Dict[str, Any]]) -> str:
    """
    Genera un reporte resumen de las pruebas realizadas
    
    Args:
        results: Lista de resultados de las pruebas
    
    Returns:
        Reporte formateado como string
    """
    report = []
    report.append("=" * 80)
    report.append("🎯 RESUMEN EJECUTIVO - TARIFAS CHINA → ARGENTINA")
    report.append("=" * 80)
    
    # Análisis general
    valid_results = [r for r in results if "error" not in r and r["rates"]]
    if not valid_results:
        report.append("❌ No se obtuvieron tarifas válidas")
        return "\n".join(report)
    
    # Estadísticas por carrier
    total_dhl_rates = sum(len(r["dhl_rates"]) for r in valid_results)
    total_fedex_rates = sum(len(r["fedex_rates"]) for r in valid_results)
    
    report.append(f"📊 ESTADÍSTICAS GENERALES:")
    report.append(f"   • Pesos testeados exitosamente: {len(valid_results)}")
    report.append(f"   • Total tarifas DHL obtenidas: {total_dhl_rates}")
    report.append(f"   • Total tarifas FedEx obtenidas: {total_fedex_rates}")
    
    if total_fedex_rates == 0:
        report.append("   ⚠️  ADVERTENCIA: No se obtuvieron tarifas de FedEx")
        report.append("      Posibles causas:")
        report.append("      - Account ID incorrecto")
        report.append("      - Restricciones de servicio China-Argentina")
        report.append("      - Configuración de cuenta pendiente")
    
    # Análisis de costos
    report.append(f"\n💰 ANÁLISIS DE COSTOS (USD):")
    
    cost_analysis = []
    for result in valid_results:
        if result["cheapest_rate"]:
            weight = result["weight_kg"]
            rate = result["cheapest_rate"]["rate"]
            cost_per_kg = rate / weight
            carrier = result["cheapest_rate"]["carrier"]
            service = result["cheapest_rate"]["service"]
            
            cost_analysis.append({
                "weight": weight,
                "total_cost": rate,
                "cost_per_kg": cost_per_kg,
                "carrier": carrier,
                "service": service
            })
    
    # Ordenar por peso
    cost_analysis.sort(key=lambda x: x["weight"])
    
    for analysis in cost_analysis:
        report.append(f"   • {analysis['weight']:2d} kg: ${analysis['total_cost']:8.2f} (${analysis['cost_per_kg']:6.2f}/kg) - {analysis['carrier']}")
    
    # Encontrar el rango más económico
    if cost_analysis:
        min_cost_per_kg = min(cost_analysis, key=lambda x: x["cost_per_kg"])
        max_cost_per_kg = max(cost_analysis, key=lambda x: x["cost_per_kg"])
        
        report.append(f"\n🏆 MEJOR TARIFA POR KG: {min_cost_per_kg['weight']} kg - ${min_cost_per_kg['cost_per_kg']:.2f}/kg")
        report.append(f"📈 PEOR TARIFA POR KG: {max_cost_per_kg['weight']} kg - ${max_cost_per_kg['cost_per_kg']:.2f}/kg")
    
    # Recomendaciones
    report.append(f"\n💡 RECOMENDACIONES:")
    
    if total_fedex_rates == 0:
        report.append("   1. Verificar configuración de cuenta FedEx en EasyPost")
        report.append("   2. Contactar soporte de EasyPost para activar servicios China-Argentina")
        report.append("   3. Considerar solo DHL para envíos desde China")
    
    if cost_analysis:
        # Identificar patrones en costos
        costs_per_kg = [a["cost_per_kg"] for a in cost_analysis]
        if len(costs_per_kg) > 1:
            variation = (max(costs_per_kg) - min(costs_per_kg)) / min(costs_per_kg) * 100
            report.append(f"   4. Variación de costo por kg: {variation:.1f}% - considerar optimizar pesos de envío")
    
    # Próximos pasos
    report.append(f"\n🚀 PRÓXIMOS PASOS:")
    report.append("   • Configurar cuenta FedEx correctamente")
    report.append("   • Testear con clave de producción para obtener más opciones")
    report.append("   • Evaluar otros carriers disponibles en EasyPost")
    report.append("   • Implementar cache de tarifas para optimizar consultas")
    
    return "\n".join(report)


def test_all_available_carriers(service: EasyPostService, weight_kg: float = 5) -> Dict[str, Any]:
    """
    Testear todos los carriers disponibles sin filtrar por account IDs específicos
    
    Args:
        service: Instancia del servicio EasyPost
        weight_kg: Peso a testear
    
    Returns:
        Resultados con todos los carriers disponibles
    """
    try:
        # Direcciones
        from_address = {
            "company": "Supplier China",
            "street1": "Huaqiang North Road 123",
            "city": "Shenzhen",
            "state": "GD",
            "zip": "518000",
            "country": "CN",
            "phone": "+86 755 1234 5678",
            "email": "supplier@example.com",
        }
        
        to_address = {
            "name": "Justo Soleno",
            "street1": "Av. Corrientes 1234",
            "city": "Ciudad Autónoma de Buenos Aires",
            "state": "CABA",
            "zip": "1001",
            "country": "AR",
            "phone": "+54 11 4444 5555",
            "email": "justo@example.com",
        }
        
        # Paquete
        parcel = {
            "weight": int(weight_kg * 1000),
            "length": 30,
            "width": 25,
            "height": 15,
        }
        
        # Información de aduana
        customs_items = [{
            "description": "General merchandise",
            "quantity": 1,
            "value": 50.0,
            "weight": int(weight_kg * 1000),
            "hs_tariff_number": "999999",
            "origin_country": "CN",
        }]
        
        customs_info = {
            "customs_certify": True,
            "customs_signer": "Supplier Representative",
            "contents_type": "merchandise",
            "eel_pfc": "NOEEI_30_37_a",
            "non_delivery_option": "return",
            "restriction_type": "none",
            "customs_items": customs_items,
        }
        
        # Crear shipment SIN filtrar carriers
        print(f"🔍 Testeando TODOS los carriers disponibles para {weight_kg} kg...")
        shipment = service.client.shipment.create(
            to_address=to_address,
            from_address=from_address,
            parcel=parcel,
            customs_info=customs_info,
            # NO especificamos carrier_accounts para obtener TODOS los disponibles
            options={
                "currency": "USD",
                "label_format": "PDF",
            }
        )
        
        rates = shipment.rates or []
        
        # Agrupar por carrier
        carriers_found = {}
        for rate in rates:
            carrier = rate.carrier
            if carrier not in carriers_found:
                carriers_found[carrier] = []
            carriers_found[carrier].append({
                "service": rate.service,
                "rate": float(rate.rate),
                "currency": rate.currency,
                "delivery_days": getattr(rate, 'delivery_days', None),
                "rate_id": rate.id
            })
        
        result = {
            "shipment_id": shipment.id,
            "weight_kg": weight_kg,
            "total_rates": len(rates),
            "carriers_found": list(carriers_found.keys()),
            "carriers_details": carriers_found,
            "cheapest_overall": None,
            "timestamp": datetime.now().isoformat()
        }
        
        # Encontrar la más barata general
        if rates:
            cheapest = min(rates, key=lambda r: float(r.rate))
            result["cheapest_overall"] = {
                "carrier": cheapest.carrier,
                "service": cheapest.service,
                "rate": float(cheapest.rate),
                "currency": cheapest.currency,
                "rate_id": cheapest.id
            }
        
        return result
        
    except Exception as e:
        return {
            "error": str(e),
            "weight_kg": weight_kg,
            "timestamp": datetime.now().isoformat()
        }


def quick_rate_check(weight_kg: float, description: str = "General merchandise", value: float = 50.0) -> Dict[str, Any]:
    """
    Función rápida para obtener tarifas sin configuraciones complejas
    
    Args:
        weight_kg: Peso en kg
        description: Descripción del producto
        value: Valor del producto en USD
    
    Returns:
        Diccionario con las tarifas más básicas
    """
    service = EasyPostService()
    return service.get_shipping_rates_china_argentina(
        weight_kg=weight_kg,
        product_description=description,
        product_value=value
    )


def test_easypost_service():
    """Función de prueba principal"""
    print("🚀 Iniciando pruebas de EasyPost Service")
    print("=" * 60)
    
    # Inicializar servicio
    service = EasyPostService()
    
    # 1. Verificar cuentas de carriers
    print("\n1. 📋 Verificando cuentas de carriers...")
    accounts_info = service.get_carrier_accounts_info()
    if "error" in accounts_info:
        print(f"❌ Error obteniendo cuentas: {accounts_info['error']}")
        print("   💡 Nota: Con API key de prueba, algunas funciones están limitadas")
    else:
        print(f"✅ Total de cuentas configuradas: {accounts_info['total_accounts']}")
        print(f"🚛 Carriers disponibles: {', '.join(set(accounts_info['configured_carriers']))}")
    
    # 2. Testear diferentes pesos
    print("\n2. 📦 Testeando diferentes pesos...")
    test_weights = [1, 5, 10, 25, 50]  # kg
    results = service.test_multiple_weights(test_weights)
    
    # 3. Mostrar comparación formateada
    print("\n3. 📊 Comparación de resultados:")
    comparison = service.format_rate_comparison(results)
    print(comparison)
    
    # 4. Generar reporte resumen
    print("\n4. 📋 Generando reporte resumen...")
    summary = generate_summary_report(results)
    print(summary)
    
    # 5. Testear todos los carriers disponibles (sin filtros)
    print("\n5. 🌐 Testeando TODOS los carriers disponibles...")
    all_carriers_result = test_all_available_carriers(service, weight_kg=5)
    
    if "error" in all_carriers_result:
        print(f"❌ Error testeando todos los carriers: {all_carriers_result['error']}")
    else:
        print(f"✅ Encontrados {all_carriers_result['total_rates']} tarifas de {len(all_carriers_result['carriers_found'])} carriers")
        print(f"🚛 Carriers encontrados: {', '.join(all_carriers_result['carriers_found'])}")
        
        if all_carriers_result["cheapest_overall"]:
            cheapest = all_carriers_result["cheapest_overall"]
            print(f"💰 Más barata (todos los carriers): {cheapest['carrier']} - {cheapest['service']} - ${cheapest['rate']:.2f} {cheapest['currency']}")
        
        # Mostrar detalles por carrier
        print("\n📋 Detalles por carrier:")
        for carrier, services in all_carriers_result["carriers_details"].items():
            print(f"   {carrier}: {len(services)} servicios")
            for service in services[:2]:  # Mostrar solo los primeros 2 servicios
                days = f" ({service['delivery_days']} días)" if service['delivery_days'] else ""
                print(f"      - {service['service']}: ${service['rate']:.2f}{days}")
    
    # 6. Guardar resultados en archivo JSON
    output_file = f"easypost_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "accounts_info": accounts_info,
            "test_results": results,
            "test_weights": test_weights,
            "summary_report": summary,
            "all_carriers_test": all_carriers_result,
            "timestamp": datetime.now().isoformat()
        }, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Resultados guardados en: {output_file}")
    return results


if __name__ == "__main__":
    # Ejecutar pruebas
    test_easypost_service()
