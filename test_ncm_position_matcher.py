#!/usr/bin/env python3
"""
🧪 Test Suite para NCM Position Matcher
=======================================

Suite de tests exhaustivos para validar todas las funcionalidades
del clasificador NCM incluyendo casos reales del dataset.

Casos de test:
- Búsqueda exacta (múltiples formatos)
- Búsqueda aproximada (jerárquica y semántica)
- Selección por IA
- Casos edge y errores
- Integración con datos reales
- Performance y stress tests
"""

import os
import sys
import json
import asyncio
import pytest
import tempfile
from pathlib import Path
from typing import Dict, List, Any
import pandas as pd
from unittest.mock import Mock, patch

# Añadir directorio actual al path para imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ncm_position_matcher import (
    NCMPositionMatcher,
    NCMDataLoader,
    NCMSearchEngine,
    AISelector,
    NCMPosition,
    match_single_ncm,
    validate_ncm_code
)

class TestNCMDataLoader:
    """Tests para el cargador de datos"""
    
    def setup_method(self):
        """Setup para cada test"""
        # Crear archivo de datos de prueba
        self.test_data = [
            {
                'file': 'test.pdf',
                'chapter': 85,
                'code': '8528.72.00',
                'sim': '',
                'description': 'Televisores LCD',
                'aec': 20.0,
                'die': 0.0,
                'te': 3.0,
                'in': '',
                'de': 0.0,
                're': 0.0,
                'code_searchable': '85287200',
                'parent': '852872',
                'parent_searchable': '852872',
                'hierarchy_level': 4,
                'record_type': 'subcategory'
            },
            {
                'file': 'test.pdf',
                'chapter': 85,
                'code': '8528.72.00',
                'sim': '100W',
                'description': 'Televisores LCD hasta 32 pulgadas',
                'aec': 20.0,
                'die': 0.0,
                'te': 3.0,
                'in': 'LA',
                'de': 15.0,
                're': 1.0,
                'code_searchable': '85287200',
                'parent': '852872',
                'parent_searchable': '852872',
                'hierarchy_level': 4,
                'record_type': 'terminal'
            },
            {
                'file': 'test.pdf',
                'chapter': 1,
                'code': '0101.21.00',
                'sim': '100W',
                'description': 'Sangre pura de carrera',
                'aec': 0.0,
                'die': 0.0,
                'te': 0.0,
                'in': 'LA',
                'de': 9.0,
                're': 0.5,
                'code_searchable': '01012100',
                'parent': '010121',
                'parent_searchable': '010121',
                'hierarchy_level': 4,
                'record_type': 'terminal'
            }
        ]
        
        # Crear archivo temporal
        self.temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        df = pd.DataFrame(self.test_data)
        df.to_csv(self.temp_file.name, index=False)
        self.temp_file.close()
    
    def teardown_method(self):
        """Cleanup después de cada test"""
        if os.path.exists(self.temp_file.name):
            os.unlink(self.temp_file.name)
    
    def test_data_loading_success(self):
        """Test carga exitosa de datos"""
        loader = NCMDataLoader(self.temp_file.name)
        
        assert loader.data is not None
        assert len(loader.data) == len(self.test_data)
        assert len(loader.positions) > 0
        
        # Verificar indexación
        assert '85287200' in loader.positions
        assert '01012100' in loader.positions
    
    def test_data_loading_file_not_found(self):
        """Test error cuando archivo no existe"""
        with pytest.raises(FileNotFoundError):
            NCMDataLoader("archivo_inexistente.csv")
    
    def test_code_normalization(self):
        """Test normalización de códigos"""
        loader = NCMDataLoader(self.temp_file.name)
        
        assert loader._normalize_code("8528.72.00") == "85287200"
        assert loader._normalize_code("85 28.72-00") == "85287200"
        assert loader._normalize_code("") == ""
        assert loader._normalize_code(None) == ""

class TestNCMSearchEngine:
    """Tests para el motor de búsqueda"""
    
    def setup_method(self):
        """Setup para cada test"""
        # Usar datos de test del loader
        self.test_data = [
            {
                'file': 'test.pdf', 'chapter': 85, 'code': '8528.72.00', 'sim': '',
                'description': 'Televisores LCD', 'aec': 20.0, 'die': 0.0, 'te': 3.0,
                'in': '', 'de': 0.0, 're': 0.0, 'code_searchable': '85287200',
                'parent': '852872', 'parent_searchable': '852872',
                'hierarchy_level': 4, 'record_type': 'subcategory'
            },
            {
                'file': 'test.pdf', 'chapter': 85, 'code': '8528.72.00', 'sim': '100W',
                'description': 'Televisores LCD hasta 32 pulgadas', 'aec': 20.0, 'die': 0.0, 'te': 3.0,
                'in': 'LA', 'de': 15.0, 're': 1.0, 'code_searchable': '85287200',
                'parent': '852872', 'parent_searchable': '852872',
                'hierarchy_level': 4, 'record_type': 'terminal'
            },
            {
                'file': 'test.pdf', 'chapter': 85, 'code': '8528.73.00', 'sim': '200B',
                'description': 'Televisores LCD de 42 a 50 pulgadas', 'aec': 20.0, 'die': 0.0, 'te': 3.0,
                'in': 'LA', 'de': 15.0, 're': 1.0, 'code_searchable': '85287300',
                'parent': '852873', 'parent_searchable': '852873',
                'hierarchy_level': 4, 'record_type': 'terminal'
            }
        ]
        
        self.temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        df = pd.DataFrame(self.test_data)
        df.to_csv(self.temp_file.name, index=False)
        self.temp_file.close()
        
        self.loader = NCMDataLoader(self.temp_file.name)
        self.search_engine = NCMSearchEngine(self.loader)
    
    def teardown_method(self):
        """Cleanup"""
        if os.path.exists(self.temp_file.name):
            os.unlink(self.temp_file.name)
    
    def test_exact_search_with_sim(self):
        """Test búsqueda exacta con código SIM"""
        result = self.search_engine.exact_search("8528.72.00 100W")
        
        assert result is not None
        assert result["match_type"] == "exacto"
        assert result["position"]["code"] == "8528.72.00"
        assert result["position"]["sim"] == "100W"
    
    def test_exact_search_base_code(self):
        """Test búsqueda exacta por código base"""
        result = self.search_engine.exact_search("8528.72.00")
        
        assert result is not None
        assert result["match_type"] == "exacto"
        assert result["position"]["code"] == "8528.72.00"
    
    def test_exact_search_not_found(self):
        """Test búsqueda exacta sin resultados"""
        result = self.search_engine.exact_search("9999.99.99")
        
        assert result is None
    
    def test_approximate_search_by_description(self):
        """Test búsqueda aproximada por descripción"""
        candidates = self.search_engine.approximate_search("televisor")
        
        assert len(candidates) > 0
        assert any("televisor" in c['candidate_info']['description'].lower() for c in candidates)
    
    def test_approximate_search_hierarchical(self):
        """Test búsqueda aproximada jerárquica"""
        candidates = self.search_engine.approximate_search("8528")
        
        assert len(candidates) > 0
        # Todos los candidatos deben empezar con 8528
        for candidate in candidates:
            assert candidate['position'].code.startswith('8528')
    
    def test_code_validation(self):
        """Test validación de códigos NCM"""
        valid_codes = [
            "8528.72.00",
            "8528.72.00 100W",
            "85287200",
            "85.28.72.00"
        ]
        
        for code in valid_codes:
            assert validate_ncm_code(code), f"Código {code} debería ser válido"
        
        invalid_codes = [
            "invalid",
            "12345",
            "85.28",
            ""
        ]
        
        for code in invalid_codes:
            assert not validate_ncm_code(code), f"Código {code} debería ser inválido"

class TestAISelector:
    """Tests para el selector de IA"""
    
    def test_ai_selector_without_openai(self):
        """Test selector sin OpenAI disponible"""
        selector = AISelector(api_key=None)
        assert selector.client is None
    
    @patch('ncm_position_matcher.OPENAI_AVAILABLE', True)
    def test_ai_selector_with_mock_api(self):
        """Test selector con API mockeada"""
        with patch('ncm_position_matcher.OpenAI') as mock_openai:
            selector = AISelector(api_key="test_key")
            assert selector.client is not None
    
    @pytest.mark.asyncio
    async def test_fallback_selection(self):
        """Test selección de fallback"""
        selector = AISelector(api_key=None)  # Sin IA
        
        # Crear candidatos de prueba
        mock_position = Mock()
        mock_position.to_dict.return_value = {
            'code': '8528.72.00',
            'description': 'Test TV'
        }
        
        candidates = [
            {
                'position': mock_position,
                'score': 0.8,
                'candidate_info': {'score': 0.8}
            }
        ]
        
        result = await selector.select_best_candidate(candidates, "test query")
        
        assert result['match_type'] == 'aproximado'
        assert 'fallback_selection' in result

class TestNCMPositionMatcher:
    """Tests para el matcher principal"""
    
    def setup_method(self):
        """Setup para tests del matcher"""
        # Crear dataset de prueba más completo
        self.test_data = [
            # Televisores
            {
                'file': 'cap85.pdf', 'chapter': 85, 'code': '8528.72.00', 'sim': '',
                'description': 'Televisores en colores', 'aec': 20.0, 'die': 0.0, 'te': 3.0,
                'in': '', 'de': 0.0, 're': 0.0, 'code_searchable': '85287200',
                'parent': '852872', 'parent_searchable': '852872',
                'hierarchy_level': 4, 'record_type': 'subcategory'
            },
            {
                'file': 'cap85.pdf', 'chapter': 85, 'code': '8528.72.00', 'sim': '100W',
                'description': 'Televisores LCD hasta 32 pulgadas', 'aec': 20.0, 'die': 0.0, 'te': 3.0,
                'in': 'LA', 'de': 15.0, 're': 1.0, 'code_searchable': '85287200',
                'parent': '852872', 'parent_searchable': '852872',
                'hierarchy_level': 4, 'record_type': 'terminal'
            },
            {
                'file': 'cap85.pdf', 'chapter': 85, 'code': '8528.72.00', 'sim': '200B',
                'description': 'Televisores LCD de 42 a 50 pulgadas', 'aec': 20.0, 'die': 0.0, 'te': 3.0,
                'in': 'LA', 'de': 15.0, 're': 1.0, 'code_searchable': '85287200',
                'parent': '852872', 'parent_searchable': '852872',
                'hierarchy_level': 4, 'record_type': 'terminal'
            },
            # Smartphones
            {
                'file': 'cap85.pdf', 'chapter': 85, 'code': '8517.12.00', 'sim': '110A',
                'description': 'Teléfonos inteligentes', 'aec': 16.0, 'die': 0.0, 'te': 3.0,
                'in': 'LA', 'de': 12.0, 're': 1.0, 'code_searchable': '85171200',
                'parent': '851712', 'parent_searchable': '851712',
                'hierarchy_level': 4, 'record_type': 'terminal'
            },
            # Caballos
            {
                'file': 'cap01.pdf', 'chapter': 1, 'code': '0101.21.00', 'sim': '100W',
                'description': 'Sangre pura de carrera', 'aec': 0.0, 'die': 0.0, 'te': 0.0,
                'in': 'LA', 'de': 9.0, 're': 0.5, 'code_searchable': '01012100',
                'parent': '010121', 'parent_searchable': '010121',
                'hierarchy_level': 4, 'record_type': 'terminal'
            }
        ]
        
        self.temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        df = pd.DataFrame(self.test_data)
        df.to_csv(self.temp_file.name, index=False)
        self.temp_file.close()
        
        self.matcher = NCMPositionMatcher(self.temp_file.name)
    
    def teardown_method(self):
        """Cleanup"""
        if os.path.exists(self.temp_file.name):
            os.unlink(self.temp_file.name)
    
    @pytest.mark.asyncio
    async def test_exact_match_success(self):
        """Test match exacto exitoso"""
        result = await self.matcher.match_position("8528.72.00 100W")
        
        assert result['match_type'] == 'exacto'
        assert result['position']['code'] == '8528.72.00'
        assert result['position']['sim'] == '100W'
        assert 'processing_time_ms' in result
    
    @pytest.mark.asyncio
    async def test_approximate_match_success(self):
        """Test match aproximado exitoso"""
        result = await self.matcher.match_position("televisor LCD")
        
        assert result['match_type'] in ['aproximado', 'sin_resultados']
        assert 'processing_time_ms' in result
        
        if result['match_type'] == 'aproximado':
            assert 'position' in result
            assert 'candidates_analyzed' in result
    
    @pytest.mark.asyncio
    async def test_empty_query_error(self):
        """Test error con consulta vacía"""
        result = await self.matcher.match_position("")
        
        assert result['match_type'] == 'error'
        assert 'error' in result
    
    @pytest.mark.asyncio
    async def test_no_results_case(self):
        """Test caso sin resultados"""
        result = await self.matcher.match_position("producto inexistente xyz123")
        
        assert result['match_type'] in ['sin_resultados', 'aproximado']
    
    def test_get_statistics(self):
        """Test obtención de estadísticas"""
        stats = self.matcher.get_statistics()
        
        assert 'total_records' in stats
        assert 'unique_codes' in stats
        assert 'chapters' in stats
        assert 'record_types' in stats
        assert stats['total_records'] == len(self.test_data)

class TestRealDataIntegration:
    """Tests de integración con datos reales"""
    
    def setup_method(self):
        """Setup con archivo real si existe"""
        self.real_data_file = "pdf_reader/ncm/resultados_ncm_hybrid/dataset_ncm_HYBRID_FIXED_20250721_175449.csv"
        self.has_real_data = Path(self.real_data_file).exists()
    
    @pytest.mark.skipif(not Path("pdf_reader/ncm/resultados_ncm_hybrid/dataset_ncm_HYBRID_FIXED_20250721_175449.csv").exists(), 
                       reason="Archivo de datos real no encontrado")
    def test_real_data_loading(self):
        """Test carga del archivo real de datos"""
        loader = NCMDataLoader(self.real_data_file)
        
        assert loader.data is not None
        assert len(loader.data) > 40000  # Dataset debe tener ~49k registros
        assert 'code' in loader.data.columns
        assert 'description' in loader.data.columns
    
    @pytest.mark.skipif(not Path("pdf_reader/ncm/resultados_ncm_hybrid/dataset_ncm_HYBRID_FIXED_20250721_175449.csv").exists(), 
                       reason="Archivo de datos real no encontrado")
    @pytest.mark.asyncio
    async def test_real_exact_searches(self):
        """Test búsquedas exactas con datos reales"""
        matcher = NCMPositionMatcher(self.real_data_file)
        
        # Casos de test basados en datos reales vistos
        test_cases = [
            "0101.21.00 100W",  # Sangre pura de carrera
            "0101.21.00",       # Código base
            "8528.72.00"        # Televisores (si existe en el dataset)
        ]
        
        for test_case in test_cases:
            result = await matcher.match_position(test_case)
            assert result['match_type'] in ['exacto', 'aproximado', 'sin_resultados']
            assert 'processing_time_ms' in result
    
    @pytest.mark.skipif(not Path("pdf_reader/ncm/resultados_ncm_hybrid/dataset_ncm_HYBRID_FIXED_20250721_175449.csv").exists(), 
                       reason="Archivo de datos real no encontrado")
    @pytest.mark.asyncio
    async def test_real_approximate_searches(self):
        """Test búsquedas aproximadas con datos reales"""
        matcher = NCMPositionMatcher(self.real_data_file)
        
        test_cases = [
            "caballos de carrera",
            "animales vivos",
            "televisores",
            "teléfonos celulares"
        ]
        
        for test_case in test_cases:
            result = await matcher.match_position(test_case)
            assert result['match_type'] in ['aproximado', 'sin_resultados']
            assert 'processing_time_ms' in result

class TestPerformance:
    """Tests de performance y stress"""
    
    def setup_method(self):
        """Setup para tests de performance"""
        # Crear dataset de prueba mediano
        data = []
        for chapter in range(1, 11):
            for i in range(100):
                data.append({
                    'file': f'cap{chapter:02d}.pdf',
                    'chapter': chapter,
                    'code': f'{chapter:02d}{i:02d}.{i%100:02d}.00',
                    'sim': f'{i:03d}W' if i % 3 == 0 else '',
                    'description': f'Producto {chapter}-{i}',
                    'aec': float(i % 20),
                    'die': 0.0,
                    'te': 3.0,
                    'in': 'LA' if i % 2 == 0 else '',
                    'de': float(i % 15),
                    're': 0.5,
                    'code_searchable': f'{chapter:02d}{i:02d}0000',
                    'parent': f'{chapter:02d}{i:02d}',
                    'parent_searchable': f'{chapter:02d}{i:02d}',
                    'hierarchy_level': 4,
                    'record_type': 'terminal' if i % 3 == 0 else 'subcategory'
                })
        
        self.temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        df = pd.DataFrame(data)
        df.to_csv(self.temp_file.name, index=False)
        self.temp_file.close()
        
        self.matcher = NCMPositionMatcher(self.temp_file.name)
    
    def teardown_method(self):
        """Cleanup"""
        if os.path.exists(self.temp_file.name):
            os.unlink(self.temp_file.name)
    
    @pytest.mark.asyncio
    async def test_performance_exact_searches(self):
        """Test performance de búsquedas exactas"""
        import time
        
        test_queries = [f"01{i:02d}.{i%50:02d}.00" for i in range(20)]
        
        start_time = time.time()
        
        for query in test_queries:
            result = await self.matcher.match_position(query)
            assert 'processing_time_ms' in result
            assert result['processing_time_ms'] < 1000  # Menos de 1 segundo
        
        total_time = time.time() - start_time
        avg_time = total_time / len(test_queries)
        
        assert avg_time < 0.5  # Promedio menos de 500ms por búsqueda
    
    @pytest.mark.asyncio
    async def test_concurrent_searches(self):
        """Test búsquedas concurrentes"""
        queries = [f"Producto {i}" for i in range(5)]
        
        # Ejecutar búsquedas concurrentes
        tasks = [self.matcher.match_position(query) for query in queries]
        results = await asyncio.gather(*tasks)
        
        assert len(results) == len(queries)
        for result in results:
            assert 'match_type' in result
            assert 'processing_time_ms' in result

class TestCLIFunctions:
    """Tests para funciones CLI"""
    
    @pytest.mark.asyncio
    async def test_match_single_ncm_convenience(self):
        """Test función de conveniencia match_single_ncm"""
        # Crear archivo temporal
        test_data = [{
            'file': 'test.pdf', 'chapter': 85, 'code': '8528.72.00', 'sim': '100W',
            'description': 'Test TV', 'aec': 20.0, 'die': 0.0, 'te': 3.0,
            'in': 'LA', 'de': 15.0, 're': 1.0, 'code_searchable': '85287200',
            'parent': '852872', 'parent_searchable': '852872',
            'hierarchy_level': 4, 'record_type': 'terminal'
        }]
        
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        df = pd.DataFrame(test_data)
        df.to_csv(temp_file.name, index=False)
        temp_file.close()
        
        try:
            result = await match_single_ncm("8528.72.00 100W", temp_file.name)
            assert result['match_type'] == 'exacto'
        finally:
            os.unlink(temp_file.name)

def run_comprehensive_tests():
    """Ejecuta todos los tests de forma comprehensiva"""
    import subprocess
    import sys
    
    print("🧪 EJECUTANDO SUITE COMPLETA DE TESTS")
    print("="*50)
    
    # Ejecutar pytest con coverage si está disponible
    try:
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            "test_ncm_position_matcher.py",
            "-v",
            "--tb=short",
            "--durations=10"
        ], capture_output=True, text=True)
        
        print("STDOUT:")
        print(result.stdout)
        
        if result.stderr:
            print("\nSTDERR:")
            print(result.stderr)
        
        return result.returncode == 0
        
    except FileNotFoundError:
        print("⚠️ pytest no disponible, ejecutando tests básicos...")
        return run_basic_tests()

def run_basic_tests():
    """Ejecuta tests básicos sin pytest"""
    print("🔧 Ejecutando tests básicos...")
    
    try:
        # Test básico de importación
        print("✓ Importación de módulos")
        
        # Test básico de validación de códigos
        test_codes = [
            ("8528.72.00", True),
            ("invalid", False),
            ("0101.21.00 100W", True)
        ]
        
        print("✓ Validación de códigos NCM")
        for code, expected in test_codes:
            result = validate_ncm_code(code)
            assert result == expected, f"Error en validación de {code}"
        
        print("✅ Tests básicos completados exitosamente")
        return True
        
    except Exception as e:
        print(f"❌ Error en tests básicos: {e}")
        return False

if __name__ == "__main__":
    """Ejecutar tests directamente"""
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--basic":
        success = run_basic_tests()
    else:
        success = run_comprehensive_tests()
    
    sys.exit(0 if success else 1) 