#!/usr/bin/env python3
"""
🔗 Ejemplo de Integración: AI NCM Classifier + Position Matcher
==============================================================

Script que demuestra cómo integrar el clasificador IA con el matcher
de posiciones para obtener clasificaciones completas y enriquecidas.

Flujo completo:
1. Producto + imagen → AI Classifier → NCM estimado
2. NCM estimado → Position Matcher → Validación + enriquecimiento
3. Resultado final con datos oficiales

Autor: Comercio exterior integrado
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

# Importar nuestros módulos
from ai_ncm_classifier import AINcmClassifier, classify_single_product
from ncm_position_matcher import NCMPositionMatcher, match_single_ncm

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

class IntegratedNCMClassifier:
    """Clasificador integrado que combina IA + validación oficial"""
    
    def __init__(self, ncm_data_file: str, openai_api_key: str = None):
        """
        Inicializar clasificador integrado
        
        Args:
            ncm_data_file: Archivo CSV con datos oficiales NCM
            openai_api_key: API key de OpenAI (opcional)
        """
        self.ai_classifier = AINcmClassifier(openai_api_key)
        self.position_matcher = NCMPositionMatcher(ncm_data_file, openai_api_key)
        logger.info("Clasificador integrado inicializado")
    
    async def classify_and_validate(
        self,
        description: str,
        image_url: Optional[str] = None,
        validate_position: bool = True
    ) -> Dict[str, Any]:
        """
        Clasifica producto con IA y valida con datos oficiales
        
        Args:
            description: Descripción del producto
            image_url: URL de imagen (opcional)
            validate_position: Si validar con datos oficiales
            
        Returns:
            Resultado integrado con clasificación y validación
        """
        logger.info(f"Iniciando clasificación integrada para: {description[:50]}...")
        
        # Paso 1: Clasificación con IA
        logger.info("Paso 1: Clasificación con IA...")
        ai_result = await self.ai_classifier.classify_product(description, image_url)
        
        if ai_result.get('error'):
            return {
                'stage': 'ai_classification',
                'success': False,
                'error': ai_result.get('error'),
                'ai_result': ai_result
            }
        
        ncm_code = ai_result.get('ncm_completo')
        if not ncm_code:
            return {
                'stage': 'ai_classification',
                'success': False,
                'error': 'IA no retornó código NCM válido',
                'ai_result': ai_result
            }
        
        logger.info(f"IA clasificó como: {ncm_code}")
        
        result = {
            'stage': 'completed',
            'success': True,
            'ai_classification': ai_result,
            'ncm_from_ai': ncm_code
        }
        
        # Paso 2: Validación con datos oficiales (opcional)
        if validate_position:
            logger.info("Paso 2: Validando con datos oficiales...")
            
            validation_result = await self.position_matcher.match_position(ncm_code)
            
            result['validation'] = validation_result
            result['final_recommendation'] = self._create_final_recommendation(
                ai_result, validation_result
            )
        
        return result
    
    def _create_final_recommendation(
        self,
        ai_result: Dict[str, Any],
        validation_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Crea recomendación final combinando IA y validación"""
        
        ai_ncm = ai_result.get('ncm_completo', '')
        ai_confidence = ai_result.get('confianza', 'Baja')
        
        validation_type = validation_result.get('match_type', 'error')
        
        if validation_type == 'exacto':
            # Match exacto: usar datos oficiales
            return {
                'recommended_ncm': validation_result['position']['code'],
                'confidence': 'Alta',
                'source': 'Datos oficiales (match exacto)',
                'fiscal_data': validation_result['position']['attributes'],
                'interventions': validation_result['position']['interventions'],
                'simplified_regime': validation_result['position']['simplified_regime'],
                'notes': f"Código IA ({ai_ncm}) validado exitosamente con datos oficiales"
            }
        
        elif validation_type == 'aproximado':
            # Match aproximado: combinar IA + aproximación
            validation_confidence = validation_result.get('metadata', {}).get('confidence', 0)
            
            if validation_confidence > 70:
                return {
                    'recommended_ncm': validation_result['position']['code'],
                    'confidence': 'Media-Alta',
                    'source': 'Datos oficiales (match aproximado)',
                    'fiscal_data': validation_result['position']['attributes'],
                    'interventions': validation_result['position']['interventions'],
                    'simplified_regime': validation_result['position']['simplified_regime'],
                    'notes': f"Código IA ({ai_ncm}) aproximado a posición oficial con {validation_confidence}% confianza"
                }
            else:
                return {
                    'recommended_ncm': ai_ncm,
                    'confidence': ai_confidence,
                    'source': 'Clasificación IA (validación aproximada baja confianza)',
                    'fiscal_data': ai_result.get('tratamiento_arancelario', {}),
                    'interventions': ai_result.get('intervenciones_requeridas', []),
                    'simplified_regime': ai_result.get('regimen_simplificado_courier', {}),
                    'notes': f"Usando clasificación IA. Validación aproximada solo {validation_confidence}% confianza"
                }
        
        else:
            # Sin validación o error: usar solo IA
            return {
                'recommended_ncm': ai_ncm,
                'confidence': ai_confidence,
                'source': 'Solo clasificación IA',
                'fiscal_data': ai_result.get('tratamiento_arancelario', {}),
                'interventions': ai_result.get('intervenciones_requeridas', []),
                'simplified_regime': ai_result.get('regimen_simplificado_courier', {}),
                'notes': f"Sin validación oficial disponible. Confianza IA: {ai_confidence}"
            }
    
    async def batch_classify(self, products: list) -> list:
        """Clasifica múltiples productos"""
        results = []
        
        for i, product in enumerate(products, 1):
            logger.info(f"Procesando producto {i}/{len(products)}")
            
            if isinstance(product, dict):
                description = product.get('description', '')
                image_url = product.get('image_url')
            else:
                description = str(product)
                image_url = None
            
            result = await self.classify_and_validate(description, image_url)
            result['product_id'] = i
            results.append(result)
        
        return results

async def demo_integration():
    """Demo de integración completa"""
    print("🚀 DEMO: Clasificador NCM Integrado")
    print("=" * 50)
    
    # Configuración
    data_file = "pdf_reader/ncm/resultados_ncm_hybrid/dataset_ncm_HYBRID_FIXED_20250721_175449.csv"
    
    if not Path(data_file).exists():
        print(f"❌ Error: Archivo de datos no encontrado: {data_file}")
        return
    
    # Inicializar clasificador integrado
    try:
        classifier = IntegratedNCMClassifier(data_file)
    except Exception as e:
        print(f"❌ Error inicializando clasificador: {e}")
        return
    
    # Productos de prueba
    test_products = [
        {
            'description': 'Televisor LCD de 32 pulgadas, marca Samsung, con conexión HDMI',
            'image_url': None
        },
        {
            'description': 'Smartphone iPhone 13, 128GB, color azul',
            'image_url': None
        },
        {
            'description': 'Caballo pura sangre de carrera, macho, 3 años',
            'image_url': None
        }
    ]
    
    # Procesar cada producto
    for i, product in enumerate(test_products, 1):
        print(f"\n{'='*60}")
        print(f"🔍 PRODUCTO {i}: {product['description'][:50]}...")
        print('='*60)
        
        try:
            result = await classifier.classify_and_validate(
                product['description'],
                product.get('image_url'),
                validate_position=True
            )
            
            print(f"✅ Estado: {result['stage']}")
            
            if result.get('success'):
                # Mostrar clasificación IA
                ai_ncm = result.get('ncm_from_ai', 'N/A')
                print(f"🤖 IA clasificó como: {ai_ncm}")
                
                # Mostrar validación
                validation = result.get('validation', {})
                validation_type = validation.get('match_type', 'N/A')
                print(f"🔍 Validación: {validation_type}")
                
                # Mostrar recomendación final
                final = result.get('final_recommendation', {})
                if final:
                    print(f"📋 RECOMENDACIÓN FINAL:")
                    print(f"   NCM: {final.get('recommended_ncm', 'N/A')}")
                    print(f"   Confianza: {final.get('confidence', 'N/A')}")
                    print(f"   Fuente: {final.get('source', 'N/A')}")
                    print(f"   Notas: {final.get('notes', 'N/A')}")
                    
                    # Datos fiscales
                    fiscal = final.get('fiscal_data', {})
                    if fiscal:
                        print(f"   💰 AEC: {fiscal.get('aec', 'N/A')}%")
                        print(f"   💰 IVA: {fiscal.get('iva', 'N/A')}%")
                    
                    # Intervenciones
                    interventions = final.get('interventions', [])
                    if interventions:
                        print(f"   🏛️  Intervenciones: {', '.join(interventions)}")
            
            else:
                print(f"❌ Error: {result.get('error', 'Error desconocido')}")
        
        except Exception as e:
            print(f"❌ Error procesando producto: {e}")
    
    print(f"\n🎉 Demo completado!")

async def quick_test():
    """Test rápido de funcionalidad"""
    print("🧪 Test rápido de integración...")
    
    data_file = "pdf_reader/ncm/resultados_ncm_hybrid/dataset_ncm_HYBRID_FIXED_20250721_175449.csv"
    
    if not Path(data_file).exists():
        print(f"❌ Archivo de datos no encontrado")
        return False
    
    try:
        # Test solo con position matcher (sin IA)
        matcher = NCMPositionMatcher(data_file)
        result = await matcher.match_position("0101.21.00 100W")
        
        print(f"✅ Position Matcher: {result['match_type']}")
        
        # Test con IA (si disponible)
        try:
            ai_result = await classify_single_product("caballo de carrera")
            if not ai_result.get('error'):
                print(f"✅ AI Classifier: NCM {ai_result.get('ncm_completo', 'N/A')}")
            else:
                print(f"⚠️ AI Classifier: {ai_result.get('error', 'Error')}")
        except Exception as e:
            print(f"⚠️ AI Classifier no disponible: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error en test: {e}")
        return False

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--quick":
        success = asyncio.run(quick_test())
        sys.exit(0 if success else 1)
    else:
        asyncio.run(demo_integration()) 