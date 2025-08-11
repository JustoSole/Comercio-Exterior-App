import pandas as pd
import numpy as np
import os

def load_freight_rates(file_path):
    """Carga las tarifas de flete desde un archivo CSV (mantener para compatibilidad)."""
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

def calculate_air_freight_by_origin(weight_kg, origin_country):
    """
    Calcula el costo del flete aéreo basado en el país de origen y peso.
    
    Args:
        weight_kg (float): Peso en kilogramos
        origin_country (str): País de origen ('CN' para China, 'US' para USA)
    
    Returns:
        float: Costo del flete en USD
    """
    # Tarifas fijas por kg según país de origen
    rates = {
        'CN': 27.0,  # China a Argentina: 27 USD/kg
        'US': 13.5   # USA a Argentina: 13.5 USD/kg
    }
    
    # Usar China como default si el país no está especificado o no está en la lista
    rate_per_kg = rates.get(origin_country, rates['CN'])
    
    return weight_kg * rate_per_kg

def calculate_air_freight(weight, rates_df=None):
    """
    Función legacy para compatibilidad con código existente.
    Ahora usa el nuevo sistema de tarifas por país de origen.
    Asume China como origen por defecto.
    """
    return calculate_air_freight_by_origin(weight, 'CN')

def calculate_sea_freight(volume_m3):
    """
    Calcula el costo del flete marítimo.
    """
    cost_per_m3 = 90.0
    return volume_m3 * cost_per_m3

if __name__ == '__main__':
    # Test del módulo con nuevas tarifas fijas
    print("=== TEST DE NUEVO SISTEMA DE FLETES ===\n")
    
    # Test de flete aéreo por país de origen
    test_weight = 5.0
    
    print("🇨🇳 CHINA → ARGENTINA:")
    china_cost = calculate_air_freight_by_origin(test_weight, 'CN')
    print(f"Peso: {test_weight} kg")
    print(f"Tarifa: 27.0 USD/kg")
    print(f"Costo total: ${china_cost:.2f} USD\n")
    
    print("🇺🇸 USA → ARGENTINA:")
    usa_cost = calculate_air_freight_by_origin(test_weight, 'US')
    print(f"Peso: {test_weight} kg")
    print(f"Tarifa: 13.5 USD/kg")
    print(f"Costo total: ${usa_cost:.2f} USD\n")
    
    print("🚢 FLETE MARÍTIMO:")
    test_volume = 1.5  # m3
    sea_cost = calculate_sea_freight(test_volume)
    print(f"Volumen: {test_volume} m³")
    print(f"Tarifa: 90.0 USD/m³")
    print(f"Costo total: ${sea_cost:.2f} USD\n")
    
    # Test de compatibilidad con función legacy
    print("🔄 TEST DE COMPATIBILIDAD:")
    legacy_cost = calculate_air_freight(test_weight)
    print(f"Función legacy (asume China): ${legacy_cost:.2f} USD")
    print(f"Función nueva (China explícito): ${china_cost:.2f} USD")
    print(f"Resultado igual: {'✅' if abs(legacy_cost - china_cost) < 0.01 else '❌'}")
    
    print("\n=== COMPARACIÓN DE COSTOS CHINA vs USA ===")
    print(f"Peso de prueba: {test_weight} kg")
    print(f"China: ${china_cost:.2f} USD ({china_cost/test_weight:.1f} USD/kg)")
    print(f"USA: ${usa_cost:.2f} USD ({usa_cost/test_weight:.1f} USD/kg)")
    print(f"Diferencia: ${abs(china_cost - usa_cost):.2f} USD")
    print(f"USA es {'más barato' if usa_cost < china_cost else 'más caro'} que China") 