#!/usr/bin/env python3
"""
🔧 Debug Script - Landed Cost Calculator
========================================

Script para testear el flujo completo de cálculo de landed cost
sin Streamlit y con debug extensivo.
"""

import json
import traceback
from datetime import datetime
from typing import Dict, Any, Optional
import sys
import os
import requests
from urllib.parse import urlparse
import re

# Imports locales
from alibaba_scraper import scrape_single_alibaba_product, extract_alibaba_pricing, format_pricing_for_display
from ai_ncm_classifier import AINcmClassifier
from import_tax_calculator import calcular_impuestos_importacion
from shipments_integrations.easypost_quotes import EasyPostQuoteService, create_sample_customs_info
from product_dimension_estimator import ProductShippingEstimator

# Import del gestor de secrets
from secrets_config import get_api_keys_dict, validate_setup, get_secrets_manager

# Cargar configuración centralizada
API_KEYS = get_api_keys_dict()

# Validar configuración
if not validate_setup():
    print("⚠️ Advertencia: Algunas API keys no están configuradas")
    secrets_manager = get_secrets_manager()
    print(secrets_manager.status_report())

def create_enhanced_description(product):
    """
    Crear descripción mejorada para clasificación NCM
    
    Args:
        product: Producto extraído de Alibaba
        
    Returns:
        String con descripción mejorada
    """
    description_parts = [product.title]
    
    # Agregar categorías si están disponibles
    if product.categories:
        description_parts.append(f"Categorías: {', '.join(product.categories)}")
    
    # Agregar origen si está disponible
    if product.place_of_origin:
        description_parts.append(f"Origen: {product.place_of_origin}")
        
    # Agregar marca si está disponible
    if hasattr(product, 'brand_name') and product.brand_name:
        description_parts.append(f"Marca: {product.brand_name}")
        
    # Agregar rango de precios para contexto
    if product.price_low > 0 and product.price_high > 0:
        description_parts.append(f"Rango de precio: ${product.price_low} - ${product.price_high}")
        
    # Agregar MOQ para contexto comercial
    if product.moq:
        description_parts.append(f"MOQ: {product.moq}")
        
    # Agregar propiedades relevantes si están disponibles
    if hasattr(product, 'properties') and product.properties:
        relevant_props = []
        for key, value in product.properties.items():
            # Filtrar propiedades relevantes para clasificación
            key_lower = key.lower()
            if any(term in key_lower for term in ['material', 'size', 'weight', 'color', 'type', 'model', 'specification', 'feature', 'capacity', 'function']):
                relevant_props.append(f"{key}: {value}")
        
        if relevant_props:
            description_parts.append(f"Propiedades: {'; '.join(relevant_props[:5])}")  # Limitar a 5 propiedades
    
    # Combinar toda la descripción
    enhanced_description = " | ".join(description_parts)
    
    return enhanced_description

def validate_and_select_best_image(images_list, logger=None):
    """
    Valida y selecciona la mejor imagen de una lista para clasificación NCM
    
    Args:
        images_list: Lista de URLs de imágenes
        logger: Logger opcional para debug
        
    Returns:
        Dict con información de la imagen seleccionada
    """
    if not images_list:
        return {
            "selected_url": None,
            "method": "no_images_available",
            "score": 0,
            "validation_results": []
        }
    
    validation_results = []
    best_image = None
    best_score = -1
    
    # Analizar cada imagen (máximo 5 para eficiencia)
    for idx, img_url in enumerate(images_list[:5]):
        if not img_url:
            continue
            
        result = {
            "index": idx,
            "url": img_url,
            "url_preview": img_url[:80] + "..." if len(img_url) > 80 else img_url,
            "score": 0,
            "reasons": []
        }
        
        try:
            # Análisis de URL
            parsed_url = urlparse(img_url)
            url_lower = img_url.lower()
            
            # Score base por posición (primeras imágenes suelen ser mejores)
            if idx == 0:
                result["score"] += 15
                result["reasons"].append("primera_imagen")
            elif idx == 1:
                result["score"] += 10
                result["reasons"].append("segunda_imagen")
            elif idx == 2:
                result["score"] += 5
                result["reasons"].append("tercera_imagen")
            
            # Penalizar thumbnails y imágenes pequeñas
            if any(term in url_lower for term in ['thumb', 'small', 'tiny', 'mini']):
                result["score"] -= 15
                result["reasons"].append("thumbnail_detected")
            
            # Premiar imágenes grandes y de calidad
            if any(term in url_lower for term in ['big', 'large', 'huge', 'full']):
                result["score"] += 20
                result["reasons"].append("large_image")
            
            if any(term in url_lower for term in ['main', 'primary', 'hero', 'featured']):
                result["score"] += 25
                result["reasons"].append("main_image")
            
            if any(term in url_lower for term in ['hd', 'quality', 'detail']):
                result["score"] += 10
                result["reasons"].append("quality_indicator")
            
            # Formato de archivo
            if '.jpg' in url_lower or '.jpeg' in url_lower:
                result["score"] += 5
                result["reasons"].append("jpeg_format")
            elif '.png' in url_lower:
                result["score"] += 3
                result["reasons"].append("png_format")
            elif '.webp' in url_lower:
                result["score"] += 2
                result["reasons"].append("webp_format")
            
            # Verificar si la URL parece válida
            if parsed_url.scheme in ['http', 'https'] and parsed_url.netloc:
                result["score"] += 5
                result["reasons"].append("valid_url_structure")
            else:
                result["score"] -= 10
                result["reasons"].append("invalid_url_structure")
            
            # Verificar accesibilidad de la imagen (con timeout corto)
            try:
                response = requests.head(img_url, timeout=3)
                if response.status_code == 200:
                    result["score"] += 10
                    result["reasons"].append("accessible")
                    
                    # Verificar Content-Type si está disponible
                    content_type = response.headers.get('content-type', '').lower()
                    if 'image' in content_type:
                        result["score"] += 5
                        result["reasons"].append("valid_content_type")
                        
                        # Premiar ciertos tipos de imagen
                        if 'jpeg' in content_type:
                            result["score"] += 3
                        elif 'png' in content_type:
                            result["score"] += 2
                else:
                    result["score"] -= 20
                    result["reasons"].append(f"http_error_{response.status_code}")
                    
            except requests.exceptions.RequestException as e:
                result["score"] -= 10
                result["reasons"].append(f"connection_error")
                if logger:
                    logger.log("IMAGE_VALIDATION", f"Error validando imagen {idx}: {str(e)}", success=False)
            
            # Detectar posibles imágenes de logo o watermark
            if any(term in url_lower for term in ['logo', 'watermark', 'brand', 'stamp']):
                result["score"] -= 5
                result["reasons"].append("possible_logo")
            
        except Exception as e:
            result["score"] = -100
            result["reasons"] = [f"validation_error: {str(e)}"]
            if logger:
                logger.log("IMAGE_VALIDATION", f"Error crítico validando imagen {idx}: {str(e)}", success=False)
        
        validation_results.append(result)
        
        # Actualizar mejor imagen si este score es mayor
        if result["score"] > best_score:
            best_score = result["score"]
            best_image = result
    
    # Determinar método de selección
    if not best_image:
        method = "no_valid_images"
        selected_url = None
    elif len(images_list) == 1:
        method = "single_image"
        selected_url = best_image["url"]
    else:
        method = f"best_of_{len(validation_results)}_score_{best_score}"
        selected_url = best_image["url"]
    
    # Log detallado si tenemos logger
    if logger:
        logger.log("IMAGE_SELECTION", "Análisis de imágenes completado", {
            "total_images": len(images_list),
            "analyzed_images": len(validation_results),
            "best_score": best_score,
            "method": method,
            "selected_index": best_image["index"] if best_image else None
        })
        
        # Log de cada imagen analizada
        for result in validation_results:
            logger.log("IMAGE_ANALYSIS", f"Imagen {result['index']}: Score {result['score']}", {
                "url_preview": result["url_preview"],
                "reasons": result["reasons"]
            })
    
    return {
        "selected_url": selected_url,
        "method": method,
        "score": best_score,
        "best_image_info": best_image,
        "validation_results": validation_results,
        "total_analyzed": len(validation_results)
    }

class DebugLogger:
    """Logger para debug extensivo"""
    
    def __init__(self):
        self.logs = []
        self.start_time = datetime.now()
        
    def log(self, step: str, message: str, data: Any = None, success: bool = True):
        """Log un paso del proceso"""
        timestamp = datetime.now()
        elapsed = (timestamp - self.start_time).total_seconds()
        
        log_entry = {
            "timestamp": timestamp.isoformat(),
            "elapsed_seconds": elapsed,
            "step": step,
            "message": message,
            "success": success,
            "data": data
        }
        
        self.logs.append(log_entry)
        
        # Print inmediato
        status = "✅" if success else "❌"
        print(f"{status} [{elapsed:.2f}s] {step}: {message}")
        
        if data and isinstance(data, dict):
            for key, value in data.items():
                print(f"   📊 {key}: {value}")
        
    def save_logs(self, filename: str = None):
        """Guardar logs en archivo JSON"""
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"debug_logs_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.logs, f, indent=2, ensure_ascii=False)
        
        print(f"📄 Logs guardados en: {filename}")
        return filename

def test_landed_cost_flow():
    """Función principal para testear el flujo completo"""
    logger = DebugLogger()
    
    print("🚀 Iniciando test del flujo completo de Landed Cost")
    print("=" * 60)
    
    try:
        # Configuración de test
        test_config = {
            "url": "https://www.alibaba.com/product-detail/Wholesale-Cologne-Perfume-Original-Men-s_1601360468060.html",
            "tipo_importador": "no_inscripto",  # Valores válidos: responsable_inscripto, no_inscripto, monotributista
            "destino_importacion": "uso_propio",  # Valores válidos: reventa, uso_propio, bien_capital
            "provincia": "CABA",
            "peso_estimado": 2.5,  # kg
            "tipo_dolar": "oficial"
        }
        
        logger.log("SETUP", "Configuración de test", test_config)
        
        # Resultado final
        result = {}
        
        # PASO 1: Scraping de Alibaba
        logger.log("STEP_1", "Iniciando scraping de Alibaba", {"url": test_config["url"]})
        
        try:
            product = scrape_single_alibaba_product(test_config["url"], API_KEYS["APIFY_API_KEY"])
            
            if not product:
                logger.log("STEP_1", "No se pudo obtener información del producto", success=False)
                return None
                
            result['producto'] = product
            
            # Debug del producto
            product_debug = {
                "title": product.title,
                "price_low": product.price_low,
                "price_high": product.price_high,
                "moq": product.moq,
                "place_of_origin": product.place_of_origin,
                "categories": product.categories,
                "images_count": len(product.images)
            }
            
            logger.log("STEP_1", "Producto extraído exitosamente", product_debug)
            
            # Extraer información de precios mejorada
            product_data = {
                'price': {
                    'productRangePrices': {
                        'dollarPriceRangeLow': product.price_low,
                        'dollarPriceRangeHigh': product.price_high
                    },
                    'unit': 'piece'
                },
                'moq': product.moq,
                'sku': getattr(product, 'sku_info', {}) if hasattr(product, 'sku_info') else {}
            }
            
            # Extraer precios con el nuevo módulo
            pricing_info = extract_alibaba_pricing(product_data, verbose=True)
            pricing_display = format_pricing_for_display(pricing_info)
            
            # Seleccionar precio (usar el más económico como default)
            if pricing_info.price_options:
                cheapest_option = pricing_info.get_cheapest_option()
                precio_promedio = float(cheapest_option.price)
                selected_variation = cheapest_option.variation_description
            else:
                # Fallback al cálculo tradicional
                precio_promedio = (product.price_low + product.price_high) / 2
                selected_variation = "Precio promedio"
            
            # Si no hay precios válidos, usar estimación
            if precio_promedio <= 0:
                logger.log("STEP_1", "Precio no disponible, usando estimación", {"precio_original": precio_promedio}, success=False)
                # Usar estimación basada en el tipo de producto
                if "perfume" in product.title.lower() or "cologne" in product.title.lower():
                    precio_promedio = 15.0  # USD estimado para perfumes
                else:
                    precio_promedio = 25.0  # USD estimado genérico
                logger.log("STEP_1", "Precio estimado asignado", {"precio_estimado": precio_promedio})
                selected_variation = "Precio estimado"
            
            result['precio_promedio'] = precio_promedio
            result['pricing_info'] = pricing_info
            result['pricing_display'] = pricing_display
            result['selected_variation'] = selected_variation
            
            logger.log("STEP_1", "Información de precios extraída y procesada", {
                "precio_seleccionado": precio_promedio,
                "variacion_seleccionada": selected_variation,
                "has_multiple_prices": pricing_info.has_multiple_prices,
                "total_options": len(pricing_info.price_options),
                "price_difference_pct": pricing_info.price_difference_pct if pricing_info.has_multiple_prices else 0,
                "moq": pricing_info.moq
            })
            
        except Exception as e:
            logger.log("STEP_1", f"Error en scraping: {str(e)}", {"error": str(e)}, success=False)
            raise
        
        # PASO 1.5: Estimar Dimensiones y Peso
        logger.log("STEP_1.5", "Iniciando estimación de dimensiones y peso")
        shipping_details = {}
        try:
            estimator = ProductShippingEstimator()
            # The estimator expects a dictionary with the raw product data structure
            # We need to construct it from the 'product' object
            product_dict_for_estimator = product.raw_data if hasattr(product, 'raw_data') else {}

            if not product_dict_for_estimator:
                 logger.log("STEP_1.5", "No raw_data found on product object, reconstructing dict.", success=False)
                 product_dict_for_estimator = {
                    'subject': product.title,
                    'categories': product.categories,
                    'mediaItems': [{'type': 'image', 'imageUrl': {'big': url}} for url in product.images],
                    'productHtmlDescription': getattr(product, 'html_description', ''),
                    'productBasicProperties': getattr(product, 'properties_list', [])
                }
            
            shipping_details = estimator.get_shipping_details(product_dict_for_estimator)
            result['shipping_details'] = shipping_details
            
            logger.log("STEP_1.5", "Estimación de envío completada", shipping_details)

        except Exception as e:
            logger.log("STEP_1.5", f"Error en estimación de envío: {str(e)}", {"error": str(e)}, success=False)
            # Fallback to default values
            shipping_details = {"method": "failed_fallback", "weight_kg": 1.0, "dimensions_cm": {"length": 20, "width": 20, "height": 10}}
            result['shipping_details'] = shipping_details

        # PASO 2: Clasificación NCM
        logger.log("STEP_2", "Iniciando clasificación NCM (v2)")
        
        try:
            # Crear descripción mejorada para clasificar
            description = create_enhanced_description(product)
            
            logger.log("STEP_2", "Descripción mejorada generada", {
                "description_length": len(description),
                "components": len(description.split(" | "))
            })
            
            # Seleccionar la mejor imagen disponible
            selected_image_info = validate_and_select_best_image(product.images, logger)
            
            logger.log("STEP_2", "Imagen seleccionada para análisis", {
                "has_image": selected_image_info["selected_url"] is not None,
                "selection_method": selected_image_info["method"],
            })
            
            # Usar el clasificador con la nueva lógica
            classifier = AINcmClassifier(API_KEYS.get("OPENAI_API_KEY"))
            ncm_result = classifier.classify_product(
                description=description,
                image_url=selected_image_info["selected_url"]
            )
            result['ncm_result'] = ncm_result
            
            # Logueo de depuración mejorado
            if "error" in ncm_result:
                logger.log("STEP_2", f"Error en clasificación NCM: {ncm_result['error']}", ncm_result, success=False)
                if 'raw_response' in ncm_result:
                    print("\n--- RAW LLM RESPONSE (FAILURE) ---")
                    print(ncm_result['raw_response'])
                    print("-------------------------------------\n")
                # Detener el flujo si la clasificación falla, ya que es crítico
                raise Exception("La clasificación NCM falló. No se puede continuar.")
            else:
                ncm_debug = {
                    "ncm_completo": ncm_result.get('ncm_completo'),
                    "confianza": ncm_result.get('confianza'),
                    "metodo": ncm_result.get('classification_method'),
                    "justificacion": ncm_result.get('justificacion_clasificacion', '')[:100] + "...",
                    "intervenciones": ncm_result.get('intervenciones_requeridas', [])
                }
                logger.log("STEP_2", "Clasificación NCM completada", ncm_debug)

        except Exception as e:
            logger.log("STEP_2", f"Excepción fatal en clasificación NCM: {str(e)}", {"traceback": traceback.format_exc()}, success=False)
            raise
        
        # PASO 3: Cálculo de impuestos
        logger.log("STEP_3", "Iniciando cálculo de impuestos")
        
        try:
            tax_result = calcular_impuestos_importacion(
                cif_value=precio_promedio,
                tipo_importador=test_config["tipo_importador"],
                destino=test_config["destino_importacion"],
                origen="extrazona",
                tipo_dolar=test_config["tipo_dolar"],
                provincia=test_config["provincia"]
            )
            
            result['tax_result'] = tax_result
            
            tax_debug = {
                "total_impuestos": float(tax_result.total_impuestos),
                "costo_total": float(tax_result.costo_total),
                "incidencia_porcentual": float(tax_result.incidencia_porcentual),
                "impuestos_aplicados": len([imp for imp in tax_result.impuestos if imp.aplica])
            }
            
            logger.log("STEP_3", "Cálculo de impuestos completado", tax_debug)
            
        except Exception as e:
            logger.log("STEP_3", f"Error en cálculo de impuestos: {str(e)}", {"error": str(e)}, success=False)
            raise
        
        # PASO 4: Cálculo de flete
        logger.log("STEP_4", "Iniciando cálculo de flete")
        
        try:
            # Dimensiones del paquete - AHORA USAMOS LAS ESTIMADAS
            estimated_weight_kg = test_config["peso_estimado"] # Fallback
            if shipping_details.get('weight_kg'):
                estimated_weight_kg = shipping_details['weight_kg']
            elif shipping_details.get('weight'): # from extraction
                # Extract numeric value from string like "1.5kg"
                match = re.search(r'(\d+(?:\.\d+)?)', shipping_details['weight'])
                if match:
                    estimated_weight_kg = float(match.group(1))

            package_dimensions = {
                "length": shipping_details.get("dimensions_cm", {}).get("length", 30.0),
                "width": shipping_details.get("dimensions_cm", {}).get("width", 25.0),
                "height": shipping_details.get("dimensions_cm", {}).get("height", 20.0),
                "weight": estimated_weight_kg * 1000  # convertir a gramos
            }
            logger.log("STEP_4", "Usando dimensiones de paquete estimadas", package_dimensions)

            # Información de aduanas
            customs_info = create_sample_customs_info()
            customs_info["customs_items"][0]["value"] = precio_promedio
            customs_info["customs_items"][0]["weight"] = estimated_weight_kg * 1000
            customs_info["customs_items"][0]["description"] = product.title[:50]
            
            # Calcular flete
            shipping_calc = EasyPostQuoteService(API_KEYS["EASYPOST_API_KEY"])
            shipping_result = shipping_calc.get_shipping_quotes(
                from_address=from_address,
                to_address=to_address,
                parcel=package_dimensions,
                customs_info=customs_info
            )
            
            # Logueo mejorado de resultado de flete
            shipping_quotes = []
            if shipping_result.get('success'):
                shipping_quotes = shipping_result.get('quotes', [])
                logger.log("STEP_4", f"Llamada a EasyPost exitosa. Se encontraron {len(shipping_quotes)} cotizaciones.", shipping_result, success=True)
                
                if shipping_quotes:
                    # Log top 3
                    logger.log("STEP_4", "Top 3 cotizaciones de flete:", {
                        f"Opción {i+1}": f"${q['cost_usd']:.2f} USD - {q['carrier']} {q['service']} ({q.get('delivery_days', 'N/D')} días)" 
                        for i, q in enumerate(shipping_quotes[:3])
                    })
            else:
                logger.log("STEP_4", "Llamada a EasyPost falló.", shipping_result, success=False)

            result['shipping_quotes'] = shipping_quotes
            result['shipping_api_result'] = shipping_result
            
            # Tomar el flete más barato
            if shipping_quotes:
                flete_costo = min(q['cost_usd'] for q in shipping_quotes)
            else:
                flete_costo = result['precio_promedio'] * 0.15  # 15% como estimación
            
            result['flete_costo'] = flete_costo
            
            flete_debug = {
                "origin_country": origin_country,
                "api_call_successful": shipping_result.get('success'),
                "shipping_quotes_count": len(shipping_quotes),
                "flete_costo_seleccionado": flete_costo,
                "usando_estimacion": not bool(shipping_quotes)
            }
            
            logger.log("STEP_4", "Cálculo de flete completado", flete_debug)
            
        except Exception as e:
            logger.log("STEP_4", f"Error en cálculo de flete: {str(e)}", {"error": str(e)}, success=False)
            
            # Usar estimación de flete
            flete_costo = result['precio_promedio'] * 0.15
            result['flete_costo'] = flete_costo
            result['shipping_quotes'] = []
            
            logger.log("STEP_4", "Usando estimación de flete", {"flete_estimado": flete_costo})
        
        # PASO 5: Cálculo de Landed Cost
        logger.log("STEP_5", "Calculando Landed Cost final")
        
        try:
            landed_cost = precio_promedio + float(tax_result.total_impuestos) + result['flete_costo']
            result['landed_cost'] = landed_cost
            
            # Análisis de rentabilidad
            incidencia_impuestos = (float(tax_result.total_impuestos) / precio_promedio) * 100
            incidencia_flete = (result['flete_costo'] / precio_promedio) * 100
            markup_total = ((landed_cost - precio_promedio) / precio_promedio) * 100
            
            landed_cost_debug = {
                "precio_producto": precio_promedio,
                "total_impuestos": float(tax_result.total_impuestos),
                "flete_costo": result['flete_costo'],
                "landed_cost": landed_cost,
                "incidencia_impuestos": incidencia_impuestos,
                "incidencia_flete": incidencia_flete,
                "markup_total": markup_total
            }
            
            logger.log("STEP_5", "Landed Cost calculado exitosamente", landed_cost_debug)
            
        except Exception as e:
            logger.log("STEP_5", f"Error en cálculo de Landed Cost: {str(e)}", {"error": str(e)}, success=False)
            raise
        
        # PASO 6: Resumen final
        logger.log("FINAL", "Proceso completado exitosamente")
        
        print("\n" + "=" * 60)
        print("📊 RESUMEN FINAL")
        print("=" * 60)
        print(f"🏷️  Producto: {product.title}")
        print(f"💰 Precio seleccionado: ${precio_promedio:.2f}")
        print(f"🎯 Variación: {result['selected_variation']}")
        if result['pricing_info'].has_multiple_prices:
            print(f"📊 Opciones de precio: {len(result['pricing_info'].price_options)}")
            print(f"💡 Diferencia de precios: {result['pricing_info'].price_difference_pct:.1f}%")
            cheapest = result['pricing_info'].get_cheapest_option()
            most_expensive = result['pricing_info'].get_most_expensive_option()
            print(f"   └ Más barato: ${cheapest.price:.2f} ({cheapest.variation_description})")
            print(f"   └ Más caro: ${most_expensive.price:.2f} ({most_expensive.variation_description})")
        print(f"📦 MOQ: {result['pricing_info'].moq} {result['pricing_info'].unit}")
        print(f"💸 Total impuestos: ${float(tax_result.total_impuestos):.2f}")
        print(f"🚚 Flete: ${result['flete_costo']:.2f}")
        if result['shipping_quotes']:
            print("   └ Opciones de flete (Top 3):")
            for i, q in enumerate(result['shipping_quotes'][:3]):
                print(f"     {i+1}. ${q['cost_usd']:.2f} - {q['carrier']} {q['service']} ({q.get('delivery_days', 'N/D')} días)")
        else:
            print("   └ (Flete estimado, no se encontraron cotizaciones reales)")
        print(f"🎯 LANDED COST: ${landed_cost:.2f}")
        print(f"📈 Markup total: {markup_total:.1f}%")
        print("=" * 60)
        
        # Guardar resultado completo
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        result_filename = f"landed_cost_result_{timestamp}.json"
        
        # Convertir objetos a diccionarios para JSON
        result_for_json = {
            "timestamp": datetime.now().isoformat(),
            "config": test_config,
            "producto": {
                "title": product.title,
                "price_low": product.price_low,
                "price_high": product.price_high,
                "moq": product.moq,
                "place_of_origin": product.place_of_origin,
                "categories": product.categories,
                "url": product.url
            },
            "precio_promedio": precio_promedio,
            "ncm_result": ncm_result,
            "tax_result": {
                "total_impuestos": float(tax_result.total_impuestos),
                "costo_total": float(tax_result.costo_total),
                "incidencia_porcentual": float(tax_result.incidencia_porcentual),
                "impuestos": [
                    {
                        "nombre": imp.nombre,
                        "alicuota": float(imp.alicuota),
                        "monto": float(imp.monto),
                        "aplica": imp.aplica,
                        "observaciones": imp.observaciones
                    }
                    for imp in tax_result.impuestos
                ]
            },
            "flete_costo": result['flete_costo'],
            "shipping_quotes": result['shipping_quotes'],
            "shipping_api_result": result['shipping_api_result'],
            "landed_cost": landed_cost,
            "analisis": {
                "incidencia_impuestos": incidencia_impuestos,
                "incidencia_flete": incidencia_flete,
                "markup_total": markup_total
            }
        }
        
        with open(result_filename, 'w', encoding='utf-8') as f:
            json.dump(result_for_json, f, indent=2, ensure_ascii=False)
        
        logger.log("SAVE", f"Resultado guardado en {result_filename}")
        
        # Guardar logs
        logs_filename = logger.save_logs()
        
        print(f"\n📁 Archivos generados:")
        print(f"   📊 Resultado: {result_filename}")
        print(f"   📄 Logs: {logs_filename}")
        
        return result
        
    except Exception as e:
        logger.log("ERROR", f"Error fatal en el flujo: {str(e)}", {"traceback": traceback.format_exc()}, success=False)
        logger.save_logs()
        raise

if __name__ == "__main__":
    print("🔧 Debug Script - Landed Cost Calculator")
    print("========================================")
    
    try:
        result = test_landed_cost_flow()
        print("✅ Test completado exitosamente!")
        
    except Exception as e:
        print(f"❌ Test falló: {str(e)}")
        traceback.print_exc()
        sys.exit(1) 