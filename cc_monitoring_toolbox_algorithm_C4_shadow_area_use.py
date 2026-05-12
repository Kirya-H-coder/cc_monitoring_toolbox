# -*- coding: utf-8 -*-

from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFeatureSink,
    QgsField,
    QgsFeature,
    QgsProject,
    QgsSymbol,
    QgsRendererCategory,
    QgsCategorizedSymbolRenderer,
    QgsWkbTypes,
    QgsProcessingUtils
)
import processing

class CCMonitoringToolboxAlgorithmShadowAreaUse(QgsProcessingAlgorithm):

    SHADOWS = 'SHADOWS'
    STAY = 'STAY'
    WALKING = 'WALKING'
    TRAFFIC = 'TRAFFIC'
    OUTPUT = 'OUTPUT'

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return CCMonitoringToolboxAlgorithmShadowAreaUse()

    def name(self):
        return 'shadowusageanalysis'

    def displayName(self):
        return self.tr('Shadow & Usage Analysis')

    def group(self):
        return self.tr('Cooling')

    def groupId(self):
        return 'Cooling'

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(self.SHADOWS, 'Schattenkarte (Polygone)', [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.STAY, 'Places of Stay (Pink)', [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.WALKING, 'Walking Routes (Blau)', [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.TRAFFIC, 'Traffic/Other (Orange)', [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, 'Analyse der beschatteten Nutzungen'))

    def processAlgorithm(self, parameters, context, feedback):
        shadows = self.parameterAsVectorLayer(parameters, self.SHADOWS, context)
        
        usage_layers = [
            (self.parameterAsVectorLayer(parameters, self.STAY, context), 'Places of Stay'),
            (self.parameterAsVectorLayer(parameters, self.WALKING, context), 'Walking Routes'),
            (self.parameterAsVectorLayer(parameters, self.TRAFFIC, context), 'Traffic')
        ]

        fields = shadows.fields()
        fields.append(QgsField('usage_type', QVariant.String))
        fields.append(QgsField('area_m2', QVariant.Double))
        fields.append(QgsField('percent', QVariant.Double))

        (sink, self.dest_id) = self.parameterAsSink(parameters, self.OUTPUT, context, fields, QgsWkbTypes.MultiPolygon, shadows.sourceCrs())

        total_shadow_area = sum(f.geometry().area() for f in shadows.getFeatures())

        for layer, label in usage_layers:
            if feedback.isCanceled(): break
            if layer is None: continue

            res = processing.run("native:intersection", {
                'INPUT': shadows,
                'OVERLAY': layer,
                'OUTPUT': 'memory:'
            }, context=context, feedback=feedback)
            
            intersect_layer = res['OUTPUT']
            
            for feat in intersect_layer.getFeatures():
                new_feat = QgsFeature(feat)
                new_feat.setFields(fields)
                
                area = feat.geometry().area()
                perc = (area / total_shadow_area * 100) if total_shadow_area > 0 else 0
                
                new_feat['usage_type'] = label
                new_feat['area_m2'] = round(area, 2)
                new_feat['percent'] = round(perc, 2)
                
                sink.addFeature(new_feat)

        return {self.OUTPUT: self.dest_id}

    def postProcessAlgorithm(self, context, feedback):
        layer = QgsProcessingUtils.mapLayerFromString(self.dest_id, context)
        if not layer:
            return {self.OUTPUT: self.dest_id}

        # 1. Farbschema definieren
        color_map = {
            'Places of Stay': '#ff00ff', # Pink
            'Walking Routes': '#0000ff', # Blau
            'Traffic': '#ffa500'         # Orange
        }

        categories = []
        
        # 2. Für jeden Typ in der color_map eine Kategorie erstellen
        for usage_val, color_hex in color_map.items():
            # Standard-Symbol für Polygone holen
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            
            # Farbe und Transparenz setzen
            symbol.setColor(QColor(color_hex))
            symbol.setOpacity(0.6)
            
            # Randlinie entfernen für besseren Look
            if symbol.symbolLayerCount() > 0:
                symbol.symbolLayer(0).setStrokeStyle(0) # 0 = No Pen

            # Kategorie erstellen (Wert in Tabelle, Symbol, Anzeigename in Legende)
            category = QgsRendererCategory(usage_val, symbol, usage_val)
            categories.append(category)

        # 3. Den Categorized Renderer auf die Spalte 'usage_type' anwenden
        renderer = QgsCategorizedSymbolRenderer('usage_type', categories)
        layer.setRenderer(renderer)
        
        # 4. Refresh erzwingen
        layer.triggerRepaint()
        
        return {self.OUTPUT: self.dest_id}