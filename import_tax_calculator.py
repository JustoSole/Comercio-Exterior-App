#!/usr/bin/env python3
"""
Calculadora de Impuestos de Importación - Argentina
==================================================

Sistema completo para calcular todos los impuestos aplicables a importaciones
en Argentina según la normativa fiscal vigente.

Autor: Desarrollado para análisis de comercio exterior
Versión: 1.0
Fecha: 2025
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Union
import json
import logging
from decimal import Decimal, ROUND_HALF_UP

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TipoImportador(Enum):
    """Tipos de importador según AFIP"""
    RESPONSABLE_INSCRIPTO = "responsable_inscripto"
    NO_INSCRIPTO = "no_inscripto"
    MONOTRIBUTISTA = "monotributista"


class DestinoImportacion(Enum):
    """Destino de la importación"""
    REVENTA = "reventa"
    USO_PROPIO = "uso_propio"
    BIEN_CAPITAL = "bien_capital"


class OrigenMercancia(Enum):
    """Origen de la mercancía"""
    MERCOSUR = "mercosur"
    EXTRAZONA = "extrazona"


@dataclass
class ImportData:
    """Datos básicos de la importación"""
    cif_value: Decimal  # Valor CIF en USD
    tipo_importador: TipoImportador
    destino: DestinoImportacion
    origen: OrigenMercancia
    derechos_importacion_pct: Optional[Decimal] = None
    es_bien_capital: bool = False
    tiene_exencion_iva: bool = False
    provincia: str = "CABA"  # Para cálculo de IIBB


@dataclass
class TaxResult:
    """Resultado del cálculo de un impuesto específico"""
    nombre: str
    alicuota: Decimal
    base_imponible: Decimal
    monto: Decimal
    aplica: bool
    observaciones: str = ""


@dataclass
class ImportTaxCalculation:
    """Resultado completo del cálculo de impuestos"""
    datos_importacion: ImportData
    impuestos: List[TaxResult]
    total_impuestos: Decimal
    costo_total: Decimal
    incidencia_porcentual: Decimal


class ImportTaxCalculator:
    """
    Calculadora de impuestos de importación para Argentina
    
    Calcula todos los impuestos aplicables según la normativa fiscal vigente,
    considerando el tipo de importador, destino de la mercancía y otras condiciones.
    """
    
    def __init__(self):
        """Inicializa la calculadora con las alícuotas vigentes"""
        self.tax_rates = {
            "tasa_estadistica": Decimal("0.03"),
            "iva_general": Decimal("0.21"),
            "iva_reducido": Decimal("0.105"),
            "percepcion_iva": Decimal("0.20"),
            "percepcion_ganancias": {
                "inscripto": Decimal("0.06"),
                "no_inscripto": Decimal("0.11")
            },
            "iibb": Decimal("0.025")
        }
        
        # Configuraciones por provincia para IIBB (ejemplo)
        self.iibb_rates = {
            "CABA": Decimal("0.025"),
            "BUENOS_AIRES": Decimal("0.025"),
            "CORDOBA": Decimal("0.03"),
            "SANTA_FE": Decimal("0.025"),
            # Agregar más provincias según necesidad
        }
    
    def calculate_all_taxes(self, import_data: ImportData) -> ImportTaxCalculation:
        """
        Calcula todos los impuestos aplicables a una importación
        
        Args:
            import_data: Datos de la importación
            
        Returns:
            ImportTaxCalculation: Resultado completo del cálculo
        """
        try:
            logger.info(f"Calculando impuestos para importación CIF: ${import_data.cif_value}")
            
            # Validar datos de entrada
            self._validate_import_data(import_data)
            
            impuestos = []
            
            # 0. Derechos de Importación (base para otros impuestos)
            derechos_importacion = self._calculate_derechos_importacion(import_data)
            impuestos.append(derechos_importacion)

            # 1. Tasa Estadística
            tasa_estadistica = self._calculate_tasa_estadistica(import_data)
            impuestos.append(tasa_estadistica)
            
            # Base imponible para IVA y percepciones: CIF + Derechos + Tasa
            base_imponible_iva = import_data.cif_value + derechos_importacion.monto + tasa_estadistica.monto
            
            # 2. IVA Importación
            iva_importacion = self._calculate_iva_importacion(import_data, base_imponible_iva)
            impuestos.append(iva_importacion)
            
            # 3. Percepción IVA Adicional
            percepcion_iva = self._calculate_percepcion_iva(import_data, base_imponible_iva)
            impuestos.append(percepcion_iva)
            
            # 4. Percepción Ganancias
            percepcion_ganancias = self._calculate_percepcion_ganancias(import_data, base_imponible_iva)
            impuestos.append(percepcion_ganancias)
            
            # 5. Ingresos Brutos
            iibb = self._calculate_iibb(import_data, base_imponible_iva)
            impuestos.append(iibb)
            
            # Calcular totales
            total_impuestos = sum(
                imp.monto for imp in impuestos if imp.aplica
            )
            
            costo_total = import_data.cif_value + total_impuestos
            incidencia_porcentual = (total_impuestos / import_data.cif_value) * 100 if import_data.cif_value > 0 else Decimal("0")
            
            resultado = ImportTaxCalculation(
                datos_importacion=import_data,
                impuestos=impuestos,
                total_impuestos=total_impuestos,
                costo_total=costo_total,
                incidencia_porcentual=incidencia_porcentual
            )
            
            logger.info(f"Cálculo completado. Total impuestos: ${total_impuestos}")
            return resultado
            
        except Exception as e:
            logger.error(f"Error calculando impuestos: {str(e)}")
            raise
    
    def _validate_import_data(self, data: ImportData) -> None:
        """Valida los datos de entrada"""
        if data.cif_value <= 0:
            raise ValueError("El valor CIF debe ser mayor a 0")
        
        if not isinstance(data.tipo_importador, TipoImportador):
            raise ValueError("Tipo de importador inválido")
        
        if not isinstance(data.destino, DestinoImportacion):
            raise ValueError("Destino de importación inválido")
    
    def _calculate_derechos_importacion(self, data: ImportData) -> TaxResult:
        """
        Calcula los Derechos de Importación (arancel).
        
        Aplica: Según el NCM del producto. Se recibe como un porcentaje.
        Base: Valor CIF.
        """
        aplica = data.derechos_importacion_pct is not None and data.derechos_importacion_pct > 0
        
        # La alícuota se convierte de % a decimal. Ej: 35.0 -> 0.35
        alicuota = data.derechos_importacion_pct / Decimal("100") if aplica else Decimal("0")
        base_imponible = data.cif_value if aplica else Decimal("0")
        monto = self._round_currency(base_imponible * alicuota)
        
        observaciones = "Calculado según % NCM." if aplica else "NCM sin derechos o no especificado."
        
        return TaxResult(
            nombre="Derechos de Importación",
            alicuota=alicuota,
            base_imponible=base_imponible,
            monto=monto,
            aplica=aplica,
            observaciones=observaciones
        )

    def _calculate_tasa_estadistica(self, data: ImportData) -> TaxResult:
        """
        Calcula la Tasa Estadística (3%)
        
        Aplica: Siempre para importaciones de bienes, excepto origen Mercosur (exento)
        Base: Valor CIF
        """
        aplica = data.origen != OrigenMercancia.MERCOSUR
        alicuota = self.tax_rates["tasa_estadistica"] if aplica else Decimal("0")
        base_imponible = data.cif_value if aplica else Decimal("0")
        monto = self._round_currency(base_imponible * alicuota)
        
        observaciones = ""
        if data.origen == OrigenMercancia.MERCOSUR:
            observaciones = "Exento por origen Mercosur"
        
        return TaxResult(
            nombre="Tasa Estadística",
            alicuota=alicuota,
            base_imponible=base_imponible,
            monto=monto,
            aplica=aplica,
            observaciones=observaciones
        )
    
    def _calculate_iva_importacion(self, data: ImportData, base_imponible: Decimal) -> TaxResult:
        """
        Calcula el IVA de Importación
        
        General: 21%
        Bienes de capital y ciertos insumos: 10.5%
        Base: Valor CIF + derechos + tasa estadística
        """
        # Determinar alícuota
        if data.es_bien_capital or data.destino == DestinoImportacion.BIEN_CAPITAL:
            alicuota = self.tax_rates["iva_reducido"]
            observaciones = "Alícuota reducida para bien de capital"
        else:
            alicuota = self.tax_rates["iva_general"]
            observaciones = "Alícuota general"
        
        # Verificar exenciones
        aplica = not data.tiene_exencion_iva
        if data.tiene_exencion_iva:
            alicuota = Decimal("0")
            observaciones = "Exento por disposición especial"
        
        # La base imponible ahora se pasa como argumento
        monto = self._round_currency(base_imponible * alicuota) if aplica else Decimal("0")
        
        return TaxResult(
            nombre="IVA Importación",
            alicuota=alicuota,
            base_imponible=base_imponible if aplica else Decimal("0"),
            monto=monto,
            aplica=aplica,
            observaciones=observaciones
        )
    
    def _calculate_percepcion_iva(self, data: ImportData, base_imponible_iva: Decimal) -> TaxResult:
        """
        Calcula la Percepción de IVA Adicional (20%)
        
        Aplica: A responsables inscriptos en IVA para reventa.
        Base: La misma que para el IVA
        """
        aplica = data.tipo_importador == TipoImportador.RESPONSABLE_INSCRIPTO and \
                 data.destino == DestinoImportacion.REVENTA
        
        alicuota = self.tax_rates["percepcion_iva"] if aplica else Decimal("0")
        monto = self._round_currency(base_imponible_iva * alicuota) if aplica else Decimal("0")
        
        observaciones = ""
        if not aplica:
            observaciones = "No aplica a monotributistas, no inscriptos o para uso propio/bien de capital."
            
        return TaxResult(
            nombre="Percepción IVA Adicional",
            alicuota=alicuota,
            base_imponible=base_imponible_iva if aplica else Decimal("0"),
            monto=monto,
            aplica=aplica,
            observaciones=observaciones
        )
    
    def _calculate_percepcion_ganancias(self, data: ImportData, base_imponible_iva: Decimal) -> TaxResult:
        """
        Calcula la Percepción de Impuesto a las Ganancias (6% o 11%)
        
        Aplica: Siempre, excepto para monotributistas.
        Base: La misma que para el IVA
        """
        if data.tipo_importador == TipoImportador.MONOTRIBUTISTA:
            aplica = False
            alicuota = Decimal("0")
            observaciones = "No aplica a monotributistas"
        elif data.tipo_importador == TipoImportador.NO_INSCRIPTO:
            aplica = True
            alicuota = self.tax_rates["percepcion_ganancias"]["no_inscripto"]
            observaciones = "Alícuota para no inscriptos"
        else: # Responsable inscripto
            aplica = True
            alicuota = self.tax_rates["percepcion_ganancias"]["inscripto"]
            observaciones = "Alícuota para responsables inscriptos"
        
        monto = self._round_currency(base_imponible_iva * alicuota) if aplica else Decimal("0")
        
        return TaxResult(
            nombre="Percepción Imp. a las Ganancias",
            alicuota=alicuota,
            base_imponible=base_imponible_iva if aplica else Decimal("0"),
            monto=monto,
            aplica=aplica,
            observaciones=observaciones
        )
    
    def _calculate_iibb(self, data: ImportData, base_imponible_iva: Decimal) -> TaxResult:
        """
        Calcula la percepción de Ingresos Brutos (2.5% general)
        
        Aplica: A responsables inscriptos y monotributistas, no a consumidores finales.
        Base: La misma que para el IVA
        """
        aplica = data.destino != DestinoImportacion.USO_PROPIO
        
        alicuota = self.iibb_rates.get(data.provincia, self.tax_rates["iibb"]) if aplica else Decimal("0")
        
        monto = self._round_currency(base_imponible_iva * alicuota) if aplica else Decimal("0")
        
        observaciones = f"Alícuota para {data.provincia}."
        if not aplica:
            observaciones = "No aplica para uso propio (consumidor final)."
            
        return TaxResult(
            nombre=f"Ingresos Brutos ({data.provincia})",
            alicuota=alicuota,
            base_imponible=base_imponible_iva if aplica else Decimal("0"),
            monto=monto,
            aplica=aplica,
            observaciones=observaciones
        )
    
    def _round_currency(self, amount: Decimal) -> Decimal:
        """Redondea un monto a 2 decimales"""
        return amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    def generate_report(self, calculation: ImportTaxCalculation) -> str:
        """
        Genera un reporte detallado del cálculo de impuestos
        
        Args:
            calculation: Resultado del cálculo de impuestos
            
        Returns:
            str: Reporte formateado
        """
        report = []
        report.append("=" * 60)
        report.append("REPORTE DE IMPUESTOS DE IMPORTACIÓN")
        report.append("=" * 60)
        report.append("")
        
        # Datos de la importación
        data = calculation.datos_importacion
        report.append("📋 DATOS DE LA IMPORTACIÓN:")
        report.append(f"   Valor CIF: ${data.cif_value:,.2f}")
        report.append(f"   Tipo importador: {data.tipo_importador.value}")
        report.append(f"   Destino: {data.destino.value}")
        report.append(f"   Origen: {data.origen.value}")
        if data.es_bien_capital:
            report.append("   ⚙️ Bien de capital: Sí")
        report.append("")
        
        # Detalle de impuestos
        report.append("💰 DETALLE DE IMPUESTOS:")
        report.append("")
        
        total_aplicables = Decimal("0")
        
        for impuesto in calculation.impuestos:
            status = "✅" if impuesto.aplica else "❌"
            report.append(f"{status} {impuesto.nombre}")
            
            if impuesto.aplica:
                report.append(f"   Alícuota: {impuesto.alicuota:.4%}")
                report.append(f"   Base: ${impuesto.base_imponible:,.2f}")
                report.append(f"   Monto: ${impuesto.monto:,.2f}")
                total_aplicables += impuesto.monto
            else:
                report.append(f"   No aplica - {impuesto.observaciones}")
            
            if impuesto.observaciones and impuesto.aplica:
                report.append(f"   Obs: {impuesto.observaciones}")
            
            report.append("")
        
        # Resumen
        report.append("=" * 40)
        report.append("📊 RESUMEN:")
        report.append(f"   Valor CIF: ${data.cif_value:,.2f}")
        report.append(f"   Total impuestos: ${calculation.total_impuestos:,.2f}")
        report.append(f"   Costo total: ${calculation.costo_total:,.2f}")
        report.append(f"   Incidencia: {calculation.incidencia_porcentual:.2f}%")
        report.append("=" * 40)
        
        return "\n".join(report)
    
    def export_to_json(self, calculation: ImportTaxCalculation) -> str:
        """
        Exporta el cálculo a formato JSON
        
        Args:
            calculation: Resultado del cálculo
            
        Returns:
            str: JSON formateado
        """
        def decimal_default(obj):
            if isinstance(obj, Decimal):
                return float(obj)
            if isinstance(obj, Enum):
                return obj.value
            raise TypeError
        
        data = {
            "datos_importacion": {
                "cif_value": calculation.datos_importacion.cif_value,
                "tipo_importador": calculation.datos_importacion.tipo_importador,
                "destino": calculation.datos_importacion.destino,
                "origen": calculation.datos_importacion.origen,
                "es_bien_capital": calculation.datos_importacion.es_bien_capital,
                "provincia": calculation.datos_importacion.provincia
            },
            "impuestos": [
                {
                    "nombre": imp.nombre,
                    "alicuota": imp.alicuota,
                    "base_imponible": imp.base_imponible,
                    "monto": imp.monto,
                    "aplica": imp.aplica,
                    "observaciones": imp.observaciones
                }
                for imp in calculation.impuestos
            ],
            "resumen": {
                "total_impuestos": calculation.total_impuestos,
                "costo_total": calculation.costo_total,
                "incidencia_porcentual": calculation.incidencia_porcentual
            }
        }
        
        return json.dumps(data, default=decimal_default, indent=2, ensure_ascii=False)


# Funciones de conveniencia
def calcular_impuestos_importacion(
    cif_value: float,
    tipo_importador: str = "responsable_inscripto",
    destino: str = "reventa",
    origen: str = "extrazona",
    es_bien_capital: bool = False,
    provincia: str = "CABA",
    derechos_importacion_pct: Optional[float] = None
) -> ImportTaxCalculation:
    """
    Calcula todos los impuestos de importación para un producto.
    
    Args:
        cif_value: Valor CIF en USD
        tipo_importador: Tipo de importador (responsable_inscripto, no_inscripto, monotributista)
        destino: Destino (reventa, uso_propio, bien_capital)
        origen: Origen (mercosur, extrazona)
        es_bien_capital: Si es bien de capital
        provincia: Provincia de destino para cálculo de IIBB.
        derechos_importacion_pct: Porcentaje de derechos de importación específico del NCM.

    Returns:
        ImportTaxCalculation: Objeto con el resultado completo del cálculo.
    """
    calculator = ImportTaxCalculator()
    
    import_data = ImportData(
        cif_value=Decimal(str(cif_value)),
        tipo_importador=TipoImportador(tipo_importador),
        destino=DestinoImportacion(destino),
        origen=OrigenMercancia(origen),
        es_bien_capital=es_bien_capital,
        provincia=provincia,
        derechos_importacion_pct=Decimal(str(derechos_importacion_pct)) if derechos_importacion_pct is not None else None
    )
    
    return calculator.calculate_all_taxes(import_data)


def main():
    """Función principal para testing y demostración"""
    print("🧮 Calculadora de Impuestos de Importación - Argentina")
    print("=" * 60)
    
    # Ejemplo 1: Importación para reventa, origen extrazona
    print("\n📦 EJEMPLO 1: Importación para reventa (origen extrazona)")
    print("-" * 50)
    
    resultado1 = calcular_impuestos_importacion(
        cif_value=10000.0,
        tipo_importador="responsable_inscripto",
        destino="reventa",
        origen="extrazona"
    )
    
    calculator = ImportTaxCalculator()
    print(calculator.generate_report(resultado1))
    
    # Ejemplo 2: Bien de capital origen Mercosur
    print("\n⚙️ EJEMPLO 2: Bien de capital (origen Mercosur)")
    print("-" * 50)
    
    resultado2 = calcular_impuestos_importacion(
        cif_value=50000.0,
        tipo_importador="responsable_inscripto",
        destino="bien_capital",
        origen="mercosur",
        es_bien_capital=True
    )
    
    print(calculator.generate_report(resultado2))


if __name__ == "__main__":
    main() 