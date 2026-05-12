# -*- coding: utf-8 -*-

from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterDestination,
    QgsRasterLayer,
    QgsRasterBandStats,
    QgsStyle,
    QgsRasterShader,
    QgsColorRampShader,
    QgsSingleBandPseudoColorRenderer,
    QgsVectorLayer,
    QgsField,
    QgsFeature,
    QgsProject
)
import processing

class CCMonitoringToolboxAlgorithmPET(QgsProcessingAlgorithm):

    INPUT_RASTER = "INPUT_RASTER"
    INPUT_MASK = "INPUT_MASK"
    USE_CUSTOM_RANGE = "USE_CUSTOM_RANGE"
    MIN_VALUE = "MIN_VALUE"
    MAX_VALUE = "MAX_VALUE"
    OUTPUT = "OUTPUT"

    def tr(self, string):
        return QCoreApplication.translate("Processing", string)

    def createInstance(self):
        return CCMonitoringToolboxAlgorithmPET()

    def name(self):
        return "pet_project_site"

    def displayName(self):
        return "PET Project Site"

    def group(self):
        return "Cooling"

    def groupId(self):
        return "Cooling"

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(self.INPUT_RASTER, "PET Raster (TIFF)"))
        self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT_MASK, "Project Site Polygon", [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterBoolean(self.USE_CUSTOM_RANGE, "Use custom min/max values", defaultValue=False))
        self.addParameter(QgsProcessingParameterNumber(self.MIN_VALUE, "Minimum value", type=QgsProcessingParameterNumber.Double, defaultValue=0, optional=True))
        self.addParameter(QgsProcessingParameterNumber(self.MAX_VALUE, "Maximum value", type=QgsProcessingParameterNumber.Double, defaultValue=50, optional=True))
        self.addParameter(QgsProcessingParameterRasterDestination(self.OUTPUT, "PET project site"))

    def processAlgorithm(self, parameters, context, feedback):
        raster = self.parameterAsRasterLayer(parameters, self.INPUT_RASTER, context)
        mask = self.parameterAsVectorLayer(parameters, self.INPUT_MASK, context)
        output = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)

        feedback.pushInfo("Clipping raster...")

        result = processing.run(
            "gdal:cliprasterbymasklayer",
            {
                "INPUT": raster,
                "MASK": mask,
                "CROP_TO_CUTLINE": True,
                "KEEP_RESOLUTION": True,
                "NODATA": -9999,
                "OUTPUT": output
            },
            context=context,
            feedback=feedback
        )

        self.output_path = result["OUTPUT"]
        self.custom_min = self.parameterAsDouble(parameters, self.MIN_VALUE, context) if parameters[self.USE_CUSTOM_RANGE] else None
        self.custom_max = self.parameterAsDouble(parameters, self.MAX_VALUE, context) if parameters[self.USE_CUSTOM_RANGE] else None

        return {"OUTPUT": self.output_path}

    def postProcessAlgorithm(self, context, feedback):
        layer = QgsProject.instance().mapLayersByName("PET project site")
        if not layer:
            layer = QgsRasterLayer(self.output_path, "PET project site")
            QgsProject.instance().addMapLayer(layer)
        else:
            layer = layer[0]

        if not layer.isValid():
            return {"OUTPUT": self.output_path}

        provider = layer.dataProvider()
        stats = provider.bandStatistics(1, QgsRasterBandStats.All)
        
        min_val = self.custom_min if self.custom_min is not None else stats.minimumValue
        max_val = self.custom_max if self.custom_max is not None else stats.maximumValue

        shader = QgsRasterShader()
        color_shader = QgsColorRampShader()
        color_shader.setColorRampType(QgsColorRampShader.Interpolated)

        style = QgsStyle.defaultStyle()
        ramp = style.colorRamp("Plasma") 
        if ramp:
            ramp.invert()
            items = []
            steps = 10 
            for i in range(steps + 1):
                val = min_val + (max_val - min_val) * (i / steps)
                color = ramp.color(i / steps)
                items.append(QgsColorRampShader.ColorRampItem(val, color, f"{val:.1f} °C"))
            color_shader.setColorRampItemList(items)

        shader.setRasterShaderFunction(color_shader)
        renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader)
        layer.setRenderer(renderer)

        layer.triggerRepaint()
        layer.emitStyleChanged()

        self.create_stats_layer(stats.minimumValue, stats.maximumValue, stats.mean)

        return {"OUTPUT": self.output_path}

    def create_stats_layer(self, v_min, v_max, v_mean):
        stats_layer = QgsVectorLayer("None?field=min:double&field=max:double&field=mean:double", 
                                    "PET Statistik", "memory")
        prov = stats_layer.dataProvider()
        feat = QgsFeature()
        feat.setAttributes([float(v_min), float(v_max), float(v_mean)])
        prov.addFeature(feat)
        QgsProject.instance().addMapLayer(stats_layer)