#!/usr/bin/env python3
"""
🤖 AI Comercio Exterior - Calculadora de Landed Cost
====================================================

Flujo simplificado:
1. URL de Alibaba → Extraer datos del producto
2. Clasificar NCM automáticamente con IA
3. Calcular impuestos argentinos
4. Calcular flete internacional
5. Mostrar landed cost total con transparencia completa

Versión simplificada con datos reales
Última actualización: 2025-01-21 - Secrets fix v2
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from decimal import Decimal
from datetime import datetime, timedelta, time
import datetime as dt_module
import json
import time as time_module
import traceback
import os
import requests
from urllib.parse import urlparse
import re
import asyncio
import io

# Import para Google Sheets
import gspread
from google.oauth2.service_account import Credentials

# Import del gestor de secrets - Usando secrets nativos de Streamlit
def get_api_keys_dict():
    """Obtener API keys desde los secrets de Streamlit"""
    try:
        return {
            "OPENAI_API_KEY": st.secrets["api_keys"]["OPENAI_API_KEY"],
            "APIFY_API_KEY": st.secrets["api_keys"]["APIFY_API_KEY"],
            "EASYPOST_API_KEY": st.secrets["api_keys"].get("EASYPOST_API_KEY", ""),
            "EASYPOST_API_KEY_TEST": st.secrets["api_keys"].get("EASYPOST_API_KEY_TEST", ""),
            "EASYPOST_WEBHOOK_SECRET": st.secrets["api_keys"].get("EASYPOST_WEBHOOK_SECRET", "")
        }
    except Exception as e:
        st.error(f"Error cargando API keys: {e}")
        return {}

def validate_setup():
    """Validar que las API keys principales estén configuradas"""
    try:
        api_keys = get_api_keys_dict()
        required_keys = ["OPENAI_API_KEY", "APIFY_API_KEY"]
        missing_keys = [key for key in required_keys if not api_keys.get(key)]
        
        if missing_keys:
            st.error(f"❌ API keys faltantes: {', '.join(missing_keys)}")
            return False
        return True
    except Exception:
        return False

def get_secrets_manager():
    """Función de compatibilidad - devuelve los secrets de Streamlit"""
    return st.secrets

# Cargar API keys desde el archivo centralizado
API_KEYS = get_api_keys_dict()

# Configurar variables de entorno para compatibilidad
os.environ['OPENAI_API_KEY'] = API_KEYS.get("OPENAI_API_KEY", "")

# Configuración del archivo de datos NCM para integración refinada
NCM_DATA_FILE = "pdf_reader/ncm/resultados_ncm_hybrid/dataset_ncm_HYBRID_FIXED_20250721_175449.csv"

# Configuración del archivo de tarifas de flete DHL
FREIGHT_RATES_FILE = "pdf_reader/dhl_carrier/extracted_tables.csv"

# Imports de módulos reales
try:
    from alibaba_scraper import scrape_single_alibaba_product, extract_alibaba_pricing, format_pricing_for_display, calculate_total_cost_for_option, get_cheapest_price_option
    from ai_ncm_classifier import AINcmClassifier  # Sistema NCM oficial actualizado
    from import_tax_calculator import calcular_impuestos_importacion
    from product_dimension_estimator import ProductShippingEstimator
    from dhl_freight_integration import DHLFreightService
    # Mantener freight_estimation como fallback
    from freight_estimation import load_freight_rates, calculate_air_freight, calculate_sea_freight
    MODULES_AVAILABLE = True
except ImportError as e:
    st.error(f"Error importing modules: {e}")
    MODULES_AVAILABLE = False

# Agregar import para Excel
try:
    import xlsxwriter
    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False

# Configuración de la página
st.set_page_config(
    page_title="🤖 AI Comercio Exterior",
    page_icon="🚢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Validar configuración de API keys al inicio
if not validate_setup():
    st.warning("⚠️ Algunas API keys no están configuradas. Revisa el archivo .streamlit/secrets.toml")

# CSS minimalista y neutro
st.markdown("""
<style>
    /* Reset y base */
    .main .block-container {
        padding-top: 1rem;
        padding-bottom: 0rem;
        padding-left: 1rem;
        padding-right: 1rem;
        max-width: 1200px;
    }
    
    /* Header principal */
    .main-header {
        background: #f8f9fa;
        border: 1px solid #e9ecef;
        padding: 1.5rem;
        border-radius: 8px;
        text-align: center;
        margin-bottom: 1.5rem;
        color: #495057;
    }
    
    .main-header h1 {
        color: #343a40;
        margin-bottom: 0.5rem;
        font-weight: 600;
    }
    
    .main-header p {
        color: #6c757d;
        margin: 0;
        font-size: 1rem;
    }
    
    /* Steps */
    .step-header {
        background: #ffffff;
        border: 1px solid #dee2e6;
        border-left: 4px solid #6c757d;
        padding: 0.75rem 1rem;
        border-radius: 4px;
        margin: 1rem 0 0.5rem 0;
        font-weight: 500;
        color: #495057;
        font-size: 1rem;
    }
    
    /* Cajas de contenido */
    .content-box {
        background: #ffffff;
        border: 1px solid #e9ecef;
        border-radius: 6px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    
    .info-card {
        background: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 6px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    
    .result-card {
        background: #ffffff;
        border: 1px solid #dee2e6;
        border-radius: 6px;
        padding: 1.25rem;
        margin: 1rem 0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    
    /* Debug styles */
    .debug-container {
        background: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 6px;
        padding: 1rem;
        margin: 1rem 0;
    }
    
    .debug-log {
        background: #ffffff;
        border: 1px solid #e9ecef;
        border-radius: 4px;
        padding: 0.75rem;
        margin: 0.5rem 0;
        font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
        font-size: 0.875rem;
        max-height: 400px;
        overflow-y: auto;
    }
    
    .api-response {
        background: #f8f9fa;
        border: 1px solid #dee2e6;
        border-radius: 4px;
        padding: 1rem;
        margin: 0.5rem 0;
        font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
        font-size: 0.8rem;
    }
    
    /* Status indicators */
    .status-success {
        color: #28a745;
        font-weight: 500;
    }
    
    .status-error {
        color: #dc3545;
        font-weight: 500;
    }
    
    .status-warning {
        color: #ffc107;
        font-weight: 500;
    }
    
    .status-info {
        color: #17a2b8;
        font-weight: 500;
    }
    
    /* Metrics styling */
    .metric-card {
        background: #ffffff;
        border: 1px solid #e9ecef;
        border-radius: 6px;
        padding: 1rem;
        text-align: center;
        margin: 0.25rem;
    }
    
    .metric-value {
        font-size: 1.5rem;
        font-weight: 600;
        color: #495057;
        margin-bottom: 0.25rem;
    }
    
    .metric-label {
        font-size: 0.875rem;
        color: #6c757d;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    /* Sidebar improvements */
    .css-1d391kg {
        background-color: #f8f9fa;
    }
    
    /* Button improvements */
    .stButton > button {
        background-color: #495057;
        color: white;
        border: none;
        border-radius: 6px;
        padding: 0.5rem 1rem;
        font-weight: 500;
        transition: background-color 0.2s;
    }
    
    .stButton > button:hover {
        background-color: #343a40;
    }
    
    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: #f8f9fa;
        padding: 0.5rem;
        border-radius: 6px;
    }
    
    .stTabs [data-baseweb="tab"] {
        padding: 0.5rem 1rem;
        background-color: transparent;
        border-radius: 4px;
        color: #6c757d;
        font-weight: 500;
        border: none;
    }
    
    .stTabs [aria-selected="true"] {
        background-color: #ffffff;
        color: #495057;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    
    /* Table styling tipo Airtable */
    .stDataFrame {
        background-color: #ffffff;
        border-radius: 8px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        border: 1px solid #e9ecef;
    }
    
    .stDataFrame > div {
        border-radius: 8px;
    }
    
    .stDataFrame table {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        font-size: 0.875rem;
    }
    
    .stDataFrame thead th {
        background-color: #f8f9fa;
        color: #495057;
        font-weight: 600;
        text-transform: uppercase;
        font-size: 0.75rem;
        letter-spacing: 0.5px;
        padding: 0.75rem 1rem;
        border-bottom: 2px solid #e9ecef;
    }
    
    .stDataFrame tbody td {
        padding: 0.75rem 1rem;
        border-bottom: 1px solid #f1f3f4;
        vertical-align: middle;
    }
    
    .stDataFrame tbody tr:hover {
        background-color: #f8f9fa;
    }
    
    .stDataFrame tbody tr:last-child td {
        border-bottom: none;
    }
    
    /* Input styling */
    .stTextInput > div > div > input {
        border-radius: 6px;
        border: 1px solid #d1d5db;
        padding: 0.75rem;
        font-size: 0.875rem;
    }
    
    .stTextInput > div > div > input:focus {
        border-color: #495057;
        box-shadow: 0 0 0 3px rgba(73, 80, 87, 0.1);
    }
    
    /* Sidebar styling */
    .css-1d391kg {
        background-color: #f8f9fa;
        border-right: 1px solid #e9ecef;
    }
    
    .css-1d391kg .stSelectbox > div > div {
        background-color: #ffffff;
        border: 1px solid #d1d5db;
        border-radius: 4px;
    }
    
    .css-1d391kg .stNumberInput > div > div > input {
        background-color: #ffffff;
        border: 1px solid #d1d5db;
        border-radius: 4px;
    }
    
    /* Remove default spacing */
    .element-container {
        margin-bottom: 0.5rem;
    }
    
    /* Header improvements */
    h1, h2, h3, h4 {
        color: #343a40;
        font-weight: 600;
    }
    
    h4 {
        margin-top: 1.5rem;
        margin-bottom: 0.75rem;
        font-size: 1.1rem;
    }
    
    /* Responsive improvements */
    @media (max-width: 768px) {
        .main .block-container {
            padding-left: 0.5rem;
            padding-right: 0.5rem;
        }
        
        .main-header {
            padding: 1rem;
        }
        
        .stDataFrame table {
            font-size: 0.75rem;
        }
        
        .stDataFrame thead th,
        .stDataFrame tbody td {
            padding: 0.5rem;
        }
    }
</style>
""", unsafe_allow_html=True)

# Sistema de debug avanzado
def initialize_session_state():
    """Inicializar estado de sesión con sistema de debug completo"""
    if 'result' not in st.session_state:
        st.session_state.result = None
    if 'debug_mode' not in st.session_state:
        st.session_state.debug_mode = True
    if 'debug_logs' not in st.session_state:
        st.session_state.debug_logs = []
    if 'api_responses' not in st.session_state:
        st.session_state.api_responses = {}
    if 'console_output' not in st.session_state:
        st.session_state.console_output = []
    if 'flow_steps' not in st.session_state:
        st.session_state.flow_steps = []
    if 'process_data' not in st.session_state:
        st.session_state.process_data = {}
    if 'current_step' not in st.session_state:
        st.session_state.current_step = None
    if 'freight_rates' not in st.session_state:
        st.session_state.freight_rates = load_freight_rates(FREIGHT_RATES_FILE)
    if 'dhl_service' not in st.session_state:
        # Crear servicio DHL con callback de debug
        st.session_state.dhl_service = DHLFreightService(
            test_mode=True,  # Por defecto usar test mode
            use_dhl_real=True,  # Por defecto intentar usar DHL real
            fallback_rates_file=FREIGHT_RATES_FILE,
            debug_callback=debug_log  # Conectar el debug
        )
    if 'entry_mode' not in st.session_state:
        st.session_state.entry_mode = "Análisis desde URL"
    if 'product_data_editable' not in st.session_state:
        st.session_state.product_data_editable = {
            "title": "",
            "pricing_df": pd.DataFrame([{"min_quantity": 1, "price_usd": 0.0}]),
            "dimensions_cm": {"length": 0.0, "width": 0.0, "height": 0.0},
            "weight_kg": 0.0,
            "import_quantity": 1,
            "image_url": "",
            "product_url": "",
            "brand_name": "",
            "place_of_origin": "",
            "categories": "",
            "properties_text": ""
        }
    if 'data_input_step_completed' not in st.session_state:
        st.session_state.data_input_step_completed = False
    if 'scraped_product' not in st.session_state:
        st.session_state.scraped_product = None
    if 'shipping_info' not in st.session_state:
        st.session_state.shipping_info = {}
    if 'origin_details' not in st.session_state:
        st.session_state.origin_details = {
            "postalCode": "518000",
            "cityName": "SHENZHEN",
            "countryCode": "CN",
            "addressLine1": "addres1",  # Formato que funciona con DHL test
            "addressLine2": "addres2",
            "addressLine3": "addres3"
        }
    if 'destination_details' not in st.session_state:
        st.session_state.destination_details = {
            "postalCode": "1440",  # Código que funciona con DHL test
            "cityName": "CAPITAL FEDERAL",
            "countryCode": "AR",
            "addressLine1": "addres1",  # Formato que funciona con DHL test
            "addressLine2": "addres2",
            "addressLine3": "addres3"
        }
    if 'planned_shipping_datetime' not in st.session_state:
        # Fecha por defecto: 3 días desde hoy a las 2 PM
        default_datetime = datetime.now() + timedelta(days=3)
        default_datetime = default_datetime.replace(hour=14, minute=0, second=0, microsecond=0)
        st.session_state.planned_shipping_datetime = default_datetime

def debug_log(message, data=None, level="INFO"):
    """Función de debug mejorada con nivel y categorización"""
    if st.session_state.debug_mode:
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        log_entry = {
            "timestamp": timestamp,
            "level": level,
            "message": message,
            "data": data,
            "step": st.session_state.current_step
        }
        st.session_state.debug_logs.append(log_entry)
        
        # Añadir a console output
        console_msg = f"[{timestamp}] {level}: {message}"
        st.session_state.console_output.append(console_msg)
        
        # Limitar tamaño de logs
        if len(st.session_state.debug_logs) > 100:
            st.session_state.debug_logs = st.session_state.debug_logs[-100:]
        if len(st.session_state.console_output) > 100:
            st.session_state.console_output = st.session_state.console_output[-100:]

def log_api_call(api_name, request_data, response_data, success=True):
    """Registrar llamadas a APIs con request y response completos"""
    timestamp = datetime.now().isoformat()
    
    api_log = {
        "timestamp": timestamp,
        "api_name": api_name,
        "success": success,
        "request": request_data,
        "response": response_data,
        "step": st.session_state.current_step
    }
    
    key = f"{api_name}_{len(st.session_state.api_responses)}"
    st.session_state.api_responses[key] = api_log
    
    # Log en debug también
    status = "SUCCESS" if success else "ERROR"
    debug_log(f"API Call: {api_name} - {status}", {
        "request_summary": str(request_data)[:200] + "..." if len(str(request_data)) > 200 else str(request_data),
        "response_summary": str(response_data)[:200] + "..." if len(str(response_data)) > 200 else str(response_data)
    }, level=status)

def log_flow_step(step_name, status="STARTED", data=None):
    """Registrar pasos del flujo principal"""
    timestamp = datetime.now().isoformat()
    
    step_log = {
        "timestamp": timestamp,
        "step_name": step_name,
        "status": status,
        "data": data
    }
    
    st.session_state.flow_steps.append(step_log)
    st.session_state.current_step = step_name if status == "STARTED" else None
    
    debug_log(f"Flow Step: {step_name} - {status}", data, level="FLOW")

def _get_duties_from_ncm_result(ncm_result: dict) -> float:
    """Extrae los derechos de importación del resultado del NCM"""
    
    if not ncm_result:
        return 0.0
    
    # Usar datos del tratamiento arancelario del nuevo sistema integrado
    tratamiento = ncm_result.get('tratamiento_arancelario', {})
    derechos_str = tratamiento.get('derechos_importacion', '0.0%')
    
    try:
        import re
        # Extraer número de la string (ej: "20.0%" -> 20.0)
        cleaned_str = re.sub(r'[^\d.]', '', str(derechos_str))
        if cleaned_str:
            return float(cleaned_str)
    except (ValueError, TypeError):
        debug_log(f"No se pudo parsear derechos de importación: '{derechos_str}'. Usando 0.0%.", level="WARNING")
    
    return 0.0

def _get_tasa_estadistica_from_ncm_result(ncm_result: dict) -> float:
    """Extrae la tasa estadística del resultado del NCM"""
    if not ncm_result:
        return 0.0
    
    tratamiento = ncm_result.get('tratamiento_arancelario', {})
    te_str = tratamiento.get('tasa_estadistica', '0.0%')
    
    try:
        import re
        cleaned_str = re.sub(r'[^\d.]', '', str(te_str))
        if cleaned_str:
            return float(cleaned_str)
    except (ValueError, TypeError):
        debug_log(f"No se pudo parsear tasa estadística: '{te_str}'. Usando 0.0%.", level="WARNING")
    
    return 0.0

def _get_intervenciones_from_ncm_result(ncm_result: dict) -> str:
    """Extrae las intervenciones del resultado del NCM"""
    if not ncm_result:
        return "Sin intervenciones"
    
    # Combinar intervenciones de múltiples fuentes
    intervenciones_list = []
    
    # Intervenciones de IA
    if ncm_result.get('intervenciones_requeridas'):
        intervenciones_list.extend(ncm_result['intervenciones_requeridas'])
    
    # Intervenciones detectadas en base oficial
    ncm_official_info = ncm_result.get('ncm_official_info', {})
    if ncm_official_info.get('intervenciones_detectadas'):
        intervenciones_list.extend(ncm_official_info['intervenciones_detectadas'])
    
    # Eliminar duplicados
    intervenciones_unicas = list(set(intervenciones_list))
    
    if intervenciones_unicas:
        return ", ".join(intervenciones_unicas)
    else:
        return "Sin intervenciones"

def _get_all_official_taxes_from_ncm_result(ncm_result: dict) -> dict:
    """
    Extrae TODOS los impuestos oficiales del resultado NCM con información detallada
    Solo incluye impuestos relevantes para IMPORTACIÓN (excluye DE y RE que son de exportación)
    """
    if not ncm_result:
        return {
            'aec': {'valor': 0.0, 'fuente': 'No disponible', 'estado': 'No definido'},
            'die': {'valor': 0.0, 'fuente': 'No disponible', 'estado': 'No definido'},
            'te': {'valor': 0.0, 'fuente': 'No disponible', 'estado': 'No definido'},
            'intervenciones': {'valor': 'Sin intervenciones', 'fuente': 'IA', 'estado': 'Sin restricciones'}
        }
    
    # Usar datos del tratamiento arancelario del nuevo sistema
    tratamiento = ncm_result.get('tratamiento_arancelario', {})
    ncm_official_info = ncm_result.get('ncm_official_info', {})
    
    # Determinar fuente de datos: si hay match exacto, es de la base oficial
    is_official_data = ncm_official_info.get('match_exacto', False)
    fuente_datos = 'Base Oficial NCM' if is_official_data else tratamiento.get('fuente', 'IA')
    
    # Extraer AEC (Arancel Externo Común) - el más importante
    aec_valor = 0.0
    if tratamiento.get('derechos_importacion'):
        import re
        derechos_str = str(tratamiento['derechos_importacion'])
        # Extraer número de strings como "20.0%" o "20" 
        cleaned_str = re.sub(r'[^\d.]', '', derechos_str)
        if cleaned_str:
            try:
                aec_valor = float(cleaned_str)
            except (ValueError, TypeError):
                pass
    
    # Extraer TE (Tasa Estadística)
    te_valor = 0.0
    if tratamiento.get('tasa_estadistica'):
        import re
        te_str = str(tratamiento['tasa_estadistica'])
        cleaned_str = re.sub(r'[^\d.]', '', te_str)
        if cleaned_str:
            try:
                te_valor = float(cleaned_str)
            except (ValueError, TypeError):
                pass
    
    # Extraer intervenciones - combinar de múltiples fuentes
    intervenciones_list = []
    
    # Intervenciones de IA
    if ncm_result.get('intervenciones_requeridas'):
        intervenciones_list.extend(ncm_result['intervenciones_requeridas'])
    
    # Intervenciones detectadas en base oficial
    if ncm_official_info.get('intervenciones_detectadas'):
        intervenciones_list.extend(ncm_official_info['intervenciones_detectadas'])
    
    # Eliminar duplicados y crear string
    intervenciones_unicas = list(set(intervenciones_list))
    intervenciones_valor = ", ".join(intervenciones_unicas) if intervenciones_unicas else "Sin intervenciones"
    
    # Construir estructura completa con SOLO impuestos de importación
    taxes = {
        'aec': {
            'valor': aec_valor,
            'fuente': fuente_datos,
            'estado': 'Definido' if aec_valor > 0 else 'No definido'
        },
        'die': {
            'valor': 0.0,  # Derechos de Importación Específicos - generalmente 0 para productos comunes
            'fuente': fuente_datos,
            'estado': 'No definido'
        },
        'te': {
            'valor': te_valor,
            'fuente': fuente_datos,
            'estado': 'Definido' if te_valor > 0 else 'No definido'
        },
        'intervenciones': {
            'valor': intervenciones_valor,
            'fuente': fuente_datos,
            'estado': 'Sin restricciones' if intervenciones_valor == "Sin intervenciones" else 'Con restricciones'
        }
        # REMOVIDO: DE y RE porque son de exportación, no importación
    }
    
    # Debug log para verificar que los datos se están extrayendo correctamente
    debug_log("✅ Impuestos oficiales extraídos (solo importación)", {
        "aec_extraido": aec_valor,
        "te_extraido": te_valor,
        "intervenciones_count": len(intervenciones_unicas),
        "fuente_datos": fuente_datos,
        "match_exacto": is_official_data,
        "tratamiento_disponible": bool(tratamiento),
        "ncm_official_info_disponible": bool(ncm_official_info),
        "nota": "DE y RE excluidos (son de exportación)"
    }, level="SUCCESS")
    
    return taxes

def _calculate_full_landed_cost(price: float, result_session: dict) -> float:
    """Calcula el landed cost completo para un precio FOB/CIF dado, usando la configuración de la sesión."""
    if not price or price <= 0:
        return 0.0
    
    ncm_result = result_session.get('ncm_result', {})
    derechos_importacion_pct = _get_duties_from_ncm_result(ncm_result)
    
    try:
        tax_result = calcular_impuestos_importacion(
            cif_value=price,
            tipo_importador=result_session['configuracion'].get('tipo_importador', 'responsable_inscripto'),
            destino=result_session['configuracion'].get('destino_importacion', 'reventa'),
            origen="extrazona",
            tipo_dolar=result_session['configuracion'].get('tipo_dolar', 'oficial'),
            provincia=result_session['configuracion'].get('provincia', 'CABA'),
            derechos_importacion_pct=derechos_importacion_pct
        )
        
        # Usar el costo de flete unitario del resultado si está disponible
        if 'costo_flete_usd' in result_session:
            flete_costo = result_session['costo_flete_usd']
        else:
            # Fallback: estimación simple
            flete_costo = price * 0.15
            
        honorarios_despachante = price * 0.02
        
        return price + float(tax_result.total_impuestos) + flete_costo + honorarios_despachante
    except Exception as e:
        debug_log(f"Error calculando landed cost para display: {e}", level="ERROR")
        return 0.0

def clear_debug_data():
    """Limpiar todos los datos de debug"""
    st.session_state.debug_logs = []
    st.session_state.api_responses = {}
    st.session_state.console_output = []
    st.session_state.flow_steps = []
    st.session_state.current_step = None

def render_debug_tab():
    """Renderizar la tab de debug completa"""
    st.header("🔍 Debug & Flow Analysis")
    
    # Controles de debug
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🗑️ Limpiar Logs", use_container_width=True):
            clear_debug_data()
            st.rerun()
    
    with col2:
        download_logs = st.button("💾 Descargar Logs", use_container_width=True)
    
    with col3:
        auto_refresh = st.checkbox("🔄 Auto-refresh", value=False)
    
    if download_logs:
        log_data = {
            "debug_logs": st.session_state.debug_logs,
            "api_responses": st.session_state.api_responses,
            "flow_steps": st.session_state.flow_steps,
            "console_output": st.session_state.console_output
        }
        
        st.download_button(
            label="📥 Descargar Debug JSON",
            data=json.dumps(log_data, indent=2, ensure_ascii=False, default=str),
            file_name=f"debug_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json"
        )
    
    # Crear tabs secundarias para different tipos de debug
    debug_tab1, debug_tab2, debug_tab3, debug_tab4 = st.tabs([
        "📊 Flow Steps", "🔧 Console Output", "🌐 API Responses", "📝 Debug Logs"
    ])
    
    with debug_tab1:
        st.subheader("Flujo de Datos Completo")
        if st.session_state.flow_steps:
            for step in st.session_state.flow_steps:
                status_color = {
                    "STARTED": "🟡",
                    "SUCCESS": "🟢", 
                    "ERROR": "🔴",
                    "WARNING": "🟠"
                }.get(step["status"], "⚪")
                
                st.markdown(f"""
                <div class="content-box">
                    <strong>{status_color} {step['step_name']}</strong><br>
                    <small>Status: {step['status']} | Time: {step['timestamp']}</small>
                </div>
                """, unsafe_allow_html=True)
                
                if step['data']:
                    with st.expander(f"📄 Datos de {step['step_name']}", expanded=False):
                        st.json(step['data'])
        else:
            st.info("No hay pasos del flujo registrados aún.")
    
    with debug_tab2:
        st.subheader("Output de Consola")
        if st.session_state.console_output:
            console_text = "\n".join(st.session_state.console_output)
            st.markdown(f"""
            <div class="debug-log">
                <pre>{console_text}</pre>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("No hay output de consola disponible.")
    
    with debug_tab3:
        st.subheader("Respuestas de APIs")
        if st.session_state.api_responses:
            for key, api_call in st.session_state.api_responses.items():
                status_icon = "✅" if api_call['success'] else "❌"
                
                with st.expander(f"{status_icon} {api_call['api_name']} - {api_call['timestamp']}", expanded=False):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown("**📤 Request:**")
                        st.markdown(f"""
                        <div class="api-response">
                            <pre>{json.dumps(api_call['request'], indent=2, ensure_ascii=False, default=str)}</pre>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    with col2:
                        st.markdown("**📥 Response:**")
                        st.markdown(f"""
                        <div class="api-response">
                            <pre>{json.dumps(api_call['response'], indent=2, ensure_ascii=False, default=str)}</pre>
                        </div>
                        """, unsafe_allow_html=True)
        else:
            st.info("No hay llamadas a APIs registradas aún.")
    
    with debug_tab4:
        st.subheader("Logs Detallados")
        if st.session_state.debug_logs:
            # Filtros
            level_filter = st.selectbox(
                "Filtrar por nivel:",
                ["TODOS"] + list(set([log['level'] for log in st.session_state.debug_logs]))
            )
            
            filtered_logs = st.session_state.debug_logs
            if level_filter != "TODOS":
                filtered_logs = [log for log in st.session_state.debug_logs if log['level'] == level_filter]
            
            for log in filtered_logs[-20:]:  # Últimos 20 logs
                level_color = {
                    "INFO": "info-card",
                    "ERROR": "status-error",
                    "SUCCESS": "status-success",
                    "WARNING": "status-warning",
                    "FLOW": "status-info"
                }.get(log['level'], "content-box")
                
                st.markdown(f"""
                <div class="{level_color}">
                    <strong>[{log['timestamp']}] {log['level']}: {log['message']}</strong>
                    {f"<br><small>Step: {log['step']}</small>" if log['step'] else ""}
                </div>
                """, unsafe_allow_html=True)
                
                if log['data']:
                    with st.expander("📄 Datos del log", expanded=False):
                        st.json(log['data'])
        else:
            st.info("No hay logs de debug disponibles.")
    
    if auto_refresh:
        time_module.sleep(2)
        st.rerun()

def render_editable_product_form():
    """Renderiza el formulario para ingresar/editar datos del producto."""
    st.markdown("#### 📝 Datos del Producto (Editables)")
    st.caption("Modifica los datos extraídos o ingrésalos manualmente. Estos valores se usarán para el cálculo final.")

    pde = st.session_state.product_data_editable

    pde['title'] = st.text_input("Título del Producto", value=pde.get('title', ''))
    pde['image_url'] = st.text_input("URL de la Imagen (para clasificación)", value=pde.get('image_url', ''))

    st.markdown("##### Detalles Adicionales (para IA)")
    col1, col2 = st.columns(2)
    pde['brand_name'] = col1.text_input("Marca", value=pde.get('brand_name', ''))
    pde['place_of_origin'] = col2.text_input("País de Origen", value=pde.get('place_of_origin', ''))
    pde['categories'] = st.text_input("Categorías (separadas por coma)", value=pde.get('categories', ''))
    pde['properties_text'] = st.text_area(
        "Propiedades Adicionales (formato: clave:valor, una por línea)",
        value=pde.get('properties_text', ''),
        height=100,
        help="Ejemplo:\nMaterial: Acero Inoxidable\nColor: Rojo\nCapacidad: 500ml"
    )

    st.markdown("##### Precios por Cantidad")
    # Asegurarse que el dataframe exista y tenga el formato correcto
    if not isinstance(pde.get('pricing_df'), pd.DataFrame) or pde['pricing_df'].empty:
        pde['pricing_df'] = pd.DataFrame([{"min_quantity": 1, "price_usd": 10.0}])

    pde['pricing_df'] = st.data_editor(
        pde['pricing_df'],
        num_rows="dynamic",
        column_config={
            "min_quantity": st.column_config.NumberColumn("Cantidad Mínima", min_value=1, required=True),
            "price_usd": st.column_config.NumberColumn(
                "Precio Unitario (USD)",
                min_value=0.01,
                format="$%.2f",
                required=True
            )
        },
        key="pricing_editor"
    )

    st.markdown("##### Dimensiones y Peso")
    col1, col2, col3, col4 = st.columns(4)
    dims = pde.get('dimensions_cm', {"length": 0.0, "width": 0.0, "height": 0.0})
    dims['length'] = col1.number_input("Largo (cm)", value=dims.get('length', 0.0), min_value=0.0, format="%.2f")
    dims['width'] = col2.number_input("Ancho (cm)", value=dims.get('width', 0.0), min_value=0.0, format="%.2f")
    dims['height'] = col3.number_input("Alto (cm)", value=dims.get('height', 0.0), min_value=0.0, format="%.2f")
    pde['dimensions_cm'] = dims
    pde['weight_kg'] = col4.number_input("Peso (kg)", value=pde.get('weight_kg', 0.0), min_value=0.0, format="%.3f")

    st.markdown("##### Embalaje y Cantidad")
    
    # Determinar MOQ para el input de cantidad
    moq = 1
    if isinstance(pde.get('pricing_df'), pd.DataFrame) and not pde['pricing_df'].empty:
        # Asegurarse que la columna existe y no está vacía antes de llamar a .min()
        if 'min_quantity' in pde['pricing_df'].columns and not pde['pricing_df']['min_quantity'].dropna().empty:
            moq = int(pde['pricing_df']['min_quantity'].min())

    # Ajuste para evitar el error StreamlitValueBelowMinError.
    # Si la cantidad de importación actual es menor que el nuevo MOQ (porque el usuario editó la tabla de precios),
    # se actualiza automáticamente la cantidad de importación para que coincida con el MOQ.
    if pde.get('import_quantity', moq) < moq:
        pde['import_quantity'] = moq

    pde['import_quantity'] = st.number_input(
        "Cantidad de Unidades a Importar", 
        value=int(pde.get('import_quantity', moq)), 
        min_value=moq, 
        step=1,
        key="import_quantity_input"
    )
    st.caption(f"El pedido mínimo (MOQ) para este producto es de {moq} unidades.")
    
    # Cálculos de peso y volumen para el envío
    peso_unitario = pde.get('weight_kg', 0.0)
    dims = pde.get('dimensions_cm', {"length": 0.0, "width": 0.0, "height": 0.0})
    cantidad = pde.get('import_quantity', 1)
    
    # Calcular peso total
    peso_total_kg = peso_unitario * cantidad
    
    # Calcular volumen y peso volumétrico
    if all(d > 0 for d in dims.values()):
        volumen_unitario_cbm = (dims['length'] * dims['width'] * dims['height']) / 1_000_000
        volumen_total_cbm = volumen_unitario_cbm * cantidad
        # Factor estándar para peso volumétrico aéreo: 167 kg/m³
        peso_volumetrico_kg = volumen_total_cbm * 167
    else:
        volumen_total_cbm = 0
        peso_volumetrico_kg = 0
    
    # Mostrar cálculos de peso y volumen
    col1, col2 = st.columns(2)
    with col1:
        st.metric(
            label="📦 Peso Total", 
            value=f"{peso_total_kg:.2f} kg",
            help=f"Peso físico total: {peso_unitario:.2f} kg × {cantidad} unidades"
        )
    
    with col2:
        st.metric(
            label="📐 Peso Volumétrico", 
            value=f"{peso_volumetrico_kg:.2f} kg" if peso_volumetrico_kg > 0 else "No calculable",
            help=f"Peso volumétrico total: {volumen_total_cbm:.6f} m³ × 167 kg/m³ (factor aéreo estándar)"
        )
    
    # Mostrar información adicional del envío
    if volumen_total_cbm > 0:
        col3, col4 = st.columns(2)
        with col3:
            st.metric(
                label="📏 Volumen Total",
                value=f"{volumen_total_cbm:.6f} m³",
                help=f"Volumen total del envío: {dims['length']:.1f} × {dims['width']:.1f} × {dims['height']:.1f} cm × {cantidad} unidades"
            )
        
        with col4:
            # Determinar qué peso se usará para el flete aéreo (el mayor entre físico y volumétrico)
            peso_facturable = max(peso_total_kg, peso_volumetrico_kg)
            st.metric(
                label="⚖️ Peso Facturable",
                value=f"{peso_facturable:.2f} kg",
                help="Para flete aéreo se cobra por el mayor entre peso real y peso volumétrico"
            )
        
        # Agregar información contextual
        if peso_volumetrico_kg > peso_total_kg:
            st.info(f"💡 **Importante:** El peso volumétrico ({peso_volumetrico_kg:.2f} kg) es mayor al peso físico ({peso_total_kg:.2f} kg). Para flete aéreo se cobrará por el peso volumétrico.")
        else:
            st.info(f"💡 **Información:** El peso físico ({peso_total_kg:.2f} kg) es mayor al peso volumétrico ({peso_volumetrico_kg:.2f} kg). Para flete aéreo se cobrará por el peso físico.")
    else:
        st.warning("⚠️ No se puede calcular el peso volumétrico sin dimensiones válidas del producto.")

    st.markdown("##### 📍 Direcciones de Envío")
    st.caption("Configura las direcciones de origen y destino para el cálculo de flete.")
    st.info("ℹ️ **Nota:** Solo necesitas completar código postal, ciudad y país. Por defecto: China → Argentina.")
    
    with st.expander("🏭 Dirección de Origen (Donde se envía)", expanded=False):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            origin_country = st.selectbox("País de Origen", ["CN", "US", "DE", "JP", "KR"], 
                                        index=0, key="main_origin_country",
                                        help="CN=China, US=USA, DE=Alemania, JP=Japón, KR=Corea")
        
        with col2:
            if origin_country == "CN":
                origin_city = st.text_input("Ciudad", value="SHENZHEN", key="main_origin_city")
            else:
                origin_city = st.text_input("Ciudad", value="CITY NAME", key="main_origin_city_generic")
        
        with col3:
            if origin_country == "CN":
                origin_postal = st.text_input("Código Postal", value="518000", key="main_origin_postal")
            else:
                origin_postal = st.text_input("Código Postal", value="00000", key="main_origin_postal_generic")
    
    with st.expander("🏠 Dirección de Destino (Donde llega)", expanded=False):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            dest_country = st.selectbox("País de Destino", ["AR", "US", "BR", "CL", "UY"], 
                                      index=0, key="main_dest_country",
                                      help="AR=Argentina, US=USA, BR=Brasil, CL=Chile, UY=Uruguay")
        
        with col2:
            if dest_country == "AR":
                dest_city = st.text_input("Ciudad", value="CAPITAL FEDERAL", key="main_dest_city")
            else:
                dest_city = st.text_input("Ciudad", value="CITY NAME", key="main_dest_city_generic")
        
        with col3:
            if dest_country == "AR":
                dest_postal = st.text_input("Código Postal", value="1440", key="main_dest_postal", 
                                          help="Código que funciona con DHL test")
            else:
                dest_postal = st.text_input("Código Postal", value="00000", key="main_dest_postal_generic")
    
    # Construir objetos de direcciones simplificados usando el formato que funciona
    origin_details = {
        "postalCode": origin_postal,
        "cityName": origin_city,
        "countryCode": origin_country,
        "addressLine1": "addres1",  # Formato compatible con DHL test
        "addressLine2": "addres2",
        "addressLine3": "addres3"
    }
    
    destination_details = {
        "postalCode": dest_postal,
        "cityName": dest_city,
        "countryCode": dest_country,
        "addressLine1": "addres1",  # Formato compatible con DHL test
        "addressLine2": "addres2",
        "addressLine3": "addres3"
    }
    
    # Actualizar session state con las nuevas direcciones
    st.session_state.origin_details = origin_details
    st.session_state.destination_details = destination_details
    
    st.markdown("##### 📅 Fecha de Envío")
    st.caption("Especifica cuándo planeas enviar el producto. Si una fecha no funciona, el sistema probará fechas cercanas automáticamente.")
    
    col1, col2 = st.columns(2)
    with col1:
        # Fecha por defecto: 3 días desde hoy
        default_date = datetime.now().date() + timedelta(days=3)
        shipping_date = st.date_input(
            "Fecha de Envío Planeada",
            value=default_date,
            min_value=datetime.now().date() + timedelta(days=1),  # Mínimo mañana
            max_value=datetime.now().date() + timedelta(days=30), # Máximo 30 días
            key="shipping_date_input",
            help="Fecha en que planeas enviar el producto desde origen"
        )
    
    with col2:
        shipping_time = st.time_input(
            "Hora de Envío Planeada",
            value=time(14, 0),  # 2:00 PM por defecto
            key="shipping_time_input",
            help="Hora estimada de pickup/envío"
        )
    
    # Combinar fecha y hora y guardar en session state
    shipping_datetime = datetime.combine(shipping_date, shipping_time)
    st.session_state.planned_shipping_datetime = shipping_datetime
    
    st.info(f"📅 Fecha/hora planeada: {shipping_datetime.strftime('%d/%m/%Y a las %H:%M')}")

def fetch_and_populate_from_url(url):
    """Extrae datos de Alibaba y los carga en el formulario editable."""
    log_flow_step("FETCH_FROM_URL", "STARTED", {"url": url})
    clear_debug_data()
    st.session_state.result = None

    with st.spinner("🔄 Extrayendo datos del producto desde Alibaba..."):
        try:
            product = scrape_single_alibaba_product(url, API_KEYS["APIFY_API_KEY"])
            if not product:
                st.error("❌ No se pudieron extraer datos del producto. Verifica la URL o intenta de nuevo.")
                log_flow_step("FETCH_FROM_URL", "ERROR", {"error": "No product data found"})
                return
            st.session_state.scraped_product = product
            log_flow_step("EXTRACCION_ALIBABA", "SUCCESS", {"title": product.title})
        except Exception as e:
            st.error(f"❌ Error extrayendo datos de Alibaba: {e}")
            log_flow_step("FETCH_FROM_URL", "ERROR", {"error": str(e)})
            return

    with st.spinner("🧠 Analizando dimensiones y peso (datos reales + IA)..."):
        try:
            estimator = ProductShippingEstimator()
            product_dict = product.raw_data if hasattr(product, 'raw_data') else {}
            
            # Usar datos reales cuando estén disponibles, IA como fallback
            if not product_dict:
                debug_log("No raw_data found, reconstructing for estimation", level="WARNING")
                product_dict = {
                    'subject': product.title,
                    'categories': product.categories,
                    'mediaItems': [{'type': 'image', 'imageUrl': {'big': url}} for url in product.images],
                    'productHtmlDescription': getattr(product, 'html_description', ''),
                    'productBasicProperties': getattr(product, 'properties_list', [])
                }
            
            # Usar lógica inteligente: datos reales primero, IA como fallback
            shipping_info = estimator.get_shipping_details(product_dict)
            st.session_state.shipping_info = shipping_info
            log_flow_step("ESTIMACION_DIMENSIONES", "SUCCESS", shipping_info)
            
            # Mostrar método usado
            method = shipping_info.get('method', 'unknown')
            if method == 'extracted_validated':
                debug_log("✅ Usando datos reales extraídos de Alibaba", shipping_info, level="SUCCESS")
                st.success("📏 Dimensiones y peso extraídos desde datos reales de Alibaba")
            elif method == 'llm_estimated':
                debug_log("🧠 Usando estimación por IA (datos extraídos insuficientes)", shipping_info, level="INFO")
                st.info("🤖 Dimensiones y peso estimados por IA (datos del producto insuficientes)")
            else:
                debug_log(f"⚠️ Método de estimación: {method}", shipping_info, level="WARNING")
            
        except Exception as e:
            st.warning(f"⚠️ No se pudieron estimar las dimensiones: {e}. Se usarán valores por defecto.")
            st.session_state.shipping_info = {"method": "failed_fallback"}
            log_flow_step("ESTIMACION_DIMENSIONES", "WARNING", {"error": str(e)})

    # Poblar el formulario editable
    pde = st.session_state.product_data_editable
    shipping_info = st.session_state.shipping_info
    
    pde['title'] = product.title
    pde['product_url'] = product.url
    
    selected_image = validate_and_select_best_image(product.images if product.images else [])
    pde['image_url'] = selected_image.get('selected_url', '')

    # Poblar detalles adicionales
    pde['brand_name'] = getattr(product, 'brand_name', '')
    pde['place_of_origin'] = product.place_of_origin or ''
    pde['categories'] = ", ".join(product.categories) if product.categories else ""
    
    properties = getattr(product, 'properties', {})
    properties_text = "\n".join([f"{k}: {v}" for k, v in properties.items()])
    pde['properties_text'] = properties_text

    # Poblar precios
    pricing_data = []
    if product.pricing and hasattr(product.pricing, 'ladder_prices') and product.pricing.ladder_prices:
        for tier in product.pricing.ladder_prices:
            pricing_data.append({"min_quantity": int(tier.get('min', 1)), "price_usd": float(tier.get('price', 0.0))})
    elif product.price_low > 0:
        pricing_data.append({"min_quantity": int(product.moq or 1), "price_usd": float(product.price_low)})
    
    if pricing_data:
        pde['pricing_df'] = pd.DataFrame(pricing_data)
    else:
        pde['pricing_df'] = pd.DataFrame([{"min_quantity": 1, "price_usd": 0.0}])

    # Poblar dimensiones y peso desde la estimación - SIEMPRE usar estimaciones IA
    dims = shipping_info.get('dimensions_cm', {})
    pde['dimensions_cm'] = {
        "length": dims.get('length_cm', 0.0),
        "width": dims.get('width_cm', 0.0),
        "height": dims.get('height_cm', 0.0)
    }
    pde['weight_kg'] = shipping_info.get('weight_kg', 0.0)
    pde['import_quantity'] = int(product.moq or 1)

    st.session_state.data_input_step_completed = True
    st.success("✅ Datos extraídos y procesados. Revisa y ajusta los valores si es necesario antes de calcular.")
    st.rerun()

def render_main_calculator():
    """Renderizar la calculadora principal con el nuevo flujo de entrada."""
    
    # Configuración en sidebar
    with st.sidebar:
        st.markdown("### ⚙️ Configuración del Cálculo")
        st.session_state.debug_mode = st.checkbox("🔧 Debug", value=True)
        
        # Nueva configuración DHL
        st.markdown("#### 🚢 Configuración de Flete DHL")
        use_real_dhl = st.checkbox("🌐 Usar DHL Real (API)", value=True, help="Si está marcado, usa la API real de DHL. Si no, usa estimaciones.")
        dhl_test_mode = st.checkbox("🧪 Modo Test DHL", value=True, help="Usar ambiente de test de DHL (recomendado)")
        

        
        # Actualizar configuración del servicio DHL si cambió
        if ('dhl_use_real' not in st.session_state or 
            st.session_state.dhl_use_real != use_real_dhl or
            getattr(st.session_state.dhl_service, 'test_mode', None) != dhl_test_mode):
            
            st.session_state.dhl_use_real = use_real_dhl
            st.session_state.dhl_service = DHLFreightService(
                test_mode=dhl_test_mode,
                use_dhl_real=use_real_dhl,
                fallback_rates_file=FREIGHT_RATES_FILE,
                debug_callback=debug_log  # Conectar el debug
            )
        
        st.divider()
        
        tipo_importador = st.selectbox("Importador:", ["responsable_inscripto", "no_inscripto", "monotributista"], key="tipo_importador_sb")
        destino_importacion = st.selectbox("Destino:", ["reventa", "uso_propio", "bien_capital"], key="destino_sb")
        provincia = st.selectbox("Provincia:", ["CABA", "BUENOS_AIRES", "CORDOBA", "SANTA_FE"], key="provincia_sb")
        tipo_flete = st.selectbox("Tipo de Flete:", ["Courier (Aéreo)", "Marítimo (Contenedor)"], key="tipo_flete_sb")
        cotizacion_dolar = st.number_input("Cotización USD/ARS", value=1746.96, format="%.2f", key="cotizacion_sb")

    st.markdown("# 📊 Calculadora de Landing Cost")

    # --- LÓGICA DE RE-CÁLCULO AUTOMÁTICO ---
    # Si ya hay un resultado, y alguna configuración de la sidebar cambia, recalcular.
    if 'result' in st.session_state and st.session_state.result:
        # Capturar configuración actual de la sidebar
        current_config = {
            "tipo_importador": tipo_importador,
            "destino_importacion": destino_importacion,
            "provincia": provincia,
            "tipo_flete": tipo_flete,
            "cotizacion_dolar": cotizacion_dolar,
        }
        
        # Capturar configuración con la que se calculó el resultado
        previous_config = st.session_state.result['configuracion']

        # Comparar si hay diferencias
        config_changed = False
        for key, current_value in current_config.items():
            previous_value = previous_config.get(key)
            # Usar una pequeña tolerancia para la comparación de floats (cotización)
            if isinstance(current_value, float):
                if not (previous_value and abs(current_value - previous_value) < 1e-9):
                    config_changed = True
                    break
            elif current_value != previous_value:
                config_changed = True
                break
                
        if config_changed:
            st.info("🔄 Detectamos un cambio en la configuración. Recalculando costos...")
            time_module.sleep(1) # Pequeña pausa para que el usuario vea el mensaje
            # Llamar a la función de cálculo con los nuevos parámetros.
            # Los datos del producto ya están en st.session_state.product_data_editable
            execute_landed_cost_calculation(
                tipo_importador, destino_importacion, provincia, cotizacion_dolar, tipo_flete
            )
            # La función de cálculo ya hace st.rerun(), por lo que la ejecución se detendrá aquí.

    # Selector de modo de entrada
    st.session_state.entry_mode = st.radio(
        "Elige el modo de entrada:",
        ["Análisis desde URL", "Ingreso Manual"],
        horizontal=True,
        key="entry_mode_selector"
    )

    if st.session_state.entry_mode == "Análisis desde URL":
        url_alibaba = st.text_input(
            "URL del producto:",
            placeholder="https://www.alibaba.com/product-detail/...",
            key="url_input"
        )
        if st.button("🔍 Extraer Datos", type="primary", use_container_width=True):
            if not url_alibaba or not url_alibaba.startswith("https://www.alibaba.com/product-detail/"):
                st.error("❌ Ingresa una URL de Alibaba válida.")
            else:
                fetch_and_populate_from_url(url_alibaba)
    else: # Modo Manual
        if st.button("📝 Cargar Formulario Manual", use_container_width=True):
            st.session_state.data_input_step_completed = True
            st.session_state.result = None
            st.session_state.scraped_product = None # Asegurar limpieza
            # Limpiar datos previos para un formulario limpio
            st.session_state.product_data_editable = {
                "title": "Producto Manual",
                "pricing_df": pd.DataFrame([{"min_quantity": 1, "price_usd": 10.0}]),
                "dimensions_cm": {"length": 10.0, "width": 10.0, "height": 10.0},
                "weight_kg": 1.0,
                "import_quantity": 1,
                "image_url": "", 
                "product_url": "",
                "brand_name": "",
                "place_of_origin": "",
                "categories": "",
                "properties_text": ""
            }
            st.rerun()

    # Si los datos están listos (desde URL o manual), mostrar el formulario y el botón de cálculo
    if st.session_state.data_input_step_completed:
        with st.container(border=True):
            render_editable_product_form()
        
        st.markdown("---")
        if st.button("🧮 Calcular Landed Cost", type="primary", use_container_width=True):
            # Validar que haya datos en el formulario
            pde = st.session_state.product_data_editable
            if not pde['title'] or pde['pricing_df'].empty or pde['pricing_df']['price_usd'].iloc[0] <= 0:
                st.error("❌ Completa al menos el título y un precio válido para calcular.")
            else:
                execute_landed_cost_calculation(
                    tipo_importador, destino_importacion, provincia, cotizacion_dolar, tipo_flete
                )
    
    # Mostrar tabla de resultados si existen
    if 'result' in st.session_state and st.session_state.result:
        # Botón para reiniciar y hacer un nuevo cálculo
        if st.button("🔄 Empezar de Nuevo"):
            st.session_state.result = None
            st.session_state.data_input_step_completed = False
            st.session_state.scraped_product = None
            st.rerun()
        show_calculator_table()

def main():
    """Función principal con tabs"""
    if not MODULES_AVAILABLE:
        st.error("⚠️ Error: No se pudieron cargar los módulos necesarios. Verifica la instalación.")
        return
    
    initialize_session_state()
    
    # Header principal minimalista
    st.markdown("""
    <div class="main-header">
        <h1>🌎 AI Comercio Exterior</h1>
        <p>Calculadora de costos de importación desde Alibaba</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Crear tabs principales
    tab1, tab2, tab3 = st.tabs(["📊 Calculadora Principal", "🔍 Debug & Análisis", "📊 Google Sheets Test"])
    
    with tab1:
        render_main_calculator()
    
    with tab2:
        render_debug_tab()
    
    with tab3:
        render_google_sheets_test_tab()

def validate_and_select_best_image(images_list, logger=None):
    """
    Valida y selecciona la mejor imagen de una lista para clasificación NCM
    
    Args:
        images_list: Lista de URLs de imágenes
        logger: Logger opcional para debug
        
    Returns:
        Dict con información de la imagen seleccionada
    """
    if not images_list:
        debug_log("No hay imágenes disponibles para validar", level="WARNING")
        return {
            "selected_url": None,
            "method": "no_images_available",
            "score": 0,
            "validation_results": []
        }
    
    validation_results = []
    best_image = None
    best_score = -1
    
    debug_log(f"Iniciando validación de {len(images_list)} imágenes", level="INFO")
    
    # Analizar cada imagen (máximo 5 para eficiencia)
    for idx, img_url in enumerate(images_list[:5]):
        if not img_url:
            continue
            
        result = {
            "index": idx,
            "url": img_url,
            "url_preview": img_url[:80] + "..." if len(img_url) > 80 else img_url,
            "score": 0,
            "reasons": []
        }
        
        try:
            # Análisis de URL
            parsed_url = urlparse(img_url)
            url_lower = img_url.lower()
            
            # Score base por posición (primeras imágenes suelen ser mejores)
            if idx == 0:
                result["score"] += 15
                result["reasons"].append("primera_imagen")
            elif idx == 1:
                result["score"] += 10
                result["reasons"].append("segunda_imagen")
            elif idx == 2:
                result["score"] += 5
                result["reasons"].append("tercera_imagen")
            
            # Penalizar thumbnails y imágenes pequeñas
            if any(term in url_lower for term in ['thumb', 'small', 'tiny', 'mini']):
                result["score"] -= 15
                result["reasons"].append("thumbnail_detected")
            
            # Premiar imágenes grandes y de calidad
            if any(term in url_lower for term in ['big', 'large', 'huge', 'full']):
                result["score"] += 20
                result["reasons"].append("large_image")
            
            if any(term in url_lower for term in ['main', 'primary', 'hero', 'featured']):
                result["score"] += 25
                result["reasons"].append("main_image")
            
            if any(term in url_lower for term in ['hd', 'quality', 'detail']):
                result["score"] += 10
                result["reasons"].append("quality_indicator")
            
            # Formato de archivo
            if '.jpg' in url_lower or '.jpeg' in url_lower:
                result["score"] += 5
                result["reasons"].append("jpeg_format")
            elif '.png' in url_lower:
                result["score"] += 3
                result["reasons"].append("png_format")
            elif '.webp' in url_lower:
                result["score"] += 2
                result["reasons"].append("webp_format")
            
            # Verificar si la URL parece válida
            if parsed_url.scheme in ['http', 'https'] and parsed_url.netloc:
                result["score"] += 5
                result["reasons"].append("valid_url_structure")
            else:
                result["score"] -= 10
                result["reasons"].append("invalid_url_structure")
            
            # Verificar accesibilidad de la imagen (con timeout corto)
            try:
                response = requests.head(img_url, timeout=3)
                if response.status_code == 200:
                    result["score"] += 10
                    result["reasons"].append("accessible")
                    
                    # Verificar Content-Type si está disponible
                    content_type = response.headers.get('content-type', '').lower()
                    if 'image' in content_type:
                        result["score"] += 5
                        result["reasons"].append("valid_content_type")
                        
                        # Premiar ciertos tipos de imagen
                        if 'jpeg' in content_type:
                            result["score"] += 3
                        elif 'png' in content_type:
                            result["score"] += 2
                else:
                    result["score"] -= 20
                    result["reasons"].append(f"http_error_{response.status_code}")
                    
            except requests.exceptions.RequestException as e:
                result["score"] -= 10
                result["reasons"].append(f"connection_error")
                debug_log(f"Error validando imagen {idx}: {str(e)}", level="WARNING")
            
            # Detectar posibles imágenes de logo o watermark
            if any(term in url_lower for term in ['logo', 'watermark', 'brand', 'stamp']):
                result["score"] -= 5
                result["reasons"].append("possible_logo")
            
        except Exception as e:
            result["score"] = -100
            result["reasons"] = [f"validation_error: {str(e)}"]
            debug_log(f"Error crítico validando imagen {idx}: {str(e)}", level="ERROR")
        
        validation_results.append(result)
        
        # Actualizar mejor imagen si este score es mayor
        if result["score"] > best_score:
            best_score = result["score"]
            best_image = result
    
    # Determinar método de selección
    if not best_image:
        method = "no_valid_images"
        selected_url = None
    elif len(images_list) == 1:
        method = "single_image"
        selected_url = best_image["url"]
    else:
        method = f"best_of_{len(validation_results)}_score_{best_score}"
        selected_url = best_image["url"]
    
    debug_log("Validación de imágenes completada", {
        "total_images": len(images_list),
        "analyzed_images": len(validation_results),
        "best_score": best_score,
        "method": method,
        "selected_index": best_image["index"] if best_image else None
    }, level="SUCCESS")
    
    return {
        "selected_url": selected_url,
        "method": method,
        "score": best_score,
        "best_image_info": best_image,
        "validation_results": validation_results,
        "total_analyzed": len(validation_results)
    }

def create_enhanced_description(product):
    """
    Crear descripción mejorada para clasificación NCM
    
    Args:
        product: Producto extraído de Alibaba
        
    Returns:
        String con descripción mejorada
    """
    description_parts = [product.title]
    
    # Agregar categorías si están disponibles
    if product.categories:
        description_parts.append(f"Categorías: {', '.join(product.categories)}")
    
    # Agregar origen si está disponible
    if product.place_of_origin:
        description_parts.append(f"Origen: {product.place_of_origin}")
        
    # Agregar marca si está disponible
    if hasattr(product, 'brand_name') and product.brand_name:
        description_parts.append(f"Marca: {product.brand_name}")
        
    # Agregar rango de precios para contexto
    if product.price_low > 0 and product.price_high > 0:
        description_parts.append(f"Rango de precio: ${product.price_low} - ${product.price_high}")
        
    # Agregar MOQ para contexto comercial
    if product.moq:
        description_parts.append(f"MOQ: {product.moq}")
        
    # Agregar propiedades relevantes si están disponibles
    if hasattr(product, 'properties') and product.properties:
        relevant_props = []
        for key, value in product.properties.items():
            # Filtrar propiedades relevantes para clasificación
            key_lower = key.lower()
            if any(term in key_lower for term in ['material', 'size', 'weight', 'color', 'type', 'model', 'specification', 'feature', 'capacity', 'function']):
                relevant_props.append(f"{key}: {value}")
        
        if relevant_props:
            description_parts.append(f"Propiedades: {'; '.join(relevant_props[:5])}")  # Limitar a 5 propiedades
    
    # Combinar toda la descripción
    enhanced_description = " | ".join(description_parts)
    
    debug_log("Descripción mejorada generada", {
        "original_length": len(product.title) if product and product.title else 0,
        "enhanced_length": len(enhanced_description),
        "components": len(description_parts)
    }, level="SUCCESS")
    
    return enhanced_description

def execute_landed_cost_calculation(tipo_importador, destino_importacion, provincia, cotizacion_dolar, tipo_flete):
    """Ejecuta el análisis de costos usando los datos del formulario editable."""
    
    editable_data = st.session_state.product_data_editable
    
    # Obtener direcciones de envío del session state (configuradas en el sidebar)
    origin_details = st.session_state.get('origin_details')
    destination_details = st.session_state.get('destination_details')
    
    log_flow_step("INICIO_ANALISIS", "STARTED", {
        "configuracion": {
            "tipo_importador": tipo_importador, "destino_importacion": destino_importacion,
            "provincia": provincia,
            "cotizacion_dolar": cotizacion_dolar, "tipo_flete": tipo_flete
        },
        "fuente_datos": st.session_state.entry_mode
    })
    
    try:
        # Simular objeto 'product' para funciones existentes
        from collections import namedtuple
        ProductInfo = namedtuple('ProductInfo', [
            'title', 'images', 'pricing', 'url', 'categories', 'place_of_origin', 'brand_name', 'moq',
            'price_low', 'price_high', 'properties'
        ])
        PricingInfo = namedtuple('PricingInfo', ['ladder_prices'])
        
        pricing_df = editable_data['pricing_df']
        ladder_prices = []
        if isinstance(pricing_df, pd.DataFrame) and not pricing_df.empty:
            ladder_prices = [{"min": row['min_quantity'], "price": row['price_usd']} for _, row in pricing_df.iterrows()]
        
        # Parsear categorías y propiedades desde el formulario
        categories_list = [cat.strip() for cat in editable_data.get('categories', '').split(',') if cat.strip()]
        
        properties_dict = {}
        properties_text = editable_data.get('properties_text', '')
        if properties_text:
            for line in properties_text.split('\n'):
                if ':' in line:
                    parts = line.split(':', 1)
                    if len(parts) == 2 and parts[0].strip():
                        properties_dict[parts[0].strip()] = parts[1].strip()
        
        # Corrección: Usar datos del producto scrapeado solo si existe.
        # En modo manual, 'scraped_product' es None y causaría un error.
        scraped_product = st.session_state.scraped_product
        
        product_for_analysis = ProductInfo(
            title=editable_data['title'],
            images=[editable_data['image_url']] if editable_data['image_url'] else [],
            pricing=PricingInfo(ladder_prices=ladder_prices),
            url=editable_data.get('product_url', ''),
            categories=categories_list,
            place_of_origin=editable_data.get('place_of_origin', 'N/A'),
            brand_name=editable_data.get('brand_name', ''),
            moq=pricing_df['min_quantity'].min() if not pricing_df.empty else 1,
            price_low=pricing_df['price_usd'].min() if not pricing_df.empty else 0,
            price_high=pricing_df['price_usd'].max() if not pricing_df.empty else 0,
            properties=properties_dict
        )

        # Paso 1: Clasificar NCM con Integración Refinada (IA + Position Matcher)
        with st.spinner("🤖 Clasificando NCM con integración refinada (IA + Datos Oficiales)..."):
            log_flow_step("CLASIFICACION_NCM_INTEGRADA", "STARTED")
            ncm_result = {}
            try:
                enhanced_description = create_enhanced_description(product_for_analysis)
                
                # NUEVO: Usar clasificador oficial NCM actualizado
                ai_classifier = AINcmClassifier(API_KEYS.get("OPENAI_API_KEY"))
                
                integrated_result = asyncio.run(ai_classifier.classify_product(
                    description=enhanced_description,
                    image_url=editable_data['image_url']
                ))

                if integrated_result.get('error'):
                    raise ValueError(integrated_result.get('error', 'Error en clasificación NCM'))
                
                # El nuevo clasificador retorna directamente los datos estructurados
                # integrated_result ya contiene toda la información necesaria
                ncm_result = integrated_result
                
                # Logging detallado del proceso de clasificación NCM
                ai_ncm = ncm_result.get('ncm_completo', 'N/A')
                confianza = ncm_result.get('confianza', 'N/A')
                fuente_oficial = ncm_result.get('ncm_official_info', {}).get('source', 'N/A')
                
                log_flow_step("CLASIFICACION_NCM_OFICIAL", "SUCCESS", {
                    "ncm_completo": ai_ncm,
                    "confianza": confianza,
                    "fuente_oficial": fuente_oficial
                })
                
                # Extraer información de validación del resultado integrado
                final_ncm = ncm_result.get('ncm_completo', 'N/A')
                ncm_official_info = ncm_result.get('ncm_official_info', {})
                match_exacto = ncm_official_info.get('match_exacto', False)
                
                # Determinar tipo de validación
                if match_exacto:
                    validation_type = 'exacto'
                elif ncm_official_info.get('source'):
                    validation_type = 'aproximado'
                else:
                    validation_type = 'ia_solo'
                
                debug_log("✅ NCM clasificado con integración refinada", {
                    "ia_resultado": ai_ncm,
                    "validacion": validation_type,
                    "ncm_final": final_ncm,
                    "fuente": ncm_official_info.get('source', 'IA')
                }, level="SUCCESS")
                
                # Mostrar información del proceso en la UI
                was_refined = ncm_result.get('ncm_official_info', {}).get('was_refined', False)
                refinement_info = ncm_result.get('ncm_official_info', {}).get('refinement_info', {})
                
                if was_refined:
                    original_code = refinement_info.get('original_code', 'N/A')
                    total_options = refinement_info.get('total_options', 'N/A')
                    st.success(f"🎯 NCM refinado automáticamente: {original_code} → {final_ncm}")
                    st.info(f"💡 LLM evaluó {total_options} subcategorías y eligió la más específica")
                elif validation_type == 'exacto':
                    st.success(f"🎯 NCM {final_ncm} validado con datos oficiales (match exacto)")
                elif validation_type == 'aproximado':
                    confidence = ncm_result.get('confianza', 'Media')
                    st.info(f"📊 NCM {final_ncm} validado con base oficial ({confidence} confianza)")
                else:
                    st.info(f"🤖 NCM {final_ncm} clasificado por IA (sin validación oficial)")

            except Exception as e:
                st.error(f"❌ Error en clasificación NCM integrada: {e}")
                log_flow_step("CLASIFICACION_NCM_INTEGRADA", "ERROR", {"error": str(e)})
                return

        # Paso 2: Calcular impuestos
        with st.spinner("💰 Calculando impuestos..."):
            if pricing_df.empty or pricing_df['price_usd'].iloc[0] <= 0:
                st.error("❌ No hay un precio válido para calcular impuestos.")
                return

            precio_base = float(pricing_df['price_usd'].iloc[0]) # Usar el primer precio de la lista como base
            derechos_importacion_pct = _get_duties_from_ncm_result(ncm_result)
            
            try:
                tax_result = calcular_impuestos_importacion(
                    cif_value=precio_base,
                    tipo_importador=tipo_importador, destino=destino_importacion,
                    origen="extrazona", provincia=provincia,
                    derechos_importacion_pct=derechos_importacion_pct
                )
                log_flow_step("CALCULO_IMPUESTOS", "SUCCESS", {"total_impuestos": float(tax_result.total_impuestos)})
            except Exception as e:
                st.error(f"❌ Error calculando impuestos: {str(e)}")
                log_flow_step("CALCULO_IMPUESTOS", "ERROR", {"error": str(e)})
                return

        # Paso 3: Calcular Flete
        log_flow_step("CALCULO_FLETE", "STARTED", {"tipo_flete": tipo_flete})
        
        import_quantity = int(editable_data.get('import_quantity', 1))
        if import_quantity == 0: import_quantity = 1 # Evitar división por cero

        peso_unitario_kg = float(editable_data['weight_kg'])
        dims = editable_data['dimensions_cm']
        
        # Calcular pesos y volúmenes
        peso_total_kg = peso_unitario_kg * import_quantity
        
        # Calcular peso volumétrico y volumen
        volumen_unitario_cbm = 0
        peso_volumetrico_total_kg = 0
        if all(d > 0 for d in dims.values()):
            volumen_unitario_cbm = (dims['length'] * dims['width'] * dims['height']) / 1_000_000
            volumen_total_cbm = volumen_unitario_cbm * import_quantity
            peso_volumetrico_total_kg = volumen_total_cbm * 167  # Factor aéreo estándar
        else:
            volumen_total_cbm = 0
            
        # Para flete aéreo, usar el mayor entre peso físico y volumétrico
        peso_facturable_kg = max(peso_total_kg, peso_volumetrico_total_kg) if peso_volumetrico_total_kg > 0 else peso_total_kg

        costo_flete_total_usd = 0
        metodo_calculo = "Sin datos"
        
        if tipo_flete == "Courier (Aéreo)":
            # NUEVO: Usar servicio DHL integrado con fallbacks automáticos
            try:
                # Construir dimensiones para DHL
                dimensions_cm_dict = {
                    "length": dims.get('length', 25),
                    "width": dims.get('width', 35), 
                    "height": dims.get('height', 15)
                }
                
                # Calcular con servicio DHL integrado usando direcciones personalizadas
                dhl_result = st.session_state.dhl_service.calculate_freight_with_fallback(
                    weight_kg=peso_facturable_kg,
                    dimensions_cm=dimensions_cm_dict,
                    origin_details=origin_details,
                    destination_details=destination_details,
                    shipping_datetime=st.session_state.get('planned_shipping_datetime')
                )
                
                # Registrar la respuesta completa en la API responses
                if 'raw_response' in dhl_result:
                    log_api_call("DHL_API", dimensions_cm_dict, dhl_result['raw_response'], dhl_result['success'])
                
                # Extraer costos detallados si están disponibles
                insurance_cost = 0.0
                argentina_taxes = 0.0
                
                if 'cost_breakdown' in dhl_result:
                    cost_breakdown = dhl_result['cost_breakdown']
                    insurance_cost = cost_breakdown.get('insurance_cost', 0.0)
                    argentina_taxes = cost_breakdown.get('argentina_taxes', 0.0)
                    
                    debug_log(f"🛡️ Seguro incluido en DHL: ${insurance_cost:.2f} USD")
                    debug_log(f"🏛️ Impuestos argentinos incluidos en DHL: ${argentina_taxes:.2f} USD")
                
                costo_flete_total_usd = dhl_result["cost_usd"]
                metodo_calculo = f"DHL {dhl_result['method']}"
                
                # Logging según el método usado
                if dhl_result["method"] == "dhl_api_real":
                    debug_log(f"✅ Flete aéreo calculado con API real de DHL: ${costo_flete_total_usd:.2f}", level="SUCCESS")
                    st.success(f"🌐 Cotización real de DHL: ${costo_flete_total_usd:.2f} USD")
                    
                    # Mostrar desglose si está disponible
                    if 'cost_breakdown' in dhl_result:
                        breakdown = dhl_result['cost_breakdown']
                        st.info(f"💼 Incluye: Servicio ${breakdown.get('base_service_cost', 0):.2f} + Combustible ${breakdown.get('fuel_surcharge', 0):.2f}" +
                               (f" + Seguro ${breakdown.get('insurance_cost', 0):.2f}" if breakdown.get('insurance_cost', 0) > 0 else "") +
                               (f" + Impuestos AR ${breakdown.get('argentina_taxes', 0):.2f}" if breakdown.get('argentina_taxes', 0) > 0 else ""))
                        
                elif dhl_result["method"] == "fallback_rates":
                    debug_log(f"✅ Flete aéreo con tarifas de fallback DHL: ${costo_flete_total_usd:.2f}", level="WARNING")
                    st.info(f"📊 Cotización con tarifas de referencia: ${costo_flete_total_usd:.2f} USD")
                else:
                    debug_log(f"✅ Flete aéreo con estimación básica: ${costo_flete_total_usd:.2f}", level="WARNING")
                    st.warning(f"📈 Cotización estimada: ${costo_flete_total_usd:.2f} USD")
                
                if dhl_result.get("note"):
                    st.caption(f"ℹ️ {dhl_result['note']}")
                    
                # Almacenar información del seguro e impuestos para uso posterior
                result_session_data = {
                    'dhl_insurance_cost': insurance_cost,
                    'dhl_argentina_taxes': argentina_taxes,
                    'dhl_insurance_included': dhl_result.get('insurance_included', False),
                    'dhl_taxes_included': dhl_result.get('taxes_included', False)
                }
                    
            except Exception as e:
                # Fallback final a cálculo tradicional
                debug_log(f"❌ Error en servicio DHL integrado: {e}. Usando fallback tradicional.", level="ERROR")
                if st.session_state.freight_rates is not None:
                    costo_flete_total_usd = calculate_air_freight(peso_facturable_kg, st.session_state.freight_rates)
                    metodo_calculo = "Fallback tradicional DHL Zona 5"
                    st.warning(f"⚠️ Usando tarifas tradicionales: ${costo_flete_total_usd:.2f} USD")
                else:
                    costo_flete_total_usd = 0
                    metodo_calculo = "Sin tarifas disponibles"
                    st.error("❌ No se pudo calcular flete aéreo")
                
                # Sin información adicional en fallback
                result_session_data = {
                    'dhl_insurance_cost': 0.0,
                    'dhl_argentina_taxes': 0.0,
                    'dhl_insurance_included': False,
                    'dhl_taxes_included': False
                }

        elif tipo_flete == "Marítimo (Contenedor)":
            if volumen_total_cbm > 0:
                # Usar exactamente 90 USD por m³
                costo_flete_total_usd = volumen_total_cbm * 90.0
                metodo_calculo = "90 USD/m³"
                debug_log(f"✅ Flete marítimo calculado: ${costo_flete_total_usd:.2f} para {volumen_total_cbm:.6f} m³ a 90 USD/m³", level="SUCCESS")
            else:
                # Sin dimensiones válidas, no calcular flete marítimo
                costo_flete_total_usd = 0
                metodo_calculo = "Sin dimensiones válidas"
                debug_log("❌ No se puede calcular flete marítimo sin dimensiones válidas", level="ERROR")
        
        # Calcular costo unitario CORRECTAMENTE
        costo_flete_unitario_usd = costo_flete_total_usd / import_quantity if import_quantity > 0 else 0
        
        # DEBUG: Mostrar información detallada del cálculo de flete
        debug_log("📦 Detalles del cálculo de flete:", {
            "peso_unitario_kg": peso_unitario_kg,
            "cantidad_unidades": import_quantity,
            "peso_total_kg": peso_total_kg,
            "peso_volumetrico_total_kg": peso_volumetrico_total_kg,
            "peso_facturable_kg": peso_facturable_kg,
            "volumen_unitario_cbm": volumen_unitario_cbm,
            "volumen_total_cbm": volumen_total_cbm if tipo_flete == "Marítimo (Contenedor)" else "N/A",
            "costo_flete_total_usd": costo_flete_total_usd,
            "costo_flete_unitario_usd": costo_flete_unitario_usd,
            "tipo_flete": tipo_flete,
            "metodo_calculo": metodo_calculo,
            "tarifas_disponibles": st.session_state.freight_rates is not None
        }, level="INFO")
        
        log_flow_step("CALCULO_FLETE", "SUCCESS", {
            "costo_total_flete": costo_flete_total_usd,
            "costo_unitario_flete": costo_flete_unitario_usd,
            "cantidad_importada": import_quantity,
            "peso_total_kg": peso_total_kg,
            "peso_facturable_kg": peso_facturable_kg,
            "volumen_total_cbm": volumen_total_cbm,
            "metodo_calculo": metodo_calculo
        })

        honorarios_despachante = precio_base * 0.02
        landed_cost = precio_base + float(tax_result.total_impuestos) + costo_flete_unitario_usd + honorarios_despachante

        # Paso 4: Consolidar resultados
        st.session_state.result = {
            "product": product_for_analysis,
            "ncm_result": ncm_result,
            "tax_result": tax_result,
            "costo_flete_usd": costo_flete_unitario_usd,
            "costo_flete_total_usd": costo_flete_total_usd,
            "peso_final_kg": peso_unitario_kg, # Mantenemos el peso unitario aquí
            "shipping_details": { # Usar los datos del formulario con información ampliada
                "weight_kg": peso_unitario_kg,
                "peso_total_kg": peso_total_kg,
                "peso_volumetrico_total_kg": peso_volumetrico_total_kg,
                "peso_facturable_kg": peso_facturable_kg,
                "dimensions_cm": dims,
                "volumen_unitario_cbm": volumen_unitario_cbm,
                "volumen_total_cbm": volumen_total_cbm,
                "method": "Manual" if st.session_state.entry_mode == 'Ingreso Manual' else 'Edited',
                "metodo_calculo_flete": metodo_calculo
            },
            "landed_cost": landed_cost,
            "precio_base": precio_base,
            "precio_seleccionado": precio_base,
            "image_selection_info": {"selected_url": editable_data['image_url']}, # Simular para render
            "configuracion": {
                "tipo_importador": tipo_importador, "destino_importacion": destino_importacion,
                "provincia": provincia,
                "cotizacion_dolar": cotizacion_dolar, "tipo_flete": tipo_flete,
                "honorarios_despachante": honorarios_despachante,
                "import_quantity": import_quantity
            },
            # NUEVO: Información adicional de DHL
            "dhl_details": result_session_data if 'result_session_data' in locals() else {
                'dhl_insurance_cost': 0.0,
                'dhl_argentina_taxes': 0.0,
                'dhl_insurance_included': False,
                'dhl_taxes_included': False
            }
        }
        log_flow_step("FIN_ANALISIS", "SUCCESS", {"landed_cost": landed_cost})
        st.rerun()

    except Exception as e:
        st.error(f"❌ Error fatal en el flujo de análisis: {str(e)}")
        log_flow_step("FIN_ANALISIS", "FATAL_ERROR", {"error": str(e), "traceback": traceback.format_exc()})
        st.session_state.result = None
    finally:
        st.session_state.current_step = None

def render_product_summary():
    """
    Renderiza una tarjeta de producto final, adaptada al nuevo flujo de datos.
    """
    result = st.session_state.result
    product = result['product']

    with st.container(border=True):
        col_img, col_details = st.columns([2, 3], gap="large")

        with col_img:
            image_url = result.get('image_selection_info', {}).get('selected_url')
            if image_url:
                st.image(image_url, use_container_width=True, caption="Imagen para clasificación")
            else:
                st.image("https://via.placeholder.com/400x400.png?text=Imagen+no+disponible", use_container_width=True)

        with col_details:
            st.title(product.title)
            st.markdown(
                "<p style='color: #6c757d; font-style: italic; font-size: 13px;'>Los costos y datos se basan en la información proporcionada (manual o extraída).</p>", 
                unsafe_allow_html=True
            )
            st.divider()

            # Resumen con st.metric
            origen = product.place_of_origin or "N/D"
            moq_unit = product.moq or "N/A"
            # Lógica de unidad simplificada para ser consistente en ambos modos
            unit = "unidades" 
            moq_str = f"{moq_unit} {unit}"
            price_range_str = f"${product.price_low:.2f}"
            if product.price_high > product.price_low:
                 price_range_str += f" - ${product.price_high:.2f}"

            row1 = st.columns(2)
            row1[0].metric(label="📍 Origen (si aplica)", value=origen)
            row1[1].metric(label="📦 Pedido Mínimo", value=moq_str)
            
            row2 = st.columns(2)
            row2[0].metric(label="💰 Precio Unitario Base", value=price_range_str)

            landed_cost_str = f"${result['landed_cost']:.2f}"
            row2[1].metric(label="💸 Landed Cost Unitario", value=landed_cost_str)
                
            st.divider()

            if product.url:
                st.link_button("Ver producto original en Alibaba ↗️", product.url, use_container_width=True)

def show_calculator_table():
    result = st.session_state.result
    
    # Mostrar métricas principales del análisis
    import_quantity = result['configuracion'].get('import_quantity', 1)
    landed_cost_unitario = result['landed_cost']
    costo_total_importacion = landed_cost_unitario * import_quantity
    flete_total = result.get('costo_flete_total_usd', result.get('costo_flete_usd', 0) * import_quantity)
    shipping_details = result.get('shipping_details', {})
    
    # Métricas principales en columnas
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            label="🎯 Landed Cost Unitario",
            value=f"${landed_cost_unitario:.2f} USD",
            help="Costo total por unidad incluyendo producto, impuestos, flete y servicios"
        )
    
    with col2:
        st.metric(
            label=f"📦 Costo Total ({import_quantity} unidades)",
            value=f"${costo_total_importacion:,.2f} USD",
            help="Costo total de la importación completa"
        )
    
    with col3:
        metodo_flete = shipping_details.get('metodo_calculo_flete', 'Calculado')
        st.metric(
            label="🚚 Flete Total Calculado",
            value=f"${flete_total:.2f} USD",
            help=f"Costo total del flete internacional para toda la cantidad (Método: {metodo_flete})"
        )
    
    # Información adicional del envío si está disponible
    if shipping_details.get('peso_facturable_kg', 0) > 0:
        st.markdown("#### 📊 Información del Envío")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                label="⚖️ Peso Físico Total",
                value=f"{shipping_details.get('peso_total_kg', 0):.2f} kg",
                help="Peso real de toda la mercadería"
            )
        
        with col2:
            peso_volumetrico = shipping_details.get('peso_volumetrico_total_kg', 0)
            if peso_volumetrico > 0:
                st.metric(
                    label="📐 Peso Volumétrico",
                    value=f"{peso_volumetrico:.2f} kg",
                    help="Peso volumétrico calculado (factor 167 kg/m³)"
                )
            else:
                st.metric(
                    label="📐 Peso Volumétrico",
                    value="No calculable",
                    help="No se puede calcular sin dimensiones válidas"
                )
        
        with col3:
            st.metric(
                label="🎯 Peso Facturable",
                value=f"{shipping_details.get('peso_facturable_kg', 0):.2f} kg",
                help="Peso utilizado para el cálculo del flete (el mayor entre físico y volumétrico)"
            )
        
        with col4:
            volumen_total = shipping_details.get('volumen_total_cbm', 0)
            if volumen_total > 0:
                st.metric(
                    label="📏 Volumen Total",
                    value=f"{volumen_total:.6f} m³",
                    help="Volumen total del envío"
                )
            else:
                st.metric(
                    label="📏 Volumen Total",
                    value="No calculable",
                    help="No se puede calcular sin dimensiones válidas"
                )
        
    st.divider()

    # Crear tabs principales - Desglose detallado separado
    tab1, tab2 = st.tabs([
        "📊 Análisis Completo", 
        "🔍 Desglose Detallado (Expertos)"
    ])
    
    with tab1:
        render_complete_analysis_tab(result)
    
    with tab2:
        render_detailed_breakdown_tab(result)
    
    # Botón para exportar a Google Sheets
    st.divider()
    st.markdown("### 📤 Exportar a Google Sheets")
    
    # Preparar datos para exportar
    export_data = prepare_export_data(result)
    
    # Mostrar un resumen de los datos a exportar
    st.write("**Datos que se exportarán:**")
    st.json(export_data)
    
    # Botón de exportación
    if st.button("📤 Subir a Google Sheets", type="primary", use_container_width=True):
        with st.spinner("Subiendo datos a Google Sheets..."):
            if upload_to_google_sheets(export_data):
                st.success("✅ Datos subidos correctamente a Google Sheets!")
            else:
                st.error("❌ Error al subir los datos a Google Sheets")

def prepare_export_data(result):
    """
    Preparar los datos de la cotización para exportar a Google Sheets.
    
    Args:
        result: Diccionario con los resultados del cálculo
        
    Returns:
        dict: Datos formateados para exportar
    """
    # Obtener datos básicos
    import_quantity = result['configuracion'].get('import_quantity', 1)
    precio_unitario = result['precio_base']
    cotizacion = result['configuracion'].get('cotizacion_dolar', 1000)
    flete_unitario = result['costo_flete_usd']
    honorarios_despachante = result['configuracion'].get('honorarios_despachante', 0)
    landed_cost = result['landed_cost']
    
    # Obtener datos de impuestos
    tax_result = result['tax_result']
    derechos_importacion = 0
    tasa_estadistica = 0
    iva_importacion = 0
    percepcion_iva = 0
    percepcion_ganancias = 0
    ingresos_brutos = 0
    
    # Porcentajes de impuestos
    derechos_importacion_pct = 0
    tasa_estadistica_pct = 0
    iva_importacion_pct = 0
    percepcion_iva_pct = 0
    percepcion_ganancias_pct = 0
    ingresos_brutos_pct = 0
    
    # Extraer valores de impuestos
    for impuesto in tax_result.impuestos:
        if impuesto.aplica:
            nombre_lower = impuesto.nombre.lower()
            monto = float(impuesto.monto)
            alicuota = float(impuesto.alicuota) * 100
            
            if "derechos" in nombre_lower or "importacion" in nombre_lower:
                derechos_importacion = monto
                derechos_importacion_pct = alicuota
            elif "estadistica" in nombre_lower:
                tasa_estadistica = monto
                tasa_estadistica_pct = alicuota
            elif "iva" in nombre_lower and "adicional" not in nombre_lower:
                iva_importacion = monto
                iva_importacion_pct = alicuota
            elif "adicional" in nombre_lower:
                percepcion_iva = monto
                percepcion_iva_pct = alicuota
            elif "ganancias" in nombre_lower:
                percepcion_ganancias = monto
                percepcion_ganancias_pct = alicuota
            elif "brutos" in nombre_lower or "iibb" in nombre_lower:
                ingresos_brutos = monto
                ingresos_brutos_pct = alicuota
    
    # Calcular totales
    total_impuestos = float(tax_result.total_impuestos)
    subtotal_con_impuestos = precio_unitario + total_impuestos
    flete_total = flete_unitario * import_quantity
    honorarios_total = honorarios_despachante * import_quantity
    total_landed_cost = landed_cost * import_quantity
    total_landed_cost_ars = total_landed_cost * cotizacion
    
    # Obtener datos de NCM
    ncm_result = result.get('ncm_result', {})
    ncm_code = ncm_result.get('ncm_completo', '')
    ncm_description = ncm_result.get('ncm_descripcion', '')
    confianza_ia = ncm_result.get('confianza', '')
    
    # Obtener datos de envío
    shipping_details = result.get('shipping_details', {})
    peso_unitario = shipping_details.get('weight_kg', 0)
    dims = shipping_details.get('dimensions_cm', {})
    dimensiones = f"{dims.get('length', 0)} × {dims.get('width', 0)} × {dims.get('height', 0)} cm"
    metodo_flete = result['configuracion'].get('tipo_flete', '')
    
    # Obtener datos de configuración
    tipo_importador = result['configuracion'].get('tipo_importador', '')
    destino = result['configuracion'].get('destino_importacion', '')
    provincia = result['configuracion'].get('provincia', '')
    origen = result['product'].place_of_origin if hasattr(result['product'], 'place_of_origin') else ''
    
    # Obtener URL de imagen
    image_url = result.get('image_selection_info', {}).get('selected_url', '')
    
    # Preparar datos para exportar
    export_data = {
        "fecha": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "producto": result['product'].title if hasattr(result['product'], 'title') else '',
        "imagen_url": image_url,  # La fórmula =IMAGE() se agregará en Google Sheets
        "url_producto": result['product'].url if hasattr(result['product'], 'url') else '',
        "cantidad": import_quantity,
        "precio_unitario_fob": precio_unitario,
        "subtotal_fob": precio_unitario * import_quantity,
        "moneda": "USD",
        "tipo_cambio": cotizacion,
        "derechos_importacion_pct": derechos_importacion_pct,
        "derechos_importacion": derechos_importacion,
        "tasa_estadistica_pct": tasa_estadistica_pct,
        "tasa_estadistica": tasa_estadistica,
        "iva_importacion_pct": iva_importacion_pct,
        "iva_importacion": iva_importacion,
        "percepcion_iva_pct": percepcion_iva_pct,
        "percepcion_iva": percepcion_iva,
        "percepcion_ganancias_pct": percepcion_ganancias_pct,
        "percepcion_ganancias": percepcion_ganancias,
        "ingresos_brutos_pct": ingresos_brutos_pct,
        "ingresos_brutos": ingresos_brutos,
        "total_impuestos": total_impuestos,
        "subtotal_con_impuestos": subtotal_con_impuestos,
        "costo_flete_unitario": flete_unitario,
        "costo_flete_total": flete_total,
        "honorarios_despachante": honorarios_total,
        "total_landed_cost": total_landed_cost,
        "total_landed_cost_ars": total_landed_cost_ars,
        "ncm": ncm_code,
        "descripcion_ncm": ncm_description,
        "confianza_ia": confianza_ia,
        "peso_unitario_kg": peso_unitario,
        "dimensiones": dimensiones,
        "metodo_flete": metodo_flete,
        "origen": origen,
        "destino": destino,
        "tipo_importador": tipo_importador,
        "provincia": provincia,
        "notas": ""
    }
    
    return export_data

def render_complete_analysis_tab(result):
    """Renderiza el análisis completo como estaba antes"""
    # Crear tabla principal de costos
    st.markdown("#### 💰 Desglose de Costo Unitario")
    
    # Calcular valores
    precio_producto = result['precio_base']
    impuestos_total = float(result['tax_result'].total_impuestos)
    flete_costo = result['costo_flete_usd']
    honorarios_despachante = result['configuracion'].get('honorarios_despachante', 0)
    landed_cost = result['landed_cost']
    cotizacion = result['configuracion'].get('cotizacion_dolar', 1000)
    
    # Etiqueta de flete mejorada
    tipo_flete = result['configuracion'].get("tipo_flete", "Courier (Aéreo)")
    flete_label = f"🚚 Flete {tipo_flete}"

    # Calcular porcentajes asegurando que la suma sea exactamente 100.0%
    components = {
        "producto": Decimal(str(precio_producto)),
        "impuestos": Decimal(str(impuestos_total)),
        "flete": Decimal(str(flete_costo)),
        "honorarios": Decimal(str(honorarios_despachante))
    }
    
    decimal_landed_cost = Decimal(str(landed_cost))
    
    if decimal_landed_cost > 0:
        percentages_unrounded = {k: (v / decimal_landed_cost) * 100 for k, v in components.items()}
        percentages_rounded = {k: v.quantize(Decimal('0.1'), rounding='ROUND_HALF_UP') for k, v in percentages_unrounded.items()}
        
        current_sum = sum(percentages_rounded.values())
        diff = Decimal('100.0') - current_sum
        
        if diff != Decimal('0'):
            key_to_adjust = max(components, key=components.get)
            percentages_rounded[key_to_adjust] += diff
    else:
        percentages_rounded = {
            "producto": Decimal('0.0'),
            "impuestos": Decimal('0.0'),
            "flete": Decimal('0.0'),
            "honorarios": Decimal('0.0')
        }

    # Tasa de cambio específica para flete marítimo
    cotizacion_flete = 1320
    
    # Crear DataFrame principal
    costos_data = [
        {
            "Concepto": "💰 Precio Producto",
            "USD": f"${precio_producto:.2f}",
            "ARS": f"${precio_producto * cotizacion:,.0f}",
            "% del Total": f"{percentages_rounded['producto']:.1f}%",
            "Categoría": "Base"
        },
        {
            "Concepto": "🏛️ Impuestos Totales",
            "USD": f"${impuestos_total:.2f}",
            "ARS": f"${impuestos_total * cotizacion:,.0f}",
            "% del Total": f"{percentages_rounded['impuestos']:.1f}%",
            "Categoría": "Tributario"
        },
        {
            "Concepto": flete_label,
            "USD": f"${flete_costo:.2f}",
            "ARS": f"${flete_costo * cotizacion_flete:,.0f}",
            "% del Total": f"{percentages_rounded['flete']:.1f}%",
            "Categoría": "Logística"
        },
        {
            "Concepto": "👤 Honorarios Despachante",
            "USD": f"${honorarios_despachante:.2f}",
            "ARS": f"${honorarios_despachante * cotizacion:,.0f}",
            "% del Total": f"{percentages_rounded['honorarios']:.1f}%",
            "Categoría": "Servicios"
        },
        {
            "Concepto": "🎯 LANDING COST UNITARIO",
            "USD": f"${landed_cost:.2f}",
            "ARS": f"${landed_cost * cotizacion:,.0f}",
            "% del Total": "100.0%",
            "Categoría": "TOTAL"
        }
    ]
    
    df_costos = pd.DataFrame(costos_data)
    
    # Configuración de estilo para el DataFrame
    def color_rows(row):
        if row['Categoría'] == 'TOTAL':
            return ['background-color: #f0f0f0; font-weight: bold'] * len(row)
        elif row['Categoría'] == 'Tributario':
            return ['background-color: #fff3cd'] * len(row)
        elif row['Categoría'] == 'Logística':
            return ['background-color: #d1ecf1'] * len(row)
        elif row['Categoría'] == 'Servicios':
            return ['background-color: #e2e3e5'] * len(row)
        else:
            return [''] * len(row)
    
    st.dataframe(
        df_costos.style.apply(color_rows, axis=1),
        use_container_width=True,
        hide_index=True
    )
    
    # NUEVA SECCIÓN: Mostrar impuestos oficiales de importación de la base de datos
    st.markdown("#### 🏛️ Impuestos Oficiales de Importación")
    st.markdown("*Datos oficiales extraídos de AFIP/VUCE para impuestos de importación únicamente*")
    
    # Obtener todos los impuestos oficiales
    official_taxes = _get_all_official_taxes_from_ncm_result(result['ncm_result'])
    
    # Crear tabla de impuestos oficiales con mejor formateo (solo importación)
    impuestos_oficiales_data = [
        {
            "Impuesto": "🏛️ AEC (Arancel Externo Común)",
            "Valor Oficial": f"{official_taxes['aec']['valor']:.1f}%" if official_taxes['aec']['valor'] > 0 else "0.0%",
            "Fuente": official_taxes['aec']['fuente']
        },
        {
            "Impuesto": "📊 DIE (Derechos de Importación Específicos)",
            "Valor Oficial": f"{official_taxes['die']['valor']:.1f}" if official_taxes['die']['valor'] > 0 else "0.0",
            "Fuente": official_taxes['die']['fuente']
        },
        {
            "Impuesto": "📈 TE (Tasa Estadística)",
            "Valor Oficial": f"{official_taxes['te']['valor']:.1f}%" if official_taxes['te']['valor'] > 0 else "0.0%",
            "Fuente": official_taxes['te']['fuente']
        },
        {
            "Impuesto": "⚠️ IN (Intervenciones)",
            "Valor Oficial": official_taxes['intervenciones']['valor'][:100] + "..." if len(official_taxes['intervenciones']['valor']) > 100 else official_taxes['intervenciones']['valor'],
            "Fuente": official_taxes['intervenciones']['fuente']
        }
    ]
        
    df_impuestos_oficiales = pd.DataFrame(impuestos_oficiales_data)
    
    # Mostrar tabla sin colores
    st.dataframe(
        df_impuestos_oficiales,
        use_container_width=True,
        hide_index=True
    )
    
    # Mostrar información sobre la fuente de datos
    fuente_principal = official_taxes['aec']['fuente']
    source_icon = "🇦🇷" if "Base Oficial NCM" in fuente_principal else "🤖"
    st.info(f"{source_icon} **Fuente de los datos:** {fuente_principal}")
    
    if fuente_principal != 'Base Oficial NCM':
        st.warning("⚠️ **Nota:** Algunos datos provienen de estimación por IA. Para mayor precisión, se recomienda verificar en AFIP/VUCE directamente.")
    
    st.divider()
    
    # Gráficos de visualización de costos
    st.markdown("#### 📊 Visualización de Costos")

    cost_components = {
        'Precio Producto': precio_producto,
        'Impuestos': impuestos_total,
        'Flete': flete_costo,
        'Despachante': honorarios_despachante
    }
    
    non_zero_labels = [k for k, v in cost_components.items() if v > 0]
    values = [v for v in cost_components.values() if v > 0]

    fig_pie = go.Figure(data=[go.Pie(
        labels=non_zero_labels, 
        values=values, 
        hole=.3,
        pull=[0.02] * len(non_zero_labels),
        textinfo='percent+label',
        hoverinfo='label+percent+value'
    )])
    fig_pie.update_layout(
        title_text='Distribución del Landed Cost',
        legend_title_text='Componentes',
        uniformtext_minsize=10, 
        uniformtext_mode='hide',
        margin=dict(t=40, b=0, l=0, r=0)
    )
    st.plotly_chart(fig_pie, use_container_width=True)

    # Añadir tabla de landed cost por cantidad
    pricing_info = result['product'].pricing
    if hasattr(pricing_info, 'ladder_prices') and pricing_info.ladder_prices:
        st.markdown("#### 💰 Landed Cost por Volumen de Compra")
        
        # Extraer derechos de importación para cálculo por tiers
        derechos_importacion_pct = _get_duties_from_ncm_result(result.get('ncm_result', {}))

        landed_cost_tiers = []
        cotizacion = result.get('cotizacion_dolar', 1220)
        # Usar el landed cost de la opción más barata como base para comparación
        base_landed_cost_unitario = result['landed_cost']

        for tier in pricing_info.ladder_prices:
            if 'price' not in tier or 'min' not in tier:
                continue
            
            price = float(tier['price'])
            min_quantity = int(tier['min'])

            # Recalcular componentes para este tier
            tax_result_tier = calcular_impuestos_importacion(
                cif_value=price,
                tipo_importador=result['configuracion'].get('tipo_importador', 'responsable_inscripto'),
                destino=result['configuracion'].get('destino_importacion', 'reventa'),
                origen="extrazona",
                provincia=result['configuracion'].get('provincia', 'CABA'),
                derechos_importacion_pct=derechos_importacion_pct
            )
            
            impuestos_total_tier = float(tax_result_tier.total_impuestos)
            # Usar el método de flete actual de la configuración para cálculo consistente
            if result['configuracion'].get('tipo_flete') == "Courier (Aéreo)":
                # Para tiers, usar estimación proporcional al precio
                flete_costo_estimado_tier = price * 0.15 
            elif result['configuracion'].get('tipo_flete') == "Marítimo (Contenedor)":
                # Para marítimo, el costo es más por volumen, no tanto por precio
                flete_costo_estimado_tier = price * 0.12
            else:
                flete_costo_estimado_tier = price * 0.15 
            honorarios_despachante_tier = price * 0.02
            
            landed_cost_unitario_tier = price + impuestos_total_tier + flete_costo_estimado_tier + honorarios_despachante_tier
            
            # Calcular ahorro vs el costo base (opción más barata)
            ahorro_unitario = base_landed_cost_unitario - landed_cost_unitario_tier
            
            landed_cost_tiers.append({
                "Cantidad Mínima": f"{min_quantity}{'+' if tier.get('max', -1) == -1 else '-' + str(tier['max'])}",
                "Precio FOB Unitario": f"${price:.2f}",
                "Landed Cost Unitario": f"${landed_cost_unitario_tier:.2f}",
                "Ahorro Unitario vs Base": f"${ahorro_unitario:.2f}" if ahorro_unitario > 0.01 else "-",
                "Costo Total Lote (USD)": f"${landed_cost_unitario_tier * min_quantity:,.2f}",
            })

        if landed_cost_tiers:
            df_tiers = pd.DataFrame(landed_cost_tiers)
            st.dataframe(df_tiers, use_container_width=True, hide_index=True)
    else:
        st.info("ℹ️ No se encontraron precios específicos por volumen para este producto.")

    # Tabla detallada de impuestos
    st.markdown("#### 🏛️ Detalle de Impuestos")
    
    impuestos_detalle = []
    for impuesto in result['tax_result'].impuestos:
        if impuesto.aplica:
            monto_usd = float(impuesto.monto)
            impuestos_detalle.append({
                "Impuesto": impuesto.nombre,
                "Alícuota": f"{impuesto.alicuota:.2%}",
                "Base USD": f"${impuesto.base_imponible:.2f}",
                "Monto USD": f"${monto_usd:.2f}",
                "Monto ARS": f"${monto_usd * cotizacion:,.0f}",
                "Estado": "✅ Aplica"
            })
        else:
            impuestos_detalle.append({
                "Impuesto": impuesto.nombre,
                "Alícuota": "N/A",
                "Base USD": "N/A",
                "Monto USD": "$0.00",
                "Monto ARS": "$0",
                "Estado": "❌ No Aplica"
            })
    
    if impuestos_detalle:
        df_impuestos = pd.DataFrame(impuestos_detalle)
        st.dataframe(df_impuestos, use_container_width=True, hide_index=True)
    
    # Análisis de Rentabilidad por Canal de Venta
    st.markdown("#### 📈 Análisis de Rentabilidad por Canal de Venta")
    st.markdown("*Precios de venta sugeridos para obtener la utilidad neta deseada, absorbiendo la comisión de cada plataforma.*")

    # Definir canales de venta y sus comisiones promedio
    canales_venta = {
        "Venta Directa (0%)": 0.0,
        "Tienda Online (6%)": 0.06,
        "ML Clásica (13%)": 0.13,
        "ML Premium (28%)": 0.28,
    }
    
    # Definir los márgenes de ganancia deseados a analizar
    margenes_deseados = [0.3, 0.5, 1.0]
    
    # Preparar datos para la tabla comparativa
    header_tuples = [
        (' ', 'Utilidad Neta (USD)'), 
        (' ', 'ROI Neto')
    ]
    for canal in canales_venta.keys():
        header_tuples.append((canal, 'Precio USD'))
        header_tuples.append((canal, 'Precio ARS'))
    
    columns = pd.MultiIndex.from_tuples(header_tuples)
    
    data_for_df = []
    for margen in margenes_deseados:
        utilidad_neta = landed_cost * margen
        row_data = [f"${utilidad_neta:,.2f}", f"{margen:.0%}"]
        
        for _, comision in canales_venta.items():
            # Fórmula: PrecioVenta = (CostoTotal * (1 + Margen)) / (1 - Comision)
            if (1 - comision) > 0:
                precio_venta_usd = (landed_cost * (1 + margen)) / (1 - comision)
            else:
                precio_venta_usd = float('inf')

            precio_venta_ars = precio_venta_usd * cotizacion
            
            row_data.append(f"${precio_venta_usd:,.2f}")
            row_data.append(f"${precio_venta_ars:,.0f}")
            
        data_for_df.append(row_data)
        
    if data_for_df:
        df_rentabilidad = pd.DataFrame(data_for_df, columns=columns)
        st.dataframe(df_rentabilidad, use_container_width=True, hide_index=True)

    # Información de clasificación arancelaria (NCM) con datos VUCE
    st.markdown("#### 📖 Clasificación Arancelaria (NCM) + Base Oficial")
    
    ncm_result = result['ncm_result']
    courier_info = ncm_result.get('regimen_simplificado_courier', {})
    ncm_official_info = ncm_result.get('ncm_official_info', {})
    
    # Tratamiento arancelario (ahora con datos oficiales NCM si están disponibles)
    tratamiento = ncm_result.get('tratamiento_arancelario', {})
    intervenciones_ia = ncm_result.get('intervenciones_requeridas', [])
    intervenciones_oficiales = ncm_official_info.get('intervenciones_detectadas', [])
    
    # Combinar intervenciones de IA y base oficial
    todas_intervenciones = list(set(intervenciones_ia + intervenciones_oficiales))
    intervenciones_str = ", ".join(todas_intervenciones) if todas_intervenciones else "Ninguna"
    
    ncm_completo = ncm_result.get('ncm_completo', 'N/A')
    
    # Construir URL para consulta oficial
    if ncm_completo and ncm_completo != "N/A":
        # Extraer solo el código base para la URL (sin sufijo SIM)
        # Ejemplo: "8528.72.00 100W" -> "85287200"
        ncm_base = ncm_completo.split()[0] if ' ' in ncm_completo else ncm_completo
        ncm_code_for_url = ncm_base.replace(".", "")
        consulta_url = f"https://www.argentina.gob.ar/afip/nomenclador-comun-del-mercosur-ncm"
    else:
        consulta_url = "https://www.argentina.gob.ar/afip/nomenclador-comun-del-mercosur-ncm"
    
    # Determinar fuente de datos
    fuente_datos = tratamiento.get('fuente', 'IA')
    ncm_official_match = ncm_official_info.get('match_exacto', False)
    
    # Información sobre refinamiento automático
    was_refined = ncm_official_info.get('was_refined', False)
    refinement_info = ncm_official_info.get('refinement_info', {})
    
    # Análisis de régimen simplificado
    courier_regime = ncm_result.get('regimen_simplificado_courier', {})
    
    ncm_data = [
        {"Campo": "Posición NCM", "Valor": ncm_completo},
        {"Campo": "Descripción NCM", "Valor": ncm_result.get('ncm_descripcion', ncm_official_info.get('descripcion_oficial', 'No disponible'))},
        {"Campo": "Capítulo", "Valor": ncm_result.get('ncm_desglose', {}).get('capitulo', 'No disponible')},
        {"Campo": "Partida", "Valor": ncm_result.get('ncm_desglose', {}).get('partida', 'No disponible')},
        {"Campo": "Subpartida", "Valor": ncm_result.get('ncm_desglose', {}).get('subpartida', 'No disponible')},
        {"Campo": "Confianza de IA", "Valor": f"{ncm_result.get('confianza', 'N/A')}"},
        {"Campo": "Fuente Datos", "Valor": f"{fuente_datos} {'🇦🇷' if ncm_official_match else '🤖'}"},
        {"Campo": "Match Oficial", "Valor": "✅ Exacto" if ncm_official_match else "❌ No encontrado" if 'ncm_official_info' in ncm_result else "⚠️ No consultado"},
        {"Campo": "Refinamiento Automático", "Valor": "🎯 Sí (LLM eligió subcategoría)" if was_refined else "➡️ No necesario"},
        {"Campo": "Derechos de Importación", "Valor": f"{tratamiento.get('derechos_importacion', 'N/A')}"},
        {"Campo": "Tasa Estadística", "Valor": f"{tratamiento.get('tasa_estadistica', 'N/A')}"},
        {"Campo": "IVA", "Valor": f"{tratamiento.get('iva', 'N/A')}"},
        {"Campo": "IVA Adicional", "Valor": f"{tratamiento.get('iva_adicional', 'N/A')}"},
        {"Campo": "Intervenciones", "Valor": intervenciones_str},
        {"Campo": "Régimen Simplificado", "Valor": courier_regime.get('aplica', 'N/A')},
        {"Campo": "Justificación", "Valor": ncm_result.get('justificacion_clasificacion', 'N/A')[:150] + '...' if ncm_result.get('justificacion_clasificacion') and len(ncm_result.get('justificacion_clasificacion', '')) > 150 else ncm_result.get('justificacion_clasificacion', 'N/A')}
    ]
    
    # Añadir información detallada del refinamiento si ocurrió
    if was_refined and refinement_info:
        ncm_data.append({
            "Campo": "Opciones Evaluadas",
            "Valor": f"{refinement_info.get('total_options', 'N/A')} subcategorías"
        })
        ncm_data.append({
            "Campo": "Posición Original",
            "Valor": f"{refinement_info.get('original_code', 'N/A')}"
        })
    
    # Añadir fecha de actualización oficial si está disponible
    if ncm_official_info.get('fecha_actualizacion'):
        ncm_data.append({
            "Campo": "Actualizado Base Oficial",
            "Valor": ncm_official_info['fecha_actualizacion']
        })
    
    df_ncm = pd.DataFrame(ncm_data)
    st.dataframe(df_ncm, use_container_width=True, hide_index=True)
    
    # Enlaces y validación
    if ncm_completo and ncm_completo != "N/A":
        st.markdown(f"<a href='{consulta_url}' target='_blank' style='text-decoration: none; color: #495057;'>🔗 Consultar NCM en Base Oficial</a>", unsafe_allow_html=True)
    
    # Alertas y advertencias
    if 'ncm_warning' in ncm_result:
        st.warning(f"⚠️ NCM: {ncm_result['ncm_warning']}")
    elif ncm_official_match:
        st.success("✅ Datos validados con base oficial NCM")
    
    # Análisis específico del régimen simplificado con base oficial
    if 'ncm_analysis' in courier_info:
        ncm_analysis = courier_info['ncm_analysis']
        st.subheader("🔍 Análisis de Régimen Simplificado (Base Oficial)")
        st.markdown(f"**Aplica potencialmente:** {'✅ Sí' if ncm_analysis.get('aplica_potencialmente') else '❌ No'}")
        
        for factor in ncm_analysis.get('factores_a_verificar', []):
            st.info(f"🔍 {factor}")
        
        if ncm_analysis.get('posibles_restricciones'):
            for restriccion in ncm_analysis['posibles_restricciones']:
                st.warning(f"⚠️ {restriccion}")
        
        st.markdown(f"**Observaciones:** {ncm_analysis.get('observaciones', 'N/A')}")
        st.markdown(f"**Capítulo NCM:** {ncm_analysis.get('capitulo_ncm', 'N/A')}")

    # Botones de acción minimalistas para exportar
    st.markdown("---")
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📊 Exportar Excel", use_container_width=True):
            try:
                excel_data = generate_excel_report(result)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"landed_cost_analysis_{timestamp}.xlsx"
                
                st.download_button(
                    label="📥 Descargar Excel",
                    data=excel_data,
                    file_name=filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            except Exception as e:
                if "xlsxwriter" in str(e):
                    st.error("📦 Para exportar a Excel, instala: pip install xlsxwriter")
                else:
                    st.error(f"❌ Error generando Excel: {str(e)}")
    
    with col2:
        if st.button("📄 Exportar JSON", use_container_width=True):
            report_data = generate_report(result)
            st.download_button(
                label="📥 Descargar",
                data=json.dumps(report_data, indent=2, ensure_ascii=False),
                file_name=f"landing_cost_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
                use_container_width=True
            )

def generate_report(result):
    """Generar reporte completo para exportación incluyendo datos oficiales NCM"""
    ncm_result = result['ncm_result']
    ncm_official_info = ncm_result.get('ncm_official_info', {})
    courier_info = ncm_result.get('regimen_simplificado_courier', {})
    
    return {
        "fecha_analisis": datetime.now().isoformat(),
        "version_sistema": "v3.1_con_entrada_manual",
        "producto": {
            "titulo": result['product'].title,
            "precio_rango_input": f"${result['product'].price_low:.2f} - ${result['product'].price_high:.2f}",
            "precio_base_calculo": result['precio_base'],
            "moq_input": result['product'].moq,
            "origen_extraido": result['product'].place_of_origin,
            "categorias_extraidas": result['product'].categories,
            "url_producto": result['product'].url,
            "url_imagen": result.get('image_selection_info', {}).get('selected_url')
        },
        "clasificacion_ncm": {
            "ncm_completo": ncm_result.get('ncm_completo'),
            "ncm_descripcion": ncm_result.get('ncm_descripcion'),
            "confianza_ia": ncm_result.get('confianza'),
            "metodo_clasificacion": ncm_result.get('classification_method'),
            "justificacion": ncm_result.get('justificacion_clasificacion'),
            "intervenciones_ia": ncm_result.get('intervenciones_requeridas', []),
                    "ncm_official_data": {
            "match_exacto": ncm_official_info.get('match_exacto', False),
            "descripcion_oficial": ncm_official_info.get('descripcion_oficial'),
            "fecha_actualizacion": ncm_official_info.get('fecha_actualizacion'),
            "intervenciones_detectadas": ncm_official_info.get('intervenciones_detectadas', []),
            "warning": ncm_result.get('ncm_warning')
        },
            "tratamiento_arancelario": ncm_result.get('tratamiento_arancelario', {}),
            "regimen_simplificado": {
                "aplica_ia": courier_info.get('aplica'),
                "aplica_vuce": courier_info.get('vuce_analysis', {}).get('aplica_potencialmente'),
                "decision_final": courier_info.get('aplica_final'),
                "justificacion_ia": courier_info.get('justificacion'),
                "justificacion_combinada": courier_info.get('justificacion_combinada'),
                "factores_verificar": courier_info.get('vuce_analysis', {}).get('factores_a_verificar', []),
                "limitaciones": courier_info.get('limitaciones'),
                "restricciones_detectadas": courier_info.get('vuce_analysis', {}).get('posibles_restricciones', [])
            }
        },
        "impuestos": {
            "total": float(result['tax_result'].total_impuestos),
            "incidencia_porcentual": float(result['tax_result'].incidencia_porcentual),
            "detalle": [
                {
                    "nombre": imp.nombre,
                    "alicuota": float(imp.alicuota),
                    "monto": float(imp.monto),
                    "aplica": imp.aplica,
                    "observaciones": imp.observaciones
                }
                for imp in result['tax_result'].impuestos
            ]
        },
        "flete": {
            "costo": result.get('costo_flete_usd', 0),
            "costo_total": result.get('costo_flete_total_usd', 0),
            "method": result.get('shipping_details', {}).get('metodo_calculo_flete', 'unknown')
        },
        "estimaciones_envio": result.get('shipping_details', {}),
        "honorarios_despachante": result.get('honorarios_despachante', 0),
        "landed_cost": result['landed_cost'],
        "analisis_rentabilidad": {
            "incidencia_impuestos": (float(result['tax_result'].total_impuestos) / result['precio_base']) * 100,
            "incidencia_flete": (result['flete_costo'] / result['precio_base']) * 100 if result['precio_base'] > 0 else 0,
            "incidencia_despachante": (result['configuracion'].get('honorarios_despachante', 0) / result['precio_base']) * 100 if result['precio_base'] > 0 else 0,
            "markup_total": ((result['landed_cost'] - result['precio_base']) / result['precio_base']) * 100 if result['precio_base'] > 0 else 0,
            "precios_sugeridos": {
                "margen_30": result['landed_cost'] * 1.3,
                "margen_50": result['landed_cost'] * 1.5,
                "margen_100": result['landed_cost'] * 2.0
            }
        },
        "configuracion_calculo": {
            "tipo_importador": result['configuracion'].get('tipo_importador'),
            "destino_importacion": result['configuracion'].get('destino_importacion'),
            "provincia": result['configuracion'].get('provincia'),
            "cotizacion_dolar": result['configuracion'].get('cotizacion_dolar')
        },
        "metadata": {
            "fuente_datos": st.session_state.entry_mode,
            "debug_logs": st.session_state.debug_logs if st.session_state.debug_mode else [],
            "image_selection_info": result.get('image_selection_info', {}),
            "pricing_input_df": st.session_state.product_data_editable['pricing_df'].to_dict('records'),
            "flujo_completado": True,
            "errores_encontrados": [log for log in st.session_state.debug_logs if log.get('level') == 'ERROR'] if st.session_state.debug_mode else []
        }
    }

def recalculate_and_update_session(result, new_price, new_flete_type, selected_option):
    """
    Recalcula todos los costos basados en nuevos parámetros y actualiza el estado de la sesión.
    """
    # Mantener import de calculate_sea_freight para flete marítimo
    from freight_estimation import calculate_sea_freight
    
    # Obtener direcciones de envío del session state (configuradas en el sidebar)
    origin_details = st.session_state.get('origin_details')
    destination_details = st.session_state.get('destination_details')
    
    if new_flete_type and new_flete_type != result.get("tipo_flete"):
        st.info(f"🔄 Recalculando con flete {new_flete_type}...")
    
    if new_price and abs(new_price - result.get("precio_seleccionado", result["precio_base"])) > 0.01:
        st.info("🔄 Recalculando con el nuevo precio...")

    try:
        # Actualizar parámetros en el objeto de resultado
        result['precio_seleccionado'] = new_price
        result['precio_base'] = new_price
        result['tipo_flete'] = new_flete_type
        if selected_option:
            result['selected_price_option'] = selected_option
        
        # 1. Recalcular impuestos (dependen del precio)
        derechos_importacion_pct = _get_duties_from_ncm_result(result.get('ncm_result', {}))
        tax_result = calcular_impuestos_importacion(
            cif_value=new_price,
            tipo_importador=result['configuracion'].get('tipo_importador', 'responsable_inscripto'),
            destino=result['configuracion'].get('destino_importacion', 'reventa'),
            origen="extrazona",
            provincia=result['configuracion'].get('provincia', 'CABA'),
            derechos_importacion_pct=derechos_importacion_pct
        )
        result['tax_result'] = tax_result
        
        # 2. Recalcular flete considerando múltiples unidades usando la misma lógica mejorada
        import_quantity = result['configuracion'].get('import_quantity', 1)
        shipping_details = result.get('shipping_details', {})
        
        # Obtener datos de peso y dimensiones
        peso_unitario = shipping_details.get('weight_kg', 1.0)
        dims = shipping_details.get('dimensions_cm', {})
        
        # Calcular pesos y volúmenes
        peso_total_kg = peso_unitario * import_quantity
        
        # Calcular peso volumétrico y volumen
        volumen_unitario_cbm = 0
        peso_volumetrico_total_kg = 0
        if all(d > 0 for d in dims.values()):
            volumen_unitario_cbm = (dims['length'] * dims['width'] * dims['height']) / 1_000_000
            volumen_total_cbm = volumen_unitario_cbm * import_quantity
            peso_volumetrico_total_kg = volumen_total_cbm * 167  # Factor aéreo estándar
        else:
            volumen_total_cbm = 0
            
        # Para flete aéreo, usar el mayor entre peso físico y volumétrico
        peso_facturable_kg = max(peso_total_kg, peso_volumetrico_total_kg) if peso_volumetrico_total_kg > 0 else peso_total_kg
        
        flete_costo_total = 0.0
        metodo_calculo = "Sin datos"
        
        if new_flete_type == "Courier (Aéreo)":
            # NUEVO: Usar servicio DHL integrado en recálculo
            try:
                dimensions_cm_dict = {
                    "length": dims.get('length', 25),
                    "width": dims.get('width', 35), 
                    "height": dims.get('height', 15)
                }
                
                dhl_result = st.session_state.dhl_service.calculate_freight_with_fallback(
                    weight_kg=peso_facturable_kg,
                    dimensions_cm=dimensions_cm_dict,
                    origin_details=origin_details,
                    destination_details=destination_details,
                    shipping_datetime=st.session_state.get('planned_shipping_datetime')
                )
                
                # Registrar la respuesta completa en la API responses
                if 'raw_response' in dhl_result:
                    log_api_call("DHL_API", dimensions_cm_dict, dhl_result['raw_response'], dhl_result['success'])
                
                # Extraer costos detallados si están disponibles
                insurance_cost = 0.0
                argentina_taxes = 0.0
                
                if 'cost_breakdown' in dhl_result:
                    cost_breakdown = dhl_result['cost_breakdown']
                    insurance_cost = cost_breakdown.get('insurance_cost', 0.0)
                    argentina_taxes = cost_breakdown.get('argentina_taxes', 0.0)
                    
                    debug_log(f"🛡️ Seguro incluido en DHL: ${insurance_cost:.2f} USD")
                    debug_log(f"🏛️ Impuestos argentinos incluidos en DHL: ${argentina_taxes:.2f} USD")
                
                costo_flete_total_usd = dhl_result["cost_usd"]
                metodo_calculo = f"DHL {dhl_result['method']}"
                
                # Logging según el método usado
                if dhl_result["method"] == "dhl_api_real":
                    debug_log(f"✅ Flete aéreo calculado con API real de DHL: ${costo_flete_total_usd:.2f}", level="SUCCESS")
                    st.success(f"🌐 Cotización real de DHL: ${costo_flete_total_usd:.2f} USD")
                    
                    # Mostrar desglose si está disponible
                    if 'cost_breakdown' in dhl_result:
                        breakdown = dhl_result['cost_breakdown']
                        st.info(f"💼 Incluye: Servicio ${breakdown.get('base_service_cost', 0):.2f} + Combustible ${breakdown.get('fuel_surcharge', 0):.2f}" +
                               (f" + Seguro ${breakdown.get('insurance_cost', 0):.2f}" if breakdown.get('insurance_cost', 0) > 0 else "") +
                               (f" + Impuestos AR ${breakdown.get('argentina_taxes', 0):.2f}" if breakdown.get('argentina_taxes', 0) > 0 else ""))
                        
                elif dhl_result["method"] == "fallback_rates":
                    debug_log(f"✅ Flete aéreo con tarifas de fallback DHL: ${costo_flete_total_usd:.2f}", level="WARNING")
                    st.info(f"📊 Cotización con tarifas de referencia: ${costo_flete_total_usd:.2f} USD")
                else:
                    debug_log(f"✅ Flete aéreo con estimación básica: ${costo_flete_total_usd:.2f}", level="WARNING")
                    st.warning(f"📈 Cotización estimada: ${costo_flete_total_usd:.2f} USD")
                
                if dhl_result.get("note"):
                    st.caption(f"ℹ️ {dhl_result['note']}")
                    
                # Almacenar información del seguro e impuestos para uso posterior
                result_session_data = {
                    'dhl_insurance_cost': insurance_cost,
                    'dhl_argentina_taxes': argentina_taxes,
                    'dhl_insurance_included': dhl_result.get('insurance_included', False),
                    'dhl_taxes_included': dhl_result.get('taxes_included', False)
                }
                    
            except Exception as e:
                # Fallback final a cálculo tradicional
                debug_log(f"❌ Error en servicio DHL integrado: {e}. Usando fallback tradicional.", level="ERROR")
                if st.session_state.freight_rates is not None:
                    costo_flete_total_usd = calculate_air_freight(peso_facturable_kg, st.session_state.freight_rates)
                    metodo_calculo = "Fallback DHL Zona 5"
                    st.warning(f"⚠️ Usando tarifas tradicionales: ${costo_flete_total_usd:.2f} USD")
                else:
                    costo_flete_total_usd = 0
                    metodo_calculo = "Sin tarifas disponibles"
                    st.error("❌ No se pudo calcular flete aéreo")
                
                # Sin información adicional en fallback
                result_session_data = {
                    'dhl_insurance_cost': 0.0,
                    'dhl_argentina_taxes': 0.0,
                    'dhl_insurance_included': False,
                    'dhl_taxes_included': False
                }

        elif new_flete_type == "Marítimo (Contenedor)":
            if volumen_total_cbm > 0:
                # Usar exactamente 90 USD por m³
                costo_flete_total_usd = volumen_total_cbm * 90.0
                metodo_calculo = "90 USD/m³"
            else:
                costo_flete_total_usd = 0
                metodo_calculo = "Sin dimensiones válidas"
        
        # Calcular costo unitario - corregir variable
        flete_costo = costo_flete_total_usd / import_quantity if import_quantity > 0 else 0
        result['costo_flete_usd'] = flete_costo
        result['costo_flete_total_usd'] = costo_flete_total_usd
        
        # Actualizar shipping_details con los nuevos cálculos
        result['shipping_details'].update({
            "peso_total_kg": peso_total_kg,
            "peso_volumetrico_total_kg": peso_volumetrico_total_kg,
            "peso_facturable_kg": peso_facturable_kg,
            "volumen_unitario_cbm": volumen_unitario_cbm,
            "volumen_total_cbm": volumen_total_cbm,
            "metodo_calculo_flete": metodo_calculo
        })

        # 3. Recalcular honorarios (dependen del precio)
        honorarios_despachante = new_price * 0.02
        result['honorarios_despachante'] = honorarios_despachante

        # 4. Recalcular el costo total final
        landed_cost = new_price + float(tax_result.total_impuestos) + flete_costo + honorarios_despachante
        result['landed_cost'] = landed_cost
        
        st.success(f"✅ Recalculado - Nuevo Landing Cost: ${landed_cost:.2f} USD")

    except Exception as e:
        st.error(f"Error recalculando: {str(e)}")

def generate_excel_report(result):
    """
    Genera un reporte Excel profesional y detallado del landed cost
    
    Args:
        result: Diccionario con todos los datos del análisis
        
    Returns:
        bytes: Archivo Excel en memoria para descarga
    """
    if not EXCEL_AVAILABLE:
        raise ImportError("xlsxwriter no está disponible. Instala con: pip install xlsxwriter")
    
    # Crear buffer en memoria
    output = io.BytesIO()
    
    # Crear workbook y worksheet
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet('Landed Cost Analysis')
    
    # Definir formatos
    title_format = workbook.add_format({
        'bold': True, 'font_size': 16, 'align': 'center',
        'bg_color': '#2E4057', 'font_color': 'white'
    })
    
    header_format = workbook.add_format({
        'bold': True, 'font_size': 12,
        'bg_color': '#F0F0F0', 'border': 1
    })
    
    subheader_format = workbook.add_format({
        'bold': True, 'font_size': 11,
        'bg_color': '#E8E8E8', 'border': 1
    })
    
    currency_format = workbook.add_format({
        'num_format': '$#,##0.00', 'border': 1
    })
    
    percentage_format = workbook.add_format({
        'num_format': '0.0%', 'border': 1
    })
    
    text_format = workbook.add_format({
        'border': 1, 'text_wrap': True
    })
    
    highlight_format = workbook.add_format({
        'bold': True, 'bg_color': '#FFE6CC', 'border': 2,
        'num_format': '$#,##0.00'
    })
    
    # Variables de datos
    product = result['product']
    config = result['configuracion']
    ncm_result = result['ncm_result']
    tax_result = result['tax_result']
    shipping_details = result.get('shipping_details', {})
    ncm_official_info = ncm_result.get('ncm_official_info', {})
    courier_info = ncm_result.get('regimen_simplificado_courier', {})
    
    row = 0
    
    # 1. TÍTULO PRINCIPAL
    worksheet.merge_range(row, 0, row, 6, f'ANÁLISIS DE LANDED COST - {product.title}', title_format)
    row += 2
    
    # 2. INFORMACIÓN EJECUTIVA
    worksheet.write(row, 0, 'RESUMEN EJECUTIVO', header_format)
    worksheet.merge_range(row, 1, row, 6, '', header_format)
    row += 1
    
    executive_data = [
        ['Fecha de Análisis', datetime.now().strftime('%d/%m/%Y %H:%M')],
        ['Producto', product.title],
        ['Cantidad a Importar', f"{config.get('import_quantity', 1)} unidades"],
        ['Precio FOB Unitario', f"${result['precio_base']:.2f} USD"],
        ['Tipo de Cambio', f"${config.get('cotizacion_dolar', 0):.2f} ARS/USD"],
        ['LANDED COST UNITARIO', f"${result['landed_cost']:.2f} USD"],
        ['LANDED COST en ARS', f"${result['landed_cost'] * config.get('cotizacion_dolar', 1):,.0f} ARS"],
        ['COSTO TOTAL IMPORTACIÓN', f"${result['landed_cost'] * config.get('import_quantity', 1):,.2f} USD"]
    ]
    
    for data in executive_data:
        worksheet.write(row, 0, data[0], text_format)
        if 'LANDED COST' in data[0] or 'COSTO TOTAL' in data[0]:
            worksheet.write(row, 1, data[1], highlight_format)
        else:
            worksheet.write(row, 1, data[1], text_format)
        row += 1
    
    row += 1
    
    # 3. DESGLOSE DETALLADO DE COSTOS
    worksheet.write(row, 0, 'DESGLOSE DETALLADO DE COSTOS', header_format)
    worksheet.merge_range(row, 1, row, 6, '', header_format)
    row += 1
    
    # Headers de la tabla de costos
    cost_headers = ['Concepto', 'Base Imponible USD', 'Alícuota/Tasa', 'Monto USD', 'Monto ARS', '% del Total']
    for col, header in enumerate(cost_headers):
        worksheet.write(row, col, header, subheader_format)
    row += 1
    
    # Datos de costos
    cotizacion = config.get('cotizacion_dolar', 1)
    landed_cost = result['landed_cost']
    
    cost_items = [
        ['Precio Producto (FOB)', result['precio_base'], '-', result['precio_base'], result['precio_base'] * cotizacion, (result['precio_base'] / landed_cost) * 100],
        ['SUBTOTAL CIF', result['precio_base'], '-', result['precio_base'], result['precio_base'] * cotizacion, (result['precio_base'] / landed_cost) * 100]
    ]
    
    # Agregar impuestos individuales
    for impuesto in tax_result.impuestos:
        if impuesto.aplica:
            cost_items.append([
                impuesto.nombre,
                float(impuesto.base_imponible),
                f"{float(impuesto.alicuota):.2%}",
                float(impuesto.monto),
                float(impuesto.monto) * cotizacion,
                (float(impuesto.monto) / landed_cost) * 100
            ])
    
    # Agregar flete y servicios
    flete_costo = result.get('costo_flete_usd', 0)
    honorarios = config.get('honorarios_despachante', 0)
    
    cost_items.extend([
        [f"Flete {config.get('tipo_flete', 'Estimado')}", result['precio_base'], '-', flete_costo, flete_costo * cotizacion, (flete_costo / landed_cost) * 100],
        ['Honorarios Despachante', result['precio_base'], '2.0%', honorarios, honorarios * cotizacion, (honorarios / landed_cost) * 100],
        ['TOTAL LANDED COST', '-', '-', landed_cost, landed_cost * cotizacion, 100.0]
    ])
    
    # Escribir datos de costos
    for item in cost_items:
        for col, value in enumerate(item):
            if col == 0:  # Concepto
                format_to_use = highlight_format if 'TOTAL' in str(value) else text_format
                worksheet.write(row, col, value, format_to_use)
            elif col == 1 and isinstance(value, (int, float)) and value > 0:  # Base imponible
                worksheet.write(row, col, value, currency_format)
            elif col == 2:  # Alícuota
                worksheet.write(row, col, value, text_format)
            elif col in [3, 4]:  # Montos
                format_to_use = highlight_format if 'TOTAL' in str(item[0]) else currency_format
                worksheet.write(row, col, value, format_to_use)
            elif col == 5:  # Porcentaje
                format_to_use = highlight_format if 'TOTAL' in str(item[0]) else percentage_format
                worksheet.write(row, col, value / 100, format_to_use)
        row += 1
    
    row += 1
    
    # 4. INFORMACIÓN DEL PRODUCTO Y ENVÍO
    worksheet.write(row, 0, 'INFORMACIÓN DEL PRODUCTO', header_format)
    worksheet.merge_range(row, 1, row, 3, '', header_format)
    worksheet.write(row, 4, 'DATOS DE ENVÍO', header_format)
    worksheet.merge_range(row, 5, row, 6, '', header_format)
    row += 1
    
    # Información del producto (columna izquierda)
    product_info = [
        ['Marca', getattr(product, 'brand_name', 'N/A')],
        ['País de Origen', getattr(product, 'place_of_origin', 'N/A')],
        ['Categorías', ', '.join(getattr(product, 'categories', []))],
        ['MOQ', f"{getattr(product, 'moq', 'N/A')} unidades"],
        ['URL Producto', getattr(product, 'url', 'N/A')]
    ]
    
    # Datos de envío (columna derecha)
    dims = shipping_details.get('dimensions_cm', {})
    shipping_info = [
        ['Peso Estimado', f"{shipping_details.get('weight_kg', 'N/A')} kg"],
        ['Dimensiones L×W×H', f"{dims.get('length', 'N/A')} × {dims.get('width', 'N/A')} × {dims.get('height', 'N/A')} cm"],
        ['Volumen Cúbico', f"{(dims.get('length', 0) * dims.get('width', 0) * dims.get('height', 0)) / 1_000_000:.6f} m³" if all(dims.values()) else 'N/A'],
        ['Método Estimación', shipping_details.get('method', 'N/A')],
        ['Tipo de Flete', config.get('tipo_flete', 'N/A')]
    ]
    
    start_row = row
    for i, (info, shipping) in enumerate(zip(product_info, shipping_info)):
        # Producto
        worksheet.write(row, 0, info[0], text_format)
        worksheet.merge_range(row, 1, row, 3, info[1], text_format)
        # Envío
        worksheet.write(row, 4, shipping[0], text_format)
        worksheet.merge_range(row, 5, row, 6, shipping[1], text_format)
        row += 1
    
    row += 1
    
    # 5. CLASIFICACIÓN ARANCELARIA (NCM)
    worksheet.write(row, 0, 'CLASIFICACIÓN ARANCELARIA Y REGULACIONES', header_format)
    worksheet.merge_range(row, 1, row, 6, '', header_format)
    row += 1
    
    ncm_data = [
        ['Posición NCM', ncm_result.get('ncm_completo', 'N/A')],
        ['Descripción NCM', ncm_result.get('ncm_descripcion', 'N/A')],
        ['Confianza IA', f"{ncm_result.get('confianza', 'N/A')}"],
        ['Match Oficial', "✅ Exacto" if ncm_official_info.get('match_exacto') else "❌ No encontrado"],
        ['Fuente de Datos', f"{'🇦🇷 Base Oficial NCM' if ncm_official_info.get('match_exacto') else '🤖 IA'}"],
        ['Intervenciones Requeridas', ', '.join(ncm_result.get('intervenciones_requeridas', [])) or 'Ninguna'],
        ['Régimen Courier', courier_info.get('aplica_final', 'N/A')],
        ['Justificación Régimen', courier_info.get('justificacion_combinada', 'N/A')[:200] + '...' if len(courier_info.get('justificacion_combinada', '')) > 200 else courier_info.get('justificacion_combinada', 'N/A')]
    ]
    
    for data in ncm_data:
        worksheet.write(row, 0, data[0], text_format)
        worksheet.merge_range(row, 1, row, 6, data[1], text_format)
        row += 1
    
    row += 1
    
    # 6. CONFIGURACIÓN TÉCNICA
    worksheet.write(row, 0, 'CONFIGURACIÓN DEL CÁLCULO', header_format)
    worksheet.merge_range(row, 1, row, 6, '', header_format)
    row += 1
    
    config_data = [
        ['Tipo de Importador', config.get('tipo_importador', 'N/A')],
        ['Destino de Importación', config.get('destino_importacion', 'N/A')],
        ['Provincia', config.get('provincia', 'N/A')],
        ['Cotización USD/ARS', f"${config.get('cotizacion_dolar', 0):.2f}"],
        ['Fuente de Datos', st.session_state.entry_mode],
        ['Sistema', 'AI Comercio Exterior v3.1']
    ]
    
    for data in config_data:
        worksheet.write(row, 0, data[0], text_format)
        worksheet.merge_range(row, 1, row, 6, data[1], text_format)
        row += 1
    
    # Ajustar anchos de columna
    worksheet.set_column(0, 0, 25)  # Conceptos
    worksheet.set_column(1, 1, 15)  # Valores numéricos
    worksheet.set_column(2, 2, 12)  # Alícuotas
    worksheet.set_column(3, 3, 15)  # Montos USD
    worksheet.set_column(4, 4, 15)  # Montos ARS
    worksheet.set_column(5, 5, 10)  # Porcentajes
    worksheet.set_column(6, 6, 20)  # Información adicional
    
    # Cerrar workbook
    workbook.close()
    output.seek(0)
    
    return output.getvalue()

def render_detailed_breakdown_tab(result):
    """Renderiza el desglose detallado paso a paso siguiendo la metodología correcta"""
    st.markdown("## 🔍 Desglose Detallado del Landed Cost")
    st.markdown("*Siguiendo la metodología profesional de importaciones*")
    
    # Obtener datos básicos
    import_quantity = result['configuracion'].get('import_quantity', 1)
    precio_unitario = result['precio_base']
    tax_result = result['tax_result']
    cotizacion = result['configuracion'].get('cotizacion_dolar', 1000)
    flete_unitario = result['costo_flete_usd']
    honorarios_unitario = result['configuracion'].get('honorarios_despachante', 0)
    
    # PASO 1: FOB (Free On Board)
    st.markdown("### 📦 PASO 1: Valor FOB (Free On Board)")
    st.markdown("""
    **Definición:** El valor FOB incluye el costo del producto más todos los gastos en origen 
    (embalaje, documentación, carga al medio de transporte, etc.)
    """)
    
    fob_unitario = precio_unitario
    fob_total = fob_unitario * import_quantity
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("FOB Unitario", f"${fob_unitario:.2f} USD")
        st.metric("Cantidad a Importar", f"{import_quantity} unidades")
    with col2:
        st.metric("FOB Total", f"${fob_total:.2f} USD", help="FOB Unitario × Cantidad")
        st.metric("FOB Total (ARS)", f"${fob_total * cotizacion:,.0f} ARS")
    
    st.markdown("**Cálculo:** FOB Total = FOB Unitario × Cantidad")
    st.code(f"FOB Total = ${fob_unitario:.2f} × {import_quantity} = ${fob_total:.2f} USD")
    
    # PASO 2: CIF (Cost, Insurance & Freight)
    st.markdown("### 🚢 PASO 2: Valor CIF (Cost, Insurance & Freight)")
    st.markdown("""
    **Definición:** El valor CIF es el FOB más los costos de flete internacional y seguro.
    Este valor se convierte en el **Valor en Aduana** sobre el cual se calculan derechos y tasas.
    """)
    
    # Calcular flete total real considerando economías de escala
    peso_total_kg = result['shipping_details'].get('weight_kg', 1.0) * import_quantity
    dims = result['shipping_details'].get('dimensions_cm', {})
    tipo_flete = result['configuracion'].get('tipo_flete', 'Courier (Aéreo)')
    
    if tipo_flete == "Courier (Aéreo)":
        st.markdown(f"**Cálculo de Flete Aéreo:** Peso total = {peso_total_kg:.2f} kg")
    elif tipo_flete == "Marítimo (Contenedor)" and all(d > 0 for d in dims.values()):
        volumen_unitario = (dims['length'] * dims['width'] * dims['height']) / 1_000_000
        volumen_total = volumen_unitario * import_quantity
        st.markdown(f"**Cálculo de Flete Marítimo:** Volumen total = {volumen_total:.6f} m³")
    
    flete_total = result.get('flete_costo_total', flete_unitario * import_quantity)
    seguro_total = fob_total * 0.005  # 0.5% típico para seguro
    cif_total = fob_total + flete_total + seguro_total
    cif_unitario = cif_total / import_quantity
    
    # Mostrar desglose del CIF
    cif_breakdown = pd.DataFrame([
        {"Concepto": "FOB Total", "Valor USD": f"${fob_total:.2f}", "Descripción": "Costo del producto en origen"},
        {"Concepto": "Flete Internacional", "Valor USD": f"${flete_total:.2f}", "Descripción": "Transporte hasta destino"},
        {"Concepto": "Seguro", "Valor USD": f"${seguro_total:.2f}", "Descripción": "Cobertura de la mercadería (0.5%)"},
        {"Concepto": "TOTAL CIF", "Valor USD": f"${cif_total:.2f}", "Descripción": "Valor en Aduana"}
    ])
    
    st.dataframe(cif_breakdown, use_container_width=True, hide_index=True)
    
    st.metric("**Valor en Aduana (CIF)**", f"${cif_total:.2f} USD", 
              help="Este es el valor sobre el cual se calculan derechos y tasa estadística")
    
    st.markdown("**Cálculo:** CIF = FOB + Flete + Seguro")
    st.code(f"CIF = ${fob_total:.2f} + ${flete_total:.2f} + ${seguro_total:.2f} = ${cif_total:.2f} USD")
    
    # PASO 3: Derechos de Importación y Tasa Estadística
    st.markdown("### 🏛️ PASO 3: Derechos de Importación y Tasa Estadística")
    st.markdown("""
    **Definición:** Estos impuestos se calculan sobre el **Valor en Aduana (CIF)**.
    Son los primeros tributos que se aplican en el proceso de nacionalización.
    """)
    
    # Encontrar derechos de importación y tasa estadística
    derechos_monto = 0
    tasa_estadistica_monto = 0
    derechos_alicuota = 0
    tasa_estadistica_alicuota = 3.0  # Estándar 3%
    
    for impuesto in tax_result.impuestos:
        if impuesto.aplica:
            if "derechos" in impuesto.nombre.lower() or "importacion" in impuesto.nombre.lower():
                derechos_monto = float(impuesto.monto) * import_quantity
                derechos_alicuota = float(impuesto.alicuota) * 100
            elif "estadistica" in impuesto.nombre.lower() or "tasa" in impuesto.nombre.lower():
                tasa_estadistica_monto = float(impuesto.monto) * import_quantity
    
    # Si no encontramos tasa estadística, calcularla
    if tasa_estadistica_monto == 0:
        tasa_estadistica_monto = cif_total * 0.03
    
    valor_despues_derechos = cif_total + derechos_monto + tasa_estadistica_monto
    
    derechos_breakdown = pd.DataFrame([
        {"Concepto": "Valor en Aduana (CIF)", "Base Cálculo": f"${cif_total:.2f}", "Alícuota": "-", "Monto USD": f"${cif_total:.2f}"},
        {"Concepto": "Derechos de Importación", "Base Cálculo": f"${cif_total:.2f}", "Alícuota": f"{derechos_alicuota:.1f}%", "Monto USD": f"${derechos_monto:.2f}"},
        {"Concepto": "Tasa Estadística", "Base Cálculo": f"${cif_total:.2f}", "Alícuota": f"{tasa_estadistica_alicuota:.1f}%", "Monto USD": f"${tasa_estadistica_monto:.2f}"},
        {"Concepto": "SUBTOTAL", "Base Cálculo": "-", "Alícuota": "-", "Monto USD": f"${valor_despues_derechos:.2f}"}
    ])
    
    st.dataframe(derechos_breakdown, use_container_width=True, hide_index=True)
    
    st.markdown("**Cálculos:**")
    st.code(f"""
Derechos de Importación = ${cif_total:.2f} × {derechos_alicuota:.1f}% = ${derechos_monto:.2f} USD
Tasa Estadística = ${cif_total:.2f} × {tasa_estadistica_alicuota:.1f}% = ${tasa_estadistica_monto:.2f} USD
    """)
    
    # PASO 4: Base IVA y otros impuestos
    st.markdown("### 💹 PASO 4: Base IVA y Otros Impuestos")
    st.markdown("""
    **Definición:** La Base IVA se calcula como: CIF + Derechos + Tasa Estadística.
    Sobre esta base se calculan: IVA, IVA Adicional, Impuesto a las Ganancias e Ingresos Brutos.
    """)
    
    base_iva = valor_despues_derechos
    
    # Encontrar otros impuestos
    iva_monto = 0
    iva_adicional_monto = 0
    ganancias_monto = 0
    iibb_monto = 0
    
    for impuesto in tax_result.impuestos:
        if impuesto.aplica:
            monto_total = float(impuesto.monto) * import_quantity
            nombre_lower = impuesto.nombre.lower()
            
            if "iva" in nombre_lower and "adicional" not in nombre_lower:
                iva_monto = monto_total
                iva_alicuota = float(impuesto.alicuota) * 100
            elif "adicional" in nombre_lower:
                iva_adicional_monto = monto_total
                iva_adicional_alicuota = float(impuesto.alicuota) * 100
            elif "ganancias" in nombre_lower:
                ganancias_monto = monto_total
                ganancias_alicuota = float(impuesto.alicuota) * 100
            elif "brutos" in nombre_lower or "iibb" in nombre_lower:
                iibb_monto = monto_total
                iibb_alicuota = float(impuesto.alicuota) * 100
    
    total_impuestos_iva = iva_monto + iva_adicional_monto + ganancias_monto + iibb_monto
    valor_despues_impuestos = base_iva + total_impuestos_iva
    
    impuestos_breakdown = pd.DataFrame([
        {"Concepto": "Base IVA", "Base Cálculo": "-", "Alícuota": "-", "Monto USD": f"${base_iva:.2f}"},
        {"Concepto": "IVA General", "Base Cálculo": f"${base_iva:.2f}", "Alícuota": f"{iva_alicuota:.1f}%" if 'iva_alicuota' in locals() else "21.0%", "Monto USD": f"${iva_monto:.2f}"},
        {"Concepto": "IVA Adicional", "Base Cálculo": f"${base_iva:.2f}", "Alícuota": f"{iva_adicional_alicuota:.1f}%" if 'iva_adicional_alicuota' in locals() else "0.0%", "Monto USD": f"${iva_adicional_monto:.2f}"},
        {"Concepto": "Imp. Ganancias", "Base Cálculo": f"${base_iva:.2f}", "Alícuota": f"{ganancias_alicuota:.1f}%" if 'ganancias_alicuota' in locals() else "6.0%", "Monto USD": f"${ganancias_monto:.2f}"},
        {"Concepto": "Ingresos Brutos", "Base Cálculo": f"${base_iva:.2f}", "Alícuota": f"{iibb_alicuota:.1f}%" if 'iibb_alicuota' in locals() else "3.0%", "Monto USD": f"${iibb_monto:.2f}"},
        {"Concepto": "SUBTOTAL con Impuestos", "Base Cálculo": "-", "Alícuota": "-", "Monto USD": f"${valor_despues_impuestos:.2f}"}
    ])
    
    st.dataframe(impuestos_breakdown, use_container_width=True, hide_index=True)
    
    st.metric("**Base IVA**", f"${base_iva:.2f} USD", 
              help="CIF + Derechos + Tasa Estadística = Base sobre la cual se calculan los demás impuestos")
    
    # PASO 5: Otros Costos
    st.markdown("### 💼 PASO 5: Otros Costos de Nacionalización")
    st.markdown("""
    **Definición:** Costos adicionales necesarios para completar la importación:
    despachante de aduana, almacenaje, otros gastos portuarios.
    """)
    
    honorarios_total = honorarios_unitario * import_quantity
    otros_gastos = 0  # Puedes expandir esto si tienes más gastos
    
    otros_costos = pd.DataFrame([
        {"Concepto": "Honorarios Despachante", "Cálculo": f"${precio_unitario:.2f} × 2% × {import_quantity}", "Monto USD": f"${honorarios_total:.2f}"},
        {"Concepto": "Otros Gastos", "Cálculo": "Almacenaje, gestiones, etc.", "Monto USD": f"${otros_gastos:.2f}"},
        {"Concepto": "TOTAL Otros Costos", "Cálculo": "-", "Monto USD": f"${honorarios_total + otros_gastos:.2f}"}
    ])
    
    st.dataframe(otros_costos, use_container_width=True, hide_index=True)
    
    # PASO 6: LANDED COST FINAL
    st.markdown("### 🎯 PASO 6: LANDED COST TOTAL")
    st.markdown("""
    **Definición:** El costo final que incluye todos los gastos necesarios para tener el producto 
    disponible en destino, listo para la venta.
    """)
    
    landed_cost_total = valor_despues_impuestos + honorarios_total + otros_gastos
    landed_cost_unitario_final = landed_cost_total / import_quantity
    
    # Resumen final
    resumen_final = pd.DataFrame([
        {"Etapa": "FOB Total", "Descripción": "Costo del producto en origen", "Monto USD": f"${fob_total:.2f}", "% del Total": f"{(fob_total/landed_cost_total)*100:.1f}%"},
        {"Etapa": "CIF (Valor Aduana)", "Descripción": "FOB + Flete + Seguro", "Monto USD": f"${cif_total:.2f}", "% del Total": f"{(cif_total/landed_cost_total)*100:.1f}%"},
        {"Etapa": "Derechos y Tasas", "Descripción": "Impuestos sobre CIF", "Monto USD": f"${derechos_monto + tasa_estadistica_monto:.2f}", "% del Total": f"{((derechos_monto + tasa_estadistica_monto)/landed_cost_total)*100:.1f}%"},
        {"Etapa": "Impuestos Internos", "Descripción": "IVA, Ganancias, IIBB", "Monto USD": f"${total_impuestos_iva:.2f}", "% del Total": f"{(total_impuestos_iva/landed_cost_total)*100:.1f}%"},
        {"Etapa": "Otros Costos", "Descripción": "Despachante, gestiones", "Monto USD": f"${honorarios_total + otros_gastos:.2f}", "% del Total": f"{((honorarios_total + otros_gastos)/landed_cost_total)*100:.1f}%"},
        {"Etapa": "LANDED COST TOTAL", "Descripción": f"Para {import_quantity} unidades", "Monto USD": f"${landed_cost_total:.2f}", "% del Total": "100.0%"}
    ])
    
    # Aplicar estilo al resumen
    def highlight_total(row):
        if "TOTAL" in row['Etapa']:
            return ['background-color: #28a745; color: white; font-weight: bold'] * len(row)
        else:
            return [''] * len(row)
    
    st.dataframe(
        resumen_final.style.apply(highlight_total, axis=1),
        use_container_width=True,
        hide_index=True
    )
    
    # Métricas finales destacadas
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("**Landed Cost Total**", f"${landed_cost_total:.2f} USD")
    with col2:
        st.metric("**Landed Cost Unitario**", f"${landed_cost_unitario_final:.2f} USD")
    with col3:
        markup_percent = ((landed_cost_unitario_final - fob_unitario) / fob_unitario) * 100
        st.metric("**Markup Total**", f"{markup_percent:.1f}%", help="Incremento sobre el precio FOB original")
    
    # Equivalencia en ARS
    st.markdown("#### 💵 Equivalencia en Pesos Argentinos")
    st.metric("Landed Cost Total (ARS)", f"${landed_cost_total * cotizacion:,.0f} ARS", 
              help=f"Cotización utilizada: ${cotizacion:.2f} ARS/USD")

def render_executive_summary_tab(result):
    # Aquí puedes agregar el contenido de la tab de resumen ejecutivo
    pass

def validate_and_clean_json_credentials(credentials_raw):
    """
    Valida y limpia las credenciales JSON de Google Service Account.
    
    Args:
        credentials_raw: String crudo del JSON de credenciales
        
    Returns:
        dict: JSON parseado y validado, o None si hay error
    """
    try:
        import re
        
        # Limpiar caracteres de control inválidos excepto \n, \r, \t
        credentials_clean = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', credentials_raw)
        
        # Remover espacios en blanco al inicio y final
        credentials_clean = credentials_clean.strip()
        
        # Intentar parsear el JSON
        credentials_json = json.loads(credentials_clean)
        
        # Validar campos requeridos
        required_fields = ["type", "project_id", "private_key", "client_email"]
        missing_fields = [field for field in required_fields if field not in credentials_json]
        
        if missing_fields:
            raise ValueError(f"Faltan campos requeridos: {missing_fields}")
        
        # Validar que sea un service account
        if credentials_json.get("type") != "service_account":
            raise ValueError("El tipo de credencial debe ser 'service_account'")
        
        return credentials_json
        
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON inválido: {e}")
    except Exception as e:
        raise ValueError(f"Error validando credenciales: {e}")

def get_gspread_client():
    """Obtener cliente de Google Sheets usando las credenciales del secrets."""
    try:
        # Obtener las credenciales del secrets
        credentials_raw = st.secrets["google_service_account"]["credentials"]
        
        # Validar y limpiar las credenciales
        try:
            credentials_json = validate_and_clean_json_credentials(credentials_raw)
        except ValueError as validation_error:
            st.error(f"Error en las credenciales de Google Sheets: {validation_error}")
            st.error("Verifica que el JSON de credenciales en secrets.toml esté bien formateado")
            
            # Mostrar información de debug si estamos en modo debug
            if st.secrets.get("settings", {}).get("DEBUG_MODE", False):
                st.error(f"JSON problemático (primeros 200 chars): {credentials_raw[:200]}...")
            
            return None
        
        # Definir los scopes necesarios
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        
        # Crear las credenciales
        credentials = Credentials.from_service_account_info(credentials_json, scopes=scopes)
        
        # Crear el cliente de gspread
        gc = gspread.authorize(credentials)
        
        return gc
        
    except KeyError as e:
        st.error(f"No se encontraron las credenciales de Google Sheets en secrets: {e}")
        st.error("Asegúrate de configurar 'google_service_account.credentials' en .streamlit/secrets.toml")
        return None
    except Exception as e:
        st.error(f"Error al conectar con Google Sheets: {e}")
        
        # Mostrar más detalles del error en modo debug
        if st.secrets.get("settings", {}).get("DEBUG_MODE", False):
            st.error(f"Detalles del error: {traceback.format_exc()}")
        
        return None

def upload_to_google_sheets(data_dict, worksheet_name="Cotizaciones APP IA"):
    """
    Subir datos a Google Sheets.
    
    Args:
        data_dict: Diccionario con los datos de la cotización
        worksheet_name: Nombre de la hoja de cálculo
        
    Returns:
        bool: True si se subió correctamente, False en caso de error
    """
    try:
        # Obtener el cliente de Google Sheets
        gc = get_gspread_client()
        if not gc:
            st.error("❌ No se pudo obtener el cliente de Google Sheets")
            return False
        
        # Abrir o crear la hoja de cálculo
        try:
            sh = create_or_open_spreadsheet(gc, worksheet_name)
            st.info(f"📊 Conectado a la hoja: {worksheet_name}")
        except Exception as sheet_error:
            st.error(f"❌ Error al acceder/crear la hoja '{worksheet_name}': {sheet_error}")
            return False
        
        # Seleccionar la primera hoja
        worksheet = sh.sheet1
        
        # Convertir los datos a formato de fila
        row_data = [
            data_dict.get("fecha", ""),
            data_dict.get("producto", ""),
            "",  # Espacio para la imagen, se actualizará después con la fórmula
            data_dict.get("url_producto", ""),
            data_dict.get("cantidad", ""),
            data_dict.get("precio_unitario_fob", ""),
            data_dict.get("subtotal_fob", ""),
            data_dict.get("moneda", ""),
            data_dict.get("tipo_cambio", ""),
            data_dict.get("derechos_importacion_pct", ""),
            data_dict.get("derechos_importacion", ""),
            data_dict.get("tasa_estadistica_pct", ""),
            data_dict.get("tasa_estadistica", ""),
            data_dict.get("iva_importacion_pct", ""),
            data_dict.get("iva_importacion", ""),
            data_dict.get("percepcion_iva_pct", ""),
            data_dict.get("percepcion_iva", ""),
            data_dict.get("percepcion_ganancias_pct", ""),
            data_dict.get("percepcion_ganancias", ""),
            data_dict.get("ingresos_brutos_pct", ""),
            data_dict.get("ingresos_brutos", ""),
            data_dict.get("total_impuestos", ""),
            data_dict.get("subtotal_con_impuestos", ""),
            data_dict.get("costo_flete_unitario", ""),
            data_dict.get("costo_flete_total", ""),
            data_dict.get("honorarios_despachante", ""),
            data_dict.get("total_landed_cost", ""),
            data_dict.get("total_landed_cost_ars", ""),
            data_dict.get("ncm", ""),
            data_dict.get("descripcion_ncm", ""),
            data_dict.get("confianza_ia", ""),
            data_dict.get("peso_unitario_kg", ""),
            data_dict.get("dimensiones", ""),
            data_dict.get("metodo_flete", ""),
            data_dict.get("origen", ""),
            data_dict.get("destino", ""),
            data_dict.get("tipo_importador", ""),
            data_dict.get("provincia", ""),
            data_dict.get("notas", "")
        ]
        
        # Verificar si ya existen encabezados
        headers_exist = False
        try:
            first_cell = worksheet.cell(1, 1).value
            if first_cell == "Fecha":
                headers_exist = True
        except:
            pass
        
        # Si no existen encabezados, agregarlos primero
        if not headers_exist:
            headers = [
                "Fecha", "Producto", "Imagen", "URL", "Cantidad", "Precio Unitario FOB", "Subtotal FOB",
                "Moneda", "Tipo de Cambio", "Derechos de Importación %", "Derechos de Importación",
                "Tasa Estadística %", "Tasa Estadística", "IVA Importación %", "IVA Importación",
                "Percepción IVA %", "Percepción IVA", "Percepción Ganancias %", "Percepción Ganancias",
                "Ingresos Brutos %", "Ingresos Brutos", "Total Impuestos", "Subtotal con Impuestos",
                "Costo Flete Unitario", "Costo Flete Total", "Honorarios Despachante", "Total Landed Cost",
                "Total Landed Cost ARS", "NCM", "Descripción NCM", "Confianza IA %", "Peso Unitario (kg)",
                "Dimensiones (L×W×H cm)", "Método Flete", "Origen", "Destino", "Tipo Importador", "Provincia", "Notas"
            ]
            worksheet.append_row(headers)
        
        # Agregar los datos
        try:
            worksheet.append_row(row_data)
            st.success("✅ Datos agregados exitosamente a la hoja")
        except Exception as data_error:
            st.error(f"❌ Error al agregar datos: {data_error}")
            return False
        
        # Actualizar la fórmula de imagen en la última fila agregada
        # La imagen está en la columna C (índice 3)
        try:
            if data_dict.get("imagen_url", ""):
                # Obtener el número de la última fila
                num_rows = worksheet.row_count
                # Actualizar la celda con la fórmula IMAGE
                image_formula = f'=IMAGE("{data_dict.get("imagen_url", "")}")'
                worksheet.update(f'C{num_rows}', image_formula)
                st.info("✅ Fórmula de imagen agregada")
        except Exception as image_error:
            st.warning(f"⚠️ No se pudo agregar la imagen: {image_error}")
            # No retornar False aquí porque los datos principales ya se subieron
        
        # Obtener la URL de la hoja para mostrarla al usuario
        try:
            sheet_url = sh.url
            st.info(f"📋 Ver hoja: {sheet_url}")
        except:
            pass
        
        return True
    except Exception as e:
        st.error(f"❌ Error general al subir datos a Google Sheets: {e}")
        
        # Mostrar más detalles del error en modo debug
        if st.secrets.get("settings", {}).get("DEBUG_MODE", False):
            st.error(f"Detalles del error: {traceback.format_exc()}")
        
        return False

def test_google_sheets_connection():
    """
    Función de prueba para verificar la conexión a Google Sheets y subir datos de ejemplo.
    
    Returns:
        bool: True si la prueba fue exitosa, False en caso contrario
    """
    try:
        st.info("🔄 Iniciando prueba de conexión a Google Sheets...")
        
        # Obtener el cliente de Google Sheets
        gc = get_gspread_client()
        if not gc:
            st.error("❌ No se pudo obtener el cliente de Google Sheets")
            return False
        
        st.success("✅ Cliente de Google Sheets obtenido correctamente")
        
        # Nombre de la hoja de prueba (usando la hoja existente del usuario)
        test_sheet_name = "Cotizaciones APP IA"
        
        # Intentar abrir la hoja, si no existe, crearla
        try:
            sh = gc.open(test_sheet_name)
            st.info(f"📊 Hoja '{test_sheet_name}' encontrada")
        except gspread.SpreadsheetNotFound:
            st.info(f"📊 Creando nueva hoja '{test_sheet_name}'...")
            sh = gc.create(test_sheet_name)
            # Hacer la hoja pública para que puedas verla
            sh.share('', perm_type='anyone', role='reader')
            st.success(f"✅ Hoja '{test_sheet_name}' creada exitosamente")
        
        # Obtener la primera worksheet
        worksheet = sh.sheet1
        
        # Limpiar la hoja y agregar encabezados de prueba
        worksheet.clear()
        
        headers = [
            "Timestamp", "Producto", "Precio FOB", "NCM", "Total Impuestos", 
            "Landed Cost", "Estado", "Origen", "Destino"
        ]
        
        worksheet.append_row(headers)
        st.success("✅ Encabezados agregados")
        
        # Datos de prueba
        test_data = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Producto de Prueba - Smartphone",
            "$150.00",
            "8517.12.00",
            "$45.30",
            "$195.30",
            "Prueba Exitosa",
            "China",
            "Argentina"
        ]
        
        # Subir datos de prueba
        worksheet.append_row(test_data)
        st.success("✅ Datos de prueba subidos exitosamente")
        
        # Obtener la URL de la hoja para mostrarla al usuario
        sheet_url = sh.url
        st.success(f"🎉 Prueba completada exitosamente!")
        st.info(f"📋 Puedes ver la hoja aquí: {sheet_url}")
        
        return True
        
    except Exception as e:
        st.error(f"❌ Error durante la prueba: {e}")
        
        # Mostrar más detalles del error en modo debug
        if st.secrets.get("settings", {}).get("DEBUG_MODE", False):
            st.error(f"Detalles del error: {traceback.format_exc()}")
        
        return False

def create_or_open_spreadsheet(gc, spreadsheet_name):
    """
    Abre una hoja de cálculo existente o crea una nueva si no existe.
    
    Args:
        gc: Cliente de gspread
        spreadsheet_name: Nombre de la hoja de cálculo
        
    Returns:
        gspread.Spreadsheet: La hoja de cálculo
    """
    try:
        # Intentar abrir la hoja existente
        sh = gc.open(spreadsheet_name)
        st.info(f"📊 Hoja existente '{spreadsheet_name}' encontrada")
        return sh
    except gspread.SpreadsheetNotFound:
        # Si no existe, intentar crear una nueva
        try:
            st.info(f"📊 Creando nueva hoja '{spreadsheet_name}'...")
            sh = gc.create(spreadsheet_name)
            # Hacer la hoja accesible
            sh.share('', perm_type='anyone', role='reader')
            st.success(f"✅ Hoja '{spreadsheet_name}' creada exitosamente")
            return sh
        except gspread.exceptions.APIError as api_error:
            if "quota has been exceeded" in str(api_error).lower():
                st.error("🚨 **ERROR DE CUOTA DE GOOGLE DRIVE**")
                st.error("La cuenta de Google Drive está llena. Soluciones:")
                st.markdown("""
                **Opciones para resolver esto:**
                1. **Liberar espacio**: Ve a [Google Drive](https://drive.google.com) y elimina archivos innecesarios
                2. **Usar otra cuenta**: Crea un nuevo Service Account con una cuenta de Google diferente
                3. **Usar hoja existente**: En lugar de crear nueva, usa una hoja que ya exista
                
                **Para crear una hoja manualmente:**
                1. Ve a [Google Sheets](https://sheets.google.com)
                2. Crea una nueva hoja llamada exactamente: `{spreadsheet_name}`
                3. Comparte la hoja con: `{gc.auth.service_account_email if hasattr(gc.auth, 'service_account_email') else 'el service account email'}`
                4. Dale permisos de Editor
                """)
                raise Exception(f"Cuota de Drive excedida. No se puede crear la hoja '{spreadsheet_name}'")
            else:
                st.error(f"❌ Error de API de Google: {api_error}")
                raise
    except Exception as e:
        st.error(f"❌ Error general al acceder/crear la hoja: {e}")
        raise

def render_google_sheets_test_tab():
    """Renderiza la tab de prueba de Google Sheets"""
    st.markdown("### 📊 Google Sheets - Pruebas y Configuración")
    
    st.markdown("""
    Esta sección te permite probar la conexión a Google Sheets y verificar que todo funcione correctamente.
    """)
    
    # Estado de la configuración
    st.markdown("#### 🔧 Estado de la Configuración")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Verificar credenciales
        try:
            credentials_raw = st.secrets["google_service_account"]["credentials"]
            credentials_json = validate_and_clean_json_credentials(credentials_raw)
            st.success("✅ Credenciales de Google válidas")
            st.info(f"📧 Service Account: {credentials_json.get('client_email', 'N/A')}")
            st.info(f"📋 Proyecto: {credentials_json.get('project_id', 'N/A')}")
        except Exception as e:
            st.error(f"❌ Error en credenciales: {e}")
    
    with col2:
        # Estado del cliente
        try:
            gc = get_gspread_client()
            if gc:
                st.success("✅ Cliente de Google Sheets conectado")
            else:
                st.error("❌ No se pudo conectar a Google Sheets")
        except Exception as e:
            st.error(f"❌ Error de conexión: {e}")
    
    st.divider()
    
    # Sección de pruebas
    st.markdown("#### 🧪 Pruebas de Funcionalidad")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🔗 Probar Conexión Básica", type="primary", use_container_width=True):
            test_google_sheets_connection()
    
    with col2:
        if st.button("🗑️ Limpiar Resultados", use_container_width=True):
            # Limpiar cualquier mensaje de estado anterior
            st.rerun()
    
    st.divider()
    
    # Sección de datos de prueba personalizados
    st.markdown("#### 🎯 Subir Datos de Prueba Personalizados")
    
    with st.form("test_data_form"):
        st.markdown("Completa los datos para hacer una prueba personalizada:")
        
        col1, col2 = st.columns(2)
        
        with col1:
            producto = st.text_input("Producto", value="Smartphone de Prueba")
            precio_fob = st.number_input("Precio FOB (USD)", value=150.0, min_value=0.0)
            ncm = st.text_input("NCM", value="8517.12.00")
            origen = st.selectbox("Origen", ["China", "Estados Unidos", "Alemania", "Japón"], index=0)
        
        with col2:
            cantidad = st.number_input("Cantidad", value=1, min_value=1)
            total_impuestos = st.number_input("Total Impuestos (USD)", value=45.0, min_value=0.0)
            destino = st.selectbox("Destino", ["Argentina", "Uruguay", "Chile", "Brasil"], index=0)
            notas = st.text_area("Notas", value="Datos de prueba generados desde la app")
        
        submitted = st.form_submit_button("📤 Subir Datos de Prueba", type="primary", use_container_width=True)
        
        if submitted:
            # Crear diccionario de datos de prueba
            test_data = {
                "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "producto": producto,
                "url_producto": "https://example.com/test-product",
                "cantidad": cantidad,
                "precio_unitario_fob": f"${precio_fob}",
                "subtotal_fob": f"${precio_fob * cantidad}",
                "moneda": "USD",
                "tipo_cambio": "1200",
                "derechos_importacion_pct": "35%",
                "derechos_importacion": f"${precio_fob * 0.35}",
                "tasa_estadistica_pct": "3%",
                "tasa_estadistica": f"${precio_fob * 0.03}",
                "iva_importacion_pct": "21%",
                "iva_importacion": f"${precio_fob * 0.21}",
                "percepcion_iva_pct": "10%",
                "percepcion_iva": f"${precio_fob * 0.10}",
                "percepcion_ganancias_pct": "5%",
                "percepcion_ganancias": f"${precio_fob * 0.05}",
                "ingresos_brutos_pct": "2%",
                "ingresos_brutos": f"${precio_fob * 0.02}",
                "total_impuestos": f"${total_impuestos}",
                "subtotal_con_impuestos": f"${precio_fob + total_impuestos}",
                "costo_flete_unitario": "$25.00",
                "costo_flete_total": f"${25 * cantidad}",
                "honorarios_despachante": "$100.00",
                "total_landed_cost": f"${precio_fob + total_impuestos + (25 * cantidad) + 100}",
                "total_landed_cost_ars": f"${(precio_fob + total_impuestos + (25 * cantidad) + 100) * 1200}",
                "ncm": ncm,
                "descripcion_ncm": "Descripción automática del NCM",
                "confianza_ia": "85%",
                "peso_unitario_kg": "0.5",
                "dimensiones": "15×7×1 cm",
                "metodo_flete": "Express",
                "origen": origen,
                "destino": destino,
                "tipo_importador": "Persona Física",
                "provincia": "Buenos Aires",
                "notas": notas,
                "imagen_url": "https://example.com/image.jpg"
            }
            
            # Intentar subir los datos
            with st.spinner("Subiendo datos de prueba..."):
                if upload_to_google_sheets(test_data, "Cotizaciones APP IA"):
                    st.success("🎉 ¡Datos de prueba subidos exitosamente!")
                else:
                    st.error("❌ Error al subir los datos de prueba")
    
    st.divider()
    
    # Información útil
    st.markdown("#### 📋 Información Útil")
    st.info("""
    **Consejos para usar Google Sheets:**
    
    1. **Permisos**: Asegúrate de que el Service Account tenga permisos para crear y editar hojas
    2. **Nombres**: Los nombres de las hojas son sensibles a mayúsculas y minúsculas  
    3. **Límites**: Google Sheets tiene límites de velocidad - no hagas muchas requests muy rápido
    4. **Formato**: Las fechas y números se formatean automáticamente según la configuración regional
    
    **En caso de problemas:**
    - Verifica que las credenciales en `secrets.toml` sean correctas
    - Asegúrate de que el Service Account tenga los scopes necesarios
    - Revisa que el proyecto de Google Cloud tenga la API de Sheets habilitada
    """)
    
    # Sección especial para problemas de cuota
    st.markdown("#### 🚨 Solución para Error de Cuota de Drive")
    
    with st.expander("Si ves 'Drive storage quota has been exceeded' - HAZ CLIC AQUÍ"):
        st.markdown("""
        ### 🔧 **Problema de Cuota Excedida - Solución Paso a Paso**
        
        **El problema:** La cuenta de Google Drive del Service Account está llena.
        
        **Solución Rápida (Recomendada):**
        
                 1. **Crea una hoja manualmente:**
            - Ve a [Google Sheets](https://sheets.google.com)
            - Crea una nueva hoja
            - Nómbrala exactamente: `Cotizaciones APP IA`
        
        2. **Comparte la hoja:**
           - Haz clic en "Compartir" (botón azul)
           - Agrega este email: `b3consulting@b3consulting.iam.gserviceaccount.com`
           - Dale permisos de **Editor**
           - Haz clic en "Enviar"
        
        3. **Prueba la conexión:**
           - Regresa aquí y haz clic en "🔗 Probar Conexión Básica"
           - Ahora debería funcionar correctamente
        
        **Otras soluciones:**
        - **Liberar espacio**: Ve a [Google Drive](https://drive.google.com) y elimina archivos
        - **Crear nuevo Service Account**: Con una cuenta de Google diferente
        """)
        
        # Botón directo para crear hoja
        st.markdown("**🚀 Enlaces Directos:**")
        col1, col2 = st.columns(2)
        with col1:
            st.link_button("📊 Crear Nueva Hoja", "https://sheets.google.com", use_container_width=True)
        with col2:
            st.link_button("🗂️ Ir a Google Drive", "https://drive.google.com", use_container_width=True)
    
    # Prueba con hoja existente
    st.markdown("#### 🔄 Probar con Hoja Existente")
    
    with st.form("existing_sheet_form"):
        st.markdown("Si ya tienes una hoja creada, puedes probarla aquí:")
        
        sheet_name = st.text_input(
            "Nombre de la hoja existente", 
            value="Cotizaciones APP IA",
            help="El nombre debe coincidir exactamente con el de Google Sheets"
        )
        
        if st.form_submit_button("🔗 Probar Hoja Existente", type="secondary", use_container_width=True):
            with st.spinner(f"Probando conexión con '{sheet_name}'..."):
                try:
                    gc = get_gspread_client()
                    if gc:
                        sh = gc.open(sheet_name)
                        st.success(f"✅ ¡Conexión exitosa con '{sheet_name}'!")
                        st.info(f"📋 URL de la hoja: {sh.url}")
                        
                        # Intentar escribir datos de prueba
                        worksheet = sh.sheet1
                        test_data = [
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "Producto de Prueba",
                            "$100.00",
                            "Test exitoso desde la app"
                        ]
                        worksheet.append_row(test_data)
                        st.success("✅ Datos de prueba agregados exitosamente")
                        
                    else:
                        st.error("❌ No se pudo obtener el cliente de Google Sheets")
                except gspread.SpreadsheetNotFound:
                    st.error(f"❌ No se encontró una hoja llamada '{sheet_name}'")
                    st.info("Verifica que el nombre sea exacto y que la hoja esté compartida con el Service Account")
                except Exception as e:
                    st.error(f"❌ Error: {e}")

if __name__ == "__main__":
    main() 