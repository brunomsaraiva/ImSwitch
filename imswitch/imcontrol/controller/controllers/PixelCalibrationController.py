import json
import os

import numpy as np
import time
import tifffile as tif
import threading
from datetime import datetime
import cv2

from imswitch.imcommon.model import dirtools, initLogger, APIExport
from ..basecontrollers import ImConWidgetController
from imswitch.imcommon.framework import Signal, Thread, Worker, Mutex, Timer
import time

from ..basecontrollers import LiveUpdatedController

#import NanoImagingPack as nip

class PixelCalibrationController(LiveUpdatedController):
    """Linked to PixelCalibrationWidget."""

    sigImageReceived = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._logger = initLogger(self)

        # Connect PixelCalibrationWidget signals
        #self._widget.PixelCalibrationLabelInfo.clicked.connect()
        self._widget.PixelCalibrationSnapPreviewButton.clicked.connect(self.snapPreview)
        self._widget.PixelCalibrationUndoButton.clicked.connect(self.undoSelection)
        self._widget.PixelCalibrationCalibrateButton.clicked.connect(self.startPixelCalibration)
        self._widget.PixelCalibrationStageCalibrationButton.clicked.connect(self.stageCalibration)
        
        self._widget.PixelCalibrationPixelSizeButton.clicked.connect(self.setPixelSize)
        self.pixelSize=500 # defaul FIXME: Load from json?
        # select detectors
        allDetectorNames = self._master.detectorsManager.getAllDeviceNames()
        self.detector = self._master.detectorsManager[allDetectorNames[0]]


    def undoSelection(self):
        # recover the previous selection
        self._widget.canvas.undoSelection()
        
    def snapPreview(self):
        self._logger.info("Snap preview...")
        self.previewImage = self.detector.getLatestFrame()
        self._widget.canvas.setImage(self.previewImage)
        
    def startPixelCalibration(self):
        # initilaze setup
        # this is not a thread!
        self.pixelSize = self._widget.getPixelSize()
        self._widget.setInformationLabel(str(self.pixelSize)+" µm")

    def setPixelSize(self):
        # returns nm from textedit
        self.pixelSize = self._widget.getPixelSizeTextEdit()

        #try setting it in the camera parameters
        try:
            self.detector.setPixelSizeUm(self.pixelSize*1e-3) # convert from nm to um
            self._widget.setInformationLabel(str(self.pixelSize)+" µm")
        except Exception as e:
            self._logger.error("Could not set pixel size in camera parameters")
            self._logger.error(e)
            self._widget.setInformationLabel("Could not set pixel size in camera parameters")
        
    def stageCalibration(self):
        import threading
        stageCalibrationT = threading.Thread(target=self.stageCalibrationThread, args=())
        stageCalibrationT.start()
        
    def stageCalibrationThread(self):
        # we assume we have a structured sample in focus
        # the sample is moved around and the deltas are measured
        # everything has to be inside a thread
        
        # select stage
        self.stages = self._master.positionersManager[self._master.positionersManager.getAllDeviceNames()[0]]

        # get current position
        currentPositions = self.stages.getPosition()
        self.initialPosition = (currentPositions["X"], currentPositions["Y"])
        self.initialPosiionZ = currentPositions["Z"]
        
        # define scan parameters
        self.xScanMin = -40
        self.xScanMax = 40
        self.yScanMin = -40
        self.yScanMax = 40
        self.xScanStep = 15
        self.yScanStep = 15
        
        # snake scan
        xyScanStepsAbsolute = []
        fwdpath = np.arange(self.xScanMin, self.xScanMax, self.xScanStep)
        bwdpath = np.flip(fwdpath)
        for indexX, ix in enumerate(np.arange(self.xScanMin, self.xScanMax, self.yScanStep)): 
            if indexX%2==0:
                for indexY, iy in enumerate(fwdpath):
                    xyScanStepsAbsolute.append([ix, iy])
            else:
                for indexY, iy in enumerate(bwdpath):
                    xyScanStepsAbsolute.append([ix, iy])

        # initialize xy coordinates
        self.stages.move(value=(self.xScanMin+self.initialPosition[0],self.yScanMin+self.initialPosition[1]), axis="XY", is_absolute=True, is_blocking=True)
        
        # store images
        allPosImages = []
        for ipos, iXYPos in enumerate(xyScanStepsAbsolute):
            
            # move to xy position is necessary
            self.stages.move(value=(iXYPos[0]+self.initialPosition[0],iXYPos[1]+self.initialPosition[1]), axis="XY", is_absolute=True, is_blocking=True)

            # antishake
            time.sleep(0.3)
            lastFrame = self.detector.getLatestFrame()
            allPosImages.append(lastFrame)
        
        # reinitialize xy coordinates
        self.stages.move(value=(self.initialPosition[0], self.initialPosition[1]), axis="XY", is_absolute=True, is_blocking=True)
        
        # process the slices and compute their relative distances in pixels
        from skimage.registration import phase_cross_correlation
        
        
        # compute shift between images relative to zeroth image
        allShifts = []
        for iImage in range(len(allPosImages)):
            image1 = allPosImages[0]
            image2 = allPosImages[iImage]
            shift, error, diffphase = phase_cross_correlation(image1, image2)
            
            allShifts.append(shift)
            
        # compute averrage shifts according to scan grid 
        shiftReal = np.array(xyScanStepsAbsolute)
        shiftReal -= np.min(shiftReal,0)
        shiftMeasured = np.array(allShifts)

        # whiten the data

        # compute differencs
        nShiftX = (self.xScanMax-self.xScanMin)//self.xScanStep
        nShiftY = (self.yScanMax-self.yScanMin)//self.yScanStep

        dReal = np.abs(shiftReal-np.roll(shiftReal,-1,0))
        dMeasured = np.abs(shiftMeasured-np.roll(shiftMeasured,-1,0))

        # determine the axis
        xAxisReal = np.argmin(np.mean(dReal,0))
        xAxisMeasured = np.argmin(np.mean(dMeasured,0))

        # swap axis (y,x)
        if xAxisReal != xAxisMeasured:
            xAxisMeasured = np.transposes(xAxisMeasured, (1,0))
        
        # stepsize => real motion / stepsize 
        stepSizeStage = (dMeasured*self.pixelSize)/dReal
        stepSizeStage[stepSizeStage == np.inf] = 0
        stepSizeStage = np.nan_to_num(stepSizeStage, nan=0.)
        stepSizeStage = stepSizeStage[np.where(stepSizeStage>0)]
        stepSizeStageDim = np.mean(stepSizeStage)
        stepSizeStageVar = np.var(stepSizeStage)

        self._logger.debug("Stage pixel size: "+str(stepSizeStageDim)+"nm/step")
        self._widget.setInformationLabel("Stage pixel size: "+str(stepSizeStageDim)+" nm/step")

        from imswitch.imcontrol.model import configfiletools
        # Set in setup info
        name="test"
        self._setupInfo.setPositionerPreset(name, self.makePreset())
        configfiletools.saveSetupInfo(configfiletools.loadOptions()[0], self._setupInfo)

        
            

       
        

        
        
        

# Copyright (C) 2020-2021 ImSwitch developers
# This file is part of ImSwitch.
#
# ImSwitch is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# ImSwitch is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.