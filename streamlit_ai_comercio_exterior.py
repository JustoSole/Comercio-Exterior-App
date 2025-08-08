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
import json
import traceback
import os
import time as time_module
import requests
from urllib.parse import urlparse, urlunparse
import re
import asyncio
import io
import base64
import math
from PIL import Image

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

# Configuración de archivos de datos
CONFIG = {
    'NCM_DATA_FILE': "pdf_reader/ncm/resultados_ncm_hybrid/dataset_ncm_HYBRID_FIXED_20250807_125734.csv",
    'FREIGHT_RATES_FILE': "pdf_reader/dhl_carrier/extracted_tables.csv",
    'DEBUG_MODE': True,  # Control global de debug
    'MAX_DEBUG_LOGS': 50  # Reducir de 100 a 50 logs
}

# Imports de módulos reales
try:
    from alibaba_scraper import scrape_single_alibaba_product, extract_alibaba_pricing, format_pricing_for_display, calculate_total_cost_for_option, get_cheapest_price_option
    # NCM classification handled by ai_ncm_deep_classifier only
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
        st.session_state.freight_rates = load_freight_rates(CONFIG['FREIGHT_RATES_FILE'])
    if 'dhl_service' not in st.session_state:
        # Crear servicio DHL con callback de debug
        st.session_state.dhl_service = DHLFreightService(
            test_mode=True,  # Por defecto usar test mode
            use_dhl_real=True,  # Por defecto intentar usar DHL real
                            fallback_rates_file=CONFIG['FREIGHT_RATES_FILE'],
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
        "packaging_type": "individual",
        "box_dimensions_cm": {"length": 0.0, "width": 0.0, "height": 0.0},
        "box_total_weight_kg": 0.0,
        "units_per_box": 1,
            "image_url": "",
            "image_source": None,  # Nuevo campo para rastrear el origen de la imagen
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
            "postalCode": "C1000",  # Código postal de Buenos Aires (será normalizado automáticamente)
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
    
    # Inicializar información de debug NCM
    if 'ncm_debug_info' not in st.session_state:
        st.session_state.ncm_debug_info = {}
    # Configuración por defecto para la tab de margen
    if 'margin_config' not in st.session_state:
        st.session_state.margin_config = {
            "precio_venta_unit_usd": 0.0,
            "comision_venta_pct": 0.0
        }

def debug_log(message, data=None, level="INFO"):
    """Función de debug optimizada con control de rendimiento"""
    if not CONFIG['DEBUG_MODE'] or not st.session_state.get('debug_mode', True):
        return
    
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = {
        "timestamp": timestamp,
        "level": level,
        "message": str(message),
        "data": data if data and len(str(data)) < 500 else None,  # Limitar data grande
        "step": st.session_state.get('current_step', 'Unknown')
    }
    
    if 'debug_logs' not in st.session_state:
        st.session_state.debug_logs = []
    if 'console_output' not in st.session_state:
        st.session_state.console_output = []
    
    st.session_state.debug_logs.append(log_entry)
    
    # Console output solo para errores críticos
    if level in ["ERROR", "FATAL"]:
        console_msg = f"[{timestamp}] {level}: {message}"
        st.session_state.console_output.append(console_msg)
    
    # Limitar memoria más agresivamente
    max_logs = CONFIG['MAX_DEBUG_LOGS']
    if len(st.session_state.debug_logs) > max_logs:
        st.session_state.debug_logs = st.session_state.debug_logs[-max_logs:]
    if len(st.session_state.console_output) > max_logs:
        st.session_state.console_output = st.session_state.console_output[-max_logs:]

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

def _calculate_shipping_metrics(editable_data: dict, import_quantity: int) -> dict:
    """
    Calcula métricas de envío (peso, volumen, peso facturable) según el tipo de embalaje.
    
    Args:
        editable_data: Datos del producto que incluyen peso, dimensiones y tipo de embalaje
        import_quantity: Cantidad de unidades a importar
    
    Returns:
        Dict con todas las métricas de envío calculadas
    """
    packaging_type = editable_data.get('packaging_type', 'individual')
    
    if packaging_type == "individual":
        # EMBALAJE INDIVIDUAL: cada unidad en su propia caja
        peso_unitario_kg = float(editable_data.get('weight_kg', 0.0))
        dims = editable_data.get('dimensions_cm', {"length": 0.0, "width": 0.0, "height": 0.0})
        
        peso_total_kg = peso_unitario_kg * import_quantity
        
        if all(d > 0 for d in dims.values()):
            volumen_unitario_cbm = (dims['length'] * dims['width'] * dims['height']) / 1_000_000
            volumen_total_cbm = volumen_unitario_cbm * import_quantity
            peso_volumetrico_kg = volumen_total_cbm * 167
        else:
            volumen_total_cbm = 0
            peso_volumetrico_kg = 0
            
    else:  # multiple
        # EMBALAJE MÚLTIPLE: usar peso total de la caja y calcular número de cajas necesarias
        units_per_box = editable_data.get('units_per_box', 1)
        box_dims = editable_data.get('box_dimensions_cm', {"length": 0.0, "width": 0.0, "height": 0.0})
        box_total_weight_kg = float(editable_data.get('box_total_weight_kg', 0.0))
        
        # Calcular número de cajas necesarias
        num_boxes = math.ceil(import_quantity / units_per_box)
        
        # Peso total = peso total de cada caja × número de cajas
        peso_total_kg = box_total_weight_kg * num_boxes
        
        # Volumen basado en las dimensiones de las cajas
        if all(d > 0 for d in box_dims.values()):
            volumen_caja_cbm = (box_dims['length'] * box_dims['width'] * box_dims['height']) / 1_000_000
            volumen_total_cbm = volumen_caja_cbm * num_boxes
            peso_volumetrico_kg = volumen_total_cbm * 167
        else:
            volumen_total_cbm = 0
            peso_volumetrico_kg = 0
    
    # Calcular peso facturable (el mayor entre peso físico y volumétrico)
    peso_facturable_kg = max(peso_total_kg, peso_volumetrico_kg) if peso_volumetrico_kg > 0 else peso_total_kg
    
    return {
        "peso_total_kg": peso_total_kg,
        "volumen_total_cbm": volumen_total_cbm,
        "peso_volumetrico_kg": peso_volumetrico_kg,
        "peso_facturable_kg": peso_facturable_kg,
        "packaging_type": packaging_type,
        "num_boxes": math.ceil(import_quantity / editable_data.get('units_per_box', 1)) if packaging_type == "multiple" else import_quantity
    }


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
    st.session_state.ncm_debug_info = {}

def render_ncm_classification_debug():
    """Renderiza información detallada del proceso de clasificación NCM"""
    ncm_debug = st.session_state.get('ncm_debug_info', {})
    
    if not ncm_debug:
        st.info("🤖 No hay información de clasificación NCM disponible. Ejecuta un análisis primero.")
        return
    
    # Información general del proceso
    st.markdown("#### 📋 Información General del Proceso")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("⏱️ Tiempo Total", f"{ncm_debug.get('processing_time_seconds', 0):.2f}s")
    with col2:
        st.metric("🔍 Método Usado", ncm_debug.get('method', 'N/A'))
    with col3:
        has_image = ncm_debug.get('has_image', False)
        st.metric("📷 Con Imagen", "Sí" if has_image else "No")
    
    # Mostrar cada fase del proceso
    if 'process_steps' in ncm_debug:
        st.markdown("#### 🚀 Fases del Proceso de Clasificación")
        
        for i, step in enumerate(ncm_debug['process_steps'], 1):
            status_icon = {"completed": "✅", "error": "❌", "started": "🟡"}.get(step.get('status', ''), "⚪")
            
            with st.expander(f"{status_icon} Fase {i}: {step.get('phase', 'Unknown').replace('_', ' ').title()}", expanded=True):
                
                if step['phase'] == 'initial_estimation':
                    st.markdown("**🤖 Estimación Inicial con IA (Despachante de Aduanas)**")
                    st.markdown(f"- **NCM Estimado:** `{step.get('ncm_estimated', 'N/A')}`")
                    st.markdown(f"- **Nivel de Confianza:** {step.get('confidence', 'N/A')}")
                    st.markdown(f"- **Requiere Exploración:** {'Sí' if step.get('requires_exploration') else 'No'}")
                    
                elif step['phase'] == 'hierarchical_exploration':
                    st.markdown("**🔍 Exploración Jerárquica Profunda**")
                    st.markdown(f"- **Candidatos Encontrados:** {step.get('candidates_found', 0)}")
                    st.markdown(f"- **Posición Recomendada:** `{step.get('recommended_position', 'N/A')}`")
    
    # Debug info detallado por fase
    debug_info = ncm_debug.get('debug_info', {})
    
    if debug_info.get('estimation_phase'):
        st.markdown("#### 🧠 Detalles de Estimación Inicial")
        with st.expander("📄 Análisis del Despachante de Aduanas", expanded=False):
            estimation = debug_info['estimation_phase']
            
            st.markdown("**Factores Determinantes:**")
            factors = estimation.get('factores_determinantes', [])
            for factor in factors:
                st.markdown(f"- {factor}")
            
            st.markdown("**Reglas de Interpretación Aplicadas:**")
            rules = estimation.get('reglas_aplicadas', [])
            for rule in rules:
                st.markdown(f"- {rule}")
            
            st.markdown("**Justificación Técnica:**")
            st.markdown(estimation.get('justificacion_ncm_inicial', 'No disponible'))
            
            if estimation.get('posibles_alternativas'):
                st.markdown("**Alternativas Consideradas:**")
                for alt in estimation['posibles_alternativas']:
                    st.markdown(f"- `{alt.get('ncm', '')}`: {alt.get('razon', '')}")
    
    if debug_info.get('exploration_phase'):
        st.markdown("#### 🔍 Detalles de Exploración Jerárquica")
        with st.expander("📊 Exploración de Base de Datos Oficial", expanded=False):
            exploration = debug_info['exploration_phase']
            
            st.markdown(f"**NCM Base:** `{exploration.get('initial_ncm', 'N/A')}`")
            st.markdown(f"**Match Exacto Encontrado:** {'Sí' if exploration.get('exact_match_found') else 'No'}")
            st.markdown(f"**Matches Jerárquicos:** {exploration.get('hierarchical_matches_count', 0)}")
            
            # Mostrar pasos de exploración
            exploration_steps = exploration.get('exploration_steps', [])
            if exploration_steps:
                st.markdown("**Pasos de Exploración:**")
                for i, exp_step in enumerate(exploration_steps, 1):
                    step_type = exp_step.get('step', '').replace('_', ' ').title()
                    st.markdown(f"{i}. **{step_type}**")
                    
                    if 'result' in exp_step:
                        st.markdown(f"   - Resultado: {exp_step['result']}")
                    if 'is_terminal' in exp_step:
                        st.markdown(f"   - Es Terminal: {'Sí' if exp_step['is_terminal'] else 'No'}")
                    if 'subcategories_found' in exp_step:
                        st.markdown(f"   - Subcategorías: {exp_step['subcategories_found']}")
            
            # Mostrar candidatos finales
            final_candidates = exploration.get('final_candidates', [])
            if final_candidates:
                st.markdown("**Candidatos Finales Evaluados:**")
                
                candidates_data = []
                for candidate in final_candidates:
                    candidates_data.append({
                        'NCM Code': candidate.get('ncm_code', ''),
                        'SIM Code': candidate.get('sim_code', ''),
                        'Descripción': candidate.get('description', '')[:50] + "..." if len(candidate.get('description', '')) > 50 else candidate.get('description', ''),
                        'Fuente': candidate.get('source', ''),
                        'Confianza': candidate.get('confidence', ''),
                        'AEC (%)': candidate.get('fiscal_data', {}).get('aec', 0)
                    })
                
                import pandas as pd
                df_candidates = pd.DataFrame(candidates_data)
                st.dataframe(df_candidates, use_container_width=True)
    
    # Clasificación final
    final_classification = ncm_debug.get('final_classification', {})
    if final_classification:
        st.markdown("#### 🎯 Clasificación Final Seleccionada")
        
        # Información principal
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**NCM Completo:** `{final_classification.get('ncm_completo', 'N/A')}`")
            st.markdown(f"**Descripción:** {final_classification.get('ncm_descripcion', 'N/A')}")
            st.markdown(f"**Nivel de Confianza:** {final_classification.get('nivel_confianza', 'N/A')}")
        
        with col2:
            st.markdown(f"**Fuente:** {final_classification.get('clasificacion_source', 'N/A')}")
            st.markdown(f"**Método:** {final_classification.get('classification_method', 'N/A')}")
        
        # Tratamiento arancelario
        tratamiento = final_classification.get('tratamiento_arancelario', {})
        if tratamiento:
            st.markdown("**💰 Tratamiento Arancelario:**")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("AEC", tratamiento.get('derechos_importacion', 'N/A'))
            with col2:
                st.metric("DIE", tratamiento.get('die', 'N/A'))
            with col3:
                st.metric("Tasa Estadística", tratamiento.get('tasa_estadistica', 'N/A'))
            with col4:
                st.metric("IVA", tratamiento.get('iva', 'N/A'))
        
            # Mostrar código IN si existe
            in_code = tratamiento.get('in_code', '')
            if in_code:
                st.markdown(f"**🏛️ Código IN:** {in_code}")
        
        # Régimen simplificado
        regimen = final_classification.get('regimen_simplificado_courier', {})
        if regimen:
            st.markdown("**📦 Régimen Simplificado Courier:**")
            st.markdown(f"- **Aplica:** {regimen.get('aplica', 'N/A')}")
            st.markdown(f"- **Justificación:** {regimen.get('justificacion', 'N/A')}")
            st.markdown(f"- **Limitaciones:** {regimen.get('limitaciones', 'N/A')}")
        
        # Intervenciones
        intervenciones = final_classification.get('intervenciones_requeridas', [])
        if intervenciones:
            st.markdown("**🏛️ Intervenciones Requeridas:**")
            for intervencion in intervenciones:
                st.markdown(f"- {intervencion}")
        
        # Justificación técnica completa
        justificacion = final_classification.get('justificacion_clasificacion', '')
        if justificacion:
            with st.expander("📖 Justificación Técnica Completa", expanded=False):
                st.markdown(justificacion)
        
        # Observaciones adicionales
        observaciones = final_classification.get('observaciones_adicionales', '')
        if observaciones:
            with st.expander("📝 Observaciones del Despachante", expanded=False):
                st.markdown(observaciones)

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
            "console_output": st.session_state.console_output,
            "ncm_classification_details": st.session_state.get('ncm_debug_info', {})
        }
        
        st.download_button(
            label="📥 Descargar Debug JSON",
            data=json.dumps(log_data, indent=2, ensure_ascii=False, default=str),
            file_name=f"debug_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json"
        )
    
    # Crear tabs secundarias para different tipos de debug
    debug_tab1, debug_tab2, debug_tab3, debug_tab4, debug_tab5 = st.tabs([
        "📊 Flow Steps", "🎯 NCM Classification", "🔧 Console Output", "🌐 API Responses", "📝 Debug Logs"
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
        st.subheader("🎯 Proceso de Clasificación NCM Detallado")
        render_ncm_classification_debug()
    
    with debug_tab3:
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
    
    with debug_tab4:
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
    
    with debug_tab5:
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



def handle_image_upload_and_display(pde):
    """Maneja la carga y visualización de imágenes para clasificación."""
    st.markdown("##### 🖼️ Imagen del Producto")
    st.caption("Sube una imagen o proporciona una URL para mejorar la clasificación NCM")
    
    # Variables para controlar el estado
    has_uploaded_file = False
    has_url_image = False
    uploaded_file = None
    image_url_input = ""
    
    # Si ya hay una imagen cargada, mostrar limpia con botón X
    if pde.get('image_url'):
        # Contenedor centrado para la imagen
        col_center = st.columns([1, 2, 1])[1]
        
        with col_center:
            # Mostrar imagen con marco más pequeña
            try:
                st.image(pde['image_url'], width=120)
            except Exception:
                st.error("❌ Error al mostrar imagen")
            
            # Botón X centrado debajo de la imagen
            if st.button("❌", key="clear_image", help="Eliminar imagen"):
                pde['image_url'] = ''
                pde['image_source'] = None
                st.rerun()
        
        st.markdown("---")
    
    # Opciones de carga en columnas compactas
    col1, col2 = st.columns(2)
    
    with col1:
        uploaded_file = st.file_uploader(
            "📁 Subir archivo",
            type=['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'],
            help="Selecciona imagen desde tu ordenador",
            label_visibility="visible"
        )
        
        if uploaded_file is not None:
            has_uploaded_file = True
    
    with col2:
        current_url = pde.get('image_url', '') if pde.get('image_source') == 'url' else ''
        image_url_input = st.text_input(
            "🔗 URL imagen",
            value=current_url,
            placeholder="https://ejemplo.com/imagen.jpg",
            help="Pega URL de imagen"
        )
        
        if image_url_input and image_url_input.strip():
            has_url_image = True
    
    # Radio buttons solo si hay múltiples opciones
    selected_method = None
    if has_uploaded_file and has_url_image:
        selected_method = st.radio(
            "Selecciona fuente:",
            ["📁 Archivo", "🔗 URL"],
            key="image_source_selector",
            horizontal=True
        )
    elif has_uploaded_file:
        selected_method = "📁 Archivo"
    elif has_url_image:
        selected_method = "🔗 URL"
    
    # Procesar selección
    if selected_method == "📁 Archivo" and uploaded_file is not None:
        try:
            # Convertir imagen a base64
            image = Image.open(uploaded_file)
            buffered = io.BytesIO()
            if image.mode in ('RGBA', 'LA'):
                image = image.convert('RGB')
            image.save(buffered, format="JPEG", quality=85)
            img_base64 = base64.b64encode(buffered.getvalue()).decode()
            
            pde['image_url'] = f"data:image/jpeg;base64,{img_base64}"
            pde['image_source'] = 'uploaded'
            
            # Vista previa compacta
            st.image(image, caption="Vista previa", width=120)
            
        except Exception as e:
            st.error(f"❌ Error: {str(e)}")
            
    elif selected_method == "🔗 URL" and image_url_input and image_url_input.strip():
        try:
            pde['image_url'] = image_url_input.strip()
            pde['image_source'] = 'url'
            
            # Vista previa compacta
            st.image(image_url_input.strip(), caption="Vista previa", width=120)
            
        except Exception as e:
            st.warning(f"⚠️ URL inválida: {str(e)}")
    
    # Consejo solo si no hay imagen
    if not pde.get('image_url') and not has_uploaded_file and not has_url_image:
        st.info("💡 Una imagen del producto mejora la precisión de la clasificación NCM")

def render_editable_product_form():
    """Renderiza el formulario para ingresar/editar datos del producto."""
    st.markdown("#### 📝 Datos del Producto (Editables)")
    st.caption("Modifica los datos extraídos o ingrésalos manualmente. Estos valores se usarán para el cálculo final.")

    pde = st.session_state.product_data_editable

    pde['title'] = st.text_input("Título del Producto", value=pde.get('title', ''))
    
    # Llamar a la nueva función para manejar imágenes
    handle_image_upload_and_display(pde)

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
    
    # NUEVO: Selector de tipo de embalaje
    st.markdown("**Tipo de Embalaje**")
    packaging_type = st.radio(
        "¿Cómo viene embalado el producto?",
        options=["individual", "multiple"],
        format_func=lambda x: {
            "individual": "📦 Embalaje Individual - Cada unidad viene en su propia caja",
            "multiple": "📦 Embalaje Múltiple - Varias unidades vienen en una caja más grande"
        }[x],
        key="packaging_type",
        horizontal=False,
        help="Selecciona el tipo de embalaje para calcular correctamente el peso y volumen del envío"
    )
    
    # Almacenar en session state
    pde['packaging_type'] = packaging_type
    
    if packaging_type == "individual":
        # EMBALAJE INDIVIDUAL: Mostrar dimensiones y peso del producto individual
        st.markdown("**Dimensiones y Peso del Producto Individual**")
        col1, col2, col3, col4 = st.columns(4)
        dims = pde.get('dimensions_cm', {"length": 0.0, "width": 0.0, "height": 0.0})
        dims['length'] = col1.number_input("Largo (cm)", value=dims.get('length', 0.0), min_value=0.0, format="%.2f", key="product_length")
        dims['width'] = col2.number_input("Ancho (cm)", value=dims.get('width', 0.0), min_value=0.0, format="%.2f", key="product_width") 
        dims['height'] = col3.number_input("Alto (cm)", value=dims.get('height', 0.0), min_value=0.0, format="%.2f", key="product_height")
        pde['dimensions_cm'] = dims
        pde['weight_kg'] = col4.number_input("Peso (kg)", value=pde.get('weight_kg', 0.0), min_value=0.0, format="%.3f", key="product_weight")
        
        # Asegurar que los campos de embalaje múltiple tengan valores por defecto
        if 'box_dimensions_cm' not in pde:
            pde['box_dimensions_cm'] = {"length": 0.0, "width": 0.0, "height": 0.0}
        if 'box_total_weight_kg' not in pde:
            pde['box_total_weight_kg'] = 0.0
        if 'units_per_box' not in pde:
            pde['units_per_box'] = 1
            
    else:  # multiple
        # EMBALAJE MÚLTIPLE: Solo mostrar datos de la caja de envío
        st.markdown("**Dimensiones y Peso de la Caja de Envío**")
        st.caption("Especifica las dimensiones y peso total de la caja que contiene múltiples unidades")
        
        col1, col2, col3, col4 = st.columns(4)
        
        box_dims = pde.get('box_dimensions_cm', {"length": 0.0, "width": 0.0, "height": 0.0})
        box_dims['length'] = col1.number_input("Largo (cm)", value=box_dims.get('length', 0.0), min_value=0.0, format="%.2f", key="box_length")
        box_dims['width'] = col2.number_input("Ancho (cm)", value=box_dims.get('width', 0.0), min_value=0.0, format="%.2f", key="box_width")
        box_dims['height'] = col3.number_input("Alto (cm)", value=box_dims.get('height', 0.0), min_value=0.0, format="%.2f", key="box_height")
        pde['box_dimensions_cm'] = box_dims
        
        pde['box_total_weight_kg'] = col4.number_input("Peso Total Caja (kg)", value=pde.get('box_total_weight_kg', 0.0), min_value=0.0, format="%.3f", key="box_total_weight", help="Peso total de la caja incluyendo todos los productos")
        
        # Unidades por caja
        col_units, col_info = st.columns([1, 2])
        with col_units:
            pde['units_per_box'] = st.number_input(
                "Unidades por Caja", 
                value=int(pde.get('units_per_box', 1)), 
                min_value=1, 
                step=1,
                key="units_per_box",
                help="¿Cuántas unidades del producto contiene cada caja?"
            )
        
        with col_info:
            units_per_box = pde.get('units_per_box', 1)
            if units_per_box > 1:
                st.info(f"💡 Cada caja contiene {units_per_box} unidades del producto")
        
        # Asegurar que los campos individuales tengan valores por defecto
        if 'dimensions_cm' not in pde:
            pde['dimensions_cm'] = {"length": 0.0, "width": 0.0, "height": 0.0}
        if 'weight_kg' not in pde:
            pde['weight_kg'] = 0.0

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
    cantidad = pde.get('import_quantity', 1)
    packaging_type = pde.get('packaging_type', 'individual')
    
    # Usar la función auxiliar para calcular métricas de envío
    shipping_metrics = _calculate_shipping_metrics(pde, cantidad)
    peso_total_kg = shipping_metrics["peso_total_kg"]
    volumen_total_cbm = shipping_metrics["volumen_total_cbm"]
    peso_volumetrico_kg = shipping_metrics["peso_volumetrico_kg"]
    peso_facturable_kg = shipping_metrics["peso_facturable_kg"]
    
    # Generar información de packaging para mostrar al usuario
    num_boxes = shipping_metrics.get("num_boxes", cantidad)
    
    if packaging_type == "individual":
        packaging_info = f"📦 **Embalaje Individual**: {cantidad} unidad(es), cada una en su propia caja"
    else:  # multiple
        units_per_box = pde.get('units_per_box', 1)
        packaging_info = f"📦 **Embalaje Múltiple**: {cantidad} unidad(es) en {num_boxes} caja(s) de {units_per_box} unidad(es) cada una"
    
    # Guardar datos de shipping para compatibilidad con el resto del código
    pde['shipping_weight_kg'] = peso_total_kg
    pde['shipping_volume_cbm'] = volumen_total_cbm
    pde['shipping_volumetric_weight_kg'] = peso_volumetrico_kg
    pde['shipping_billable_weight_kg'] = peso_facturable_kg
    
    # Mostrar información del tipo de embalaje
    st.markdown(packaging_info)
    
    # Mostrar cálculos de peso y volumen
    col1, col2 = st.columns(2)
    with col1:
        if packaging_type == "individual":
            peso_unitario = pde.get('weight_kg', 0.0)
            help_text = f"Peso físico total: {peso_unitario:.2f} kg × {cantidad} unidades"
        else:
            box_total_weight = pde.get('box_total_weight_kg', 0.0)
            help_text = f"Peso total: {box_total_weight:.2f} kg por caja × {num_boxes} caja(s) = {peso_total_kg:.2f} kg"
        
        st.metric(
            label="📦 Peso Total", 
            value=f"{peso_total_kg:.2f} kg",
            help=help_text
        )
    
    with col2:
        if packaging_type == "individual":
            help_text = f"Peso volumétrico: {volumen_total_cbm:.6f} m³ × 167 kg/m³ (factor aéreo estándar)"
        else:
            help_text = f"Peso volumétrico: {volumen_total_cbm:.6f} m³ × 167 kg/m³ (basado en {num_boxes} caja(s))"
        
        st.metric(
            label="📐 Peso Volumétrico", 
            value=f"{peso_volumetrico_kg:.2f} kg" if peso_volumetrico_kg > 0 else "No calculable",
            help=help_text
        )
    
    # Mostrar peso facturable
    col_facturable1, col_facturable2 = st.columns([1, 1])
    with col_facturable1:
        peso_facturable_diferencia = peso_facturable_kg - peso_total_kg
        
        st.metric(
            label="⚖️ Peso Facturable", 
            value=f"{peso_facturable_kg:.2f} kg",
            delta=f"+{peso_facturable_diferencia:.2f} kg" if peso_facturable_diferencia > 0 else None,
            help="Peso usado para calcular el costo de envío (mayor entre peso físico y volumétrico)"
        )
    
    with col_facturable2:
        if packaging_type == "multiple":
            # Mostrar peso por unidad en embalaje múltiple
            units_per_box = pde.get('units_per_box', 1)
            box_total_weight = pde.get('box_total_weight_kg', 0.0)
            peso_por_unidad = box_total_weight / units_per_box if units_per_box > 0 else 0
            st.metric(
                label="📊 Peso por Unidad",
                value=f"{peso_por_unidad:.3f} kg",
                help=f"Peso promedio por unidad en la caja: {box_total_weight:.2f} kg ÷ {units_per_box} unidades"
            )
    
    # Mostrar información adicional del envío
    if volumen_total_cbm > 0:
        col3, col4 = st.columns(2)
        with col3:
            if packaging_type == "individual":
                dims = pde.get('dimensions_cm', {"length": 0.0, "width": 0.0, "height": 0.0})
                help_text = f"Volumen total: {dims['length']:.1f} × {dims['width']:.1f} × {dims['height']:.1f} cm × {cantidad} unidades"
            else:
                box_dims = pde.get('box_dimensions_cm', {"length": 0.0, "width": 0.0, "height": 0.0})
                help_text = f"Volumen total: {box_dims['length']:.1f} × {box_dims['width']:.1f} × {box_dims['height']:.1f} cm × {num_boxes} caja(s)"
            
            st.metric(
                label="📏 Volumen Total",
                value=f"{volumen_total_cbm:.6f} m³",
                help=help_text
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
                dest_postal = st.text_input("Código Postal", value="C1000", key="main_dest_postal", 
                                          help="Código postal de Buenos Aires (se normaliza automáticamente para APIs)")
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
    # Normalizar subdominios de Alibaba (spanish., french., m., etc.) -> www.alibaba.com
    try:
        parsed = urlparse(url.strip())
        hostname = parsed.hostname or ""
        if hostname.endswith(".alibaba.com") and hostname != "www.alibaba.com":
            normalized_netloc = "www.alibaba.com"
            parsed = parsed._replace(netloc=normalized_netloc)
            url = urlunparse(parsed)
    except Exception:
        pass

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
    
    # Asegurar que el packaging_type esté establecido
    if 'packaging_type' not in pde:
        pde['packaging_type'] = 'individual'

    st.session_state.data_input_step_completed = True
    st.success("✅ Datos extraídos y procesados. Revisa y ajusta los valores si es necesario antes de calcular.")
    st.rerun()

def render_sidebar_config():
    """Renderiza la configuración del sidebar de manera optimizada"""
    with st.sidebar:
        st.markdown("### ⚙️ Configuración del Cálculo")
        st.session_state.debug_mode = st.checkbox("🔧 Debug", value=CONFIG['DEBUG_MODE'])
        
        # DHL configuración automática (sin UI)
        use_real_dhl = True  # Siempre usar DHL real
        dhl_test_mode = True  # Mantener en modo test por defecto
        
        # Configurar servicio DHL solo si cambió
        if (_needs_dhl_update(use_real_dhl, dhl_test_mode)):
            _update_dhl_service(use_real_dhl, dhl_test_mode)
        
        return {
            "tipo_importador": st.selectbox("Importador:", ["responsable_inscripto", "no_inscripto", "monotributista"], key="tipo_importador_sb"),
            "destino_importacion": st.selectbox("Destino:", ["reventa", "uso_propio", "bien_capital"], key="destino_sb"),
            "provincia": st.selectbox("Provincia:", ["CABA", "BUENOS_AIRES", "CORDOBA", "SANTA_FE"], key="provincia_sb"),
            "tipo_flete": st.selectbox("Tipo de Flete:", ["Courier (Aéreo)", "Marítimo (Contenedor)"], key="tipo_flete_sb"),
            "cotizacion_dolar": st.number_input("Cotización USD/ARS", value=1746.96, format="%.2f", key="cotizacion_sb")
        }

def _needs_dhl_update(use_real_dhl, dhl_test_mode):
    """Verifica si necesita actualizar la configuración DHL"""
    return ('dhl_use_real' not in st.session_state or 
            st.session_state.dhl_use_real != use_real_dhl or
            getattr(st.session_state.dhl_service, 'test_mode', None) != dhl_test_mode)

def _update_dhl_service(use_real_dhl, dhl_test_mode):
    """Actualiza el servicio DHL solo cuando es necesario"""
    st.session_state.dhl_use_real = use_real_dhl
    st.session_state.dhl_service = DHLFreightService(
        test_mode=dhl_test_mode,
        use_dhl_real=use_real_dhl,
        fallback_rates_file=CONFIG['FREIGHT_RATES_FILE'],
        debug_callback=debug_log
    )

def render_main_calculator():
    """Renderizar la calculadora principal optimizada"""
    # Configuración desde sidebar
    config = render_sidebar_config()

    st.markdown("# 📊 Calculadora de Landing Cost")

    # --- LÓGICA DE RE-CÁLCULO AUTOMÁTICO ---
    # Si ya hay un resultado, y alguna configuración de la sidebar cambia, recalcular.
    if 'result' in st.session_state and st.session_state.result:
        # Usar configuración actual del sidebar
        current_config = config
        
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
            with st.spinner("🔄 Recalculando con nueva configuración..."):
                execute_landed_cost_calculation(
                    config["tipo_importador"], config["destino_importacion"], 
                    config["provincia"], config["cotizacion_dolar"], config["tipo_flete"]
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
            # Normalizar la URL para que use www.alibaba.com
            normalized_url = url_alibaba.strip() if url_alibaba else ""
            try:
                parsed = urlparse(normalized_url)
                host = (parsed.hostname or "").lower()
                if host.endswith(".alibaba.com") and host != "www.alibaba.com":
                    parsed = parsed._replace(netloc="www.alibaba.com")
                    normalized_url = urlunparse(parsed)
            except Exception:
                pass

            if not normalized_url or not normalized_url.startswith("https://www.alibaba.com/product-detail/"):
                st.error("❌ Ingresa una URL de Alibaba válida.")
            else:
                fetch_and_populate_from_url(normalized_url)
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
                "image_source": None,  # Nuevo campo para rastrear el origen de la imagen
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
                    config["tipo_importador"], config["destino_importacion"], 
                    config["provincia"], config["cotizacion_dolar"], config["tipo_flete"]
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
    tab1, tab2, tab3 = st.tabs(["📊 Calculadora Principal", "💹 Margen y Precio", "🔍 Debug & Análisis"])
    
    with tab1:
        render_main_calculator()
    
    with tab2:
        render_margin_tab()
    
    with tab3:
        render_debug_tab()

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
    
    # Debug: Mostrar las direcciones que se están usando
    if st.session_state.get('debug_mode', False):
        with st.expander("🔍 **Debug: Direcciones de envío**", expanded=False):
            col_debug1, col_debug2 = st.columns(2)
            with col_debug1:
                st.json({
                    "origin_details": origin_details,
                    "entry_mode": st.session_state.entry_mode
                })
            with col_debug2:
                st.json({
                    "destination_details": destination_details,
                    "debug_mode": st.session_state.get('debug_mode', False)
                })
    
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

        # Paso 1: Clasificar NCM con Sistema Profundo (Despachante de Aduanas + Exploración Jerárquica)
        with st.spinner("🎯 Clasificando NCM con sistema profundo (Despachante + Exploración Jerárquica)..."):
            log_flow_step("CLASIFICACION_NCM_PROFUNDA", "STARTED")
            ncm_result = {}
            try:
                enhanced_description = create_enhanced_description(product_for_analysis)
                
                # NUEVO: Usar clasificador profundo con expertise de despachante de aduanas
                from ai_ncm_deep_classifier import DeepNCMClassifier
                
                deep_classifier = DeepNCMClassifier(
                    api_key=API_KEYS.get("OPENAI_API_KEY"),
                    debug_callback=debug_log
                )
                
                deep_result = asyncio.run(deep_classifier.classify_product_deep(
                    description=enhanced_description,
                    image_url=editable_data['image_url']
                ))

                if deep_result.get('error'):
                    # Si hay fallback disponible, usarlo en lugar de fallar
                    if deep_result.get('final_classification'):
                        debug_log(f"⚠️ Clasificación con fallback: {deep_result.get('error')}", level="WARNING")
                        if deep_result.get('is_fallback'):
                            st.warning("⚠️ Se usó clasificación de fallback. Se recomienda validación manual.")
                        elif deep_result.get('is_emergency_fallback'):
                            st.error("🚨 Clasificación de emergencia. **REQUIERE REVISIÓN MANUAL INMEDIATA**")
                    else:
                        raise ValueError(deep_result.get('error', 'Error en clasificación NCM profunda'))
                
                # Guardar información completa de debug NCM
                st.session_state.ncm_debug_info = deep_result
                
                # Extraer clasificación final para compatibilidad
                final_classification = deep_result.get('final_classification', {})
                if not final_classification:
                    raise ValueError("No se pudo obtener clasificación final del sistema profundo")
                
                # Convertir al formato esperado por el resto del sistema
                ncm_result = {
                    'ncm_completo': final_classification.get('ncm_completo', 'N/A'),
                    'ncm_descripcion': final_classification.get('ncm_descripcion', ''),
                    'confianza': final_classification.get('nivel_confianza', 'Media'),
                    'justificacion_clasificacion': final_classification.get('justificacion_clasificacion', ''),
                    'tratamiento_arancelario': final_classification.get('tratamiento_arancelario', {}),
                    'regimen_simplificado_courier': final_classification.get('regimen_simplificado_courier', {}),
                    'intervenciones_requeridas': final_classification.get('intervenciones_requeridas', []),
                    'ncm_desglose': final_classification.get('ncm_desglose', {}),
                    'observaciones_adicionales': final_classification.get('observaciones_adicionales', ''),
                    'classification_method': final_classification.get('classification_method', 'deep_hierarchical_ai'),
                    
                    # Información adicional para debug
                    'ncm_official_info': {
                        'source': 'Deep NCM Classification System',
                        'method': deep_result.get('method', ''),
                        'processing_time': deep_result.get('processing_time_seconds', 0),
                        'phases_completed': len(deep_result.get('process_steps', [])),
                        'was_deep_analyzed': True
                    }
                }
                
                # Logging detallado del proceso de clasificación NCM profundo
                ai_ncm = ncm_result.get('ncm_completo', 'N/A')
                confianza = ncm_result.get('confianza', 'N/A')
                processing_time = deep_result.get('processing_time_seconds', 0)
                phases = len(deep_result.get('process_steps', []))
                
                log_flow_step("CLASIFICACION_NCM_PROFUNDA_COMPLETADA", "SUCCESS", {
                    "ncm_completo": ai_ncm,
                    "confianza": confianza,
                    "metodo": "deep_hierarchical_classification",
                    "tiempo_procesamiento": f"{processing_time:.2f}s",
                    "fases_completadas": phases,
                    "clasificacion_source": final_classification.get('clasificacion_source', 'N/A')
                })
                
                # Extraer información para validación 
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

        # Calcular métricas de envío usando la nueva función que maneja ambos tipos de embalaje
        shipping_metrics = _calculate_shipping_metrics(editable_data, import_quantity)
        peso_total_kg = shipping_metrics["peso_total_kg"]
        volumen_total_cbm = shipping_metrics["volumen_total_cbm"]
        peso_volumetrico_total_kg = shipping_metrics["peso_volumetrico_kg"]
        peso_facturable_kg = shipping_metrics["peso_facturable_kg"]
        
        # Para compatibilidad con código existente - usar dimensiones correctas según tipo de embalaje
        packaging_type = editable_data.get('packaging_type', 'individual')
        if packaging_type == 'individual':
            dims = editable_data.get('dimensions_cm', {"length": 0.0, "width": 0.0, "height": 0.0})
            peso_unitario_kg = float(editable_data.get('weight_kg', 0.0))
        else:
            # Para embalaje múltiple, usar dimensiones de la caja para DHL
            dims = editable_data.get('box_dimensions_cm', {"length": 0.0, "width": 0.0, "height": 0.0})
            # Calcular peso unitario estimado para compatibilidad
            box_total_weight = float(editable_data.get('box_total_weight_kg', 0.0))
            units_per_box = editable_data.get('units_per_box', 1)
            peso_unitario_kg = box_total_weight / units_per_box if units_per_box > 0 else 0.0
        
        volumen_unitario_cbm = (dims['length'] * dims['width'] * dims['height']) / 1_000_000 if all(d > 0 for d in dims.values()) else 0

        costo_flete_total_usd = 0
        metodo_calculo = "Sin datos"
        
        if tipo_flete == "Courier (Aéreo)":
            # NUEVO: Usar API unificada que compara FedEx + DHL y elige la mejor opción
            try:
                from carriers_apis_conections.unified_shipping_api import get_cheapest_shipping_rate
                
                # Construir dimensiones
                dimensions_cm_dict = {
                    "length": dims.get('length', 25),
                    "width": dims.get('width', 35), 
                    "height": dims.get('height', 15)
                }
                
                # Obtener mejor cotización comparando FedEx y DHL usando direcciones del session state
                unified_result = get_cheapest_shipping_rate(
                    weight_kg=peso_facturable_kg,
                    origin_country=origin_details.get('countryCode', 'CN'),  # Usar país de origen real (China)
                    origin_postal=origin_details.get('postalCode', '518000'),  # Usar código postal real
                    dest_country=destination_details.get('countryCode', 'AR'),
                    dest_postal=destination_details.get('postalCode', 'C1000'),
                    test_mode=True,
                    debug=False
                )
                
                if unified_result["success"]:
                    best_quote = unified_result["best_quote"]
                    all_quotes = unified_result["all_quotes"]
                    
                    costo_flete_total_usd = best_quote.cost_usd
                    metodo_calculo = f"{best_quote.carrier} - {best_quote.service_name}"
                    
                    debug_log(f"✅ Mejor cotización: {best_quote.carrier} ${best_quote.cost_usd:.2f} USD", level="SUCCESS")
                    
                    # Mostrar resultado principal con información detallada
                    st.success(f"🏆 **Mejor opción seleccionada: {best_quote.carrier}** - ${best_quote.cost_usd:.2f} USD")
                    
                    # Información detallada del envío seleccionado
                    col_best1, col_best2, col_best3 = st.columns(3)
                    with col_best1:
                        st.metric("📦 Servicio", best_quote.service_name)
                    with col_best2:
                        st.metric("⏰ Tiempo de tránsito", f"{best_quote.transit_days or 'N/A'} días")
                    with col_best3:
                        st.metric("💰 Costo total", f"${best_quote.cost_usd:.2f} USD")
                    
                    # Información detallada de direcciones y APIs
                    col_route1, col_route2 = st.columns(2)
                    with col_route1:
                        st.info(f"📍 **Origen**: {origin_details.get('countryCode', 'CN')} - {origin_details.get('cityName', 'SHENZHEN')} ({origin_details.get('postalCode', '518000')})")
                    with col_route2:
                        st.info(f"🎯 **Destino**: {destination_details.get('countryCode', 'AR')} - {destination_details.get('cityName', 'CAPITAL FEDERAL')} ({destination_details.get('postalCode', 'C1000')})")
                    
                    # Información técnica de la consulta
                    with st.expander("🔧 **Detalles técnicos de la consulta**", expanded=False):
                        st.write("**Parámetros enviados a las APIs:**")
                        col_tech1, col_tech2 = st.columns(2)
                        with col_tech1:
                            st.code(f"""FedEx API:
origin_country: {origin_details.get('countryCode', 'CN')}
origin_postal: {origin_details.get('postalCode', '518000')}
dest_country: {destination_details.get('countryCode', 'AR')}
dest_postal: {destination_details.get('postalCode', 'C1000')}
weight: {peso_facturable_kg:.2f} kg""")
                        with col_tech2:
                            # Mostrar códigos postales normalizados para DHL
                            from carriers_apis_conections.unified_shipping_api import UnifiedShippingAPI
                            api_temp = UnifiedShippingAPI()
                            dest_postal_norm = api_temp._normalize_postal_code(destination_details.get('postalCode', 'C1000'), destination_details.get('countryCode', 'AR'))
                            origin_postal_norm = api_temp._normalize_postal_code(origin_details.get('postalCode', '518000'), origin_details.get('countryCode', 'CN'))
                            st.code(f"""DHL API (normalizado):
origin_country: {origin_details.get('countryCode', 'CN')}
origin_postal: {origin_postal_norm}
dest_country: {destination_details.get('countryCode', 'AR')}
dest_postal: {dest_postal_norm}
weight: {peso_facturable_kg:.2f} kg""")
                    
                    # Mostrar comparación de todas las opciones
                    with st.expander("📊 **Ver todas las opciones disponibles y comparar carriers**", expanded=False):
                        col1, col2 = st.columns(2)
                        
                        # Mostrar FedEx options
                        with col1:
                            st.markdown("### 🚀 **FedEx**")
                            fedex_quotes = all_quotes.get("FedEx", [])
                            if fedex_quotes:
                                for i, quote in enumerate(fedex_quotes[:5], 1):  # Top 5
                                    if quote.success:
                                        is_selected = quote.carrier == best_quote.carrier and abs(quote.cost_usd - best_quote.cost_usd) < 0.01
                                        icon = "🏆" if is_selected else "📦"
                                        style = "background-color: #e8f5e8; padding: 10px; border-radius: 5px; margin: 5px 0;" if is_selected else ""
                                        
                                        rate_type_text = f" ({quote.rate_type})" if hasattr(quote, 'rate_type') and quote.rate_type != "Unknown" else ""
                                        
                                        st.markdown(f"""
                                        <div style="{style}">
                                            {icon} <strong>${quote.cost_usd:.2f} USD</strong> - {quote.service_name}{rate_type_text}<br>
                                            <small>⏰ {quote.transit_days or 'N/A'} días de tránsito</small>
                                        </div>
                                        """, unsafe_allow_html=True)
                                    else:
                                        st.write(f"❌ Error: {quote.error_message}")
                            else:
                                st.write("❌ No disponible")
                        
                        # Mostrar DHL options  
                        with col2:
                            st.markdown("### 📦 **DHL**")
                            dhl_quotes = all_quotes.get("DHL", [])
                            if dhl_quotes:
                                for i, quote in enumerate(dhl_quotes, 1):
                                    if quote.success:
                                        is_selected = quote.carrier == best_quote.carrier and abs(quote.cost_usd - best_quote.cost_usd) < 0.01
                                        icon = "🏆" if is_selected else "📦"
                                        style = "background-color: #e8f5e8; padding: 10px; border-radius: 5px; margin: 5px 0;" if is_selected else ""
                                        
                                        rate_type_text = f" ({quote.rate_type})" if hasattr(quote, 'rate_type') and quote.rate_type != "Unknown" else ""
                                        
                                        st.markdown(f"""
                                        <div style="{style}">
                                            {icon} <strong>${quote.cost_usd:.2f} USD</strong> - {quote.service_name}{rate_type_text}<br>
                                            <small>⏰ {quote.transit_days or 'N/A'} días de tránsito</small>
                                        </div>
                                        """, unsafe_allow_html=True)
                                    else:
                                        st.write(f"❌ Error: {quote.error_message}")
                            else:
                                st.write("❌ No disponible")
                    
                    # Log todas las respuestas para debug
                    log_api_call("UNIFIED_SHIPPING", {"weight": peso_facturable_kg}, unified_result, True)
                    
                    # Variables para compatibilidad con código existente
                    insurance_cost = 0.0
                    argentina_taxes = 0.0
                    
                else:
                    # Fallback: usar solo DHL si la API unificada falla
                    debug_log(f"⚠️ API unificada falló, usando DHL como fallback: {unified_result.get('error')}", level="WARNING")
                    st.warning("⚠️ Comparación de carriers no disponible, usando DHL...")
                    
                    # Usar direcciones reales del session state también en fallback DHL
                    fallback_origin = origin_details or {
                        "postalCode": "518000",
                        "cityName": "SHENZHEN",
                        "countryCode": "CN",
                        "addressLine1": "address1",
                        "addressLine2": "address2",
                        "addressLine3": "address3"
                    }
                    fallback_destination = destination_details or {
                        "postalCode": "C1000",
                        "cityName": "BUENOS AIRES",
                        "countryCode": "AR",
                        "addressLine1": "address1",
                        "addressLine2": "address2",
                        "addressLine3": "address3"
                    }
                    
                    # Usar servicio DHL original como fallback
                    dhl_result = st.session_state.dhl_service.calculate_freight_with_fallback(
                        weight_kg=peso_facturable_kg,
                        dimensions_cm=dimensions_cm_dict,
                        origin_details=fallback_origin,
                        destination_details=fallback_destination,
                        shipping_datetime=st.session_state.get('planned_shipping_datetime')
                    )
                    
                    costo_flete_total_usd = dhl_result["cost_usd"]
                    metodo_calculo = f"DHL {dhl_result['method']} (fallback)"
                    
                    # Extraer costos detallados si están disponibles
                    insurance_cost = 0.0
                    argentina_taxes = 0.0
                    
                    if 'cost_breakdown' in dhl_result:
                        cost_breakdown = dhl_result['cost_breakdown']
                        insurance_cost = cost_breakdown.get('insurance_cost', 0.0)
                        argentina_taxes = cost_breakdown.get('argentina_taxes', 0.0)
                    
                    if dhl_result["success"]:
                        st.info(f"📦 DHL: ${costo_flete_total_usd:.2f} USD")
                    else:
                        st.error(f"❌ Error en cotización: {dhl_result.get('error')}")
                        costo_flete_total_usd = peso_facturable_kg * 45  # Estimación básica
                        metodo_calculo = "Estimación básica"
                        st.warning(f"📈 Usando estimación: ${costo_flete_total_usd:.2f} USD")
                    
                # Almacenar información completa del resultado para uso posterior
                result_session_data = {
                    'dhl_insurance_cost': insurance_cost,
                    'dhl_argentina_taxes': argentina_taxes,
                    'dhl_insurance_included': False,  # API unificada no tiene esta info
                    'dhl_taxes_included': False,  # API unificada no tiene esta info
                    'cost_breakdown': {},  # API unificada maneja esto diferente
                    'test_mode': True,
                    'service': metodo_calculo,
                    'transit_days': best_quote.transit_days if unified_result["success"] else 2
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
                "weight_kg": editable_data.get('weight_kg', 0.0),
                "peso_total_kg": peso_total_kg,
                "peso_volumetrico_total_kg": peso_volumetrico_total_kg,
                "peso_facturable_kg": peso_facturable_kg,
                "dimensions_cm": editable_data.get('dimensions_cm', {"length": 0.0, "width": 0.0, "height": 0.0}),
                "box_dimensions_cm": editable_data.get('box_dimensions_cm', {"length": 0.0, "width": 0.0, "height": 0.0}),
                "box_total_weight_kg": editable_data.get('box_total_weight_kg', 0.0),
                "units_per_box": editable_data.get('units_per_box', 1),
                "packaging_type": editable_data.get('packaging_type', 'individual'),
                "volumen_unitario_cbm": volumen_unitario_cbm,
                "volumen_total_cbm": volumen_total_cbm,
                "method": "Manual" if st.session_state.entry_mode == 'Ingreso Manual' else 'Edited',
                "metodo_calculo_flete": metodo_calculo,
                # NUEVO: Agregar desglose de costos DHL si está disponible
                "dhl_cost_breakdown": result_session_data.get('cost_breakdown', {}) if 'result_session_data' in locals() and result_session_data else {},
                "dhl_test_mode": result_session_data.get('test_mode', True) if 'result_session_data' in locals() and result_session_data else True,
                "dhl_service_name": result_session_data.get('service', 'N/A') if 'result_session_data' in locals() and result_session_data else 'N/A',
                "dhl_transit_days": result_session_data.get('transit_days', 2) if 'result_session_data' in locals() and result_session_data else 2
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

            # Obtener NCM completo (incluye sufijo si existe)
            ncm_result = result.get('ncm_result', {})
            ncm_completo = ncm_result.get('ncm_completo', 'N/A')
            ncm_confianza = ncm_result.get('confianza', 'N/A')
            
            # Determinar si hay match oficial para mostrar indicador
            ncm_official_info = ncm_result.get('ncm_official_info', {})
            match_oficial = ncm_official_info.get('match_exacto', False)
            fue_refinado = ncm_official_info.get('was_refined', False)
            
            # Construir valor de NCM con indicadores
            if match_oficial:
                ncm_display = f"{ncm_completo} 🇦🇷"
                ncm_help = "Validado con base oficial argentina"
            elif fue_refinado:
                ncm_display = f"{ncm_completo} 🎯"
                ncm_help = "Refinado automáticamente por IA"
            else:
                ncm_display = f"{ncm_completo} 🤖"
                ncm_help = "Clasificado por IA"

            row1 = st.columns(2)
            row1[0].metric(label="📍 Origen (si aplica)", value=origen)
            row1[1].metric(label="📦 Pedido Mínimo", value=moq_str)
            
            row2 = st.columns(2)
            row2[0].metric(label="💰 Precio Unitario Base", value=price_range_str)

            landed_cost_str = f"${result['landed_cost']:.2f}"
            row2[1].metric(label="💸 Landed Cost Unitario", value=landed_cost_str)
            
            # Nueva fila para NCM y confianza
            row3 = st.columns(2)
            row3[0].metric(
                label="🏷️ Posición NCM Completa", 
                value=ncm_display,
                help=ncm_help
            )
            row3[1].metric(
                label="🎯 Confianza IA", 
                value=f"{ncm_confianza}",
                help="Nivel de confianza de la clasificación automática"
            )
                
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
        
        # Mostrar desglose de costos DHL si está disponible
        dhl_cost_breakdown = shipping_details.get('dhl_cost_breakdown', {})
        dhl_method = shipping_details.get('metodo_calculo_flete', '')
        
        if dhl_cost_breakdown and 'dhl_api' in dhl_method.lower():
            st.markdown("#### 💰 Desglose de Costos DHL (API Real)")
            
            # Crear DataFrame con el desglose de costos
            breakdown_data = []
            
            # Servicio base
            if dhl_cost_breakdown.get('base_service_cost', 0) > 0:
                breakdown_data.append({
                    "Concepto": "🚀 Servicio Base",
                    "Costo USD": f"${dhl_cost_breakdown['base_service_cost']:.2f}",
                    "Descripción": dhl_cost_breakdown.get('service_name', 'EXPRESS WORLDWIDE')
                })
            
            # Recargo de combustible
            if dhl_cost_breakdown.get('fuel_surcharge', 0) > 0:
                breakdown_data.append({
                    "Concepto": "⛽ Recargo Combustible",
                    "Costo USD": f"${dhl_cost_breakdown['fuel_surcharge']:.2f}",
                    "Descripción": "Ajuste por precio del combustible"
                })
            
            # Seguro
            if dhl_cost_breakdown.get('insurance_cost', 0) > 0:
                breakdown_data.append({
                    "Concepto": "🛡️ Seguro",
                    "Costo USD": f"${dhl_cost_breakdown['insurance_cost']:.2f}",
                    "Descripción": "Protección de la mercadería"
                })
            
            # Impuestos Argentina
            if dhl_cost_breakdown.get('argentina_taxes', 0) > 0:
                breakdown_data.append({
                    "Concepto": "🏛️ Impuestos Argentina",
                    "Costo USD": f"${dhl_cost_breakdown['argentina_taxes']:.2f}",
                    "Descripción": "IVA, Ganancias y otros impuestos locales"
                })
            
            # Otros costos
            if dhl_cost_breakdown.get('other_costs', 0) > 0:
                breakdown_data.append({
                    "Concepto": "📋 Otros Costos",
                    "Costo USD": f"${dhl_cost_breakdown['other_costs']:.2f}",
                    "Descripción": "Tasas adicionales y servicios"
                })
            
            # GoGreen (excluido pero mostrar para transparencia)
            if dhl_cost_breakdown.get('gogreen_cost', 0) > 0:
                breakdown_data.append({
                    "Concepto": "🌿 GoGreen Plus (Excluido)",
                    "Costo USD": f"${dhl_cost_breakdown['gogreen_cost']:.2f}",
                    "Descripción": "Compensación carbono (no incluido en total)"
                })
            
            # Total
            total_cost = dhl_cost_breakdown.get('total_cost', 0)
            if total_cost > 0:
                breakdown_data.append({
                    "Concepto": "💯 TOTAL FLETE DHL",
                    "Costo USD": f"${total_cost:.2f}",
                    "Descripción": f"Tiempo de tránsito: {dhl_cost_breakdown.get('transit_days', 2)} días"
                })
            
            if breakdown_data:
                df_dhl_breakdown = pd.DataFrame(breakdown_data)
                st.dataframe(df_dhl_breakdown, use_container_width=True, hide_index=True)
                
                # Información adicional
                col_info1, col_info2 = st.columns(2)
                with col_info1:
                    st.success(f"✅ **API DHL Exitosa** - Cotización en tiempo real")
                with col_info2:
                    test_mode = shipping_details.get('dhl_test_mode', True)
                    mode_text = "🧪 Modo TEST" if test_mode else "🏭 Modo PRODUCCIÓN"
                    st.info(f"{mode_text}")
        
        elif 'fallback' in dhl_method.lower():
            st.markdown("#### 📊 Información del Flete")
            st.warning(f"⚠️ **Flete calculado con método de respaldo**: {dhl_method}")
            st.markdown("*La API de DHL no estuvo disponible, se usaron tarifas de referencia.*")
        
        elif 'estimation' in dhl_method.lower():
            st.markdown("#### 📊 Información del Flete")
            st.info(f"📊 **Estimación básica**: {dhl_method}")
            st.markdown("*Cálculo estimativo basado en peso. Se recomienda verificar con cotización real.*")
        
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

def render_margin_tab():
    """Renderiza la pestaña de margen y precio de venta."""
    st.markdown("## 💹 Margen y Precio de Venta")
    if 'result' not in st.session_state or not st.session_state.result:
        st.info("Primero realiza un cálculo en la pestaña 'Calculadora Principal'.")
        return

    result = st.session_state.result
    qty = int(result['configuracion'].get('import_quantity', 1))
    landed_unit = float(result.get('landed_cost', 0.0))
    fob_unit = float(result.get('precio_base', 0.0))

    top1, top2, top3 = st.columns(3)
    top1.metric("Landed Cost Unit.", f"${landed_unit:.2f} USD")
    top2.metric("Cantidad", f"{qty} u")
    top3.metric("FOB Unit.", f"${fob_unit:.2f} USD")

    st.divider()

    default_pv = float(st.session_state.margin_config.get('precio_venta_unit_usd', max(landed_unit * 1.3, 0.0)))
    default_comm = float(st.session_state.margin_config.get('comision_venta_pct', 10.0))

    c1, c2 = st.columns(2)
    with c1:
        pv_unit = st.number_input(
            "Precio de venta unitario (USD)",
            min_value=0.0,
            value=default_pv,
            step=1.0,
            key="pv_unit_input"
        )
    with c2:
        comm_pct = st.number_input(
            "Comisión de venta (%)",
            min_value=0.0,
            max_value=100.0,
            value=default_comm,
            step=0.5,
            key="comm_pct_input"
        )

    # Guardar en sesión
    st.session_state.margin_config['precio_venta_unit_usd'] = pv_unit
    st.session_state.margin_config['comision_venta_pct'] = comm_pct

    commission_unit = pv_unit * (comm_pct / 100.0)
    net_revenue_unit = max(pv_unit - commission_unit, 0.0)
    margin_unit = net_revenue_unit - landed_unit
    margin_pct_over_price = (margin_unit / pv_unit * 100.0) if pv_unit > 0 else 0.0
    markup_over_cost = (margin_unit / landed_unit * 100.0) if landed_unit > 0 else 0.0
    breakeven_price = landed_unit / (1 - (comm_pct / 100.0)) if (1 - (comm_pct / 100.0)) > 0 else 0.0

    st.markdown("### Resultados por Unidad")
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Comisión/Unit.", f"${commission_unit:.2f}")
    r2.metric("Ingreso Neto/Unit.", f"${net_revenue_unit:.2f}")
    r3.metric("Margen/Unit.", f"${margin_unit:.2f}")
    r4.metric("Margen % sobre PV", f"{margin_pct_over_price:.1f}%")

    k1, k2 = st.columns(2)
    k1.metric("Markup % sobre Costo", f"{markup_over_cost:.1f}%")
    k2.metric("Precio Breakeven (PV)", f"${breakeven_price:.2f}")

    st.markdown("### Totales")
    t1, t2, t3 = st.columns(3)
    t1.metric("Ingreso Total", f"${(pv_unit * qty):,.2f}")
    t2.metric("Comisión Total", f"${(commission_unit * qty):,.2f}")
    t3.metric("Ganancia Total", f"${(margin_unit * qty):,.2f}")

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
            alicuota = float(impuesto.alicuota)
            
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
    
    # CORREGIDO: Obtener flete total de manera más robusta
    flete_total = 0
    if 'costo_flete_total_usd' in result:
        flete_total = result['costo_flete_total_usd']
    elif 'shipping_details' in result and 'total_cost_usd' in result['shipping_details']:
        flete_total = result['shipping_details']['total_cost_usd']
    else:
        # Fallback: calcular desde flete unitario
        flete_total = flete_unitario * import_quantity
    
    honorarios_total = honorarios_despachante * import_quantity
    total_landed_cost = landed_cost * import_quantity
    # Eliminado: No cargar datos en ARS
    
    # Obtener datos de NCM
    ncm_result = result.get('ncm_result', {})
    ncm_code = ncm_result.get('ncm_completo', '')
    ncm_description = ncm_result.get('ncm_descripcion', '')
    confianza_ia = ncm_result.get('confianza', '')
    
    # Obtener datos de envío - MEJORADO para incluir métricas completas
    shipping_details = result.get('shipping_details', {})
    
    # Calcular métricas de envío usando la función existente
    shipping_metrics = _calculate_shipping_metrics(shipping_details, import_quantity)
    
    # Datos unitarios (para embalaje individual)
    peso_unitario = shipping_details.get('weight_kg', 0)
    dims_unitarias = shipping_details.get('dimensions_cm', {})
    dimensiones_unitarias = f"{dims_unitarias.get('length', 0):.1f} × {dims_unitarias.get('width', 0):.1f} × {dims_unitarias.get('height', 0):.1f} cm"
    
    # Datos del envío total (aplica a ambos tipos de embalaje)
    peso_total_envio = shipping_metrics.get('peso_total_kg', 0)
    volumen_total_envio = shipping_metrics.get('volumen_total_cbm', 0)
    peso_facturable = shipping_metrics.get('peso_facturable_kg', 0)
    packaging_type = shipping_metrics.get('packaging_type', 'individual')
    num_cajas = shipping_metrics.get('num_boxes', 1)
    
    # Para embalaje múltiple, también incluir datos de la caja
    if packaging_type == 'multiple':
        dims_caja = shipping_details.get('box_dimensions_cm', {})
        dimensiones_caja = f"{dims_caja.get('length', 0):.1f} × {dims_caja.get('width', 0):.1f} × {dims_caja.get('height', 0):.1f} cm"
        units_per_box = shipping_details.get('units_per_box', 1)
    else:
        dimensiones_caja = dimensiones_unitarias
        units_per_box = 1
    
    metodo_flete = result['configuracion'].get('tipo_flete', '')
    
    # Obtener datos de configuración
    tipo_importador = result['configuracion'].get('tipo_importador', '')
    destino = result['configuracion'].get('destino_importacion', '')
    provincia = result['configuracion'].get('provincia', '')
    
    # CORREGIDO: Obtener origen de manera más robusta
    origen = ''
    if 'product' in result:
        product = result['product']
        if hasattr(product, 'place_of_origin'):
            origen = product.place_of_origin
        elif isinstance(product, dict) and 'place_of_origin' in product:
            origen = product['place_of_origin']
        elif isinstance(product, dict) and 'origen' in product:
            origen = product['origen']
    
    # CORREGIDO: Obtener URL de imagen de manera más robusta
    image_url = ''
    if 'image_selection_info' in result and 'selected_url' in result['image_selection_info']:
        image_url = result['image_selection_info']['selected_url']
    elif 'product' in result:
        product = result['product']
        if hasattr(product, 'image_url'):
            image_url = product.image_url
        elif isinstance(product, dict) and 'image_url' in product:
            image_url = product['image_url']
    
    # CORREGIDO: Obtener datos del producto de manera más robusta
    producto_titulo = ''
    producto_url = ''
    if 'product' in result:
        product = result['product']
        if hasattr(product, 'title'):
            producto_titulo = product.title
        elif isinstance(product, dict) and 'title' in product:
            producto_titulo = product['title']
        elif isinstance(product, dict) and 'name' in product:
            producto_titulo = product['name']
            
        if hasattr(product, 'url'):
            producto_url = product.url
        elif isinstance(product, dict) and 'url' in product:
            producto_url = product['url']
    
    # Preparar datos para exportar - TODOS LOS VALORES COMO NÚMEROS O STRINGS PARA EVITAR ERRORES DE API
    export_data = {
        "fecha": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "producto": str(producto_titulo),
        "imagen_url": str(image_url),
        "url_producto": str(producto_url),
        "cantidad": int(import_quantity),
        "precio_unitario_fob": round(float(precio_unitario), 2),
        "subtotal_fob": round(float(precio_unitario * import_quantity), 2),
        "moneda": "USD",
        "tipo_cambio": round(float(cotizacion), 2),
        "ncm": str(ncm_code),
        "descripcion_ncm": str(ncm_description),
        "derechos_importacion_pct": round(float(derechos_importacion_pct), 4),
        "derechos_importacion": round(float(derechos_importacion), 2),
        "tasa_estadistica_pct": round(float(tasa_estadistica_pct), 4),
        "tasa_estadistica": round(float(tasa_estadistica), 2),
        "iva_importacion_pct": round(float(iva_importacion_pct), 4),
        "iva_importacion": round(float(iva_importacion), 2),
        "percepcion_iva_pct": round(float(percepcion_iva_pct), 4),
        "percepcion_iva": round(float(percepcion_iva), 2),
        "percepcion_ganancias_pct": round(float(percepcion_ganancias_pct), 4),
        "percepcion_ganancias": round(float(percepcion_ganancias), 2),
        "ingresos_brutos_pct": round(float(ingresos_brutos_pct), 4),
        "ingresos_brutos": round(float(ingresos_brutos), 2),
        "total_impuestos": round(float(total_impuestos), 2),
        "subtotal_con_impuestos": round(float(subtotal_con_impuestos), 2),
        "peso_unitario_kg": round(float(peso_unitario), 3),
        "dimensiones_unitarias": str(dimensiones_unitarias),
        "peso_total_envio_kg": round(float(peso_total_envio), 3),
        "volumen_total_envio_cbm": round(float(volumen_total_envio), 6),
        "peso_facturable_kg": round(float(peso_facturable), 3),
        "tipo_embalaje": str(packaging_type),
        "num_cajas": int(num_cajas),
        "dimensiones_caja": str(dimensiones_caja),
        "unidades_por_caja": int(units_per_box),
        "costo_flete_total": round(float(flete_total), 2),  # VALOR BASE para editar en Sheets
        "costo_flete_unitario": round(float(flete_unitario), 2),  # Para referencia
        "honorarios_despachante": round(float(honorarios_total), 2),
        "total_landed_cost": round(float(total_landed_cost), 2),
        "landed_cost_unit": round(float(landed_cost), 2),
        # Campos de margen (cuando haya configuración cargada)
        "precio_venta_unit": round(float(st.session_state.margin_config.get("precio_venta_unit_usd", 0.0)), 2),
        "comision_venta_pct": round(float(st.session_state.margin_config.get("comision_venta_pct", 0.0)) / 100.0, 4),
        # Eliminado: No exportar ARS
        "metodo_flete": str(metodo_flete),
        "origen": str(origen),
        "destino": str(destino),
        "tipo_importador": str(tipo_importador),
        "provincia": str(provincia),
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
        {"Campo": "DIE", "Valor": f"{tratamiento.get('die', 'N/A')}"},
        {"Campo": "Código IN", "Valor": f"{tratamiento.get('in_code', 'Sin intervenciones')}"},
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
        
        # Usar la nueva función de cálculo de métricas de envío
        shipping_metrics = _calculate_shipping_metrics(shipping_details, import_quantity)
        peso_total_kg = shipping_metrics["peso_total_kg"]
        volumen_total_cbm = shipping_metrics["volumen_total_cbm"]
        peso_volumetrico_total_kg = shipping_metrics["peso_volumetrico_kg"]
        peso_facturable_kg = shipping_metrics["peso_facturable_kg"]
        
        # Para compatibilidad con código existente - usar dimensiones correctas según tipo de embalaje
        packaging_type = shipping_details.get('packaging_type', 'individual')
        if packaging_type == 'individual':
            dims = shipping_details.get('dimensions_cm', {"length": 0.0, "width": 0.0, "height": 0.0})
            peso_unitario = shipping_details.get('weight_kg', 1.0)
        else:
            # Para embalaje múltiple, usar dimensiones de la caja
            dims = shipping_details.get('box_dimensions_cm', {"length": 0.0, "width": 0.0, "height": 0.0})
            # Calcular peso unitario estimado para compatibilidad
            box_total_weight = float(shipping_details.get('box_total_weight_kg', 0.0))
            units_per_box = shipping_details.get('units_per_box', 1)
            peso_unitario = box_total_weight / units_per_box if units_per_box > 0 else 1.0
        
        volumen_unitario_cbm = (dims['length'] * dims['width'] * dims['height']) / 1_000_000 if all(d > 0 for d in dims.values()) else 0
        
        flete_costo_total = 0.0
        metodo_calculo = "Sin datos"
        
        if new_flete_type == "Courier (Aéreo)":
            # NUEVO: Usar API unificada también en recálculo
            try:
                from carriers_apis_conections.unified_shipping_api import get_cheapest_shipping_rate
                
                dimensions_cm_dict = {
                    "length": dims.get('length', 25),
                    "width": dims.get('width', 35), 
                    "height": dims.get('height', 15)
                }
                
                # Usar API unificada en recálculo también con direcciones reales
                unified_result = get_cheapest_shipping_rate(
                    weight_kg=peso_facturable_kg,
                    origin_country=st.session_state.origin_details.get('countryCode', 'CN'),
                    origin_postal=st.session_state.origin_details.get('postalCode', '518000'),
                    dest_country=st.session_state.destination_details.get('countryCode', 'AR'),
                    dest_postal=st.session_state.destination_details.get('postalCode', 'C1000'),
                    test_mode=True,
                    debug=False
                )
                
                if unified_result["success"]:
                    best_quote = unified_result["best_quote"]
                    flete_costo_total = best_quote.cost_usd
                    metodo_calculo = f"{best_quote.carrier} - {best_quote.service_name} (recalc)"
                else:
                    # Fallback a DHL solo si la API unificada falla
                    # Definir direcciones por defecto para DHL
                    origin_details = {
                        "postalCode": "38125",
                        "cityName": "MEMPHIS",
                        "countryCode": "US",
                        "addressLine1": "address1",
                        "addressLine2": "address2",
                        "addressLine3": "address3"
                    }
                    destination_details = {
                        "postalCode": "C1000",
                        "cityName": "BUENOS AIRES",
                        "countryCode": "AR",
                        "addressLine1": "address1",
                        "addressLine2": "address2",
                        "addressLine3": "address3"
                    }
                    
                    dhl_result = st.session_state.dhl_service.calculate_freight_with_fallback(
                        weight_kg=peso_facturable_kg,
                        dimensions_cm=dimensions_cm_dict,
                        origin_details=origin_details,
                        destination_details=destination_details,
                        shipping_datetime=st.session_state.get('planned_shipping_datetime')
                    )
                    flete_costo_total = dhl_result["cost_usd"]
                    metodo_calculo = f"DHL {dhl_result['method']} (fallback recalc)"
                
                # Mantener variables para compatibilidad
                insurance_cost = 0.0
                argentina_taxes = 0.0
                
                # Usar flete_costo_total que ya se asignó arriba
                costo_flete_total_usd = flete_costo_total
                
                # Almacenar información completa del resultado para uso posterior
                result_session_data = {
                    'dhl_insurance_cost': insurance_cost,
                    'dhl_argentina_taxes': argentina_taxes,
                    'dhl_insurance_included': False,  # API unificada no maneja estos detalles
                    'dhl_taxes_included': False,  # API unificada no maneja estos detalles  
                    'cost_breakdown': {},  # API unificada maneja esto diferente
                    'test_mode': True,
                    'service': metodo_calculo,
                    'transit_days': 2  # Default para recálculo
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
            "metodo_calculo_flete": metodo_calculo,
            # NUEVO: Agregar desglose de costos DHL en recálculo si está disponible
            "dhl_cost_breakdown": result_session_data.get('cost_breakdown', {}) if 'result_session_data' in locals() and result_session_data else {},
            "dhl_test_mode": result_session_data.get('test_mode', True) if 'result_session_data' in locals() and result_session_data else True,
            "dhl_service_name": result_session_data.get('service', 'N/A') if 'result_session_data' in locals() and result_session_data else 'N/A',
            "dhl_transit_days": result_session_data.get('transit_days', 2) if 'result_session_data' in locals() and result_session_data else 2
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
    Subir datos a Google Sheets con fórmulas automáticas para cálculos dinámicos.
    
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
                # Información básica del producto
                "Fecha", "Producto", "Imagen", "URL", "Cantidad", 
                # Costos base
                "Precio Unit. FOB USD", "Subtotal FOB USD", "Tipo de Cambio", 
                # Clasificación arancelaria
                "Posición NCM Completa", "Descripción NCM",
                # Impuestos (porcentajes y montos)
                "Derechos Import. %", "Derechos Import. USD", 
                "Tasa Estadística %", "Tasa Estadística USD",
                "IVA Import. %", "IVA Import. USD",
                "Percep. IVA %", "Percep. IVA USD", 
                "Percep. Ganancias %", "Percep. Ganancias USD",
                "Ingresos Brutos %", "Ingresos Brutos USD",
                # Totales calculados
                "Total Impuestos USD", "Subtotal + Impuestos USD",
                # Logística detallada (individual vs múltiple)
                "Peso Unitario (kg)", "Dimensiones Unitarias (L×W×H cm)",
                "Peso Total Envío (kg)", "Volumen Total (m³)", "Peso Facturable (kg)",
                "Tipo Embalaje", "Núm. Cajas", "Dimensiones Caja (L×W×H cm)", "Unidades/Caja",
                "Flete Total USD", "Flete Unit. USD", "Honorarios USD",
                # Resultado final
                "Total Landed Cost USD", "Landed Cost Unit USD",
                # Precio y margen
                "Precio Venta Unit USD", "Comisión Venta %", "Comisión Unit USD", "Ingreso Neto Unit USD",
                "Margen Unit USD", "Margen % sobre PV", "Markup % sobre Costo", "Precio Breakeven PV",
                # Información adicional
                "Método Flete", "Origen", "Destino", "Tipo Importador"
            ]
            worksheet.append_row(headers)
            st.info("✅ Encabezados optimizados y relevantes agregados")
        
        # Función helper para limpiar valores
        def clean_value(value, default=""):
            """Limpiar valores para evitar errores de API de Google Sheets"""
            if value is None or value == "":
                return default
            if isinstance(value, (int, float)):
                return value
            if isinstance(value, str):
                return value.strip()
            return str(value)
        
        # Preparar datos usando los valores reales del diccionario
        row_data = [
            # Información básica del producto  
            clean_value(data_dict.get("fecha", "")),
            clean_value(data_dict.get("producto", "")),
            "",  # Imagen: se agregará fórmula después
            clean_value(data_dict.get("url_producto", "")),
            clean_value(data_dict.get("cantidad", 0)),
            # Costos base
            clean_value(data_dict.get("precio_unitario_fob", 0)),
            "",  # Subtotal FOB: FÓRMULA = Cantidad × Precio Unitario
            clean_value(data_dict.get("tipo_cambio", 0)),
            # Clasificación arancelaria
            clean_value(data_dict.get("ncm", "")),
            clean_value(data_dict.get("descripcion_ncm", "")),
            # Impuestos (porcentajes y montos)
            clean_value(data_dict.get("derechos_importacion_pct", 0)),
            "",  # Derechos Import. USD: FÓRMULA
            clean_value(data_dict.get("tasa_estadistica_pct", 0)),
            "",  # Tasa Estadística USD: FÓRMULA  
            clean_value(data_dict.get("iva_importacion_pct", 0)),
            "",  # IVA Import. USD: FÓRMULA
            clean_value(data_dict.get("percepcion_iva_pct", 0)),
            "",  # Percep. IVA USD: FÓRMULA
            clean_value(data_dict.get("percepcion_ganancias_pct", 0)),
            "",  # Percep. Ganancias USD: FÓRMULA
            clean_value(data_dict.get("ingresos_brutos_pct", 0)),
            "",  # Ingresos Brutos USD: FÓRMULA
            # Totales calculados
            "",  # Total Impuestos USD: FÓRMULA
            "",  # Subtotal + Impuestos USD: FÓRMULA
            # Logística detallada (individual vs múltiple)
            clean_value(data_dict.get("peso_unitario_kg", 0)),
            clean_value(data_dict.get("dimensiones_unitarias", "")),
            clean_value(data_dict.get("peso_total_envio_kg", 0)),
            clean_value(data_dict.get("volumen_total_envio_cbm", 0)),
            clean_value(data_dict.get("peso_facturable_kg", 0)),
            clean_value(data_dict.get("tipo_embalaje", "")),
            clean_value(data_dict.get("num_cajas", 1)),
            clean_value(data_dict.get("dimensiones_caja", "")),
            clean_value(data_dict.get("unidades_por_caja", 1)),
            clean_value(data_dict.get("costo_flete_total", 0)),  # FLETE TOTAL - VALOR BASE
            "",  # Flete Unit. USD: FÓRMULA = Flete Total / Cantidad
            "",  # Honorarios USD: FÓRMULA
            # Resultado final  
            "",  # Total Landed Cost USD: FÓRMULA
            clean_value(data_dict.get("landed_cost_unit", 0)),
            # Precio y margen (valores base, varias serán fórmulas)
            clean_value(data_dict.get("precio_venta_unit", 0)),
            clean_value(data_dict.get("comision_venta_pct", 0)),
            "",  # Comisión Unit USD: FÓRMULA
            "",  # Ingreso Neto Unit USD: FÓRMULA
            "",  # Margen Unit USD: FÓRMULA
            "",  # Margen % sobre PV: FÓRMULA
            "",  # Markup % sobre Costo: FÓRMULA
            "",  # Precio Breakeven PV: FÓRMULA
            # Información adicional
            clean_value(data_dict.get("metodo_flete", "")),
            clean_value(data_dict.get("origen", "")),
            clean_value(data_dict.get("destino", "")),
            clean_value(data_dict.get("tipo_importador", ""))
        ]
        
        # Agregar los datos base
        try:
            worksheet.append_row(row_data)
            st.success("✅ Datos base agregados exitosamente")
        except Exception as data_error:
            st.error(f"❌ Error al agregar datos: {data_error}")
            return False
        
        # Obtener el número de la última fila agregada (más confiable)
        try:
            # Contar las filas que realmente tienen datos
            all_values = worksheet.get_all_values()
            num_rows = len([row for row in all_values if any(cell.strip() for cell in row)])
            # Si no hay datos, usar un valor por defecto
            if num_rows == 0:
                num_rows = 2  # Asumiendo que hay encabezados en la fila 1
        except:
            # Fallback: usar row_count como antes
            num_rows = worksheet.row_count
        
        # AGREGAR FÓRMULAS DINÁMICAS USANDO BATCH UPDATE API V4
        st.info(f"🧮 Agregando fórmulas automáticas en fila {num_rows}...")
        
        try:
            # MAPEO CORRECTO DE COLUMNAS ACTUALIZADO (A=0, B=1, C=2...):
            # G=6: Subtotal FOB, L=11: Derechos USD, N=13: Tasa USD, P=15: IVA USD
            # R=17: Percep.IVA USD, T=19: Percep.Gan. USD, V=21: IIBB USD
            # W=22: Total Impuestos, X=23: Subtotal+Impuestos
            # Y=24: Peso Unit, Z=25: Dims Unit, AA=26: Peso Total, AB=27: Volumen, AC=28: Peso Fact
            # AD=29: Tipo Emb, AE=30: Núm Cajas, AF=31: Dims Caja, AG=32: Units/Caja
            # AH=33: Flete Total, AI=34: Flete Unit, AJ=35: Honorarios, AK=36: Landed Cost USD
            # AL=37: Landed Cost Unit USD, AM=38: PV Unit, AN=39: Comisión %, AO=40: Comisión USD
            # AP=41: Ingreso Neto Unit, AQ=42: Margen Unit, AR=43: Margen % PV, AS=44: Markup % Costo, AT=45: Breakeven PV
            
            # Preparar fórmulas críticas con batch_update
            formulas_requests = []
            
            # TODAS las fórmulas necesarias (CORREGIDAS CON MAPEO EXACTO)
            critical_formulas = [
                (6, f"=E{num_rows}*F{num_rows}"),   # G: Subtotal FOB = Cantidad × Precio Unit
                (11, f"=G{num_rows}*K{num_rows}"),  # L: Derechos USD = Subtotal × % Derechos
                (13, f"=G{num_rows}*M{num_rows}"),  # N: Tasa USD = Subtotal × % Tasa
                (15, f"=(G{num_rows}+L{num_rows}+N{num_rows})*O{num_rows}"),  # P: IVA USD = (Base+Derechos+Tasa) × % IVA
                (17, f"=(G{num_rows}+L{num_rows}+N{num_rows}+P{num_rows})*Q{num_rows}"),  # R: Percep. IVA USD
                (19, f"=G{num_rows}*S{num_rows}"),  # T: Percep. Ganancias USD = Subtotal × %
                (21, f"=G{num_rows}*U{num_rows}"),  # V: Ingresos Brutos USD = Subtotal × %
                (22, f"=L{num_rows}+N{num_rows}+P{num_rows}+R{num_rows}+T{num_rows}+V{num_rows}"),  # W: Total Impuestos
                (23, f"=G{num_rows}+W{num_rows}"),  # X: Subtotal + Impuestos
                # FLETE Y COSTOS FINALES (COLUMNAS ACTUALIZADAS):
                (34, f"=AH{num_rows}/E{num_rows}"),  # AI: Flete Unit = Flete Total ÷ Cantidad
                (35, f"=G{num_rows}*0,02"),         # AJ: Honorarios = 2% del Subtotal FOB (formato argentino)
                (36, f"=G{num_rows}+W{num_rows}+AH{num_rows}+AJ{num_rows}"),  # AK: Landed Cost Total
                # Precio y margen:
                (40, f"=AM{num_rows}*AN{num_rows}"),  # AO: Comisión USD = PV × Comisión %
                (41, f"=AM{num_rows}-AO{num_rows}"),  # AP: Ingreso Neto Unit = PV - Comisión
                (42, f"=AP{num_rows}-AL{num_rows}"),  # AQ: Margen Unit = Neto - Landed Unit
                (43, f"=IF(AM{num_rows}>0, AQ{num_rows}/AM{num_rows}, 0)"),  # AR: Margen % PV
                (44, f"=IF(AL{num_rows}>0, AQ{num_rows}/AL{num_rows}, 0)"),  # AS: Markup % Costo
                (45, f"=IF(1-AN{num_rows}>0, AL{num_rows}/(1-AN{num_rows}), 0)"),  # AT: Breakeven PV
            ]
            
            # Crear requests para batch_update
            for col_index, formula in critical_formulas:
                formulas_requests.append({
                    'updateCells': {
                        'range': {
                            'sheetId': 0,
                            'startRowIndex': num_rows - 1,  # 0-indexed
                            'endRowIndex': num_rows,
                            'startColumnIndex': col_index,  # 0-indexed
                            'endColumnIndex': col_index + 1
                        },
                        'rows': [{
                            'values': [{
                                'userEnteredValue': {
                                    'formulaValue': formula
                                }
                            }]
                        }],
                        'fields': 'userEnteredValue'
                    }
                })
            
            # Ejecutar batch_update
            sh.batch_update({'requests': formulas_requests})
            st.success(f"✅ {len(critical_formulas)} fórmulas aplicadas con batch_update")
            
        except Exception as formula_error:
            st.warning(f"⚠️ Error con batch_update: {formula_error}")
            
            # Fallback: usar update_cell individual (método que sabemos que funciona)
            try:
                st.info("🔄 Intentando método fallback con update_cell...")
                
                # Fórmulas críticas con números de columna 1-based para update_cell (CORREGIDAS)
                formulas_fallback = [
                    (7, f"=E{num_rows}*F{num_rows}"),   # G: Subtotal FOB = Cantidad × Precio Unit
                    (12, f"=G{num_rows}*K{num_rows}"),  # L: Derechos USD = Subtotal × % Derechos
                    (14, f"=G{num_rows}*M{num_rows}"),  # N: Tasa USD = Subtotal × % Tasa
                    (16, f"=(G{num_rows}+L{num_rows}+N{num_rows})*O{num_rows}"),  # P: IVA USD
                    (18, f"=(G{num_rows}+L{num_rows}+N{num_rows}+P{num_rows})*Q{num_rows}"),  # R: Percep. IVA USD
                    (20, f"=G{num_rows}*S{num_rows}"),  # T: Percep. Ganancias USD
                    (22, f"=G{num_rows}*U{num_rows}"),  # V: Ingresos Brutos USD
                    (23, f"=L{num_rows}+N{num_rows}+P{num_rows}+R{num_rows}+T{num_rows}+V{num_rows}"),  # W: Total Impuestos
                    (24, f"=G{num_rows}+W{num_rows}"),  # X: Subtotal + Impuestos
                    (35, f"=AH{num_rows}/E{num_rows}"), # AI: Flete Unit = Flete Total ÷ Cantidad (ACTUALIZADO)
                    (36, f"=G{num_rows}*0,02"),         # AJ: Honorarios = 2% del Subtotal FOB (ACTUALIZADO)
                    (37, f"=G{num_rows}+W{num_rows}+AH{num_rows}+AJ{num_rows}"),  # AK: Landed Cost Total (ACTUALIZADO)
                    # Precio y margen (1-based): AO=41, AP=42, AQ=43, AR=44, AS=45, AT=46
                    (41, f"=AM{num_rows}*AN{num_rows}"),  # AO: Comisión USD
                    (42, f"=AM{num_rows}-AO{num_rows}"),  # AP: Ingreso Neto Unit
                    (43, f"=AP{num_rows}-AL{num_rows}"),  # AQ: Margen Unit
                    (44, f"=IF(AM{num_rows}>0, AQ{num_rows}/AM{num_rows}, 0)"),  # AR: Margen % PV
                    (45, f"=IF(AL{num_rows}>0, AQ{num_rows}/AL{num_rows}, 0)"),  # AS: Markup % Costo
                    (46, f"=IF(1-AN{num_rows}>0, AL{num_rows}/(1-AN{num_rows}), 0)"),  # AT: Breakeven PV
                ]
                
                successful_formulas = 0
                for col_num, formula in formulas_fallback:
                    try:
                        worksheet.update_cell(num_rows, col_num, formula)
                        successful_formulas += 1
                        st.info(f"✅ Fórmula aplicada en columna {col_num}")
                    except Exception as cell_error:
                        st.warning(f"⚠️ Error en columna {col_num}: {cell_error}")
                        continue
                
                if successful_formulas > 0:
                    st.success(f"✅ {successful_formulas} fórmulas aplicadas con método fallback")
                else:
                    st.warning("⚠️ No se pudieron aplicar fórmulas automáticas")
                    
            except Exception as fallback_error:
                st.error(f"❌ Error en método fallback: {fallback_error}")
                # No retornar False porque los datos principales ya se subieron
        
        # Actualizar la fórmula de imagen usando método confiable
        try:
            imagen_url = data_dict.get("imagen_url", "")
            if imagen_url and imagen_url.strip() and imagen_url.startswith('http'):
                try:
                    # Usar update_cell que sabemos que funciona
                    worksheet.update_cell(num_rows, 3, f'=IMAGE("{imagen_url.strip()}")')
                    st.info("✅ Imagen agregada exitosamente")
                except Exception as img_api_error:
                    # Si falla la imagen, agregar solo la URL como texto
                    worksheet.update_cell(num_rows, 3, imagen_url.strip())
                    st.info("ℹ️ Imagen como texto agregada (fórmula IMAGE falló)")
            else:
                st.info("ℹ️ Sin imagen válida para mostrar")
        except Exception as image_error:
            st.warning(f"⚠️ Error general con imagen: {image_error}")
        
        # Aplicar formato a las columnas de moneda
        try:
            # Formato de moneda para columnas USD (precios y costos) - ACTUALIZADO
            currency_usd_columns = ['F', 'G', 'L', 'N', 'P', 'R', 'T', 'V', 'W', 'X', 'AH', 'AI', 'AJ', 'AK', 'AL', 'AM', 'AO', 'AP', 'AQ', 'AT']
            for col in currency_usd_columns:
                try:
                    worksheet.format(f'{col}{num_rows}', {
                        'numberFormat': {
                            'type': 'CURRENCY',
                            'pattern': '"$"#,##0.00'
                        }
                    })
                except:
                    pass  # Si falla el formato, continuar
            
            # Formato para columnas numéricas especiales
            # Peso (kg) - columnas Y, AA, AC
            weight_columns = ['Y', 'AA', 'AC']
            for col in weight_columns:
                try:
                    worksheet.format(f'{col}{num_rows}', {
                        'numberFormat': {
                            'type': 'NUMBER',
                            'pattern': '#0.000" kg"'
                        }
                    })
                except:
                    pass
            
            # Volumen (m³) - columna AB
            try:
                worksheet.format(f'AB{num_rows}', {
                    'numberFormat': {
                        'type': 'NUMBER',
                        'pattern': '#0.000000" m³"'
                    }
                })
            except:
                pass
            
            # Formato de porcentaje para columnas de %
            percentage_columns = ['K', 'M', 'O', 'Q', 'S', 'U', 'AN', 'AR', 'AS']
            for col in percentage_columns:
                try:
                    worksheet.format(f'{col}{num_rows}', {
                        'numberFormat': {
                            'type': 'PERCENT',
                            'pattern': '#0.00%'
                        }
                    })
                except:
                    pass  # Si falla el formato, continuar
            
            # Formato para columnas de cantidad (enteros)
            integer_columns = ['E', 'AE', 'AG']  # Cantidad, Núm. Cajas, Unidades/Caja
            for col in integer_columns:
                try:
                    worksheet.format(f'{col}{num_rows}', {
                        'numberFormat': {
                            'type': 'NUMBER',
                            'pattern': '#0'
                        }
                    })
                except:
                    pass
                    
            st.info("✅ Formato esencial aplicado (USD, ARS, porcentajes, peso)")
            
        except Exception as format_error:
            st.warning(f"⚠️ Error al aplicar formato: {format_error}")
        
        # Obtener la URL de la hoja para mostrarla al usuario
        try:
            sheet_url = sh.url
            st.info(f"📋 Ver hoja: {sheet_url}")
            
            # Mostrar resumen de fórmulas agregadas
            st.success("🧮 **Fórmulas dinámicas aplicadas (LOGÍSTICA MEJORADA - SIN ARS):**")
            formulas_info = [
                "✅ Subtotal FOB = Cantidad × Precio Unitario (E×F)",
                "✅ Derechos = Subtotal FOB × % Derechos (G×K)",
                "✅ Tasa Estadística = Subtotal FOB × % Tasa (G×M)",
                "✅ IVA = (Base + Derechos + Tasa) × % IVA",
                "✅ Percepciones calculadas según normativa argentina",
                "✅ Honorarios = 2% del Subtotal FOB (G×0,02)",
                "📦 NUEVO: Columnas específicas para embalaje múltiple",
                "⚖️ Peso Total Envío, Volumen Total, Peso Facturable",
                "📊 Núm. Cajas, Dimensiones Caja, Unidades/Caja",
                "🚚 Flete Total = VALOR BASE EDITABLE (de la app)",
                "🧮 Flete Unitario = Flete Total ÷ Cantidad (AH÷E)",
                "✅ Landed Cost = Subtotal + Impuestos + Flete + Honorarios",
                "❌ ELIMINADO: Conversión a ARS (solo USD)",
                "✅ Formato optimizado: USD, kg, m³, cantidades",
                "🎯 VENTAJA: Claridad total entre embalaje individual vs múltiple",
                "🔢 Fórmulas con formato argentino (comas como separador decimal)"
            ]
            for info in formulas_info:
                st.write(f"  {info}")
                
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



if __name__ == "__main__":
    main() 