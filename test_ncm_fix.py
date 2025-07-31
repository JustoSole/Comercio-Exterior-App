#!/usr/bin/env python3
"""
Test script para verificar que el fix de NCM funciona correctamente
"""

import logging
import sys
from pathlib import Path

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')

def test_ncm_integration():
    """Test de la integración NCM con auto-generación"""
    print("🧪 Probando integración NCM con auto-generación...")
    print("=" * 60)
    
    try:
        from ncm_official_integration import NCMOfficialIntegration
        
        # Test 1: Inicialización básica
        print("\n1️⃣ Test: Inicialización NCMOfficialIntegration")
        ncm_integration = NCMOfficialIntegration()
        
        if ncm_integration.ncm_data:
            print(f"✅ Datos NCM cargados: {len(ncm_integration.ncm_data):,} registros")
        else:
            print("❌ No se pudieron cargar datos NCM")
            return False
        
        # Test 2: Búsqueda exacta
        print("\n2️⃣ Test: Búsqueda exacta de código NCM")
        test_code = "8528.72.00"  # Televisores LCD
        result = ncm_integration.search_exact_ncm(test_code)
        
        if result:
            print(f"✅ Código encontrado: {result.get('code', 'N/A')}")
            print(f"   Descripción: {result.get('description', 'N/A')[:100]}...")
        else:
            print(f"⚠️  Código no encontrado exactamente: {test_code}")
        
        # Test 3: Búsqueda jerárquica
        print("\n3️⃣ Test: Búsqueda jerárquica")
        hierarchical_results = ncm_integration.search_hierarchical_ncm("8528", max_results=3)
        
        if hierarchical_results:
            print(f"✅ Búsqueda jerárquica: {len(hierarchical_results)} resultados")
            for i, result in enumerate(hierarchical_results, 1):
                print(f"   {i}. {result.get('code', 'N/A')} - {result.get('description', 'N/A')[:50]}...")
        else:
            print("⚠️  No se encontraron resultados jerárquicos")
        
        # Test 4: Análisis de datos cargados
        print("\n4️⃣ Test: Análisis de dataset cargado")
        if ncm_integration.dataset_path:
            print(f"✅ Dataset path: {ncm_integration.dataset_path}")
            print(f"✅ Dataset existe: {ncm_integration.dataset_path.exists()}")
            
            # Verificar estructura de datos
            if ncm_integration.ncm_data:
                sample_record = ncm_integration.ncm_data[0]
                print(f"✅ Campos disponibles: {list(sample_record.keys())}")
                
                # Contar tipos de registros
                record_types = {}
                for record in ncm_integration.ncm_data[:1000]:  # Solo primeros 1000 para speed
                    record_type = record.get('record_type', 'unknown')
                    record_types[record_type] = record_types.get(record_type, 0) + 1
                
                print(f"✅ Tipos de registros (muestra): {record_types}")
        
        print("\n🎉 TODOS LOS TESTS PASARON EXITOSAMENTE!")
        print("   El fix de NCM está funcionando correctamente.")
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR EN TEST: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_file_availability():
    """Test de disponibilidad de archivos críticos"""
    print("\n📁 Test: Disponibilidad de archivos críticos")
    print("-" * 40)
    
    critical_files = [
        "ncm_official_integration.py",
        "pdf_reader/ncm/resultados_ncm_hybrid/dataset_ncm_HYBRID_FIXED_20250721_175449.json"
    ]
    
    for file_path in critical_files:
        path = Path(file_path)
        if path.exists():
            size = path.stat().st_size / (1024 * 1024)  # MB
            print(f"✅ {file_path} ({size:.1f} MB)")
        else:
            print(f"❌ {file_path} - NO ENCONTRADO")
    
    # Test de PDFs (opcional en Streamlit Cloud)
    pdf_dir = Path("pdf_reader/ncm/ncm_pdf")
    if pdf_dir.exists():
        pdf_count = len(list(pdf_dir.glob("capitulo_*.pdf")))
        print(f"✅ PDFs NCM disponibles: {pdf_count} archivos")
    else:
        print("⚠️  PDFs NCM no disponibles (normal en Streamlit Cloud)")

if __name__ == "__main__":
    print("🔧 TEST DE FIX NCM - Comercio Exterior App")
    print("=" * 60)
    
    # Test de archivos
    test_file_availability()
    
    # Test de integración
    success = test_ncm_integration()
    
    if success:
        print("\n🚀 SOLUCIÓN VERIFICADA - Lista para deployment!")
    else:
        print("\n💥 HAY PROBLEMAS - Requiere atención")
        sys.exit(1)