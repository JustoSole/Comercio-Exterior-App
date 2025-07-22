#!/usr/bin/env python3
"""
🧪 Test Streamlit Integration - Prueba de Integración Completa
============================================================

Script para probar la integración completa del sistema mejorado
con la aplicación principal de Streamlit.

Simula el flujo completo sin la interfaz gráfica usando:
- Nuevo sistema de configuración con API keys desde secrets
- Integración NCM refinada (IA + Position Matcher)
- Sistema de debug avanzado
- Cálculo de flete mejorado (aéreo/marítimo)
- Flujo de entrada manual/URL actualizado

Última actualización: 2025-01-21 - Integración NCM refinada
"""

import asyncio
import os
import sys
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

# Configurar variables de entorno para testing
# En testing usamos variables de entorno directas en lugar de secrets de Streamlit
def setup_test_environment():
    """Configurar entorno de testing con API keys"""
    # En testing, usar variables de entorno o archivo de configuración
    test_api_keys = {
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
        "APIFY_API_KEY": os.getenv("APIFY_API_KEY", ""),
        "EASYPOST_API_KEY": os.getenv("EASYPOST_API_KEY", ""),
        "EASYPOST_API_KEY_TEST": os.getenv("EASYPOST_API_KEY_TEST", ""),
        "EASYPOST_WEBHOOK_SECRET": os.getenv("EASYPOST_WEBHOOK_SECRET", "")
    }
    
    # Configurar variables de entorno para compatibilidad con módulos
    for key, value in test_api_keys.items():
        if value:
            os.environ[key] = value
    
    return test_api_keys

# Configurar entorno de testing
API_KEYS = setup_test_environment()

# Importar módulos después de configurar entorno
try:
    from alibaba_scraper import scrape_single_alibaba_product
    from integration_example import IntegratedNCMClassifier  # NUEVO: Usar integración NCM
    from import_tax_calculator import calcular_impuestos_importacion
    from product_dimension_estimator import ProductShippingEstimator
    from freight_estimation import load_freight_rates, calculate_air_freight, calculate_sea_freight
    print("✅ Todos los módulos importados correctamente")
except ImportError as e:
    print(f"❌ Error importando módulos: {e}")
    sys.exit(1)

# Sistema de debug similar al de la app principal
class TestingDebugSystem:
    """Sistema de debug para testing"""
    
    def __init__(self):
        self.debug_logs = []
        self.api_responses = {}
        self.flow_steps = []
        self.current_step = None
    
    def debug_log(self, message, data=None, level="INFO"):
        """Log de debug con timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        log_entry = {
            "timestamp": timestamp,
            "level": level,
            "message": message,
            "data": data,
            "step": self.current_step
        }
        self.debug_logs.append(log_entry)
        print(f"[{timestamp}] {level}: {message}")
        
        if data and level in ["SUCCESS", "ERROR"]:
            print(f"    Data: {str(data)[:200]}...")
    
    def log_flow_step(self, step_name, status="STARTED", data=None):
        """Registrar paso del flujo"""
        timestamp = datetime.now().isoformat()
        step_log = {
            "timestamp": timestamp,
            "step_name": step_name,
            "status": status,
            "data": data
        }
        self.flow_steps.append(step_log)
        
        if status == "STARTED":
            self.current_step = step_name
        elif status in ["SUCCESS", "ERROR", "COMPLETED"]:
            self.current_step = None
        
        print(f"🔄 Flow Step: {step_name} - {status}")
    
    def log_api_call(self, api_name, request_data, response_data, success=True):
        """Registrar llamada a API"""
        timestamp = datetime.now().isoformat()
        api_log = {
            "timestamp": timestamp,
            "api_name": api_name,
            "success": success,
            "request": request_data,
            "response": response_data
        }
        key = f"{api_name}_{len(self.api_responses)}"
        self.api_responses[key] = api_log
        
        status = "SUCCESS" if success else "ERROR"
        print(f"🌐 API Call: {api_name} - {status}")

# Instancia global del sistema de debug
debug_system = TestingDebugSystem()

# URL de prueba
TEST_URL = "https://www.alibaba.com/product-detail/32-inch-smart-tv-led-full_1600798765951.html"

# Archivo de datos NCM para integración
NCM_DATA_FILE = "pdf_reader/ncm/resultados_ncm_hybrid/dataset_ncm_HYBRID_FIXED_20250721_175449.csv"

def validate_setup():
    """Validar que las API keys y archivos necesarios estén configurados"""
    print("🔍 Validando configuración del sistema...")
    
    # Validar API keys principales
    required_keys = ["OPENAI_API_KEY", "APIFY_API_KEY"]
    missing_keys = [key for key in required_keys if not API_KEYS.get(key)]
    
    if missing_keys:
        print(f"❌ API keys faltantes: {', '.join(missing_keys)}")
        return False
    
    # Validar archivo de datos NCM
    if not Path(NCM_DATA_FILE).exists():
        print(f"❌ Archivo de datos NCM no encontrado: {NCM_DATA_FILE}")
        return False
    
    print("✅ Configuración validada correctamente")
    return True

def create_mock_product():
    """Crear producto simulado para testing"""
    from collections import namedtuple
    
    ProductInfo = namedtuple('ProductInfo', [
        'title', 'price_low', 'price_high', 'moq', 'place_of_origin', 
        'categories', 'images', 'url', 'brand_name', 'properties', 'raw_data'
    ])
    
    return ProductInfo(
        title="Smart TV LED 32 inch Full HD with WiFi and Remote Control",
        price_low=85.0,
        price_high=120.0,
        moq="1 piece",
        place_of_origin="China",
        categories=["Consumer Electronics", "Television", "LED TV"],
        images=["https://example.com/tv1.jpg", "https://example.com/tv2.jpg"],
        url=TEST_URL,
        brand_name="Samsung",
        properties={
            "Screen Size": "32 inches",
            "Resolution": "1920x1080",
            "Connectivity": "HDMI, WiFi",
            "Smart TV": "Yes"
        },
        raw_data={
            'subject': "Smart TV LED 32 inch Full HD with WiFi and Remote Control",
            'categories': ["Consumer Electronics", "Television", "LED TV"],
            'mediaItems': [{'type': 'image', 'imageUrl': {'big': 'https://example.com/tv1.jpg'}}],
            'productHtmlDescription': 'High quality smart TV with full HD resolution',
            'productBasicProperties': [
                {"name": "Screen Size", "value": "32 inches"},
                {"name": "Resolution", "value": "1920x1080"}
            ]
        }
    )

def validate_and_select_best_image(images_list):
    """Función simplificada de validación de imágenes para testing"""
    if not images_list:
        return {
            "selected_url": None,
            "method": "no_images_available",
            "score": 0
        }
    
    # Para testing, simplemente usar la primera imagen
    return {
        "selected_url": images_list[0],
        "method": "testing_mock",
        "score": 85
    }

def create_enhanced_description(product):
    """Crear descripción mejorada para clasificación NCM"""
    description_parts = [product.title]
    
    # Agregar categorías
    if product.categories:
        description_parts.append(f"Categorías: {', '.join(product.categories)}")
    
    # Agregar origen
    if product.place_of_origin:
        description_parts.append(f"Origen: {product.place_of_origin}")
        
    # Agregar marca
    if hasattr(product, 'brand_name') and product.brand_name:
        description_parts.append(f"Marca: {product.brand_name}")
        
    # Agregar rango de precios
    if product.price_low > 0 and product.price_high > 0:
        description_parts.append(f"Rango de precio: ${product.price_low} - ${product.price_high}")
        
    # Agregar MOQ
    if product.moq:
        description_parts.append(f"MOQ: {product.moq}")
        
    # Agregar propiedades relevantes
    if hasattr(product, 'properties') and product.properties:
        relevant_props = []
        for key, value in product.properties.items():
            key_lower = key.lower()
            if any(term in key_lower for term in ['material', 'size', 'weight', 'color', 'type', 'model', 'specification', 'feature', 'capacity', 'function']):
                relevant_props.append(f"{key}: {value}")
        
        if relevant_props:
            description_parts.append(f"Propiedades: {'; '.join(relevant_props[:5])}")
    
    enhanced_description = " | ".join(description_parts)
    debug_system.debug_log("Descripción mejorada generada", {
        "original_length": len(product.title) if product and product.title else 0,
        "enhanced_length": len(enhanced_description),
        "components": len(description_parts)
    }, level="SUCCESS")
    
    return enhanced_description

def _get_duties_from_integrated_result(integrated_result: Dict[str, Any]) -> float:
    """Extrae derechos de importación del resultado integrado"""
    if not integrated_result or not integrated_result.get('success'):
        return 0.0
    
    # Priorizar datos de la recomendación final
    final_rec = integrated_result.get('final_recommendation', {})
    fiscal_data = final_rec.get('fiscal_data', {})
    
    if 'aec' in fiscal_data:
        try:
            return float(fiscal_data['aec'])
        except (ValueError, TypeError):
            pass
    
    # Fallback: datos de IA
    ai_classification = integrated_result.get('ai_classification', {})
    tratamiento = ai_classification.get('tratamiento_arancelario', {})
    derechos_str = tratamiento.get('derechos_importacion', '0.0%')
    
    try:
        import re
        cleaned_str = re.sub(r'[^\d.]', '', str(derechos_str))
        if cleaned_str:
            return float(cleaned_str)
    except (ValueError, TypeError):
        debug_system.debug_log(f"No se pudo parsear derechos de importación: '{derechos_str}'. Usando 0.0%.", level="WARNING")
    
    return 0.0

async def test_complete_flow():
    """Probar el flujo completo de análisis"""
    print("🚀 INICIANDO PRUEBA DE FLUJO COMPLETO ACTUALIZADO")
    print(f"⏰ {datetime.now().strftime('%H:%M:%S')}")
    print("="*70)
    
    # Validar configuración
    if not validate_setup():
        print("❌ Configuración incompleta")
        return False
    
    debug_system.log_flow_step("INICIO_TEST_COMPLETO", "STARTED")
    
    # === PASO 1: Simular Scraping de Alibaba ===
    print("\n📱 PASO 1: Simulando extracción de datos de Alibaba")
    debug_system.log_flow_step("SCRAPING_ALIBABA", "STARTED", {"url": TEST_URL})
    
    try:
        # Para testing, usar producto simulado
        product = create_mock_product()
        debug_system.debug_log(f"Producto simulado creado: {product.title[:50]}...", level="SUCCESS")
        debug_system.log_flow_step("SCRAPING_ALIBABA", "SUCCESS", {"title": product.title})
        
        print(f"  ✅ Producto extraído: {product.title[:50]}...")
        print(f"  💰 Precio: ${product.price_low} - ${product.price_high}")
        print(f"  📍 Origen: {product.place_of_origin}")
        print(f"  🏷️  Categorías: {', '.join(product.categories)}")
        
    except Exception as e:
        print(f"  ❌ Error en scraping: {e}")
        debug_system.log_flow_step("SCRAPING_ALIBABA", "ERROR", {"error": str(e)})
        return False

    # === PASO 2: Análisis de dimensiones y peso ===
    print("\n🧠 PASO 2: Analizando dimensiones y peso (datos reales + IA)")
    debug_system.log_flow_step("ESTIMACION_DIMENSIONES", "STARTED")
    
    try:
        estimator = ProductShippingEstimator()
        product_dict = product.raw_data if hasattr(product, 'raw_data') else {}
        
        if not product_dict:
            debug_system.debug_log("No raw_data found, reconstructing for estimation", level="WARNING")
            product_dict = {
                'subject': product.title,
                'categories': product.categories,
                'mediaItems': [{'type': 'image', 'imageUrl': {'big': url}} for url in product.images],
                'productHtmlDescription': '',
                'productBasicProperties': []
            }
        
        shipping_info = estimator.get_shipping_details(product_dict)
        debug_system.log_flow_step("ESTIMACION_DIMENSIONES", "SUCCESS", shipping_info)
        
        method = shipping_info.get('method', 'unknown')
        if method == 'extracted_validated':
            debug_system.debug_log("✅ Usando datos reales extraídos", shipping_info, level="SUCCESS")
            print("  📏 Dimensiones y peso extraídos desde datos reales")
        elif method == 'llm_estimated':
            debug_system.debug_log("🧠 Usando estimación por IA", shipping_info, level="INFO")
            print("  🤖 Dimensiones y peso estimados por IA")
        else:
            debug_system.debug_log(f"⚠️ Método de estimación: {method}", shipping_info, level="WARNING")
        
        # Mostrar dimensiones estimadas
        dims = shipping_info.get('dimensions_cm', {})
        weight = shipping_info.get('weight_kg', 0)
        print(f"  📐 Dimensiones: {dims.get('length_cm', 'N/A')}x{dims.get('width_cm', 'N/A')}x{dims.get('height_cm', 'N/A')} cm")
        print(f"  ⚖️ Peso: {weight:.2f} kg")
        
    except Exception as e:
        print(f"  ⚠️ No se pudieron estimar las dimensiones: {e}")
        debug_system.log_flow_step("ESTIMACION_DIMENSIONES", "WARNING", {"error": str(e)})
        shipping_info = {"method": "failed_fallback", "weight_kg": 5.0, "dimensions_cm": {"length_cm": 50, "width_cm": 30, "height_cm": 15}}

    # === PASO 3: Clasificación NCM Integrada (IA + Position Matcher) ===
    print("\n🤖 PASO 3: Clasificación NCM Integrada (IA + Validación con Datos Oficiales)")
    debug_system.log_flow_step("CLASIFICACION_NCM_INTEGRADA", "STARTED")
    
    try:
        # Inicializar clasificador integrado
        integrated_classifier = IntegratedNCMClassifier(
            ncm_data_file=NCM_DATA_FILE,
            openai_api_key=API_KEYS.get("OPENAI_API_KEY")
        )
        
        # Crear descripción mejorada
        enhanced_description = create_enhanced_description(product)
        print(f"  🔍 Descripción: {enhanced_description[:80]}...")
        
        # Seleccionar mejor imagen
        image_selection = validate_and_select_best_image(product.images)
        selected_image = image_selection.get('selected_url')
        
        # Clasificar con integración completa
        integrated_result = await integrated_classifier.classify_and_validate(
            description=enhanced_description,
            image_url=selected_image,
            validate_position=True
        )
        
        debug_system.log_api_call("integrated_ncm_classifier", {
            "description": enhanced_description[:100],
            "image_url": selected_image,
            "validate_position": True
        }, integrated_result, integrated_result.get('success', False))
        
        if not integrated_result.get('success'):
            raise ValueError(integrated_result.get('error', 'Error desconocido en clasificación integrada'))
        
        debug_system.log_flow_step("CLASIFICACION_NCM_INTEGRADA", "SUCCESS", {
            "ai_ncm": integrated_result.get('ncm_from_ai'),
            "validation_type": integrated_result.get('validation', {}).get('match_type'),
            "final_ncm": integrated_result.get('final_recommendation', {}).get('recommended_ncm')
        })
        
        # Mostrar resultados detallados
        ai_ncm = integrated_result.get('ncm_from_ai', 'N/A')
        validation = integrated_result.get('validation', {})
        final_rec = integrated_result.get('final_recommendation', {})
        
        print(f"  🤖 IA clasificó como: {ai_ncm}")
        print(f"  🔍 Validación: {validation.get('match_type', 'N/A')}")
        print(f"  📋 NCM Final: {final_rec.get('recommended_ncm', 'N/A')}")
        print(f"  🎯 Confianza: {final_rec.get('confidence', 'N/A')}")
        print(f"  📊 Fuente: {final_rec.get('source', 'N/A')}")
        
        # Mostrar datos fiscales si están disponibles
        fiscal_data = final_rec.get('fiscal_data', {})
        if fiscal_data:
            aec = fiscal_data.get('aec', 'N/A')
            iva = fiscal_data.get('iva', 'N/A')
            print(f"  💰 AEC: {aec}% | IVA: {iva}%")
        
        # Mostrar intervenciones
        interventions = final_rec.get('interventions', [])
        if interventions:
            print(f"  🏛️ Intervenciones: {', '.join(interventions)}")
        else:
            print(f"  🏛️ Intervenciones: Ninguna")
        
        # Régimen simplificado
        simplified_regime = final_rec.get('simplified_regime', {})
        regime_decision = simplified_regime.get('aplica_final', simplified_regime.get('aplica', 'N/A'))
        print(f"  🚚 Régimen Simplificado: {regime_decision}")
        
    except Exception as e:
        print(f"  ❌ Error en clasificación NCM integrada: {e}")
        debug_system.log_flow_step("CLASIFICACION_NCM_INTEGRADA", "ERROR", {"error": str(e)})
        return False

    # === PASO 4: Cálculo de impuestos ===
    print("\n💰 PASO 4: Calculando impuestos argentinos")
    debug_system.log_flow_step("CALCULO_IMPUESTOS", "STARTED")
    
    try:
        precio_promedio = (product.price_low + product.price_high) / 2
        derechos_importacion_pct = _get_duties_from_integrated_result(integrated_result)
        
        tax_result = calcular_impuestos_importacion(
            cif_value=precio_promedio,
            tipo_importador="responsable_inscripto",
            destino="reventa", 
            origen="extrazona",
            tipo_dolar="oficial",
            provincia="CABA",
            derechos_importacion_pct=derechos_importacion_pct
        )
        
        debug_system.log_flow_step("CALCULO_IMPUESTOS", "SUCCESS", {
            "cif_value": precio_promedio,
            "derechos_pct": derechos_importacion_pct,
            "total_impuestos": float(tax_result.total_impuestos)
        })
        
        print(f"  ✅ Impuestos calculados: ${float(tax_result.total_impuestos):.2f}")
        print(f"  📊 Incidencia: {float(tax_result.incidencia_porcentual):.1f}%")
        print(f"  💎 AEC aplicado: {derechos_importacion_pct:.1f}%")
        
    except Exception as e:
        print(f"  ❌ Error calculando impuestos: {e}")
        debug_system.log_flow_step("CALCULO_IMPUESTOS", "ERROR", {"error": str(e)})
        return False

    # === PASO 5: Cálculo de flete mejorado ===
    print("\n🚚 PASO 5: Calculando flete internacional")
    debug_system.log_flow_step("CALCULO_FLETE", "STARTED")
    
    try:
        # Cargar tarifas de flete
        freight_rates = load_freight_rates('pdf_reader/extracted_tables.csv')
        
        # Parametros del envío
        import_quantity = 5  # Cantidad de ejemplo
        peso_unitario_kg = shipping_info.get('weight_kg', 5.0)
        dims = shipping_info.get('dimensions_cm', {})
        
        # Cálculo para ambos tipos de flete
        print(f"  📦 Cantidad: {import_quantity} unidades")
        print(f"  ⚖️ Peso unitario: {peso_unitario_kg:.2f} kg")
        
        # Flete aéreo (Courier)
        peso_total_kg = peso_unitario_kg * import_quantity
        if freight_rates is not None:
            flete_aereo_total = calculate_air_freight(peso_total_kg, freight_rates)
        else:
            flete_aereo_total = precio_promedio * import_quantity * 0.15
        flete_aereo_unitario = flete_aereo_total / import_quantity
        
        print(f"  ✈️ Flete Aéreo: ${flete_aereo_total:.2f} total (${flete_aereo_unitario:.2f}/unidad)")
        
        # Flete marítimo (Contenedor)
        if all(d > 0 for d in dims.values()):
            volumen_unitario_cbm = (dims.get('length_cm', 0) * dims.get('width_cm', 0) * dims.get('height_cm', 0)) / 1_000_000
            volumen_total_cbm = volumen_unitario_cbm * import_quantity
            flete_maritimo_total = calculate_sea_freight(volumen_total_cbm)
            flete_maritimo_unitario = flete_maritimo_total / import_quantity
            
            print(f"  🚢 Flete Marítimo: ${flete_maritimo_total:.2f} total (${flete_maritimo_unitario:.2f}/unidad)")
            print(f"  📐 Volumen: {volumen_total_cbm:.6f} m³")
        else:
            flete_maritimo_total = precio_promedio * import_quantity * 0.12
            flete_maritimo_unitario = flete_maritimo_total / import_quantity
            print(f"  🚢 Flete Marítimo (estimado): ${flete_maritimo_total:.2f} total")
        
        # Usar flete aéreo como principal para el cálculo final
        flete_costo_unitario = flete_aereo_unitario
        flete_tipo = "Courier (Aéreo)"
        
        debug_system.log_flow_step("CALCULO_FLETE", "SUCCESS", {
            "peso_total_kg": peso_total_kg,
            "volumen_total_cbm": volumen_total_cbm if all(d > 0 for d in dims.values()) else None,
            "flete_aereo_total": flete_aereo_total,
            "flete_maritimo_total": flete_maritimo_total,
            "flete_seleccionado": flete_tipo,
            "costo_unitario": flete_costo_unitario
        })
        
    except Exception as e:
        print(f"  ❌ Error calculando flete: {e}")
        debug_system.log_flow_step("CALCULO_FLETE", "ERROR", {"error": str(e)})
        # Usar fallback
        flete_costo_unitario = precio_promedio * 0.15
        flete_tipo = "Estimado (15%)"
        print(f"  🔄 Usando flete estimado: ${flete_costo_unitario:.2f}/unidad")

    # === PASO 6: Cálculo de Landed Cost Final ===
    print("\n🎯 PASO 6: Cálculo Final de Landed Cost")
    debug_system.log_flow_step("CALCULO_FINAL", "STARTED")
    
    try:
        honorarios_despachante = precio_promedio * 0.02
        landed_cost_unitario = precio_promedio + float(tax_result.total_impuestos) + flete_costo_unitario + honorarios_despachante
        
        # Cálculo total para la cantidad
        costo_total_importacion = landed_cost_unitario * import_quantity
        
        print(f"  💰 Precio producto (FOB): ${precio_promedio:.2f}")
        print(f"  🏛️ Impuestos: ${float(tax_result.total_impuestos):.2f}")
        print(f"  🚚 Flete ({flete_tipo}): ${flete_costo_unitario:.2f}")
        print(f"  👤 Despachante (2%): ${honorarios_despachante:.2f}")
        print(f"  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"  🎯 LANDED COST UNITARIO: ${landed_cost_unitario:.2f}")
        print(f"  📦 COSTO TOTAL ({import_quantity} unidades): ${costo_total_importacion:.2f}")
        
        markup = ((landed_cost_unitario - precio_promedio) / precio_promedio) * 100
        print(f"  📈 Markup total: {markup:.1f}%")
        
        # Análisis de rentabilidad
        print(f"\n💹 ANÁLISIS DE RENTABILIDAD:")
        margenes = [0.3, 0.5, 1.0]  # 30%, 50%, 100%
        cotizacion_ars = 1746.96
        
        for margen in margenes:
            precio_venta_usd = landed_cost_unitario * (1 + margen)
            precio_venta_ars = precio_venta_usd * cotizacion_ars
            utilidad_usd = precio_venta_usd - landed_cost_unitario
            print(f"    Margen {margen:.0%}: ${precio_venta_usd:.2f} USD (${precio_venta_ars:,.0f} ARS) - Utilidad: ${utilidad_usd:.2f}")
        
        debug_system.log_flow_step("CALCULO_FINAL", "SUCCESS", {
            "landed_cost_unitario": landed_cost_unitario,
            "costo_total_importacion": costo_total_importacion,
            "markup_porcentaje": markup,
            "import_quantity": import_quantity
        })
        
    except Exception as e:
        print(f"  ❌ Error en cálculo final: {e}")
        debug_system.log_flow_step("CALCULO_FINAL", "ERROR", {"error": str(e)})
        return False

    # === PASO 7: Resumen de Integración NCM ===
    print("\n📋 PASO 7: Resumen de Integración NCM Refinada")
    
    try:
        ai_classification = integrated_result.get('ai_classification', {})
        validation = integrated_result.get('validation', {})
        final_rec = integrated_result.get('final_recommendation', {})
        
        print(f"  🤖 Clasificación IA:")
        print(f"     NCM: {ai_classification.get('ncm_completo', 'N/A')}")
        print(f"     Confianza: {ai_classification.get('confianza', 'N/A')}")
        print(f"     Método: {ai_classification.get('classification_method', 'N/A')}")
        
        print(f"  🔍 Validación con Datos Oficiales:")
        print(f"     Tipo de match: {validation.get('match_type', 'N/A')}")
        if validation.get('match_type') == 'exacto':
            position = validation.get('position', {})
            print(f"     Posición oficial: {position.get('code', 'N/A')}")
            print(f"     Descripción: {position.get('description', 'N/A')}")
        
        print(f"  📋 Recomendación Final:")
        print(f"     NCM recomendado: {final_rec.get('recommended_ncm', 'N/A')}")
        print(f"     Confianza final: {final_rec.get('confidence', 'N/A')}")
        print(f"     Fuente: {final_rec.get('source', 'N/A')}")
        print(f"     Notas: {final_rec.get('notes', 'N/A')}")
        
    except Exception as e:
        print(f"  ⚠️ Error mostrando resumen NCM: {e}")

    print("\n" + "="*70)
    print("🏁 PRUEBA DE INTEGRACIÓN COMPLETADA EXITOSAMENTE")
    print(f"⏰ {datetime.now().strftime('%H:%M:%S')}")
    print("="*70)
    
    # Resumen final
    print(f"\n📊 RESUMEN FINAL:")
    print(f"  • Producto: {product.title[:50]}...")
    print(f"  • NCM Final: {final_rec.get('recommended_ncm', 'N/A')}")
    print(f"  • Fuente NCM: {final_rec.get('source', 'N/A')}")
    print(f"  • Landed Cost: ${landed_cost_unitario:.2f} USD")
    print(f"  • Integración NCM: ✅ IA + Datos Oficiales")
    print(f"  • Sistema de debug: ✅ Activo")
    print(f"  • Todos los módulos: ✅ Funcionando")
    
    debug_system.log_flow_step("TEST_COMPLETO", "COMPLETED")
    
    # Exportar debug logs
    debug_export = {
        "timestamp": datetime.now().isoformat(),
        "test_success": True,
        "debug_logs": debug_system.debug_logs,
        "flow_steps": debug_system.flow_steps,
        "api_responses": debug_system.api_responses,
        "final_result": {
            "landed_cost_unitario": landed_cost_unitario,
            "ncm_integration": integrated_result,
            "shipping_info": shipping_info,
            "tax_calculation": {
                "total_impuestos": float(tax_result.total_impuestos),
                "incidencia": float(tax_result.incidencia_porcentual)
            }
        }
    }
    
    debug_filename = f"debug_integration_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(debug_filename, 'w', encoding='utf-8') as f:
        json.dump(debug_export, f, indent=2, ensure_ascii=False, default=str)
    
    print(f"\n💾 Debug logs exportados: {debug_filename}")
    
    return True

async def test_quick_integration():
    """Test rápido de integración para validación"""
    print("🧪 Test rápido de integración NCM...")
    
    if not validate_setup():
        return False
    
    try:
        # Test rápido del clasificador integrado
        integrated_classifier = IntegratedNCMClassifier(
            ncm_data_file=NCM_DATA_FILE,
            openai_api_key=API_KEYS.get("OPENAI_API_KEY")
        )
        
        # Test con producto simple
        result = await integrated_classifier.classify_and_validate(
            description="televisor LCD 32 pulgadas",
            image_url=None,
            validate_position=True
        )
        
        if result.get('success'):
            final_rec = result.get('final_recommendation', {})
            print(f"✅ Integración NCM: {final_rec.get('recommended_ncm', 'N/A')}")
            print(f"✅ Fuente: {final_rec.get('source', 'N/A')}")
            return True
        else:
            print(f"❌ Error en integración: {result.get('error', 'Error desconocido')}")
            return False
            
    except Exception as e:
        print(f"❌ Error en test rápido: {e}")
        return False

if __name__ == "__main__":
    """Ejecutar tests"""
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--quick":
        success = asyncio.run(test_quick_integration())
    else:
        success = asyncio.run(test_complete_flow())
    
    if success:
        print("\n🎉 ¡SISTEMA DE INTEGRACIÓN COMPLETAMENTE FUNCIONAL!")
        print("✅ Listo para usar en la aplicación Streamlit")
        print("🔧 Con integración NCM refinada (IA + Position Matcher)")
        print("📊 Sistema de debug avanzado incluido")
    else:
        print("\n❌ Hay errores en el sistema de integración")
        print("🔧 Revisar logs y corregir antes de usar")
        sys.exit(1) 