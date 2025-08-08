#!/usr/bin/env python3
"""
🚀 Configuración Centralizada FedEx
==================================

Configuración centralizada para evitar duplicación de credenciales
y parámetros de FedEx en múltiples archivos.
"""

import os

# Credenciales FedEx - Ahora se cargan desde secrets.toml
def get_fedex_credentials_from_secrets():
    """Cargar credenciales FedEx desde secrets.toml de Streamlit"""
    try:
        import streamlit as st
        return {
            "client_id": st.secrets["api_keys"]["FEDEX_CLIENT_ID"],
            "client_secret": st.secrets["api_keys"]["FEDEX_CLIENT_SECRET"],
            "account_number": st.secrets["api_keys"]["FEDEX_ACCOUNT_NUMBER"]
        }
    except Exception:
        # Fallback para scripts que no usan Streamlit
        import os
        return {
            "client_id": os.getenv("FEDEX_CLIENT_ID", ""),
            "client_secret": os.getenv("FEDEX_CLIENT_SECRET", ""),
            "account_number": os.getenv("FEDEX_ACCOUNT_NUMBER", "")
        }

# URLs de API
FEDEX_URLS = {
    "test": {
        "base": "https://apis-sandbox.fedex.com",
        "oauth": "https://apis-sandbox.fedex.com/oauth/token",
        "rates": "https://apis-sandbox.fedex.com/rate/v1/comprehensiverates/quotes",
        "transit": "https://apis-sandbox.fedex.com/availability/v1/transittimes"
    },
    "production": {
        "base": "https://apis.fedex.com",
        "oauth": "https://apis.fedex.com/oauth/token",
        "rates": "https://apis.fedex.com/rate/v1/comprehensiverates/quotes",
        "transit": "https://apis.fedex.com/availability/v1/transittimes"
    }
}

# Configuración por defecto
FEDEX_DEFAULTS = {
    "test_mode": True,
    "timeout": 40,
    "pickup_type": "USE_SCHEDULED_PICKUP",
    "packaging_type": "YOUR_PACKAGING",
    "currency": "USD",
    "weight_units": "KG"
}

# Direcciones por defecto
DEFAULT_ADDRESSES = {
    "origin": {
        "postalCode": "38125",  # Memphis, TN (FedEx hub)
        "countryCode": "US",
        "residential": False
    },
    "destination": {
        "postalCode": "C1000",  # Buenos Aires, Argentina
        "countryCode": "AR", 
        "residential": False
    }
}

def get_fedex_credentials():
    """Obtener credenciales FedEx desde secrets.toml"""
    return get_fedex_credentials_from_secrets()

def get_fedex_urls(test_mode=True):
    """Obtener URLs de API según el modo"""
    return FEDEX_URLS["test"] if test_mode else FEDEX_URLS["production"]

def get_default_addresses():
    """Obtener direcciones por defecto"""
    return DEFAULT_ADDRESSES.copy()

def should_allow_production():
    """Verificar si se permite modo producción"""
    return os.getenv("FEDEX_ALLOW_PROD", "false").lower() in {"1", "true", "yes", "y"}