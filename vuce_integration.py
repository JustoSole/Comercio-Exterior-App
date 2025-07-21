#!/usr/bin/env python3
"""
🇦🇷 VUCE Integration - Integración con Sistema VUCE Argentina
============================================================

Módulo para extraer información arancelaria desde VUCE.
Intercepta las llamadas XHR y extrae los datos de aranceles de forma automática.

Funcionalidades:
- Extracción de información arancelaria por código NCM
- Validación de códigos NCM en base oficial
- Extracción de alícuotas de impuestos
- Análisis de régimen simplificado
- Detección de intervenciones requeridas

Autor: Desarrollado para comercio exterior
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
import re

try:
    from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VuceIntegration:
    """Integración con el sistema VUCE de Argentina para extraer información arancelaria."""
    
    def __init__(self, headless: bool = True, timeout: int = 30000):
        """
        Inicializar la integración con VUCE
        
        Args:
            headless: Si ejecutar el navegador en modo headless
            timeout: Timeout en milisegundos
        """
        self.headless = headless
        self.timeout = timeout
        self.base_url = "https://www.vuce.gob.ar"
        
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError("Playwright no está instalado. Instalar con: pip install playwright")
    
    async def _extract_terminales_recursively(self, nodo: Dict, terminales: List[Dict]) -> None:
        """
        Recorre recursivamente el JSON devolviendo los nodos terminales.
        
        Args:
            nodo: Nodo actual del JSON
            terminales: Lista donde se almacenan los nodos terminales encontrados
        """
        if not isinstance(nodo, dict):
            return
        
        actual = nodo.get("actual")
        if not actual:
            return
        
        hijo = actual.get("hijo")
        if not hijo:
            # Nodo terminal - no tiene más hijos
            terminal_info = {
                "codigo": actual.get("posicion"),
                "descripcion": actual.get("descripcion"),
                "derechos_importacion_intrazona": actual.get("derechos_importacion_intrazona"),
                "arancel_externo_comun": actual.get("arancel_externo_comun"),
                "derechos_importacion_extrazona": actual.get("derechos_importacion_extrazona"),
                "derechos_exportacion": actual.get("derechos_exportacion"),
                "reintegros_extrazona": actual.get("reintegros_extrazona"),
                "reintegros_intrazona": actual.get("reintegros_intrazona"),
                "unidad": actual.get("unidad"),
                "actualizado": actual.get("actualizado"),
                "activo": actual.get("activo", 0) == 1,
                "texto_partida": actual.get("texto_partida"),
                "bk": actual.get("bk", 0),
                "bit": actual.get("bit", 0),
                "la": actual.get("la", 0) == 1  # Licencia automática
            }
            terminales.append(terminal_info)
            logger.info(f"Encontrado terminal: {terminal_info['codigo']} - {terminal_info['descripcion'][:50]}...")
        else:
            # Nodo con hijo - continuar recursivamente
            await self._extract_terminales_recursively({"actual": hijo.get("actual")}, terminales)
    
    async def _fetch_from_vuce_url(self, page_url: str, posicion_formateada: str) -> Dict[str, Any]:
        """Ejecuta Playwright para obtener datos de una URL de VUCE."""
        api_path_snippet = "/posicionesPosicion"
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            page = await browser.new_page()
            
            try:
                responses = []
                page.on("response", lambda response: responses.append(response))
                
                await page.goto(page_url, wait_until="networkidle", timeout=self.timeout)
                await page.wait_for_timeout(3000)
                
                target_response = next((r for r in responses if api_path_snippet in r.url and r.status == 200), None)
                
                if not target_response:
                    logger.error(f"No se encontró la respuesta JSON para {posicion_formateada} en {page_url}")
                    return {"error": "No se encontró información arancelaria", "success": False}
                
                data = await target_response.json()
                logger.info(f"JSON extraído exitosamente para {posicion_formateada}")
                return data
                
            except PlaywrightTimeout:
                logger.error(f"Timeout al cargar la página de VUCE: {page_url}")
                return {"error": f"Timeout esperando la respuesta de VUCE para {posicion_formateada}", "success": False}
            except Exception as e:
                logger.error(f"Error al obtener información de VUCE para {posicion_formateada}: {e}")
                return {"error": f"Error inesperado al obtener datos: {str(e)}", "success": False}
            finally:
                await browser.close()

    async def get_ncm_info(self, posicion: str, pais: str = "") -> Dict[str, Any]:
        """
        Extraer información completa de una posición arancelaria desde VUCE.
        Reintenta con un código más corto si no encuentra un match exacto con arancel.
        """
        if not PLAYWRIGHT_AVAILABLE:
            return {"error": "Playwright no disponible", "success": False}
        
        posicion_limpia = posicion.replace(".", "").replace(" ", "")
        posicion_formateada = self._format_ncm_code(posicion_limpia)
        
        logger.info(f"Intentando extraer información de VUCE para: {posicion_formateada}")
        page_url = f"{self.base_url}/posicionesArancelarias?posicion={posicion_formateada}"
        data = await self._fetch_from_vuce_url(page_url, posicion_formateada)
        
        if "error" in data:
            return {**data, "posicion_buscada": posicion_formateada}
            
        result = await self._process_vuce_response(data, posicion_formateada)
        
        # Lógica de reintento si no hay match exacto y falta arancel
        tratamiento = result.get("tratamiento_arancelario", {})
        is_exact_match = result.get("match_exacto", False)
        has_arancel = tratamiento.get("arancel_externo_comun") is not None
        
        if not is_exact_match and not has_arancel and len(posicion_formateada.replace(".", "")) >= 8:
            posicion_truncada = ".".join(posicion_formateada.split(".")[:2])
            logger.info(f"Match no exacto y sin arancel. Reintentando con NCM truncado: {posicion_truncada}")
            
            page_url_retry = f"{self.base_url}/posicionesArancelarias?posicion={posicion_truncada}"
            data_retry = await self._fetch_from_vuce_url(page_url_retry, posicion_truncada)
            
            if "error" not in data_retry:
                result_retry = await self._process_vuce_response(data_retry, posicion_truncada)
                result_retry["metadata"]["posicion_buscada_original"] = posicion_formateada
                return result_retry
            else:
                logger.warning("El reintento con NCM truncado falló. Devolviendo el resultado original.")
        
        return result
    
    async def _process_vuce_response(self, data: Dict, posicion_buscada: str) -> Dict[str, Any]:
        """
        Procesar la respuesta de VUCE y extraer información relevante
        
        Args:
            data: Respuesta JSON de VUCE
            posicion_buscada: Código de posición buscada
            
        Returns:
            Dict con información procesada
        """
        try:
            # Buscar el nodo raíz en el JSON
            raiz = None
            if isinstance(data, dict):
                raiz = data.get("data")
            
            if not raiz:
                return {
                    "error": "No se encontró el nodo raíz en el JSON",
                    "success": False,
                    "raw_data": data
                }
            
            # Extraer todos los nodos terminales
            terminales = []
            await self._extract_terminales_recursively(raiz, terminales)
            
            if not terminales:
                return {
                    "error": "No se encontraron posiciones terminales",
                    "success": False,
                    "posicion_buscada": posicion_buscada
                }
            
            # Buscar la posición específica o la más cercana
            posicion_exacta = None
            posiciones_relacionadas = []
            mejor_match_parcial = None
            largo_mejor_match = 0
            
            posicion_limpia = posicion_buscada.replace(".", "")

            for terminal in terminales:
                codigo_terminal_limpio = terminal["codigo"].replace(".", "")
                
                if codigo_terminal_limpio == posicion_limpia:
                    posicion_exacta = terminal
                    break

                if posicion_limpia.startswith(codigo_terminal_limpio) and len(codigo_terminal_limpio) > largo_mejor_match:
                    mejor_match_parcial = terminal
                    largo_mejor_match = len(codigo_terminal_limpio)
                
                if codigo_terminal_limpio != posicion_limpia:
                    posiciones_relacionadas.append(terminal)
            
            posicion_principal = posicion_exacta or mejor_match_parcial or (terminales[0] if terminales else None)

            if not posicion_principal:
                return {
                    "error": "No se encontraron posiciones terminales para procesar.",
                    "success": False,
                    "posicion_buscada": posicion_buscada
                }

            # Analizar régimen simplificado
            regimen_info = self._analyze_simplified_regime(posicion_principal)
            
            # Analizar intervenciones potenciales
            intervenciones_info = self._analyze_interventions(posicion_principal)
            
            result = {
                "success": True,
                "posicion_buscada": posicion_buscada,
                "posicion_encontrada": posicion_principal,
                "posiciones_relacionadas": posiciones_relacionadas,
                "total_posiciones": len(terminales),
                "match_exacto": posicion_exacta is not None,
                "tratamiento_arancelario": {
                    "derechos_importacion_extrazona": posicion_principal.get("derechos_importacion_extrazona"),
                    "arancel_externo_comun": posicion_principal.get("arancel_externo_comun"),
                    "derechos_importacion_intrazona": posicion_principal.get("derechos_importacion_intrazona"),
                    "tasa_estadistica": 3.0,  # Estándar para Argentina
                    "iva": 21.0,  # IVA estándar
                    "iva_adicional": 0.0  # Por defecto
                },
                "regimen_simplificado": regimen_info,
                "intervenciones": intervenciones_info,
                "metadata": {
                    "fecha_extraccion": datetime.now().isoformat(),
                    "fuente": "VUCE Argentina",
                    "fecha_actualizacion": posicion_principal.get("actualizado"),
                    "activo": posicion_principal.get("activo", False)
                }
            }
            
            logger.info(f"Información procesada exitosamente para {posicion_buscada}")
            return result
            
        except Exception as e:
            logger.error(f"Error procesando respuesta de VUCE: {e}")
            return {
                "error": f"Error procesando datos: {str(e)}",
                "success": False,
                "raw_data": data
            }
    
    def _format_ncm_code(self, codigo: str) -> str:
        """
        Formatear código NCM para búsqueda en VUCE
        
        Args:
            codigo: Código NCM sin formato
            
        Returns:
            Código NCM formateado
        """
        # Remover cualquier formato existente
        codigo_limpio = re.sub(r'[^\d]', '', codigo)
        
        # Formatear según longitud
        if len(codigo_limpio) >= 8:
            # Formato completo: 1234.56.78
            return f"{codigo_limpio[:4]}.{codigo_limpio[4:6]}.{codigo_limpio[6:8]}"
        elif len(codigo_limpio) >= 6:
            # Formato parcial: 1234.56
            return f"{codigo_limpio[:4]}.{codigo_limpio[4:6]}"
        elif len(codigo_limpio) >= 4:
            # Solo partida: 1234
            return codigo_limpio[:4]
        else:
            # Muy corto, devolver como está
            return codigo_limpio
    
    def _analyze_simplified_regime(self, posicion_info: Dict) -> Dict[str, Any]:
        """
        Analizar si la posición aplica para régimen simplificado
        
        Args:
            posicion_info: Información de la posición arancelaria
            
        Returns:
            Dict con análisis de régimen simplificado
        """
        codigo = posicion_info.get("codigo", "")
        descripcion = posicion_info.get("descripcion", "").lower()
        
        # Productos típicamente excluidos del régimen simplificado
        exclusiones_keywords = [
            "alcohol", "tabaco", "cigarrillo", "vino", "cerveza",
            "medicamento", "farmaceutico", "droga", "estupefaciente",
            "arma", "municion", "explosivo", "fuego artificial",
            "automovil", "vehiculo", "motocicleta", "avion",
            "maquinaria pesada", "industrial"
        ]
        
        posible_exclusion = any(keyword in descripcion for keyword in exclusiones_keywords)
        
        # Análisis específico por capítulo NCM
        capitulo = codigo[:2] if len(codigo) >= 2 else ""
        
        # Capítulos típicamente restringidos
        capitulos_restringidos = ["22", "24", "30", "87", "88", "89", "93"]
        
        return {
            "aplica_potencialmente": not posible_exclusion and capitulo not in capitulos_restringidos,
            "capitulo_ncm": capitulo,
            "posibles_restricciones": exclusiones_keywords if posible_exclusion else [],
            "observaciones": "Análisis preliminar. Verificar con normativa específica RG 5631/2025",
            "factores_a_verificar": [
                "Valor CIF máximo USD 3,000",
                "Peso máximo 50kg",
                "Sin restricciones específicas del producto",
                "Origen del envío (courier habilitado)"
            ]
        }
    
    def _analyze_interventions(self, posicion_info: Dict) -> Dict[str, Any]:
        """
        Analizar posibles intervenciones requeridas
        
        Args:
            posicion_info: Información de la posición arancelaria
            
        Returns:
            Dict con análisis de intervenciones
        """
        codigo = posicion_info.get("codigo", "")
        descripcion = posicion_info.get("descripcion", "").lower()
        
        intervenciones_potenciales = []
        
        # Mapeo de keywords a organismos
        organismos_map = {
            "alimento": ["SENASA", "INAL"],
            "medicamento": ["ANMAT"],
            "cosmetic": ["ANMAT"],
            "electronico": ["INTI - CIE"],
            "juguete": ["INTI"],
            "textil": ["INTI"],
            "quimico": ["SENASA"],
            "planta": ["SENASA"],
            "animal": ["SENASA"],
            "carne": ["SENASA"],
            "lacteo": ["SENASA"],
            "pesquero": ["SENASA"],
            "alcohol": ["ANMAT", "AFIP"],
            "tabaco": ["AFIP"],
            "vehiculo": ["INTI"],
            "maquinaria": ["INTI"],
            "radioactivo": ["CNEA"],
            "residuo": ["ACUMAR"],
            "usado": ["Ministerio de Ambiente"]
        }
        
        for keyword, organismos in organismos_map.items():
            if keyword in descripcion:
                intervenciones_potenciales.extend(organismos)
        
        # Eliminar duplicados
        intervenciones_potenciales = list(set(intervenciones_potenciales))
        
        return {
            "organismos_potenciales": intervenciones_potenciales,
            "requiere_licencia_previa": len(intervenciones_potenciales) > 0,
            "observaciones": "Análisis preliminar basado en descripción. Verificar en VUCE oficial.",
            "recomendacion": "Consultar VUCE para intervenciones específicas antes de importar"
        }
    
    def validate_ncm_code(self, codigo: str) -> Dict[str, Any]:
        """
        Validar formato de código NCM
        
        Args:
            codigo: Código NCM a validar
            
        Returns:
            Dict con resultado de validación
        """
        # Limpiar código
        codigo_limpio = re.sub(r'[^\d]', '', codigo)
        
        # Validaciones básicas
        validations = {
            "formato_valido": len(codigo_limpio) >= 4,
            "longitud_correcta": len(codigo_limpio) in [4, 6, 8, 10],
            "solo_numeros": codigo_limpio.isdigit(),
            "capitulo_valido": False,
            "partida_valida": False
        }
        
        if len(codigo_limpio) >= 2:
            capitulo = int(codigo_limpio[:2])
            validations["capitulo_valido"] = 1 <= capitulo <= 97
        
        if len(codigo_limpio) >= 4:
            partida = int(codigo_limpio[:4])
            validations["partida_valida"] = partida > 0
        
        return {
            "codigo_original": codigo,
            "codigo_limpio": codigo_limpio,
            "codigo_formateado": self._format_ncm_code(codigo_limpio),
            "es_valido": all(validations.values()),
            "validaciones": validations,
            "recomendacion": "Código válido" if all(validations.values()) else "Revisar formato de código NCM"
        }

# Función de conveniencia para uso externo
async def get_vuce_info(ncm_code: str, headless: bool = True) -> Dict[str, Any]:
    """
    Función de conveniencia para extraer información de VUCE
    
    Args:
        ncm_code: Código NCM a consultar
        headless: Si ejecutar en modo headless
        
    Returns:
        Dict con información de VUCE
    """
    integration = VuceIntegration(headless=headless)
    return await integration.get_ncm_info(ncm_code)

# Función síncrona para compatibilidad
def get_vuce_info_sync(ncm_code: str, headless: bool = True) -> Dict[str, Any]:
    """
    Versión síncrona de get_vuce_info
    
    Args:
        ncm_code: Código NCM a consultar
        headless: Si ejecutar en modo headless
        
    Returns:
        Dict con información de VUCE
    """
    return asyncio.run(get_vuce_info(ncm_code, headless))

if __name__ == "__main__":
    # Test básico
    import asyncio
    
    async def test():
        integration = VuceIntegration()
        result = await integration.get_ncm_info("8528.72.00")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    asyncio.run(test()) 