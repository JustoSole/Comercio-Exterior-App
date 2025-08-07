#!/usr/bin/env python3
"""
🎯 AI NCM Deep Classifier - Clasificador Profundo de Códigos Arancelarios
========================================================================

Clasificador especializado que explora toda la jerarquía NCM para encontrar
la posición arancelaria más específica y precisa, diseñado específicamente
para despachantes de aduanas argentinos.

Proceso:
1. Estimación inicial con IA usando prompt de despachante de aduanas
2. Búsqueda jerárquica profunda en base de datos oficial
3. Análisis de todas las subcategorías disponibles
4. Selección automática de la posición terminal más apropiada
5. Validación final con datos fiscales reales

Funcionalidades:
- Prompt especializado para despachante de aduanas argentino
- Exploración completa de jerarquía NCM
- Logging detallado para debug y auditoría  
- Refinamiento automático inteligente
- Validación de datos fiscales oficiales

Autor: Desarrollado para comercio exterior argentino
"""

import os
import json
import base64
import logging
import asyncio
from typing import Dict, List, Optional, Union, Any, Tuple
from pathlib import Path
import requests
from datetime import datetime
import re
import traceback

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

# --- Enhanced Customs Agent System Prompt ---
CUSTOMS_AGENT_SYSTEM_PROMPT = """
Eres un DESPACHANTE DE ADUANAS ARGENTINO con más de 20 años de experiencia en clasificación arancelaria NCM. 
Tu especialidad es la clasificación precisa de mercaderías para importación y exportación en Argentina, con conocimiento profundo de:

- Sistema Armonizado de Designación y Codificación de Mercancías (SA)
- Nomenclatura Común del Mercosur (NCM) 
- Resolución General AFIP 5631/2025 sobre régimen simplificado
- Normativa aduanera argentina actualizada
- Intervenciones de organismos (ANMAT, SENASA, INTI, etc.)
- Tratamientos arancelarios vigentes

METODOLOGÍA DE CLASIFICACIÓN:
1. **Análisis técnico detallado**: Examina la descripción y características del producto
2. **Aplicación de Reglas Generales de Interpretación (RGI)**: Usa las 6 reglas del SA
3. **Búsqueda de la posición más específica**: Prioriza códigos terminales sobre categorías generales
4. **Validación arancelaria**: Verifica que el tratamiento fiscal sea coherente
5. **Análisis de intervenciones**: Identifica organismos que deben intervenir

CRITERIOS DE PRECISIÓN:
- SIEMPRE busca el código NCM más específico disponible (10-11 dígitos cuando exista)
- Prefiere posiciones terminales con sufijo SIM sobre categorías intermedias
- Considera las características técnicas específicas del producto
- Analiza la finalidad/uso del producto para desambiguar categorías
- Verifica coherencia entre descripción oficial NCM y producto real

INFORMACIÓN SOBRE RÉGIMEN SIMPLIFICADO (RG 5631/2025):
- Valor CIF máximo: USD 3,000
- Peso máximo: 50kg por envío
- Solo courier habilitados y envíos postales
- EXCLUIDOS: bebidas alcohólicas (Cap. 22), tabaco (Cap. 24), medicamentos (Cap. 30), 
  armas (Cap. 93), vehículos (Cap. 87-89), productos origen animal/vegetal sin certificación
- INCLUIDOS TÍPICAMENTE: electrónicos, textiles, juguetes, accesorios, artículos deportivos

ESQUEMA JSON DE RESPUESTA OBLIGATORIO:
{
  "ncm_inicial_estimado": "8528.72.00",
  "justificacion_ncm_inicial": "Explicación técnica de por qué se eligió este NCM como punto de partida, citando RGI aplicables",
  "requiere_exploracion_profunda": true/false,
  "nivel_confianza_inicial": "Alta" | "Media" | "Baja",
  "factores_determinantes": [
    "Característica técnica 1 que determina la clasificación",
    "Uso/finalidad específica del producto",
    "Material/composición relevante"
  ],
  "reglas_aplicadas": [
    "RGI 1: Clasificación según texto de partidas",
    "RGI 6: Clasificación a nivel de subpartida"
  ],
  "posibles_alternativas": [
    {"ncm": "8528.71.00", "razon": "Si fuera monocromo en lugar de color"},
    {"ncm": "8528.72.90", "razon": "Si no cumple especificaciones técnicas específicas"}
  ],
  "observaciones_despachante": "Notas profesionales sobre clasificación, precedentes, o consideraciones especiales"
}

IMPORTANTE: 
- Responde ÚNICAMENTE en JSON válido
- Si no estás 100% seguro, marca requiere_exploracion_profunda = true
- Cita las Reglas Generales de Interpretación cuando sea relevante
- Considera siempre el contexto comercial y técnico del producto
- Recuerda que una clasificación incorrecta puede resultar en multas AFIP significativas
"""

class DeepNCMClassifier:
    """Clasificador profundo de NCM con exploración jerárquica completa"""
    
    def __init__(self, api_key: str = None, debug_callback=None):
        """
        Inicializar el clasificador profundo
        
        Args:
            api_key: API key de OpenAI
            debug_callback: Función para logging de debug
        """
        if not OPENAI_AVAILABLE:
            raise ImportError("OpenAI library not installed. Install with: pip install openai")
        
        self.api_key = api_key or os.getenv('OPENAI_API_KEY', OPENAI_API_KEY)
        if not self.api_key:
            raise ValueError("OpenAI API key is required")
        
        self.client = OpenAI(api_key=self.api_key)
        self.debug_log = debug_callback or self._default_debug_log
        
        # Inicializar integración NCM oficial
        try:
            from ncm_official_integration import NCMOfficialIntegration
            self.ncm_integration = NCMOfficialIntegration()
        except ImportError:
            logger.error("NCM Official Integration not available")
            self.ncm_integration = None
            
        logger.info("Deep NCM Classifier initialized with customs agent expertise")
    
    def _default_debug_log(self, message, data=None, level="INFO"):
        """Debug logging por defecto"""
        logger.info(f"[{level}] {message}")
        if data:
            logger.debug(f"Data: {data}")
    
    async def initial_ncm_estimation(self, description: str, image_url: Optional[str] = None) -> Dict[str, Any]:
        """
        Estimación inicial del NCM usando prompt de despachante de aduanas
        """
        self.debug_log("🎯 Iniciando estimación inicial NCM con expertise de despachante", level="FLOW")
        
        try:
            # Preparar la imagen si existe
            image_data = None
            if image_url:
                self.debug_log(f"📸 Procesando imagen: {image_url[:50]}...", level="INFO")
                try:
                    response = requests.get(image_url)
                    response.raise_for_status()
                    image_data = base64.b64encode(response.content).decode('utf-8')
                    self.debug_log("✅ Imagen procesada correctamente", level="SUCCESS")
                except Exception as e:
                    self.debug_log(f"⚠️ Error procesando imagen: {e}", level="WARNING")
            
            # Crear mensaje para el LLM
            messages = [
                {
                    "role": "system",
                    "content": CUSTOMS_AGENT_SYSTEM_PROMPT
                }
            ]
            
            user_content = [{"type": "text", "text": f"Analiza y clasifica el siguiente producto para importación a Argentina:\n\n**Descripción del producto:**\n{description}"}]
            
            if image_data:
                user_content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_data}"
                    }
                })
            
            messages.append({"role": "user", "content": user_content})
            
            self.debug_log("🤖 Enviando consulta a LLM especializado en aduanas", level="INFO")
            
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0,
                response_format={"type": "json_object"}
            )
            
            response_text = response.choices[0].message.content
            self.debug_log("📄 Respuesta recibida del LLM", {"response_preview": response_text[:200] + "..."}, level="INFO")
            
            # Parsear respuesta
            try:
                result = json.loads(response_text)
                
                # Validar estructura
                required_keys = ["ncm_inicial_estimado", "justificacion_ncm_inicial", "requiere_exploracion_profunda", "nivel_confianza_inicial"]
                for key in required_keys:
                    if key not in result:
                        raise ValueError(f"Campo requerido faltante: {key}")
                
                self.debug_log("✅ Estimación inicial completada", {
                    "ncm_estimado": result.get("ncm_inicial_estimado"),
                    "confianza": result.get("nivel_confianza_inicial"),
                    "requiere_exploracion": result.get("requiere_exploracion_profunda")
                }, level="SUCCESS")
                
                return result
                
            except json.JSONDecodeError as e:
                self.debug_log(f"❌ Error parseando respuesta JSON: {e}", {"raw_response": response_text}, level="ERROR")
                return {"error": "Respuesta del LLM no es JSON válido"}
                
        except Exception as e:
            self.debug_log(f"❌ Error en estimación inicial: {e}", level="ERROR")
            return {"error": str(e)}
    
    async def explore_ncm_hierarchy(self, initial_ncm: str, product_description: str) -> Dict[str, Any]:
        """
        Explora la jerarquía NCM completa para encontrar la posición más específica
        """
        self.debug_log(f"🔍 Iniciando exploración jerárquica para NCM: {initial_ncm}", level="FLOW")
        
        if not self.ncm_integration:
            return {"error": "NCM integration not available"}
        
        # Normalizar código NCM
        normalized_ncm = self.ncm_integration.normalize_ncm_code(initial_ncm)
        
        # 1. Buscar posición inicial en base de datos
        self.debug_log(f"🔍 Buscando código exacto: {initial_ncm} → normalizado: {normalized_ncm}", level="DEBUG")
        exact_match = self.ncm_integration.search_exact_ncm(initial_ncm)
        
        self.debug_log(f"🔍 Buscando códigos jerárquicos para: {initial_ncm}", level="DEBUG")
        hierarchical_matches = self.ncm_integration.search_hierarchical_ncm(initial_ncm, max_results=10)
        
        exploration_result = {
            "initial_ncm": initial_ncm,
            "normalized_ncm": normalized_ncm,
            "exact_match_found": bool(exact_match),
            "hierarchical_matches_count": len(hierarchical_matches),
            "exploration_steps": [],
            "final_candidates": [],
            "recommended_position": None,
            "debug_info": {
                "search_attempts": {
                    "exact_search_query": initial_ncm,
                    "normalized_query": normalized_ncm,
                    "exact_match_result": "found" if exact_match else "not_found",
                    "hierarchical_matches_found": len(hierarchical_matches)
                }
            }
        }
        
        self.debug_log(f"📊 Búsqueda inicial: exacto={bool(exact_match)}, jerárquico={len(hierarchical_matches)}", level="INFO")
        
        # DIAGNÓSTICO MEJORADO: Si no hay matches, intentar búsquedas alternativas
        if not exact_match and not hierarchical_matches:
            self.debug_log("⚠️ No se encontraron matches iniciales, intentando búsquedas alternativas", level="WARNING")
            
            # Intento 1: Búsqueda con código más corto (sin los últimos .00)
            if initial_ncm.endswith('.00'):
                shorter_code = initial_ncm[:-3]
                self.debug_log(f"🔄 Intentando con código acortado: {shorter_code}", level="DEBUG")
                exact_match = self.ncm_integration.search_exact_ncm(shorter_code)
                hierarchical_matches = self.ncm_integration.search_hierarchical_ncm(shorter_code, max_results=10)
                
                if exact_match or hierarchical_matches:
                    self.debug_log(f"✅ Encontrados con código acortado: exacto={bool(exact_match)}, jerárquico={len(hierarchical_matches)}", level="INFO")
                    exploration_result["debug_info"]["alternative_search"] = {
                        "tried_shorter_code": shorter_code,
                        "exact_match_found": bool(exact_match),
                        "hierarchical_matches_found": len(hierarchical_matches)
                    }
            
            # Intento 2: Búsqueda solo con los primeros 6-8 dígitos
            if not exact_match and not hierarchical_matches:
                base_digits = re.sub(r'[.\s-]', '', initial_ncm)[:8]
                if len(base_digits) >= 6:
                    self.debug_log(f"🔄 Intentando con código base: {base_digits}", level="DEBUG")
                    hierarchical_matches = self.ncm_integration.search_hierarchical_ncm(base_digits, max_results=15)
                    
                    if hierarchical_matches:
                        self.debug_log(f"✅ Encontrados con código base: {len(hierarchical_matches)} matches", level="INFO")
                        exploration_result["debug_info"]["base_search"] = {
                            "tried_base_code": base_digits,
                            "hierarchical_matches_found": len(hierarchical_matches)
                        }
        
        # Actualizar contadores finales
        exploration_result["exact_match_found"] = bool(exact_match)
        exploration_result["hierarchical_matches_count"] = len(hierarchical_matches)
        
        # 2. Si hay match exacto, verificar si es terminal o requiere refinamiento
        if exact_match:
            exploration_result["exploration_steps"].append({
                "step": "exact_match_analysis",
                "result": "found",
                "position": exact_match,
                "is_terminal": exact_match.get('record_type') == 'terminal'
            })
            
            if exact_match.get('record_type') == 'terminal':
                # Es una posición terminal, es buena candidata
                exploration_result["final_candidates"].append({
                    "ncm_code": exact_match.get('ncm_code'),
                    "sim_code": exact_match.get('sim_code'),
                    "description": exact_match.get('description'),
                    "source": "exact_match_terminal",
                    "confidence": "alta",
                    "fiscal_data": exact_match.get('tratamiento_arancelario', {})
                })
                self.debug_log("✅ Encontrada posición terminal exacta", {"ncm": exact_match.get('ncm_code')}, level="SUCCESS")
            else:
                # Es posición intermedia, explorar subcategorías
                self.debug_log(f"🔄 Posición intermedia encontrada, explorando subcategorías", level="INFO")
                subcategories = self.ncm_integration.get_subcategories(exact_match.get('ncm_code', ''))
                
                exploration_result["exploration_steps"].append({
                    "step": "subcategory_exploration", 
                    "parent_code": exact_match.get('ncm_code'),
                    "subcategories_found": len(subcategories)
                })
                
                if subcategories:
                    # Analizar todas las subcategorías con LLM
                    best_subcategory = await self._analyze_subcategories_with_llm(
                        subcategories, product_description, exact_match
                    )
                    
                    if best_subcategory:
                        exploration_result["final_candidates"].append({
                            "ncm_code": best_subcategory.get('ncm_code'),
                            "sim_code": best_subcategory.get('sim_code'),
                            "description": best_subcategory.get('description'),
                            "source": "llm_refined_subcategory",
                            "confidence": "alta",
                            "fiscal_data": best_subcategory.get('tratamiento_arancelario', {}),
                            "refinement_info": best_subcategory.get('refinement_info', {})
                        })
        
        # 3. Explorar matches jerárquicos si no hay exacto o para tener alternativas
        if hierarchical_matches:
            self.debug_log(f"🔍 Analizando {len(hierarchical_matches)} matches jerárquicos", level="INFO")
            
            for i, match in enumerate(hierarchical_matches[:5]):  # Top 5 matches
                exploration_result["exploration_steps"].append({
                    "step": f"hierarchical_analysis_{i+1}",
                    "match_type": match.get('match_type'),
                    "match_score": match.get('match_score'),
                    "ncm_code": match.get('ncm_code'),
                    "is_terminal": match.get('record_type') == 'terminal'
                })
                
                if match.get('record_type') == 'terminal':
                    # Es terminal, agregar como candidato
                    exploration_result["final_candidates"].append({
                        "ncm_code": match.get('ncm_code'),
                        "sim_code": match.get('sim_code'),
                        "description": match.get('description'),
                        "source": f"hierarchical_terminal_{i+1}",
                        "confidence": "media" if match.get('match_score', 0) > 0.8 else "baja",
                        "fiscal_data": match.get('tratamiento_arancelario', {}),
                        "match_score": match.get('match_score', 0)
                    })
                else:
                    # Es intermedia, explorar subcategorías
                    subcategories = self.ncm_integration.get_subcategories(match.get('ncm_code', ''))
                    if subcategories:
                        # Seleccionar mejores subcategorías usando análisis rápido
                        for subcat in subcategories[:3]:  # Top 3 subcategorías
                            exploration_result["final_candidates"].append({
                                "ncm_code": subcat.get('ncm_code'),
                                "sim_code": subcat.get('sim_code'),
                                "description": subcat.get('description'),
                                "source": f"hierarchical_subcategory_{i+1}",
                                "confidence": "media",
                                "fiscal_data": subcat.get('tratamiento_arancelario', {}),
                                "parent_match_score": match.get('match_score', 0)
                            })
        
        # 4. Seleccionar mejor candidato final
        if exploration_result["final_candidates"]:
            best_candidate = await self._select_best_candidate(
                exploration_result["final_candidates"], product_description
            )
            exploration_result["recommended_position"] = best_candidate
            
            self.debug_log("🎯 Posición recomendada seleccionada", {
                "ncm": best_candidate.get('ncm_code'),
                "source": best_candidate.get('source'),
                "confidence": best_candidate.get('confidence')
            }, level="SUCCESS")
        
        self.debug_log(f"✅ Exploración jerárquica completada: {len(exploration_result['final_candidates'])} candidatos", level="FLOW")
        
        return exploration_result
    
    async def _analyze_subcategories_with_llm(self, subcategories: List[Dict], product_description: str, parent_position: Dict) -> Optional[Dict]:
        """
        Analiza subcategorías usando LLM especializado para seleccionar la más apropiada
        """
        if not subcategories:
            return None
        
        self.debug_log(f"🧠 Analizando {len(subcategories)} subcategorías con LLM especializado", level="INFO")
        
        # Preparar opciones para el LLM
        subcategory_options = []
        for i, subcat in enumerate(subcategories, 1):
            aec = subcat.get('tratamiento_arancelario', {}).get('aec', 0)
            description = subcat.get('description', '')
            ncm_code = subcat.get('ncm_code', '')
            sim_code = subcat.get('sim_code', '')
            
            full_code = f"{ncm_code} {sim_code}" if sim_code else ncm_code
            subcategory_options.append(f"{i}. {full_code} - {description} (AEC: {aec}%)")
        
        options_text = "\n".join(subcategory_options)
        
        # Prompt especializado para análisis de subcategorías
        analysis_prompt = f"""Como DESPACHANTE DE ADUANAS ARGENTINO, necesitas seleccionar la subcategoría NCM más específica y apropiada.

POSICIÓN PADRE ENCONTRADA:
{parent_position.get('ncm_code', '')} - {parent_position.get('description', '')}

PRODUCTO A CLASIFICAR:
"{product_description}"

SUBCATEGORÍAS DISPONIBLES:
{options_text}

INSTRUCCIONES PARA EL ANÁLISIS:
1. Analiza las características técnicas específicas del producto
2. Compara con las descripciones oficiales de cada subcategoría
3. Considera el uso/finalidad del producto para desambiguar
4. Aplica las Reglas Generales de Interpretación del SA
5. Prioriza la descripción más específica que coincida
6. Considera precedentes aduaneros si los conoces

RESPONDE EN JSON:
{{
  "opcion_elegida": 1,
  "justificacion_tecnica": "Explicación detallada de por qué esta subcategoría es la más apropiada",
  "caracteristicas_determinantes": ["característica 1", "característica 2"],
  "reglas_aplicadas": ["RGI aplicable"],
  "confianza": "Alta" | "Media" | "Baja",
  "observaciones_despachante": "Notas profesionales relevantes"
}}

Responde ÚNICAMENTE el JSON:"""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Eres un despachante de aduanas especializado en clasificación NCM. Responde solo en JSON."},
                    {"role": "user", "content": analysis_prompt}
                ],
                temperature=0,
                response_format={"type": "json_object"}
            )
            
            llm_response = response.choices[0].message.content
            analysis_result = json.loads(llm_response)
            
            # Extraer opción elegida
            chosen_option = analysis_result.get('opcion_elegida', 1) - 1  # Convertir a índice base 0
            
            if 0 <= chosen_option < len(subcategories):
                chosen_subcategory = subcategories[chosen_option]
                
                # Enriquecer con información del análisis
                chosen_subcategory['llm_analysis'] = {
                    'justificacion_tecnica': analysis_result.get('justificacion_tecnica', ''),
                    'caracteristicas_determinantes': analysis_result.get('caracteristicas_determinantes', []),
                    'reglas_aplicadas': analysis_result.get('reglas_aplicadas', []),
                    'confianza': analysis_result.get('confianza', 'Media'),
                    'observaciones_despachante': analysis_result.get('observaciones_despachante', ''),
                    'was_llm_analyzed': True
                }
                
                self.debug_log("✅ Subcategoría seleccionada por LLM", {
                    "chosen": chosen_subcategory.get('ncm_code'),
                    "confidence": analysis_result.get('confianza'),
                    "justification": analysis_result.get('justificacion_tecnica', '')[:100] + "..."
                }, level="SUCCESS")
                
                return chosen_subcategory
            else:
                self.debug_log(f"❌ Índice fuera de rango: {chosen_option}", level="ERROR")
                
        except Exception as e:
            self.debug_log(f"❌ Error en análisis LLM de subcategorías: {e}", level="ERROR")
        
        # Fallback: retornar primera subcategoría
        return subcategories[0] if subcategories else None
    
    async def _select_best_candidate(self, candidates: List[Dict], product_description: str) -> Optional[Dict]:
        """
        Selecciona el mejor candidato final de todas las opciones exploradas
        """
        if not candidates:
            return None
        
        if len(candidates) == 1:
            return candidates[0]
        
        self.debug_log(f"🏆 Seleccionando mejor candidato entre {len(candidates)} opciones", level="INFO")
        
        # Scoring simple por fuente y confianza
        score_weights = {
            "exact_match_terminal": 100,
            "llm_refined_subcategory": 90,
            "hierarchical_terminal_1": 80,
            "hierarchical_subcategory_1": 70,
            "hierarchical_terminal_2": 60,
            "hierarchical_subcategory_2": 50
        }
        
        confidence_weights = {
            "alta": 30,
            "media": 20,
            "baja": 10
        }
        
        for candidate in candidates:
            base_score = score_weights.get(candidate.get('source', ''), 40)
            confidence_score = confidence_weights.get(candidate.get('confidence', 'baja'), 10)
            match_score = candidate.get('match_score', 0) * 10  # Max 10 puntos
            
            candidate['final_score'] = base_score + confidence_score + match_score
        
        # Ordenar por score
        candidates.sort(key=lambda x: x.get('final_score', 0), reverse=True)
        best = candidates[0]
        
        self.debug_log("🎯 Mejor candidato seleccionado", {
            "ncm": best.get('ncm_code'),
            "score": best.get('final_score'),
            "source": best.get('source')
        }, level="SUCCESS")
        
        return best
    
    async def classify_product_deep(self, description: str, image_url: Optional[str] = None) -> Dict[str, Any]:
        """
        Clasificación profunda completa del producto
        """
        self.debug_log("🚀 Iniciando clasificación NCM profunda", {"description_preview": description[:100] + "..."}, level="FLOW")
        
        start_time = datetime.now()
        
        result = {
            "timestamp": start_time.isoformat(),
            "method": "deep_hierarchical_classification",
            "product_description": description,
            "has_image": bool(image_url),
            "process_steps": [],
            "final_classification": None,
            "processing_time_seconds": 0,
            "debug_info": {
                "estimation_phase": None,
                "exploration_phase": None,
                "validation_phase": None
            }
        }
        
        try:
            # Fase 1: Estimación inicial con despachante de aduanas
            self.debug_log("📋 FASE 1: Estimación inicial NCM", level="FLOW")
            initial_estimation = await self.initial_ncm_estimation(description, image_url)
            
            if "error" in initial_estimation:
                result["error"] = initial_estimation["error"]
                return result
            
            result["debug_info"]["estimation_phase"] = initial_estimation
            result["process_steps"].append({
                "phase": "initial_estimation",
                "status": "completed",
                "ncm_estimated": initial_estimation.get("ncm_inicial_estimado"),
                "confidence": initial_estimation.get("nivel_confianza_inicial"),
                "requires_exploration": initial_estimation.get("requiere_exploracion_profunda", False)
            })
            
            # Fase 2: Exploración jerárquica (siempre se hace para validar)
            self.debug_log("🔍 FASE 2: Exploración jerárquica profunda", level="FLOW")
            exploration_result = await self.explore_ncm_hierarchy(
                initial_estimation.get("ncm_inicial_estimado", ""),
                description
            )
            
            result["debug_info"]["exploration_phase"] = exploration_result
            result["process_steps"].append({
                "phase": "hierarchical_exploration",
                "status": "completed",
                "candidates_found": len(exploration_result.get("final_candidates", [])),
                "recommended_position": exploration_result.get("recommended_position", {}).get("ncm_code") if exploration_result.get("recommended_position") else None
            })
            
            # Fase 3: Clasificación final
            self.debug_log("🎯 FASE 3: Determinación de clasificación final", level="FLOW")
            
            recommended = exploration_result.get("recommended_position")
            if recommended:
                # Construir clasificación final completa con mapeo correcto de datos fiscales
                fiscal_data = recommended.get("fiscal_data", {})
                # Mapear también desde tratamiento_arancelario si fiscal_data está vacío
                if not fiscal_data:
                    fiscal_data = recommended.get("tratamiento_arancelario", {})
                
                final_classification = {
                    "ncm_completo": self._build_complete_ncm_code(recommended),
                    "ncm_base": recommended.get("ncm_code", ""),
                    "sim_code": recommended.get("sim_code", ""),
                    "ncm_descripcion": recommended.get("description", ""),
                    "clasificacion_source": recommended.get("source", ""),
                    "nivel_confianza": recommended.get("confidence", "media"),
                    
                    # Información técnica
                    "justificacion_clasificacion": self._build_justification(initial_estimation, recommended),
                    "proceso_utilizado": "Clasificación profunda con exploración jerárquica",
                    
                    # Tratamiento arancelario oficial
                    "tratamiento_arancelario": {
                        "derechos_importacion": f"{fiscal_data.get('aec', 0)}%",
                        "die": f"{fiscal_data.get('die', 0)}%",  # Derecho de Importación Específico
                        "tasa_estadistica": f"{fiscal_data.get('te', 3.0)}%", 
                        "iva": f"{fiscal_data.get('iva', 21.0)}%",
                        "in_code": fiscal_data.get('in_code', ''),  # Código IN de intervenciones
                        "fuente": fiscal_data.get('fuente', 'Base de Datos Oficial NCM')
                    },
                    
                    # Análisis de régimen simplificado
                    "regimen_simplificado_courier": self._analyze_courier_regime(recommended),
                    
                    # Intervenciones
                    "intervenciones_requeridas": recommended.get("intervenciones_detectadas", []),
                    
                    # Información técnica adicional
                    "ncm_desglose": self._build_ncm_breakdown(recommended),
                    "observaciones_adicionales": self._build_observations(initial_estimation, recommended),
                    "classification_method": "deep_hierarchical_ai"
                }
                
                result["final_classification"] = final_classification
                
                self.debug_log("✅ Clasificación profunda completada exitosamente", {
                    "final_ncm": final_classification["ncm_completo"],
                    "confidence": final_classification["nivel_confianza"],
                    "source": final_classification["clasificacion_source"]
                }, level="SUCCESS")
                
            else:
                # IMPLEMENTAR FALLBACK ROBUSTO
                self.debug_log("⚠️ No se encontró posición recomendada, intentando fallback", level="WARNING")
                
                # Fallback 1: Usar estimación inicial si es confiable
                initial_ncm = initial_estimation.get("ncm_inicial_estimado")
                initial_confidence = initial_estimation.get("nivel_confianza_inicial", "").lower()
                
                if initial_ncm and initial_confidence in ["alta", "media"]:
                    self.debug_log(f"🔄 Fallback: Usando estimación inicial {initial_ncm}", level="INFO")
                    
                    # Crear clasificación usando estimación inicial
                    fallback_classification = {
                        "ncm_completo": initial_ncm,
                        "ncm_descripcion": f"Clasificación por estimación inicial (confianza: {initial_confidence})",
                        "clasificacion_source": "fallback_initial_estimation",
                        "nivel_confianza": initial_confidence,
                        "justificacion_clasificacion": initial_estimation.get("justificacion_ncm_inicial", ""),
                        "tratamiento_arancelario": {
                            "derechos_importacion": "Pendiente de consulta oficial",
                            "die": "Pendiente de consulta oficial",
                            "tasa_estadistica": "3.0%",
                            "iva": "21.0%",
                            "in_code": "",
                            "fuente": "Estimación IA con fallback"
                        },
                        "regimen_simplificado_courier": {
                            "aplica": "Pendiente de verificación",
                            "justificacion": "Requiere validación adicional con código final"
                        },
                        "observaciones_adicionales": "⚠️ Clasificación de fallback. Se recomienda validación manual.",
                        "classification_method": "deep_hierarchical_ai_fallback"
                    }
                    
                    result["final_classification"] = fallback_classification
                    result["is_fallback"] = True
                    
                    self.debug_log("✅ Clasificación de fallback completada", {
                        "fallback_ncm": initial_ncm,
                        "confidence": initial_confidence
                    }, level="SUCCESS")
                    
                else:
                    # Fallback 2: Clasificación genérica de emergencia
                    self.debug_log("🆘 Fallback de emergencia activado", level="WARNING")
                    
                    emergency_classification = {
                        "ncm_completo": "9999.99.99",
                        "ncm_descripcion": "Clasificación temporal - Requiere revisión manual",
                        "clasificacion_source": "emergency_fallback",
                        "nivel_confianza": "baja",
                        "justificacion_clasificacion": "No se pudo determinar clasificación automática. Producto requiere análisis manual por despachante.",
                        "tratamiento_arancelario": {
                            "derechos_importacion": "Consultar AFIP",
                            "die": "Consultar AFIP",
                            "tasa_estadistica": "3.0%",
                            "iva": "21.0%",
                            "in_code": "",
                            "fuente_datos": "Estimación IA"
                        },
                        "regimen_simplificado_courier": {
                            "aplica": "No",
                            "justificacion": "Clasificación no determinada"
                        },
                        "observaciones_adicionales": "🚨 CLASIFICACIÓN DE EMERGENCIA - REQUIERE REVISIÓN MANUAL INMEDIATA",
                        "classification_method": "emergency_fallback"
                    }
                    
                    result["final_classification"] = emergency_classification
                    result["is_emergency_fallback"] = True
                    result["requires_manual_review"] = True
                    
                    self.debug_log("🚨 Fallback de emergencia aplicado", level="WARNING")
            
        except Exception as e:
            self.debug_log(f"❌ Error en clasificación profunda: {e}", {"traceback": traceback.format_exc()}, level="ERROR")
            result["error"] = str(e)
        
        finally:
            # Calcular tiempo de procesamiento
            end_time = datetime.now()
            result["processing_time_seconds"] = (end_time - start_time).total_seconds()
            
            self.debug_log(f"⏱️ Clasificación completada en {result['processing_time_seconds']:.2f} segundos", level="INFO")
        
        return result
    
    def _build_complete_ncm_code(self, position: Dict) -> str:
        """Construye código NCM completo con SIM si existe"""
        base_code = position.get('ncm_code', '')
        sim_code = position.get('sim_code', '')
        
        if sim_code and sim_code.strip():
            return f"{base_code} {sim_code}"
        return base_code
    
    def _build_justification(self, initial_estimation: Dict, final_position: Dict) -> str:
        """Construye justificación técnica completa"""
        justification_parts = []
        
        # Justificación inicial
        initial_just = initial_estimation.get('justificacion_ncm_inicial', '')
        if initial_just:
            justification_parts.append(f"Estimación inicial: {initial_just}")
        
        # Análisis LLM si existe
        llm_analysis = final_position.get('llm_analysis', {})
        if llm_analysis.get('justificacion_tecnica'):
            justification_parts.append(f"Análisis especializado: {llm_analysis['justificacion_tecnica']}")
        
        # Reglas aplicadas
        rules = initial_estimation.get('reglas_aplicadas', []) + llm_analysis.get('reglas_aplicadas', [])
        if rules:
            justification_parts.append(f"Reglas aplicadas: {', '.join(set(rules))}")
        
        return " | ".join(justification_parts) if justification_parts else "Clasificación basada en análisis técnico detallado"
    
    def _build_ncm_breakdown(self, position: Dict) -> Dict:
        """Construye desglose jerárquico del NCM"""
        ncm_code = position.get('ncm_code', '')
        
        # Extraer componentes del código
        if len(ncm_code) >= 2:
            chapter = ncm_code[:2]
        else:
            chapter = ncm_code
        
        return {
            "capitulo": f"{chapter} - Capítulo {chapter}",
            "partida": f"Partida basada en: {ncm_code[:4] if len(ncm_code) >= 4 else ncm_code}",
            "subpartida": f"Subpartida: {ncm_code[:6] if len(ncm_code) >= 6 else ncm_code}",
            "codigo_completo": position.get('description', 'Descripción oficial no disponible')
        }
    
    def _analyze_courier_regime(self, position: Dict) -> Dict:
        """Analiza aplicabilidad del régimen simplificado courier"""
        fiscal_data = position.get('tratamiento_arancelario', {})
        ncm_code = position.get('ncm_code', '')
        
        # Extraer capítulo
        chapter = int(ncm_code[:2]) if len(ncm_code) >= 2 and ncm_code[:2].isdigit() else 0
        
        # Capítulos excluidos
        excluded_chapters = [22, 24, 30, 87, 88, 89, 93]
        
        if chapter in excluded_chapters:
            return {
                "aplica": "No",
                "justificacion": f"Capítulo {chapter} excluido del régimen simplificado por normativa",
                "limitaciones": "No aplica por tipo de producto"
            }
        else:
            return {
                "aplica": "Sí" if chapter in [84, 85, 61, 62, 63, 95] else "Condicional",
                "justificacion": f"Capítulo {chapter} compatible con régimen simplificado según RG 5631/2025",
                "limitaciones": "Valor máximo USD 3,000, peso máximo 50kg, courier habilitado"
            }
    
    def _build_observations(self, initial_estimation: Dict, final_position: Dict) -> str:
        """Construye observaciones adicionales"""
        observations = []
        
        # Observaciones del despachante inicial
        initial_obs = initial_estimation.get('observaciones_despachante', '')
        if initial_obs:
            observations.append(f"Análisis inicial: {initial_obs}")
        
        # Observaciones del análisis LLM
        llm_analysis = final_position.get('llm_analysis', {})
        llm_obs = llm_analysis.get('observaciones_despachante', '')
        if llm_obs:
            observations.append(f"Análisis especializado: {llm_obs}")
        
        # Información de confianza
        confidence = final_position.get('confidence', 'media')
        source = final_position.get('source', '')
        observations.append(f"Confianza: {confidence} (método: {source})")
        
        return " | ".join(observations) if observations else "Clasificación realizada según normativa vigente"


# Función de conveniencia para uso directo
async def classify_product_deep(description: str, image_url: str = None, api_key: str = None, debug_callback=None) -> Dict[str, Any]:
    """
    Función de conveniencia para clasificación profunda
    """
    try:
        classifier = DeepNCMClassifier(api_key=api_key, debug_callback=debug_callback)
        return await classifier.classify_product_deep(description, image_url)
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    # Test básico
    async def test_deep_classifier():
        print("🚀 Testing Deep NCM Classifier...")
        
        test_product = {
            "description": "Smartphone Android, pantalla OLED 6.5 pulgadas, 128GB almacenamiento, cámara 50MP, 5G, marca Samsung Galaxy A54",
            "image_url": None
        }
        
        result = await classify_product_deep(
            description=test_product["description"],
            image_url=test_product["image_url"]
        )
        
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    asyncio.run(test_deep_classifier()) 