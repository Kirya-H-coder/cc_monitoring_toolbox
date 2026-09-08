# -*- coding: utf-8 -*-

"""
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""

import os
import tempfile
from qgis.PyQt.QtCore import QCoreApplication, QVariant, Qt
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFileDestination,
    QgsProcessingOutputHtml,
    QgsProcessingOutputNumber,
    QgsProcessingUtils,
    QgsField,
    QgsFields,
    QgsFeature,
    QgsFeatureSink,
    QgsGeometry,
    QgsWkbTypes,
    QgsRuleBasedRenderer,
    QgsSymbol,
    QgsVectorLayerSimpleLabeling,
    QgsPalLayerSettings,
    QgsTextFormat,
    QgsTextBufferSettings
)


class CCMonitoringToolboxAlgorithmAccessibility(QgsProcessingAlgorithm):
    """
    QGIS Processing Algorithm for Green Space Visibility and Accessibility Analysis.
    Evaluates Visibility (A-D) and Accessibility (1-5), clips features to project border,
    generates summary HTML report, and applies custom HEX color-mapped styling (without outline borders) and labeling directly to the layer.
    """

    PROJECT_BORDER = 'PROJECT_BORDER'
    GREEN_LAYER = 'GREEN_LAYER'
    FIELD_VISIBILITY = 'FIELD_VISIBILITY'
    FIELD_ACCESSIBILITY = 'FIELD_ACCESSIBILITY'

    OUTPUT_LAYER = 'OUTPUT_LAYER'
    OUTPUT_HTML_REPORT = 'OUTPUT_HTML_REPORT'
    OUTPUT_TOTAL_GREEN_AREA = 'TOTAL_GREEN_AREA_M2'

    def __init__(self):
        super().__init__()
        self.dest_id = None

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return CCMonitoringToolboxAlgorithmAccessibility()

    def name(self):
        return 'accessibilityvisibilityanalyzer'

    def displayName(self):
        return self.tr('Green Space Visibility & Accessibility Analysis')

    def group(self):
        return self.tr('Greening')

    def groupId(self):
        return 'greening'

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.PROJECT_BORDER,
            self.tr('Project Border Area (Polygon)'),
            [QgsProcessing.TypeVectorPolygon]
        ))

        self.addParameter(QgsProcessingParameterFeatureSource(
            self.GREEN_LAYER,
            self.tr('Green Spaces Layer (Polygon)'),
            [QgsProcessing.TypeVectorPolygon]
        ))

        self.addParameter(QgsProcessingParameterField(
            self.FIELD_VISIBILITY,
            self.tr('Visibility Field (A=Visible, B=Screened, C=Hidden, D=Elevated)'),
            parentLayerParameterName=self.GREEN_LAYER,
            type=QgsProcessingParameterField.String
        ))

        self.addParameter(QgsProcessingParameterField(
            self.FIELD_ACCESSIBILITY,
            self.tr('Accessibility Field (1=Inaccessible to 5=Open Functional)'),
            parentLayerParameterName=self.GREEN_LAYER
        ))

        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT_LAYER,
            self.tr('Evaluated Accessibility Layer'),
            type=QgsProcessing.TypeVectorPolygon
        ))

        self.addParameter(QgsProcessingParameterFileDestination(
            self.OUTPUT_HTML_REPORT,
            self.tr('Accessibility HTML Report'),
            fileFilter='HTML files (*.html)',
            optional=True
        ))

        self.addOutput(QgsProcessingOutputHtml(
            self.OUTPUT_HTML_REPORT,
            self.tr('Accessibility HTML Summary')
        ))
        self.addOutput(QgsProcessingOutputNumber(
            self.OUTPUT_TOTAL_GREEN_AREA,
            self.tr('Total Green Area (m²)')
        ))

    def _get_mapped_color(self, vis, acc):
        # Exakte HEX-Farbcodes für Accessibility (1..5)
        base_hex_map = {
            1: '#bf661d',  # Rot / Braunrot
            2: '#ed941d',  # Orange
            3: '#f8d66d',  # Gelb
            4: '#b8d39c',  # Hellgrün
            5: '#71a05d'   # Dunkelgrün
        }
        
        # Sättigungsfaktor für Visibility (A..D): Vollfarbig -> Graustufen
        sat_factor_map = {
            'A': 1.0,   # Voll farbig (100% Originalfarbe)
            'B': 0.65,  # Leicht entsättigt
            'C': 0.35,  # Stark entsättigt
            'D': 0.08   # Nahezu grau
        }

        acc_int = int(acc) if str(acc).isdigit() else 1
        vis_str = str(vis).strip().upper() if vis else 'A'

        hex_color = base_hex_map.get(acc_int, '#bf661d')
        sat_factor = sat_factor_map.get(vis_str, 1.0)

        qcol = QColor(hex_color)
        h, s, l, a = qcol.getHslF()

        # Sättigung basierend auf Visibility reduzieren
        new_s = s * sat_factor
        return QColor.fromHslF(h, new_s, l, a).name()

    def processAlgorithm(self, parameters, context, feedback):
        border_source = self.parameterAsSource(parameters, self.PROJECT_BORDER, context)
        green_source = self.parameterAsSource(parameters, self.GREEN_LAYER, context)
        
        f_vis = self.parameterAsString(parameters, self.FIELD_VISIBILITY, context)
        f_acc = self.parameterAsString(parameters, self.FIELD_ACCESSIBILITY, context)

        html_path = self.parameterAsOutputLayer(parameters, self.OUTPUT_HTML_REPORT, context)
        if not html_path:
            html_path = os.path.join(tempfile.gettempdir(), 'accessibility_report.html')

        project_geom = QgsGeometry()
        total_project_area = 0.0

        if border_source:
            for feat in border_source.getFeatures():
                geom = feat.geometry()
                if geom and not geom.isEmpty():
                    project_geom = project_geom.combine(geom) if not project_geom.isEmpty() else QgsGeometry(geom)

        if not project_geom.isEmpty():
            total_project_area = project_geom.area()

        fields = QgsFields(green_source.fields())
        fields.append(QgsField("Vis_Code", QVariant.String))
        fields.append(QgsField("Acc_Code", QVariant.String))
        fields.append(QgsField("Green_Code", QVariant.String))
        fields.append(QgsField("Area_m2", QVariant.Double))

        sink, self.dest_id = self.parameterAsSink(
            parameters, self.OUTPUT_LAYER, context,
            fields, QgsWkbTypes.MultiPolygon, green_source.sourceCrs()
        )

        vis_stats = {'A': 0.0, 'B': 0.0, 'C': 0.0, 'D': 0.0}
        acc_stats = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0}
        combined_stats = {}

        total_green_area = 0.0

        for feat in green_source.getFeatures():
            if feedback.isCanceled():
                break

            geom = feat.geometry()
            if not geom or geom.isEmpty():
                continue

            if not project_geom.isEmpty() and geom.intersects(project_geom):
                intersection = geom.intersection(project_geom)
                if intersection.isEmpty():
                    continue

                poly_geom = QgsGeometry()
                if intersection.type() == QgsWkbTypes.PolygonGeometry:
                    poly_geom = intersection
                elif intersection.isMultipart():
                    polys = [g for g in intersection.asGeometryCollection() if g.type() == QgsWkbTypes.PolygonGeometry]
                    if polys:
                        poly_geom = QgsGeometry.collectGeometry(polys)

                if poly_geom.isEmpty():
                    continue
                
                target_geom = poly_geom
            elif project_geom.isEmpty():
                target_geom = geom
            else:
                continue

            area = target_geom.area()
            total_green_area += area

            vis_val = str(feat[f_vis]).strip().upper() if f_vis in feat.fields().names() and feat[f_vis] is not None else 'A'
            if vis_val not in vis_stats:
                vis_val = 'A'

            acc_raw = feat[f_acc] if f_acc in feat.fields().names() else 1
            try:
                acc_val = int(acc_raw)
                if acc_val not in acc_stats:
                    acc_val = 1
            except (ValueError, TypeError):
                acc_val = 1

            combined_code = f"{vis_val}{acc_val}"

            vis_stats[vis_val] += area
            acc_stats[acc_val] += area
            combined_stats[combined_code] = combined_stats.get(combined_code, 0.0) + area

            if sink:
                out_feat = QgsFeature(fields)
                out_feat.setGeometry(target_geom)
                attrs = feat.attributes()
                attrs.append(vis_val)
                attrs.append(str(acc_val))
                attrs.append(combined_code)
                attrs.append(round(area, 2))
                out_feat.setAttributes(attrs)
                sink.addFeature(out_feat, QgsFeatureSink.FastInsert)

        pct_project = (total_green_area / total_project_area * 100.0) if total_project_area > 0 else 0.0

        vis_labels = {
            'A': 'A - Street-level & fully visible',
            'B': 'B - Street-level (screened by hedges/fences)',
            'C': 'C - Hidden / enclosed in complexes',
            'D': 'D - Elevated (roofs, garages, etc.)'
        }

        acc_labels = {
            1: '1 - Publicly inaccessible or unusable',
            2: '2 - Incidental green (e.g. road verges)',
            3: '3 - Time-restricted / conditional green',
            4: '4 - Passive open (no active infrastructure)',
            5: '5 - Open functional green'
        }

        vis_rows = ""
        for code in ['A', 'B', 'C', 'D']:
            area_v = vis_stats[code]
            pct = (area_v / total_green_area * 100.0) if total_green_area > 0 else 0.0
            vis_rows += f"<tr><td><b>{vis_labels[code]}</b></td><td>{area_v:.2f} m²</td><td>{pct:.1f}%</td></tr>"

        acc_rows = ""
        for code in [1, 2, 3, 4, 5]:
            area_a = acc_stats[code]
            pct = (area_a / total_green_area * 100.0) if total_green_area > 0 else 0.0
            acc_rows += f"<tr><td><b>{acc_labels[code]}</b></td><td>{area_a:.2f} m²</td><td>{pct:.1f}%</td></tr>"

        matrix_headers = "".join([f"<th>Acc {i}</th>" for i in range(1, 6)])
        matrix_rows = ""
        for v in ['A', 'B', 'C', 'D']:
            matrix_rows += f"<tr><th>Vis {v}</th>"
            for a in range(1, 6):
                code = f"{v}{a}"
                c_area = combined_stats.get(code, 0.0)
                c_pct = (c_area / total_green_area * 100.0) if total_green_area > 0 else 0.0
                matrix_rows += f"<td><b>{code}</b><br>{c_pct:.1f}%<br><small>({c_area:.0f} m²)</small></td>"
            matrix_rows += "</tr>"

        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; color: #222; background-color: #fcfcfc; }}
        h2 {{ color: #71a05d; border-bottom: 2px solid #71a05d; padding-bottom: 6px; }}
        h3 {{ color: #71a05d; margin-top: 25px; }}
        .cards {{ display: flex; gap: 15px; margin-bottom: 20px; }}
        .card {{ background: #ffffff; border-radius: 8px; padding: 15px; flex: 1; border-left: 5px solid #71a05d; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .card h4 {{ margin: 0; font-size: 12px; color: #666; text-transform: uppercase; }}
        .card p {{ margin: 5px 0 0 0; font-size: 22px; font-weight: bold; color: #71a05d; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; background: white; }}
        th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
        th {{ background-color: #f2f5f2; color: #333; }}
        tr:nth-child(even) {{ background-color: #fafafa; }}
        .matrix td {{ text-align: center; font-size: 12px; }}
    </style>
</head>
<body>
    <h2>Green Space Visibility & Accessibility Report</h2>
    
    <div class="cards">
        <div class="card">
            <h4>Total Green Area</h4>
            <p>{total_green_area:.2f} m²</p>
        </div>
        <div class="card">
            <h4>Project Area Coverage</h4>
            <p>{pct_project:.1f}%</p>
        </div>
    </div>

    <h3>1. Visibility Distribution</h3>
    <table>
        <tr><th>Visibility Category</th><th>Area (m²)</th><th>% of Total Green</th></tr>
        {vis_rows}
    </table>

    <h3>2. Accessibility & Usability Distribution</h3>
    <table>
        <tr><th>Accessibility Category</th><th>Area (m²)</th><th>% of Total Green</th></tr>
        {acc_rows}
    </table>

    <h3>3. Combined Matrix Breakdown (% of Total Green Area)</h3>
    <table class="matrix">
        <tr><th>Visibility / Access</th>{matrix_headers}</tr>
        {matrix_rows}
    </table>
</body>
</html>
"""

        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        results = {
            self.OUTPUT_TOTAL_GREEN_AREA: total_green_area,
            self.OUTPUT_HTML_REPORT: html_path
        }
        if self.dest_id:
            results[self.OUTPUT_LAYER] = self.dest_id

        return results

    def postProcessAlgorithm(self, context, feedback):
        results = super().postProcessAlgorithm(context, feedback)
        
        if not self.dest_id:
            return results

        layer = QgsProcessingUtils.mapLayerFromString(self.dest_id, context)
        if not layer:
            return results

        # --- REGELBASIERTE SYMBOLOGIE (OHNE RAHMENLINIE) ---
        root_rule = QgsRuleBasedRenderer.Rule(None)

        for v in ['A', 'B', 'C', 'D']:
            for a in range(1, 6):
                code = f"{v}{a}"
                hex_color = self._get_mapped_color(v, a)
                
                symbol = QgsSymbol.defaultSymbol(layer.geometryType())
                symbol.setColor(QColor(hex_color))
                symbol.setOpacity(0.85)

                # Randlinie/Umrandung vollständig entfernen
                symbolLayer = symbol.symbolLayer(0)
                if symbolLayer:
                    symbolLayer.setStrokeStyle(Qt.NoPen)

                expression = f"\"Green_Code\" = '{code}'"
                rule = QgsRuleBasedRenderer.Rule(symbol, 0, 0, expression, code)
                root_rule.appendChild(rule)

        renderer = QgsRuleBasedRenderer(root_rule)
        layer.setRenderer(renderer)

        # --- KARTENBESCHRIFTUNG (LABELS FÜR GREEN_CODE) ---
        label_settings = QgsPalLayerSettings()
        label_settings.fieldName = "Green_Code"
        label_settings.placement = QgsPalLayerSettings.AroundPoint
        
        text_format = QgsTextFormat()
        text_format.setSize(9)
        text_format.setColor(QColor("#000000"))
        
        # Weißer Halo-Puffer für gute Lesbarkeit auf farbigem Grund
        buffer_settings = QgsTextBufferSettings()
        buffer_settings.setEnabled(True)
        buffer_settings.setSize(1.0)
        buffer_settings.setColor(QColor("#FFFFFF"))
        text_format.setBuffer(buffer_settings)

        label_settings.setFormat(text_format)
        label_settings.drawLabels = True

        labeling = QgsVectorLayerSimpleLabeling(label_settings)
        layer.setLabeling(labeling)
        layer.setLabelsEnabled(True)

        layer.triggerRepaint()
        return results