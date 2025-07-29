#!/usr/bin/env python3
"""
Script de prueba para Google Sheets
Ejecutar después de habilitar las APIs
"""

import sys
import toml
from datetime import datetime

def test_formulas_with_upload_function():
    """Probar la nueva función upload_to_google_sheets con fórmulas automáticas"""
    try:
        print("🧮 Probando función upload_to_google_sheets con fórmulas...")
        
        # Importar módulos
        sys.path.append('.')
        from streamlit_ai_comercio_exterior import get_gspread_client, upload_to_google_sheets
        
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
        
        # Crear datos de prueba simulando una cotización real
        test_data = {
            "fecha": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            "producto": "Smartphone Samsung Galaxy A54 - TEST FÓRMULAS",
            "imagen_url": "https://via.placeholder.com/150x150.png?text=Samsung+A54",
            "url_producto": "https://alibaba.com/product/test-smartphone",
            "cantidad": 50,
            "precio_unitario_fob": 180.50,
            "moneda": "USD",
            "tipo_cambio": 1250.00,
            "derechos_importacion_pct": 16,
            "tasa_estadistica_pct": 3,
            "iva_importacion_pct": 21,
            "percepcion_iva_pct": 10,
            "percepcion_ganancias_pct": 7,
            "ingresos_brutos_pct": 2.5,
            "costo_flete_unitario": 8.25,
            "honorarios_despachante": 1200,
            "ncm": "8517.12.00",
            "descripcion_ncm": "Teléfonos móviles y demás equipos de telefonía móvil",
            "confianza_ia": "95%",
            "peso_unitario_kg": 0.195,
            "dimensiones": "15.4 × 7.6 × 0.82 cm",
            "metodo_flete": "Aéreo Express",
            "origen": "China",
            "destino": "Argentina",
            "tipo_importador": "Habitual",
            "provincia": "Buenos Aires",
            "notas": "Producto de prueba para testing de fórmulas automáticas"
        }
        
        print("📊 Datos de prueba preparados:")
        print(f"  Producto: {test_data['producto']}")
        print(f"  Cantidad: {test_data['cantidad']} unidades")
        print(f"  Precio FOB: USD {test_data['precio_unitario_fob']}")
        print(f"  Tipo de cambio: ${test_data['tipo_cambio']}")
        print(f"  Impuestos: {test_data['derechos_importacion_pct']}% + {test_data['iva_importacion_pct']}% + otros")
        
        # Probar la función upload_to_google_sheets
        print("\n🚀 Ejecutando upload_to_google_sheets...")
        
        # Simular el contexto de Streamlit para evitar errores
        class MockStreamlit:
            def error(self, msg): print(f"ERROR: {msg}")
            def warning(self, msg): print(f"WARNING: {msg}")
            def info(self, msg): print(f"INFO: {msg}")
            def success(self, msg): print(f"SUCCESS: {msg}")
            def write(self, msg): print(f"WRITE: {msg}")
        
        st.error = MockStreamlit().error
        st.warning = MockStreamlit().warning
        st.info = MockStreamlit().info
        st.success = MockStreamlit().success
        st.write = MockStreamlit().write
        
        # Ejecutar la función
        result = upload_to_google_sheets(test_data, "Cotizaciones APP IA")
        
        if result:
            print("\n✅ ¡ÉXITO! Función upload_to_google_sheets ejecutada correctamente")
            print("\n🧮 VERIFICAR EN GOOGLE SHEETS:")
            print("  1. ✅ Datos base cargados")
            print("  2. ✅ Fórmulas de cálculo automático aplicadas")
            print("  3. ✅ Status visual con emojis")
            print("  4. ✅ Alertas de impuestos")
            print("  5. ✅ ROI y precio de venta calculados")
            print("  6. ✅ Formato de moneda aplicado")
            print("  7. ✅ Fórmula de imagen agregada")
            
            expected_formulas = [
                "Subtotal FOB = Cantidad × Precio Unitario",
                "Derechos Importación = Subtotal × (Porcentaje/100)", 
                "Total Impuestos = SUMA de todos los impuestos",
                "Total Landed Cost = Subtotal + Impuestos + Flete",
                "Status visual basado en el costo total",
                "ROI calculado automáticamente"
            ]
            
            print("\n📋 FÓRMULAS ESPERADAS:")
            for i, formula in enumerate(expected_formulas, 1):
                print(f"  {i}. {formula}")
            
            return True
        else:
            print("\n❌ Error en la función upload_to_google_sheets")
            return False
            
    except Exception as e:
        print(f"\n❌ Error en test de fórmulas con upload: {e}")
        import traceback
        print(f"📋 Detalles: {traceback.format_exc()}")
        return False

def test_formulas_google_sheets():
    """Probar carga de fórmulas específicas en Google Sheets"""
    try:
        print("🧮 Probando fórmulas en Google Sheets...")
        
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
        
        # Conectar a Google Sheets
        gc = get_gspread_client()
        if not gc:
            print("❌ No se pudo crear el cliente de Google Sheets")
            return False
        
        # Usar la hoja existente en lugar de crear una nueva
        hoja_nombre = "Cotizaciones APP IA"
        try:
            sh = gc.open(hoja_nombre)
            print(f"✅ Usando hoja existente '{hoja_nombre}'")
        except Exception as e:
            print(f"❌ Error al acceder a la hoja '{hoja_nombre}': {e}")
            return False
        
        # Crear un nuevo worksheet para las pruebas de fórmulas
        try:
            # Intentar crear un nuevo worksheet dentro de la hoja existente
            worksheet = sh.add_worksheet(title="TEST Fórmulas", rows="100", cols="20")
            print("✅ Worksheet de prueba creado")
        except Exception as ws_error:
            print(f"⚠️ No se pudo crear nuevo worksheet, usando el principal: {ws_error}")
            # Usar el worksheet principal y agregar datos al final
            worksheet = sh.sheet1
            
            # Encontrar la primera fila vacía para no sobrescribir datos existentes
            values = worksheet.get_all_values()
            start_row = len(values) + 2  # Dejar una fila en blanco
            
            print(f"📊 Usando worksheet principal, iniciando en fila {start_row}")
        
        # 1. AGREGAR ENCABEZADOS PARA LA SECCIÓN DE PRUEBAS
        print("📋 Agregando sección de pruebas de fórmulas...")
        
        try:
            if 'start_row' in locals():
                # Estamos en el worksheet principal, agregar desde la fila calculada
                current_row = start_row
                worksheet.update(f'A{current_row}', "=== PRUEBA DE FÓRMULAS ===")
                current_row += 1
            else:
                # Estamos en un worksheet nuevo, empezar desde la fila 1
                current_row = 1
                worksheet.clear()
            
            headers = [
                "Producto", "Cantidad", "Precio USD", "Tipo Cambio", 
                "Precio ARS", "Impuestos %", "Total Impuestos", 
                "Flete USD", "Total Landed", "Status", "Validación"
            ]
            
            # Agregar encabezados
            for col, header in enumerate(headers, start=1):
                worksheet.update_cell(current_row, col, header)
            
            current_row += 1
            
            # 2. AGREGAR DATOS DE EJEMPLO
            print("📊 Agregando datos de ejemplo...")
            datos_ejemplo = [
                ["Smartphone Samsung", 10, 150, 1200, "", 35, "", 25, "", "", ""],
                ["Laptop Dell", 5, 800, 1200, "", 35, "", 75, "", "", ""],
                ["Tablet iPad", 8, 500, 1200, "", 35, "", 40, "", "", ""]
            ]
            
            start_data_row = current_row
            for datos in datos_ejemplo:
                for col, valor in enumerate(datos, start=1):
                    if valor != "":
                        worksheet.update_cell(current_row, col, valor)
                current_row += 1
            
            # 3. AGREGAR FÓRMULAS DE CÁLCULO
            print("💰 Agregando fórmulas de cálculo...")
            
            for row in range(start_data_row, start_data_row + 3):
                # Precio ARS = Precio USD * Tipo Cambio (columna E = 5)
                formula_ars = f"=C{row}*D{row}"
                worksheet.update_cell(row, 5, formula_ars)
                
                # Total Impuestos = Precio ARS * (Impuestos% / 100) (columna G = 7)
                formula_impuestos = f"=E{row}*(F{row}/100)"
                worksheet.update_cell(row, 7, formula_impuestos)
                
                # Total Landed = Precio ARS + Impuestos + (Flete USD * Tipo Cambio) (columna I = 9)
                formula_landed = f"=E{row}+G{row}+(H{row}*D{row})"
                worksheet.update_cell(row, 9, formula_landed)
                
                # Status condicional (columna J = 10)
                formula_status = f'=IF(I{row}>500000;"🔴 ALTO";IF(I{row}>200000;"🟡 MEDIO";"🟢 BAJO"))'
                worksheet.update_cell(row, 10, formula_status)
                
                # Validación (columna K = 11)
                formula_validacion = f'=IF(AND(B{row}>0;C{row}>0;D{row}>0);"✅";"❌")'
                worksheet.update_cell(row, 11, formula_validacion)
            
            # 4. AGREGAR FÓRMULAS DE RESUMEN
            print("📊 Agregando fórmulas de resumen...")
            current_row += 1
            worksheet.update_cell(current_row, 1, "RESUMEN:")
            current_row += 1
            
            # Total cantidad
            worksheet.update_cell(current_row, 1, "Total Cantidad:")
            formula_total_cant = f"=SUM(B{start_data_row}:B{start_data_row+2})"
            worksheet.update_cell(current_row, 2, formula_total_cant)
            
            # Promedio precio USD
            worksheet.update_cell(current_row, 3, "Prom USD:")
            formula_prom_usd = f"=AVERAGE(C{start_data_row}:C{start_data_row+2})"
            worksheet.update_cell(current_row, 4, formula_prom_usd)
            
            # Total ARS
            worksheet.update_cell(current_row, 5, "Total ARS:")
            formula_total_ars = f"=SUM(E{start_data_row}:E{start_data_row+2})"
            worksheet.update_cell(current_row, 6, formula_total_ars)
            
            # Total Landed Cost
            worksheet.update_cell(current_row, 7, "Total Landed:")
            formula_total_landed = f"=SUM(I{start_data_row}:I{start_data_row+2})"
            worksheet.update_cell(current_row, 8, formula_total_landed)
            
            # 5. PRUEBA DE FÓRMULA DE IMAGEN (si hay espacio)
            print("🖼️ Agregando fórmula de imagen...")
            try:
                current_row += 2
                worksheet.update_cell(current_row, 1, "Test Imagen:")
                formula_imagen = '=IMAGE("https://via.placeholder.com/100x100.png?text=TEST")'
                worksheet.update_cell(current_row, 2, formula_imagen)
            except Exception as img_error:
                print(f"⚠️ No se pudo agregar imagen: {img_error}")
            
            print("✅ ¡Todas las fórmulas agregadas exitosamente!")
            print(f"📋 Ver hoja con fórmulas: {sh.url}")
            
            # Resumen de fórmulas probadas
            formulas_probadas = [
                "✅ Conversión de moneda (=C*D)",
                "✅ Cálculo de impuestos (=E*(F/100))",
                "✅ Landed cost total (=E+G+(H*D))",
                "✅ Condicionales IF anidadas con ;",
                "✅ Validación con AND usando ;",
                "✅ Funciones SUM, AVERAGE",
                "✅ Fórmulas IMAGE",
                "✅ Formato condicional con emojis"
            ]
            
            print("\n🧮 FÓRMULAS PROBADAS:")
            for formula in formulas_probadas:
                print(f"  {formula}")
            
            return True
            
        except Exception as formula_error:
            print(f"❌ Error agregando fórmulas: {formula_error}")
            import traceback
            print(f"📋 Detalles: {traceback.format_exc()}")
            return False
        
    except Exception as e:
        print(f"\n❌ Error en test de fórmulas: {e}")
        import traceback
        print(f"📋 Detalles: {traceback.format_exc()}")
        return False

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

def test_simple_upload():
    """Test simple para verificar upload_to_google_sheets con fórmulas"""
    try:
        print("🚀 Test simple de upload con fórmulas...")
        
        # Importar módulos
        sys.path.append('.')
        from streamlit_ai_comercio_exterior import upload_to_google_sheets
        
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
        
        # Mock simple de streamlit
        class MockST:
            def error(self, msg): print(f"❌ {msg}")
            def warning(self, msg): print(f"⚠️ {msg}")
            def info(self, msg): print(f"ℹ️ {msg}")
            def success(self, msg): print(f"✅ {msg}")
            def write(self, msg): print(f"📝 {msg}")
        
        mock_st = MockST()
        st.error = mock_st.error
        st.warning = mock_st.warning
        st.info = mock_st.info
        st.success = mock_st.success
        st.write = mock_st.write
        
        # Datos mínimos para test
        test_data = {
            "fecha": "29/07/2024 10:00:00",
            "producto": "TEST SIMPLE - Smartphone",
            "imagen_url": "https://via.placeholder.com/100x100.png?text=TEST",
            "url_producto": "https://test.com",
            "cantidad": 10,
            "precio_unitario_fob": 100.0,
            "moneda": "USD",
                         "tipo_cambio": 1200.0,
             "derechos_importacion_pct": 0.15,  # 15% como decimal
             "tasa_estadistica_pct": 0.03,   # 3% como decimal
             "iva_importacion_pct": 0.21,    # 21% como decimal
             "percepcion_iva_pct": 0.08,     # 8% como decimal
             "percepcion_ganancias_pct": 0.05, # 5% como decimal
             "ingresos_brutos_pct": 0.02,    # 2% como decimal
            "costo_flete_unitario": 5.0,
            "honorarios_despachante": 500,
            "ncm": "8517.12.00",
            "descripcion_ncm": "Teléfonos móviles",
            "confianza_ia": "90%",
            "peso_unitario_kg": 0.2,
            "dimensiones": "15 × 7 × 1 cm",
            "metodo_flete": "Aéreo",
            "origen": "China",
            "destino": "Argentina",
            "tipo_importador": "Habitual",
            "provincia": "Buenos Aires",
            "notas": "Test de fórmulas automáticas"
        }
        
        print("📊 Ejecutando upload_to_google_sheets...")
        result = upload_to_google_sheets(test_data)
        
        if result:
            print("\n🎉 ¡ÉXITO! Upload completado con fórmulas")
            print("📋 Ve tu Google Sheets para verificar:")
            print("  • Subtotal FOB = Cantidad × Precio")
            print("  • Impuestos calculados automáticamente")
            print("  • Total Landed Cost dinámico")
            print("  • Status visual con emojis")
            print("  • ROI y alertas")
        else:
            print("\n❌ Error en upload")
            
        return result
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    print("=" * 70)
    print("🧪 PRUEBA DE GOOGLE SHEETS Y FÓRMULAS AUTOMÁTICAS")
    print("=" * 70)
    
    # Test básico de conexión
    success_basic = test_google_sheets()
    
    if success_basic:
        print("\n" + "=" * 70)
        print("🚀 TEST SIMPLE DE UPLOAD CON FÓRMULAS")
        print("=" * 70)
        
        # Test simple de upload
        success_simple = test_simple_upload()
        
        if success_simple:
            print("\n" + "=" * 70)
            print("✅ ¡PERFECTO! Fórmulas automáticas funcionando")
            print("📊 Revisa tu Google Sheets para ver:")
            print("  🧮 Cálculos automáticos")
            print("  💰 Formato de moneda aplicado")
            print("  📊 Status y alertas visuales")
            print("  🔄 Fórmulas dinámicas")
            print("\n🚀 Tu aplicación está lista:")
            print("streamlit run streamlit_ai_comercio_exterior.py")
            print("=" * 70)
        else:
            print("\n" + "=" * 70)
            print("⚠️ Problemas con fórmulas - revisar implementación")
            print("=" * 70)
    else:
        print("\n" + "=" * 70)
        print("❌ Problemas de conexión básica")
        print("=" * 70) 