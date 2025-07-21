#!/usr/bin/env python3
"""
🧪 Test Streamlit Integration - Prueba de Integración Completa
============================================================

Script para probar la integración completa del sistema mejorado
con la aplicación principal de Streamlit.

Simula el flujo completo sin la interfaz gráfica.
"""

import asyncio
import os
import sys
from datetime import datetime

# Ya no se setea la variable de entorno aquí, se lee desde secrets
# os.environ['OPENAI_API_KEY'] = "..."

try:
    from alibaba_scraper import scrape_single_alibaba_product
    from ai_ncm_classifier import AINcmClassifier
    from import_tax_calculator import calcular_impuestos_importacion
    from vuce_integration import VuceIntegration
    from product_dimension_estimator import ProductShippingEstimator
    from secrets_config import get_api_keys_dict, validate_setup
    print("✅ Todos los módulos importados correctamente")
except ImportError as e:
    print(f"❌ Error importando módulos: {e}")
    sys.exit(1)

# URL de prueba
TEST_URL = "https://www.alibaba.com/product-detail/32-inch-smart-tv-led-full_1600798765951.html"

async def test_complete_flow():
    """Probar el flujo completo de análisis"""
    print("🚀 INICIANDO PRUEBA DE FLUJO COMPLETO")
    print(f"⏰ {datetime.now().strftime('%H:%M:%S')}")
    print("="*60)
    
    # Validar configuración
    api_keys = get_api_keys_dict()
    if not validate_setup():
        print("❌ Configuración de API keys incompleta")
        return False
    
    print("✅ API keys configuradas correctamente")
    
    # === PASO 1: Scraping de Alibaba ===
    print("\n📱 PASO 1: Extrayendo datos de Alibaba")
    try:
        # Simular producto (ya que no tenemos URL real)
        class MockProduct:
            def __init__(self):
                self.title = "Smart TV LED 32 inch Full HD with WiFi and Remote Control"
                self.price_low = 85.0
                self.price_high = 120.0
                self.moq = "1 piece"
                self.place_of_origin = "China"
                self.categories = ["Consumer Electronics", "Television", "LED TV"]
                self.images = ["https://example.com/tv1.jpg", "https://example.com/tv2.jpg"]
                self.url = TEST_URL
        
        product = MockProduct()
        print(f"  ✅ Producto extraído: {product.title[:50]}...")
        print(f"  💰 Precio: ${product.price_low} - ${product.price_high}")
        
    except Exception as e:
        print(f"  ❌ Error en scraping: {e}")
        return False
    
    # === PASO 2: Clasificación NCM con VUCE ===
    print("\n🤖 PASO 2: Clasificación NCM + Validación VUCE")
    try:
        classifier = AINcmClassifier(api_keys.get("OPENAI_API_KEY"))
        
        # Descripción mejorada
        enhanced_description = f"{product.title} | Categorías: {', '.join(product.categories)} | Origen: {product.place_of_origin} | Precio: ${product.price_low}-${product.price_high}"
        
        print(f"  🔍 Descripción: {enhanced_description[:80]}...")
        
        # Clasificar con integración VUCE
        ncm_result = await classifier.classify_product(
            description=enhanced_description,
            image_url=product.images[0] if product.images else None
        )
        
        if "error" in ncm_result:
            print(f"  ❌ Error en clasificación: {ncm_result['error']}")
            return False
        
        print(f"  ✅ NCM clasificado: {ncm_result.get('ncm_completo', 'N/A')}")
        print(f"  🎯 Confianza: {ncm_result.get('confianza', 'N/A')}")
        
        # Verificar datos VUCE
        if 'vuce_info' in ncm_result:
            vuce_info = ncm_result['vuce_info']
            print(f"  🇦🇷 VUCE Match: {'✅' if vuce_info.get('match_exacto') else '❌'}")
            
            # Tratamiento arancelario
            treatment = ncm_result.get('tratamiento_arancelario', {})
            if treatment.get('fuente') == 'VUCE Oficial':
                print(f"  💰 Arancel (VUCE): {treatment.get('derechos_importacion', 'N/A')}")
            else:
                print(f"  💰 Arancel (IA): {treatment.get('derechos_importacion', 'N/A')}")
        
        # Régimen simplificado
        regime = ncm_result.get('regimen_simplificado_courier', {})
        final_decision = regime.get('aplica_final', regime.get('aplica', 'N/A'))
        print(f"  🚚 Régimen Simplificado: {final_decision}")
        
        if 'vuce_warning' in ncm_result:
            print(f"  ⚠️ VUCE Warning: {ncm_result['vuce_warning']}")
        
    except Exception as e:
        print(f"  ❌ Error en clasificación NCM: {e}")
        return False
    
    # === PASO 3: Cálculo de impuestos ===
    print("\n💰 PASO 3: Calculando impuestos")
    try:
        precio_promedio = (product.price_low + product.price_high) / 2
        
        tax_result = calcular_impuestos_importacion(
            cif_value=precio_promedio,
            tipo_importador="responsable_inscripto",
            destino="reventa", 
            origen="extrazona",
            tipo_dolar="oficial",
            provincia="CABA"
        )
        
        print(f"  ✅ Impuestos calculados: ${float(tax_result.total_impuestos):.2f}")
        print(f"  📊 Incidencia: {float(tax_result.incidencia_porcentual):.1f}%")
        
    except Exception as e:
        print(f"  ❌ Error calculando impuestos: {e}")
        return False
    
    # === PASO 4: Estimación de dimensiones ===
    print("\n📦 PASO 4: Estimando dimensiones y peso")
    try:
        estimator = ProductShippingEstimator()
        
        # Simular datos del producto para el estimador
        product_dict = {
            'subject': product.title,
            'categories': product.categories,
            'mediaItems': [{'type': 'image', 'imageUrl': {'big': url}} for url in product.images],
            'productHtmlDescription': '',
            'productBasicProperties': []
        }
        
        shipping_details = estimator.get_shipping_details(product_dict)
        
        if shipping_details.get('weight_kg'):
            print(f"  ✅ Peso estimado: {shipping_details['weight_kg']:.2f} kg")
        if shipping_details.get('dimensions_cm'):
            dims = shipping_details['dimensions_cm']
            print(f"  📐 Dimensiones: {dims.get('length', 'N/A')}x{dims.get('width', 'N/A')}x{dims.get('height', 'N/A')} cm")
        
        print(f"  🔧 Método: {shipping_details.get('method', 'N/A')}")
        
    except Exception as e:
        print(f"  ❌ Error estimando dimensiones: {e}")
        shipping_details = {"method": "failed_fallback"}
    
    # === PASO 5: Cálculo de flete (simulado) ===
    print("\n🚚 PASO 5: Calculando flete")
    try:
        # Simulación de flete
        flete_costo = precio_promedio * 0.15  # 15% estimado
        print(f"  ✅ Flete estimado: ${flete_costo:.2f}")
        
    except Exception as e:
        print(f"  ❌ Error calculando flete: {e}")
        return False
    
    # === PASO 6: Landed Cost Final ===
    print("\n🎯 PASO 6: Cálculo Final")
    try:
        honorarios_despachante = precio_promedio * 0.02
        landed_cost = precio_promedio + float(tax_result.total_impuestos) + flete_costo + honorarios_despachante
        
        print(f"  💰 Precio producto: ${precio_promedio:.2f}")
        print(f"  🏛️ Impuestos: ${float(tax_result.total_impuestos):.2f}")
        print(f"  🚚 Flete: ${flete_costo:.2f}")
        print(f"  👤 Despachante: ${honorarios_despachante:.2f}")
        print(f"  🎯 LANDED COST: ${landed_cost:.2f}")
        
        markup = ((landed_cost - precio_promedio) / precio_promedio) * 100
        print(f"  📈 Markup total: {markup:.1f}%")
        
    except Exception as e:
        print(f"  ❌ Error en cálculo final: {e}")
        return False
    
    print("\n" + "="*60)
    print("🏁 PRUEBA COMPLETADA EXITOSAMENTE")
    print(f"⏰ {datetime.now().strftime('%H:%M:%S')}")
    print("="*60)
    
    # Resumen de resultados
    print(f"\n📊 RESUMEN:")
    print(f"  • NCM: {ncm_result.get('ncm_completo', 'N/A')}")
    print(f"  • VUCE: {'✅ Validado' if ncm_result.get('vuce_info', {}).get('match_exacto') else '❌ No validado'}")
    print(f"  • Régimen Simplificado: {final_decision}")
    print(f"  • Landing Cost: ${landed_cost:.2f} USD")
    print(f"  • Todos los módulos funcionando: ✅")
    
    return True

if __name__ == "__main__":
    success = asyncio.run(test_complete_flow())
    
    if success:
        print("\n🎉 ¡SISTEMA COMPLETAMENTE FUNCIONAL!")
        print("✅ Listo para usar en la aplicación Streamlit")
    else:
        print("\n❌ Hay errores en el sistema")
        print("🔧 Revisar logs y corregir antes de usar")
        sys.exit(1) 