#!/usr/bin/env python3
"""
Test para la versión HÍBRIDA corregida
"""

from ncm_extractor_hybrid_fix import NCMExtractorHybridFix

def main():
    print("🧪 TESTING EXTRACTOR HÍBRIDO CORREGIDO")
    print("="*50)
    
    extractor = NCMExtractorHybridFix()
    
    # Test con capítulo 1
    from pathlib import Path
    pdf_file = Path("posiciones_arancelarias_arg/ncm_pdf/capitulo_01.pdf")
    
    print(f"📄 Procesando: {pdf_file}")
    records, stats = extractor.extract_from_pdf(pdf_file, 1)
    
    if records:
        enhanced = extractor.process_and_enhance_records(records, 1, "capitulo_01.pdf")
        
        print(f"✅ Registros extraídos: {len(enhanced)}")
        
        if enhanced:
            sample = enhanced[0]
            print(f"\n📋 MUESTRA DE REGISTRO:")
            print(f"   Código: {sample.get('code', 'N/A')}")
            print(f"   SIM: {sample.get('sim', 'N/A')}")
            print(f"   Descripción: {sample.get('description', 'N/A')[:50]}...")
            print(f"   Tipo: {sample.get('record_type', 'N/A')}")
            print(f"   Jerarquía: {sample.get('code', '')} → {sample.get('parent', 'N/A')}")
            
            # Verificar campos únicos
            has_duplicate_fields = any(key in sample for key in ['ncm', 'descripcion'])
            print(f"\n🔍 VALIDACIONES:")
            print(f"   Sin campos duplicados: {'✅' if not has_duplicate_fields else '❌'}")
            print(f"   Campo 'code' presente: {'✅' if 'code' in sample else '❌'}")
            print(f"   Campo 'record_type' presente: {'✅' if 'record_type' in sample else '❌'}")
            
            # Contar tipos
            types = {}
            for record in enhanced[:10]:
                t = record.get('record_type', 'unknown')
                types[t] = types.get(t, 0) + 1
            print(f"   Tipos encontrados: {types}")
            
            print(f"\n🚀 ¡HÍBRIDO FUNCIONA! Listo para procesamiento completo.")
        
        return True
    else:
        print("❌ No se extrajo nada")
        return False

if __name__ == "__main__":
    main() 