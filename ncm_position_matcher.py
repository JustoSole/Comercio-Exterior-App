#!/usr/bin/env python3
"""
🎯 NCM Position Matcher - Validador y Enriquecedor de Códigos NCM
================================================================

Script que valida códigos NCM contra base de datos oficial y enriquece
con atributos arancelarios específicos. Funciona como segunda etapa
después del ai_ncm_classifier.py.

Funcionalidades:
- Búsqueda exacta de códigos NCM
- Búsqueda aproximada jerárquica 
- Selección inteligente por IA
- Enriquecimiento con datos arancelarios
- CLI completo para integración

Autor: Desarrollado para comercio exterior argentino
"""

import os
import sys
import json
import re
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Optional, Union, Tuple, Any
from datetime import datetime
import pandas as pd
from dataclasses import dataclass
from difflib import SequenceMatcher
import asyncio

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Intentar importar OpenAI para selección IA
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("OpenAI no disponible. Funcionalidad de IA deshabilitada.")

# Intentar cargar API key
try:
    from secrets_config import get_api_key
    OPENAI_API_KEY = get_api_key("OPENAI_API_KEY") or ""
except ImportError:
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', "")

@dataclass
class NCMPosition:
    """Estructura de datos para una posición NCM"""
    file: str
    chapter: int
    code: str
    sim: str
    description: str
    aec: float
    die: float
    te: float
    in_field: str  # 'in' es palabra reservada
    de: float
    re: float
    code_searchable: str
    parent: Optional[str]
    parent_searchable: Optional[str]
    hierarchy_level: int
    record_type: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario para JSON"""
        return {
            'code': str(self.code),
            'sim': str(self.sim),
            'description': str(self.description),
            'attributes': {
                'aec': float(self.aec),
                'die': float(self.die),
                'te': float(self.te),
                'in': str(self.in_field),  # Campo IN oficial de la base de datos
                'de': float(self.de),      # Datos adicionales oficiales
                're': float(self.re),      # Datos adicionales oficiales
                'iva': 21.0,  # IVA estándar Argentina
        
            },
            'interventions': self._get_interventions(),
            'simplified_regime': self._analyze_simplified_regime(),
            'hierarchy_info': {
                'parent': str(self.parent) if self.parent else None,
                'level': int(self.hierarchy_level),
                'type': str(self.record_type)
            },
            'source_info': {
                'file': str(self.file),
                'chapter': int(self.chapter)
            }
        }
    
    def _get_interventions(self) -> List[str]:
        """Determina intervenciones basadas en capítulo y descripción"""
        interventions = []
        
        # Mapeo de capítulos a organismos típicos
        chapter_interventions = {
            range(1, 25): ["SENASA"],  # Productos animales/vegetales
            range(28, 39): ["ANMAT"],  # Químicos/farmacéuticos
            range(84, 86): ["INTI-CIE"],  # Electrónicos
            range(61, 64): ["INTI"],  # Textiles
            95: ["INTI"]  # Juguetes
        }
        
        for chapter_range, orgs in chapter_interventions.items():
            if isinstance(chapter_range, range) and self.chapter in chapter_range:
                interventions.extend(orgs)
            elif isinstance(chapter_range, int) and self.chapter == chapter_range:
                interventions.extend(orgs)
        
        return interventions
    
    def _analyze_simplified_regime(self) -> Dict[str, Any]:
        """Analiza elegibilidad para régimen simplificado"""
        # Capítulos típicamente excluidos
        excluded_chapters = [22, 24, 30, 87, 88, 89, 93]
        
        if self.chapter in excluded_chapters:
            return {
                "eligible": False,
                "reason": f"Capítulo {self.chapter} excluido del régimen simplificado",
                "restrictions": ["excluded_chapter"]
            }
        
        # Análisis por tipo de producto
        if self.chapter in range(84, 86):  # Electrónicos
            return {
                "eligible": True,
                "reason": "Productos electrónicos generalmente elegibles",
                "restrictions": ["max_value_usd_3000", "max_weight_50kg", "inti_certification"]
            }
        
        return {
            "eligible": True,
            "reason": "Posible elegibilidad (verificar restricciones específicas)",
            "restrictions": ["max_value_usd_3000", "max_weight_50kg"]
        }

class NCMDataLoader:
    """Cargador y preprocesador de datos NCM"""
    
    def __init__(self, data_file: str):
        self.data_file = Path(data_file)
        self.data: Optional[pd.DataFrame] = None
        self.positions: Dict[str, List[NCMPosition]] = {}
        self.load_data()
    
    def load_data(self) -> None:
        """Carga y preprocesa los datos NCM"""
        if not self.data_file.exists():
            raise FileNotFoundError(f"Archivo de datos no encontrado: {self.data_file}")
        
        logger.info(f"Cargando datos desde {self.data_file}")
        
        try:
            self.data = pd.read_csv(self.data_file)
            logger.info(f"Datos cargados: {len(self.data)} registros")
            
            # Validar estructura
            required_columns = ['code', 'sim', 'description', 'aec', 'die', 'te', 'in', 'de', 're']
            missing_columns = [col for col in required_columns if col not in self.data.columns]
            
            if missing_columns:
                raise ValueError(f"Columnas faltantes: {missing_columns}")
            
            # Preprocesar datos
            self._preprocess_data()
            self._index_positions()
            
        except Exception as e:
            logger.error(f"Error cargando datos: {e}")
            raise
    
    def _preprocess_data(self) -> None:
        """Preprocesa y limpia los datos"""
        # Limpiar valores nulos
        self.data = self.data.fillna({
            'sim': '',
            'description': '',
            'aec': 0.0,
            'die': 0.0,
            'te': 0.0,
            'in': '',
            'de': 0.0,
            're': 0.0,
            'parent': '',
            'parent_searchable': ''
        })
        
        # Normalizar códigos
        self.data['code_normalized'] = self.data['code'].apply(self._normalize_code)
        
        logger.info(f"Datos preprocesados. Tipos de registro: {self.data['record_type'].value_counts().to_dict()}")
    
    def _normalize_code(self, code: str) -> str:
        """Normaliza código NCM eliminando puntos y espacios"""
        if pd.isna(code):
            return ""
        return re.sub(r'[.\s-]', '', str(code).strip())
    
    def _index_positions(self) -> None:
        """Indexa posiciones para búsqueda rápida"""
        for _, row in self.data.iterrows():
            position = NCMPosition(
                file=row.get('file', ''),
                chapter=int(row.get('chapter', 0)),
                code=row.get('code', ''),
                sim=row.get('sim', ''),
                description=row.get('description', ''),
                aec=float(row.get('aec', 0)),
                die=float(row.get('die', 0)),
                te=float(row.get('te', 0)),
                in_field=row.get('in', ''),
                de=float(row.get('de', 0)),
                re=float(row.get('re', 0)),
                code_searchable=row.get('code_searchable', ''),
                parent=row.get('parent') if pd.notna(row.get('parent')) else None,
                parent_searchable=row.get('parent_searchable') if pd.notna(row.get('parent_searchable')) else None,
                hierarchy_level=int(row.get('hierarchy_level', 0)),
                record_type=row.get('record_type', 'unknown')
            )
            
            # Indexar por código normalizado
            normalized_code = self._normalize_code(position.code)
            if normalized_code not in self.positions:
                self.positions[normalized_code] = []
            self.positions[normalized_code].append(position)
        
        logger.info(f"Indexados {len(self.positions)} códigos únicos")

class NCMSearchEngine:
    """Motor de búsqueda para códigos NCM"""
    
    def __init__(self, data_loader: NCMDataLoader):
        self.data_loader = data_loader
        self.data = data_loader.data
        self.positions = data_loader.positions
    
    def exact_search(self, query: str) -> Optional[Dict[str, Any]]:
        """Búsqueda exacta con múltiples estrategias"""
        logger.info(f"Búsqueda exacta para: '{query}'")
        
        # Estrategia 1: Búsqueda por código completo con SIM
        exact_match = self._search_with_sim(query)
        if exact_match:
            return self._format_exact_result(query, exact_match, "exact_with_sim")
        
        # Estrategia 2: Búsqueda por código base (sin SIM)
        base_code = self._extract_base_code(query)
        if base_code:
            base_match = self._search_base_code(base_code)
            if base_match:
                return self._format_exact_result(query, base_match, "exact_base_code")
        
        # Estrategia 3: Normalización y búsqueda
        normalized_query = self.data_loader._normalize_code(query)
        if normalized_query in self.positions:
            # Preferir registros terminales
            candidates = self.positions[normalized_query]
            terminal_candidates = [p for p in candidates if p.record_type == 'terminal']
            
            if terminal_candidates:
                best_candidate = self._select_best_terminal(terminal_candidates)
                return self._format_exact_result(query, best_candidate, "exact_normalized")
            elif candidates:
                return self._format_exact_result(query, candidates[0], "exact_normalized")
        
        logger.info("No se encontró coincidencia exacta")
        return None
    
    def _search_with_sim(self, query: str) -> Optional[NCMPosition]:
        """Busca código específico con SIM"""
        # Patrón: "8528.72.00 100W" o "8528.72.00.100"
        pattern1 = re.match(r'^(\d{4}\.\d{2}\.\d{2})\s+([A-Z0-9]+)$', query.strip())
        pattern2 = re.match(r'^(\d{4}\.\d{2}\.\d{2})\.([A-Z0-9]+)$', query.strip())
        
        if pattern1:
            base_code = pattern1.group(1)
            sim_code = pattern1.group(2)
        elif pattern2:
            base_code = pattern2.group(1)
            sim_code = pattern2.group(2)
        else:
            return None
        
        # Buscar en dataframe
        mask = (self.data['code'] == base_code) & (self.data['sim'] == sim_code)
        matches = self.data[mask]
        
        if not matches.empty:
            row = matches.iloc[0]
            return self._row_to_position(row)
        
        return None
    
    def _extract_base_code(self, query: str) -> Optional[str]:
        """Extrae código base NCM de la consulta"""
        # Patrones típicos
        patterns = [
            r'^(\d{4}\.\d{2}\.\d{2})',  # 8528.72.00
            r'^(\d{8})',  # 85287200
            r'^(\d{2}\.\d{2}\.\d{2}\.\d{2})',  # 85.28.72.00
            r'^(\d{4})',  # 8528
            r'^(\d{2})'   # 85
        ]
        
        for pattern in patterns:
            match = re.match(pattern, query.strip())
            if match:
                return match.group(1)
        
        return None
    
    def _search_base_code(self, base_code: str) -> Optional[NCMPosition]:
        """Busca por código base sin SIM"""
        mask = (self.data['code'] == base_code) & (self.data['record_type'] == 'terminal')
        matches = self.data[mask]
        
        if not matches.empty:
            # Preferir registro con SIM más específico
            best_match = matches.iloc[0]
            return self._row_to_position(best_match)
        
        return None
    
    def _select_best_terminal(self, candidates: List[NCMPosition]) -> NCMPosition:
        """Selecciona el mejor candidato terminal"""
        # Priorizar por SIM específico, luego por descripción más detallada
        terminal_candidates = [c for c in candidates if c.record_type == 'terminal']
        
        if not terminal_candidates:
            return candidates[0]
        
        # Preferir los que tienen SIM específico
        with_sim = [c for c in terminal_candidates if c.sim]
        if with_sim:
            return with_sim[0]
        
        return terminal_candidates[0]
    
    def approximate_search(self, query: str) -> List[Dict[str, Any]]:
        """Búsqueda aproximada jerárquica"""
        logger.info(f"Búsqueda aproximada para: '{query}'")
        
        candidates = []
        
        # Estrategia 1: Búsqueda por descripción
        if not re.match(r'^\d', query.strip()):
            candidates.extend(self._search_by_description(query))
        
        # Estrategia 2: Búsqueda jerárquica por código parcial
        else:
            candidates.extend(self._hierarchical_search(query))
        
        # Eliminar duplicados y ordenar por relevancia
        unique_candidates = self._deduplicate_candidates(candidates)
        scored_candidates = self._score_candidates(unique_candidates, query)
        
        return scored_candidates[:15]  # Top 15 candidatos
    
    def _search_by_description(self, query: str) -> List[NCMPosition]:
        """Búsqueda por similitud de descripción mejorada"""
        candidates = []
        query_lower = query.lower()
        query_words = set(query_lower.split())
        
        # Palabras clave importantes para diferentes categorías
        category_keywords = {
            'electronics': ['televisor', 'tv', 'lcd', 'led', 'monitor', 'pantalla', 'telefono', 'celular', 'smartphone'],
            'animals': ['caballo', 'animal', 'vivo', 'ganado', 'equino'],
            'food': ['alimento', 'comida', 'bebida'],
            'chemicals': ['quimico', 'farmaco', 'medicamento'],
            'textiles': ['ropa', 'textil', 'tela', 'vestimenta']
        }
        
        # Determinar categoría probable del query
        query_category = None
        for category, keywords in category_keywords.items():
            if any(word in query_lower for word in keywords):
                query_category = category
                break
        
        for _, row in self.data.iterrows():
            description = str(row.get('description', '')).lower()
            if not description or len(description) < 3:
                continue
            
            # Filtro por categoría para evitar falsos positivos
            chapter = int(row.get('chapter', 0))
            if query_category == 'electronics' and chapter not in [84, 85]:
                continue
            elif query_category == 'animals' and chapter not in range(1, 25):
                continue
            elif query_category == 'chemicals' and chapter not in range(28, 40):
                continue
            
            # Similitud básica
            similarity = SequenceMatcher(None, query_lower, description).ratio()
            
            # Bonus por palabras clave coincidentes
            desc_words = set(description.split())
            word_overlap = len(query_words & desc_words) / max(len(query_words), 1)
            
            # Bonus por coincidencia exacta de palabras importantes
            exact_matches = 0
            for word in query_words:
                if word in description:
                    exact_matches += 1
            exact_match_bonus = exact_matches / len(query_words) if query_words else 0
            
            # Penalización por descripciones genéricas
            generic_penalty = 0
            if any(generic in description for generic in ['los demás', 'otros', 'las demás']):
                generic_penalty = 0.2
            
            combined_score = (similarity * 0.4) + (word_overlap * 0.3) + (exact_match_bonus * 0.3) - generic_penalty
            
            if combined_score > 0.4:  # Umbral más alto para mayor precisión
                position = self._row_to_position(row)
                position.similarity_score = combined_score
                candidates.append(position)
        
        return sorted(candidates, key=lambda x: getattr(x, 'similarity_score', 0), reverse=True)[:20]  # Top 20
    
    def _hierarchical_search(self, query: str) -> List[NCMPosition]:
        """Búsqueda jerárquica por código NCM"""
        base_code = self._extract_base_code(query)
        if not base_code:
            # Si no es un código, intentar búsqueda numérica directa
            if query.isdigit() and len(query) >= 2:
                base_code = query
            else:
                return []
        
        candidates = []
        normalized_base = self.data_loader._normalize_code(base_code)
        
        # Buscar por jerarquía: capítulo -> partida -> subpartida
        search_lengths = []
        if len(normalized_base) >= 2:
            search_lengths.append(min(len(normalized_base), 2))  # Capítulo
        if len(normalized_base) >= 4:
            search_lengths.append(min(len(normalized_base), 4))  # Partida
        if len(normalized_base) >= 6:
            search_lengths.append(min(len(normalized_base), 6))  # Subpartida
        if len(normalized_base) >= 8:
            search_lengths.append(min(len(normalized_base), 8))  # Código completo
        
        for level in search_lengths:
            prefix = normalized_base[:level]
            if len(prefix) == level:
                # Asegurar que code_searchable sea string
                searchable_col = self.data['code_searchable'].astype(str)
                matches = self.data[searchable_col.str.startswith(prefix)]
                
                for _, row in matches.iterrows():
                    position = self._row_to_position(row)
                    position.hierarchy_match_level = level
                    candidates.append(position)
                
                # Si encontramos muchos resultados en un nivel específico, no necesitamos más generales
                if len(matches) > 50 and level >= 4:
                    break
        
        return candidates
    
    def _deduplicate_candidates(self, candidates: List[NCMPosition]) -> List[NCMPosition]:
        """Elimina candidatos duplicados"""
        seen = set()
        unique = []
        
        for candidate in candidates:
            key = f"{candidate.code}_{candidate.sim}"
            if key not in seen:
                seen.add(key)
                unique.append(candidate)
        
        return unique
    
    def _score_candidates(self, candidates: List[NCMPosition], query: str) -> List[Dict[str, Any]]:
        """Asigna puntajes a candidatos"""
        scored = []
        
        for candidate in candidates:
            score = 0.0
            
            # Bonus por tipo terminal
            if candidate.record_type == 'terminal':
                score += 0.3
            
            # Bonus por nivel jerárquico específico
            if candidate.hierarchy_level >= 4:
                score += 0.2
            
            # Bonus por similitud precomputada
            if hasattr(candidate, 'similarity_score'):
                score += candidate.similarity_score * 0.5
            
            # Bonus por match jerárquico
            if hasattr(candidate, 'hierarchy_match_level'):
                score += (candidate.hierarchy_match_level / 8) * 0.3
            
            scored.append({
                'position': candidate,
                'score': score,
                'candidate_info': {
                    'code': candidate.code,
                    'sim': candidate.sim,
                    'description': candidate.description,
                    'score': round(score, 3),
                    'match_reasons': self._get_match_reasons(candidate, query)
                }
            })
        
        return sorted(scored, key=lambda x: x['score'], reverse=True)
    
    def _get_match_reasons(self, candidate: NCMPosition, query: str) -> List[str]:
        """Obtiene razones de coincidencia"""
        reasons = []
        
        if hasattr(candidate, 'similarity_score'):
            reasons.append(f"Similitud descripción: {candidate.similarity_score:.2f}")
        
        if hasattr(candidate, 'hierarchy_match_level'):
            reasons.append(f"Match jerárquico nivel {candidate.hierarchy_match_level}")
        
        if candidate.record_type == 'terminal':
            reasons.append("Registro terminal (específico)")
        
        return reasons
    
    def _row_to_position(self, row) -> NCMPosition:
        """Convierte fila de DataFrame a NCMPosition"""
        return NCMPosition(
            file=row.get('file', ''),
            chapter=int(row.get('chapter', 0)),
            code=row.get('code', ''),
            sim=row.get('sim', ''),
            description=row.get('description', ''),
            aec=float(row.get('aec', 0)),
            die=float(row.get('die', 0)),
            te=float(row.get('te', 0)),
            in_field=row.get('in', ''),
            de=float(row.get('de', 0)),
            re=float(row.get('re', 0)),
            code_searchable=row.get('code_searchable', ''),
            parent=row.get('parent') if pd.notna(row.get('parent')) else None,
            parent_searchable=row.get('parent_searchable') if pd.notna(row.get('parent_searchable')) else None,
            hierarchy_level=int(row.get('hierarchy_level', 0)),
            record_type=row.get('record_type', 'unknown')
        )
    
    def _format_exact_result(self, query: str, position: NCMPosition, method: str) -> Dict[str, Any]:
        """Formatea resultado de búsqueda exacta"""
        return {
            "input": query,
            "match_type": "exacto",
            "processing_time_ms": 0,  # Se calculará en el matcher principal
            "position": position.to_dict(),
            "metadata": {
                "classification_method": method,
                "confidence": 100,
                "search_strategy": "exact_match"
            }
        }

class AISelector:
    """Selector inteligente usando IA para casos aproximados"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or OPENAI_API_KEY
        self.client = None
        
        if OPENAI_AVAILABLE and self.api_key:
            self.client = OpenAI(api_key=self.api_key)
            logger.info("Selector IA inicializado correctamente")
        else:
            logger.warning("Selector IA no disponible (falta OpenAI o API key)")
    
    async def select_best_candidate(self, candidates: List[Dict], original_query: str) -> Dict[str, Any]:
        """Selecciona el mejor candidato usando IA"""
        if not self.client or not candidates:
            return self._fallback_selection(candidates, original_query)
        
        try:
            # Preparar contexto para IA
            candidates_text = self._format_candidates_for_ai(candidates)
            
            system_prompt = """
Eres un experto en códigos NCM argentinos. Te proporciono candidatos de posiciones arancelarias.
Selecciona la MÁS ESPECÍFICA y APROPIADA basada en la descripción original.

CRITERIOS DE SELECCIÓN:
1. Máxima especificidad (más dígitos = mejor)
2. Descripción más cercana al producto original  
3. Evitar códigos genéricos ("los demás")
4. Preferir registros terminales sobre subcategorías
5. Considerar el contexto del capítulo NCM

RESPUESTA: JSON con 'selected_code', 'selected_sim', 'confidence_score' (0-100) y 'reasoning'
"""
            
            user_prompt = f"""
PRODUCTO ORIGINAL: {original_query}

CANDIDATOS DISPONIBLES:
{candidates_text}

Selecciona el código más apropiado considerando especificidad y relevancia.
"""
            
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            ai_decision = json.loads(response.choices[0].message.content)
            
            # Encontrar el candidato seleccionado
            selected_candidate = self._find_selected_candidate(candidates, ai_decision)
            
            if selected_candidate:
                return self._format_ai_result(original_query, selected_candidate, ai_decision)
            else:
                logger.warning("IA no pudo seleccionar candidato válido, usando fallback")
                return self._fallback_selection(candidates, original_query)
                
        except Exception as e:
            logger.error(f"Error en selección IA: {e}")
            return self._fallback_selection(candidates, original_query)
    
    def _format_candidates_for_ai(self, candidates: List[Dict]) -> str:
        """Formatea candidatos para enviar a IA"""
        formatted = []
        
        for i, candidate in enumerate(candidates[:10], 1):  # Top 10 para IA
            pos = candidate['position']
            info = candidate['candidate_info']
            
            formatted.append(f"""
{i}. CÓDIGO: {pos.code} {pos.sim if pos.sim else '(sin SIM)'}
   DESCRIPCIÓN: {pos.description}
   TIPO: {pos.record_type}
   CAPÍTULO: {pos.chapter}
   NIVEL: {pos.hierarchy_level}
   SCORE: {info['score']}
   RAZONES: {', '.join(info['match_reasons'])}
""")
        
        return '\n'.join(formatted)
    
    def _find_selected_candidate(self, candidates: List[Dict], ai_decision: Dict) -> Optional[NCMPosition]:
        """Encuentra el candidato seleccionado por la IA"""
        selected_code = ai_decision.get('selected_code', '')
        selected_sim = ai_decision.get('selected_sim', '')
        
        for candidate in candidates:
            pos = candidate['position']
            if pos.code == selected_code and pos.sim == selected_sim:
                return pos
        
        # Fallback: buscar solo por código
        for candidate in candidates:
            pos = candidate['position']
            if pos.code == selected_code:
                return pos
        
        return None
    
    def _format_ai_result(self, query: str, position: NCMPosition, ai_decision: Dict) -> Dict[str, Any]:
        """Formatea resultado de selección IA"""
        return {
            "input": query,
            "match_type": "aproximado",
            "processing_time_ms": 0,  # Se calculará en el matcher principal
            "position": position.to_dict(),
            "ai_selection": {
                "confidence": ai_decision.get('confidence_score', 0),
                "reasoning": ai_decision.get('reasoning', ''),
                "method": "gpt-4o-mini"
            },
            "metadata": {
                "classification_method": "ai_assisted_approximate",
                "confidence": ai_decision.get('confidence_score', 0)
            }
        }
    
    def _fallback_selection(self, candidates: List[Dict], query: str) -> Dict[str, Any]:
        """Selección de fallback sin IA"""
        if not candidates:
            return {
                "input": query,
                "match_type": "error",
                "error": "No se encontraron candidatos válidos",
                "metadata": {"classification_method": "fallback_none"}
            }
        
        # Seleccionar candidato con mayor score
        best_candidate = max(candidates, key=lambda x: x['score'])
        position = best_candidate['position']
        
        return {
            "input": query,
            "match_type": "aproximado",
            "processing_time_ms": 0,
            "position": position.to_dict(),
            "fallback_selection": {
                "confidence": min(int(best_candidate['score'] * 100), 95),
                "reasoning": "Selección automática por mayor puntaje de coincidencia",
                "method": "score_based"
            },
            "metadata": {
                "classification_method": "fallback_score_based",
                "confidence": min(int(best_candidate['score'] * 100), 95)
            }
        }

class NCMPositionMatcher:
    """Clasificador principal de posiciones NCM"""
    
    def __init__(self, data_file: str, ai_api_key: str = None):
        self.data_loader = NCMDataLoader(data_file)
        self.search_engine = NCMSearchEngine(self.data_loader)
        self.ai_selector = AISelector(ai_api_key)
        logger.info("NCMPositionMatcher inicializado correctamente")
    
    async def match_position(self, input_query: str) -> Dict[str, Any]:
        """Función principal de matching"""
        start_time = datetime.now()
        
        logger.info(f"Procesando consulta: '{input_query}'")
        
        if not input_query or not input_query.strip():
            return {
                "input": input_query,
                "match_type": "error",
                "error": "Consulta vacía",
                "processing_time_ms": 0
            }
        
        try:
            # Paso 1: Búsqueda exacta
            exact_result = self.search_engine.exact_search(input_query)
            
            if exact_result:
                processing_time = (datetime.now() - start_time).total_seconds() * 1000
                exact_result["processing_time_ms"] = round(processing_time, 2)
                logger.info(f"Coincidencia exacta encontrada en {processing_time:.2f}ms")
                return exact_result
            
            # Paso 2: Búsqueda aproximada
            candidates = self.search_engine.approximate_search(input_query)
            
            if not candidates:
                processing_time = (datetime.now() - start_time).total_seconds() * 1000
                return {
                    "input": input_query,
                    "match_type": "sin_resultados",
                    "error": "No se encontraron candidatos relevantes",
                    "processing_time_ms": round(processing_time, 2),
                    "metadata": {"classification_method": "no_matches"}
                }
            
            # Paso 3: Selección por IA
            result = await self.ai_selector.select_best_candidate(candidates, input_query)
            
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            result["processing_time_ms"] = round(processing_time, 2)
            result["candidates_analyzed"] = len(candidates)
            
            logger.info(f"Selección completada en {processing_time:.2f}ms con {len(candidates)} candidatos")
            return result
            
        except Exception as e:
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            logger.error(f"Error en matching: {e}")
            return {
                "input": input_query,
                "match_type": "error",
                "error": str(e),
                "processing_time_ms": round(processing_time, 2),
                "metadata": {"classification_method": "error"}
            }
    
    def get_statistics(self) -> Dict[str, Any]:
        """Obtiene estadísticas del dataset cargado"""
        data = self.data_loader.data
        
        return {
            "total_records": len(data),
            "unique_codes": data['code'].nunique(),
            "chapters": sorted(data['chapter'].unique().tolist()),
            "record_types": data['record_type'].value_counts().to_dict(),
            "terminal_records": len(data[data['record_type'] == 'terminal']),
            "subcategory_records": len(data[data['record_type'] == 'subcategory']),
            "data_file": str(self.data_loader.data_file)
        }

# Funciones de conveniencia
async def match_single_ncm(input_query: str, data_file: str, ai_api_key: str = None) -> Dict[str, Any]:
    """Función de conveniencia para matching individual"""
    matcher = NCMPositionMatcher(data_file, ai_api_key)
    return await matcher.match_position(input_query)

def find_latest_ncm_dataset(fallback_path: str = None) -> str:
    """Encuentra el dataset NCM más reciente automáticamente"""
    from pathlib import Path
    
    # Buscar en la carpeta de resultados
    results_dir = Path("pdf_reader/ncm/resultados_ncm_hybrid")
    if results_dir.exists():
        # Buscar archivos de dataset consolidado
        dataset_files = list(results_dir.glob("dataset_ncm_HYBRID_FIXED_*.csv"))
        if dataset_files:
            # Retornar el más reciente
            latest_file = max(dataset_files, key=lambda f: f.stat().st_mtime)
            return str(latest_file)
    
    # Usar fallback si no se encuentra nada
    return fallback_path or 'pdf_reader/ncm/resultados_ncm_hybrid/dataset_ncm_HYBRID_FIXED_20250721_175449.csv'

def validate_ncm_code(code: str) -> bool:
    """Valida formato de código NCM"""
    patterns = [
        r'^\d{4}\.\d{2}\.\d{2}$',  # 8528.72.00
        r'^\d{4}\.\d{2}\.\d{2}\s+[A-Z0-9]+$',  # 8528.72.00 100W
        r'^\d{8}$',  # 85287200
        r'^\d{2}\.\d{2}\.\d{2}\.\d{2}$'  # 85.28.72.00
    ]
    
    return any(re.match(pattern, code.strip()) for pattern in patterns)

# CLI Interface
async def main():
    """Función principal CLI"""
    parser = argparse.ArgumentParser(
        description="NCM Position Matcher - Validador de códigos NCM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  python ncm_position_matcher.py --input "8528.72.00" --data posiciones.csv
  python ncm_position_matcher.py --input "televisor LCD" --data posiciones.csv --ai
  python ncm_position_matcher.py --batch productos.json --output resultados.json
  python ncm_position_matcher.py --stats --data posiciones.csv
        """
    )
    
    parser.add_argument('--input', '-i', type=str, help='Código NCM o descripción a buscar')
    parser.add_argument('--data', '-d', type=str, default=None, help='Archivo CSV con datos NCM (usa el más reciente si no se especifica)')
    parser.add_argument('--output', '-o', type=str, help='Archivo de salida para resultados (opcional)')
    parser.add_argument('--batch', '-b', type=str, help='Archivo JSON con múltiples consultas')
    parser.add_argument('--stats', action='store_true', help='Mostrar estadísticas del dataset')
    parser.add_argument('--ai', action='store_true', help='Habilitar selección por IA (requiere OpenAI API key)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Logging detallado')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Buscar dataset automáticamente si no se especifica
    if not args.data:
        args.data = find_latest_ncm_dataset()
        print(f"📁 Usando dataset automático: {args.data}")
    
    # Verificar archivo de datos
    if not Path(args.data).exists():
        print(f"❌ Error: Archivo de datos no encontrado: {args.data}")
        return 1
    
    try:
        matcher = NCMPositionMatcher(args.data, OPENAI_API_KEY if args.ai else None)
        
        # Mostrar estadísticas
        if args.stats:
            stats = matcher.get_statistics()
            print(f"\n📊 ESTADÍSTICAS DEL DATASET")
            print(f"{'='*50}")
            print(f"📋 Total de registros: {stats['total_records']:,}")
            print(f"🔢 Códigos únicos: {stats['unique_codes']:,}")
            print(f"📚 Capítulos: {len(stats['chapters'])} ({min(stats['chapters'])}-{max(stats['chapters'])})")
            print(f"💰 Registros terminales: {stats['terminal_records']:,}")
            print(f"📂 Subcategorías: {stats['subcategory_records']:,}")
            print(f"📁 Archivo fuente: {stats['data_file']}")
            return 0
        
        # Búsqueda individual
        if args.input:
            print(f"\n🔍 Buscando: '{args.input}'")
            result = await matcher.match_position(args.input)
            
            # Mostrar resultado
            print(f"\n📋 RESULTADO")
            print(f"{'='*50}")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            
            # Guardar si se especifica archivo
            if args.output:
                with open(args.output, 'w', encoding='utf-8') as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
                print(f"\n💾 Resultado guardado en: {args.output}")
            
            return 0
        
        # Procesamiento por lotes
        if args.batch:
            if not Path(args.batch).exists():
                print(f"❌ Error: Archivo de lotes no encontrado: {args.batch}")
                return 1
            
            with open(args.batch, 'r', encoding='utf-8') as f:
                batch_data = json.load(f)
            
            if not isinstance(batch_data, list):
                print(f"❌ Error: El archivo de lotes debe contener una lista de consultas")
                return 1
            
            print(f"\n🔄 Procesando {len(batch_data)} consultas...")
            results = []
            
            for i, query in enumerate(batch_data, 1):
                print(f"Procesando {i}/{len(batch_data)}: {query}")
                result = await matcher.match_position(str(query))
                results.append(result)
            
            # Guardar resultados
            output_file = args.output or f"batch_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            
            print(f"\n✅ Procesamiento completado. Resultados en: {output_file}")
            return 0
        
        # Si no hay argumentos específicos, mostrar ayuda
        parser.print_help()
        return 0
        
    except Exception as e:
        logger.error(f"Error en ejecución: {e}")
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main())) 