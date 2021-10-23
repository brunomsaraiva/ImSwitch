import numpy as np
import time
from imswitch.imcommon.model import initLogger

from imswitch.imcontrol.model.interfaces.pymbacamera import AVCamera
 
class CameraAV:
    def __init__(self,cameraNo=None):
        super().__init__()
        self.__logger = initLogger(self, tryInheritParent=True)

        # many to be purged
        self.model = "AV Camera"
        self.shape = (0, 0)

        # camera parameters
        self.blacklevel = 100
        self.exposure_time = 0
        self.analog_gain = 0

        self.is_streaming = False

        self.GAIN_MAX = 24
        self.GAIN_MIN = 0
        self.GAIN_STEP = 1
        self.EXPOSURE_TIME_MS_MIN = 0.01
        self.EXPOSURE_TIME_MS_MAX = 4000

        self.FRAME_WIDTH = 1000
        self.FRAME_HEIGHT = 1000

        #%% starting the camera thread
        self.camera = AVCamera()
        

    def start_live(self):
        if self.camera.is_active:
            # TODO: Hacky way :/
            self.camera.stop()
            time.sleep(1)
            del self.camera
            self.camera = AVCamera()
        self.camera.start()
        self.is_streaming = True

    def stop_live(self):
        if self.is_streaming:
            self.camera.stop()
            del self.camera
        self.is_streaming = False

    def suspend_live(self):
        pass

    def prepare_live(self):
        pass

    def set_exposure_time(self,exposure_time):
        self.exposure_time = exposure_time
        self.camera.setExposureTime(self.exposure_time*1000)

    def set_analog_gain(self,analog_gain):
        self.analog_gain = analog_gain
        self.camera.setGain(self.analog_gain)
        
    def set_blacklevel(self,blacklevel):
        self.blacklevel = blacklevel
        self.camera.setBlacklevel(self.blacklevel)

    def set_pixel_format(self,format):
        #TODO: Implement
        
        if self.is_streaming == True:
            was_streaming = True
            self.stop_streaming()
        else:
            was_streaming = False
        if self.camera.PixelFormat.is_implemented() and self.camera.PixelFormat.is_writable():
            if format == 'MONO8':
                self.camera.PixelFormat.set(gx.GxPixelFormatEntry.MONO8)
            if format == 'MONO12':
                self.camera.PixelFormat.set(gx.GxPixelFormatEntry.MONO12)
            if format == 'MONO14':
                self.camera.PixelFormat.set(gx.GxPixelFormatEntry.MONO14)
            if format == 'MONO16':
                self.camera.PixelFormat.set(gx.GxPixelFormatEntry.MONO16)
            if format == 'BAYER_RG8':
                self.camera.PixelFormat.set(gx.GxPixelFormatEntry.BAYER_RG8)
            if format == 'BAYER_RG12':
                self.camera.PixelFormat.set(gx.GxPixelFormatEntry.BAYER_RG12)
        else:
            print("pixel format is not implemented or not writable")
        if was_streaming:
           self.start_streaming()
        
    def getLast(self):
        # get frame and save
        return  self.camera.last_frame_preview

    def getLastChunk(self):
        return self.camera.last_frame
       
    def setROI(self, hpos, vpos, hsize, vsize):
        hsize = max(hsize, 256)  # minimum ROI size
        vsize = max(vsize, 24)  # minimum ROI size
        pass
        # self.__logger.debug(
        #     f'{self.model}: setROI started with {hsize}x{vsize} at {hpos},{vpos}.'
        # )
        #self.camera.setROI(vpos, hpos, vsize, hsize)


    def setPropertyValue(self, property_name, property_value):
        # Check if the property exists.
        if property_name == "gain":
            self.set_analog_gain(property_value)
        elif property_name == "exposure":
            self.set_exposure_time(property_value)
        elif property_name == "blacklevel":
            self.set_blacklevel(property_value)
        else:
            self.__logger.warning(f'Property {property_name} does not exist')
            return False
        return property_value

    def getPropertyValue(self, property_name):
        # Check if the property exists.
        if property_name == "gain":
            property_value = self.camera.gain
        elif property_name == "exposure":
            property_value = self.camera.gain
        elif property_name == "blacklevel":
            property_value = self.camera.blacklevel
        elif property_name == "image_width":
            property_value = self.FRAME_WIDTH
        elif property_name == "image_height":
            property_value = self.FRAME_HEIGHT
        else:
            self.__logger.warning(f'Property {property_name} does not exist')
            return False
        return property_value

    def openPropertiesGUI(self):
        pass