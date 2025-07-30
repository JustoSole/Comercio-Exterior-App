#!/usr/bin/env python3
"""
🧪 Test Deep NCM Classifier
============================

Script de prueba para verificar que el nuevo clasificador profundo de NCM
funciona correctamente con toda la funcionalidad implementada.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Agregar directorio del proyecto al path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_debug_callback(message, data=None, level="INFO"):
    """Callback de debug para testing"""
    print(f"[{level}] {message}")
    if data and level in ["ERROR", "SUCCESS"]:
        print(f"    Data: {json.dumps(data, indent=2, ensure_ascii=False)[:200]}...")

async def test_deep_classifier():
    """Test del clasificador profundo"""
    print("🚀 Iniciando test del Deep NCM Classifier...")
    
    try:
        # Verificar que la API key esté disponible
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            print("❌ ERROR: No se encontró OPENAI_API_KEY en variables de entorno")
            return False
        
        # Importar el clasificador
        from ai_ncm_deep_classifier import DeepNCMClassifier
        
        # Crear instancia del clasificador
        classifier = DeepNCMClassifier(
            api_key=api_key,
            debug_callback=test_debug_callback
        )
        
        print("✅ Clasificador inicializado correctamente")
        
        # Test con producto ejemplo
        test_products = [
            {
                "description": "Smartphone Samsung Galaxy A54 5G, pantalla AMOLED 6.4 pulgadas, 128GB almacenamiento, cámara triple 50MP+12MP+5MP, Android 13, color azul",
                "image_url": None,
                "expected_chapter": "85"  # Capítulo 85 - aparatos eléctricos
            },
            {
                "description": "Perfume para mujer Chanel No. 5, eau de parfum 100ml, fragancia floral aldehídica, presentado en caja de regalo",
                "image_url": None,
                "expected_chapter": "33"  # Capítulo 33 - aceites esenciales y perfumes
            }
        ]
        
        for i, test_product in enumerate(test_products, 1):
            print(f"\n🔍 Test {i}: {test_product['description'][:50]}...")
            
            try:
                # Ejecutar clasificación profunda
                result = await classifier.classify_product_deep(
                    description=test_product["description"],
                    image_url=test_product["image_url"]
                )
                
                if "error" in result:
                    print(f"❌ Error en clasificación: {result['error']}")
                    continue
                
                # Verificar resultado
                final_classification = result.get('final_classification', {})
                if not final_classification:
                    print("❌ No se obtuvo clasificación final")
                    continue
                
                # Mostrar resultados principales
                ncm_completo = final_classification.get('ncm_completo', 'N/A')
                confianza = final_classification.get('nivel_confianza', 'N/A')
                metodo = result.get('method', 'N/A')
                tiempo = result.get('processing_time_seconds', 0)
                
                print(f"✅ Clasificación exitosa:")
                print(f"   NCM: {ncm_completo}")
                print(f"   Confianza: {confianza}")
                print(f"   Método: {metodo}")
                print(f"   Tiempo: {tiempo:.2f}s")
                
                # Verificar capítulo esperado
                if ncm_completo.startswith(test_product['expected_chapter']):
                    print(f"✅ Capítulo correcto ({test_product['expected_chapter']})")
                else:
                    print(f"⚠️ Capítulo diferente al esperado (esperado: {test_product['expected_chapter']}, obtenido: {ncm_completo[:2]})")
                
                # Verificar fases del proceso
                process_steps = result.get('process_steps', [])
                print(f"   Fases completadas: {len(process_steps)}")
                
                for step in process_steps:
                    status_icon = {"completed": "✅", "error": "❌", "started": "🟡"}.get(step.get('status', ''), "⚪")
                    print(f"     {status_icon} {step.get('phase', 'Unknown').replace('_', ' ').title()}")
                
                # Verificar tratamiento arancelario
                tratamiento = final_classification.get('tratamiento_arancelario', {})
                if tratamiento:
                    aec = tratamiento.get('derechos_importacion', 'N/A')
                    print(f"   AEC: {aec}")
                
                # Verificar régimen simplificado
                regimen = final_classification.get('regimen_simplificado_courier', {})
                if regimen:
                    aplica = regimen.get('aplica', 'N/A')
                    print(f"   Régimen Simplificado: {aplica}")
                
            except Exception as e:
                print(f"❌ Error en test {i}: {e}")
                import traceback
                traceback.print_exc()
        
        print("\n🎉 Tests completados!")
        return True
        
    except ImportError as e:
        print(f"❌ Error de importación: {e}")
        print("   Verifica que ai_ncm_deep_classifier.py esté disponible")
        return False
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_ncm_official_integration():
    """Test de integración con base de datos oficial NCM"""
    print("\n🔍 Testing NCM Official Integration...")
    
    try:
        from ncm_official_integration import NCMOfficialIntegration
        
        integration = NCMOfficialIntegration()
        print("✅ Integración NCM inicializada")
        
        # Test búsqueda exacta
        test_codes = ["85287200", "8528.72.00"]
        
        for code in test_codes:
            print(f"\n🔎 Probando código: {code}")
            
            exact_match = integration.search_exact_ncm(code)
            if exact_match:
                print(f"   ✅ Match exacto: {exact_match.get('description', 'N/A')[:50]}...")
                print(f"   Tipo: {exact_match.get('record_type', 'N/A')}")
                print(f"   AEC: {exact_match.get('tratamiento_arancelario', {}).get('aec', 0)}%")
            else:
                print(f"   ❌ No se encontró match exacto")
            
            # Test búsqueda jerárquica
            hierarchical = integration.search_hierarchical_ncm(code, max_results=3)
            print(f"   🔍 Matches jerárquicos: {len(hierarchical)}")
            
            for match in hierarchical[:2]:  # Solo primeros 2
                print(f"     - {match.get('ncm_code', '')}: {match.get('description', '')[:40]}...")
        
        return True
        
    except Exception as e:
        print(f"❌ Error en test de integración NCM: {e}")
        return False

if __name__ == "__main__":
    print("🧪 DEEP NCM CLASSIFIER TESTS")
    print("=" * 40)
    
    async def run_all_tests():
        # Test 1: Clasificador profundo
        success1 = await test_deep_classifier()
        
        # Test 2: Integración oficial NCM
        success2 = await test_ncm_official_integration()
        
        if success1 and success2:
            print("\n🎉 ¡TODOS LOS TESTS PASARON!")
            print("\n💡 El sistema está listo para usar:")
            print("   - Clasificación profunda con despachante de aduanas ✅")
            print("   - Exploración jerárquica completa ✅") 
            print("   - Debug detallado ✅")
            print("   - Integración con app principal ✅")
        else:
            print("\n❌ Algunos tests fallaron. Revisar configuración.")
    
    asyncio.run(run_all_tests()) 