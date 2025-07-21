#!/usr/bin/env python3
"""
🔧 Alibaba Scraper - Extractor Completo de Productos de Alibaba
==============================================================

Usa la API oficial de Apify para extraer información detallada de productos de Alibaba
incluyendo precios, dimensiones, peso, volumen y variaciones.

Funcionalidades:
- Scraping completo de productos
- Extracción de dimensiones y peso
- Análisis detallado de precios y variaciones  
- Cálculo de volúmenes y pesos volumétricos
- Soporte para múltiples SKUs y variaciones

Actor ID: F1vYvaTdy8vfPulOg
"""

import time
import json
import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict, field
from apify_client import ApifyClient
from decimal import Decimal
import logging
import sys
import argparse
try:
    from secrets_config import get_api_key
except ImportError:
    # Definir una función dummy si secrets_config no existe para no romper la importación
    def get_api_key(key_name):
        return None

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class PriceOption:
    """Opción de precio con variación y cantidad"""
    price: Decimal
    sku_id: str
    variation_description: str
    min_quantity: int
    max_quantity: Optional[int] = None
    formatted_price: str = ""
    attributes: Dict[str, str] = None
    
    def __post_init__(self):
        if not self.formatted_price:
            self.formatted_price = f"${self.price:.2f}"
        if self.attributes is None:
            self.attributes = {}

@dataclass
class ProductDimensions:
    """Dimensiones y peso del producto"""
    length_cm: Optional[float] = None
    width_cm: Optional[float] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    volume_cbm: Optional[float] = None
    dimensional_weight_kg: Optional[float] = None
    source: str = "extracted"  # extracted, estimated, fallback
    
    def __post_init__(self):
        # Calcular volumen si tenemos las dimensiones
        if self.length_cm and self.width_cm and self.height_cm:
            self.volume_cbm = (self.length_cm * self.width_cm * self.height_cm) / 1_000_000
            
            # Calcular peso dimensional (factor típico para envío aéreo: 167 kg/m³)
            self.dimensional_weight_kg = self.volume_cbm * 167
    
    def to_dict(self) -> Dict:
        return asdict(self)

@dataclass
class ProductPricing:
    """Estructura completa de precios del producto"""
    base_price_range: Tuple[Decimal, Decimal]
    price_options: List[PriceOption]
    moq: int
    unit: str
    ladder_prices: List[Dict[str, Any]] = field(default_factory=list)
    currency_pattern: str = "${0}"
    has_multiple_prices: bool = False
    price_difference_pct: float = 0.0
    
    def __post_init__(self):
        self.has_multiple_prices = len(set(opt.price for opt in self.price_options)) > 1
        
        if self.has_multiple_prices and self.price_options:
            prices = [opt.price for opt in self.price_options]
            min_price = min(prices)
            max_price = max(prices)
            if min_price > 0:
                self.price_difference_pct = float((max_price - min_price) / min_price * 100)
    
    def get_cheapest_option(self) -> Optional[PriceOption]:
        """Obtener la opción más económica"""
        if not self.price_options:
            return None
        return min(self.price_options, key=lambda x: x.price)
    
    def get_most_expensive_option(self) -> Optional[PriceOption]:
        """Obtener la opción más cara"""
        if not self.price_options:
            return None
        return max(self.price_options, key=lambda x: x.price)

    def get_price_groups(self) -> Dict[str, List[PriceOption]]:
        """Agrupar opciones de precio por el valor del precio."""
        from collections import defaultdict
        groups = defaultdict(list)
        for option in self.price_options:
            price_str = f"{option.price:.2f}"
            groups[price_str].append(option)
        return dict(groups)
    
    def to_dict(self) -> Dict:
        data = asdict(self)
        data['base_price_range'] = [float(p) for p in self.base_price_range]
        
        # Convertir Decimal a float en price_options
        for option in data['price_options']:
            option['price'] = float(option['price'])
        
        return data

@dataclass
class ProductInfo:
    """Información completa del producto extraído"""
    url: str
    product_id: str
    title: str
    categories: List[str]
    price_range: str
    price_low: float
    price_high: float
    moq: int
    currency: str
    unit: str
    images: List[str]
    place_of_origin: str
    brand_name: str
    description: str
    properties: Dict[str, str]
    dimensions: ProductDimensions
    pricing: ProductPricing
    raw_data: Dict = None
    processed_at: str = ""
    
    def __post_init__(self):
        if not self.processed_at:
            self.processed_at = time.strftime("%Y-%m-%d %H:%M:%S")
    
    def to_dict(self) -> Dict:
        """Convertir a diccionario"""
        data = asdict(self)
        data['dimensions'] = self.dimensions.to_dict()
        data['pricing'] = self.pricing.to_dict()
        return data

class AlibabaScraperApify:
    """Scraper completo de Alibaba usando la API oficial de Apify"""
    
    def __init__(self, api_key: str = None):
        """
        Inicializar el cliente de Apify
        
        Args:
            api_key: API key de Apify (opcional, usa una por defecto)
        """
        # Intentar cargar API key desde secrets centralizados
        if not api_key:
            try:
                from secrets_config import get_api_key
                api_key = get_api_key("APIFY_API_KEY")
            except ImportError:
                pass
        
        # Usar API key proporcionada o fallback
        self.api_key = api_key
        if not self.api_key:
            raise ValueError("No se proporcionó API key de Apify. El scraper no puede continuar.")
        
        self.actor_id = "F1vYvaTdy8vfPulOg"
        self.client = ApifyClient(self.api_key)
        
        logger.info(f"✅ Cliente Apify inicializado")
        logger.info(f"🔑 API Key: {self.api_key[:20]}...")
        logger.info(f"🎭 Actor ID: {self.actor_id}")
    
    def extract_dimensions_and_weight(self, raw_data: Dict) -> ProductDimensions:
        """
        Extraer dimensiones y peso del producto
        
        Args:
            raw_data: Datos crudos del producto
            
        Returns:
            ProductDimensions: Dimensiones y peso extraídos
        """
        dimensions = ProductDimensions()
        
        # Buscar en propiedades básicas
        basic_props = raw_data.get("productBasicProperties", [])
        
        for prop in basic_props:
            attr_name = prop.get("attrName", "").lower()
            attr_value = prop.get("attrValue", "")
            
            if not attr_value:
                continue
                
            # Buscar dimensiones
            if any(keyword in attr_name for keyword in ["size", "dimension", "measurement"]):
                dims = self._parse_dimensions(attr_value)
                if dims:
                    dimensions.length_cm, dimensions.width_cm, dimensions.height_cm = dims
                    dimensions.source = "extracted"
                    logger.info(f"📏 Dimensiones encontradas: {dims[0]}×{dims[1]}×{dims[2]} cm")
            
            # Buscar peso
            elif any(keyword in attr_name for keyword in ["weight", "gross weight", "net weight"]):
                weight = self._parse_weight(attr_value)
                if weight:
                    dimensions.weight_kg = weight
                    logger.info(f"⚖️ Peso encontrado: {weight} kg")
        
        # Buscar en descripción HTML
        html_desc = raw_data.get("productHtmlDescription", "")
        if html_desc and (not dimensions.length_cm or not dimensions.weight_kg):
            desc_dims = self._extract_from_description(html_desc)
            if desc_dims.get("dimensions") and not dimensions.length_cm:
                dims = desc_dims["dimensions"]
                dimensions.length_cm, dimensions.width_cm, dimensions.height_cm = dims
                dimensions.source = "description"
                logger.info(f"📏 Dimensiones desde descripción: {dims[0]}×{dims[1]}×{dims[2]} cm")
            
            if desc_dims.get("weight") and not dimensions.weight_kg:
                dimensions.weight_kg = desc_dims["weight"]
                logger.info(f"⚖️ Peso desde descripción: {desc_dims['weight']} kg")
        
        # Calcular volumen y peso dimensional si tenemos dimensiones
        if dimensions.length_cm and dimensions.width_cm and dimensions.height_cm:
            volume = (dimensions.length_cm * dimensions.width_cm * dimensions.height_cm) / 1_000_000
            dimensions.volume_cbm = volume
            dimensions.dimensional_weight_kg = volume * 167  # Factor estándar aéreo
            logger.info(f"📦 Volumen calculado: {volume:.6f} m³")
            logger.info(f"⚖️ Peso dimensional: {dimensions.dimensional_weight_kg:.2f} kg")
        
        return dimensions
    
    def _parse_dimensions(self, text: str) -> Optional[Tuple[float, float, float]]:
        """Parsear dimensiones desde texto"""
        if not text:
            return None
            
        # Patrones comunes: "30x20x15", "30*20*15", "30 x 20 x 15", "30cm×20cm×15cm"
        patterns = [
            r'(\d+(?:\.\d+)?)\s*[x×*]\s*(\d+(?:\.\d+)?)\s*[x×*]\s*(\d+(?:\.\d+)?)',
            r'(\d+(?:\.\d+)?)\s*cm\s*[x×*]\s*(\d+(?:\.\d+)?)\s*cm\s*[x×*]\s*(\d+(?:\.\d+)?)\s*cm',
            r'L:\s*(\d+(?:\.\d+)?)\s*cm.*W:\s*(\d+(?:\.\d+)?)\s*cm.*H:\s*(\d+(?:\.\d+)?)\s*cm',
            r'Length:\s*(\d+(?:\.\d+)?)\s*cm.*Width:\s*(\d+(?:\.\d+)?)\s*cm.*Height:\s*(\d+(?:\.\d+)?)\s*cm'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    dims = [float(match.group(i)) for i in range(1, 4)]
                    # Validar que sean dimensiones razonables (1mm a 10m)
                    if all(0.1 <= dim <= 1000 for dim in dims):
                        return tuple(dims)
                except (ValueError, IndexError):
                    continue
        
        return None
    
    def _parse_weight(self, text: str) -> Optional[float]:
        """Parsear peso desde texto"""
        if not text:
            return None
            
        # Patrones: "5kg", "5.5 kg", "5000g", "5.5 KG"
        patterns = [
            r'(\d+(?:\.\d+)?)\s*kg',
            r'(\d+(?:\.\d+)?)\s*g',  # convertir gramos a kg
        ]
        
        for i, pattern in enumerate(patterns):
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    weight = float(match.group(1))
                    # Convertir gramos a kg si es necesario
                    if i == 1:  # patrón de gramos
                        weight = weight / 1000
                    # Validar que sea un peso razonable (1g a 1000kg)
                    if 0.001 <= weight <= 1000:
                        return weight
                except ValueError:
                    continue
        
        return None
    
    def _extract_from_description(self, html_desc: str) -> Dict[str, Any]:
        """Extraer dimensiones y peso desde descripción HTML"""
        result = {}
        
        # Limpiar HTML básico
        text = re.sub(r'<[^>]+>', ' ', html_desc)
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Buscar dimensiones
        dims = self._parse_dimensions(text)
        if dims:
            result["dimensions"] = dims
        
        # Buscar peso
        weight = self._parse_weight(text)
        if weight:
            result["weight"] = weight
        
        return result
    
    def extract_pricing_info(self, raw_data: Dict) -> ProductPricing:
        """
        Extraer información detallada de precios, priorizando precios de SKU sobre
        precios por volumen para el rango base.
        
        Args:
            raw_data: Datos crudos del producto
            
        Returns:
            ProductPricing: Estructura con opciones de precios
        """
        price_info = raw_data.get('price', {})
        sku_info = raw_data.get('sku', {})

        # 1. Obtener precios por volumen (ladder prices)
        ladder_prices_raw = price_info.get('productLadderPrices', [])
        ladder_prices = []
        for lp in ladder_prices_raw:
            price = Decimal(str(lp.get('price') or lp.get('dollarPrice', 0)))
            if price > 0:
                ladder_prices.append({
                    "min": lp.get("min"),
                    "max": lp.get("max"),
                    "price": price
                })

        # 2. Obtener precios por variación (SKU) para determinar el rango base
        price_options = []
        sku_prices = []
        sku_samples = sku_info.get('skuSample', [])
        
        if sku_samples:
            logger.info(f"🎯 Encontrados {len(sku_samples)} SKUs de ejemplo con precios")
            for sample in sku_samples:
                price = Decimal(str(sample.get('price', 0)))
                if price == 0:
                    continue

                sku_prices.append(price)
                
                # Construir descripción de la variación
                variation_desc_parts = []
                attributes = {}
                for val in sample.get('values', []):
                    prop_name = val.get('propName', 'Atributo')
                    value_name = val.get('name', 'Valor')
                    variation_desc_parts.append(f"{prop_name}: {value_name}")
                    attributes[prop_name] = value_name
                
                variation_desc = " | ".join(variation_desc_parts) if variation_desc_parts else "Estándar"

                price_options.append(PriceOption(
                    price=price,
                    sku_id=str(sample.get('id', '')),
                    variation_description=variation_desc,
                    min_quantity=raw_data.get('moq', 1), # MOQ general
                    formatted_price=f"${price:.2f}",
                    attributes=attributes
                ))
        
        # 3. Consolidar precios y rango base, considerando TODOS los precios
        all_prices = sku_prices[:] # Copiar precios de SKU
        if ladder_prices:
            all_prices.extend([lp['price'] for lp in ladder_prices])

        price_low = min(all_prices) if all_prices else Decimal('0')
        price_high = max(all_prices) if all_prices else Decimal('0')

        # Fallback si no se encontró ningún precio
        if price_low == 0 and price_high == 0:
             # Este caso es poco probable si hay ladder_prices o sku_prices, pero es un buen seguro
             raw_price_low = Decimal(str(price_info.get('promotionPrice', {}).get('minPrice') or price_info.get('minPrice', 0)))
             raw_price_high = Decimal(str(price_info.get('promotionPrice', {}).get('maxPrice') or price_info.get('maxPrice', 0)))
             if raw_price_low > 0:
                 price_low = raw_price_low
                 price_high = raw_price_high if raw_price_high > 0 else raw_price_low
                 logger.info(f"  ⚠️ No se encontraron precios de SKU o escalonados. Usando rango de precio general: ${price_low:.2f} - ${price_high:.2f}")

        base_range = (price_low, price_high)
        
        # Si no se crearon opciones de precio en los SKU pero tenemos un precio base, crear una opción por defecto
        if not price_options and price_low > 0:
            price_options.append(PriceOption(
                price=price_low,
                sku_id="default",
                variation_description="Precio estándar",
                min_quantity=raw_data.get('moq', 1),
                formatted_price=f"${price_low:.2f}"
            ))
            logger.info(f"  💰 Usando precio base como opción única: ${price_low:.2f}")

        # 4. Construir objeto de pricing final
        product_pricing = ProductPricing(
            base_price_range=base_range,
            price_options=price_options,
            ladder_prices=ladder_prices,
            moq=raw_data.get('moq', 1),
            unit=price_info.get('unit', 'piece'),
            currency_pattern=price_info.get('currencyRule', {}).get('currencyPattern', '${0}')
        )

        logger.info(f"✅ Precios procesados: {len(price_options)} opciones de variación, {len(ladder_prices)} tramos de cantidad.")
        return product_pricing

    def extract_product_info(self, raw_data: Dict) -> ProductInfo:
        """
        Extraer información completa del producto desde los datos crudos
        
        Args:
            raw_data: Datos crudos del producto de Apify
            
        Returns:
            ProductInfo: Información estructurada del producto
        """
        # Información básica
        url = raw_data.get("url", "")
        product_id = str(raw_data.get("productId", ""))
        title = raw_data.get("subject", "")
        categories = raw_data.get("categories", [])
        
        # --- Lógica de precios centralizada ---
        pricing = self.extract_pricing_info(raw_data)
        price_low = float(pricing.base_price_range[0])
        price_high = float(pricing.base_price_range[1])
        price_range_str = f"${price_low:.2f} - ${price_high:.2f}" if price_low != price_high else f"${price_low:.2f}"
        
        moq = pricing.moq
        currency = "USD"
        unit = pricing.unit
        
        # Imágenes
        media_items = raw_data.get("mediaItems", [])
        images = []
        for item in media_items:
            if item.get("type") == "image":
                image_url = item.get("imageUrl", {})
                if image_url.get("big"):
                    images.append(image_url["big"])
        
        # Propiedades básicas - búsqueda mejorada
        basic_props = raw_data.get("productBasicProperties", [])
        properties = {}
        place_of_origin = ""
        brand_name = ""
        
        for prop in basic_props:
            attr_name = prop.get("attrName", "")
            attr_value = prop.get("attrValue", "")
            if attr_name and attr_value:
                properties[attr_name] = attr_value
                # Búsqueda más flexible (case-insensitive)
                attr_name_lower = attr_name.lower()
                if "place of origin" in attr_name_lower:
                    place_of_origin = attr_value
                elif "brand name" in attr_name_lower:
                    brand_name = attr_value
        
        # Descripción HTML (simplificada)
        description_html = raw_data.get("productHtmlDescription", "")
        description = description_html[:500] + "..." if len(description_html) > 500 else description_html
        
        # Extraer dimensiones y peso
        dimensions = self.extract_dimensions_and_weight(raw_data)
        
        # Extraer información detallada de precios
        pricing = self.extract_pricing_info(raw_data)
        
        # Usar el rango de precios del objeto pricing
        price_low = float(pricing.base_price_range[0])
        price_high = float(pricing.base_price_range[1])

        # Debug info
        logger.info(f"📦 Producto procesado:")
        logger.info(f"   🏷️ Título: {title}")
        logger.info(f"   💰 Precio: ${price_low} - ${price_high}")
        logger.info(f"   📊 MOQ: {moq}")
        logger.info(f"   🌍 Origen: {place_of_origin}")
        logger.info(f"   🏭 Marca: {brand_name}")
        logger.info(f"   📸 Imágenes: {len(images)}")
        logger.info(f"   📏 Dimensiones: {dimensions.source}")
        logger.info(f"   💰 Precios: {len(pricing.price_options)} opciones")
        
        return ProductInfo(
            url=url,
            product_id=product_id,
            title=title,
            categories=categories,
            price_range=price_range_str,
            price_low=price_low,
            price_high=price_high,
            moq=moq,
            currency=currency,
            unit=unit,
            images=images,
            place_of_origin=place_of_origin,
            brand_name=brand_name,
            description=description,
            properties=properties,
            dimensions=dimensions,
            pricing=pricing,
            raw_data=raw_data
        )
    
    def scrape_product(self, url: str) -> Optional[ProductInfo]:
        """
        Scraper un producto individual de Alibaba
        
        Args:
            url: URL del producto de Alibaba
            
        Returns:
            ProductInfo o None si hay error
        """
        try:
            logger.info(f"🚀 Iniciando scraping de: {url}")
            
            # Configurar input para el actor
            run_input = {
                "size": 1,
                "detail_urls": [{"url": url}]
            }
            
            logger.info("📤 Enviando request al actor de Apify...")
            
            # Ejecutar actor y esperar resultados
            run = self.client.actor(self.actor_id).call(run_input=run_input)
            
            logger.info(f"✅ Actor ejecutado exitosamente. Run ID: {run.get('id')}")
            
            # Obtener resultados del dataset
            items = list(self.client.dataset(run["defaultDatasetId"]).iterate_items())
            
            if not items:
                logger.warning("⚠️ No se encontraron resultados en la API de Apify.")
                return None
            
            # Procesar primer resultado
            raw_data = items[0]
            product_info = self.extract_product_info(raw_data)
            
            return product_info
            
        except Exception as e:
            logger.error(f"❌ Error en scraping: {str(e)}")
            return None
            
    def scrape_multiple_products(self, urls: List[str]) -> List[ProductInfo]:
        """
        Scraper múltiples productos de Alibaba
        
        Args:
            urls: Lista de URLs de productos
            
        Returns:
            Lista de ProductInfo
        """
        results = []
        
        try:
            logger.info(f"🚀 Iniciando scraping de {len(urls)} productos...")
            
            # Configurar input para el actor
            detail_urls = [{"url": url} for url in urls]
            run_input = {
                "size": len(urls),
                "detail_urls": detail_urls
            }
            
            logger.info("📤 Enviando request al actor de Apify...")
            
            # Ejecutar actor y esperar resultados
            run = self.client.actor(self.actor_id).call(run_input=run_input)
            
            logger.info(f"✅ Actor ejecutado exitosamente. Run ID: {run.get('id')}")
            
            # Obtener resultados del dataset
            items = list(self.client.dataset(run["defaultDatasetId"]).iterate_items())
            
            logger.info(f"📊 Obtenidos {len(items)} resultados")
            
            # Procesar cada resultado
            for i, raw_data in enumerate(items):
                try:
                    product_info = self.extract_product_info(raw_data)
                    results.append(product_info)
                    logger.info(f"✅ Producto {i+1} procesado: {product_info.title}")
                except Exception as e:
                    logger.error(f"❌ Error procesando producto {i+1}: {str(e)}")
                    continue
            
            logger.info(f"🎉 Scraping completado: {len(results)} productos procesados")
            
        except Exception as e:
            logger.error(f"❌ Error en scraping múltiple: {str(e)}")
        
        return results

# Funciones de compatibilidad para mantener la API existente
def extract_alibaba_pricing(product_data: dict, verbose: bool = False) -> ProductPricing:
    """
    Función de compatibilidad para extract_alibaba_pricing.
    Ahora devuelve el objeto ProductPricing directamente.
    """
    scraper = AlibabaScraperApify()
    pricing = scraper.extract_pricing_info(product_data)
    return pricing

def format_pricing_for_display(pricing: ProductPricing) -> Dict[str, Any]:
    """
    Formatea la información de precios para mostrar en UI
    """
    display_data = {
        'has_multiple_prices': pricing.has_multiple_prices,
        'price_difference_pct': pricing.price_difference_pct,
        'moq': pricing.moq,
        'unit': pricing.unit,
        'total_options': len(pricing.price_options),
        'price_groups': {},
        'cheapest_option': None,
        'most_expensive_option': None
    }
    
    # Formatear grupos de precios
    price_groups = pricing.get_price_groups()
    for price_str, options in price_groups.items():
        display_data['price_groups'][price_str] = {
            'price': f"${price_str}",
            'count': len(options),
            'options': [
                {
                    'sku_id': opt.sku_id,
                    'variation': opt.variation_description,
                    'attributes': opt.attributes,
                    'formatted_price': opt.formatted_price
                }
                for opt in options
            ]
        }
    
    # Opciones destacadas
    if pricing.price_options:
        cheapest = pricing.get_cheapest_option()
        most_expensive = pricing.get_most_expensive_option()
        
        if cheapest:
            display_data['cheapest_option'] = {
                'price': float(cheapest.price),
                'formatted_price': cheapest.formatted_price,
                'variation': cheapest.variation_description,
                'sku_id': cheapest.sku_id
            }
        
        if most_expensive:
            display_data['most_expensive_option'] = {
                'price': float(most_expensive.price),
                'formatted_price': most_expensive.formatted_price,
                'variation': most_expensive.variation_description,
                'sku_id': most_expensive.sku_id
            }
    
    return display_data

def get_cheapest_price_option(pricing: ProductPricing) -> Optional[Dict[str, Any]]:
    """Función de compatibilidad para obtener la opción más barata."""
    if pricing.price_options:
        cheapest = pricing.get_cheapest_option()
        return {
            'price': float(cheapest.price),
            'formatted_price': cheapest.formatted_price,
            'variation': cheapest.variation_description,
            'sku_id': cheapest.sku_id
        }
    return None

def calculate_total_cost_for_option(price_option, quantity: int, additional_costs: Dict[str, Decimal] = None) -> Dict[str, Decimal]:
    """
    Función de compatibilidad para calculate_total_cost_for_option
    """
    if additional_costs is None:
        additional_costs = {}
    
    # Verificar MOQ
    if hasattr(price_option, 'min_quantity'):
        min_qty = price_option.min_quantity
    else:
        min_qty = price_option.get('min_quantity', 1)
    
    if quantity < min_qty:
        quantity = min_qty
    
    # Cálculos básicos
    if hasattr(price_option, 'price'):
        unit_cost = price_option.price
    else:
        unit_cost = Decimal(str(price_option.get('price', 0)))
    
    subtotal = unit_cost * quantity
    
    # Construir breakdown
    cost_breakdown = {
        'unit_cost': unit_cost,
        'quantity': Decimal(str(quantity)),
        'subtotal': subtotal,
        'total_additional_costs': Decimal('0')
    }
    
    # Agregar costos adicionales
    for cost_name, cost_value in additional_costs.items():
        cost_breakdown[cost_name] = cost_value
        cost_breakdown['total_additional_costs'] += cost_value
    
    # Total final
    cost_breakdown['total'] = subtotal + cost_breakdown['total_additional_costs']
    
    return cost_breakdown

def scrape_alibaba_products(urls: List[str], api_key: str = None) -> List[ProductInfo]:
    """
    Función principal para scraper productos de Alibaba
    
    Args:
        urls: Lista de URLs de productos de Alibaba
        api_key: API key de Apify (opcional)
        
    Returns:
        Lista de ProductInfo
    """
    scraper = AlibabaScraperApify(api_key)
    return scraper.scrape_multiple_products(urls)

def scrape_single_alibaba_product(url: str, api_key: str = None) -> Optional[ProductInfo]:
    """
    Función para scraper un solo producto de Alibaba
    
    Args:
        url: URL del producto de Alibaba
        api_key: API key de Apify (opcional)
        
    Returns:
        ProductInfo o None
    """
    scraper = AlibabaScraperApify(api_key)
    return scraper.scrape_product(url)

# Función para testing
def test_scraper(url: str, api_key: str):
    """Función para testear el scraper mejorado..."""
    
    print("🧪 Iniciando test del scraper mejorado...")
    print(f"📋 URL de prueba: {url}")
    
    result = scrape_single_alibaba_product(url, api_key)
    
    if result:
        print("\n✅ Test exitoso!")
        print("-" * 20)
        print(f"📦 Título: {result.title}")
        print(f"💰 Rango de Precio: {result.price_range} ({result.currency})")
        print(f"📦 MOQ: {result.moq} {result.unit}")
        print(f"🌍 Origen: {result.place_of_origin}")
        print(f"🏷️ Marca: {result.brand_name}")
        print(f"🖼️ Imágenes: {len(result.images)}")
        
        print("\n--- Dimensiones y Peso ---")
        print(f"📏 Fuente: {result.dimensions.source}")
        print(f"   - L/W/H: {result.dimensions.length_cm} x {result.dimensions.width_cm} x {result.dimensions.height_cm} cm")
        print(f"   - Peso: {result.dimensions.weight_kg} kg")
        print(f"   - Volumen: {result.dimensions.volume_cbm:.6f} m³" if result.dimensions.volume_cbm else "N/A")
        print(f"   - Peso Volumétrico: {result.dimensions.dimensional_weight_kg:.2f} kg" if result.dimensions.dimensional_weight_kg else "N/A")

        print("\n--- Precios Detallados ---")
        pricing = result.pricing
        print(f"📊 Opciones por variación: {len(pricing.price_options)}")
        for i, option in enumerate(pricing.price_options[:5]): # Mostrar hasta 5
            print(f"  {i+1}. {option.formatted_price} - {option.variation_description}")
        
        print(f"\n📊 Precios por cantidad: {len(pricing.ladder_prices)}")
        for i, ladder in enumerate(pricing.ladder_prices):
             print(f"  {i+1}. Cantidad: {ladder['min']}-{ladder.get('max', '∞')}, Precio: ${ladder['price']:.2f}")

        # Guardar resultado para debug
        output_filename = "test_result.json"
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Resultado completo guardado en '{output_filename}'")
    else:
        print("\n❌ Test falló. No se pudo extraer la información.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Testear el Scraper de Alibaba con una URL.")
    parser.add_argument("url", nargs='?', default=None, help="La URL del producto de Alibaba a testear.")
    args = parser.parse_args()

    test_url = args.url
    if not test_url:
        print("⚠️ No se proporcionó URL. Usando una URL de ejemplo.")
        test_url = "https://www.alibaba.com/product-detail/Hongyan-Man-Shoes-White-Men-Casual_1600919254225.html"

    try:
        apify_key = get_api_key("APIFY_API_KEY")
        if not apify_key:
            print("❌ Error: No se encontró la API key de Apify en la configuración de secrets.")
            print("Asegúrate de tener un archivo .streamlit/secrets.toml válido o una variable de entorno.")
            sys.exit(1)
            
        test_scraper(test_url, apify_key)
        
    except ImportError:
        print("❌ Error: No se pudo importar 'get_api_key' desde 'secrets_config'.")
        print("Asegúrate que el archivo 'secrets_config.py' existe y es accesible.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Ocurrió un error inesperado: {e}")
        sys.exit(1) 