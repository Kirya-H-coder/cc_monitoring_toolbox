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
from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingOutputHtml,
    QgsField,
    QgsFields,
    QgsFeature,
    QgsFeatureSink,
    QgsGeometry,
    QgsWkbTypes
)


class CCMonitoringToolboxAlgorithmGreenQuantity(QgsProcessingAlgorithm):
    """
    QGIS Processing Algorithm to evaluate Green Space Quantity,
    including 2D areas (Grass, Shrubs) and 3D Tree Metrics.
    Calculates individual tree volume per feature into output layer attribute table.
    """

    # --- PARAMETER IDENTIFIERS ---
    PROJECT_BORDER = 'PROJECT_BORDER'
    
    GRASS_LAYER = 'GRASS_LAYER'
    SHRUBS_LAYER = 'SHRUBS_LAYER'
    
    TREES_LAYER = 'TREES_LAYER'
    FIELD_TREE_HEIGHT = 'FIELD_TREE_HEIGHT'
    FIELD_TREE_CROWN_DIAMETER = 'FIELD_TREE_CROWN_DIAMETER'
    TREE_SHAPE_MODEL = 'TREE_SHAPE_MODEL'

    OUTPUT_TREES_LAYER = 'OUTPUT_TREES_LAYER'
    OUTPUT_HTML_REPORT = 'OUTPUT_HTML_REPORT'

    # Shape models for volume estimation
    SHAPE_MODELS = [
        'Cone (V = 1/12 * PI * d² * h)',
        'Paraboloid (V = 1/8 * PI * d² * h)',
        'Ellipsoid / Sphere (V = 1/6 * PI * d² * h)',
        'Cylinder (V = 1/4 * PI * d² * h)'
    ]

    def tr(self, string):
        """Helper function for string translation support."""
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        """Creates a new instance of the algorithm."""
        return CCMonitoringToolboxAlgorithmQuantity()

    def name(self):
        """Unique technical algorithm identifier."""
        return 'greenquantityanalyzer'

    def displayName(self):
        """Human-readable name displayed in the Processing Toolbox."""
        return self.tr('Green Space Quantity & Tree Metrics')

    def group(self):
        """Parent category folder name in the Processing Toolbox UI."""
        return self.tr('Greening')

    def groupId(self):
        """Parent category technical identifier."""
        return 'greening'

    def initAlgorithm(self, config=None):
        """
        Defines input parameters including Project Border, 2D Green Spaces,
        Tree parameters and geometric shape model.
        """
        # 1. Project Border Area (Polygon)
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.PROJECT_BORDER,
            self.tr('Project Border Area (Polygon)'),
            [QgsProcessing.TypeVectorPolygon]
        ))

        # 2. 2D Green Layers (Grass / Shrubs)
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.GRASS_LAYER,
            self.tr('Grass / Lawn Layer (Polygons)'),
            [QgsProcessing.TypeVectorPolygon],
            optional=True
        ))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.SHRUBS_LAYER,
            self.tr('Shrub Layer (Polygons)'),
            [QgsProcessing.TypeVectorPolygon],
            optional=True
        ))

        # 3. Tree Layer & Geometry Input Fields
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.TREES_LAYER,
            self.tr('Tree Layer (Points or Polygons)'),
            [QgsProcessing.TypeVectorPoint, QgsProcessing.TypeVectorPolygon],
            optional=True
        ))
        self.addParameter(QgsProcessingParameterField(
            self.FIELD_TREE_HEIGHT,
            self.tr('Tree Height Field (m)'),
            parentLayerParameterName=self.TREES_LAYER,
            type=QgsProcessingParameterField.Numeric,
            optional=True
        ))
        self.addParameter(QgsProcessingParameterField(
            self.FIELD_TREE_CROWN_DIAMETER,
            self.tr('Crown Diameter Field (m)'),
            parentLayerParameterName=self.TREES_LAYER,
            type=QgsProcessingParameterField.Numeric,
            optional=True
        ))
        self.addParameter(QgsProcessingParameterEnum(
            self.TREE_SHAPE_MODEL,
            self.tr('Crown Geometric Shape Model'),
            options=self.SHAPE_MODELS,
            defaultValue=0  # Default: Cone
        ))

        # Output Evaluated Trees Vector Layer
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT_TREES_LAYER,
            self.tr('Evaluated Trees with Volume Attribute'),
            type=QgsProcessing.TypeVectorAnyGeometry,
            optional=True
        ))

        # HTML Report Output
        self.addOutput(QgsProcessingOutputHtml(
            self.OUTPUT_HTML_REPORT, 
            self.tr('Green Quantity Summary Report')
        ))

    def _calculate_volume(self, diameter, height, shape_idx):
        """
        Calculates individual crown volume based on chosen geometric shape.
        """
        if diameter <= 0 or height <= 0:
            return 0.0

        if shape_idx == 0:    # Cone: V = (1/12) * PI * d^2 * h
            return (1.0 / 12.0) * math.pi * (diameter ** 2) * height
        elif shape_idx == 1:  # Paraboloid: V = (1/8) * PI * d^2 * h
            return (1.0 / 8.0) * math.pi * (diameter ** 2) * height
        elif shape_idx == 2:  # Ellipsoid/Sphere: V = (1/6) * PI * d^2 * h
            return (1.0 / 6.0) * math.pi * (diameter ** 2) * height
        elif shape_idx == 3:  # Cylinder: V = (1/4) * PI * d^2 * h
            return (1.0 / 4.0) * math.pi * (diameter ** 2) * height
        return 0.0

    def processAlgorithm(self, parameters, context, feedback):
        """
        Processes 2D green coverage and calculates 3D tree volume per individual tree feature.
        """
        border_source = self.parameterAsSource(parameters, self.PROJECT_BORDER, context)
        grass_source = self.parameterAsSource(parameters, self.GRASS_LAYER, context)
        shrub_source = self.parameterAsSource(parameters, self.SHRUBS_LAYER, context)
        tree_source = self.parameterAsSource(parameters, self.TREES_LAYER, context)

        f_tree_hgt = self.parameterAsString(parameters, self.FIELD_TREE_HEIGHT, context)
        f_crown_dia = self.parameterAsString(parameters, self.FIELD_TREE_CROWN_DIAMETER, context)
        shape_idx = self.parameterAsEnum(parameters, self.TREE_SHAPE_MODEL, context)

        # ---------------------------------------------------------------------
        # 1. Combine Project Area Geometries
        # ---------------------------------------------------------------------
        project_geom = QgsGeometry()
        total_project_area = 0.0

        for feat in border_source.getFeatures():
            geom = feat.geometry()
            if geom and not geom.isEmpty():
                project_geom = project_geom.combine(geom) if not project_geom.isEmpty() else QgsGeometry(geom)

        if not project_geom.isEmpty():
            total_project_area = project_geom.area()

        # ---------------------------------------------------------------------
        # 2. Calculate 2D Green Coverage within Project Area
        # ---------------------------------------------------------------------
        def calc_intersected_area(source):
            if not source or project_geom.isEmpty():
                return 0.0
            total_area = 0.0
            for feat in source.getFeatures():
                geom = feat.geometry()
                if geom and geom.intersects(project_geom):
                    intersection = geom.intersection(project_geom)
                    if not intersection.isEmpty():
                        total_area += intersection.area()
            return total_area

        grass_area = calc_intersected_area(grass_source)
        shrub_area = calc_intersected_area(shrub_source)
        total_2d_green = grass_area + shrub_area

        # ---------------------------------------------------------------------
        # 3. Process Individual Trees: Write Volume to Sink & Compute Statistics
        # ---------------------------------------------------------------------
        tree_count = 0
        tree_volumes = []
        tree_heights = []

        # Prepare Sink Fields if tree layer is supplied
        sink = None
        dest_id = None

        if tree_source and not project_geom.isEmpty():
            output_fields = QgsFields(tree_source.fields())
            output_fields.append(QgsField("Tree_Vol_m3", QVariant.Double))
            output_fields.append(QgsField("Crown_Shape", QVariant.String))

            (sink, dest_id) = self.parameterAsSink(
                parameters,
                self.OUTPUT_TREES_LAYER,
                context,
                output_fields,
                tree_source.wkbType(),
                tree_source.sourceCrs()
            )

            feedback.pushInfo(self.tr("Calculating individual tree volume per feature..."))

            for feat in tree_source.getFeatures():
                if feedback.isCanceled():
                    break

                geom = feat.geometry()
                if geom and geom.intersects(project_geom):
                    tree_count += 1

                    height = 0.0
                    diameter = 0.0

                    if f_tree_hgt and feat[f_tree_hgt] is not None:
                        try:
                            height = float(feat[f_tree_hgt])
                            tree_heights.append(height)
                        except (ValueError, TypeError):
                            pass

                    if f_crown_dia and feat[f_crown_dia] is not None:
                        try:
                            diameter = float(feat[f_crown_dia])
                        except (ValueError, TypeError):
                            pass

                    # Individual volume calculation using selected formula
                    indiv_volume = self._calculate_volume(diameter, height, shape_idx)
                    tree_volumes.append(indiv_volume)

                    # Export updated feature to output sink
                    if sink:
                        out_feat = QgsFeature(output_fields)
                        out_feat.setGeometry(geom)
                        attrs = feat.attributes()
                        attrs.append(round(indiv_volume, 2))
                        attrs.append(self.SHAPE_MODELS[shape_idx].split(' ')[0])
                        out_feat.setAttributes(attrs)
                        sink.addFeature(out_feat, QgsFeatureSink.FastInsert)

        # Statistics computation over individual feature volumes
        total_tree_volume = sum(tree_volumes) if tree_volumes else 0.0
        avg_tree_volume = (total_tree_volume / len(tree_volumes)) if tree_volumes else 0.0
        min_tree_volume = min(tree_volumes) if tree_volumes else 0.0
        max_tree_volume = max(tree_volumes) if tree_volumes else 0.0

        min_tree_height = min(tree_heights) if tree_heights else 0.0
        max_tree_height = max(tree_heights) if tree_heights else 0.0
        avg_tree_height = (sum(tree_heights) / len(tree_heights)) if tree_heights else 0.0

        # Percentages
        grass_pct = (grass_area / total_project_area * 100.0) if total_project_area > 0 else 0.0
        shrub_pct = (shrub_area / total_project_area * 100.0) if total_project_area > 0 else 0.0
        total_2d_pct = (total_2d_green / total_project_area * 100.0) if total_project_area > 0 else 0.0

        # ---------------------------------------------------------------------
        # 4. Generate HTML Summary Report
        # ---------------------------------------------------------------------
        shape_name = self.SHAPE_MODELS[shape_idx]

        html_report = f"""
        <h2>Green Space Quantity & Tree Analysis Report</h2>
        <p>Evaluation of 2D green coverage and individual 3D tree volumes within the Project Area.</p>
        
        <h3>1. Project Site Summary</h3>
        <table border="1" cellspacing="0" cellpadding="6" style="border-collapse: collapse; font-family: sans-serif; width: 100%; margin-bottom: 20px;">
            <tr style="background-color: #f2f2f2; text-align: left;">
                <th>Parameter</th>
                <th>Value</th>
            </tr>
            <tr>
                <td><b>Total Project Boundary Area</b></td>
                <td>{total_project_area:.2f} m²</td>
            </tr>
            <tr>
                <td>Grass / Lawn Area</td>
                <td>{grass_area:.2f} m² ({grass_pct:.1f}%)</td>
            </tr>
            <tr>
                <td>Shrub Area</td>
                <td>{shrub_area:.2f} m² ({shrub_pct:.1f}%)</td>
            </tr>
            <tr style="background-color: #f0fdf4; font-weight: bold;">
                <td>Total 2D Green Coverage</td>
                <td>{total_2d_green:.2f} m² ({total_2d_pct:.1f}%)</td>
            </tr>
        </table>

        <h3>2. Tree Inventory & Feature-Level Volume Summary</h3>
        <table border="1" cellspacing="0" cellpadding="6" style="border-collapse: collapse; font-family: sans-serif; width: 100%;">
            <tr style="background-color: #f2f2f2; text-align: left;">
                <th>Tree Metric</th>
                <th>Result</th>
            </tr>
            <tr>
                <td><b>Total Tree Count On-Site</b></td>
                <td><b>{tree_count} Trees</b></td>
            </tr>
            <tr>
                <td>Volume Geometry Model</td>
                <td>{shape_name}</td>
            </tr>
            <tr>
                <td><b>Average Individual Tree Volume</b></td>
                <td><b>{avg_tree_volume:.2f} m³</b></td>
            </tr>
            <tr>
                <td>Min / Max Individual Volume</td>
                <td>{min_tree_volume:.2f} m³ / {max_tree_volume:.2f} m³</td>
            </tr>
            <tr style="background-color: #f0fdf4; font-weight: bold;">
                <td>Total Combined Tree Volume</td>
                <td>{total_tree_volume:.2f} m³</td>
            </tr>
            <tr>
                <td>Minimum Tree Height</td>
                <td>{min_tree_height:.2f} m</td>
            </tr>
            <tr>
                <td>Maximum Tree Height</td>
                <td>{max_tree_height:.2f} m</td>
            </tr>
            <tr>
                <td>Average Tree Height</td>
                <td>{avg_tree_height:.2f} m</td>
            </tr>
        </table>
        """

        res = {self.OUTPUT_HTML_REPORT: html_report}
        if dest_id:
            res[self.OUTPUT_TREES_LAYER] = dest_id

        return res