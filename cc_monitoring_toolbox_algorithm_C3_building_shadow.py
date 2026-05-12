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

class CCMonitoringToolboxAlgorithmBuildingShadow(QgsProcessingAlgorithm):
    
    INPUT = 'INPUT'
    HEIGHT_FIELD = 'HEIGHT_FIELD'
    AZIMUTH = 'AZIMUTH'
    ALTITUDE = 'ALTITUDE'
    OUTPUT = 'OUTPUT'

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return CCMonitoringToolboxAlgorithmBuildingShadow()

    def name(self):
        return 'buildingshadows'

    def displayName(self):
        return self.tr('Building Shadow Generator')

    def group(self):
        return self.tr('Cooling')

    def groupId(self):
        return 'Cooling'

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT, 'Building layer', [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterField(self.HEIGHT_FIELD, 'Building height field (m)', parentLayerParameterName=self.INPUT))
        self.addParameter(QgsProcessingParameterNumber(self.AZIMUTH, 'Azimuth angle (0-360°)', type=QgsProcessingParameterNumber.Double, defaultValue=197.21))
        self.addParameter(QgsProcessingParameterNumber(self.ALTITUDE, 'Altitude angle (0-90°)', type=QgsProcessingParameterNumber.Double, defaultValue=59.06))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, 'Building shadows'))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        height_field = self.parameterAsString(parameters, self.HEIGHT_FIELD, context)
        azimuth = self.parameterAsDouble(parameters, self.AZIMUTH, context)
        altitude = self.parameterAsDouble(parameters, self.ALTITUDE, context)

        (sink, self.dest_id) = self.parameterAsSink(parameters, self.OUTPUT, context, source.fields(), QgsWkbTypes.Polygon, source.sourceCrs())

        shadow_factor = 1.0 / math.tan(math.radians(altitude)) if altitude < 90 else 0
        azi_rad = math.radians(azimuth)

        features = source.getFeatures()
        for feature in features:
            if feedback.isCanceled(): break
            
            geom = feature.geometry()
            if geom.isEmpty(): continue

            try:
                building_h = float(feature[height_field])
            except (ValueError, TypeError, KeyError):
                building_h = 0.0

            max_dist = building_h * shadow_factor
            
            dx = math.sin(azi_rad) * max_dist * -1
            dy = math.cos(azi_rad) * max_dist * -1
            
            # Effiziente Schatten-Logik: Ursprung mit verschobener Kopie vereinen
            moved_geom = QgsGeometry(geom)
            moved_geom.translate(dx, dy)
            
            # Erzeugt eine Fläche zwischen dem Gebäude und seinem Schattenwurf
            shadow_geom = geom.combine(moved_geom).convexHull()

            new_feat = QgsFeature(feature)
            new_feat.setGeometry(shadow_geom)
            sink.addFeature(new_feat, QgsFeatureSink.FastInsert)

        return {self.OUTPUT: self.dest_id}

    def postProcessAlgorithm(self, context, feedback):
        layer = QgsProcessingUtils.mapLayerFromString(self.dest_id, context)
        if layer:
            symbol = QgsFillSymbol.createSimple({'color': '#1b1b1b', 'outline_style': 'no'})
            layer.setRenderer(QgsSingleSymbolRenderer(symbol))
            layer.setOpacity(0.7)
            layer.triggerRepaint()
        return {self.OUTPUT: self.dest_id}