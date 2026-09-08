# -*- coding: utf-8 -*-

from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterString,
    QgsProcessingParameterFeatureSink,
    QgsVectorLayer,
    QgsField,
    QgsFeature,
    QgsProject,
    QgsSymbol,
    QgsRendererCategory,
    QgsCategorizedSymbolRenderer,
    QgsFeatureRequest,
    QgsFeatureSink,
    edit
)
import processing

class CCMonitoringToolboxAlgorithmInfiltrationPotential(QgsProcessingAlgorithm):

    INPUT_POINTS = "INPUT_POINTS"
    SOIL_FIELD = "SOIL_FIELD"
    MAPPING_STRING = "MAPPING_STRING"
    OUTPUT = "OUTPUT"

    def tr(self, string):
        return QCoreApplication.translate("Processing", string)

    def createInstance(self):
        return CCMonitoringToolboxAlgorithmInfiltrationPotential()

    def name(self):
        return "infiltration_potential"

    def displayName(self):
        return self.tr("Infiltration Potential Map")

    def group(self):
        return self.tr("Water")

    def groupId(self):
        return "Water"

    def initAlgorithm(self, config=None):
        # Point layer with borehole data
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.INPUT_POINTS, 
            self.tr("Borehole Data (Point Layer)"), 
            [QgsProcessing.TypeVectorPoint]
        ))

        # Field selection for soil type
        self.addParameter(QgsProcessingParameterField(
            self.SOIL_FIELD, 
            self.tr("Soil Description Column (Text)"), 
            parentLayerParameterName=self.INPUT_POINTS
        ))

        # Flexible mapping as string
        self.addParameter(QgsProcessingParameterString(
            self.MAPPING_STRING, 
            self.tr("Soil Mapping (Keyword:Score, ...)"), 
            defaultValue="sand:3,silt:2,loam:2,clay:1"
        ))

        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, 
            self.tr("Infiltration Potential Polygons")
        ))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsVectorLayer(parameters, self.INPUT_POINTS, context)
        # Fix for AttributeError from image_38f07f.png: Use parameterAsString instead
        soil_field = self.parameterAsString(parameters, self.SOIL_FIELD, context)
        mapping_raw = self.parameterAsString(parameters, self.MAPPING_STRING, context)

        # 1. Parsing the Mapping
        mapping = {}
        try:
            for item in mapping_raw.split(','):
                if ':' in item:
                    key, val = item.split(':')
                    mapping[key.strip().lower()] = int(val.strip())
        except Exception as e:
            feedback.reportError(f"Mapping format error: {str(e)}. Please use 'Keyword:Score, Keyword:Score'.")

        # 2. Create temporary layer with Score field
        feedback.pushInfo("Classifying soil points based on mapping...")
        
        # Create a memory layer copy to hold the calculated scores
        temp_points = source.materialize(QgsFeatureRequest())
        temp_points.dataProvider().addAttributes([QgsField("score", QVariant.Int)])
        temp_points.updateFields()
        
        score_idx = temp_points.fields().indexOf("score")
        
        with edit(temp_points):
            for feat in temp_points.getFeatures():
                soil_text = str(feat[soil_field]).lower()
                score = 0  # Default: No match
                for key, value in mapping.items():
                    if key in soil_text:
                        score = value
                        break
                temp_points.changeAttributeValue(feat.id(), score_idx, score)

        # 3. Generate Voronoi Polygons (Spatial Interpolation)
        feedback.pushInfo("Interpolating potential areas (Voronoi)...")
        voronoi_result = processing.run(
            "qgis:voronoipolygons",  # Hier war der Fehler (das '概' Zeichen muss weg)
            {
                'INPUT': temp_points,
                'BUFFER': 20,
                'OUTPUT': 'TEMPORARY_OUTPUT'
            },
            context=context,
            feedback=feedback
        )

        voronoi_layer = voronoi_result['OUTPUT']

        # 4. Write to destination sink
        (sink, dest_id) = self.parameterAsSink(
            parameters, 
            self.OUTPUT, 
            context, 
            voronoi_layer.fields(), 
            voronoi_layer.wkbType(), 
            voronoi_layer.sourceCrs()
        )
        
        for feat in voronoi_layer.getFeatures():
            sink.addFeature(feat, QgsFeatureSink.FastInsert)

        self.output_id = dest_id
        return {self.OUTPUT: self.output_id}

    def postProcessAlgorithm(self, context, feedback):
        """Automatic styling of the resulting map"""
        layer = QgsProject.instance().mapLayer(self.output_id)
        if not layer:
            return {self.OUTPUT: self.output_id}

        # Setup categorized renderer (1=Low, 2=Medium, 3=High)
        props = {
            '1': ('#e74c3c', 'Low Potential'),
            '2': ('#f1c40f', 'Medium Potential'),
            '3': ('#2ecc71', 'High Potential'),
            '0': ('#95a5a6', 'No Data / Unknown')
        }

        categories = []
        for val, (color, label) in props.items():
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            symbol.setColor(QColor(color))
            symbol.setOpacity(0.7)
            category = QgsRendererCategory(val, symbol, self.tr(label))
            categories.append(category)

        renderer = QgsCategorizedSymbolRenderer("score", categories)
        layer.setRenderer(renderer)
        layer.triggerRepaint()

        return {self.OUTPUT: self.output_id}