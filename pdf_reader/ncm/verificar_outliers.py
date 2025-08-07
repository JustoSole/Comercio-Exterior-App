import pandas as pd
import numpy as np

def analizar_dataset_ncm(file_path):
    """
    Realiza un Análisis Exploratorio de Datos (EDA) sobre el dataset NCM.
    
    El análisis incluye:
    1. Resumen general del dataset (dimensiones, tipos de datos).
    2. Conteo de valores nulos por columna.
    3. Estadísticas descriptivas de los impuestos.
    4. Identificación y listado de posiciones con impuestos > 100%.
    5. Exportación de los resultados a un archivo CSV para revisión.
    """
    try:
        df = pd.read_csv(file_path)
    except FileNotFoundError:
        print(f"❌ Error: No se pudo encontrar el archivo en la ruta: {file_path}")
        return

    print("--- INICIANDO ANÁLISIS EXPLORATORIO DE DATOS (EDA) DEL NCM ---")

    # --- 1. Información General del Dataset ---
    print("\n✅ 1. Resumen General del Dataset")
    print("-------------------------------------")
    print(f"El dataset tiene {df.shape[0]} filas y {df.shape[1]} columnas.")
    print("\nTipos de datos por columna:")
    # Usamos print para un formato más limpio que df.info() directamente
    for col, dtype in df.dtypes.items():
        print(f"- {col}: {dtype}")

    # --- 2. Conteo de Valores Nulos ---
    print("\n✅ 2. Conteo de Valores Nulos por Columna")
    print("------------------------------------------")
    null_counts = df.isnull().sum()
    null_counts = null_counts[null_counts > 0]
    if not null_counts.empty:
        print(null_counts.to_string())
    else:
        print("¡Excelente! No hay valores nulos en el dataset.")

    # --- 3. Estadísticas Descriptivas de Impuestos ---
    print("\n✅ 3. Estadísticas Descriptivas de Impuestos")
    print("---------------------------------------------")
    tax_columns = ['aec', 'die', 'te', 'de', 're']
    
    # Limpieza: Convertir columnas de impuestos a numérico, forzando errores a NaN
    for col in tax_columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Rellenar NaN con 0 para el análisis estadístico
    df[tax_columns] = df[tax_columns].fillna(0)
    
    # Mostramos las estadísticas
    pd.set_option('display.float_format', '{:.2f}'.format) # Formato de 2 decimales
    print(df[tax_columns].describe().to_string())


    # --- 4. Análisis de Impuestos Altos (> 100%) ---
    print("\n✅ 4. Posiciones con Impuestos (aec, die, te) > 100%")
    print("-----------------------------------------------------")
    
    # Filtrar filas donde cualquier impuesto principal sea mayor a 100
    filtro_impuestos_altos = (df['aec'] > 100) | (df['die'] > 100) | (df['te'] > 100)
    df_altos = df[filtro_impuestos_altos].copy()

    if df_altos.empty:
        print("No se encontraron posiciones con impuestos superiores al 100%.")
    else:
        # Encontrar el valor máximo de impuesto en cada fila para ordenar
        df_altos['impuesto_maximo'] = df_altos[tax_columns].max(axis=1)

        # Ordenar el DataFrame de mayor a menor
        df_ordenado = df_altos.sort_values(by='impuesto_maximo', ascending=False)

        # Seleccionar y mostrar las columnas relevantes en consola
        columnas_a_mostrar = ['code', 'description', 'aec', 'die', 'te', 'impuesto_maximo']
        print("Resultados encontrados (ordenados de mayor a menor):")
        print(df_ordenado[columnas_a_mostrar].to_string(index=False))

        # --- 5. Exportar Resultados Accionables a CSV ---
        output_filename = 'impuestos_altos_para_revision.csv'
        try:
            df_ordenado.to_csv(output_filename, index=False, encoding='utf-8-sig')
            print(f"\n✅ 5. Resultados exportados exitosamente")
            print("-------------------------------------------")
            print(f"Se ha guardado un archivo llamado '{output_filename}' con las posiciones a revisar.")
        except Exception as e:
            print(f"❌ Error al guardar el archivo CSV: {e}")
            
    print("\n--- ANÁLISIS FINALIZADO ---")


# --- Ejecutar el script ---
if __name__ == "__main__":
    # Ruta al archivo CSV. Asegúrate de que sea la correcta.
    archivo_ncm = 'pdf_reader/ncm/resultados_ncm_hybrid/dataset_ncm_HYBRID_FIXED_20250721_175449.csv'
    analizar_dataset_ncm(archivo_ncm)