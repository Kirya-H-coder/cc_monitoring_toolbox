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
    QgsCategorizedSymbolRenderer,
    QgsRendererCategory,
    QgsFillSymbol,
    QgsWkbTypes
)


class CCMonitoringToolboxAlgorithmSurfaceMaterial(QgsProcessingAlgorithm):

    INPUT = 'INPUT'
    MATERIAL_FIELD = 'MATERIAL_FIELD'
    DARKNESS_FIELD = 'DARKNESS_FIELD'
    OUTPUT_WET = 'OUTPUT_WET'
    OUTPUT_DRY = 'OUTPUT_DRY'
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

    SPECIAL_CASES = {
        "VEG": (3.5, 3.5, 2.5, 1.0, 2.5, 3.0),
        "WAT": (2.5, 2.5, 3.5, 2.5, 2.5, 3.5)
    }

    MATERIAL_NAMES = {
        "ASP": "Asphalt (ASP)",
        "CON": "Concrete (CON)",
        "CBL": "Concrete block paving (CBL)",
        "BRK": "Brick paving (BRK)",
        "GRV": "Gravel (GRV)",
        "WD": "Wood (WD)",
        "RBR": "Rubber (RBR)",
        "LMS": "Limestone (LMS)",
        "GRN": "Granite (GRN)",
        "BST": "Basalt (BST)",
        "PER": "Permeable material (PER)",
        "SPS": "Semi-paved surfaces (SPS)",
        "SOI": "Soil/Sand (SOI)",
        "VEG": "Vegetation/Grass (VEG)",
        "WAT": "Water (WAT)",
        "UNASSIGNED": "Unassigned / Fallback Material"
    }

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
        
        # Dual Map Output Sinks
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_WET, self.tr('Evaluated Layer - Day Comfort (Wet)')))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_DRY, self.tr('Evaluated Layer - Day Comfort (Dry)')))
        
        self.addParameter(QgsProcessingParameterFileDestination(self.OUTPUT_HTML, self.tr('HTML Matrix Report'), 'HTML files (*.html)'))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        mat_field = self.parameterAsString(parameters, self.MATERIAL_FIELD, context)
        dark_field = self.parameterAsString(parameters, self.DARKNESS_FIELD, context)
        html_path = self.parameterAsFileOutput(parameters, self.OUTPUT_HTML, context)

        fields = QgsFields(source.fields())
        eval_fields = ['Ds_dry', 'Dc_dry', 'N_dry', 'Ds_wet', 'Dc_wet', 'N_wet']
        for name in eval_fields:
            fields.append(QgsField(name, QVariant.Double))

        (sink_wet, self.dest_id_wet) = self.parameterAsSink(parameters, self.OUTPUT_WET, context, fields, QgsWkbTypes.Polygon, source.sourceCrs())
        (sink_dry, self.dest_id_dry) = self.parameterAsSink(parameters, self.OUTPUT_DRY, context, fields, QgsWkbTypes.Polygon, source.sourceCrs())

        total_area = 0.0
        weighted_sums = [0.0] * 6
        material_areas = defaultdict(float)
        score_wet_areas = defaultdict(float)
        score_dry_areas = defaultdict(float)

        features = source.getFeatures()
        for feature in features:
            if feedback.isCanceled():
                break

            mat_val = str(feature[mat_field]).strip().upper() if mat_field and feature[mat_field] is not None else "UNASSIGNED"
            if not mat_val:
                mat_val = "UNASSIGNED"
            
            try:
                dark_val = int(feature[dark_field]) if dark_field and feature[dark_field] is not None else None
            except (ValueError, TypeError):
                dark_val = None

            if mat_val in self.SPECIAL_CASES:
                scores = self.SPECIAL_CASES[mat_val]
            elif (mat_val, dark_val) in self.LOOKUP_TABLE:
                scores = self.LOOKUP_TABLE[(mat_val, dark_val)]
            else:
                scores = self.DEFAULT_VALUES

            geom = feature.geometry()
            area = geom.area() if geom else 0.0
            total_area += area

            material_areas[mat_val] += area
            
            dc_dry_score = scores[1]  # Day comfort dry score
            dc_wet_score = scores[4]  # Day comfort wet score
            
            score_dry_areas[dc_dry_score] += area
            score_wet_areas[dc_wet_score] += area

            for i in range(6):
                weighted_sums[i] += scores[i] * area

            new_feature = QgsFeature(feature)
            new_feature.setFields(fields)
            attributes = feature.attributes() + list(scores)
            new_feature.setAttributes(attributes)
            
            sink_wet.addFeature(new_feature, QgsFeatureSink.FastInsert)
            sink_dry.addFeature(new_feature, QgsFeatureSink.FastInsert)

        averages = [
            (w_sum / total_area) if total_area > 0 else 3.0 
            for w_sum in weighted_sums
        ]

        mat_percentages = {
            mat: (area / total_area * 100) if total_area > 0 else 0.0 
            for mat, area in material_areas.items()
        }
        
        all_scores = sorted(list(set(score_dry_areas.keys()).union(set(score_wet_areas.keys()))))
        
        score_dry_percentages = {score: (score_dry_areas[score] / total_area * 100) if total_area > 0 else 0.0 for score in all_scores}
        score_wet_percentages = {score: (score_wet_areas[score] / total_area * 100) if total_area > 0 else 0.0 for score in all_scores}

        self.generate_html_report(html_path, averages, total_area, mat_percentages, all_scores, score_dry_percentages, score_wet_percentages)

        if html_path and os.path.exists(html_path):
            webbrowser.open(f"file:///{os.path.abspath(html_path)}")

        return {
            self.OUTPUT_WET: self.dest_id_wet,
            self.OUTPUT_DRY: self.dest_id_dry,
            self.OUTPUT_HTML: html_path
        }

    def generate_html_report(self, filepath, averages, total_area, mat_percentages, all_scores, score_dry_percentages, score_wet_percentages):
        """Generates HTML report comparing Dry and Wet day comfort breakdowns side-by-side."""
        
        # Build Material Coverage Rows
        mat_rows_html = ""
        for mat in sorted(mat_percentages.keys()):
            full_name = self.MATERIAL_NAMES.get(mat, f"{mat} (Unknown)")
            pct = mat_percentages[mat]
            mat_rows_html += f"<tr><td style='text-align: left;'>{full_name}</td><td>{pct:.2f}%</td></tr>"

        # Build Side-by-Side Score Breakdown Rows
        score_rows_html = ""
        for score in all_scores:
            dry_pct = score_dry_percentages.get(score, 0.0)
            wet_pct = score_wet_percentages.get(score, 0.0)
            score_rows_html += f"<tr><td>Score {score:.1f}</td><td>{dry_pct:.2f}%</td><td>{wet_pct:.2f}%</td></tr>"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8"/>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 30px; color: #2c3e50; line-height: 1.6; }}
                h2, h3 {{ color: #1a252f; border-bottom: 2px solid #34495e; padding-bottom: 6px; }}
                p {{ font-size: 14px; }}
                .tables-container {{ display: flex; gap: 20px; flex-wrap: wrap; margin-top: 15px; }}
                table {{ border-collapse: collapse; width: 100%; max-width: 650px; margin-top: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.08); }}
                .small-table {{ max-width: 320px; }}
                .wide-table {{ max-width: 420px; }}
                th, td {{ border: 1px solid #bdc3c7; padding: 10px; text-align: center; }}
                th {{ background-color: #34495e; color: #ffffff; font-size: 14px; }}
                tr:nth-child(even) {{ background-color: #f8f9fa; }}
                .target-row {{ background-color: #e8f8f5; font-weight: bold; color: #16a085; }}
                .explanation-box {{ background-color: #f4f6f7; border-left: 4px solid #34495e; padding: 15px; margin-top: 25px; border-radius: 4px; max-width: 650px; }}
                .explanation-box ul {{ margin: 5px 0 0 0; padding-left: 20px; }}
                .explanation-box li {{ margin-bottom: 6px; font-size: 13px; }}
            </style>
        </head>
        <body>
            <h2>Surface Material Evaluation Report</h2>
            <p><strong>Total Evaluated Site Area:</strong> {total_area:.2f} m²</p>
            
            <h3>1. Thermal Scenario Site Averages</h3>
            <table>
                <tr>
                    <th>Thermal Scenario</th>
                    <th>Dry State Average</th>
                    <th>Wet State Average</th>
                </tr>
                <tr>
                    <td style="text-align: left;"><strong>Day surface temperature</strong></td>
                    <td>{averages[0]:.2f}</td>
                    <td>{averages[3]:.2f}</td>
                </tr>
                <tr class="target-row">
                    <td style="text-align: left;"><strong>Day comfort temperature</strong></td>
                    <td>{averages[1]:.2f}</td>
                    <td>{averages[4]:.2f}</td>
                </tr>
                <tr>
                    <td style="text-align: left;"><strong>Night</strong></td>
                    <td>{averages[2]:.2f}</td>
                    <td>{averages[5]:.2f}</td>
                </tr>
            </table>

            <h3>2. Material & Thermal Rating Breakdown</h3>
            <div class="tables-container">
                <table class="small-table">
                    <tr>
                        <th>Material</th>
                        <th>Coverage (% Area)</th>
                    </tr>
                    {mat_rows_html}
                </table>

                <table class="wide-table">
                    <tr>
                        <th>Thermal Rating</th>
                        <th>Day Comfort (Dry)</th>
                        <th>Day Comfort (Wet)</th>
                    </tr>
                    {score_rows_html}
                </table>
            </div>

            <div class="explanation-box">
                <strong>Understanding the Rating Scale (1 to 5):</strong>
                <ul>
                    <li><strong>Value 1 (Strong Cooling):</strong> Active day cooling (e.g., irrigated vegetation) or minimal night heat retention.</li>
                    <li><strong>Value 2 (Low Heating / Favorable):</strong> Day-favorable due to high reflectivity (e.g., limestone) or night-favorable due to low heat storage (e.g., wood, low-density soil).</li>
                    <li><strong>Value 3 (Moderate / Neutral):</strong> Moderate day absorption with balanced night heat release (e.g., light pavers, brick).</li>
                    <li><strong>Value 4 (High Heating):</strong> High daytime solar absorption or notable night heat release (e.g., standard concrete, granite).</li>
                    <li><strong>Value 5 (Strong Heating):</strong> Severe heat accumulation during the day and sustained night heat release (e.g., dark asphalt, basalt).</li>
                </ul>
            </div>
        </body>
        </html>
        """
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)

    def postProcessAlgorithm(self, context, feedback):
        """Styles both output layers separately (Wet mapped to Dc_wet, Dry mapped to Dc_dry)."""
        categories_wet = [
            QgsRendererCategory(1.0, QgsFillSymbol.createSimple({'color': '#4472C4', 'outline_style': 'no'}), '1.0 - Strong Cooling'),
            QgsRendererCategory(1.5, QgsFillSymbol.createSimple({'color': '#4472C4', 'outline_style': 'no'}), '1.5 - High Cooling'),
            QgsRendererCategory(2.0, QgsFillSymbol.createSimple({'color': '#B8D39C', 'outline_style': 'no'}), '2.0 - Moderate Cooling'),
            QgsRendererCategory(2.5, QgsFillSymbol.createSimple({'color': '#B8D39C', 'outline_style': 'no'}), '2.5 - Slight Cooling'),
            QgsRendererCategory(3.0, QgsFillSymbol.createSimple({'color': '#FECA36', 'outline_style': 'no'}), '3.0 - Neutral'),
            QgsRendererCategory(3.5, QgsFillSymbol.createSimple({'color': '#FECA36', 'outline_style': 'no'}), '3.5 - Slight Heating'),
            QgsRendererCategory(4.0, QgsFillSymbol.createSimple({'color': '#CC6813', 'outline_style': 'no'}), '4.0 - Moderate Heating'),
            QgsRendererCategory(4.5, QgsFillSymbol.createSimple({'color': '#CC6813', 'outline_style': 'no'}), '4.5 - High Heating'),
            QgsRendererCategory(5.0, QgsFillSymbol.createSimple({'color': '#CC6813', 'outline_style': 'no'}), '5.0 - Strong Heating'),
        ]

        # Apply Dc_wet styling to wet layer
        layer_wet = QgsProcessingUtils.mapLayerFromString(self.dest_id_wet, context)
        if layer_wet:
            renderer_wet = QgsCategorizedSymbolRenderer('Dc_wet', categories_wet)
            layer_wet.setRenderer(renderer_wet)
            layer_wet.triggerRepaint()

        # Apply Dc_dry styling to dry layer
        layer_dry = QgsProcessingUtils.mapLayerFromString(self.dest_id_dry, context)
        if layer_dry:
            renderer_dry = QgsCategorizedSymbolRenderer('Dc_dry', categories_wet)
            layer_dry.setRenderer(renderer_dry)
            layer_dry.triggerRepaint()

        return {
            self.OUTPUT_WET: self.dest_id_wet,
            self.OUTPUT_DRY: self.dest_id_dry
        }