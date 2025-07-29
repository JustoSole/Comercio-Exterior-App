#!/usr/bin/env python3
"""
Script de prueba para Google Sheets
Ejecutar después de habilitar las APIs
"""

import sys
import toml
from datetime import datetime

def test_google_sheets():
    """Probar conexión a Google Sheets"""
    try:
        print("🔄 Probando conexión a Google Sheets...")
        
        # Importar módulos
        sys.path.append('.')
        from streamlit_ai_comercio_exterior import get_gspread_client
        
        # Simular secrets de Streamlit
        class MockSecrets:
            def __init__(self, secrets_dict):
                self._secrets = secrets_dict
            def __getitem__(self, key):
                return self._secrets[key]
            def get(self, key, default=None):
                return self._secrets.get(key, default)
        
        import streamlit as st
        secrets = toml.load('.streamlit/secrets.toml')
        st.secrets = MockSecrets(secrets)
        
        # Intentar conectar
        gc = get_gspread_client()
        if not gc:
            print("❌ No se pudo crear el cliente de Google Sheets")
            return False
            
        print("✅ Cliente de Google Sheets creado")
        
        # Intentar abrir la hoja
        hoja_nombre = "Cotizaciones APP IA"
        sh = gc.open(hoja_nombre)
        print(f"✅ Hoja '{hoja_nombre}' encontrada")
        print(f"📋 URL: {sh.url}")
        
        # Verificar worksheets
        worksheets = sh.worksheets()
        print(f"📊 Worksheets disponibles: {[ws.title for ws in worksheets]}")
        
        # Probar escritura
        worksheet = sh.sheet1
        print(f"✅ Acceso a worksheet: {worksheet.title}")
        
        # Agregar una fila de prueba
        datos_prueba = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "PRUEBA - Conexión exitosa",
            "$100.00", 
            "8517.12.00",
            "Test automático - APIs habilitadas"
        ]
        
        worksheet.append_row(datos_prueba)
        print("✅ Datos de prueba escritos exitosamente")
        
        print("\n🎉 ¡ÉXITO TOTAL! Google Sheets está funcionando perfectamente.")
        print(f"👀 Revisa tu hoja aquí: {sh.url}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        
        if "has not been used" in str(e) or "is disabled" in str(e):
            print("\n🔧 Las APIs aún no están habilitadas o no se han propagado.")
            print("Espera unos minutos más y vuelve a intentar.")
        elif "not found" in str(e).lower():
            print(f"\n🔧 No se encontró la hoja '{hoja_nombre}'")
            print("Verifica que el nombre sea exacto.")
        elif "permission" in str(e).lower():
            print(f"\n🔧 La hoja no está compartida con el Service Account")
            print("Comparte con: b3consulting@b3consulting.iam.gserviceaccount.com")
        
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("🧪 PRUEBA DE GOOGLE SHEETS")
    print("=" * 60)
    
    success = test_google_sheets()
    
    if success:
        print("\n" + "=" * 60)
        print("✅ ¡TODO LISTO! Ahora puedes usar tu aplicación:")
        print("streamlit run streamlit_ai_comercio_exterior.py")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("❌ Aún hay problemas. Revisa las instrucciones arriba.")
        print("=" * 60) 