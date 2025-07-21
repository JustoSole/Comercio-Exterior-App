import pandas as pd
import numpy as np
import os

def load_freight_rates(file_path):
    """Carga las tarifas de flete desde un archivo CSV."""
    try:
        df = pd.read_csv(file_path)
        # Convertir todas las columnas a numérico, forzando errores a NaN
        for col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce')
        # Eliminar filas con valores NaN que podrían haber sido creados por la coerción
        df = df.dropna()
        return df
    except FileNotFoundError:
        return None

def calculate_air_freight(weight, rates_df):
    """
    Calcula el costo del flete aéreo para la Zona 5 basado en el peso,
    utilizando interpolación lineal.
    """
    if rates_df is None or 'KG' not in rates_df.columns or 'Zona 5' not in rates_df.columns:
        return 0.0

    # Asegurarse que los datos están ordenados por KG
    rates_df = rates_df.sort_values(by='KG').reset_index(drop=True)

    # Usar np.interp para la interpolación lineal
    # Asume que rates_df['KG'] y rates_df['Zona 5'] son los puntos conocidos
    cost = np.interp(weight, rates_df['KG'], rates_df['Zona 5'])
    
    return cost

def calculate_sea_freight(volume_m3):
    """
    Calcula el costo del flete marítimo.
    """
    cost_per_m3 = 90.0
    return volume_m3 * cost_per_m3

if __name__ == '__main__':
    # Test del módulo
    current_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(current_dir, 'pdf_reader', 'extracted_tables.csv')

    rates = load_freight_rates(csv_path)

    if rates is not None:
        print("Tarifas cargadas exitosamente:")
        print(rates.head())

        # Test de flete aéreo
        test_weight = 220.5
        air_cost = calculate_air_freight(test_weight, rates)
        print(f"\nCosto de flete aéreo para {test_weight} kg: ${air_cost:.2f}")
        
        test_weight_exact = 220.0
        air_cost_exact = calculate_air_freight(test_weight_exact, rates)
        print(f"Costo de flete aéreo para {test_weight_exact} kg: ${air_cost_exact:.2f}")


        # Test de flete marítimo
        test_volume = 1.5  # m3
        sea_cost = calculate_sea_freight(test_volume)
        print(f"Costo de flete marítimo para {test_volume} m³: ${sea_cost:.2f}")
    else:
        print(f"No se pudo cargar el archivo de tarifas en: {csv_path}") 