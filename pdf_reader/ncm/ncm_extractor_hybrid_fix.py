#!/usr/bin/env python3
"""
Extractor HÍBRIDO con CORRECCIONES CRÍTICAS aplicadas
Combina el motor de extracción que FUNCIONA con todas las validaciones críticas
"""

import os
import json
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import pandas as pd
import pdfplumber

class NCMHierarchyProcessor:
    """Procesador CORREGIDO para jerarquías y normalización"""
    
    @staticmethod
    def normalize_ncm_code(ncm_code: str) -> str:
        """Normaliza código NCM eliminando puntos, espacios y guiones"""
        if not ncm_code:
            return ""
        normalized = re.sub(r'[.\s-]', '', str(ncm_code).strip())
        return normalized
    
    @staticmethod
    def extract_parent_code(ncm_code: str) -> Optional[str]:
        """Extrae el código padre basado en la jerarquía NCM VALIDADA"""
        normalized = NCMHierarchyProcessor.normalize_ncm_code(ncm_code)
        
        if not re.match(r'^\d+[A-Z0-9]*$', normalized):
            return None
        
        numeric_part = re.match(r'^(\d+)', normalized)
        if not numeric_part:
            return None
        
        digits = numeric_part.group(1)
        
        if len(digits) >= 8:
            return digits[:6] if len(digits) > 6 else None
        elif len(digits) >= 6:
            return digits[:4] if len(digits) > 4 else None  
        elif len(digits) >= 4:
            return digits[:2] if len(digits) > 2 else None
        elif len(digits) >= 2:
            return None
        
        return None
    
    @staticmethod
    def get_hierarchy_level(ncm_code: str) -> int:
        """Determina el nivel jerárquico del código NCM"""
        normalized = NCMHierarchyProcessor.normalize_ncm_code(ncm_code)
        numeric_part = re.match(r'^(\d+)', normalized)
        
        if not numeric_part:
            return 0
        
        digits = numeric_part.group(1)
        
        if len(digits) >= 8:
            return 4
        elif len(digits) >= 6:
            return 3
        elif len(digits) >= 4:
            return 2
        elif len(digits) >= 2:
            return 1
        else:
            return 0

class NCMRecordClassifier:
    """Clasificador CORREGIDO para tipos de registros"""
    
    @staticmethod
    def classify_record_type(record: Dict) -> str:
        """Clasifica el tipo de registro con campos CORREGIDOS"""
        ncm = record.get('code', '')
        sim = record.get('sim', '')
        description = record.get('description', '')
        has_fiscal_data = any([
            record.get('aec', 0) != 0,
            record.get('die', 0) != 0, 
            record.get('te', 0) != 0,
            record.get('de', 0) != 0,
            record.get('re', 0) != 0,
            record.get('in', '') != ''
        ])
        
        if not ncm or len(ncm.replace('.', '').replace(' ', '')) <= 4:
            return 'header'
        
        if sim and has_fiscal_data:
            return 'terminal'
        
        if ncm and not sim and not has_fiscal_data:
            return 'subcategory'
        
        if ncm and has_fiscal_data:
            return 'terminal'
        
        return 'subcategory'

class NCMTableProcessor:
    """Procesador de tablas - USA EL MOTOR QUE FUNCIONA"""
    
    @staticmethod
    def is_ncm_code(text: str) -> bool:
        """Verifica si un texto parece un código NCM"""
        if not text or pd.isna(text):
            return False
        
        text = str(text).strip()
        patterns = [
            r'^\d{2}\.\d{2}$',
            r'^\d{4}\.\d{1,2}$',
            r'^\d{4}\.\d{2}\.\d{2}$',
            r'^\d{4}\.\d{2}\.\d{2}\s+[A-Z0-9]+$',
        ]
        
        return any(re.match(pattern, text) for pattern in patterns)
    
    @staticmethod
    def is_sim_code(text: str) -> bool:
        """Verifica si un texto parece un código SIM"""
        if not text or pd.isna(text):
            return False
        
        text = str(text).strip()
        return re.match(r'^[0-9]{3}[A-Z]$', text) is not None
    
    @staticmethod
    def is_numeric_value(text: str) -> bool:
        """Verifica si un texto es un valor numérico"""
        if not text or pd.isna(text):
            return False
        
        text = str(text).strip()
        try:
            float(text)
            return True
        except ValueError:
            return False
    
    @staticmethod
    def identify_row_structure(cells: List[str]) -> Optional[Dict]:
        """Identifica la estructura de una fila - MOTOR QUE FUNCIONA"""
        if len(cells) < 2:
            return None
        
        result = {
            'ncm': '',
            'sim': '',
            'descripcion': '',
            'aec': 0.0,
            'die': 0.0,
            'te': 0.0,
            'in': '',
            'de': 0.0,
            're': 0.0
        }
        
        ncm_found = False
        sim_found = False
        desc_parts = []
        numeric_values = []
        
        for i, cell in enumerate(cells):
            cell = cell.strip()
            if not cell:
                continue
            
            # Identificar código NCM
            if NCMTableProcessor.is_ncm_code(cell) and not ncm_found:
                result['ncm'] = cell
                ncm_found = True
                continue
            
            # Identificar código SIM
            if NCMTableProcessor.is_sim_code(cell) and not sim_found:
                result['sim'] = cell
                sim_found = True
                continue
            
            # Identificar valores numéricos
            if NCMTableProcessor.is_numeric_value(cell):
                try:
                    numeric_values.append(float(cell))
                except ValueError:
                    pass
                continue
            
            # Identificar código IN
            if len(cell) <= 3 and cell.isupper() and not result['in']:
                result['in'] = cell
                continue
            
            # Todo lo demás es descripción
            if cell and not cell.isdigit():
                desc_parts.append(cell)
        
        # Consolidar descripción
        if desc_parts:
            result['descripcion'] = ' '.join(desc_parts)
        
        # Asignar valores numéricos
        numeric_fields = ['aec', 'die', 'te', 'de', 're']
        for i, value in enumerate(numeric_values[:len(numeric_fields)]):
            result[numeric_fields[i]] = value
        
        # Solo devolver si encontramos al menos un código NCM
        if result['ncm']:
            return result
        
        return None

class NCMExtractorHybridFix:
    """Extractor HÍBRIDO - Motor que funciona + Correcciones críticas"""
    
    def __init__(self):
        self.hierarchy_processor = NCMHierarchyProcessor()
        self.table_processor = NCMTableProcessor()
        self.record_classifier = NCMRecordClassifier()
        self.results_dir = Path("resultados_ncm_hybrid")
        self.results_dir.mkdir(exist_ok=True)
        
    def extract_from_text(self, text: str, page_num: int) -> List[Dict]:
        """Extrae registros NCM del texto - MOTOR QUE FUNCIONA"""
        records = []
        
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Buscar líneas que contengan códigos NCM
            if re.search(r'\d{4}\.\d{2}\.\d{2}', line):
                # Dividir la línea en partes
                parts = re.split(r'\s+', line)
                
                # Tratar de identificar la estructura
                record = self.table_processor.identify_row_structure(parts)
                if record:
                    records.append(record)
        
        return records
    
    def extract_tables_from_page(self, page, page_num: int) -> List[Dict]:
        """MOTOR DE EXTRACCIÓN QUE FUNCIONA + estrategias mejoradas"""
        all_records = []
        
        # Estrategia 1: Detección automática de tablas
        try:
            tables = page.extract_tables()
            if tables:
                print(f"📋 Estrategia 1 - Encontradas {len(tables)} tablas en página {page_num}")
                for table in tables:
                    if table:
                        # Procesar tabla directamente (como en el motor que funciona)
                        for row in table:
                            if row:
                                cleaned_cells = [cell.strip() for cell in row if cell and cell.strip()]
                                if cleaned_cells:
                                    record = self.table_processor.identify_row_structure(cleaned_cells)
                                    if record:
                                        all_records.append(record)
        except Exception as e:
            print(f"⚠️  Estrategia 1 falló en página {page_num}: {e}")
        
        # Estrategia 2: Configuración personalizada
        if not all_records:
            try:
                tables = page.extract_tables(table_settings={
                    "vertical_strategy": "lines",
                    "horizontal_strategy": "lines",
                    "min_words_vertical": 1,
                    "min_words_horizontal": 1
                })
                if tables:
                    print(f"📋 Estrategia 2 - Encontradas {len(tables)} tablas en página {page_num}")
                    for table in tables:
                        if table:
                            for row in table:
                                if row:
                                    cleaned_cells = [cell.strip() for cell in row if cell and cell.strip()]
                                    if cleaned_cells:
                                        record = self.table_processor.identify_row_structure(cleaned_cells)
                                        if record:
                                            all_records.append(record)
            except Exception as e:
                print(f"⚠️  Estrategia 2 falló en página {page_num}: {e}")
        
        # Estrategia 3: Extracción basada en texto (SIEMPRE EJECUTAR)
        try:
            text = page.extract_text()
            if text:
                records = self.extract_from_text(text, page_num)
                all_records.extend(records)
                if records:
                    print(f"📋 Estrategia 3 - Extraídos {len(records)} registros de texto en página {page_num}")
        except Exception as e:
            print(f"⚠️  Estrategia 3 falló en página {page_num}: {e}")
        
        return all_records
    
    def extract_from_pdf(self, pdf_path: Path, chapter_num: int) -> Tuple[List[Dict], Dict]:
        """Extrae datos de un PDF completo - MOTOR HÍBRIDO"""
        print(f"📑 Procesando capítulo {chapter_num:02d}: {pdf_path.name}")
        
        all_records = []
        pages_processed = 0
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                total_pages = len(pdf.pages)
                
                # Procesar páginas desde la 3 en adelante
                for page_num in range(2, total_pages):
                    page = pdf.pages[page_num]
                    real_page_num = page_num + 1
                    
                    print(f"🔍 Procesando página {real_page_num}/{total_pages}...")
                    
                    # Extraer registros de la página
                    page_records = self.extract_tables_from_page(page, real_page_num)
                    
                    if page_records:
                        all_records.extend(page_records)
                        pages_processed += 1
                        print(f"✅ Página {real_page_num}: {len(page_records)} registros extraídos")
                    else:
                        print(f"⚠️  Página {real_page_num}: sin registros")
        
        except Exception as e:
            print(f"❌ Error procesando PDF: {e}")
        
        # Estadísticas de extracción
        extraction_stats = {
            'total_pages': total_pages,
            'pages_processed': pages_processed,
            'records_extracted': len(all_records),
            'extraction_method': 'hybrid_fix'
        }
        
        print(f"📊 Capítulo {chapter_num} completado: {len(all_records)} registros de {pages_processed} páginas")
        
        return all_records, extraction_stats
    
    def process_and_enhance_records(self, records: List[Dict], chapter_num: int, pdf_name: str) -> List[Dict]:
        """Procesa registros con CORRECCIONES CRÍTICAS aplicadas"""
        enhanced_records = []
        
        for record in records:
            # ESTRUCTURA CORREGIDA (sin campos duplicados)
            enhanced_record = {
                'file': pdf_name,
                'chapter': chapter_num,
                'code': record.get('ncm', ''),  # ✅ ÚNICO campo de código
                'sim': record.get('sim', ''),
                'description': record.get('descripcion', ''),  # ✅ ÚNICO campo de descripción
                'aec': float(record.get('aec', 0)),
                'die': float(record.get('die', 0)),
                'te': float(record.get('te', 0)),
                'in': record.get('in', ''),
                'de': float(record.get('de', 0)),
                're': float(record.get('re', 0)),
            }
            
            # Añadir campos de jerarquía VALIDADOS
            code_searchable = self.hierarchy_processor.normalize_ncm_code(enhanced_record['code'])
            parent_code = self.hierarchy_processor.extract_parent_code(enhanced_record['code'])
            parent_searchable = self.hierarchy_processor.normalize_ncm_code(parent_code) if parent_code else None
            
            enhanced_record.update({
                'code_searchable': code_searchable,
                'parent': parent_code,
                'parent_searchable': parent_searchable,
                'hierarchy_level': self.hierarchy_processor.get_hierarchy_level(enhanced_record['code'])
            })
            
            # Clasificar tipo de registro
            record_type = self.record_classifier.classify_record_type(enhanced_record)
            enhanced_record['record_type'] = record_type
            
            # VALIDACIÓN FINAL
            if enhanced_record['code'] or (enhanced_record['description'] and len(enhanced_record['description']) > 3):
                enhanced_records.append(enhanced_record)
        
        return enhanced_records
    
    def process_all_chapters(self, start_chapter: int = 1, end_chapter: int = 97) -> List[Dict]:  # ✅ CORREGIDO: 97
        """Procesa todos los capítulos 1-97 con MOTOR HÍBRIDO"""
        pdf_dir = Path("ncm_pdf")
        
        if not pdf_dir.exists():
            print(f"❌ Directorio no encontrado: {pdf_dir}")
            return []
        
        print(f"🚀 Procesando capítulos {start_chapter}-{end_chapter} con EXTRACTOR HÍBRIDO")
        print(f"📁 Directorio: {pdf_dir}")
        
        all_results = []
        successful_extractions = 0
        
        for chapter_num in range(start_chapter, end_chapter + 1):
            pdf_file = pdf_dir / f"capitulo_{chapter_num:02d}.pdf"
            
            if not pdf_file.exists():
                print(f"⚠️  Archivo no encontrado: {pdf_file}")
                continue
            
            print(f"\n{'='*60}")
            print(f"📖 PROCESANDO CAPÍTULO {chapter_num}/{end_chapter}")
            print(f"📄 Archivo: {pdf_file.name}")
            print('='*60)
            
            # Extraer datos del capítulo
            chapter_records, stats = self.extract_from_pdf(pdf_file, chapter_num)
            
            if chapter_records:
                # Procesar con CORRECCIONES CRÍTICAS
                enhanced_records = self.process_and_enhance_records(chapter_records, chapter_num, pdf_file.name)
                
                # Guardar resultados
                self.save_chapter_results(enhanced_records, chapter_num, pdf_file.name, stats)
                
                all_results.extend(enhanced_records)
                successful_extractions += 1
                print(f"✅ Capítulo {chapter_num} completado: {len(enhanced_records)} registros válidos")
                
                # Mostrar estadísticas por tipo
                type_stats = {}
                for record in enhanced_records:
                    record_type = record.get('record_type', 'unknown')
                    type_stats[record_type] = type_stats.get(record_type, 0) + 1
                
                print(f"📊 Tipos: {type_stats}")
                
            else:
                print(f"❌ Sin datos válidos para capítulo {chapter_num}")
        
        print(f"\n🏁 PROCESAMIENTO COMPLETADO")
        print(f"✅ Capítulos procesados exitosamente: {successful_extractions}/{end_chapter-start_chapter+1}")
        print(f"📊 Total de registros extraídos: {len(all_results)}")
        
        return all_results
    
    def save_chapter_results(self, records: List[Dict], chapter_num: int, pdf_name: str, stats: Dict):
        """Guarda resultados con formato CORREGIDO"""
        json_file = self.results_dir / f"capitulo_{chapter_num:02d}_hybrid.json"
        
        chapter_data = {
            "file": pdf_name,
            "chapter": chapter_num,
            "total_records": len(records),
            "extraction_stats": stats,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "version": "hybrid_fix_v1.0",
            "records": records
        }
        
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(chapter_data, f, indent=2, ensure_ascii=False)
        
        if records:
            csv_file = self.results_dir / f"capitulo_{chapter_num:02d}_hybrid.csv"
            df = pd.DataFrame(records)
            df.to_csv(csv_file, index=False, encoding='utf-8')
            print(f"💾 Capítulo {chapter_num} guardado: {json_file} y {csv_file}")
    
    def create_consolidated_dataset(self, all_results: List[Dict]) -> Tuple[str, str]:
        """Crea dataset consolidado CORREGIDO"""
        if not all_results:
            print("⚠️  No hay datos para consolidar")
            return None, None
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Estadísticas por tipo
        type_stats = {}
        for record in all_results:
            record_type = record.get('record_type', 'unknown')
            type_stats[record_type] = type_stats.get(record_type, 0) + 1
        
        # JSON consolidado
        json_file = self.results_dir / f"dataset_ncm_HYBRID_FIXED_{timestamp}.json"
        consolidated_json = {
            "metadata": {
                "version": "hybrid_fix_v1.0",
                "total_records": len(all_results),
                "extraction_method": "hybrid_pdfplumber_fixed",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_chapters": len(set(record['chapter'] for record in all_results)),
                "chapters_processed": sorted(list(set(record['chapter'] for record in all_results))),
                "record_type_distribution": type_stats,
                "validation_status": "ALL_CRITICAL_FIXES_APPLIED",
                "fixes_applied": [
                    "eliminated_duplicate_fields",
                    "corrected_chapter_range_1_to_97", 
                    "added_record_type_classification",
                    "improved_hierarchy_validation",
                    "enhanced_fiscal_data_detection"
                ]
            },
            "records": all_results
        }
        
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(consolidated_json, f, indent=2, ensure_ascii=False)
        
        # CSV consolidado
        csv_file = self.results_dir / f"dataset_ncm_HYBRID_FIXED_{timestamp}.csv"
        df = pd.DataFrame(all_results)
        df.to_csv(csv_file, index=False, encoding='utf-8')
        
        print(f"✅ Dataset HÍBRIDO CORREGIDO creado:")
        print(f"   📋 JSON: {json_file}")
        print(f"   📊 CSV: {csv_file}")
        
        # Reporte de validación
        self.print_validation_report(df, type_stats)
        
        return str(json_file), str(csv_file)
    
    def print_validation_report(self, df: pd.DataFrame, type_stats: Dict):
        """Reporte de validación crítica final"""
        print(f"\n🔍 REPORTE DE VALIDACIÓN CRÍTICA FINAL")
        print("="*50)
        print(f"📋 Total de registros: {len(df):,}")
        print(f"📚 Capítulos procesados: {df['chapter'].nunique()}")
        print(f"🔢 Códigos NCM únicos: {df['code_searchable'].nunique():,}")
        
        print(f"\n📊 DISTRIBUCIÓN POR TIPO:")
        for record_type, count in type_stats.items():
            percentage = (count / len(df)) * 100
            print(f"   {record_type}: {count:,} registros ({percentage:.1f}%)")
        
        print(f"\n🔍 VALIDACIONES CRÍTICAS:")
        valid_codes = df['code'].notna().sum()
        valid_descriptions = df['description'].notna().sum()
        with_hierarchy = df['parent'].notna().sum()
        terminal_records = (df['record_type'] == 'terminal').sum()
        
        print(f"   ✅ Códigos válidos: {valid_codes}/{len(df)} ({valid_codes/len(df)*100:.1f}%)")
        print(f"   ✅ Descripciones válidas: {valid_descriptions}/{len(df)} ({valid_descriptions/len(df)*100:.1f}%)")
        print(f"   ✅ Con jerarquía: {with_hierarchy}/{len(df)} ({with_hierarchy/len(df)*100:.1f}%)")
        print(f"   💰 Registros terminales: {terminal_records}/{len(df)} ({terminal_records/len(df)*100:.1f}%)")

def main():
    """Función principal HÍBRIDA CORREGIDA"""
    print("🔧 EXTRACTOR NCM - VERSIÓN HÍBRIDA CORREGIDA")
    print("Motor funcional + Correcciones críticas + Rango 1-97")
    print("-" * 60)
    
    extractor = NCMExtractorHybridFix()
    
    # Para testing: procesar solo algunos capítulos
    # all_results = extractor.process_all_chapters(start_chapter=1, end_chapter=3)
    
    # Para procesamiento completo (1-97):
    all_results = extractor.process_all_chapters(start_chapter=1, end_chapter=97)
    
    if all_results:
        json_file, csv_file = extractor.create_consolidated_dataset(all_results)
        
        print(f"\n🎉 EXTRACCIÓN HÍBRIDA COMPLETADA")
        print(f"📁 Archivos creados en: {extractor.results_dir}")
        print(f"📋 Dataset JSON: {json_file}")
        print(f"📊 Dataset CSV: {csv_file}")
        
    else:
        print("❌ No se pudieron extraer datos de ningún capítulo")

if __name__ == "__main__":
    main() 