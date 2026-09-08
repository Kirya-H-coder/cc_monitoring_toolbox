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
    QgsPointXY,
    QgsProcessingUtils,
    QgsFillSymbol,
    QgsSingleSymbolRenderer,
    QgsWkbTypes
)
import math

class CCMonitoringToolboxAlgorithmModuleShadow(QgsProcessingAlgorithm):
    
    INPUT = 'INPUT'
    HEIGHT_FIELD = 'HEIGHT_FIELD'
    TILT_FIELD = 'TILT_FIELD'
    ORIENTATION_FIELD = 'ORIENTATION_FIELD'
    AZIMUTH = 'AZIMUTH'
    ALTITUDE = 'ALTITUDE'
    OUTPUT = 'OUTPUT'

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return CCMonitoringToolboxAlgorithmModuleShadow()

    def name(self):
        return 'moduleshadowgenerator'

    def displayName(self):
        return self.tr('Module / Sun Sail Shadow Generator')

    def group(self):
        return self.tr('Cooling')

    def groupId(self):
        return 'Cooling'

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT, 'Module / Sun Sail layer (Polygons)', [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterField(self.HEIGHT_FIELD, 'Field of base height (m)', parentLayerParameterName=self.INPUT))
        self.addParameter(QgsProcessingParameterField(self.TILT_FIELD, 'Field of tilt angle (°)', parentLayerParameterName=self.INPUT, optional=True))
        self.addParameter(QgsProcessingParameterField(self.ORIENTATION_FIELD, 'Field of module orientation (0-360°)', parentLayerParameterName=self.INPUT, optional=True))
        self.addParameter(QgsProcessingParameterNumber(self.AZIMUTH, 'Sun Azimuth angle (0-360°)', type=QgsProcessingParameterNumber.Double, defaultValue=197.21))
        self.addParameter(QgsProcessingParameterNumber(self.ALTITUDE, 'Sun Altitude angle (0-90°)', type=QgsProcessingParameterNumber.Double, defaultValue=59.06))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, 'Module shadow layer'))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        height_field = self.parameterAsString(parameters, self.HEIGHT_FIELD, context)
        tilt_field = self.parameterAsString(parameters, self.TILT_FIELD, context)
        orientation_field = self.parameterAsString(parameters, self.ORIENTATION_FIELD, context)
        azimuth = self.parameterAsDouble(parameters, self.AZIMUTH, context)
        altitude = self.parameterAsDouble(parameters, self.ALTITUDE, context)

        (sink, self.dest_id) = self.parameterAsSink(parameters, self.OUTPUT, context, source.fields(), QgsWkbTypes.Polygon, source.sourceCrs())

        if altitude >= 90:
            shadow_factor = 0
        else:
            shadow_factor = 1.0 / math.tan(math.radians(altitude))
        
        sun_azi_rad = math.radians(azimuth)

        features = source.getFeatures()
        for feature in features:
            if feedback.isCanceled(): break
            
            geom = feature.geometry()
            if geom.isEmpty(): continue

            try:
                z_base = float(feature[height_field]) if height_field and feature[height_field] is not None else 0.0
            except (ValueError, TypeError, KeyError):
                z_base = 0.0

            try:
                tilt_deg = float(feature[tilt_field]) if tilt_field and feature[tilt_field] is not None else 0.0
            except (ValueError, TypeError, KeyError):
                tilt_deg = 0.0

            try:
                module_orient_deg = float(feature[orientation_field]) if orientation_field and feature[orientation_field] is not None else 0.0
            except (ValueError, TypeError, KeyError):
                module_orient_deg = 0.0

            tilt_rad = math.radians(tilt_deg)
            orient_rad = math.radians(module_orient_deg)
            
            dir_x = math.sin(orient_rad)
            dir_y = math.cos(orient_rad)

            centroid = geom.centroid().asPoint()
            cx, cy = centroid.x(), centroid.y()

            shadow_polygons = []
            multi_polygons = geom.asMultiPolygon() if geom.isMultipart() else [geom.asPolygon()]

            for poly in multi_polygons:
                shadow_poly = []
                for ring in poly:
                    
                    # Tiefsten Punkt (Unterkante) auf der Karte finden
                    local_proj = []
                    for pt in ring:
                        rel_x = pt.x() - cx
                        rel_y = pt.y() - cy
                        proj = rel_x * dir_x + rel_y * dir_y
                        local_proj.append(proj)
                    
                    max_proj = max(local_proj) if local_proj else 0.0

                    shadow_ring = []
                    for pt in ring:
                        x_2d, y_2d = pt.x(), pt.y()
                        
                        rel_x = x_2d - cx
                        rel_y = y_2d - cy
                        proj = rel_x * dir_x + rel_y * dir_y
                        
                        # Abstand im 2D-Grundriss zur Unterkante
                        dist_ground = max_proj - proj
                        
                        # Höhe Z = Basishöhe + (Grundrissabstand * tan(tilt))
                        # Da das Polygon bereits im Grundriss gezeichnet ist, liefert tan() die exakte 3D-Höhe!
                        z_point = z_base + (dist_ground * math.tan(tilt_rad))
                        
                        # Schattenwurf berechnen
                        dist_shadow = z_point * shadow_factor
                        dx = math.sin(sun_azi_rad) * dist_shadow * -1
                        dy = math.cos(sun_azi_rad) * dist_shadow * -1
                        
                        shadow_ring.append(QgsPointXY(x_2d + dx, y_2d + dy))
                        
                    shadow_poly.append(shadow_ring)
                shadow_polygons.append(shadow_poly)

            if geom.isMultipart():
                shadow_geom = QgsGeometry.fromMultiPolygonXY(shadow_polygons)
            else:
                shadow_geom = QgsGeometry.fromPolygonXY(shadow_polygons[0])

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