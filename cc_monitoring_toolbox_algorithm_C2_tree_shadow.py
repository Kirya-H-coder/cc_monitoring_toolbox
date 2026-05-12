# -*- coding: utf-8 -*-

from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsProcessingParameterFeatureSink,
    QgsFeature,
    QgsFeatureSink,
    QgsGeometry,
    QgsProcessingUtils,
    QgsFillSymbol,
    QgsSingleSymbolRenderer,
    QgsWkbTypes
)
import math

class CCMonitoringToolboxAlgorithmTreeShadow(QgsProcessingAlgorithm):
    
    INPUT = 'INPUT'
    HEIGHT_FIELD = 'HEIGHT_FIELD'
    STEM_HEIGHT_FIELD = 'STEM_HEIGHT_FIELD'
    AZIMUTH = 'AZIMUTH'
    ALTITUDE = 'ALTITUDE'
    OUTPUT = 'OUTPUT'

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return CCMonitoringToolboxAlgorithmTreeShadow()

    def name(self):
        # WICHTIG: Keine Leerzeichen im technischen Namen!
        return 'treeshadowgenerator'

    def displayName(self):
        # Hier sind Leerzeichen erlaubt
        return self.tr('Tree Shadow Generator')

    def group(self):
        return self.tr('Cooling')

    def groupId(self):
        return 'Cooling'

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT, 'Tree layer (Polygons)', [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterField(self.HEIGHT_FIELD, 'Field of tree height (m)', parentLayerParameterName=self.INPUT))
        self.addParameter(QgsProcessingParameterField(self.STEM_HEIGHT_FIELD, 'Field of stem height (m)', parentLayerParameterName=self.INPUT))
        self.addParameter(QgsProcessingParameterNumber(self.AZIMUTH, 'Azimuth angle (0-360°)', type=QgsProcessingParameterNumber.Double, defaultValue=197.21))
        self.addParameter(QgsProcessingParameterNumber(self.ALTITUDE, 'Altitude angle (0-90°)', type=QgsProcessingParameterNumber.Double, defaultValue=59.06))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, 'Tree shadow layer'))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        height_field = self.parameterAsString(parameters, self.HEIGHT_FIELD, context)
        stem_height_field = self.parameterAsString(parameters, self.STEM_HEIGHT_FIELD, context)
        azimuth = self.parameterAsDouble(parameters, self.AZIMUTH, context)
        altitude = self.parameterAsDouble(parameters, self.ALTITUDE, context)

        (sink, self.dest_id) = self.parameterAsSink(parameters, self.OUTPUT, context, source.fields(), QgsWkbTypes.Polygon, source.sourceCrs())

        if altitude >= 90:
            shadow_factor = 0
        else:
            shadow_factor = 1.0 / math.tan(math.radians(altitude))
        
        azi_rad = math.radians(azimuth)

        features = source.getFeatures()
        for feature in features:
            if feedback.isCanceled(): break
            
            geom = feature.geometry()
            if geom.isEmpty(): continue

            try:
                h_tree = float(feature[height_field]) if feature[height_field] is not None else 0.0
                h_stem = float(feature[stem_height_field]) if feature[stem_height_field] is not None else 0.0
            except (ValueError, TypeError, KeyError):
                h_tree = 0.0; h_stem = 0.0

            dist_start = h_stem * shadow_factor
            dist_ende = h_tree * shadow_factor

            dx_start = math.sin(azi_rad) * dist_start * -1
            dy_start = math.cos(azi_rad) * dist_start * -1
            dx_ende = math.sin(azi_rad) * dist_ende * -1
            dy_ende = math.cos(azi_rad) * dist_ende * -1

            g_start = QgsGeometry(geom)
            g_start.translate(dx_start, dy_start)

            g_ende = QgsGeometry(geom)
            g_ende.translate(dx_ende, dy_ende)

            # Schattengeometrie über Convex Hull der kombinierten Verschiebungen
            shadow_geom = g_start.combine(g_ende).convexHull()

            new_feature = QgsFeature(feature)
            new_feature.setGeometry(shadow_geom)
            sink.addFeature(new_feature, QgsFeatureSink.FastInsert)

        return {self.OUTPUT: self.dest_id}

    def postProcessAlgorithm(self, context, feedback):
        layer = QgsProcessingUtils.mapLayerFromString(self.dest_id, context)
        if layer:
            symbol = QgsFillSymbol.createSimple({'color': '#1b1b1b', 'outline_style': 'no'})
            layer.setRenderer(QgsSingleSymbolRenderer(symbol))
            layer.setOpacity(0.7)
            layer.triggerRepaint()
        return {self.OUTPUT: self.dest_id}