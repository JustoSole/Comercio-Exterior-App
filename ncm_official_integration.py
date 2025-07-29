#!/usr/bin/env python3
"""
🏛️ NCM Official Integration - Integración con Base de Datos Oficial NCM
========================================================================

Módulo que integra el sistema de clasificación con la base de datos oficial
de códigos NCM extraída de los PDFs oficiales usando el sistema híbrido.

Reemplaza la funcionalidad obsoleta de scraping VUCE con datos oficiales
procesados localmente.

Funcionalidades:
- Búsqueda exacta de códigos NCM en base de datos oficial
- Búsqueda jerárquica inteligente
- Enriquecimiento con datos arancelarios oficiales
- Validación y normalización de códigos
- Análisis de régimen simplificado actualizado

Autor: Desarrollado para comercio exterior argentino
"""

import os
import json
import re
import logging
from typing import Dict, List, Optional, Union, Any, Tuple
from pathlib import Path
import pandas as pd
from datetime import datetime

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

class NCMOfficialIntegration:
    """Integración con la base de datos oficial NCM procesada localmente"""
    
    def __init__(self, dataset_path: Optional[str] = None):
        """
        Inicializar la integración con base de datos oficial NCM
        
        Args:
            dataset_path: Ruta al dataset consolidado. Si None, busca automáticamente.
        """
        self.dataset_path = self._find_latest_dataset(dataset_path)
        self.ncm_data = None
        self.load_dataset()
        
    def _find_latest_dataset(self, custom_path: Optional[str] = None) -> Optional[Path]:
        """Encuentra el dataset más reciente de NCM"""
        if custom_path:
            return Path(custom_path)
            
        # Buscar en la carpeta de resultados
        results_dir = Path("pdf_reader/ncm/resultados_ncm_hybrid")
        if not results_dir.exists():
            logger.error(f"Directorio de resultados no encontrado: {results_dir}")
            return None
            
        # Buscar archivos de dataset consolidado
        dataset_files = list(results_dir.glob("dataset_ncm_HYBRID_FIXED_*.json"))
        if not dataset_files:
            logger.error("No se encontraron datasets NCM consolidados")
            return None
            
        # Retornar el más reciente
        latest_file = max(dataset_files, key=lambda f: f.stat().st_mtime)
        logger.info(f"Usando dataset NCM: {latest_file}")
        return latest_file
        
    def load_dataset(self) -> bool:
        """Carga el dataset de NCM en memoria"""
        if not self.dataset_path or not self.dataset_path.exists():
            logger.error(f"Dataset no encontrado: {self.dataset_path}")
            return False
            
        try:
            with open(self.dataset_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # Extraer registros
            self.ncm_data = data.get('records', [])
            metadata = data.get('metadata', {})
            
            logger.info(f"Dataset cargado exitosamente:")
            logger.info(f"  - Total registros: {len(self.ncm_data):,}")
            logger.info(f"  - Versión: {metadata.get('version', 'N/A')}")
            logger.info(f"  - Capítulos: {metadata.get('total_chapters', 'N/A')}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error cargando dataset: {e}")
            return False
            
    def normalize_ncm_code(self, ncm_code: str) -> str:
        """Normaliza código NCM eliminando puntos, espacios y guiones"""
        if not ncm_code:
            return ""
        return re.sub(r'[.\s-]', '', str(ncm_code).strip())
        
    def search_exact_ncm(self, ncm_code: str) -> Optional[Dict[str, Any]]:
        """Búsqueda exacta de código NCM"""
        if not self.ncm_data:
            return None
            
        normalized_code = self.normalize_ncm_code(ncm_code)
        
        # Buscar por código exacto
        for record in self.ncm_data:
            if record.get('code_searchable') == normalized_code:
                return self._enrich_ncm_record(record)
                
        return None
        
    def search_hierarchical_ncm(self, ncm_code: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Búsqueda jerárquica de códigos NCM similares"""
        if not self.ncm_data:
            return []
            
        normalized_code = self.normalize_ncm_code(ncm_code)
        matches = []
        
        # Búsqueda por prefijo (jerarquía)
        for length in [8, 6, 4, 2]:  # Buscar desde más específico a más general
            prefix = normalized_code[:length]
            if len(prefix) >= 2:  # Mínimo un capítulo
                for record in self.ncm_data:
                    record_code = record.get('code_searchable', '')
                    if record_code.startswith(prefix) and len(matches) < max_results:
                        enriched_record = self._enrich_ncm_record(record)
                        enriched_record['match_type'] = f'hierarchical_{length}digits'
                        enriched_record['match_score'] = self._calculate_match_score(normalized_code, record_code)
                        matches.append(enriched_record)
                        
            if matches:  # Si encontramos matches en este nivel, retornar
                break
                
        # Ordenar por score de similitud
        matches.sort(key=lambda x: x.get('match_score', 0), reverse=True)
        return matches[:max_results]
        
    def _calculate_match_score(self, query_code: str, record_code: str) -> float:
        """Calcula score de similitud entre códigos"""
        if not query_code or not record_code:
            return 0.0
            
        # Score basado en longitud de prefijo común
        common_prefix = 0
        min_length = min(len(query_code), len(record_code))
        
        for i in range(min_length):
            if query_code[i] == record_code[i]:
                common_prefix += 1
            else:
                break
                
        return common_prefix / max(len(query_code), len(record_code))
        
    def _enrich_ncm_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Enriquece un registro NCM con información adicional"""
        enriched = {
            'ncm_code': record.get('code', ''),
            'ncm_code_normalized': record.get('code_searchable', ''),
            'sim_code': record.get('sim', ''),
            'description': record.get('description', ''),
            'chapter': record.get('chapter', 0),
            'record_type': record.get('record_type', 'unknown'),
            'hierarchy_level': record.get('hierarchy_level', 0),
            'parent_code': record.get('parent', ''),
            
            # Datos arancelarios oficiales
            'tratamiento_arancelario': {
                'aec': float(record.get('aec', 0)),  # Arancel Externo Común
                'die': float(record.get('die', 0)),  # Derecho de Importación Específico
                'te': float(record.get('te', 3.0)),   # Tasa Estadística (default 3%)
                'de': float(record.get('de', 0)),    # Derecho de Exportación
                're': float(record.get('re', 0)),    # Reintegro de Exportación
                'in_code': record.get('in', ''),     # Código IN oficial
                'iva': 21.0,                         # IVA Argentina
                'iva_adicional': 0.0,
                'fuente': 'Base de Datos Oficial NCM'
            },
            
            # Análisis de régimen simplificado
            'regimen_simplificado': self._analyze_simplified_regime(record),
            
            # Intervenciones potenciales
            'intervenciones_detectadas': self._detect_interventions(record),
            
            # Metadatos
            'source_metadata': {
                'extraction_method': 'official_database',
                'file_source': record.get('file', ''),
                'data_quality': 'high',
                'last_updated': datetime.now().isoformat()
            }
        }
        
        return enriched
        
    def _analyze_simplified_regime(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Analiza si el producto puede aplicar al régimen simplificado"""
        chapter = record.get('chapter', 0)
        ncm_code = record.get('code', '')
        description = record.get('description', '').lower()
        
        # Capítulos típicamente excluidos del régimen simplificado
        excluded_chapters = [22, 24, 30]  # Bebidas, tabaco, farmacéuticos
        potentially_excluded = [87, 88, 89, 93]  # Vehículos, armas
        
        if chapter in excluded_chapters:
            return {
                'aplica_potencialmente': False,
                'razon': f'Capítulo {chapter} excluido del régimen simplificado',
                'factores_verificar': ['Autorización ANMAT/SENASA requerida'],
                'observaciones': 'Producto típicamente excluido por normativa'
            }
            
        elif chapter in potentially_excluded:
            return {
                'aplica_potencialmente': False,
                'razon': f'Capítulo {chapter} generalmente excluido',
                'factores_verificar': ['Verificar con organismo competente'],
                'observaciones': 'Requiere verificación específica'
            }
            
        else:
            # Capítulos que generalmente SÍ aplican
            favorable_chapters = [84, 85, 61, 62, 63, 95]  # Electrónicos, textiles, juguetes
            
            return {
                'aplica_potencialmente': chapter in favorable_chapters,
                'razon': f'Capítulo {chapter} {"favorable" if chapter in favorable_chapters else "neutral"} para régimen simplificado',
                'factores_verificar': [
                    'Valor CIF ≤ USD 3,000',
                    'Peso ≤ 50kg',
                    'Courier habilitado',
                    'Sin restricciones específicas'
                ],
                'observaciones': 'Sujeto a límites de valor y peso'
            }
            
    def _detect_interventions(self, record: Dict[str, Any]) -> List[str]:
        """Detecta posibles intervenciones según el capítulo NCM"""
        chapter = record.get('chapter', 0)
        description = record.get('description', '').lower()
        
        interventions = []
        
        # Mapeo de capítulos a organismos
        # Productos agropecuarios y alimentarios
        if 1 <= chapter <= 24:
            interventions.append('SENASA')
        
        # Farmacéuticos
        if chapter == 30:
            interventions.append('ANMAT')
            
        # Cosméticos
        if chapter == 33:
            interventions.append('ANMAT')
            
        # Productos eléctricos/electrónicos
        if chapter in [84, 85]:
            interventions.append('INTI-CIE')
            
        # Vehículos (generalmente no aplica régimen)
        if chapter in [87, 88, 89]:
            interventions.append('INTI')
            
        # Juguetes
        if chapter == 95:
            interventions.append('INTI')
            
        # Armas (generalmente no aplica régimen)
        if chapter == 93:
            interventions.append('ANMaC')
                
        # Detección adicional por palabras clave
        if any(word in description for word in ['electronic', 'electr', 'bateria', 'cargador']):
            if 'INTI-CIE' not in interventions:
                interventions.append('INTI-CIE')
                
        if any(word in description for word in ['juguete', 'toy', 'niño']):
            if 'INTI' not in interventions:
                interventions.append('INTI')
                
        return interventions
        
    def _is_intermediate_position(self, record: Dict[str, Any]) -> bool:
        """Detecta si una posición NCM es intermedia (tiene subcategorías)"""
        # Criterio principal: record_type debe ser 'subcategory'
        record_type = record.get('record_type', '')
        
        # Es intermedia si es explícitamente marcada como subcategoría
        is_subcategory = record_type == 'subcategory'
        
        # Log para debugging
        if is_subcategory:
            logger.info(f"✅ Posición intermedia detectada: {record.get('ncm_code', 'N/A')} (record_type = {record_type})")
        
        return is_subcategory
        
    def get_subcategories(self, parent_code: str) -> List[Dict[str, Any]]:
        """Obtiene todas las subcategorías hijas de un código NCM"""
        if not self.ncm_data:
            return []
            
        normalized_parent = self.normalize_ncm_code(parent_code)
        subcategories = []
        
        logger.info(f"🔍 Buscando subcategorías para código padre: {parent_code} (normalizado: {normalized_parent})")
        
        for record in self.ncm_data:
            record_code = record.get('code_searchable', '')
            record_type = record.get('record_type', '')
            sim_code = record.get('sim', '')
            
            # Buscar registros terminales que tengan el mismo código base pero con SIM diferente
            # Ejemplo: padre "61159500" (subcategory) -> hijos "61159500" con SIM "100P", "200V", etc. (terminal)
            if (record_code == normalized_parent and 
                record_type == 'terminal' and 
                sim_code and sim_code.strip()):
                
                enriched = self._enrich_ncm_record(record)
                subcategories.append(enriched)
                logger.debug(f"   Encontrada subcategoría: {record.get('code', 'N/A')} SIM:{sim_code} - {record.get('description', 'N/A')[:50]}...")
                
        logger.info(f"📊 Total subcategorías encontradas: {len(subcategories)}")
        
        # Ordenar por SIM code para mantener orden lógico
        subcategories.sort(key=lambda x: x.get('sim_code', ''))
        return subcategories
        
    async def refine_ncm_with_llm(self, initial_position: Dict[str, Any], 
                                  product_description: str) -> Dict[str, Any]:
        """
        Refina la clasificación NCM usando un segundo LLM cuando hay subcategorías
        """
        # Verificar si la posición inicial es intermedia
        if not self._is_intermediate_position(initial_position):
            logger.info("Posición ya es terminal, no requiere refinamiento")
            return initial_position
            
        # Obtener subcategorías
        parent_code = initial_position.get('ncm_code', '')
        subcategories = self.get_subcategories(parent_code)
        
        if not subcategories:
            logger.warning(f"No se encontraron subcategorías para {parent_code}")
            return initial_position
            
        logger.info(f"Encontradas {len(subcategories)} subcategorías para refinamiento")
        
        # Preparar opciones para el LLM
        subcategory_options = []
        for i, subcat in enumerate(subcategories, 1):
            aec = subcat.get('tratamiento_arancelario', {}).get('aec', 0)
            description = subcat.get('description', '')
            code = subcat.get('ncm_code', '')
            
            subcategory_options.append(f"{i}. {code} - {description} (AEC: {aec}%)")
            
        options_text = "\n".join(subcategory_options)
        
        # Prompt para el LLM de refinamiento
        refinement_prompt = f"""Eres un especialista en clasificación arancelaria NCM. 

Se encontró la categoría general: {parent_code} - {initial_position.get('description', '')}

Pero necesitas elegir la subcategoría específica más apropiada para este producto:
"{product_description}"

Opciones disponibles:
{options_text}

INSTRUCCIONES:
1. Analiza cuidadosamente la descripción del producto
2. Compara con las opciones disponibles
3. Elige la subcategoría MÁS ESPECÍFICA y APROPIADA
4. Responde ÚNICAMENTE con el número de la opción elegida (1, 2, 3, etc.)
5. NO agregues explicaciones adicionales

Tu respuesta debe ser solo el número:"""

        try:
            # Importar OpenAI para el refinamiento
            from openai import OpenAI
            import os
            
            # Obtener API key
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                try:
                    import streamlit as st
                    api_key = st.secrets["api_keys"]["OPENAI_API_KEY"]
                except:
                    pass
                    
            if not api_key:
                logger.error("No se encontró API key de OpenAI para refinamiento")
                return initial_position
                
            client = OpenAI(api_key=api_key)
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Eres un especialista en clasificación arancelaria. Responde solo con números."},
                    {"role": "user", "content": refinement_prompt}
                ],
                temperature=0,
                max_tokens=10
            )
            
            llm_response = response.choices[0].message.content.strip()
            logger.info(f"LLM de refinamiento respondió: '{llm_response}'")
            
            # Extraer número de la respuesta
            import re
            number_match = re.search(r'\b(\d+)\b', llm_response)
            
            if number_match:
                chosen_index = int(number_match.group(1)) - 1  # Convertir a índice base 0
                
                if 0 <= chosen_index < len(subcategories):
                    chosen_subcategory = subcategories[chosen_index]
                    
                    logger.info(f"✅ LLM eligió subcategoría: {chosen_subcategory.get('ncm_code')} - {chosen_subcategory.get('description')}")
                    
                    # Enriquecer con información del refinamiento
                    chosen_subcategory['refinement_info'] = {
                        'was_refined': True,
                        'original_code': parent_code,
                        'total_options': len(subcategories),
                        'chosen_option': chosen_index + 1,
                        'llm_response': llm_response
                    }
                    
                    return chosen_subcategory
                else:
                    logger.error(f"Índice fuera de rango: {chosen_index}")
            else:
                logger.error(f"No se pudo extraer número de la respuesta: '{llm_response}'")
                
        except Exception as e:
            logger.error(f"Error en refinamiento con LLM: {e}")
            
        # Si algo falla, retornar la posición original
        logger.warning("Refinamiento falló, usando posición original")
        return initial_position
        
    def _build_complete_ncm_code(self, record: Dict[str, Any]) -> str:
        """Construye el código NCM completo incluyendo sufijo SIM si existe"""
        base_code = record.get('ncm_code', '')
        sim_code = record.get('sim_code', '')
        
        if sim_code and sim_code.strip():
            # Formato estándar: código_base + ' ' + sufijo_SIM
            # Ejemplo: "8528.72.00 100W" o "8528.72.00.100"
            complete_code = f"{base_code} {sim_code}"
            logger.info(f"✅ Código NCM completo construido: {complete_code}")
            return complete_code
        else:
            return base_code

    async def get_ncm_info(self, ncm_code: str, product_description: str = None) -> Dict[str, Any]:
        """
        Función principal para obtener información de NCM
        Mantiene compatibilidad con la interfaz anterior de VUCE
        
        Args:
            ncm_code: Código NCM a buscar
            product_description: Descripción del producto para refinamiento automático
        """
        if not self.ncm_data:
            return {
                'success': False,
                'error': 'Base de datos NCM no disponible',
                'ncm_code': ncm_code
            }
            
        # Búsqueda exacta primero
        exact_match = self.search_exact_ncm(ncm_code)
        if exact_match:
            # Verificar si necesita refinamiento y si tenemos descripción del producto
            if product_description and self._is_intermediate_position(exact_match):
                logger.info(f"Posición intermedia detectada para {ncm_code}, iniciando refinamiento...")
                refined_match = await self.refine_ncm_with_llm(exact_match, product_description)
                
                return {
                    'success': True,
                    'match_exacto': True,
                    'was_refined': refined_match.get('refinement_info', {}).get('was_refined', False),
                    'posicion_encontrada': {
                        'codigo': self._build_complete_ncm_code(refined_match),
                        'descripcion': refined_match['description']
                    },
                    'tratamiento_arancelario': refined_match['tratamiento_arancelario'],
                    'regimen_simplificado': refined_match['regimen_simplificado'],
                    'intervenciones': {
                        'organismos_potenciales': refined_match['intervenciones_detectadas']
                    },
                    'metadata': refined_match['source_metadata'],
                    'refinement_info': refined_match.get('refinement_info', {})
                }
            else:
                return {
                    'success': True,
                    'match_exacto': True,
                    'was_refined': False,
                    'posicion_encontrada': {
                        'codigo': self._build_complete_ncm_code(exact_match),
                        'descripcion': exact_match['description']
                    },
                    'tratamiento_arancelario': exact_match['tratamiento_arancelario'],
                    'regimen_simplificado': exact_match['regimen_simplificado'],
                    'intervenciones': {
                        'organismos_potenciales': exact_match['intervenciones_detectadas']
                    },
                    'metadata': exact_match['source_metadata']
                }
            
        # Búsqueda jerárquica si no hay match exacto
        hierarchical_matches = self.search_hierarchical_ncm(ncm_code)
        if hierarchical_matches:
            best_match = hierarchical_matches[0]
            
            # Verificar si el mejor match necesita refinamiento
            if product_description and self._is_intermediate_position(best_match):
                logger.info(f"Match jerárquico intermedio detectado para {ncm_code}, iniciando refinamiento...")
                refined_match = await self.refine_ncm_with_llm(best_match, product_description)
                
                return {
                    'success': True,
                    'match_exacto': False,
                    'was_refined': refined_match.get('refinement_info', {}).get('was_refined', False),
                    'posicion_encontrada': {
                        'codigo': self._build_complete_ncm_code(refined_match),
                        'descripcion': refined_match['description']
                    },
                    'tratamiento_arancelario': refined_match['tratamiento_arancelario'],
                    'regimen_simplificado': refined_match['regimen_simplificado'],
                    'intervenciones': {
                        'organismos_potenciales': refined_match['intervenciones_detectadas']
                    },
                    'metadata': refined_match['source_metadata'],
                    'match_info': {
                        'type': best_match.get('match_type', 'hierarchical'),
                        'score': best_match.get('match_score', 0),
                        'alternatives': len(hierarchical_matches)
                    },
                    'refinement_info': refined_match.get('refinement_info', {})
                }
            else:
                return {
                    'success': True,
                    'match_exacto': False,
                    'was_refined': False,
                    'posicion_encontrada': {
                        'codigo': self._build_complete_ncm_code(best_match),
                        'descripcion': best_match['description']
                    },
                    'tratamiento_arancelario': best_match['tratamiento_arancelario'],
                    'regimen_simplificado': best_match['regimen_simplificado'],
                    'intervenciones': {
                        'organismos_potenciales': best_match['intervenciones_detectadas']
                    },
                    'metadata': best_match['source_metadata'],
                    'match_info': {
                        'type': best_match.get('match_type', 'hierarchical'),
                        'score': best_match.get('match_score', 0),
                        'alternatives': len(hierarchical_matches)
                    }
                }
            
        # No se encontró información
        return {
            'success': False,
            'error': f'No se encontró información para el código NCM: {ncm_code}',
            'ncm_code': ncm_code,
            'suggestions': 'Verificar que el código NCM sea válido'
        }
        
    def get_chapter_summary(self, chapter: int) -> Dict[str, Any]:
        """Obtiene resumen de un capítulo específico"""
        if not self.ncm_data:
            return {}
            
        chapter_records = [r for r in self.ncm_data if r.get('chapter') == chapter]
        
        if not chapter_records:
            return {'error': f'No se encontraron datos para el capítulo {chapter}'}
            
        return {
            'chapter': chapter,
            'total_records': len(chapter_records),
            'record_types': {
                record_type: len([r for r in chapter_records if r.get('record_type') == record_type])
                for record_type in set(r.get('record_type', 'unknown') for r in chapter_records)
            },
            'terminal_positions': len([r for r in chapter_records if r.get('record_type') == 'terminal']),
            'has_fiscal_data': len([r for r in chapter_records if r.get('aec', 0) > 0])
        }
        
    def validate_ncm_format(self, ncm_code: str) -> Dict[str, Any]:
        """Valida el formato de un código NCM"""
        if not ncm_code:
            return {'valid': False, 'error': 'Código NCM vacío'}
            
        # Patterns válidos para NCM
        patterns = [
            r'^\d{4}\.\d{2}\.\d{2}$',      # Formato completo: 1234.56.78
            r'^\d{8}$',                     # Sin puntos: 12345678
            r'^\d{4}\.\d{2}$',             # Parcial: 1234.56
            r'^\d{6}$',                     # Parcial sin puntos: 123456
            r'^\d{4}$',                     # Solo partida: 1234
            r'^\d{2}$'                      # Solo capítulo: 12
        ]
        
        normalized = self.normalize_ncm_code(ncm_code)
        
        for pattern in patterns:
            if re.match(pattern, ncm_code) or re.match(pattern.replace(r'\.', ''), normalized):
                return {
                    'valid': True,
                    'normalized': normalized,
                    'format': 'valid_ncm',
                    'length': len(normalized)
                }
                
        return {
            'valid': False,
            'error': 'Formato de código NCM inválido',
            'expected_formats': ['1234.56.78', '12345678', '1234.56', '123456', '1234', '12']
        }

# Instancia global para uso fácil
_ncm_integration_instance = None

def get_ncm_integration() -> NCMOfficialIntegration:
    """Obtiene instancia singleton de la integración NCM"""
    global _ncm_integration_instance
    if _ncm_integration_instance is None:
        _ncm_integration_instance = NCMOfficialIntegration()
    return _ncm_integration_instance

# Función de compatibilidad para reemplazar VUCE
async def get_ncm_info_official(ncm_code: str, product_description: str = None) -> Dict[str, Any]:
    """
    Función de compatibilidad que reemplaza la funcionalidad de VUCE
    usando la base de datos oficial NCM
    
    Args:
        ncm_code: Código NCM a buscar
        product_description: Descripción del producto para refinamiento automático
    """
    integration = get_ncm_integration()
    return await integration.get_ncm_info(ncm_code, product_description)

if __name__ == "__main__":
    # Test básico
    import asyncio
    
    async def test_integration():
        integration = NCMOfficialIntegration()
        
        # Test con código de ejemplo
        test_codes = ["8528.72.00", "84", "8528"]
        
        for code in test_codes:
            print(f"\n🔍 Probando código: {code}")
            result = await integration.get_ncm_info(code)
            
            if result.get('success'):
                print(f"✅ Encontrado: {result['posicion_encontrada']['descripcion'][:100]}...")
                print(f"   Match exacto: {result.get('match_exacto', 'N/A')}")
                if result.get('match_info'):
                    print(f"   Score: {result['match_info']['score']:.2f}")
            else:
                print(f"❌ Error: {result.get('error', 'Desconocido')}")
    
    asyncio.run(test_integration()) 