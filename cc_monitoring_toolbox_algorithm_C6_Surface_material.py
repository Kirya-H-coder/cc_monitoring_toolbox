# -*- coding: utf-8 -*-

import os
import webbrowser
from collections import defaultdict
from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFileDestination,
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsProcessingUtils,
    QgsGraduatedSymbolRenderer,
    QgsRendererRange,
    QgsFillSymbol,
    QgsWkbTypes
)


class CCMonitoringToolboxAlgorithmSurfaceMaterial(QgsProcessingAlgorithm):

    INPUT = 'INPUT'
    MATERIAL_FIELD = 'MATERIAL_FIELD'
    DARKNESS_FIELD = 'DARKNESS_FIELD'
    OUTPUT = 'OUTPUT'
    OUTPUT_HTML = 'OUTPUT_HTML'

    # Mapping dictionary based on PDF: (Ds_dry, Dc_dry, N_dry, Ds_wet, Dc_wet, N_wet)
    LOOKUP_TABLE = {
        ("ASP", 1): (3.5, 4.0, 3.5, 3.5, 4.0, 3.5),
        ("ASP", 2): (4.5, 4.5, 4.0, 4.5, 4.5, 4.0),
        ("ASP", 3): (5.0, 5.0, 4.0, 5.0, 5.0, 4.0),
        ("CON", 1): (2.0, 4.0, 4.0, 2.0, 4.0, 4.0),
        ("CON", 2): (4.0, 4.0, 5.0, 4.0, 4.0, 5.0),
        ("CON", 3): (4.5, 4.5, 5.0, 4.5, 4.5, 5.0),
        ("CBL", 1): (3.0, 3.5, 3.0, 3.0, 3.5, 3.0),
        ("CBL", 2): (3.5, 3.5, 3.0, 3.5, 3.5, 3.0),
        ("CBL", 3): (4.0, 4.0, 3.5, 4.0, 4.0, 3.5),
        ("BRK", 1): (2.5, 3.5, 2.5, 2.5, 3.5, 2.5),
        ("BRK", 2): (3.5, 3.0, 2.5, 3.5, 3.0, 2.5),
        ("BRK", 3): (4.0, 4.0, 3.0, 4.0, 4.0, 3.0),
        ("GRV", 1): (2.5, 3.5, 2.0, 2.5, 3.5, 2.0),
        ("GRV", 2): (3.5, 3.5, 2.5, 3.5, 3.5, 2.5),
        ("GRV", 3): (4.0, 4.0, 3.0, 4.0, 4.0, 3.0),
        ("WD", 1): (3.0, 3.0, 1.5, 3.0, 3.0, 1.5),
        ("WD", 2): (3.5, 3.5, 1.5, 3.5, 3.5, 1.5),
        ("WD", 3): (4.5, 4.5, 1.5, 4.5, 4.5, 1.5),
        ("RBR", 1): (3.5, 4.0, 1.5, 3.5, 4.0, 1.5),
        ("RBR", 2): (4.5, 4.5, 1.5, 4.5, 4.5, 1.5),
        ("RBR", 3): (5.0, 5.0, 1.5, 5.0, 5.0, 1.5),
        ("LMS", 1): (1.5, 3.5, 2.5, 1.5, 3.5, 2.5),
        ("LMS", 2): (2.5, 3.5, 3.0, 2.5, 3.5, 3.0),
        ("LMS", 3): (3.5, 4.0, 3.5, 3.5, 4.0, 3.5),
        ("GRN", 1): (2.5, 3.5, 4.0, 2.5, 3.5, 4.0),
        ("GRN", 2): (3.0, 3.5, 4.0, 3.0, 3.5, 4.0),
        ("GRN", 3): (4.0, 4.0, 4.5, 4.0, 4.0, 4.5),
        ("BST", 1): (3.5, 4.0, 5.0, 3.5, 4.0, 5.0),
        ("BST", 2): (4.0, 4.0, 5.0, 4.0, 4.0, 5.0),
        ("BST", 3): (4.5, 4.5, 5.0, 4.5, 4.5, 5.0),
        ("PER", 1): (3.5, 4.0, 2.0, 2.0, 3.0, 3.5),
        ("PER", 2): (4.5, 4.5, 2.0, 2.5, 2.5, 3.5),
        ("PER", 3): (5.0, 5.0, 2.0, 3.0, 3.0, 3.5),
        ("SPS", 1): (3.0, 3.5, 2.5, 1.5, 2.0, 3.5),
        ("SPS", 2): (3.5, 3.5, 2.5, 1.5, 2.0, 3.5),
        ("SPS", 3): (4.0, 4.0, 2.5, 2.0, 2.5, 3.5),
        ("SOI", 1): (3.5, 3.5, 1.5, 2.0, 2.5, 3.5),
        ("SOI", 2): (4.0, 4.0, 1.5, 2.0, 2.5, 3.5),
        ("SOI", 3): (4.5, 4.5, 2.0, 2.5, 2.5, 3.5),
    }

    # Special materials independent of darkness[cite: 1]
    SPECIAL_CASES = {
        "VEG": (3.5, 3.5, 2.5, 1.0, 2.5, 3.0),
        "WAT": (2.5, 2.5, 3.5, 2.5, 2.5, 3.5)
    }

    # Default fallback for unassigned materials[cite: 1]
    DEFAULT_VALUES = (3.0, 3.0, 3.0, 3.0, 3.0, 3.0)

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return CCMonitoringToolboxAlgorithmSurfaceMaterial()

    def name(self):
        return 'surfacematerialevaluator'

    def displayName(self):
        return self.tr('Surface Material Evaluator')

    def group(self):
        return self.tr('Cooling')

    def groupId(self):
        return 'Cooling'

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT, self.tr('Surface Material Layer (Polygons)'), [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterField(self.MATERIAL_FIELD, self.tr('Material Abbreviation Field'), parentLayerParameterName=self.INPUT))
        self.addParameter(QgsProcessingParameterField(self.DARKNESS_FIELD, self.tr('Darkness Field (1-3)'), parentLayerParameterName=self.INPUT, optional=True))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr('Evaluated Surface Material Layer')))
        self.addParameter(QgsProcessingParameterFileDestination(self.OUTPUT_HTML, self.tr('HTML Matrix Report'), 'HTML files (*.html)'))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        mat_field = self.parameterAsString(parameters, self.MATERIAL_FIELD, context)
        dark_field = self.parameterAsString(parameters, self.DARKNESS_FIELD, context)
        html_path = self.parameterAsFileOutput(parameters, self.OUTPUT_HTML, context)

        # Build output field schema
        fields = QgsFields(source.fields())
        eval_fields = ['Ds_dry', 'Dc_dry', 'N_dry', 'Ds_wet', 'Dc_wet', 'N_wet']
        for name in eval_fields:
            fields.append(QgsField(name, QVariant.Double))

        (sink, self.dest_id) = self.parameterAsSink(
            parameters, 
            self.OUTPUT, 
            context, 
            fields, 
            QgsWkbTypes.Polygon, 
            source.sourceCrs()
        )

        total_area = 0.0
        weighted_sums = [0.0] * 6
        material_areas = defaultdict(float)
        score_areas = defaultdict(float)

        features = source.getFeatures()
        for feature in features:
            if feedback.isCanceled():
                break

            # Parse material and darkness safely
            mat_val = str(feature[mat_field]).strip().upper() if mat_field and feature[mat_field] is not None else "UNASSIGNED"
            if not mat_val:
                mat_val = "UNASSIGNED"
            
            try:
                dark_val = int(feature[dark_field]) if dark_field and feature[dark_field] is not None else None
            except (ValueError, TypeError):
                dark_val = None

            # Look up evaluation values
            if mat_val in self.SPECIAL_CASES:
                scores = self.SPECIAL_CASES[mat_val]
            elif (mat_val, dark_val) in self.LOOKUP_TABLE:
                scores = self.LOOKUP_TABLE[(mat_val, dark_val)]
            else:
                scores = self.DEFAULT_VALUES

            # Area calculations
            geom = feature.geometry()
            area = geom.area() if geom else 0.0
            total_area += area

            # Track area per material and per Dc_wet score rating
            material_areas[mat_val] += area
            dc_wet_score = scores[4]  # Dc_wet score
            score_areas[dc_wet_score] += area

            for i in range(6):
                weighted_sums[i] += scores[i] * area

            # Write values to output layer
            new_feature = QgsFeature(feature)
            new_feature.setFields(fields)
            attributes = feature.attributes() + list(scores)
            new_feature.setAttributes(attributes)
            sink.addFeature(new_feature, QgsFeatureSink.FastInsert)

        # Calculate area-weighted site averages
        averages = [
            (w_sum / total_area) if total_area > 0 else 3.0 
            for w_sum in weighted_sums
        ]

        # Calculate percentage contribution dictionaries
        mat_percentages = {
            mat: (area / total_area * 100) if total_area > 0 else 0.0 
            for mat, area in material_areas.items()
        }
        score_percentages = {
            score: (area / total_area * 100) if total_area > 0 else 0.0 
            for score, area in score_areas.items()
        }

        # Generate HTML report file
        self.generate_html_report(html_path, averages, total_area, mat_percentages, score_percentages)

        # Open the generated HTML report automatically in default browser
        if html_path and os.path.exists(html_path):
            webbrowser.open(f"file:///{os.path.abspath(html_path)}")

        return {
            self.OUTPUT: self.dest_id,
            self.OUTPUT_HTML: html_path
        }

    def generate_html_report(self, filepath, averages, total_area, mat_percentages, score_percentages):
        """Generates an HTML report containing site averages and percentage contributions."""
        
        # Build Material Percentage Rows
        mat_rows_html = ""
        for mat in sorted(mat_percentages.keys()):
            pct = mat_percentages[mat]
            mat_rows_html += f"<tr><td>{mat}</td><td>{pct:.2f}%</td></tr>"

        # Build Score Grading Percentage Rows
        score_rows_html = ""
        for score in sorted(score_percentages.keys()):
            pct = score_percentages[score]
            score_rows_html += f"<tr><td>Rating {score}</td><td>{pct:.2f}%</td></tr>"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8"/>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 25px; color: #2c3e50; }}
                h2, h3 {{ color: #1a252f; border-bottom: 2px solid #34495e; padding-bottom: 6px; }}
                p {{ font-size: 14px; line-height: 1.5; }}
                .tables-container {{ display: flex; gap: 20px; flex-wrap: wrap; margin-top: 15px; }}
                table {{ border-collapse: collapse; width: 100%; max-width: 650px; margin-top: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
                .small-table {{ max-width: 310px; }}
                th, td {{ border: 1px solid #bdc3c7; padding: 10px; text-align: center; }}
                th {{ background-color: #34495e; color: #ffffff; font-size: 14px; }}
                tr:nth-child(even) {{ background-color: #f8f9fa; }}
                .target-row {{ background-color: #e8f8f5; font-weight: bold; color: #16a085; }}
                .footer-note {{ margin-top: 20px; font-size: 12px; color: #7f8c8d; italic; }}
            </style>
        </head>
        <body>
            <h2>Surface Material Assessment Report</h2>
            <p><strong>Total Evaluated Site Area:</strong> {total_area:.2f} m²</p>
            
            <h3>1. Thermal Scenario Site Averages</h3>
            <table>
                <tr>
                    <th>Thermal Scenario</th>
                    <th>Dry State Average</th>
                    <th>Wet State Average</th>
                </tr>
                <tr>
                    <td><strong>Surface Temp (Ds)</strong></td>
                    <td>{averages[0]:.2f}</td>
                    <td>{averages[3]:.2f}</td>
                </tr>
                <tr class="target-row">
                    <td><strong>Comfort Temp (Dc)</strong></td>
                    <td>{averages[1]:.2f}</td>
                    <td>{averages[4]:.2f}</td>
                </tr>
                <tr>
                    <td><strong>Night (N)</strong></td>
                    <td>{averages[2]:.2f}</td>
                    <td>{averages[5]:.2f}</td>
                </tr>
            </table>

            <h3>2. Material & Rating Coverage Breakdown</h3>
            <div class="tables-container">
                <table class="small-table">
                    <tr>
                        <th>Material</th>
                        <th>Coverage (% Area)</th>
                    </tr>
                    {mat_rows_html}
                </table>

                <table class="small-table">
                    <tr>
                        <th>Dc_wet Rating</th>
                        <th>Coverage (% Area)</th>
                    </tr>
                    {score_rows_html}
                </table>
            </div>

            <p class="footer-note">* Rating scale: 1 (Low thermal contribution / high cooling) to 5 (High thermal contribution / heating).</p>
        </body>
        </html>
        """
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)

    def postProcessAlgorithm(self, context, feedback):
        """Applies graduated vector styling based on Day Wet Comfort (Dc_wet)."""
        layer = QgsProcessingUtils.mapLayerFromString(self.dest_id, context)
        if layer:
            ranges = [
                QgsRendererRange(1.0, 2.0, QgsFillSymbol.createSimple({'color': '#2b83ba', 'outline_style': 'no'}), '1.0 - 2.0 (Low)'),
                QgsRendererRange(2.0, 3.0, QgsFillSymbol.createSimple({'color': '#abdda4', 'outline_style': 'no'}), '2.0 - 3.0 (Moderate-Low)'),
                QgsRendererRange(3.0, 4.0, QgsFillSymbol.createSimple({'color': '#fdae61', 'outline_style': 'no'}), '3.0 - 4.0 (Moderate-High)'),
                QgsRendererRange(4.0, 5.0, QgsFillSymbol.createSimple({'color': '#d7191c', 'outline_style': 'no'}), '4.0 - 5.0 (High)')
            ]

            renderer = QgsGraduatedSymbolRenderer('Dc_wet', ranges)
            layer.setRenderer(renderer)
            layer.triggerRepaint()

        return {self.OUTPUT: self.dest_id}