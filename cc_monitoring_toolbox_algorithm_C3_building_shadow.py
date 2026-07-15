# -*- coding: utf-8 -*-

"""
/***************************************************************************
 CCMonitoringToolbox - Building Shadow Generator (Balanced Version)
 ***************************************************************************/
"""

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
    QgsGeometryCollection,
    QgsProcessingUtils,
    QgsFillSymbol,
    QgsSingleSymbolRenderer
)
import math

class CCMonitoringToolboxAlgorithmBuildingShadow(QgsProcessingAlgorithm):
    # These constants are like internal labels for our inputs/outputs
    INPUT = 'INPUT'
    HEIGHT_FIELD = 'HEIGHT_FIELD'
    AZIMUTH = 'AZIMUTH'
    ALTITUDE = 'ALTITUDE'
    OUTPUT = 'OUTPUT'

    def initAlgorithm(self, config=None):
        """
        STEP 1: DEFINE THE USER INTERFACE
        Setting up the boxes and menus the user sees in QGIS.
        """
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT, 'Building layer', [QgsProcessing.TypeVectorPolygon]
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.HEIGHT_FIELD, 'Building height field (m)', 
                parentLayerParameterName=self.INPUT
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.AZIMUTH, 'Azimuth angle (0-360°)', 
                type=QgsProcessingParameterNumber.Double, defaultValue=268.5
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.ALTITUDE, 'Altitude angle (0-90°)', 
                type=QgsProcessingParameterNumber.Double, defaultValue=30.0
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(self.OUTPUT, 'Building shadows')
        )

    def processAlgorithm(self, parameters, context, feedback):
        """
        STEP 2: THE LOGIC ENGINE
        This is where we "pull" the building shape to create a shadow.
        """
        source = self.parameterAsSource(parameters, self.INPUT, context)
        height_field = self.parameterAsString(parameters, self.HEIGHT_FIELD, context)
        azimuth = self.parameterAsDouble(parameters, self.AZIMUTH, context)
        altitude = self.parameterAsDouble(parameters, self.ALTITUDE, context)

        # Prepare the container (Sink) for the new shadow features
        (sink, self.dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context, source.fields(), 
            source.wkbType(), source.sourceCrs()
        )

        # Basic Math: Calculate how long the shadow is relative to height (Shadow Factor)
        shadow_factor = 1.0 / math.tan(math.radians(altitude)) if altitude < 90 else 0
        azi_rad = math.radians(azimuth)

        # Process every building one by one
        features = source.getFeatures()
        for feature in features:
            if feedback.isCanceled():
                break
            
            geom = feature.geometry()
            if geom.isEmpty():
                continue

            # Read the building's height from the attribute table
            try:
                building_h = float(feature[height_field])
            except (ValueError, TypeError, KeyError):
                building_h = 0.0

            # This is the total distance the shadow tip travels from the building base
            max_dist = building_h * shadow_factor
            
            # We create a 'Collection' to bundle many copies of the building together
            shadow_parts = QgsGeometryCollection()
            
            # --- THE "STEPPING" METHOD ---
            # Instead of just moving the shape once, we move it in small steps.
            # This fills the "volume" of the shadow so complex buildings don't have holes.
            # 0.25m is a good balance: smooth enough but not too slow for the computer.
            current_step = 0.0
            step_size = 0.25 
            
            while current_step <= (max_dist + 0.001):
                # Calculate the X and Y shift based on the current distance and sun direction
                dx = math.sin(azi_rad) * current_step * -1
                dy = math.cos(azi_rad) * current_step * -1
                
                # Make a copy and move it
                moved_part = QgsGeometry(geom)
                moved_part.translate(dx, dy)
                
                # Add this slice to our collection
                if moved_part.get():
                    shadow_parts.addGeometry(moved_part.get().clone())
                
                # Move to the next slice position
                current_step += step_size

            # --- DISSOLVE EVERYTHING ---
            # We have a pile of building slices. Now we merge them into one solid polygon.
            # buffer(0) is a "magic trick" in GIS to dissolve everything and fix geometry errors.
            if not shadow_parts.isEmpty():
                full_collection_geom = QgsGeometry(shadow_parts)
                final_shadow = full_collection_geom.buffer(0.0, 5)
            else:
                final_shadow = QgsGeometry()

            # Save the final shadow shape
            if not final_shadow.isEmpty():
                new_feat = QgsFeature(feature)
                new_feat.setGeometry(final_shadow)
                sink.addFeature(new_feat, QgsFeatureSink.FastInsert)

        return {self.OUTPUT: self.dest_id}

    def postProcessAlgorithm(self, context, feedback):
        """
        STEP 3: AUTOMATIC STYLING
        Making the result look like a shadow (dark and semi-transparent).
        """
        layer = QgsProcessingUtils.mapLayerFromString(self.dest_id, context)
        if layer:
            # Dark grey color, no outline
            symbol = QgsFillSymbol.createSimple({'color': '#222222', 'outline_style': 'no'})
            layer.setOpacity(0.6) # Transparency
            layer.setRenderer(QgsSingleSymbolRenderer(symbol))
            layer.triggerRepaint()
        return {self.OUTPUT: self.dest_id}

    # REQUIRED BOILERPLATE (Metadata)
    def name(self): return 'cc_monitoring_toolbox_algorithm_building_shadow'
    def displayName(self): return self.tr('Building Shadow Generator')
    def group(self): return self.tr('Cooling')
    def groupId(self): return 'Cooling'
    def tr(self, string): return QCoreApplication.translate('Processing', string)
    def createInstance(self): return CCMonitoringToolboxAlgorithmBuildingShadow()
