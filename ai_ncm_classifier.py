#!/usr/bin/env python3
"""
🤖 AI NCM Classifier - Clasificador Automático de Códigos Arancelarios
=====================================================================

Script que usa GPT-4o-mini para clasificar automáticamente productos
con códigos NCM/HS usando imágenes y descripciones.

Funcionalidades:
- Análisis de imágenes + descripción
- Clasificación NCM/HS automática usando base de datos oficial
- Determinación de régimen simplificado
- Identificación de intervenciones
- Output en JSON estructurado

Autor: Desarrollado para comercio exterior
Actualizado: Base de datos oficial NCM en lugar de scraping VUCE
"""

import os
import json
import base64
import logging
from typing import Dict, List, Optional, Union, Any
from pathlib import Path
import requests
from datetime import datetime
import re
import traceback
import backoff
import openai
from tenacity import retry, stop_after_attempt, wait_exponential
from typing import Dict, Any, Optional
from urllib.parse import urlparse

import asyncio

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Intentar importar OpenAI
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("OpenAI library not installed. Install with: pip install openai")

# Intentar cargar desde secrets centralizados
try:
    from secrets_config import get_api_key
    OPENAI_API_KEY = get_api_key("OPENAI_API_KEY") or ""
except ImportError:
    # Fallback para cuando se ejecuta independientemente
    OPENAI_API_KEY = ""

# --- Enhanced System Prompt ---
SYSTEM_PROMPT_V2_REVISED = """
Eres un especialista en comercio exterior y un experto en la Nomenclatura Común del Mercosur (NCM) de Argentina, actualizado a la última normativa incluyendo la RG 5631/2025 sobre régimen simplificado de importación. Tu tarea es analizar la información de un producto y devolver una clasificación arancelaria precisa y bien justificada.

REGLAS ESTRICTAS:
1.  **ANÁLISIS**: Examina la descripción y, si se proporciona, la imagen del producto. La imagen es la fuente de verdad principal si hay discrepancias.
2.  **CLASIFICACIÓN**: Usa el Sistema Armonizado y la NCM para encontrar el código más específico posible. El código NCM debe ser un código válido en Argentina.
3.  **FORMATO DE SALIDA**: Tu respuesta DEBE SER ÚNICAMENTE un objeto JSON válido, sin texto introductorio ni explicaciones fuera del JSON.

INFORMACIÓN SOBRE RÉGIMEN SIMPLIFICADO (RG 5631/2025):
- Aplica para productos con valor CIF hasta USD 3,000
- Peso máximo de 50kg por envío
- Solo para envíos postales o courier habilitados
- Excluye: bebidas alcohólicas, tabaco, medicamentos, armas, vehículos, productos de origen animal/vegetal sin certificación
- Capítulos típicamente EXCLUIDOS: 22 (bebidas), 24 (tabaco), 30 (farmacéuticos), 87-89 (vehículos), 93 (armas)
- Productos electrónicos, textiles, juguetes, accesorios GENERALMENTE SÍ APLICAN si cumplen valor y peso

ESQUEMA JSON DE RESPUESTA OBLIGATORIO:
{
  "ncm_completo": "8528.72.00",            // Código NCM completo (8 dígitos con puntos). Ejemplo: 8528.72.00
  "ncm_descripcion": "Descripción oficial del NCM",
  "ncm_desglose": {
    "capitulo": "85 - Máquinas, aparatos y material eléctrico",
    "partida": "8528 - Monitores y proyectores, aparatos receptores de televisión",
    "subpartida": "8528.72 - Aparatos receptores de televisión, los demás, en colores"
  },
  "justificacion_clasificacion": "Explicación técnica detallada de por qué se eligió este NCM, citando las Reglas Generales de Interpretación si es relevante.",
  "tratamiento_arancelario": {
    "derechos_importacion": "20.0%",        // Arancel de importación estimado
    "tasa_estadistica": "3.0%",
    "iva": "21.0%",
    "iva_adicional": "0.0%",
    "intervenciones": []                     // Lista de organismos que intervienen
  },
  "regimen_simplificado_courier": {
    "aplica": "Sí" | "No" | "Condicional",
    "justificacion": "Análisis específico basado en RG 5631/2025 considerando tipo de producto, capítulo NCM y restricciones típicas.",
    "limitaciones": "Valor máximo USD 3,000, peso máximo 50kg, origen courier habilitado"
  },
  "intervenciones_requeridas": [           // Lista específica de organismos. Si no hay, array vacío []
    "INTI - CIE (productos electrónicos)",
    "ANMAT (productos de salud)"
  ],
  "confianza": "Alta" | "Media" | "Baja",  // Tu nivel de confianza en esta clasificación
  "observaciones_adicionales": "Notas adicionales relevantes para la importación",
  "classification_method": "ia_analysis"   // Método usado para clasificación
}

IMPORTANTE: 
- Siempre devuelve códigos NCM REALES y válidos
- Si no estás seguro del código exacto, usa el más específico que puedas determinar
- Las intervenciones deben ser organismos argentinos reales (ANMAT, INTI, SENASA, etc.)
- El análisis de régimen simplificado debe ser detallado y basado en la normativa real
- La confianza debe reflejar qué tan seguro estás de la clasificación (Alta: >90%, Media: 70-90%, Baja: <70%)
"""


class AINcmClassifier:
    """Clasificador automático de NCM usando OpenAI GPT-4o-mini con validación mejorada."""
    
    def __init__(self, api_key: str = None):
        """
        Inicializar el clasificador
        
        Args:
            api_key: API key de OpenAI (opcional, usa variable de entorno si no se proporciona)
        """
        if not OPENAI_AVAILABLE:
            raise ImportError("OpenAI library not installed. Install with: pip install openai")
        
        self.api_key = api_key or os.getenv('OPENAI_API_KEY', OPENAI_API_KEY)
        if not self.api_key:
            raise ValueError("OpenAI API key is required")
        
        self.client = OpenAI(api_key=self.api_key)
        logger.info("AI NCM Classifier initialized (v2 with validation)")
    
    def encode_image_to_base64(self, image_path: str) -> str:
        """
        Codificar imagen a base64
        
        Args:
            image_path: Ruta a la imagen
            
        Returns:
            String base64 de la imagen
        """
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
            logger.error(f"Error encoding image: {e}")
            raise
    
    def download_image_from_url(self, url: str) -> str:
        """
        Descargar imagen desde URL y convertir a base64
        
        Args:
            url: URL de la imagen
            
        Returns:
            String base64 de la imagen
        """
        try:
            response = requests.get(url)
            response.raise_for_status()
            return base64.b64encode(response.content).decode('utf-8')
        except Exception as e:
            logger.error(f"Error downloading image from URL: {e}")
            raise
    
    def _validate_response(self, response_dict: Dict) -> Optional[str]:
        """
        Valida que la respuesta del LLM cumpla con el esquema requerido.
        Returns: Un string con el error si la validación falla, None si es válida.
        """
        required_keys = [
            "ncm_completo", "ncm_desglose", "justificacion_clasificacion", 
            "regimen_simplificado_courier", "intervenciones_requeridas", "confianza"
        ]
        
        for key in required_keys:
            if key not in response_dict:
                return f"La clave requerida '{key}' no se encontró en la respuesta del LLM."

        # Validar formato del NCM (ahora más flexible)
        ncm_code = response_dict.get("ncm_completo", "")
        # Acepta formatos como: 8711.60.00, 3303.00.10, o incluso con más puntos.
        # La regla principal es que contenga dígitos y al menos un punto.
        if not re.match(r'^[\d.]+$', ncm_code) or '.' not in ncm_code:
            return f"El 'ncm_completo' ('{ncm_code}') no parece un código NCM válido. Debe contener solo dígitos y puntos."

        # Validar confianza
        if response_dict.get("confianza") not in ["Alta", "Media", "Baja"]:
            return f"El valor de 'confianza' ('{response_dict.get('confianza')}') no es válido."
            
        return None # Validación exitosa

    def _parse_llm_response(self, raw_response: str) -> Dict[str, Any]:
        """
        Parses the raw response from the LLM and returns a dictionary.
        Handles JSON parsing errors and returns an error message.
        """
        try:
            return json.loads(raw_response)
        except json.JSONDecodeError:
            return {
                "error": f"La respuesta del modelo no contenía un JSON válido. Respuesta: {raw_response}"
            }

    async def classify_product(self, description: str, image_url: Optional[str] = None) -> Dict[str, Any]:
        """
        Clasifica un producto para obtener su NCM y detalles de VUCE.
        
        Orquesta la llamada a la IA y el posterior scraping de VUCE.
        """
        # 1. Clasificar con IA para obtener NCM
        logger.info("Iniciando clasificación NCM con IA...")
        # Aquí llamamos al método síncrono que hace la llamada a la API de OpenAI
        initial_result = self.classify_product_sync(description, image_url)
        
        if initial_result.get("error"):
            logger.error(f"Error en la clasificación inicial de IA: {initial_result['error']}")
            return initial_result
        
        ncm_code = initial_result.get("ncm_completo")
        if not ncm_code:
            error_msg = "La IA no retornó un código NCM válido."
            logger.error(error_msg)
            initial_result["error"] = error_msg
            return initial_result

        # 2. Enriquecer con datos oficiales de NCM (CON REFINAMIENTO AUTOMÁTICO)
        logger.info(f"NCM obtenido: {ncm_code}. Buscando detalles en base de datos oficial...")
        try:
            from ncm_official_integration import get_ncm_info_official
            
            # Pasar la descripción del producto para refinamiento automático
            ncm_details = await get_ncm_info_official(ncm_code, description)
            
            if ncm_details.get("success"):
                was_refined = ncm_details.get("was_refined", False)
                refinement_info = ncm_details.get("refinement_info", {})
                
                # ACTUALIZAR NCM_COMPLETO CON POSICIÓN OFICIAL COMPLETA (INCLUYENDO SUFIJO SIM)
                ncm_position = ncm_details.get("posicion_encontrada", {})
                official_ncm_code = ncm_position.get('codigo', '')
                
                if official_ncm_code:
                    # Actualizar el código NCM con la posición oficial completa
                    initial_result['ncm_completo'] = official_ncm_code
                    logger.info(f"✅ NCM actualizado con posición oficial completa: {official_ncm_code}")
                
                if was_refined:
                    logger.info(f"🎯 Detalles oficiales de NCM obtenidos con REFINAMIENTO automático")
                    logger.info(f"   Original: {refinement_info.get('original_code', 'N/A')}")
                    logger.info(f"   Refinado: {official_ncm_code}")
                    logger.info(f"   Opciones evaluadas: {refinement_info.get('total_options', 'N/A')}")
                else:
                    logger.info("Detalles oficiales de NCM obtenidos exitosamente.")
                
                # Enriquecer el resultado con información oficial de base de datos NCM
                ncm_treatment = ncm_details.get("tratamiento_arancelario", {})
                ncm_regime = ncm_details.get("regimen_simplificado", {})
                ncm_interventions = ncm_details.get("intervenciones", {})
                
                # Actualizar tratamiento arancelario con datos oficiales
                initial_result['tratamiento_arancelario'] = {
                    "derechos_importacion": f"{ncm_treatment.get('aec', 0)}%",
                    "tasa_estadistica": f"{ncm_treatment.get('te', 3.0)}%",
                    "iva": f"{ncm_treatment.get('iva', 21.0)}%",
                    "iva_adicional": f"{ncm_treatment.get('iva_adicional', 0.0)}%",
                    "fuente": ncm_treatment.get('fuente', 'Base de Datos Oficial NCM')
                }
                
                # Enriquecer información de régimen simplificado con análisis oficial
                if 'regimen_simplificado_courier' in initial_result:
                    initial_result['regimen_simplificado_courier']['ncm_analysis'] = ncm_regime
                    
                    # Combinar análisis de IA con análisis oficial de NCM
                    ia_aplica = initial_result['regimen_simplificado_courier'].get('aplica', 'No')
                    ncm_aplica = ncm_regime.get('aplica_potencialmente', False)
                    
                    if ia_aplica == "Sí" and ncm_aplica:
                        final_decision = "Sí"
                    elif ia_aplica == "No" or not ncm_aplica:
                        final_decision = "No"
                    else:
                        final_decision = "Condicional"
                    
                    initial_result['regimen_simplificado_courier']['aplica_final'] = final_decision
                    initial_result['regimen_simplificado_courier']['justificacion_combinada'] = (
                        f"IA: {ia_aplica}. Base oficial: {'Sí' if ncm_aplica else 'No'}. "
                        f"Decisión final: {final_decision}. "
                        f"Factores a verificar: {', '.join(ncm_regime.get('factores_verificar', []))}"
                    )
                
                # Añadir información adicional de la base de datos oficial
                initial_result['ncm_official_info'] = {
                    "match_exacto": ncm_details.get("match_exacto", False),
                    "descripcion_oficial": ncm_position.get("descripcion", ""),
                    "fecha_actualizacion": ncm_details.get("metadata", {}).get("last_updated"),
                    "intervenciones_detectadas": ncm_interventions.get("organismos_potenciales", []),
                    "source": "Base de Datos Oficial NCM",
                    "was_refined": was_refined,
                    "refinement_info": refinement_info
                }
                
                # Enriquecer intervenciones si se detectaron organismos
                ncm_organismos = ncm_interventions.get("organismos_potenciales", [])
                if ncm_organismos:
                    if 'intervenciones_requeridas' not in initial_result:
                        initial_result['intervenciones_requeridas'] = []
                    
                    # Combinar intervenciones de IA y base oficial (sin duplicados)
                    todas_intervenciones = list(set(
                        initial_result.get('intervenciones_requeridas', []) + ncm_organismos
                    ))
                    initial_result['intervenciones_requeridas'] = todas_intervenciones
                
            else:
                logger.warning(f"No se pudieron obtener detalles oficiales de NCM: {ncm_details.get('error', 'Error desconocido')}")
                initial_result['ncm_warning'] = ncm_details.get('error', 'Error obteniendo datos oficiales de NCM')
                
        except Exception as e:
            logger.error(f"Error al consultar base de datos oficial de NCM: {str(e)}")
            initial_result['ncm_warning'] = f"Error al consultar base de datos oficial: {str(e)}"

        return initial_result

    def classify_product_sync(
        self, 
        description: str, 
        image_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Clasifica un producto usando GPT-4o-mini de forma síncrona.
        
        Args:
            description: Descripción del producto
            image_url: URL de la imagen (opcional)
            
        Returns:
            Dict con la clasificación NCM/HS
        """
        try:
            logger.info(f"Classifying product: {description[:100]}...")
            
            # Preparar la imagen
            image_data = None
            image_source = None
            image_processing_info = {"has_image": False, "source": None, "size_estimate": None}
            
            if image_url:
                logger.info(f"Processing image from URL: {image_url[:100]}...")
                try:
                    image_data = self.download_image_from_url(image_url)
                    image_source = f"url: {image_url}"
                    image_processing_info.update({
                        "has_image": True, 
                        "source": "url",
                        "url": image_url,
                        "url_preview": image_url[:100] + "..." if len(image_url) > 100 else image_url
                    })
                except Exception as img_error:
                    logger.warning(f"Failed to download image from URL: {img_error}")
                    image_processing_info.update({
                        "has_image": False,
                        "source": "url_failed",
                        "error": str(img_error)
                    })
                    
            # Crear el mensaje con el nuevo prompt revisado
            messages = [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT_V2_REVISED
                }
            ]
            
            # Contenido del mensaje del usuario
            user_content = [{"type": "text", "text": f"Por favor, clasifica el siguiente producto:\n\n**Descripción:**\n{description}"}]
            
            if image_data:
                user_content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_data}"
                    }
                })

            messages.append({"role": "user", "content": user_content})

            # --- Logging para Debug ---
            # No loguear la imagen completa en base64 para no llenar la consola
            log_request = {
                "model": "gpt-4o-mini",
                "prompt_text": description,
                "has_image": bool(image_data),
                "system_prompt_version": "v2"
            }
            logger.info(f"Enviando solicitud a OpenAI... Request: {json.dumps(log_request, indent=2)}")
            
            try:
                response = self.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages,
                    temperature=0,
                    response_format={"type": "json_object"}
                )
                
                response_text = response.choices[0].message.content
                logger.info(f"Respuesta cruda recibida de OpenAI: {response_text}")
                
                # Parsear y validar la respuesta
                try:
                    result_dict = json.loads(response_text)
                    validation_error = self._validate_response(result_dict)
                    
                    if validation_error:
                        logger.error(f"Error de validación en la respuesta del LLM: {validation_error}")
                        result_dict['error'] = f"Validación fallida: {validation_error}"
                        result_dict['classification_method'] = "llm_text_only" if not image_data else "llm_with_image"
                        result_dict['raw_response'] = response_text # Guardar la respuesta cruda para debug
                        return result_dict
                    
                    logger.info("La respuesta del LLM pasó la validación.")
                    
                except json.JSONDecodeError:
                    error_msg = "La respuesta del LLM no es un JSON válido."
                    logger.error(error_msg)
                    return {"error": error_msg, "raw_response": response_text}

                # Añadir información de la ejecución para debug
                result_dict['classification_method'] = "llm_text_only" if not image_data else "llm_with_image"
                result_dict['response_info'] = {
                    'model_used': response.model,
                    'tokens_used': response.usage.total_tokens,
                    'raw_response': response_text
                }
                
                return result_dict

            except Exception as e:
                logger.error(f"Ocurrió un error durante la llamada a la API de OpenAI: {e}")
                return {"error": str(e), "traceback": traceback.format_exc()}
            
        except Exception as e:
            logger.error(f"Error in product classification: {e}")
            return {
                "error": str(e),
                "error_type": "general_error",
                "timestamp": datetime.now().isoformat(),
                "image_processing_info": image_processing_info if 'image_processing_info' in locals() else {},
                "description": description
            }
    
    def classify_multiple_products(self, products: List[Dict]) -> List[Dict]:
        """
        Clasificar múltiples productos
        
        Args:
            products: Lista de productos con 'description' y opcionalmente 'image_path', 'image_url', 'image_base64'
            
        Returns:
            Lista de clasificaciones
        """
        results = []
        
        for i, product in enumerate(products, 1):
            logger.info(f"Processing product {i}/{len(products)}")
            
            description = product.get('description', '')
            image_path = product.get('image_path')
            image_url = product.get('image_url')
            image_base64 = product.get('image_base64')
            
            result = self.classify_product(
                description=description,
                image_url=image_url
            )
            
            result['product_id'] = i
            results.append(result)
        
        return results
    
    def save_results(self, results: Union[Dict, List[Dict]], filename: str = None) -> str:
        """
        Guardar resultados en archivo JSON
        
        Args:
            results: Resultado(s) de clasificación
            filename: Nombre del archivo (opcional)
            
        Returns:
            Nombre del archivo guardado
        """
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"ncm_classification_{timestamp}.json"
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Results saved to: {filename}")
            return filename
            
        except Exception as e:
            logger.error(f"Error saving results: {e}")
            raise


def classify_single_product(
    description: str,
    image_path: str = None,
    image_url: str = None,
    image_base64: str = None,
    api_key: str = None
) -> Dict:
    """
    Función de conveniencia para clasificar un solo producto
    
    Args:
        description: Descripción del producto
        image_path: Ruta local a la imagen (opcional)
        image_url: URL de la imagen (opcional)
        image_base64: Imagen en base64 (opcional)
        api_key: API key de OpenAI (opcional)
        
    Returns:
        Dict con la clasificación
    """
    try:
        classifier = AINcmClassifier(api_key=api_key)
        return classifier.classify_product(
            description=description,
            image_url=image_url
        )
    except (ImportError, ValueError) as e:
        logger.error(f"Error de inicialización del clasificador: {e}")
        return {"error": str(e)}


async def test_classifier():
    """Función de test para el clasificador NCM con un ejemplo real."""
    print("🚀 Iniciando test del clasificador NCM (v2)...")
    
    # Ejemplo 1: Perfume (requiere ANMAT)
    test_product = {
        "description": "Perfume para hombre, fragancia amaderada y especiada, 100ml. Presentado en caja de lujo. Marca: 'Elegance'. Origen: Francia.",
        "image_url": "https://i.ebayimg.com/images/g/sVIAAOSw94VlNa~y/s-l1600.jpg" # URL de una imagen real
    }
    
    print(f"\n--- Test 1: {test_product['description'][:50]}... ---")
    
    # Usar el clasificador
    result = await classify_single_product(
        description=test_product["description"],
        image_url=test_product["image_url"]
    )
    
    # Mostrar resultados de forma legible
    print("\n--- Resultados del Test ---")
    if "error" in result:
        print(f"❌ ERROR: {result['error']}")
        if 'raw_response' in result:
            print(f"📄 Respuesta cruda del LLM:\n{result['raw_response']}")
    else:
        print(f"✅ Clasificación exitosa:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        # Validar NCM
        ncm = result.get("ncm_completo")
        print(f"\n🔍 NCM Obtenido: {ncm}")
        if re.match(r'^\d{8}\.\d{2}\.\d{1}$', ncm):
            print("   -> Formato Válido (XXXXXXXX.XX.X)")
        else:
            print("   -> ❌ FORMATO INVÁLIDO")

    print("\n✅ Test del clasificador finalizado.")


async def main():
    """Función principal para demostración"""
    print("🤖 AI NCM CLASSIFIER")
    print("=" * 30)
    
    # Ejecutar tests
    await test_classifier()
    
    if success:
        print("\n🎉 Tests completed successfully!")
        print("💡 Ready for production use")
        print("\nUsage examples:")
        print("result = classify_single_product('Laptop i5 8GB RAM')")
        print("result = classify_single_product('Smartphone', image_path='phone.jpg')")
    else:
        print("\n❌ Tests failed")
        print("🔧 Check OpenAI installation and API key")


if __name__ == "__main__":
    # La función de prueba ahora debe ser ejecutada con asyncio
    asyncio.run(main()) 