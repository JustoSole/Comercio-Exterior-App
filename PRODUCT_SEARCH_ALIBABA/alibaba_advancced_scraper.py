from selenium import webdriver
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.common.action_chains import ActionChains
import time
import json
import re
from typing import List, Dict, Optional, Union, Tuple
from datetime import datetime
import logging
from functools import wraps
import random

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AlibabaAdvancedScraper:
    """Scraper avanzado para Alibaba con técnicas adaptativas y manejo robusto de errores"""
    
    def __init__(self, driver: WebDriver, headless: bool = False):
        self.driver = driver
        self.wait = WebDriverWait(driver, 20)
        self.actions = ActionChains(driver)
        
    def retry_on_stale_element(max_attempts: int = 3):
        """Decorador para reintentar en caso de StaleElementReferenceException"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                for attempt in range(max_attempts):
                    try:
                        return func(*args, **kwargs)
                    except StaleElementReferenceException:
                        if attempt == max_attempts - 1:
                            raise
                        time.sleep(0.5)
                return None
            return wrapper
        return decorator
    
    def random_delay(self, min_seconds: float = 0.5, max_seconds: float = 2.0):
        """Añade un retraso aleatorio para evitar detección"""
        time.sleep(random.uniform(min_seconds, max_seconds))
    
    def scroll_to_element(self, element):
        """Desplaza hasta el elemento de forma suave"""
        self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
        self.random_delay(0.3, 0.8)
    
    def safe_find_element(self, parent, selectors: List[Tuple[By, str]], default: str = "N/A") -> str:
        """
        Busca elementos usando múltiples selectores (técnica adaptativa)
        Siguiendo las mejores prácticas de scraping adaptativo
        """
        for by, selector in selectors:
            try:
                if parent:
                    element = parent.find_element(by, selector)
                else:
                    element = self.driver.find_element(by, selector)
                    
                if element:
                    text = element.text.strip()
                    if not text and element.get_attribute('value'):
                        text = element.get_attribute('value').strip()
                    return text if text else default
            except (NoSuchElementException, StaleElementReferenceException):
                continue
        return default
    
    def safe_get_attribute(self, parent, selectors: List[Tuple[By, str]], attribute: str, default: str = "N/A") -> str:
        """Obtiene un atributo de forma segura con múltiples selectores"""
        for by, selector in selectors:
            try:
                if parent:
                    element = parent.find_element(by, selector)
                else:
                    element = self.driver.find_element(by, selector)
                    
                if element:
                    attr_value = element.get_attribute(attribute)
                    return attr_value if attr_value else default
            except (NoSuchElementException, StaleElementReferenceException):
                continue
        return default
    
    def extract_price_info(self, container) -> Dict[str, any]:
        """Extrae información detallada de precios incluyendo escalas"""
        price_info = {
            "min_price": "N/A",
            "max_price": "N/A",
            "currency": "USD",
            "price_ranges": [],
            "sample_price": "N/A",
            "negotiable": False
        }
        
        try:
            # Buscar precios con múltiples selectores
            price_selectors = [
                (By.CSS_SELECTOR, ".search-card-e-price-main"),
                (By.CSS_SELECTOR, "[class*='price']"),
                (By.CSS_SELECTOR, "span[class*='Price']"),
                (By.XPATH, ".//*[contains(text(), '$') or contains(text(), 'US')]")
            ]
            
            price_text = self.safe_find_element(container, price_selectors)
            
            if price_text != "N/A":
                # Extraer rango de precios
                price_match = re.findall(r'[\d,]+\.?\d*', price_text)
                if price_match:
                    prices = [float(p.replace(',', '')) for p in price_match]
                    if prices:
                        price_info["min_price"] = min(prices)
                        price_info["max_price"] = max(prices) if len(prices) > 1 else min(prices)
                
                # Detectar moneda
                if "€" in price_text:
                    price_info["currency"] = "EUR"
                elif "¥" in price_text or "CNY" in price_text:
                    price_info["currency"] = "CNY"
                
                # Detectar si es negociable
                if "negotiable" in price_text.lower():
                    price_info["negotiable"] = True
                    
        except Exception as e:
            logger.error(f"Error extrayendo precio: {e}")
            
        return price_info
    
    def extract_product_details(self, product_url: str) -> Dict[str, any]:
        """Extrae TODOS los detalles del producto de la página individual"""
        
        logger.info(f"Extrayendo detalles de: {product_url}")
        self.driver.get(product_url)
        self.random_delay(3, 5)
        
        product_details = {
            "url": product_url,
            "scraped_at": datetime.now().isoformat(),
            "basic_info": {},
            "pricing": {},
            "specifications": {},
            "shipping": {},
            "company": {},
            "images": [],
            "videos": [],
            "certifications": [],
            "reviews": {},
            "variations": [],
            "keywords": []
        }
        
        try:
            # Información básica del producto
            product_details["basic_info"] = {
                "title": self.safe_find_element(None, [
                    (By.CSS_SELECTOR, "h1"),
                    (By.CSS_SELECTOR, ".product-title-container h1"),
                    (By.CSS_SELECTOR, "[data-module-name='module_title'] h1")
                ]),
                "subtitle": self.safe_find_element(None, [
                    (By.CSS_SELECTOR, ".product-subtitle"),
                    (By.CSS_SELECTOR, "[class*='subtitle']")
                ]),
                "product_id": self.extract_product_id(product_url),
                "category_path": self.extract_breadcrumbs()
            }
            
            # Información de la empresa
            product_details["company"] = self.extract_company_info()
            
            # Reviews y ratings
            product_details["reviews"] = self.extract_reviews_info()
            
            # Precios detallados
            product_details["pricing"] = self.extract_detailed_pricing()
            
            # Especificaciones y atributos
            product_details["specifications"] = self.extract_specifications()
            
            # Información de envío
            product_details["shipping"] = self.extract_shipping_info()
            
            # Imágenes y videos
            product_details["images"], product_details["videos"] = self.extract_media()
            
            # Certificaciones
            product_details["certifications"] = self.extract_certifications()
            
            # Variaciones del producto
            product_details["variations"] = self.extract_variations()
            
            # Keywords y tags
            product_details["keywords"] = self.extract_keywords()
            
        except Exception as e:
            logger.error(f"Error extrayendo detalles del producto: {e}")
            
        return product_details
    
    def extract_product_id(self, url: str) -> str:
        """Extrae el ID del producto de la URL"""
        match = re.search(r'(\d{10,})', url)
        return match.group(1) if match else "N/A"
    
    def extract_breadcrumbs(self) -> List[Dict[str, str]]:
        """Extrae la ruta de categorías"""
        breadcrumbs = []
        try:
            crumb_elements = self.driver.find_elements(
                By.CSS_SELECTOR, 
                "[data-module-name='module_breadcrumbNew'] a, .detail-breadcrumb-layout a"
            )
            for crumb in crumb_elements:
                breadcrumbs.append({
                    "name": crumb.text.strip(),
                    "url": crumb.get_attribute("href")
                })
        except Exception as e:
            logger.error(f"Error extrayendo breadcrumbs: {e}")
        return breadcrumbs
    
    def extract_company_info(self) -> Dict[str, any]:
        """Extrae información detallada de la empresa"""
        company_info = {
            "name": "N/A",
            "verified": False,
            "years_active": "N/A",
            "country": "N/A",
            "response_rate": "N/A",
            "response_time": "N/A",
            "transactions": "N/A",
            "main_products": [],
            "certifications": []
        }
        
        try:
            # Nombre de la empresa
            company_info["name"] = self.safe_find_element(None, [
                (By.CSS_SELECTOR, ".company-name a"),
                (By.CSS_SELECTOR, "[data-module-name='module_company'] .company-name")
            ])
            
            # Verificación
            try:
                verified_element = self.driver.find_element(By.CSS_SELECTOR, ".verify-icon, [class*='verified']")
                if verified_element:
                    company_info["verified"] = True
            except NoSuchElementException:
                company_info["verified"] = False
                
            # Años activo
            years = self.safe_find_element(None, [
                (By.CSS_SELECTOR, ".company-life"),
                (By.XPATH, "//*[contains(text(), 'yrs') or contains(text(), 'years')]")
            ])
            company_info["years_active"] = years
            
            # País
            country = self.safe_find_element(None, [
                (By.CSS_SELECTOR, ".register-country"),
                (By.CSS_SELECTOR, ".company-country span:last-child")
            ])
            company_info["country"] = country
            
        except Exception as e:
            logger.warning(f"Error extrayendo info de empresa: {e}")
            
        return company_info
    
    def extract_reviews_info(self) -> Dict[str, any]:
        """Extrae información de reviews y ratings"""
        reviews_info = {
            "rating": "N/A",
            "total_reviews": 0,
            "star_distribution": {},
            "recent_reviews": []
        }
        
        try:
            # Rating
            rating = self.safe_find_element(None, [
                (By.CSS_SELECTOR, "[class*='rating'] strong"),
                (By.XPATH, "(//*[contains(@class, 'star-rating-list')]/following-sibling::*)[1]"),
            ])
            reviews_info["rating"] = rating
            
            # Total reviews
            review_count = self.safe_find_element(None, [
                (By.CSS_SELECTOR, ".detail-review"),
                (By.XPATH, "//*[contains(text(), 'reseña') or contains(text(), 'review')]")
            ])
            
            match = re.search(r'\d+', review_count)
            if match:
                reviews_info["total_reviews"] = int(match.group())
                
        except Exception as e:
            logger.error(f"Error extrayendo reviews: {e}")
            
        return reviews_info
    
    def extract_detailed_pricing(self) -> Dict[str, any]:
        """Extrae información detallada de precios incluyendo MOQ y escalas"""
        pricing_info = {
            "moq": "N/A",
            "price_ranges": [],
            "sample_available": False,
            "sample_price": "N/A",
            "payment_terms": [],
            "trade_terms": []
        }
        
        try:
            # MOQ
            moq_selectors = [
                (By.CSS_SELECTOR, "[data-testid='ladder-price'] div"),
                (By.XPATH, "//*[contains(text(), 'unidad') or contains(text(), 'piece')]"),
                (By.CSS_SELECTOR, ".price-item div:first-child")
            ]
            
            # Extraer rangos de precio
            price_items = self.driver.find_elements(By.CSS_SELECTOR, ".price-item, [data-testid='ladder-price'] > div")
            for item in price_items:
                try:
                    quantity = item.find_element(By.CSS_SELECTOR, "div:first-child").text
                    price = item.find_element(By.CSS_SELECTOR, "div:last-child span").text
                    pricing_info["price_ranges"].append({
                        "quantity": quantity,
                        "price": price
                    })
                except:
                    continue
            
            # Precio de muestra
            try:
                sample_section = self.driver.find_element(By.CSS_SELECTOR, "[data-testid='fortifiedSample']")
                if sample_section:
                    pricing_info["sample_available"] = True
                    sample_price = self.safe_find_element(sample_section, [
                        (By.XPATH, ".//span[contains(text(), 'US$')]"),
                        (By.CSS_SELECTOR, "span:last-child")
                    ])
                    pricing_info["sample_price"] = sample_price
            except NoSuchElementException:
                pricing_info["sample_available"] = False
                
        except Exception as e:
            logger.warning(f"Error extrayendo pricing detallado: {e}")
            
        return pricing_info
    
    def extract_specifications(self) -> Dict[str, str]:
        """Extrae todas las especificaciones del producto"""
        specifications = {}
        
        try:
            # Buscar tabla de atributos
            attr_rows = self.driver.find_elements(
                By.CSS_SELECTOR, 
                "[data-testid='module-attribute'] .id-grid, .module_attribute .id-grid"
            )
            
            for row in attr_rows:
                try:
                    # Buscar clave-valor en cada fila
                    cells = row.find_elements(By.CSS_SELECTOR, "div")
                    if len(cells) >= 2:
                        key = cells[0].text.strip()
                        value = cells[1].text.strip()
                        if key and value:
                            specifications[key] = value
                except:
                    continue
                    
            # Buscar atributos adicionales en otras secciones
            detail_sections = self.driver.find_elements(
                By.CSS_SELECTOR, 
                "[class*='detail-attribute'], [class*='product-attribute']"
            )
            
            for section in detail_sections:
                try:
                    key_elements = section.find_elements(By.CSS_SELECTOR, "[class*='label'], dt")
                    value_elements = section.find_elements(By.CSS_SELECTOR, "[class*='value'], dd")
                    
                    for key_el, value_el in zip(key_elements, value_elements):
                        key = key_el.text.strip()
                        value = value_el.text.strip()
                        if key and value and key not in specifications:
                            specifications[key] = value
                except:
                    continue
                    
        except Exception as e:
            logger.error(f"Error extrayendo especificaciones: {e}")
            
        return specifications
    
    def extract_shipping_info(self) -> Dict[str, any]:
        """Extrae información de envío"""
        shipping_info = {
            "methods": [],
            "lead_time": "N/A",
            "port": "N/A",
            "packaging": {},
            "customs_info": {}
        }
        
        try:
            # Información de empaquetado
            packaging_section = self.driver.find_element(
                By.XPATH, 
                "//h3[contains(text(), 'Embalaje') or contains(text(), 'Packaging')]/following-sibling::div"
            )
            
            if packaging_section:
                packaging_rows = packaging_section.find_elements(By.CSS_SELECTOR, ".id-grid")
                for row in packaging_rows:
                    cells = row.find_elements(By.CSS_SELECTOR, "div")
                    if len(cells) >= 2:
                        key = cells[0].text.strip()
                        value = cells[1].text.strip()
                        shipping_info["packaging"][key] = value
                        
        except Exception as e:
            logger.error(f"Error extrayendo shipping info: {e}")
            
        return shipping_info
    
    def extract_media(self) -> Tuple[List[str], List[str]]:
        """Extrae todas las imágenes y videos del producto"""
        images = []
        videos = []
        
        try:
            # Imágenes principales
            image_thumbnails = self.driver.find_elements(
                By.CSS_SELECTOR, 
                "[data-submodule='ProductImageThumbsList'] div[style*='background-image']"
            )
            
            for thumb in image_thumbnails:
                style = thumb.get_attribute("style")
                match = re.search(r'url\("?([^"]+)"?\)', style)
                if match:
                    img_url = match.group(1)
                    # Obtener versión de alta resolución
                    high_res = img_url.replace("_150x150", "_720x720")
                    images.append(high_res)
            
            # Buscar videos
            video_elements = self.driver.find_elements(
                By.CSS_SELECTOR, 
                "video[src], [class*='video'] source"
            )
            
            for video in video_elements:
                src = video.get_attribute("src")
                if src:
                    videos.append(src)
                    
        except Exception as e:
            logger.error(f"Error extrayendo media: {e}")
            
        return images, videos
    
    def extract_certifications(self) -> List[Dict[str, str]]:
        """Extrae certificaciones del producto"""
        certifications = []
        
        try:
            cert_elements = self.driver.find_elements(
                By.CSS_SELECTOR, 
                "[data-auto-exp='certificateSellingPoints'] img, [class*='certificate'] img"
            )
            
            for cert in cert_elements:
                cert_info = {
                    "image": cert.get_attribute("src"),
                    "alt": cert.get_attribute("alt") or "Certificate"
                }
                certifications.append(cert_info)
                
        except Exception as e:
            logger.error(f"Error extrayendo certificaciones: {e}")
            
        return certifications
    
    def extract_variations(self) -> List[Dict[str, any]]:
        """Extrae variaciones del producto (colores, tamaños, etc)"""
        variations = []
        
        try:
            # Buscar selectores de variación
            variation_sections = self.driver.find_elements(
                By.CSS_SELECTOR, 
                "[class*='variation'], [class*='sku-property'], [data-module-name*='sku']"
            )
            
            for section in variation_sections:
                variation_type = self.safe_find_element(section, [
                    (By.CSS_SELECTOR, "label"),
                    (By.CSS_SELECTOR, ".title")
                ])
                
                options = []
                option_elements = section.find_elements(By.CSS_SELECTOR, "[class*='option'], [class*='value']")
                
                for option in option_elements:
                    option_text = option.text.strip()
                    if option_text:
                        options.append(option_text)
                
                if variation_type != "N/A" and options:
                    variations.append({
                        "type": variation_type,
                        "options": options
                    })
                    
        except Exception as e:
            logger.error(f"Error extrayendo variaciones: {e}")
            
        return variations
    
    def extract_keywords(self) -> List[str]:
        """Extrae keywords y tags del producto"""
        keywords = []
        
        try:
            # Meta keywords
            meta_keywords = self.driver.find_element(By.CSS_SELECTOR, "meta[name='keywords']")
            if meta_keywords:
                content = meta_keywords.get_attribute("content")
                keywords.extend([k.strip() for k in content.split(",") if k.strip()])
            
            # Tags visibles
            tag_elements = self.driver.find_elements(
                By.CSS_SELECTOR, 
                "[class*='tag'], [class*='keyword'], .product-tag"
            )
            
            for tag in tag_elements:
                tag_text = tag.text.strip()
                if tag_text and tag_text not in keywords:
                    keywords.append(tag_text)
                    
        except Exception as e:
            logger.error(f"Error extrayendo keywords: {e}")
            
        return keywords
    
    def scrape_search_results(self, search_term: str, max_price: str = "", 
                            max_pages: int = 1, extract_full_details: bool = True) -> List[Dict]:
        """
        Scraper principal mejorado con extracción completa opcional
        """
        search_query = "+".join(search_term.split())
        all_products = []
        
        # Construir URL con parámetros
        base_url = f"https://www.alibaba.com/trade/search?fsb=y&mergeResult=true&ta=y&tab=all&searchText={search_query}"
        if max_price:
            base_url += f"&pricet={max_price}"
            
        logger.info(f"Iniciando búsqueda: {search_term}")
        self.driver.get(base_url)
        self.random_delay(3, 5)
        
        # Aplicar filtros inteligentes
        self._apply_smart_filters(search_term)
        
        for page_num in range(1, max_pages + 1):
            logger.info(f"Scrapeando página {page_num}")
            
            if page_num > 1:
                self._navigate_to_page(page_num)
                
            # Esperar a que los productos carguen
            try:
                self.wait.until(
                    EC.presence_of_all_elements_located((By.CLASS_NAME, "fy23-search-card"))
                )
            except TimeoutException:
                logger.warning(f"No se encontraron productos en la página {page_num}")
                break
                
            # Scroll gradual para cargar lazy-loaded content
            self._gradual_scroll()
            
            # Extraer productos de la página actual
            products = self._extract_products_from_page(extract_full_details)
            all_products.extend(products)
            
            # Verificar si hay más páginas
            if not self._has_next_page():
                logger.info("No hay más páginas disponibles")
                break
                
        logger.info(f"Scraping completado. Total productos: {len(all_products)}")
        return all_products
    
    def _apply_smart_filters(self, search_term: str):
        """Aplica filtros de forma inteligente basándose en el término de búsqueda"""
        try:
            # Esperar a que la sección de filtros esté presente
            self.wait.until(
                EC.presence_of_element_located((By.CLASS_NAME, "searchx-filter-wrapper"))
            )
            
            applied_filters = 0
            search_words = search_term.lower().split()
            
            # Intentar aplicar hasta 3 filtros relevantes
            for _ in range(3): # Limitar los reintentos para evitar bucles infinitos
                if applied_filters >= 3:
                    break
                
                try:
                    filter_section = self.driver.find_element(By.CLASS_NAME, "searchx-filter-wrapper")
                    filters = filter_section.find_elements(By.CSS_SELECTOR, ".searchx-filter-item__label")
                    
                    applied_this_iteration = False
                    for filter_element in filters:
                        filter_text = filter_element.text.strip().lower()
                        
                        if any(word in filter_text for word in search_words):
                            try:
                                # Usar un closure para comprobar si el elemento sigue siendo válido
                                def click_if_valid(el):
                                    try:
                                        el.click()
                                        return True
                                    except StaleElementReferenceException:
                                        return False

                                self.scroll_to_element(filter_element)
                                if click_if_valid(filter_element):
                                    applied_filters += 1
                                    logger.info(f"Filtro aplicado: {filter_text}")
                                    self.random_delay(2, 4) # Esperar un poco más a que la página se recargue
                                    applied_this_iteration = True
                                    break # Salir del bucle de filtros y volver a buscar
                                else:
                                    logger.warning(f"Elemento de filtro '{filter_text}' se volvió obsoleto. Reintentando...")
                                    break

                            except Exception as e:
                                logger.warning(f"No se pudo aplicar filtro '{filter_text}': {e}")
                    
                    if not applied_this_iteration:
                        # Si no se aplicó ningún filtro en esta iteración, salir
                        break
                        
                except (NoSuchElementException, StaleElementReferenceException):
                    logger.warning("Sección de filtros no encontrada o obsoleta, reintentando búsqueda de filtros...")
                    self.random_delay(1, 2)
                    continue # Reintentar el bucle principal

        except Exception as e:
            logger.warning(f"No se pudieron aplicar filtros: {e}")
    
    def _gradual_scroll(self):
        """Realiza scroll gradual para cargar contenido lazy-loaded"""
        total_height = self.driver.execute_script("return document.body.scrollHeight")
        viewport_height = self.driver.execute_script("return window.innerHeight")
        
        current_position = 0
        while current_position < total_height:
            # Scroll suave
            self.driver.execute_script(f"window.scrollTo(0, {current_position});")
            current_position += viewport_height // 2
            self.random_delay(0.5, 1)
            
            # Actualizar altura total (puede cambiar con lazy loading)
            total_height = self.driver.execute_script("return document.body.scrollHeight")
    
    def _extract_products_from_page(self, extract_full_details: bool) -> List[Dict]:
        """Extrae productos de la página actual de forma robusta."""
        product_data_list = []
        
        # 1. Extraer la información básica y los enlaces de todos los productos en la página.
        try:
            product_containers = self.driver.find_elements(By.CLASS_NAME, "fy23-search-card")
            logger.info(f"Encontrados {len(product_containers)} productos en la página")

            for container in product_containers:
                try:
                    product_data = self._extract_product_from_container(container)
                    if product_data["product_link"] != "N/A":
                        product_data_list.append(product_data)
                except StaleElementReferenceException:
                    logger.warning("Contenedor de producto obsoleto, saltando.")
                    continue
        except Exception as e:
            logger.error(f"Error crítico extrayendo la lista de productos: {e}")
            return []

        if not extract_full_details:
            return product_data_list

        # 2. Iterar sobre la lista de enlaces para extraer los detalles completos.
        #    Esto evita problemas de StaleElementReferenceException al navegar fuera de la página.
        detailed_products = []
        for i, product_data in enumerate(product_data_list, 1):
            try:
                logger.info(f"Extrayendo detalles del producto {i}/{len(product_data_list)}...")
                detailed_info = self.extract_product_details(product_data["product_link"])
                product_data.update(detailed_info)
                detailed_products.append(product_data)
                logger.info(f"Producto {i} extraído: {product_data.get('title', 'N/A')[:50]}...")
            except Exception as e:
                logger.error(f"Error extrayendo detalles de {product_data['product_link']}: {e}")
                # Añadir la información básica aunque fallen los detalles
                detailed_products.append(product_data)
        
        return detailed_products
    
    def _extract_product_from_container(self, container) -> Dict[str, any]:
        """Extrae información básica del producto desde el contenedor de búsqueda"""
        product_data = {
            "title": self.safe_find_element(container, [
                (By.CSS_SELECTOR, ".search-card-e-title a span"),
                (By.CSS_SELECTOR, "h2 a"),
                (By.CSS_SELECTOR, "[class*='title'] a")
            ]),
            "product_link": self.safe_get_attribute(container, [
                (By.CSS_SELECTOR, ".search-card-e-title a"),
                (By.CSS_SELECTOR, "h2 a"),
                (By.CSS_SELECTOR, "[class*='title'] a")
            ], "href"),
            "main_image": self.safe_get_attribute(container, [
                (By.CSS_SELECTOR, ".search-card-e-slider__img"),
                (By.CSS_SELECTOR, "img[class*='product']"),
                (By.CSS_SELECTOR, "[class*='image'] img")
            ], "src"),
            "company_name": self.safe_find_element(container, [
                (By.CSS_SELECTOR, ".search-card-e-company"),
                (By.CSS_SELECTOR, "[class*='supplier']"),
                (By.CSS_SELECTOR, "[class*='company']")
            ]),
            "moq": self.safe_find_element(container, [
                (By.CSS_SELECTOR, ".search-card-m-sale-features__item"),
                (By.CSS_SELECTOR, "[class*='moq']"),
                (By.XPATH, ".//*[contains(text(), 'MOQ')]")
            ]),
            "certifications": self._extract_search_certifications(container),
            "trade_assurance": self._check_trade_assurance(container),
            "response_rate": self.safe_find_element(container, [
                (By.CSS_SELECTOR, "[class*='response']"),
                (By.XPATH, ".//*[contains(text(), '%')]")
            ])
        }
        
        # Extraer información de precio
        price_info = self.extract_price_info(container)
        product_data.update(price_info)
        
        # Extraer rating
        rating_info = {
            "rating": self.safe_find_element(container, [
                (By.CSS_SELECTOR, ".search-card-e-review strong"),
                (By.CSS_SELECTOR, "[class*='rating'] strong")
            ]),
            "review_count": self.safe_find_element(container, [
                (By.CSS_SELECTOR, ".search-card-e-review span"),
                (By.XPATH, ".//*[contains(text(), 'review')]")
            ])
        }
        product_data.update(rating_info)
        
        return product_data
    
    def _extract_search_certifications(self, container) -> List[str]:
        """Extrae certificaciones desde el contenedor de búsqueda"""
        certs = []
        try:
            cert_elements = container.find_elements(By.CSS_SELECTOR, "[class*='cert'] img, [class*='badge']")
            for cert in cert_elements:
                alt_text = cert.get_attribute("alt") or cert.get_attribute("title")
                if alt_text:
                    certs.append(alt_text)
        except:
            pass
        return certs
    
    def _check_trade_assurance(self, container) -> bool:
        """Verifica si el producto tiene Trade Assurance"""
        try:
            ta_element = container.find_element(By.XPATH, ".//*[contains(text(), 'Trade Assurance')]")
            return True if ta_element else False
        except:
            return False
    
    def _navigate_to_page(self, page_num: int):
        """Navega a una página específica"""
        try:
            # Método 1: Modificar URL
            current_url = self.driver.current_url
            if "page=" in current_url:
                new_url = re.sub(r'page=\d+', f'page={page_num}', current_url)
            else:
                separator = "&" if "?" in current_url else "?"
                new_url = f"{current_url}{separator}page={page_num}"
                
            self.driver.get(new_url)
            self.random_delay(3, 5)
            
        except Exception as e:
            logger.error(f"Error navegando a página {page_num}: {e}")
    
    def _has_next_page(self) -> bool:
        """Verifica si hay una página siguiente"""
        try:
            # Buscar botón de siguiente página
            next_button = self.driver.find_element(
                By.CSS_SELECTOR, 
                ".pagination-next:not(.disabled), [class*='next']:not([disabled])"
            )
            return next_button.is_enabled()
        except:
            return False


def main():
    """Función principal con configuración mejorada"""
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    
    # Configuración del navegador
    options = ChromeOptions()
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    # Modo headless opcional
    # options.add_argument('--headless')
    
    # Input del usuario
    search_term = input("Ingrese el producto a buscar: ")
    max_price = input("Ingrese el precio máximo (dejar vacío para sin límite): ")
    max_pages = int(input("Número máximo de páginas a scrapear (default: 1): ") or "1")
    extract_details = input("¿Extraer detalles completos de cada producto? (s/n): ").lower() == 's'
    
    # Inicializar driver y scraper
    driver = webdriver.Chrome(options=options)
    scraper = AlibabaAdvancedScraper(driver)
    
    try:
        # Ejecutar scraping
        products = scraper.scrape_search_results(
            search_term=search_term,
            max_price=max_price,
            max_pages=max_pages,
            extract_full_details=extract_details
        )
        
        # Guardar resultados
        if products:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"alibaba_{search_term.replace(' ', '_')}_{timestamp}.json"
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(products, f, indent=2, ensure_ascii=False)
                
            print(f"\n✅ Scraping completado exitosamente!")
            print(f"📊 Total de productos extraídos: {len(products)}")
            print(f"💾 Resultados guardados en: {filename}")
            
            # Mostrar resumen
            if products:
                print("\n📋 Resumen de campos extraídos del primer producto:")
                first_product = products[0]
                for key, value in first_product.items():
                    if isinstance(value, dict):
                        print(f"  - {key}: {len(value)} campos")
                    elif isinstance(value, list):
                        print(f"  - {key}: {len(value)} elementos")
                    else:
                        print(f"  - {key}: {'✓' if value != 'N/A' else '✗'}")
        else:
            print("\n❌ No se encontraron productos para los criterios especificados.")
            
    except Exception as e:
        logger.error(f"Error durante el scraping: {e}")
        
    finally:
        driver.quit()


if __name__ == "__main__":
    main()