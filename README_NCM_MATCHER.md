# 🎯 NCM Position Matcher

**Validador y Enriquecedor de Códigos NCM para Comercio Exterior Argentino**

Sistema que valida códigos NCM contra base de datos oficial argentina y enriquece con atributos arancelarios específicos. Funciona como segunda etapa después del `ai_ncm_classifier.py`.

## 🚀 Características Principales

- ✅ **Búsqueda Exacta**: Validación directa de códigos NCM con datos oficiales
- 🔍 **Búsqueda Aproximada**: Algoritmo jerárquico inteligente para códigos parciales  
- 🤖 **Selección por IA**: GPT-4o-mini elige el mejor candidato cuando hay múltiples opciones
- 💰 **Enriquecimiento Fiscal**: AEC, DIE, TE, IVA, intervenciones automáticas
- 🏛️ **Régimen Simplificado**: Análisis de elegibilidad courier/postal
- ⚡ **Performance**: Búsquedas en ~2ms, dataset de 49K+ registros indexado
- 🔄 **Integración**: Compatible con `ai_ncm_classifier.py` existente

## 📊 Dataset

- **49,247 registros** oficiales NCM Argentina
- **10,283 códigos únicos** 
- **96 capítulos** (1-97)
- **35,132 posiciones terminales** + **14,115 subcategorías**
- Datos extraídos de PDFs oficiales con validación

## 🔧 Instalación

```bash
# Instalar dependencias
pip install pandas openai python-dotenv

# Verificar instalación
python ncm_position_matcher.py --stats
```

## 💻 Uso

### CLI Básico

```bash
# Búsqueda exacta
python ncm_position_matcher.py --input "0101.21.00 100W"

# Búsqueda aproximada
python ncm_position_matcher.py --input "televisor LCD"

# Con IA habilitada
python ncm_position_matcher.py --input "smartphone" --ai

# Estadísticas del dataset
python ncm_position_matcher.py --stats

# Procesamiento por lotes
python ncm_position_matcher.py --batch example_products.json --output results.json
```

### API Python

```python
import asyncio
from ncm_position_matcher import NCMPositionMatcher

# Inicializar
matcher = NCMPositionMatcher("path/to/ncm_data.csv")

# Búsqueda individual
result = await matcher.match_position("8528.72.00 100W")
print(result['match_type'])  # 'exacto'
print(result['position']['code'])  # '8528.72.00'

# Función de conveniencia
from ncm_position_matcher import match_single_ncm
result = await match_single_ncm("televisor", "data.csv")
```

### Integración con AI Classifier

```python
from integration_example import IntegratedNCMClassifier

# Clasificación completa: IA + Validación
classifier = IntegratedNCMClassifier("ncm_data.csv")
result = await classifier.classify_and_validate(
    "Televisor Samsung 32 pulgadas LCD",
    image_url="https://example.com/tv.jpg"
)

print(result['final_recommendation']['recommended_ncm'])
```

## 📋 Formato de Respuesta

### Búsqueda Exacta
```json
{
  "input": "0101.21.00 100W",
  "match_type": "exacto",
  "processing_time_ms": 2.35,
  "position": {
    "code": "0101.21.00",
    "sim": "100W", 
    "description": "Sangre pura de carrera",
    "attributes": {
      "aec": 0.0,
      "die": 0.0,
      "te": 0.0,
      "iva": 21.0,
      "iva_adicional": 0.0
    },
    "interventions": ["SENASA"],
    "simplified_regime": {
      "eligible": true,
      "restrictions": ["max_value_usd_3000", "max_weight_50kg"]
    },
    "hierarchy_info": {
      "parent": "10121",
      "level": 4,
      "type": "terminal"
    }
  },
  "metadata": {
    "classification_method": "exact_with_sim",
    "confidence": 100
  }
}
```

### Búsqueda Aproximada
```json
{
  "input": "televisor LCD",
  "match_type": "aproximado",
  "processing_time_ms": 1250.0,
  "candidates_analyzed": 15,
  "position": {
    "code": "8528.72.00",
    "description": "Televisores LCD hasta 42 pulgadas",
    "similarity_score": 0.89
  },
  "ai_selection": {
    "confidence": 89,
    "reasoning": "Seleccionado por tamaño específico y tecnología LCD",
    "method": "gpt-4o-mini"
  }
}
```

## 🧪 Testing

```bash
# Tests básicos
python test_ncm_position_matcher.py --basic

# Suite completa (requiere pytest)
pytest test_ncm_position_matcher.py -v

# Test de integración
python integration_example.py --quick
```

## 🏗️ Arquitectura

### Componentes Principales

1. **NCMDataLoader**: Carga y indexa datos CSV
2. **NCMSearchEngine**: Motor de búsqueda exacta/aproximada  
3. **AISelector**: Selección inteligente con GPT-4o-mini
4. **NCMPositionMatcher**: Orquestador principal

### Algoritmo de Búsqueda

```
Entrada → Búsqueda Exacta → [Encontrado] → Resultado
    ↓
    Búsqueda Aproximada → Candidatos → Selección IA → Resultado
    ↓
    [Sin Candidatos] → Error
```

### Estrategias de Matching

1. **Exacto con SIM**: `"8528.72.00 100W"`
2. **Exacto base**: `"8528.72.00"`  
3. **Jerárquico**: `"8528"` → busca `8528*`
4. **Semántico**: `"televisor"` → análisis NLP

## 🔍 Casos de Uso

### E-commerce
```python
# Validar código de producto
result = await matcher.match_position("8517.12.00")
if result['match_type'] == 'exacto':
    aec = result['position']['attributes']['aec']
    print(f"Arancel: {aec}%")
```

### Logística
```python
# Verificar régimen simplificado courier
result = await matcher.match_position("producto_importado")
if result['position']['simplified_regime']['eligible']:
    print("✅ Elegible para courier")
```

### Clasificación Automática
```python
# Flujo completo IA + Validación
integrated = IntegratedNCMClassifier("data.csv")
final = await integrated.classify_and_validate("iPhone 13")
ncm = final['final_recommendation']['recommended_ncm']
```

## ⚠️ Limitaciones

- **Datos**: Basado en extracción de PDFs (puede tener inconsistencias menores)
- **IA**: Requiere OpenAI API key para selección inteligente
- **Performance**: Búsquedas aproximadas más lentas (~1-3 segundos)
- **Cobertura**: Solo códigos NCM argentinos (no todos los países Mercosur)

## 🔧 Configuración Avanzada

### Variables de Entorno
```bash
export OPENAI_API_KEY="sk-..."
export NCM_DATA_FILE="custom_path.csv"
export LOG_LEVEL="DEBUG"
```

### Customización de IA
```python
matcher = NCMPositionMatcher(
    data_file="data.csv",
    ai_api_key="custom_key"
)

# Personalizar prompts en AISelector
```

## 📈 Performance

- **Carga inicial**: ~2 segundos (49K registros)
- **Búsqueda exacta**: 2-5ms
- **Búsqueda aproximada**: 500-3000ms (dependiendo de IA)
- **Memoria**: ~150MB para dataset completo
- **Concurrencia**: Soporta múltiples búsquedas simultáneas

## 🤝 Contribuciones

1. Fork del repositorio
2. Crear rama de feature: `git checkout -b feature/nueva-funcionalidad`
3. Tests: `pytest test_ncm_position_matcher.py`
4. Commit: `git commit -m "Añadir nueva funcionalidad"`
5. Push: `git push origin feature/nueva-funcionalidad`
6. Pull Request

## 📝 Changelog

### v1.0.0 (2025-01-21)
- ✅ Búsqueda exacta y aproximada
- ✅ Integración con IA (GPT-4o-mini)
- ✅ CLI completo
- ✅ Tests exhaustivos
- ✅ Documentación completa
- ✅ Dataset 49K+ registros oficiales

## 📄 Licencia

MIT License - Ver archivo LICENSE para detalles.

## 🆘 Soporte

- **Issues**: GitHub Issues
- **Documentación**: Este README
- **Ejemplos**: Ver `integration_example.py`
- **Tests**: Ver `test_ncm_position_matcher.py`

---

**Desarrollado para comercio exterior argentino** 🇦🇷 