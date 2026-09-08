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

import math
import os
import tempfile
from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFileDestination,
    QgsProcessingOutputHtml,
    QgsProcessingOutputNumber,
    QgsField,
    QgsFields,
    QgsFeature,
    QgsFeatureSink,
    QgsGeometry,
    QgsWkbTypes
)


class CCMonitoringToolboxAlgorithmGreenQuantity(QgsProcessingAlgorithm):
    """
    QGIS Processing Algorithm to evaluate Green Space Quantity.
    Outputs metrics directly to QGIS Results Panel, HTML Report, and
    calculates exact area (m²) and 3D volume (m³) attributes into feature tables.
    """

    # --- PARAMETER IDENTIFIERS ---
    PROJECT_BORDER = 'PROJECT_BORDER'
    
    # 1. Grass
    GRASS_LAYER = 'GRASS_LAYER'
    
    # 2. Shrubs
    SHRUBS_LAYER = 'SHRUBS_LAYER'
    FIELD_SHRUB_HEIGHT = 'FIELD_SHRUB_HEIGHT'

    # 3. Hedges
    HEDGES_LAYER = 'HEDGES_LAYER'
    FIELD_HEDGE_HEIGHT = 'FIELD_HEDGE_HEIGHT'

    # 4. Trees
    TREES_LAYER = 'TREES_LAYER'
    FIELD_TREE_HEIGHT = 'FIELD_TREE_HEIGHT'
    FIELD_STEM_HEIGHT = 'FIELD_STEM_HEIGHT'
    FIELD_CROWN_DIAMETER = 'FIELD_CROWN_DIAMETER'
    FIELD_CROWN_SHAPE = 'FIELD_CROWN_SHAPE'

    # Vector Output Sinks
    OUTPUT_GRASS_LAYER = 'OUTPUT_GRASS_LAYER'
    OUTPUT_SHRUBS_LAYER = 'OUTPUT_SHRUBS_LAYER'
    OUTPUT_HEDGES_LAYER = 'OUTPUT_HEDGES_LAYER'
    OUTPUT_TREES_LAYER = 'OUTPUT_TREES_LAYER'

    # Results Panel Outputs
    OUTPUT_HTML_REPORT = 'OUTPUT_HTML_REPORT'
    OUTPUT_TOTAL_GREEN_AREA = 'TOTAL_GREEN_AREA_M2'
    OUTPUT_TOTAL_GREEN_VOLUME = 'TOTAL_GREEN_VOLUME_M3'
    OUTPUT_TOTAL_TREE_COUNT = 'TOTAL_TREE_COUNT'

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return CCMonitoringToolboxAlgorithmGreenQuantity()

    def name(self):
        return 'greenquantityanalyzer'

    def displayName(self):
        return self.tr('Green Space Quantity & 3D Green Volume Metrics')

    def group(self):
        return self.tr('Greening')

    def groupId(self):
        return 'greening'

    def initAlgorithm(self, config=None):
        # Project Border Area
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.PROJECT_BORDER,
            self.tr('Project Border Area (Polygon)'),
            [QgsProcessing.TypeVectorPolygon]
        ))

        # 1. GRASS
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.GRASS_LAYER,
            self.tr('1. Grass / Lawn Layer (Polygons)'),
            [QgsProcessing.TypeVectorPolygon],
            optional=True
        ))

        # 2. SHRUBS
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.SHRUBS_LAYER,
            self.tr('2. Low Shrub / Groundcover Layer (Polygons)'),
            [QgsProcessing.TypeVectorPolygon],
            optional=True
        ))
        self.addParameter(QgsProcessingParameterField(
            self.FIELD_SHRUB_HEIGHT,
            self.tr('Shrub Average Height Field (m)'),
            parentLayerParameterName=self.SHRUBS_LAYER,
            type=QgsProcessingParameterField.Numeric,
            optional=True
        ))

        # 3. HEDGES
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.HEDGES_LAYER,
            self.tr('3. Hedge / High Shrub Layer (Polygons)'),
            [QgsProcessing.TypeVectorPolygon],
            optional=True
        ))
        self.addParameter(QgsProcessingParameterField(
            self.FIELD_HEDGE_HEIGHT,
            self.tr('Hedge Average Height Field (m)'),
            parentLayerParameterName=self.HEDGES_LAYER,
            type=QgsProcessingParameterField.Numeric,
            optional=True
        ))

        # 4. TREES
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.TREES_LAYER,
            self.tr('4. Tree Layer (Points or Polygons)'),
            [QgsProcessing.TypeVectorPoint, QgsProcessing.TypeVectorPolygon],
            optional=True
        ))
        self.addParameter(QgsProcessingParameterField(
            self.FIELD_TREE_HEIGHT,
            self.tr('Total Tree Height Field [h] (m)'),
            parentLayerParameterName=self.TREES_LAYER,
            type=QgsProcessingParameterField.Numeric,
            optional=True
        ))
        self.addParameter(QgsProcessingParameterField(
            self.FIELD_STEM_HEIGHT,
            self.tr('Stem Height Field [h_stem] (m)'),
            parentLayerParameterName=self.TREES_LAYER,
            type=QgsProcessingParameterField.Numeric,
            optional=True
        ))
        self.addParameter(QgsProcessingParameterField(
            self.FIELD_CROWN_DIAMETER,
            self.tr('Crown Diameter Field [d] (m)'),
            parentLayerParameterName=self.TREES_LAYER,
            type=QgsProcessingParameterField.Numeric,
            optional=True
        ))
        self.addParameter(QgsProcessingParameterField(
            self.FIELD_CROWN_SHAPE,
            self.tr('Crown Shape Field (Text string in attribute table)'),
            parentLayerParameterName=self.TREES_LAYER,
            type=QgsProcessingParameterField.String,
            optional=True
        ))

        # --- FEATURE SINK OUTPUTS ---
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT_GRASS_LAYER,
            self.tr('Evaluated Grass Layer (2D Area)'),
            type=QgsProcessing.TypeVectorPolygon,
            optional=True
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT_SHRUBS_LAYER,
            self.tr('Evaluated Shrubs Layer (2D Area & 3D Vol)'),
            type=QgsProcessing.TypeVectorPolygon,
            optional=True
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT_HEDGES_LAYER,
            self.tr('Evaluated Hedges Layer (3D Vol)'),
            type=QgsProcessing.TypeVectorPolygon,
            optional=True
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT_TREES_LAYER,
            self.tr('Evaluated Trees Layer (3D Vol)'),
            type=QgsProcessing.TypeVectorAnyGeometry,
            optional=True
        ))

        # --- HTML FILE DESTINATION PARAMETER ---
        self.addParameter(QgsProcessingParameterFileDestination(
            self.OUTPUT_HTML_REPORT,
            self.tr('Green Quantity HTML Report'),
            fileFilter='HTML files (*.html)',
            optional=True
        ))

        # --- RESULTS VIEWER OUTPUT DEFINITIONS ---
        self.addOutput(QgsProcessingOutputHtml(
            self.OUTPUT_HTML_REPORT,
            self.tr('Green Quantity HTML Summary')
        ))
        self.addOutput(QgsProcessingOutputNumber(
            self.OUTPUT_TOTAL_GREEN_AREA,
            self.tr('Total Green Area (m²)')
        ))
        self.addOutput(QgsProcessingOutputNumber(
            self.OUTPUT_TOTAL_GREEN_VOLUME,
            self.tr('Total 3D Green Volume (m³)')
        ))
        self.addOutput(QgsProcessingOutputNumber(
            self.OUTPUT_TOTAL_TREE_COUNT,
            self.tr('Tree Count')
        ))

    def _safe_float(self, val):
        if val is None:
            return 0.0
        try:
            val_str = str(val).replace(',', '.').strip()
            return float(val_str)
        except (ValueError, TypeError):
            return 0.0

    def _calc_tree_volume_from_shape(self, r, h_crown, shape_str):
        if r <= 0 or h_crown <= 0:
            return 0.0

        shape_str = str(shape_str).lower().strip() if shape_str else ""

        if any(s in shape_str for s in ["cone", "kegel", "pyramid"]):
            return (1.0 / 3.0) * math.pi * (r ** 2) * h_crown
        elif any(s in shape_str for s in ["paraboloid", "column", "säule"]):
            return 0.5 * math.pi * (r ** 2) * h_crown
        elif any(s in shape_str for s in ["cylinder", "zylinder"]):
            return math.pi * (r ** 2) * h_crown
        elif any(s in shape_str for s in ["hemisphere", "halbkugel"]):
            return (2.0 / 3.0) * math.pi * (r ** 2) * h_crown
        else:
            return (4.0 / 3.0) * math.pi * (r ** 2) * (h_crown / 2.0)

    def processAlgorithm(self, parameters, context, feedback):
        border_source = self.parameterAsSource(parameters, self.PROJECT_BORDER, context)
        
        grass_source = self.parameterAsSource(parameters, self.GRASS_LAYER, context)
        
        shrub_source = self.parameterAsSource(parameters, self.SHRUBS_LAYER, context)
        f_shrub_hgt = self.parameterAsString(parameters, self.FIELD_SHRUB_HEIGHT, context)

        hedge_source = self.parameterAsSource(parameters, self.HEDGES_LAYER, context)
        f_hedge_hgt = self.parameterAsString(parameters, self.FIELD_HEDGE_HEIGHT, context)

        tree_source = self.parameterAsSource(parameters, self.TREES_LAYER, context)
        f_h = self.parameterAsString(parameters, self.FIELD_TREE_HEIGHT, context)
        f_ts = self.parameterAsString(parameters, self.FIELD_STEM_HEIGHT, context)
        f_d = self.parameterAsString(parameters, self.FIELD_CROWN_DIAMETER, context)
        f_shape = self.parameterAsString(parameters, self.FIELD_CROWN_SHAPE, context)

        html_path = self.parameterAsOutputLayer(parameters, self.OUTPUT_HTML_REPORT, context)
        
        if not html_path:
            html_path = os.path.join(tempfile.gettempdir(), 'green_quantity_report.html')

        project_geom = QgsGeometry()
        total_project_area = 0.0

        if border_source:
            for feat in border_source.getFeatures():
                geom = feat.geometry()
                if geom and not geom.isEmpty():
                    project_geom = project_geom.combine(geom) if not project_geom.isEmpty() else QgsGeometry(geom)

        if not project_geom.isEmpty():
            total_project_area = project_geom.area()

        def process_polygon_layer(source, height_field, sink_param_id, mode='area_only'):
            if not source or project_geom.isEmpty():
                return 0.0, 0.0, None

            fields = QgsFields(source.fields())
            
            if mode == 'area_only':
                fields.append(QgsField("Area_m2", QVariant.Double))
                fields.append(QgsField("Sum_Area_m2", QVariant.Double))
            elif mode == 'both':
                fields.append(QgsField("Area_m2", QVariant.Double))
                fields.append(QgsField("Vol_m3", QVariant.Double))
                fields.append(QgsField("Sum_Area_m2", QVariant.Double))
                fields.append(QgsField("Sum_Vol_m3", QVariant.Double))
            elif mode == 'vol_only':
                fields.append(QgsField("Vol_m3", QVariant.Double))
                fields.append(QgsField("Sum_Vol_m3", QVariant.Double))

            sink, dest_id = self.parameterAsSink(
                parameters, sink_param_id, context,
                fields, QgsWkbTypes.MultiPolygon, source.sourceCrs()
            )

            cached_features = []
            layer_total_area = 0.0
            layer_total_vol = 0.0

            for feat in source.getFeatures():
                if feedback.isCanceled():
                    break
                geom = feat.geometry()
                if geom and geom.intersects(project_geom):
                    intersection = geom.intersection(project_geom)
                    if not intersection.isEmpty():
                        poly_geom = QgsGeometry()
                        if intersection.type() == QgsWkbTypes.PolygonGeometry:
                            poly_geom = intersection
                        elif intersection.isMultipart():
                            polys = [g for g in intersection.asGeometryCollection() if g.type() == QgsWkbTypes.PolygonGeometry]
                            if polys:
                                poly_geom = QgsGeometry.collectGeometry(polys)

                        if poly_geom.isEmpty():
                            continue

                        area = poly_geom.area()
                        
                        h = 0.0
                        if height_field and height_field in feat.fields().names():
                            h = self._safe_float(feat[height_field])
                        
                        vol = area * h
                        
                        layer_total_area += area
                        layer_total_vol += vol
                        
                        cached_features.append((feat, poly_geom, area, vol))

            if sink:
                for feat, poly_geom, area, vol in cached_features:
                    if feedback.isCanceled():
                        break
                    out_feat = QgsFeature(fields)
                    out_feat.setGeometry(poly_geom)
                    attrs = feat.attributes()

                    if mode == 'area_only':
                        attrs.append(round(area, 2))
                        attrs.append(round(layer_total_area, 2))
                    elif mode == 'both':
                        attrs.append(round(area, 2))
                        attrs.append(round(vol, 2))
                        attrs.append(round(layer_total_area, 2))
                        attrs.append(round(layer_total_vol, 2))
                    elif mode == 'vol_only':
                        attrs.append(round(vol, 2))
                        attrs.append(round(layer_total_vol, 2))

                    out_feat.setAttributes(attrs)
                    sink.addFeature(out_feat, QgsFeatureSink.FastInsert)

            return layer_total_area, layer_total_vol, dest_id

        area_grass, _, grass_dest_id = process_polygon_layer(
            grass_source, None, self.OUTPUT_GRASS_LAYER, mode='area_only'
        )

        area_shrubs, vol_shrubs, shrub_dest_id = process_polygon_layer(
            shrub_source, f_shrub_hgt, self.OUTPUT_SHRUBS_LAYER, mode='both'
        )

        area_hedges, vol_hedges, hedge_dest_id = process_polygon_layer(
            hedge_source, f_hedge_hgt, self.OUTPUT_HEDGES_LAYER, mode='vol_only'
        )

        # 4. PROCESS TREES (Mittelpunkt-Prüfung)
        vol_trees = 0.0
        tree_count = 0
        tree_sink, tree_dest_id = None, None

        if tree_source and not project_geom.isEmpty():
            tree_fields = QgsFields(tree_source.fields())
            tree_fields.append(QgsField("Vol_m3", QVariant.Double))
            tree_fields.append(QgsField("Sum_Vol_m3", QVariant.Double))

            (tree_sink, tree_dest_id) = self.parameterAsSink(
                parameters, self.OUTPUT_TREES_LAYER, context,
                tree_fields, tree_source.wkbType(), tree_source.sourceCrs()
            )

            cached_trees = []

            for feat in tree_source.getFeatures():
                if feedback.isCanceled():
                    break
                geom = feat.geometry()
                if not geom or geom.isEmpty():
                    continue

                # Mittelpunkt/Schwerpunkt der Geometrie bestimmen
                centroid_geom = geom if geom.type() == QgsWkbTypes.PointGeometry else geom.centroid()

                # Prüfen, ob der Mittelpunkt innerhalb der Projektgrenze liegt
                if project_geom.contains(centroid_geom) or project_geom.intersects(centroid_geom):
                    tree_count += 1
                    
                    h_tree = self._safe_float(feat[f_h]) if f_h and f_h in feat.fields().names() else 0.0
                    h_stem = self._safe_float(feat[f_ts]) if f_ts and f_ts in feat.fields().names() else 0.0
                    d_crown = self._safe_float(feat[f_d]) if f_d and f_d in feat.fields().names() else 0.0
                    shape_str = str(feat[f_shape]) if f_shape and f_shape in feat.fields().names() else ""

                    r = d_crown / 2.0
                    h_crown = max(0.0, h_tree - h_stem)

                    feature_vol = self._calc_tree_volume_from_shape(r, h_crown, shape_str)
                    vol_trees += feature_vol
                    
                    cached_trees.append((feat, geom, feature_vol))

            if tree_sink:
                for feat, geom, feature_vol in cached_trees:
                    if feedback.isCanceled():
                        break
                    out_feat = QgsFeature(tree_fields)
                    out_feat.setGeometry(geom)
                    attrs = feat.attributes()
                    attrs.append(round(feature_vol, 2))
                    attrs.append(round(vol_trees, 2))
                    out_feat.setAttributes(attrs)
                    tree_sink.addFeature(out_feat, QgsFeatureSink.FastInsert)

        total_green_area = area_grass + area_shrubs + area_hedges
        total_green_volume = vol_shrubs + vol_hedges + vol_trees

        pct_grass = (area_grass / total_project_area * 100.0) if total_project_area > 0 else 0.0
        pct_shrubs = (area_shrubs / total_project_area * 100.0) if total_project_area > 0 else 0.0
        pct_hedges = (area_hedges / total_project_area * 100.0) if total_project_area > 0 else 0.0
        pct_total_2d = (total_green_area / total_project_area * 100.0) if total_project_area > 0 else 0.0

        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: Arial, sans-serif; margin: 15px; color: #333; }}
        h2 {{ color: #2e7d32; border-bottom: 2px solid #2e7d32; padding-bottom: 5px; }}
        .cards {{ display: flex; gap: 15px; margin-bottom: 20px; }}
        .card {{ background: #f4f6f8; border-radius: 8px; padding: 12px 20px; flex: 1; border-left: 5px solid #2e7d32; }}
        .card h3 {{ margin: 0; font-size: 13px; color: #666; text-transform: uppercase; }}
        .card p {{ margin: 5px 0 0 0; font-size: 22px; font-weight: bold; color: #1b5e20; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
        th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        tr:nth-child(even) {{ background-color: #fafafa; }}
        .total-row {{ background-color: #e8f5e9 !important; font-weight: bold; }}
    </style>
</head>
<body>
    <h2>Green Infrastructure Overview</h2>
    
    <div class="cards">
        <div class="card">
            <h3>Total Green Area</h3>
            <p>{total_green_area:.2f} m²</p>
        </div>
        <div class="card">
            <h3>Total 3D Volume</h3>
            <p>{total_green_volume:.2f} m³</p>
        </div>
        <div class="card">
            <h3>Tree Count</h3>
            <p>{tree_count}</p>
        </div>
    </div>

    <p>Project Border Area: <b>{total_project_area:.2f} m²</b></p>

    <table>
        <tr>
            <th>Category</th>
            <th>2D Area (m²)</th>
            <th>% Coverage</th>
            <th>3D Volume (m³)</th>
        </tr>
        <tr>
            <td>1. Grass / Lawn</td>
            <td>{area_grass:.2f}</td>
            <td>{pct_grass:.1f}%</td>
            <td>-</td>
        </tr>
        <tr>
            <td>2. Shrubs</td>
            <td>{area_shrubs:.2f}</td>
            <td>{pct_shrubs:.1f}%</td>
            <td>{vol_shrubs:.2f}</td>
        </tr>
        <tr>
            <td>3. Hedges</td>
            <td>-</td>
            <td>-</td>
            <td>{vol_hedges:.2f}</td>
        </tr>
        <tr>
            <td>4. Trees ({tree_count} features)</td>
            <td>-</td>
            <td>-</td>
            <td>{vol_trees:.2f}</td>
        </tr>
        <tr class="total-row">
            <td>TOTAL</td>
            <td>{total_green_area:.2f}</td>
            <td>{pct_total_2d:.1f}%</td>
            <td>{total_green_volume:.2f}</td>
        </tr>
    </table>
</body>
</html>
"""

        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        results = {
            self.OUTPUT_TOTAL_GREEN_AREA: total_green_area,
            self.OUTPUT_TOTAL_GREEN_VOLUME: total_green_volume,
            self.OUTPUT_TOTAL_TREE_COUNT: tree_count,
            self.OUTPUT_HTML_REPORT: html_path
        }
        
        if grass_dest_id:
            results[self.OUTPUT_GRASS_LAYER] = grass_dest_id
        if shrub_dest_id:
            results[self.OUTPUT_SHRUBS_LAYER] = shrub_dest_id
        if hedge_dest_id:
            results[self.OUTPUT_HEDGES_LAYER] = hedge_dest_id
        if tree_dest_id:
            results[self.OUTPUT_TREES_LAYER] = tree_dest_id

        return results