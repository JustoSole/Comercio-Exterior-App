import camelot
import pandas as pd
import os

def extract_tables_from_pdf(pdf_path):
    # Extraer tablas de las páginas 1-6
    tables = camelot.read_pdf(pdf_path, pages='1-6', flavor='lattice')

    # Concatenar todas las tablas extraídas en un solo DataFrame
    all_dfs = [table.df for table in tables]
    df = pd.concat(all_dfs, ignore_index=True)

    return df

if __name__ == "__main__":
    # Obtener la ruta del directorio actual
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Construir la ruta al archivo PDF
    pdf_filename = 'SUNA SOLUTIONS_AR_102628161_spa_20250704-234913-041.PDF'
    pdf_path = os.path.join(current_dir, pdf_filename)
    
    # Construir la ruta para el archivo CSV de salida
    output_csv_path = os.path.join(current_dir, 'extracted_tables.csv')

    # Extraer las tablas
    extracted_data = extract_tables_from_pdf(pdf_path)

    # Limpiar y reestructurar los datos
    # La primera columna es 'KG', las demás están en la segunda columna separadas por '\n'
    
    # Crear una lista para almacenar los datos reestructurados
    new_data = []

    # Iterar sobre cada fila del DataFrame extraído
    for index, row in extracted_data.iterrows():
        kg = row[0]
        # Dividir la segunda columna por el salto de línea y limpiar espacios
        zones = [z.strip() for z in row[1].split('\n')]
        
        # Crear una nueva fila con KG y las zonas
        new_row = [kg] + zones
        new_data.append(new_row)

    # Crear un nuevo DataFrame con los datos reestructurados
    cleaned_df = pd.DataFrame(new_data)

    # Asignar los nombres de las columnas
    # Comprobar si hay 7 columnas antes de asignar nombres
    if cleaned_df.shape[1] == 7:
        cleaned_df.columns = ['KG', 'Zona 1', 'Zona 2', 'Zona 3', 'Zona 4', 'Zona 5', 'Zona 6']
    else:
        # Si no hay 7 columnas, es posible que la extracción haya fallado en alguna parte.
        # Imprimir un aviso y los datos para depuración.
        print("Advertencia: El número de columnas no es 7. La extracción puede ser incorrecta.")
        print(cleaned_df.head())


    # Guardar el DataFrame en un archivo CSV
    cleaned_df.to_csv(output_csv_path, index=False)

    print(f"Tablas extraídas y guardadas en {output_csv_path}")
    print(cleaned_df.head()) 