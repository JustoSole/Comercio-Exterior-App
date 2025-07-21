#!/usr/bin/env python3
"""
🧪 Test Enhanced NCM Classifier - Test del Clasificador Mejorado
===============================================================

Script para probar el clasificador NCM mejorado con integración VUCE.
Prueba tanto el clasificador de IA como la validación con VUCE.

Funcionalidades:
- Test de clasificación NCM con IA
- Test de integración con VUCE
- Validación de régimen simplificado
- Test de detección de intervenciones

Autor: Desarrollado para comercio exterior
"""

import asyncio
import json
import os
from datetime import datetime

# Intentar importar los módulos
try:
    from vuce_integration import VuceIntegration, get_vuce_info
    VUCE_AVAILABLE = True
    print("✅ Módulo VUCE disponible")
except ImportError as e:
    VUCE_AVAILABLE = False
    print(f"❌ Error importando VUCE: {e}")

try:
    from ai_ncm_classifier import AINcmClassifier
    AI_AVAILABLE = True
    print("✅ Módulo AI Classifier disponible")
except ImportError as e:
    AI_AVAILABLE = False
    print(f"❌ Error importando AI Classifier: {e}")

# Productos de prueba
TEST_PRODUCTS = [
    {
        "description": "Smart TV LED 32 pulgadas Full HD con WiFi y control remoto",
        "expected_ncm": "8528.72.00",
        "expected_chapter": "85",
        "expected_simplified_regime": True,
        "image_url": None
    },
    {
        "description": "Auriculares inalámbricos Bluetooth con micrófono y estuche de carga",
        "expected_ncm": "8518.30.00",
        "expected_chapter": "85", 
        "expected_simplified_regime": True,
        "image_url": None
    },
    {
        "description": "Suplemento vitamínico B12 en cápsulas 60 unidades",
        "expected_ncm": "2106.90.90",
        "expected_chapter": "21",
        "expected_simplified_regime": False,  # Requiere ANMAT
        "image_url": None
    },
    {
        "description": "Camiseta 100% algodón manga corta para hombre talla M",
        "expected_ncm": "6109.10.00",
        "expected_chapter": "61",
        "expected_simplified_regime": True,
        "image_url": None
    }
]

async def test_vuce_integration():
    """Test de integración básica con VUCE"""
    print("\n" + "="*60)
    print("🧪 TESTE DE INTEGRACIÓN CON VUCE")
    print("="*60)
    
    if not VUCE_AVAILABLE:
        print("❌ VUCE no disponible para testing")
        return False
    
    test_ncm_codes = ["8528.72.00", "8518.30.00", "6109.10.00"]
    
    for ncm_code in test_ncm_codes:
        print(f"\n🔍 Probando NCM: {ncm_code}")
        try:
            result = await get_vuce_info(ncm_code, headless=True)
            
            if result.get("success"):
                print(f"  ✅ Éxito - Match exacto: {result.get('match_exacto')}")
                print(f"  📋 Descripción: {result.get('posicion_encontrada', {}).get('descripcion', 'N/A')[:80]}...")
                
                treatment = result.get('tratamiento_arancelario', {})
                print(f"  💰 Arancel: {treatment.get('arancel_externo_comun', 'N/A')}%")
                
                regime = result.get('regimen_simplificado', {})
                print(f"  🚚 Régimen Simplificado: {'✅' if regime.get('aplica_potencialmente') else '❌'}")
                
                interventions = result.get('intervenciones', {})
                orgs = interventions.get('organismos_potenciales', [])
                print(f"  🏛️ Intervenciones: {', '.join(orgs) if orgs else 'Ninguna'}")
                
            else:
                print(f"  ❌ Error: {result.get('error', 'Error desconocido')}")
                
        except Exception as e:
            print(f"  💥 Excepción: {str(e)}")
    
    return True

async def test_enhanced_classifier():
    """Test del clasificador mejorado con integración VUCE"""
    print("\n" + "="*60)
    print("🤖 TEST DE CLASIFICADOR MEJORADO")
    print("="*60)
    
    if not AI_AVAILABLE:
        print("❌ AI Classifier no disponible para testing")
        return False
    
    # Verificar API key (muy básico)
    openai_key = os.environ.get('OPENAI_API_KEY', '')
    if not openai_key or len(openai_key) < 20:
        print("⚠️ API Key de OpenAI no configurada correctamente")
        print("   Configurar OPENAI_API_KEY en las variables de entorno")
        return False
    
    print(f"✅ API Key detectada: {openai_key[:10]}...{openai_key[-4:]}")
    
    classifier = AINcmClassifier(api_key=openai_key)
    
    results = []
    
    for i, product in enumerate(TEST_PRODUCTS, 1):
        print(f"\n🔍 Producto {i}/4: {product['description'][:60]}...")
        
        try:
            # Usar el método async que incluye integración con VUCE
            result = await classifier.classify_product(
                description=product['description'],
                image_url=product.get('image_url')
            )
            
            if 'error' in result:
                print(f"  ❌ Error: {result['error']}")
                continue
            
            # Análisis del resultado
            ncm_code = result.get('ncm_completo', 'N/A')
            confidence = result.get('confianza', 'N/A')
            
            print(f"  📋 NCM Clasificado: {ncm_code}")
            print(f"  🎯 Confianza: {confidence}")
            
            # Verificar si coincide con lo esperado
            expected_ncm = product['expected_ncm']
            if ncm_code == expected_ncm:
                print(f"  ✅ NCM correcto (esperado: {expected_ncm})")
            else:
                print(f"  ⚠️ NCM diferente (esperado: {expected_ncm})")
            
            # Análisis de régimen simplificado
            regime = result.get('regimen_simplificado_courier', {})
            final_decision = regime.get('aplica_final', regime.get('aplica', 'N/A'))
            expected_regime = product['expected_simplified_regime']
            
            print(f"  🚚 Régimen Simplificado: {final_decision}")
            
            if (final_decision == "Sí") == expected_regime:
                print(f"  ✅ Régimen correcto (esperado: {'Sí' if expected_regime else 'No'})")
            else:
                print(f"  ⚠️ Régimen diferente (esperado: {'Sí' if expected_regime else 'No'})")
            
            # Información de VUCE si está disponible
            if 'vuce_info' in result:
                vuce_info = result['vuce_info']
                print(f"  🇦🇷 VUCE: Match exacto {vuce_info.get('match_exacto', False)}")
                if vuce_info.get('intervenciones_detectadas'):
                    print(f"  🏛️ Intervenciones VUCE: {', '.join(vuce_info['intervenciones_detectadas'])}")
            
            # Tratamiento arancelario
            treatment = result.get('tratamiento_arancelario', {})
            if treatment:
                print(f"  💰 Arancel: {treatment.get('derechos_importacion', 'N/A')}")
                print(f"  📊 Fuente: {treatment.get('fuente', 'IA')}")
            
            results.append({
                "product": product['description'],
                "ncm_classified": ncm_code,
                "ncm_expected": expected_ncm,
                "ncm_correct": ncm_code == expected_ncm,
                "regime_classified": final_decision,
                "regime_expected": "Sí" if expected_regime else "No",
                "regime_correct": (final_decision == "Sí") == expected_regime,
                "confidence": confidence,
                "has_vuce_info": 'vuce_info' in result,
                "vuce_warning": result.get('vuce_warning')
            })
            
        except Exception as e:
            print(f"  💥 Excepción: {str(e)}")
            results.append({
                "product": product['description'],
                "error": str(e)
            })
    
    # Resumen de resultados
    print("\n" + "="*60)
    print("📊 RESUMEN DE RESULTADOS")
    print("="*60)
    
    successful_tests = [r for r in results if 'error' not in r]
    failed_tests = [r for r in results if 'error' in r]
    
    print(f"✅ Tests exitosos: {len(successful_tests)}/{len(results)}")
    print(f"❌ Tests fallidos: {len(failed_tests)}/{len(results)}")
    
    if successful_tests:
        ncm_correct = sum(1 for r in successful_tests if r.get('ncm_correct', False))
        regime_correct = sum(1 for r in successful_tests if r.get('regime_correct', False))
        with_vuce = sum(1 for r in successful_tests if r.get('has_vuce_info', False))
        
        print(f"🎯 Precisión NCM: {ncm_correct}/{len(successful_tests)} ({ncm_correct/len(successful_tests)*100:.1f}%)")
        print(f"🚚 Precisión Régimen: {regime_correct}/{len(successful_tests)} ({regime_correct/len(successful_tests)*100:.1f}%)")
        print(f"🇦🇷 Con datos VUCE: {with_vuce}/{len(successful_tests)} ({with_vuce/len(successful_tests)*100:.1f}%)")
    
    if failed_tests:
        print(f"\n❌ Errores encontrados:")
        for test in failed_tests:
            print(f"  - {test['product'][:50]}...: {test['error']}")
    
    # Guardar resultados detallados
    output_file = f"test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n💾 Resultados guardados en: {output_file}")
    
    return len(successful_tests) > 0

async def test_ncm_validation():
    """Test de validación de códigos NCM"""
    print("\n" + "="*60)
    print("🔍 TEST DE VALIDACIÓN NCM")
    print("="*60)
    
    if not VUCE_AVAILABLE:
        print("❌ VUCE no disponible para validación")
        return False
    
    integration = VuceIntegration()
    
    test_codes = [
        "8528.72.00",    # Válido - TVs
        "8518.30.00",    # Válido - Auriculares
        "1234.56.78",    # Inválido - No existe
        "85287200",      # Sin puntos
        "8528.72",       # Incompleto
        "99999999"       # Código inválido
    ]
    
    for code in test_codes:
        print(f"\n🔍 Validando: {code}")
        validation = integration.validate_ncm_code(code)
        
        is_valid = validation['es_valido']
        formatted = validation['codigo_formateado']
        
        print(f"  {'✅' if is_valid else '❌'} Válido: {is_valid}")
        print(f"  📝 Formateado: {formatted}")
        print(f"  📋 Recomendación: {validation['recomendacion']}")
    
    return True

async def main():
    """Función principal que ejecuta todos los tests"""
    print("🚀 INICIANDO TESTS DEL SISTEMA MEJORADO")
    print(f"⏰ Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Test 1: Validación NCM
    await test_ncm_validation()
    
    # Test 2: Integración VUCE
    await test_vuce_integration()
    
    # Test 3: Clasificador mejorado (requiere API key)
    await test_enhanced_classifier()
    
    print("\n" + "="*60)
    print("🏁 TESTS COMPLETADOS")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main()) 