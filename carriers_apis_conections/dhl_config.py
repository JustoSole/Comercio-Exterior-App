#!/usr/bin/env python3
"""
🔧 Configuración Centralizada DHL
================================

Configuración centralizada para evitar duplicación de credenciales
y parámetros de DHL en múltiples archivos.
"""

# Credenciales DHL - Ahora se cargan desde secrets.toml
def get_dhl_credentials_from_secrets():
    """Cargar credenciales DHL desde secrets.toml de Streamlit"""
    try:
        import streamlit as st
        return {
            "username": st.secrets["api_keys"]["DHL_USERNAME"],
            "password": st.secrets["api_keys"]["DHL_PASSWORD"],
            "account_number": st.secrets["api_keys"]["DHL_ACCOUNT_NUMBER"]
        }
    except Exception:
        # Fallback para scripts que no usan Streamlit
        import os
        return {
            "username": os.getenv("DHL_USERNAME", ""),
            "password": os.getenv("DHL_PASSWORD", ""),
            "account_number": os.getenv("DHL_ACCOUNT_NUMBER", "")
        }

# URLs de API - Usando formato estándar
DHL_URLS = {
    "test": "https://express.api.dhl.com/mydhlapi/test/rates",
    "production": "https://express.api.dhl.com/mydhlapi/rates"
}

# Configuración por defecto
DHL_DEFAULTS = {
    "test_mode": True,
    "timeout": 30,
    "product_code": "P",  # EXPRESS WORLDWIDE
    "unit_of_measurement": "metric"
}

# Direcciones por defecto
DEFAULT_ADDRESSES = {
    "origin": {
        "postalCode": "518000",  # Shenzhen, China
        "cityName": "SHENZHEN",
        "countryCode": "CN",
        "addressLine1": "addres1",  # Formato que funciona con DHL test
        "addressLine2": "addres2",
        "addressLine3": "addres3"
    },
    "destination": {
        "postalCode": "1440",  # Código que funciona con DHL test
        "cityName": "CAPITAL FEDERAL",
        "countryCode": "AR",
        "addressLine1": "addres1",  # Formato que funciona con DHL test
        "addressLine2": "addres2",
        "addressLine3": "addres3"
    }
}

def get_dhl_credentials():
    """Obtener credenciales DHL desde secrets.toml"""
    return get_dhl_credentials_from_secrets()

def get_dhl_url(test_mode=True):
    """Obtener URL de API según el modo"""
    return DHL_URLS["test"] if test_mode else DHL_URLS["production"]

def get_default_addresses():
    """Obtener direcciones por defecto"""
    return DEFAULT_ADDRESSES.copy() 