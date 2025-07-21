
import asyncio
import os
import json
import traceback
from urllib.parse import urlparse
import re
import requests
from decimal import Decimal

# -- Colores para la consola --
class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def log_step(message):
    print(f"{bcolors.BOLD}{bcolors.OKBLUE}➡️  {message}{bcolors.ENDC}")

def log_success(message):
    print(f"{bcolors.OKGREEN}✅ {message}{bcolors.ENDC}")

def log_warning(message):
    print(f"{bcolors.WARNING}⚠️  {message}{bcolors.ENDC}")

def log_error(message, details=""):
    print(f"{bcolors.FAIL}❌ {message}{bcolors.ENDC}")
    if details:
        print(details)

def log_info(message):
    print(f"{bcolors.OKCYAN}ℹ️  {message}{bcolors.ENDC}")


# --- Headless versions of Streamlit-dependent functions ---

def create_enhanced_description_headless(product):
    """
    Copia de create_enhanced_description pero sin dependencias de Streamlit.
    Usa el logger de este script en su lugar.
    """
    description_parts = [product.title]
    
    if product.categories:
        description_parts.append(f"Categorías: {', '.join(product.categories)}")
    if product.place_of_origin:
        description_parts.append(f"Origen: {product.place_of_origin}")
    if hasattr(product, 'brand_name') and product.brand_name:
        description_parts.append(f"Marca: {product.brand_name}")
    if product.price_low > 0 and product.price_high > 0:
        description_parts.append(f"Rango de precio: ${product.price_low} - ${product.price_high}")
    if product.moq:
        description_parts.append(f"MOQ: {product.moq}")
    if hasattr(product, 'properties') and product.properties:
        relevant_props = []
        for key, value in product.properties.items():
            key_lower = key.lower()
            if any(term in key_lower for term in ['material', 'size', 'weight', 'color', 'type', 'model', 'specification', 'feature', 'capacity', 'function']):
                relevant_props.append(f"{key}: {value}")
        if relevant_props:
            description_parts.append(f"Propiedades: {'; '.join(relevant_props[:5])}")
    
    enhanced_description = " | ".join(description_parts)
    log_success("Descripción mejorada generada (headless)")
    return enhanced_description

def validate_and_select_best_image_headless(images_list):
    """
    Copia de validate_and_select_best_image pero sin dependencias de Streamlit.
    Usa el logger de este script y la librería requests.
    """
    if not images_list:
        log_warning("No hay imágenes disponibles para validar.")
        return {"selected_url": None}

    validation_results = []
    best_image = None
    best_score = -1
    
    log_info(f"Iniciando validación de {len(images_list)} imágenes (headless)...")
    
    for idx, img_url in enumerate(images_list[:5]):
        if not img_url:
            continue
            
        result = {"index": idx, "url": img_url, "score": 0, "reasons": []}
        
        try:
            # Lógica de puntuación simplificada para brevedad
            if idx == 0: result["score"] += 15
            if any(term in img_url.lower() for term in ['big', 'large', 'main']): result["score"] += 20
            
            # Verificar accesibilidad
            try:
                response = requests.head(img_url, timeout=2)
                if response.status_code == 200 and 'image' in response.headers.get('content-type', ''):
                    result["score"] += 15
                else:
                    result["score"] -= 20
            except requests.exceptions.RequestException:
                result["score"] -= 10
                
        except Exception as e:
            result["score"] = -100
            log_error(f"Error validando imagen {idx}: {str(e)}")
        
        validation_results.append(result)
        if result["score"] > best_score:
            best_score = result["score"]
            best_image = result
    
    selected_url = best_image["url"] if best_image else (images_list[0] if images_list else None)
    log_success("Validación de imágenes completada (headless).")
    
    return {"selected_url": selected_url}


# --- Cargar configuración y módulos ---
try:
    from secrets_config import get_api_keys_dict
    API_KEYS = get_api_keys_dict()

    os.environ['OPENAI_API_KEY'] = API_KEYS.get("OPENAI_API_KEY", "")
    os.environ['EASYPOST_API_KEY'] = API_KEYS.get("EASYPOST_API_KEY", "")

    from alibaba_scraper import scrape_single_alibaba_product, get_cheapest_price_option
    from ai_ncm_classifier import AINcmClassifier
    from import_tax_calculator import calcular_impuestos_importacion
    from product_dimension_estimator import ProductShippingEstimator
    # Ya no importamos las funciones con dependencias de Streamlit

    log_success("Módulos y configuración cargados correctamente.")
except ImportError as e:
    log_error(f"No se pudo importar un módulo necesario: {e}", "Asegúrate de que todos los archivos .py estén en el mismo directorio y que 'secrets_config.py' exista.")
    exit(1)
except Exception as e:
    log_error(f"Error al configurar las API keys: {e}", "Revisa tu archivo 'secrets_config.py'.")
    exit(1)


async def test_product_flow(url: str, raw_data: dict):
    """
    Ejecuta el flujo de análisis completo para una única URL de producto,
    usando datos crudos ya extraídos.
    """
    log_step(f"Iniciando análisis para la URL: {url[:70]}...")

    try:
        # --- 1. Procesamiento de datos de Alibaba (desde archivo local) ---
        log_info("Paso 1: Procesando datos locales de Alibaba...")
        # Usamos una instancia del scraper solo para acceder a su lógica de extracción
        scraper_logic = AINcmClassifier.scraper_class() 
        product = scraper_logic.extract_product_info(raw_data)
        
        if not product:
            log_error("No se pudieron procesar los datos del producto.")
            return
        log_success(f"Producto procesado: '{product.title}'")
        log_info(f"Rango de precios completo detectado: ${product.price_low:.2f} - ${product.price_high:.2f}")


        # --- Mostrar todas las opciones de precio para cumplir el requerimiento ---
        if product.pricing.price_options:
            log_info(f"Opciones de precio por variación encontradas: {len(product.pricing.price_options)}")
            for option in product.pricing.price_options:
                log_info(f"  - Precio: {option.formatted_price}, Variación: {option.variation_description}")
        else:
            log_warning("No se encontraron precios por variación de SKU.")

        # --- 1.5. Estimación de Dimensiones y Peso ---
        log_info("Paso 1.5: Estimando dimensiones y peso...")
        estimator = ProductShippingEstimator()
        product_dict_for_estimator = product.raw_data if hasattr(product, 'raw_data') else {
            'subject': product.title,
            'categories': product.categories,
            'mediaItems': [{'type': 'image', 'imageUrl': {'big': img_url}} for img_url in product.images],
            'productHtmlDescription': getattr(product, 'html_description', ''),
            'productBasicProperties': getattr(product, 'properties_list', [])
        }
        shipping_details = estimator.get_shipping_details(product_dict_for_estimator)
        log_success("Estimación de envío completada.")
        print(json.dumps(shipping_details, indent=2))

        # --- 2. Clasificación NCM con IA ---
        log_info("Paso 2: Clasificando NCM (el punto crítico)...")
        enhanced_description = create_enhanced_description_headless(product)
        image_selection = validate_and_select_best_image_headless(product.images if product.images else [])
        
        log_info("Descripción para IA: " + enhanced_description)
        log_info("URL de imagen para IA: " + str(image_selection.get("selected_url")))

        classifier = AINcmClassifier(API_KEYS.get("OPENAI_API_KEY"))
        
        # Esta es la llamada asíncrona que estamos depurando
        ncm_result = await classifier.classify_product(
            description=enhanced_description,
            image_url=image_selection.get("selected_url")
        )

        if "error" in ncm_result:
            log_error("Error en la clasificación NCM.", json.dumps(ncm_result, indent=2))
            return
        
        log_success("Clasificación NCM completada.")
        
        # --- 2.5. Desglose de Información de VUCE ---
        log_step("Paso 2.5: Analizando datos de VUCE...")
        vuce_info = ncm_result.get("vuce_info")
        vuce_warning = ncm_result.get("vuce_warning")

        if vuce_warning:
            log_warning(f"Advertencia de VUCE: {vuce_warning}")

        if vuce_info:
            log_success("Información de VUCE encontrada y procesada.")
            
            log_info(f"  - Match Exacto: {'Sí' if vuce_info.get('match_exacto') else 'No'}")
            
            desc = vuce_info.get('descripcion_oficial', 'N/A')
            log_info(f"  - Descripción Oficial VUCE: {desc[:100]}...")

            treatment = ncm_result.get('tratamiento_arancelario', {})
            if treatment.get('fuente') == 'VUCE Oficial':
                log_info("  - Tratamiento Arancelario (Fuente: VUCE):")
                log_info(f"    - Derechos de Importación: {treatment.get('derechos_importacion', 'N/A')}%")
                log_info(f"    - Tasa Estadística: {treatment.get('tasa_estadistica', 'N/A')}%")

            regime_courier = ncm_result.get('regimen_simplificado_courier', {})
            vuce_analysis = regime_courier.get('vuce_analysis', {})
            if vuce_analysis:
                log_info("  - Régimen Simplificado (Análisis VUCE):")
                log_info(f"    - Aplica Potencialmente: {'Sí' if vuce_analysis.get('aplica_potencialmente') else 'No'}")
                if vuce_analysis.get('observaciones'):
                    log_info(f"    - Observaciones: {vuce_analysis['observaciones']}")

            interventions = vuce_info.get('intervenciones_detectadas', [])
            if interventions:
                log_info(f"  - Intervenciones Detectadas: {', '.join(interventions)}")
            else:
                log_info("  - Intervenciones Detectadas: Ninguna.")
        else:
            log_warning("No se encontró información de VUCE en el resultado de la clasificación.")
        
        # --- Pasos 3, 4 y 5: Calcular Landed Cost por cada rango de precios ---
        log_step("Pasos 3, 4 y 5: Calculando Landed Cost por Rango de Precios")

        # FIX: Manejar productos con precio único creando un tier de precios artificial
        tiers_to_calculate = product.pricing.ladder_prices
        if not tiers_to_calculate and product.price_low > 0:
            log_warning("No se encontraron precios escalonados. Calculando para el precio base único.")
            tiers_to_calculate = [{
                "min": product.moq if product.moq > 0 else 1,
                "price": Decimal(str(product.price_low))
            }]
        
        if not tiers_to_calculate:
            log_error("No se encontraron precios para calcular el landed cost.")
            return

        for tier in tiers_to_calculate:
            price = tier['price']
            min_quantity = tier.get('min', 1)
            
            log_info(f"--- Calculando para el rango: Cantidad >= {min_quantity} a ${price:.2f} USD ---")

            # a) Calcular impuestos por unidad
            tax_result = calcular_impuestos_importacion(
                cif_value=float(price),
                tipo_importador="responsable_inscripto",
                destino="reventa",
                origen="extrazona",
                tipo_dolar="oficial",
                provincia="CABA"
            )
            impuestos_por_unidad = float(tax_result.total_impuestos)

            # b) Calcular flete para el lote (SIMPLIFICADO AL 15% DEL FOB)
            log_info(f"Calculando flete SIMPLIFICADO para un lote de {min_quantity} unidades...")
            fob_lote = float(price) * min_quantity
            flete_costo_lote = fob_lote * 0.15
            log_success(f"Costo de flete (15% FOB) para {min_quantity} unidades: ${flete_costo_lote:.2f} USD")

            flete_por_unidad = flete_costo_lote / min_quantity if min_quantity > 0 else 0

            # c) Calcular honorarios por unidad (2% del FOB unitario)
            honorarios_por_unidad = float(price) * 0.02

            # d) Calcular y mostrar Landed Cost unitario final
            landed_cost_unitario = float(price) + impuestos_por_unidad + flete_por_unidad + honorarios_por_unidad

            log_success(f"➡️  Landed Cost Unitario (para >={min_quantity} unidades): ${landed_cost_unitario:.2f} USD")
            print(f"    - Precio FOB:      ${float(price):.2f}")
            print(f"    - Impuestos:       ${impuestos_por_unidad:.2f}")
            print(f"    - Flete Unitario:  ${flete_por_unidad:.2f}")
            print(f"    - Honorarios:      ${honorarios_por_unidad:.2f}")

    except Exception as e:
        log_error(f"Ocurrió una excepción fatal en el flujo de análisis para {url}", traceback.format_exc())


async def main():
    """
    Función principal que ejecuta el test para una lista de URLs,
    cargando los datos desde un archivo local de Apify.
    """
    # Cargar datos locales de Apify
    local_data_path = "apify_results/dataset_scrape-alibaba-item_2025-07-06_16-21-14-335.json"
    try:
        with open(local_data_path, 'r', encoding='utf-8') as f:
            all_products_data = json.load(f)
        log_success(f"Datos locales de Apify cargados desde '{local_data_path}'")
    except FileNotFoundError:
        log_error(f"No se encontró el archivo de datos locales: {local_data_path}", "Ejecuta el scraper una vez para generarlo.")
        return
    except json.JSONDecodeError:
        log_error(f"Error al decodificar el archivo JSON: {local_data_path}", "El archivo podría estar corrupto.")
        return

    # Mapear URL a datos de producto para fácil acceso
    product_data_map = {item['url']: item for item in all_products_data if 'url' in item}

    product_urls = [
        "https://www.alibaba.com/product-detail/Retail-Store-Commercial-65-Inch-LCD_1601365832644.html?spm=a2700.galleryofferlist.p_offer.d_image.744413a0QzIZHg&s=p",
        "https://www.alibaba.com/product-detail/2025-new-Top-Quality-Luxury-designer_1601361795075.html?spm=a2700.galleryofferlist.normal_offer.d_image.61ca13a0MTLlQZ",
        "https://www.alibaba.com/product-detail/314AH-3-2V-Lithium-Ion-Battery_1601451822666.html?spm=a27aq.28778915.8965415670.1.56ba5cbe2B0Vt2&venueType=getSample"
    ]

    for url in product_urls:
        if url in product_data_map:
            await test_product_flow(url, product_data_map[url])
        else:
            log_warning(f"No se encontraron datos para la URL {url} en el archivo local. Omitiendo.")
        print("\n" + "="*80 + "\n")


if __name__ == "__main__":
    # Adjuntamos la clase del scraper al clasificador para evitar importaciones circulares y dependencias
    AINcmClassifier.scraper_class = __import__('alibaba_scraper').AlibabaScraperApify

    # Usamos asyncio.run() para ejecutar la función asíncrona principal.
    # Esto es mucho más estable que hacerlo dentro de Streamlit.
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProceso interrumpido por el usuario.")
    except Exception as e:
        log_error("Error inesperado en el script principal.", traceback.format_exc()) 