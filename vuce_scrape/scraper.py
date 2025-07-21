import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
import logging

# Configurar logging detallado
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('vuce_scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class VuceARScraper:
    """
    Scraper inteligente para VUCE Argentina usando Playwright.
    Navega como un usuario real e intercepta las llamadas a la API.
    """
    
    def __init__(self):
        self.base_url = "https://www.vuce.gob.ar/posicionesArancelarias"
        self.api_data = []
        self.browser = None
        self.context = None
        self.page = None
        
    async def setup_browser(self):
        """Configura el navegador con opciones optimizadas."""
        logger.info("Iniciando navegador Playwright...")
        
        self.playwright = await async_playwright().start()
        
        # Configurar navegador con opciones optimizadas
        self.browser = await self.playwright.chromium.launch(
            headless=False,  # Visible para debugging
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor'
            ]
        )
        
        # Configurar contexto con user agent realista
        self.context = await self.browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080}
        )
        
        self.page = await self.context.new_page()
        
        # Interceptar llamadas a la API
        await self.setup_api_interception()
        
        logger.info("Navegador configurado exitosamente")
        
    async def setup_api_interception(self):
        """Configura la interceptación de llamadas a la API."""
        logger.info("Configurando interceptación de API...")
        
        async def handle_response(response):
            """Maneja las respuestas de la API."""
            url = response.url
            method = response.request.method
            
            # Interceptar TODAS las llamadas para debugging completo
            if method == "POST" or "api" in url.lower() or "posiciones" in url.lower():
                logger.info(f"🔍 POST/API detectada: {method} {url}")
                
                try:
                    content_type = response.headers.get('content-type', '')
                    logger.info(f"   Content-Type: {content_type}")
                    
                    if 'json' in content_type.lower():
                        json_data = await response.json()
                        logger.info(f"📊 JSON obtenido: {len(json_data) if isinstance(json_data, list) else 'objeto'}")
                        
                        if isinstance(json_data, list) and len(json_data) > 0:
                            self.api_data = json_data
                            logger.info(f"✅ DATOS CAPTURADOS: {len(json_data)} registros")
                        elif isinstance(json_data, dict):
                            logger.info(f"📋 Objeto: {list(json_data.keys())}")
                            # Buscar datos en el objeto
                            for key, value in json_data.items():
                                if isinstance(value, list) and len(value) > 0:
                                    self.api_data = value
                                    logger.info(f"✅ Datos en '{key}': {len(value)} registros")
                                    break
                    else:
                        # Intentar parsear como JSON aunque no diga que es JSON
                        try:
                            text = await response.text()
                            if text.strip().startswith('[') or text.strip().startswith('{'):
                                json_data = json.loads(text)
                                logger.info(f"📊 JSON manual: {len(json_data) if isinstance(json_data, list) else 'objeto'}")
                                if isinstance(json_data, list) and len(json_data) > 0:
                                    self.api_data = json_data
                                    logger.info(f"✅ DATOS CAPTURADOS MANUAL: {len(json_data)} registros")
                        except Exception as parse_error:
                            logger.debug(f"No es JSON válido: {str(parse_error)[:100]}")
                        
                except Exception as e:
                    logger.error(f"Error procesando respuesta: {e}")
        
        # Escuchar todas las respuestas
        self.page.on("response", handle_response)
        
        # También interceptar requests para debugging
        async def handle_request(request):
            """Maneja las peticiones para debugging."""
            url = request.url
            method = request.method
            
            if method == "POST":
                logger.info(f"🌐 POST Request: {url}")
                if request.post_data:
                    logger.info(f"📤 Post data: {request.post_data[:200]}...")
        
        self.page.on("request", handle_request)

    async def navigate_to_site(self):
        """Navega al sitio principal."""
        logger.info(f"Navegando a: {self.base_url}")
        
        try:
            await self.page.goto(self.base_url, wait_until='networkidle')
            logger.info("Página cargada exitosamente")
            
            # Esperar más tiempo para que se carguen todos los recursos JavaScript
            logger.info("⏳ Esperando carga completa de JavaScript...")
            await asyncio.sleep(10)
            
            # Verificar que la página esté completamente cargada
            await self.page.wait_for_load_state('domcontentloaded')
            await self.page.wait_for_load_state('networkidle')
            
            logger.info("✅ Página completamente cargada")
            
            # Analizar el contenido de la página
            await self._analyze_page_content()
            
        except Exception as e:
            logger.error(f"Error navegando al sitio: {e}")
            raise
    
    async def _analyze_page_content(self):
        """Analiza el contenido de la página para entender la estructura."""
        logger.info("🔍 Analizando contenido de la página...")
        
        try:
            # Obtener el HTML completo
            html_content = await self.page.content()
            
            # Buscar patrones específicos en el HTML
            import re
            
            # Buscar URLs de API en el HTML
            api_patterns = [
                r'["\']([^"\']*api[^"\']*)["\']',
                r'["\']([^"\']*posiciones[^"\']*)["\']',
                r'["\']([^"\']*arancel[^"\']*)["\']',
                r'["\']([^"\']*busqueda[^"\']*)["\']',
                r'["\']([^"\']*search[^"\']*)["\']'
            ]
            
            found_urls = set()
            for pattern in api_patterns:
                matches = re.findall(pattern, html_content, re.IGNORECASE)
                for match in matches:
                    if match.startswith('/') or 'http' in match:
                        found_urls.add(match)
            
            if found_urls:
                logger.info(f"🔗 URLs encontradas en HTML: {list(found_urls)}")
            
            # Buscar funciones JavaScript
            js_functions = re.findall(r'function\s+(\w+)\s*\(', html_content)
            if js_functions:
                logger.info(f"🔧 Funciones JS encontradas: {js_functions[:10]}...")
            
            # Buscar variables globales
            global_vars = re.findall(r'window\.(\w+)\s*=', html_content)
            if global_vars:
                logger.info(f"🌐 Variables globales: {global_vars[:10]}...")
            
            # Analizar archivos JavaScript específicos
            await self._analyze_js_files()
            
        except Exception as e:
            logger.error(f"Error analizando contenido: {e}")
    
    async def _analyze_js_files(self):
        """Analiza los archivos JavaScript específicos para encontrar la API."""
        logger.info("🔍 Analizando archivos JavaScript específicos...")
        
        js_files = [
            "https://www.vuce.gob.ar/PosicionesArancelarias52867.js",
            "https://www.vuce.gob.ar/BusquedaArbol52867.js"
        ]
        
        for js_url in js_files:
            try:
                logger.info(f"📄 Analizando: {js_url}")
                
                # Obtener el contenido del archivo JS
                response = await self.page.evaluate(f"""
                    async () => {{
                        try {{
                            const response = await fetch('{js_url}');
                            const text = await response.text();
                            return {{ success: true, content: text }};
                        }} catch (error) {{
                            return {{ success: false, error: error.message }};
                        }}
                    }}
                """)
                
                if response.get('success'):
                    js_content = response.get('content')
                    
                    # Buscar patrones específicos en el JS
                    import re
                    
                    # Buscar URLs de API
                    api_urls = re.findall(r'["\']([^"\']*posiciones[^"\']*busqueda[^"\']*)["\']', js_content)
                    if api_urls:
                        logger.info(f"🔗 URLs de API en {js_url}: {api_urls}")
                    
                    # Buscar funciones de búsqueda
                    search_functions = re.findall(r'function\s+(\w*[Bb]uscar\w*)\s*\(', js_content)
                    if search_functions:
                        logger.info(f"🔍 Funciones de búsqueda en {js_url}: {search_functions}")
                    
                    # Buscar llamadas fetch
                    fetch_calls = re.findall(r'fetch\s*\(\s*["\']([^"\']+)["\']', js_content)
                    if fetch_calls:
                        logger.info(f"🌐 Llamadas fetch en {js_url}: {fetch_calls}")
                    
                    # Buscar payloads
                    payload_patterns = re.findall(r'JSON\.stringify\s*\(\s*(\{[^}]+\})', js_content)
                    if payload_patterns:
                        logger.info(f"📦 Payloads en {js_url}: {payload_patterns}")
                    
                else:
                    logger.warning(f"❌ No se pudo obtener {js_url}: {response.get('error')}")
                    
            except Exception as e:
                logger.error(f"Error analizando {js_url}: {e}")
    
    async def trigger_search(self):
        """Activa la búsqueda para obtener todos los datos."""
        logger.info("Activando búsqueda de posiciones arancelarias...")
        
        try:
            # Tomar screenshot para debugging
            await self.page.screenshot(path="debug_page.png")
            logger.info("📸 Screenshot guardado como debug_page.png")
            
            # Estrategia 1: Buscar elementos específicos de la interfaz
            search_triggered = await self._try_interface_elements()
            
            if not search_triggered:
                # Estrategia 2: Intentar activar con JavaScript directo
                search_triggered = await self._try_javascript_activation()
            
            if not search_triggered:
                # Estrategia 3: Intentar diferentes eventos
                search_triggered = await self._try_event_triggers()
            
            if not search_triggered:
                # Estrategia 4: Intentar hacer clic en cualquier elemento interactivo
                search_triggered = await self._try_click_everything()
            
            if not search_triggered:
                # Estrategia 5: Intentar llamadas directas a API conocidas
                search_triggered = await self._try_direct_api_calls()
            
            # Esperar a que se procese la búsqueda
            logger.info("⏳ Esperando respuesta de la API...")
            await asyncio.sleep(10)
            
            # Tomar otro screenshot después de la búsqueda
            await self.page.screenshot(path="debug_after_search.png")
            logger.info("📸 Screenshot post-búsqueda guardado como debug_after_search.png")
            
        except Exception as e:
            logger.error(f"Error activando búsqueda: {e}")
    
    async def _try_interface_elements(self):
        """Intenta encontrar y activar elementos de la interfaz."""
        logger.info("🔍 Buscando elementos de interfaz...")
        
        search_selectors = [
            'input[type="text"]',
            'input[placeholder*="buscar"]',
            'input[placeholder*="código"]',
            'input[placeholder*="descripción"]',
            'input[placeholder*="search"]',
            'input[placeholder*="position"]',
            'button[type="submit"]',
            'button:has-text("Buscar")',
            'button:has-text("Search")',
            'button:has-text("Consultar")',
            'button:has-text("Filtrar")',
            '.search-button',
            '#search-button',
            '[data-testid*="search"]',
            '.btn-search',
            '.btn-buscar',
            '.btn-consultar',
            '.btn-filtrar'
        ]
        
        for selector in search_selectors:
            try:
                element = await self.page.query_selector(selector)
                if element:
                    logger.info(f"🎯 Elemento encontrado: {selector}")
                    
                    # Verificar si es visible
                    is_visible = await element.is_visible()
                    logger.info(f"   Visible: {is_visible}")
                    
                    if is_visible:
                        if 'input' in selector:
                            # Es un campo de texto, limpiarlo y presionar Enter
                            await element.fill("")
                            await element.press("Enter")
                            logger.info("✅ Búsqueda activada con Enter")
                            return True
                        elif 'button' in selector:
                            # Es un botón, hacer clic
                            await element.click()
                            logger.info("✅ Búsqueda activada con clic en botón")
                            return True
                    else:
                        logger.info(f"   Elemento no visible, saltando...")
                        
            except Exception as e:
                logger.debug(f"Selector {selector} no funcionó: {e}")
                continue
        
        return False
    
    async def _try_javascript_activation(self):
        """Intenta activar la búsqueda con JavaScript directo."""
        logger.info("🔧 Intentando activación con JavaScript...")
        
        try:
            result = await self.page.evaluate("""
                console.log('=== ACTIVACIÓN JAVASCRIPT ===');
                
                // Lista de funciones posibles
                const functions = [
                    'buscarPosiciones',
                    'searchPositions', 
                    'buscar',
                    'search',
                    'consultar',
                    'filtrar',
                    'loadData',
                    'loadPositions',
                    'getData',
                    'fetchData'
                ];
                
                // Intentar cada función
                for (const funcName of functions) {
                    if (window[funcName] && typeof window[funcName] === 'function') {
                        console.log('Llamando:', funcName);
                        try {
                            window[funcName]();
                            return { success: true, function: funcName };
                        } catch (e) {
                            console.log('Error en', funcName, ':', e);
                        }
                    }
                }
                
                // Intentar disparar eventos
                const events = ['search', 'load', 'data', 'positions'];
                for (const eventName of events) {
                    console.log('Disparando evento:', eventName);
                    try {
                        const event = new Event(eventName);
                        document.dispatchEvent(event);
                    } catch (e) {
                        console.log('Error disparando', eventName, ':', e);
                    }
                }
                
                // Intentar activar cualquier función que contenga 'buscar' o 'search'
                for (const key in window) {
                    if (typeof window[key] === 'function' && 
                        (key.toLowerCase().includes('buscar') || 
                         key.toLowerCase().includes('search') ||
                         key.toLowerCase().includes('position'))) {
                        console.log('Función encontrada:', key);
                        try {
                            window[key]();
                            return { success: true, function: key };
                        } catch (e) {
                            console.log('Error en', key, ':', e);
                        }
                    }
                }
                
                return { success: false, message: 'No se encontraron funciones' };
            """)
            
            if result.get('success'):
                logger.info(f"✅ JavaScript ejecutado: {result.get('function')}")
                return True
            else:
                logger.info(f"❌ JavaScript no encontró funciones: {result.get('message')}")
                return False
                
        except Exception as e:
            logger.error(f"Error ejecutando JavaScript: {e}")
            return False
    
    async def _try_event_triggers(self):
        """Intenta activar eventos específicos."""
        logger.info("🎯 Intentando activar eventos...")
        
        try:
            # Intentar diferentes tipos de eventos
            events = ['search', 'load', 'data', 'positions', 'submit', 'change']
            
            for event_name in events:
                try:
                    await self.page.evaluate(f"""
                        console.log('Disparando evento: {event_name}');
                        const event = new Event('{event_name}');
                        document.dispatchEvent(event);
                    """)
                    logger.info(f"✅ Evento disparado: {event_name}")
                    await asyncio.sleep(2)
                except Exception as e:
                    logger.debug(f"Error disparando evento {event_name}: {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error activando eventos: {e}")
            return False
    
    async def _try_click_everything(self):
        """Intenta hacer clic en cualquier elemento interactivo."""
        logger.info("🖱️ Intentando clic en elementos interactivos...")
        
        try:
            # Buscar todos los botones
            buttons = await self.page.query_selector_all('button')
            logger.info(f"Encontrados {len(buttons)} botones")
            
            for i, button in enumerate(buttons):
                try:
                    text = await button.text_content()
                    is_visible = await button.is_visible()
                    
                    if is_visible and text:
                        logger.info(f"Botón {i}: '{text.strip()}'")
                        
                        # Hacer clic en botones que parezcan relevantes
                        if any(keyword in text.lower() for keyword in [
                            'buscar', 'search', 'consultar', 'filtrar', 'cargar', 'load'
                        ]):
                            await button.click()
                            logger.info(f"✅ Clic en botón: '{text.strip()}'")
                            return True
                            
                except Exception as e:
                    logger.debug(f"Error con botón {i}: {e}")
                    continue
            
            # Buscar enlaces que parezcan de búsqueda
            links = await self.page.query_selector_all('a')
            logger.info(f"Encontrados {len(links)} enlaces")
            
            for i, link in enumerate(links):
                try:
                    text = await link.text_content()
                    is_visible = await link.is_visible()
                    
                    if is_visible and text:
                        if any(keyword in text.lower() for keyword in [
                            'buscar', 'search', 'consultar', 'filtrar'
                        ]):
                            await link.click()
                            logger.info(f"✅ Clic en enlace: '{text.strip()}'")
                            return True
                            
                except Exception as e:
                    logger.debug(f"Error con enlace {i}: {e}")
                    continue
            
            return False
            
        except Exception as e:
            logger.error(f"Error haciendo clic: {e}")
            return False
    
    async def _try_direct_api_calls(self):
        """Intenta hacer llamadas directas a APIs conocidas."""
        logger.info("🌐 Intentando llamadas directas a API...")
        
        # URLs de API que podrían funcionar basándose en los archivos JS que vimos
        api_endpoints = [
            "https://www.vuce.gob.ar/posicionesArancelarias/busqueda",
            "https://www.vuce.gob.ar/api/posiciones",
            "https://www.vuce.gob.ar/api/arancel",
            "https://www.vuce.gob.ar/api/busqueda",
            "https://qa.api.ci.vuce.gob.ar/posiciones",
            "https://qa.api.ci.vuce.gob.ar/arancel",
            "https://qa.api.ci.vuce.gob.ar/busqueda",
            "https://www.vuce.gob.ar/historialCambiosPosiciones/busqueda"
        ]
        
        # Payloads posibles
        payloads = [
            {},
            {"codigo": "", "descripcion": "", "capitulo": "", "seccion": ""},
            {"search": "", "filter": ""},
            {"query": "", "type": "all"},
            {"action": "search", "params": {}},
            {"filtros": {"codigo": "", "descripcion": ""}},
            {"criterios": {"codigo": "", "descripcion": ""}}
        ]
        
        for endpoint in api_endpoints:
            for payload in payloads:
                try:
                    logger.info(f"🔍 Probando: {endpoint} con payload: {payload}")
                    
                    # Hacer la llamada directamente desde el navegador
                    result = await self.page.evaluate(f"""
                        async () => {{
                            try {{
                                const response = await fetch('{endpoint}', {{
                                    method: 'POST',
                                    headers: {{
                                        'Content-Type': 'application/json',
                                        'Accept': 'application/json',
                                        'X-Requested-With': 'XMLHttpRequest'
                                    }},
                                    body: JSON.stringify({json.dumps(payload)})
                                }});
                                
                                if (response.ok) {{
                                    const data = await response.json();
                                    return {{ success: true, data: data, endpoint: '{endpoint}' }};
                                }} else {{
                                    return {{ success: false, status: response.status, endpoint: '{endpoint}' }};
                                }}
                            }} catch (error) {{
                                return {{ success: false, error: error.message, endpoint: '{endpoint}' }};
                            }}
                        }}
                    """)
                    
                    if result.get('success'):
                        data = result.get('data')
                        if isinstance(data, list) and len(data) > 0:
                            self.api_data = data
                            logger.info(f"✅ DATOS OBTENIDOS DIRECTAMENTE: {len(data)} registros desde {endpoint}")
                            return True
                        elif isinstance(data, dict):
                            # Buscar datos en el objeto
                            for key, value in data.items():
                                if isinstance(value, list) and len(value) > 0:
                                    self.api_data = value
                                    logger.info(f"✅ Datos en '{key}': {len(value)} registros desde {endpoint}")
                                    return True
                    else:
                        logger.debug(f"❌ {endpoint}: {result.get('error', result.get('status'))}")
                        
                except Exception as e:
                    logger.debug(f"Error probando {endpoint}: {e}")
                    continue
        
        # Si no funcionó, intentar con GET
        logger.info("🔄 Intentando con método GET...")
        for endpoint in api_endpoints:
            try:
                logger.info(f"🔍 Probando GET: {endpoint}")
                
                result = await self.page.evaluate(f"""
                    async () => {{
                        try {{
                            const response = await fetch('{endpoint}', {{
                                method: 'GET',
                                headers: {{
                                    'Accept': 'application/json',
                                    'X-Requested-With': 'XMLHttpRequest'
                                }}
                            }});
                            
                            if (response.ok) {{
                                const data = await response.json();
                                return {{ success: true, data: data, endpoint: '{endpoint}' }};
                            }} else {{
                                return {{ success: false, status: response.status, endpoint: '{endpoint}' }};
                            }}
                        }} catch (error) {{
                            return {{ success: false, error: error.message, endpoint: '{endpoint}' }};
                        }}
                    }}
                """)
                
                if result.get('success'):
                    data = result.get('data')
                    if isinstance(data, list) and len(data) > 0:
                        self.api_data = data
                        logger.info(f"✅ DATOS OBTENIDOS CON GET: {len(data)} registros desde {endpoint}")
                        return True
                    elif isinstance(data, dict):
                        for key, value in data.items():
                            if isinstance(value, list) and len(value) > 0:
                                self.api_data = value
                                logger.info(f"✅ Datos en '{key}' (GET): {len(value)} registros desde {endpoint}")
                                return True
                else:
                    logger.debug(f"❌ GET {endpoint}: {result.get('error', result.get('status'))}")
                    
            except Exception as e:
                logger.debug(f"Error probando GET {endpoint}: {e}")
                continue
        
        return False
            
    async def wait_for_data(self, timeout=60):
        """Espera a que se carguen los datos con timeout."""
        logger.info(f"⏳ Esperando datos (timeout: {timeout}s)...")
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.api_data:
                logger.info(f"✅ Datos obtenidos: {len(self.api_data)} registros")
                return True
            await asyncio.sleep(1)
            
        logger.warning("⏰ Timeout esperando datos")
        return False
        
    async def save_data(self):
        """Guarda los datos obtenidos en archivos estructurados."""
        if not self.api_data:
            logger.warning("No hay datos para guardar")
            return
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Crear directorio para los datos
        data_dir = Path("vuce_data")
        data_dir.mkdir(exist_ok=True)
        
        # Guardar datos completos en JSON
        json_file = data_dir / f"posiciones_arancelarias_{timestamp}.json"
        try:
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(self.api_data, f, ensure_ascii=False, indent=2)
            logger.info(f"✅ Datos guardados en: {json_file}")
        except Exception as e:
            logger.error(f"Error guardando JSON: {e}")
            
        # Crear archivo de resumen
        summary_file = data_dir / f"resumen_{timestamp}.txt"
        try:
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write(f"SCRAPER VUCE ARGENTINA - RESUMEN\n")
                f.write(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Total de registros: {len(self.api_data)}\n")
                f.write(f"Archivo de datos: {json_file.name}\n\n")
                
                # Mostrar estructura de los datos
                if self.api_data:
                    f.write("ESTRUCTURA DE DATOS:\n")
                    sample = self.api_data[0]
                    for key, value in sample.items():
                        f.write(f"  {key}: {type(value).__name__}\n")
                        
            logger.info(f"✅ Resumen guardado en: {summary_file}")
        except Exception as e:
            logger.error(f"Error guardando resumen: {e}")
            
        # Mostrar estadísticas
        logger.info(f"📊 ESTADÍSTICAS:")
        logger.info(f"   - Total de registros: {len(self.api_data)}")
        if self.api_data:
            logger.info(f"   - Primer registro: {list(self.api_data[0].keys())}")
            
    async def run(self):
        """Ejecuta el scraper completo."""
        logger.info("🚀 Iniciando scraper inteligente para VUCE Argentina")
        
        try:
            # Configurar navegador
            await self.setup_browser()
            
            # Navegar al sitio
            await self.navigate_to_site()
            
            # Activar búsqueda
            await self.trigger_search()
            
            # Esperar datos
            data_obtained = await self.wait_for_data()
            
            if data_obtained:
                # Guardar datos
                await self.save_data()
                logger.info("✅ Scraping completado exitosamente")
            else:
                logger.error("❌ No se pudieron obtener los datos")
                
        except Exception as e:
            logger.error(f"❌ Error en el scraper: {e}")
            raise
            
        finally:
            # Limpiar recursos
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            logger.info("🧹 Recursos liberados")

async def main():
    """Función principal."""
    scraper = VuceARScraper()
    await scraper.run()

if __name__ == "__main__":
    asyncio.run(main())
