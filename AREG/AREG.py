import os, sys, time, logging, zipfile, urllib.request, shutil, glob
import vtk, qt, slicer
from qt import (
    QWidget,
    QVBoxLayout,
    QScrollArea,
    QTabWidget,
    QGridLayout,
)
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin, pip_install
from functools import partialmethod

from AREG_Method.IOS import Auto_IOS, Semi_IOS
from AREG_Method.CBCT import Semi_CBCT, Auto_CBCT, Or_Auto_CBCT
from AREG_Method.Method import Method
from AREG_Method.Progress import Display

from CondaSetUp import  CondaSetUpCallWsl
from pathlib import Path
import pkg_resources
import platform
import threading
import subprocess
import re

def install_pytorch3d():
    try:
        import torch
        desired_pytorch_version= "1.11.0"
        desired_cuda_version = "cu113"
        if torch.__version__ != desired_pytorch_version or torch.version.cuda != desired_cuda_version.replace("cu",""):
            raise ImportError("Incompatible Pytorch version or CUDA version")
    except ImportError:
        # torch_install_cmd = f'torch=={desired_pytorch_version}+{desired_cuda_version} torchvision==0.12.0+{desired_cuda_version} torchaudio==0.11.0+{desired_cuda_version} --extra-index-url https://download.pytorch.org/whl/{desired_cuda_version}'
        # pip_install(torch_install_cmd)

        pip_install(f'--force-reinstall torch==1.12.0 torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/{desired_cuda_version}')
        import torch

    system = platform.system()

    if system == 'Darwin':  # MACOS
        try:
            import pytorch3d
        except ImportError:
            pip_install('pytorch3d')
            import pytorch3d

    else: # Linux or Windows
        # try:
        #     import pytorch3d
        #     # print('version_constraint splitted', version_constraint.split("==").split("<=").split(">=").split("<").split(">"))
        #     if pytorch3d.__version__ != version_constraint.replace("==","").replace("<=","").replace(">=","").replace("<","").replace(">",""):
        #         raise ImportError
        # except ImportError:
        # pyt_message = "ALI IOS needs to install pytorch3d library. \n"
        # pyt_message += "Do you agree to modify these libraries? Doing so could cause conflicts with other installed Extensions."
        # pyt_user_choice = slicer.util.confirmYesNoDisplay(pyt_message)
        # if pyt_user_choice:

        # try:
        #     import torch
        #     pyt_version_str=torch.__version__.split("+")[0].replace(".", "")
        #     version_str="".join([f"py3{sys.version_info.minor}_cu",torch.version.cuda.replace(".",""),f"_pyt{pyt_version_str}"])
        #     # pip_install('--upgrade pip')
        #     pip_install(f'pytorch3d -f https://dl.fbaipublicfiles.com/pytorch3d/packaging/wheels/{version_str}/download.html')
        # except: # install correct torch version
        #     print('force install pytorch3d')
        #     pip_install('torch==1.11.0+cu113 torchvision==0.12.0+cu113 torchaudio==0.11.0+cu113 --extra-index-url https://download.pytorch.org/whl/cu113')
        #     pip_install('pytorch3d -f https://dl.fbaipublicfiles.com/pytorch3d/packaging/wheels/py39_cu113_pyt1110/download.html')

        try:
            code_path = os.sep.join(
                os.path.dirname(os.path.abspath(__file__)).split(os.sep)
            )
            # print(code_path)
            pip_install(
                os.path.join(
                    code_path,
                    "AREG_IOS_utils",
                    "pytorch3d-0.7.0-cp39-cp39-linux_x86_64.whl",
                )
            )  # py39_cu113_pyt1120
            import pytorch3d
        except:
            pip_install(
                "--force-reinstall --no-deps --no-index --no-cache-dir pytorch3d -f https://dl.fbaipublicfiles.com/pytorch3d/packaging/wheels/py39_cu113_pyt1120/download.html"
            )
            import pytorch3d

def check_lib_installed(lib_name, required_version=None):
    '''
    Check if the library with the good version (if needed) is already installed in the slicer environment
    input: lib_name (str) : name of the library
            required_version (str) : required version of the library (if None, any version is accepted)
    output: bool : True if the library is installed with the good version, False otherwise
    '''
    try:
        installed_version = pkg_resources.get_distribution(lib_name).version
        # check if the version is the good one - if required_version != None it's considered as a True
        #required_version can have some constraints like ==, <=, >=, <, >, ex: >=1.0.0
        if required_version and installed_version != required_version:
          return False
        else:
          return True
    except pkg_resources.DistributionNotFound:
        return False

# import csv

def install_function(self,list_libs:list):
    '''
    Test the necessary libraries and install them with the specific version if needed
    User is asked if he wants to install/update-by changing his environment- the libraries with a pop-up window
    '''
    libs = list_libs
    libs_to_install = []
    libs_to_update = []
    installation_errors = []
    for lib, version_constraint,url in libs:
        if not check_lib_installed(lib, version_constraint):
            try:
            # check if the library is already installed
                if pkg_resources.get_distribution(lib).version:
                    libs_to_update.append((lib, version_constraint))
            except:
                libs_to_install.append((lib, version_constraint))

    if libs_to_install or libs_to_update:
          message = "The following changes are required for the libraries:\n"

          #Specify which libraries will be updated with a new version
          #and which libraries will be installed for the first time
          if libs_to_update:
              message += "\n --- Libraries to update (version mismatch): \n"
              message += "\n".join([f"{lib} (current: {pkg_resources.get_distribution(lib).version}) -> {version_constraint.replace('==','').replace('<=','').replace('>=','').replace('<','').replace('>','')}" for lib, version_constraint in libs_to_update])
              message += "\n"
          if libs_to_install:

              message += "\n --- Libraries to install:  \n"
          message += "\n".join([f"{lib}{version_constraint}" if version_constraint else lib for lib, version_constraint in libs_to_install])

          message += "\n\nDo you agree to modify these libraries? Doing so could cause conflicts with other installed Extensions."
          message += "\n\n (If you are using other extensions, consider downloading another Slicer to use AutomatedDentalTools exclusively.)"

          user_choice = slicer.util.confirmYesNoDisplay(message)

          if user_choice:
            self.ui.label_LibsInstallation.setVisible(True)
            try:
                for lib, version_constraint in libs_to_install + libs_to_update:
                    if lib == "pytorch3d":
                        install_pytorch3d()
                        continue
                    if not version_constraint:
                        pip_install(lib)

                    elif "https:/" in version_constraint:
                        print("version_constraint", version_constraint)
                        # download the library from the url
                        pip_install(version_constraint)
                    else:
                        print("version_constraint else", version_constraint)
                        lib_version = f'{lib}{version_constraint}' if version_constraint else lib
                        pip_install(lib_version)

                return True
            except Exception as e:
                    installation_errors.append((lib, str(e)))

            if installation_errors:
                error_message = "The following errors occured during installation:\n"
                error_message += "\n".join([f"{lib}: {error}" for lib, error in installation_errors])
                slicer.util.errorDisplay(error_message)
                return False
          else :
            return False

    else:
        return True

class AREG(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = (
            "AREG"  # TODO: make this more human readable by adding spaces
        )
        self.parent.categories = [
            "Automated Dental Tools"
        ]  # set categories (folders where the module shows up in the module selector)
        self.parent.dependencies = (
            []
        )  # TODO: add here list of module names that this module requires
        self.parent.contributors = [
            "Nathan Hutin (UoM), Luc Anchling (UoM)"
        ]  # TODO: replace with "Firstname Lastname (Organization)"
        # TODO: update with short description of the module and a link to online module documentation
        self.parent.helpText = """
        This is an example of scripted loadable module bundled in an extension.
        See more information in <a href="https://github.com/organization/projectname#AREG">module documentation</a>.
        """
        # TODO: replace with organization, grant and thanks
        self.parent.acknowledgementText = """
        This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
        and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
        """

        # Additional initialization step after application startup is complete
        slicer.app.connect("startupCompleted()", self.registerSampleData)

        #
        # Register sample data sets in Sample Data module
        #

    def registerSampleData(self):
        """
        Add data sets to Sample Data module.
        """
        # It is always recommended to provide sample data for users to make it easy to try the module,
        # but if no sample data is available then this method (and associated startupCompeted signal connection) can be removed.

        import SampleData

        iconsPath = os.path.join(os.path.dirname(__file__), "Resources/Icons")

        # To ensure that the source code repository remains small (can be downloaded and installed quickly)
        # it is recommended to store data sets that are larger than a few MB in a Github release.

        # ALI1
        SampleData.SampleDataLogic.registerCustomSampleDataSource(
            # Category and sample name displayed in Sample Data module
            category="AREG",
            sampleName="AREG1",
            # Thumbnail should have size of approximately 260x280 pixels and stored in Resources/Icons folder.
            # It can be created by Screen Capture module, "Capture all views" option enabled, "Number of images" set to "Single".
            thumbnailFileName=os.path.join(iconsPath, "AREG1.png"),
            # Download URL and target file name
            uris="https://github.com/Slicer/SlicerTestingData/releases/download/SHA256/998cb522173839c78657f4bc0ea907cea09fd04e44601f17c82ea27927937b95",
            fileNames="AREG1.nrrd",
            # Checksum to ensure file integrity. Can be computed by this command:
            #  import hashlib; print(hashlib.sha256(open(filename, "rb").read()).hexdigest())
            checksums="SHA256:998cb522173839c78657f4bc0ea907cea09fd04e44601f17c82ea27927937b95",
            # This node name will be used when the data set is loaded
            nodeNames="AREG1",
        )

        # AREG2
        SampleData.SampleDataLogic.registerCustomSampleDataSource(
            # Category and sample name displayed in Sample Data module
            category="AREG",
            sampleName="AREG2",
            thumbnailFileName=os.path.join(iconsPath, "AREG2.png"),
            # Download URL and target file name
            uris="https://github.com/Slicer/SlicerTestingData/releases/download/SHA256/1a64f3f422eb3d1c9b093d1a18da354b13bcf307907c66317e2463ee530b7a97",
            fileNames="AREG2.nrrd",
            checksums="SHA256:1a64f3f422eb3d1c9b093d1a18da354b13bcf307907c66317e2463ee530b7a97",
            # This node name will be used when the data set is loaded
            nodeNames="AREG2",
        )

        # self.ui.ButtonSearchModel2.clicked.connect(
        #     lambda: self.SearchModel(self.ui.lineEditModel2)
        # )


class PopUpWindow(qt.QDialog):
    """Class to generate a popup window with text and button (either radio or checkbox)"""

    def __init__(
        self,
        title="Title",
        text=None,
        listename=["1", "2", "3"],
        type=None,
        tocheck=None,
    ):
        QWidget.__init__(self)
        self.setWindowTitle(title)
        layout = QGridLayout()
        self.setLayout(layout)
        self.ListButtons = []
        self.listename = listename
        self.type = type

        if self.type == "radio":
            self.radiobutton(layout)

        elif self.type == "checkbox":
            self.checkbox(layout)
            if tocheck is not None:
                self.toCheck(tocheck)

        elif text is not None:
            label = qt.QLabel(text)
            layout.addWidget(label)
            # add ok button to close the window
            button = qt.QPushButton("OK")
            button.connect("clicked()", self.onClickedOK)
            layout.addWidget(button)

    def checkbox(self, layout):
        j = 0
        for i in range(len(self.listename)):
            button = qt.QCheckBox(self.listename[i])
            self.ListButtons.append(button)
            if i % 20 == 0:
                j += 1
            layout.addWidget(button, i % 20, j)
        # Add a button to select and deselect all
        button = qt.QPushButton("Select All")
        button.connect("clicked()", self.onClickedSelectAll)
        layout.addWidget(button, len(self.listename) + 1, j - 2)
        button = qt.QPushButton("Deselect All")
        button.connect("clicked()", self.onClickedDeselectAll)
        layout.addWidget(button, len(self.listename) + 1, j - 1)

        # Add a button to close the dialog
        button = qt.QPushButton("OK")
        button.connect("clicked()", self.onClickedCheckbox)
        layout.addWidget(button, len(self.listename) + 1, j)

    def toCheck(self, tocheck):
        for i in range(len(self.listename)):
            if self.listename[i] in tocheck:
                self.ListButtons[i].setChecked(True)

    def onClickedSelectAll(self):
        for button in self.ListButtons:
            button.setChecked(True)

    def onClickedDeselectAll(self):
        for button in self.ListButtons:
            button.setChecked(False)

    def onClickedCheckbox(self):
        TrueFalse = [button.isChecked() for button in self.ListButtons]
        self.checked = [
            self.listename[i] for i in range(len(self.listename)) if TrueFalse[i]
        ]
        self.accept()

    def radiobutton(self, layout):
        for i in range(len(self.listename)):
            radiobutton = qt.QRadioButton(self.listename[i])
            self.ListButtons.append(radiobutton)
            radiobutton.connect("clicked(bool)", self.onClickedRadio)
            layout.addWidget(radiobutton, i, 0)

    def onClickedRadio(self):
        self.checked = self.listename[
            [button.isChecked() for button in self.ListButtons].index(True)
        ]
        self.accept()

    def onClickedOK(self):
        self.accept()


#
# AREGWidget
#


class AREGWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent=None):
        """
        Called when the user opens the module the first time and the widget is initiAREGzed.
        """
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)  # needed for parameter node observation
        self.logic = None
        self._parameterNode = None
        self._updatingGUIFromParameterNode = False

        self.nb_patient = 0  # number of scans in the input folder

    def setup(self):
        """
        Called when the user opens the module the first time and the widget is initiAREGzed.
        """
        ScriptedLoadableModuleWidget.setup(self)

        # Load widget from .ui file (created by Qt Designer).
        # Additional widgets can be instantiated manually and added to self.layout.
        uiWidget = slicer.util.loadUI(self.resourcePath("UI/AREG.ui"))
        self.layout.addWidget(uiWidget)

        self.ui = slicer.util.childWidgetVariables(uiWidget)

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = AREGLogic()

        # Connections

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(
            slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose
        )
        self.addObserver(
            slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose
        )

        # These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
        # (in the selected parameter node).

        """
            888     888        d8888 8888888b.  8888888        d8888 888888b.   888      8888888888  .d8888b.
            888     888       d88888 888   Y88b   888         d88888 888  "88b  888      888        d88P  Y88b
            888     888      d88P888 888    888   888        d88P888 888  .88P  888      888        Y88b.
            Y88b   d88P     d88P 888 888   d88P   888       d88P 888 8888888K.  888      8888888     "Y888b.
             Y88b d88P     d88P  888 8888888P"    888      d88P  888 888  "Y88b 888      888            "Y88b.
              Y88o88P     d88P   888 888 T88b     888     d88P   888 888    888 888      888              "888
               Y888P     d8888888888 888  T88b    888    d8888888888 888   d88P 888      888        Y88b  d88P
                Y8P     d88P     888 888   T88b 8888888 d88P     888 8888888P"  88888888 8888888888  "Y8888P"
        """

        self.MethodDic = {
            "Semi_IOS": Semi_IOS(self),
            "Auto_IOS": Auto_IOS(self),
            "Semi_CBCT": Semi_CBCT(self),
            "Auto_CBCT": Auto_CBCT(self),
            "Or_Auto_CBCT": Or_Auto_CBCT(self),
        }
        self.reference_lm = []
        self.ActualMeth = Method
        self.ActualMeth = self.MethodDic["Or_Auto_CBCT"]
        self.type = "CBCT"
        self.nb_scan = 0
        self.startprocess = 0
        self.patient_process = 0
        self.dicchckbox = {}
        self.dicchckbox2 = {}
        self.display = Display
        self.isDCMInput = False
        self.CBCTOrientRef = "Frankfurt Horizontal and Midsagittal Plane"
        self.SegmentationLabels = [0]
        """
        exemple dic = {'teeth'=['A,....],'Type'=['O',...]}
        """

        self.log_path = os.path.join(slicer.util.tempDirectory(), "process.log")
        self.time = 0

        # use messletter to add big comment with univers as police

        documentsLocation = qt.QStandardPaths.DocumentsLocation
        self.documents = qt.QStandardPaths.writableLocation(documentsLocation)
        self.SlicerDownloadPath = os.path.join(
            self.documents,
            slicer.app.applicationName + "Downloads",
            "AREG",
            "AREG_" + self.type,
        )

        if not os.path.exists(self.SlicerDownloadPath):
            os.makedirs(self.SlicerDownloadPath)

        """

                                        8888888 888b    888 8888888 88888888888
                                          888   8888b   888   888       888
                                          888   88888b  888   888       888
                                          888   888Y88b 888   888       888
                                          888   888 Y88b888   888       888
                                          888   888  Y88888   888       888
                                          888   888   Y8888   888       888
                                        8888888 888    Y888 8888888     888

        """

        self.initCheckBoxCBCT(
            self.MethodDic["Semi_CBCT"],
            self.ui.LayoutSemiCBCT,
            self.ui.tohideCBCT,
        )

        self.initCheckBoxCBCT(
            self.MethodDic["Auto_CBCT"],
            self.ui.LayoutAutoCBCT,
            self.ui.tohideCBCT_2,
        )

        self.initCheckBoxCBCT(
            self.MethodDic["Or_Auto_CBCT"],
            self.ui.LayoutOrAutoCBCT,
            self.ui.tohideCBCT_3,
        )

        self.HideComputeItems()
        # self.initTest(self.MethodDic['Semi_IOS'])

        # self.dicchckbox=self.ActualMeth.getcheckbox()
        # self.dicchckbox2=self.ActualMeth.getcheckbox2()

        # self.enableCheckbox()

        # self.SwitchMode(0)
        self.SwitchType()

        """

                     .d8888b.   .d88888b.  888b    888 888b    888 8888888888  .d8888b.  88888888888
                    d88P  Y88b d88P" "Y88b 8888b   888 8888b   888 888        d88P  Y88b     888
                    888    888 888     888 88888b  888 88888b  888 888        888    888     888
                    888        888     888 888Y88b 888 888Y88b 888 8888888    888            888
                    888        888     888 888 Y88b888 888 Y88b888 888        888            888
                    888    888 888     888 888  Y88888 888  Y88888 888        888    888     888
                    Y88b  d88P Y88b. .d88P 888   Y8888 888   Y8888 888        Y88b  d88P     888
                     "Y8888P"   "Y88888P"  888    Y888 888    Y888 8888888888  "Y8888P"      888

        """

        self.ui.ButtonSearchScan1.pressed.connect(
            lambda: self.SearchScan(self.ui.lineEditScanT1LmPath)
        )
        self.ui.ButtonSearchScan2.pressed.connect(
            lambda: self.SearchScan(self.ui.lineEditScanT2LmPath)
        )
        self.ui.ButtonSearchModel1.pressed.connect(
            lambda: self.downloadModel(
                self.ui.lineEditModel1, self.ui.label_7.text.split(" ")[0]
            )
        )
        self.ui.ButtonSearchModel3.pressed.connect(
            lambda: self.downloadModel(
                self.ui.lineEditModel3, self.ui.label_4.text.split(" ")[0]
            )
        )
        self.ui.ButtonSearchModel2.pressed.connect(
            lambda: self.downloadModel(
                self.ui.lineEditModel2, self.ui.label_6.text.split(" ")[0]
            )
        )
        self.ui.ButtonOriented.connect("clicked(bool)", self.onPredictButton)
        self.ui.ButtonOutput.connect("clicked(bool)", self.ChosePathOutput)
        self.ui.ButtonCancel.connect("clicked(bool)", self.onCancel)
        self.ui.CbInputType.activated.connect(self.SwitchType)
        self.ui.CbModeType.activated.connect(self.SwitchType)
        self.ui.CbCBCTInputType.currentIndexChanged.connect(self.SwitchCBCTInputType)
        self.ui.ButtonTestFiles.clicked.connect(self.TestFiles)

    """


                888888b.   888     888 88888888888 88888888888  .d88888b.  888b    888  .d8888b.
                888  "88b  888     888     888         888     d88P" "Y88b 8888b   888 d88P  Y88b
                888  .88P  888     888     888         888     888     888 88888b  888 Y88b.
                8888888K.  888     888     888         888     888     888 888Y88b 888  "Y888b.
                888  "Y88b 888     888     888         888     888     888 888 Y88b888     "Y88b.
                888    888 888     888     888         888     888     888 888  Y88888       "888
                888   d88P Y88b. .d88P     888         888     Y88b. .d88P 888   Y8888 Y88b  d88P
                8888888P"   "Y88888P"      888         888      "Y88888P"  888    Y888  "Y8888P"



    """

    def SwitchCBCTInputType(self, index):
        """Function to change the input type of the CBCT (NIFTI or DCM)"""
        if index == 0:  # NIFTI as Input
            self.isDCMInput = False
        if index == 1:  # DCM as Input
            self.isDCMInput = True

    def SwitchModeCBCT(self, index):
        """Function to change the UI depending on the mode selected (Semi or Fully Automated)"""
        self.ui.CbCBCTInputType.setVisible(True)
        self.ui.label_CBCTInputType.setVisible(True)
        self.ui.label_CBCTInputType_2.setVisible(True)

        if index == 2:  # Semi-Automated
            self.ui.label_6.setVisible(False)
            # self.ui.label_7.setVisible(False)
            self.ui.lineEditModel2.setVisible(False)
            self.ui.lineEditModel2.setText(" ")
            # self.ui.lineEditModel1.setVisible(False)
            # self.ui.lineEditModel1.setText(" ")
            self.ui.ButtonSearchModel2.setVisible(False)
            # self.ui.ButtonSearchModel1.setVisible(False)
            # self.ui.advancedCollapsibleButton.setMaximumHeight(350)
            self.ui.label_4.setVisible(False)
            self.ui.lineEditModel3.setVisible(False)
            self.ui.ButtonSearchModel3.setVisible(False)
            self.ui.label_LibsInstallation.setVisible(False)

        if index == 1:  # Fully Automated
            # self.ui.label_6.setVisible(True)
            # self.ui.label_7.setVisible(True)
            # self.ui.lineEditModel1.setVisible(True)
            # self.ui.ButtonSearchModel1.setVisible(True)
            self.ui.lineEditModel2.setVisible(False)
            self.ui.ButtonSearchModel2.setVisible(False)
            self.ui.label_6.setVisible(False)
            self.ui.label_4.setVisible(False)
            self.ui.lineEditModel3.setVisible(False)
            self.ui.ButtonSearchModel3.setVisible(False)
            self.ui.label_LibsInstallation.setVisible(False)

        if index == 0:  #  Orientation & Fully Auto Reg
            if self.type == "CBCT":
                # self.ui.advancedCollapsibleButton.setMaximumHeight(10000)
                self.ui.label_6.setVisible(True)
                self.ui.lineEditModel2.setVisible(True)
                self.ui.ButtonSearchModel2.setVisible(True)
                self.ui.label_4.setVisible(False)
                self.ui.label_6.setText("Orientation Model Folder")
                self.ui.lineEditModel3.setVisible(False)
                self.ui.ButtonSearchModel3.setVisible(False)
                self.ui.CbCBCTInputType.setVisible(False)
                self.ui.label_CBCTInputType.setVisible(False)
                self.ui.label_CBCTInputType_2.setVisible(False)
                self.isDCMInput = False
                self.ui.label_LibsInstallation.setVisible(False)

    def SwitchModeIOS(self, index):
        self.ui.CbCBCTInputType.setVisible(False)
        self.ui.label_CBCTInputType.setVisible(False)
        self.ui.label_CBCTInputType_2.setVisible(False)
        self.isDCMInput = False
        # registration and orientation
        if index == 0:
            self.ui.label_7.setVisible(True)
            self.ui.label_7.setText("Segmentation Model Folder")
            self.ui.ButtonSearchModel1.setVisible(True)
            self.ui.lineEditModel1.setVisible(True)

            self.ui.label_6.setVisible(True)
            self.ui.label_6.setText("Reference Orientation Folder")
            self.ui.lineEditModel2.setVisible(True)
            self.ui.ButtonSearchModel2.setVisible(True)

            self.ui.label_4.setVisible(True)
            self.ui.label_4.setText("Registration Model Folder")
            self.ui.lineEditModel3.setVisible(True)
            self.ui.ButtonSearchModel3.setVisible(True)

            self.ui.label_LibsInstallation.setVisible(False)
        # Registration
        if index == 1:
            self.ui.label_7.setVisible(False)
            self.ui.label_7.setText("Segmentation Model Folder")
            self.ui.ButtonSearchModel1.setVisible(False)
            self.ui.lineEditModel1.setVisible(False)

            self.ui.label_6.setVisible(False)
            self.ui.label_6.setText("Reference Orientation Folder")
            self.ui.lineEditModel2.setVisible(False)
            self.ui.ButtonSearchModel2.setVisible(False)

            self.ui.label_4.setVisible(True)
            self.ui.label_4.setText("Registration Model Folder")
            self.ui.lineEditModel3.setVisible(True)
            self.ui.ButtonSearchModel3.setVisible(True)

            self.ui.label_LibsInstallation.setVisible(False)
    def SwitchType(self):
        """Function to change the UI and the Method in AREG depending on the selected type (Semi CBCT, Fully CBCT...)"""
        if self.ui.CbInputType.currentIndex == 0:
            if self.ui.CbModeType.currentIndex == 2:
                self.ActualMeth = self.MethodDic["Semi_CBCT"]
                self.ui.stackedWidget.setCurrentIndex(0)

            elif self.ui.CbModeType.currentIndex == 0:
                self.ActualMeth = self.MethodDic["Or_Auto_CBCT"]
                self.ui.stackedWidget.setCurrentIndex(2)
                self.ui.label_7.setText("Segmentation Model Folder")

            elif self.ui.CbModeType.currentIndex == 1:
                self.ActualMeth = self.MethodDic["Auto_CBCT"]
                self.ui.stackedWidget.setCurrentIndex(1)
                self.ui.label_7.setText("Segmentation Model Folder")

            self.type = "CBCT"
            self.SwitchModeCBCT(self.ui.CbModeType.currentIndex)

            number_item = self.ui.CbModeType.count
            if number_item == 2:
                for _ in range(number_item):
                    self.ui.CbModeType.removeItem(0)

                self.ui.CbModeType.addItem("Orientation and Registration")
                self.ui.CbModeType.addItem("Fully-Automated Registration")
                self.ui.CbModeType.addItem("Semi-Automated Registration")

        elif self.ui.CbInputType.currentIndex == 1:
            if self.ui.CbModeType.currentIndex == 1:
                self.ActualMeth = self.MethodDic["Semi_IOS"]
                self.ui.stackedWidget.setCurrentIndex(3)
                self.type = "IOS"

            elif self.ui.CbModeType.currentIndex == 0:
                self.ActualMeth = self.MethodDic["Auto_IOS"]
                self.ui.stackedWidget.setCurrentIndex(3)
                self.type = "IOS"
                self.ui.label_7.setText("Segmentation Model Folder")

            number_item = self.ui.CbModeType.count
            if number_item == 3:
                for _ in range(number_item):
                    self.ui.CbModeType.removeItem(0)

                self.ui.CbModeType.addItem("Orientation and Registration")
                self.ui.CbModeType.addItem("Registration")

            self.SwitchModeIOS(self.ui.CbModeType.currentIndex)

        self.dicchckbox = self.ActualMeth.getcheckbox()
        self.dicchckbox2 = self.ActualMeth.getcheckbox2()

        self.SlicerDownloadPath = os.path.join(
            self.documents,
            slicer.app.applicationName + "Downloads",
            "AREG",
            "AREG_" + self.type,
        )

        self.ClearAllLineEdits()

        self.enableCheckbox()

        self.HideComputeItems()

        if self.type == "CBCT":
            self.ui.CbCBCTInputType.setVisible(True)
            self.ui.label_CBCTInputType.setVisible(True)
            self.ui.label_CBCTInputType_2.setVisible(True)

        if self.type == "IOS" or (
            self.type == "CBCT" and self.ui.CbModeType.currentIndex != 0
        ):
            self.ui.CbCBCTInputType.setVisible(False)
            self.ui.label_CBCTInputType.setVisible(False)
            self.ui.label_CBCTInputType_2.setVisible(False)
            self.isDCMInput = False

    def ClearAllLineEdits(self):
        """Function to clear all the line edits"""
        self.ui.lineEditScanT1LmPath.setText("")
        self.ui.lineEditScanT2LmPath.setText("")
        self.ui.lineEditModel2.setText("")
        self.ui.lineEditModel1.setText("")
        self.ui.lineEditOutputPath.setText("")

    def DownloadUnzip(
        self, url, directory, folder_name=None, num_downl=1, total_downloads=1
    ):
        out_path = os.path.join(directory, folder_name)

        if not os.path.exists(out_path):
            # print("Downloading {}...".format(folder_name.split(os.sep)[0]))
            os.makedirs(out_path)

            temp_path = os.path.join(directory, "temp.zip")

            # Download the zip file from the url
            with urllib.request.urlopen(url) as response, open(
                temp_path, "wb"
            ) as out_file:
                # Pop up a progress bar with a QProgressDialog
                progress = qt.QProgressDialog(
                    "Downloading {} (File {}/{})".format(
                        folder_name.split(os.sep)[0], num_downl, total_downloads
                    ),
                    "Cancel",
                    0,
                    100,
                    self.parent,
                )
                progress.setCancelButton(None)
                progress.setWindowModality(qt.Qt.WindowModal)
                progress.setWindowTitle(
                    "Downloading {}...".format(folder_name.split(os.sep)[0])
                )
                # progress.setWindowFlags(qt.Qt.WindowStaysOnTopHint)
                progress.show()
                length = response.info().get("Content-Length")
                if length:
                    length = int(length)
                    blocksize = max(4096, length // 100)
                    read = 0
                    while True:
                        buffer = response.read(blocksize)
                        if not buffer:
                            break
                        read += len(buffer)
                        out_file.write(buffer)
                        progress.setValue(read * 100.0 / length)
                        qt.QApplication.processEvents()
                shutil.copyfileobj(response, out_file)

            # Unzip the file
            with zipfile.ZipFile(temp_path, "r") as zip:
                zip.extractall(out_path)

            # Delete the zip file
            os.remove(temp_path)

        return out_path

    def TestFiles(self):
        """Function to download and select all the test files"""
        if self.isDCMInput:
            name, url = self.ActualMeth.getTestFileListDCM()
        else:
            name, url = self.ActualMeth.getTestFileList()

        print("name : ",name)
        print("url : ",url)

        scan_folder = self.DownloadUnzip(
            url=url,
            directory=os.path.join(self.SlicerDownloadPath),
            folder_name=os.path.join("Test_Files", name)
            if not self.isDCMInput
            else os.path.join("Test_Files", "DCM", name),
        )

        print("scan folder : ",scan_folder)
        scan_folder_t1 = os.path.join(scan_folder, "T1")
        scan_folder_t2 = os.path.join(scan_folder, "T2")

        if self.isDCMInput:
            nb_scans = self.ActualMeth.NumberScanDCM(scan_folder_t1, scan_folder_t2)
            error = self.ActualMeth.TestScanDCM(scan_folder_t1, scan_folder_t2)
        else:
            nb_scans = self.ActualMeth.NumberScan(scan_folder_t1, scan_folder_t2)
            error = self.ActualMeth.TestScan(scan_folder_t1, scan_folder_t2)

        if isinstance(error, str):
            qt.QMessageBox.warning(self.parent, "Warning", error)
        else:
            self.nb_patient = nb_scans
            self.ui.lineEditScanT1LmPath.setText(scan_folder_t1)
            self.ui.lineEditScanT2LmPath.setText(scan_folder_t2)
            self.ui.LabelInfoPreProc.setText(
                "Number of Patients to process : " + str(nb_scans)
            )
            self.ui.LabelProgressPatient.setText(
                "Patient processed : 0 /" + str(nb_scans)
            )
            self.enableCheckbox()

        if self.type == "CBCT":
            self.downloadModel(
                lineEdit=self.ui.lineEditModel1, name="Segmentation", test=True
            )
            if self.ui.CbModeType.currentIndex == 0:
                self.SearchModelALI(self.CBCTOrientRef)
                self.downloadModel(
                    lineEdit=self.ui.lineEditModel2, name="Orientation", test=True
                )

        if self.ui.lineEditOutputPath.text == "":
            dir, spl = os.path.split(scan_folder)
            self.ui.lineEditOutputPath.setText(os.path.join(dir, spl, "Registered"))

    def CheckScan(self):
        """Function to test both t1 and t2 scan folders"""
        if self.isDCMInput:
            nb_scans = self.ActualMeth.NumberScanDCM(
                self.ui.lineEditScanT1LmPath.text, self.ui.lineEditScanT2LmPath.text
            )
            error = self.ActualMeth.TestScanDCM(
                self.ui.lineEditScanT1LmPath.text, self.ui.lineEditScanT2LmPath.text
            )

        else:
            nb_scans = self.ActualMeth.NumberScan(
                self.ui.lineEditScanT1LmPath.text, self.ui.lineEditScanT2LmPath.text
            )
            error = self.ActualMeth.TestScan(
                self.ui.lineEditScanT1LmPath.text, self.ui.lineEditScanT2LmPath.text
            )

        if isinstance(error, str):
            qt.QMessageBox.warning(self.parent, "Warning", error)

        else:
            self.nb_patient = nb_scans
            self.ui.LabelInfoPreProc.setText(
                "Number of Patients to process : " + str(nb_scans)
            )
            self.ui.LabelProgressPatient.setText(
                "Patient process : 0 /" + str(nb_scans)
            )
            self.enableCheckbox()

    def SearchScan(self, lineEdit):
        scan_folder = qt.QFileDialog.getExistingDirectory(
            self.parent, "Select a scan folder for Input"
        )

        if not scan_folder == "":
            lineEdit.setText(scan_folder)

            # To check if the input segmentation (for the Semi-Auto CBCT mode) has different labels to show them in a combobox
            if (
                self.ui.lineEditScanT1LmPath.text != ""
                and self.ui.lineEditScanT2LmPath.text == ""
            ):
                if (
                    self.ui.CbInputType.currentIndex == 0
                    and self.ui.CbModeType.currentIndex == 2
                ):
                    if self.SegmentationLabels == [0]:
                        self.SegmentationLabels += self.ActualMeth.GetSegmentationLabel(
                            self.ui.lineEditScanT1LmPath.text
                        )
                        for i in self.SegmentationLabels:
                            if i != 0:
                                self.ui.LabelSelectcomboBox.addItem(f"Label {i}")

            if (
                self.ui.lineEditScanT1LmPath.text != ""
                and self.ui.lineEditScanT2LmPath.text != ""
            ):
                self.CheckScan()

    def downloadModel(self, lineEdit, name, test=False):
        """Function to download the model files from the link in the getModelUrl function"""

        # To select the reference files (CBCT Orientation and Registration mode only)
        if (
            self.type == "CBCT"
            and self.ui.CbModeType.currentIndex == 0
            and not test
            and name == "Orientation"
        ):
            referenceList = self.ActualMeth.getReferenceList()
            refList = list(referenceList.keys())

            s = PopUpWindow(
                title="Choice of Reference Files", listename=refList, type="radio"
            )
            s.exec_()
            self.CBCTOrientRef = s.checked

            self.SearchModelALI(self.CBCTOrientRef)

        listmodel = self.ActualMeth.getModelUrl()

        urls = listmodel[name]
        if isinstance(urls, str):
            url = urls
            _ = self.DownloadUnzip(
                url=url,
                directory=os.path.join(self.SlicerDownloadPath),
                folder_name=os.path.join("Models", name),
                num_downl=1,
                total_downloads=1,
            )
            model_folder = os.path.join(self.SlicerDownloadPath, "Models", name)

        elif isinstance(urls, dict):
            for i, (name_bis, url) in enumerate(urls.items()):
                _ = self.DownloadUnzip(
                    url=url,
                    directory=os.path.join(self.SlicerDownloadPath),
                    folder_name=os.path.join("Models", name, name_bis),
                    num_downl=i + 1,
                    total_downloads=len(urls),
                )
            model_folder = os.path.join(self.SlicerDownloadPath, "Models", name)

        if not model_folder == "":
            error = self.ActualMeth.TestModel(model_folder, lineEdit.name)

            if isinstance(error, str):
                qt.QMessageBox.warning(self.parent, "Warning", error)

            else:
                lineEdit.setText(model_folder)
                self.enableCheckbox()

    def SearchModelALI(self, reference_type=None):
        """Function to download the ALI CBCT model files"""
        if reference_type is None:
            ret = ["Ba", "S", "N", "RPo", "LPo", "ROr", "LOr"]
        else:
            correspondance = {
                "Occlusal and Midsagittal Plane": [
                    "IF",
                    "ANS",
                    "PNS",
                    "UR1O",
                    "UR6O",
                    "UL6O",
                ],
                "Frankfurt Horizontal and Midsagittal Plane": [
                    "N",
                    "S",
                    "Ba",
                    "RPo",
                    "LPo",
                    "LOr",
                    "ROr",
                ],
            }
            ret = correspondance[reference_type]

        name, url = self.ActualMeth.getALIModelList()
        # dirr = self.SlicerDownloadPath.replace("AREG", "ASO")
        for i, model in enumerate(ret):
            _ = self.DownloadUnzip(
                url=os.path.join(url, "{}.zip".format(model)),
                directory=self.SlicerDownloadPath.replace("AREG", "ALI"),
                folder_name=model,
                num_downl=i + 1,
                total_downloads=len(ret),
            )

        model_folder = self.SlicerDownloadPath.replace("AREG", "ALI")

        if not model_folder == "":
            error = self.ActualMeth.TestModel(model_folder, self.ui.lineEditModel3.name)

            if isinstance(error, str):
                qt.QMessageBox.warning(self.parent, "Warning", error)

            else:
                self.ui.lineEditModel3.setText(model_folder)
                self.enableCheckbox()

    def ChosePathOutput(self):
        out_folder = qt.QFileDialog.getExistingDirectory(
            self.parent, "Select a scan folder"
        )
        if not out_folder == "":
            self.ui.lineEditOutputPath.setText(out_folder)

    def enableCheckbox(self):
        status = self.ActualMeth.existsLandmark(
            self.ui.lineEditScanT1LmPath.text,
            self.ui.lineEditScanT2LmPath.text,
            self.ui.lineEditModel2.text,
        )

        if status is None:
            return

        if self.type == "CBCT":
            for checkboxs, checkboxs2 in zip(
                self.dicchckbox.values(), self.dicchckbox2.values()
            ):
                for checkbox, checkbox2 in zip(checkboxs, checkboxs2):
                    checkbox.setVisible(status[checkbox.text])
                    checkbox2.setVisible(status[checkbox2.text])
                    if status[checkbox.text]:
                        checkbox.setChecked(True)
                        checkbox2.setChecked(True)

    """

                    8888888b.  8888888b.   .d88888b.   .d8888b.  8888888888  .d8888b.   .d8888b.
                    888   Y88b 888   Y88b d88P" "Y88b d88P  Y88b 888        d88P  Y88b d88P  Y88b
                    888    888 888    888 888     888 888    888 888        Y88b.      Y88b.
                    888   d88P 888   d88P 888     888 888        8888888     "Y888b.    "Y888b.
                    8888888P"  8888888P"  888     888 888        888            "Y88b.     "Y88b.
                    888        888 T88b   888     888 888    888 888              "888       "888
                    888        888  T88b  Y88b. .d88P Y88b  d88P 888        Y88b  d88P Y88b  d88P
                    888        888   T88b  "Y88888P"   "Y8888P"  8888888888  "Y8888P"   "Y8888P"


    """

    def onPredictButton(self):
        # install required libraries for all modules used (ASO,ALI,AMASS) and for the selected module
        if platform.system()== "Windows":
            if self.type == "CBCT":
                # libraries and versions compatibility to use AREG_CBCT
                list_libs_CBCT_windows = [('itk','<=5.4.rc1',None),('itk-elastix','==0.17.1',None),('dicom2nifti', '==2.3.0',None),('pydicom', '==2.2.2',None),('einops',None,None),('nibabel',None,None),('connected-components-3d','==3.9.1',None),
                            ('pandas',None,None),('torch',None,"https://download.pytorch.org/whl/cu118"),('monai','==0.7.0',None)] #(lib_name, version, url)

                is_installed = install_function(self,list_libs_CBCT_windows)

            if self.type == "IOS":
                is_installed = False
                check_env = self.check_wsl_environment()
                print("seg_env : ",check_env)
                
                if check_env :
                    list_libs_IOS =[("tqdm",None,None),('vtk',None,None),('pandas',None,None),('monai','==0.7.0',None)]

                    is_installed = install_function(self,list_libs_IOS)
                # qt.QMessageBox.warning(self.parent, 'Warning', 'AREG IOS is currently not available on Windows. Please use a Linux or MacOS system to run the module.')

        else:
            if self.type == "CBCT":
                # libraries and versions compatibility to use AREG_CBCT
                list_libs_CBCT = [('itk','<=5.4.rc1',None),('itk-elastix','==0.17.1',None),('dicom2nifti', '==2.3.0',None),('pydicom', '==2.2.2',None),('einops',None,None),('nibabel',None,None),('connected-components-3d','==3.9.1',None),
                            ('pandas',None,None),('torch',None,None),('monai','==0.7.0',None)] #(lib_name, version, url)

                is_installed = install_function(self,list_libs_CBCT)

            if self.type == "IOS":
                # Installation of pytorch is done before pytorch3d installation in the function because the order is important andfor version compatibility
                list_libs_IOS =[("shapeaxi",None,None),('vtk',None,None),('pandas',None,None),('monai','==0.7.0',None),
                                ('pytorch3d',"==0.7.0","https://dl.fbaipublicfiles.com/pytorch3d/packaging/wheels/py39_cu113_pyt1120/download.html"),
                                ('torchmetrics','==0.9.3',None),('pytorch-lightning','==1.7.7',None)]

                is_installed = install_function(self,list_libs_IOS)

        # If the user didn't accept the installation, the module doesn't run
        if not is_installed:
            qt.QMessageBox.warning(self.parent, 'Warning', 'The module will not work properly without the required libraries.\nPlease install them and try again.')
            return

        self.ui.label_LibsInstallation.setVisible(False)
        error = self.ActualMeth.TestProcess(
            input_t1_folder=self.ui.lineEditScanT1LmPath.text,
            input_t2_folder=self.ui.lineEditScanT2LmPath.text,
            folder_output=self.ui.lineEditOutputPath.text,
            model_folder_1=self.ui.lineEditModel1.text,
            model_folder_2=self.ui.lineEditModel2.text,
            model_folder_3=self.ui.lineEditModel3.text,
            add_in_namefile=self.ui.lineEditAddName.text,
            dic_checkbox=self.dicchckbox,
            isDCMInput=self.isDCMInput,
            OrientReference=self.CBCTOrientRef,
        )

        # print('error',error)
        if isinstance(error, str):
            qt.QMessageBox.warning(self.parent, "Warning", error.replace(",", "\n"))

        else:
            if self.type == "CBCT":
                merge_seg = (
                    self.ActualMeth.merge_seg_checkbox.isChecked()
                    if self.ActualMeth.merge_seg_checkbox is not None
                    else False
                )
            else:
                merge_seg = None

            self.list_Processes_Parameters = self.ActualMeth.Process(
                input_t1_folder=self.ui.lineEditScanT1LmPath.text,
                input_t2_folder=self.ui.lineEditScanT2LmPath.text,
                folder_output=self.ui.lineEditOutputPath.text,
                model_folder_1=self.ui.lineEditModel1.text,
                model_folder_2=self.ui.lineEditModel2.text,
                model_folder_3=self.ui.lineEditModel3.text,
                add_in_namefile=self.ui.lineEditAddName.text,
                dic_checkbox=self.dicchckbox,
                logPath=self.log_path,
                merge_seg=merge_seg,
                isDCMInput=self.isDCMInput,
                slicerDownload=self.SlicerDownloadPath,
                OrientReference=self.CBCTOrientRef,
                LabelSeg=str(
                    self.SegmentationLabels[self.ui.LabelSelectcomboBox.currentIndex]
                ),
                ApproxStep=self.ui.ApproxcheckBox.isChecked(),
            )

            self.nb_extension_launch = len(self.list_Processes_Parameters)
            self.onProcessStarted()

            # /!\ Launch of the first process /!\
            print("module name : ",self.list_Processes_Parameters[0]["Module"])
            # if we are on windows, crownsegmentation and areg ios need to be run in wsl because of Pytorch3D
            if (self.list_Processes_Parameters[0]["Module"]=="CrownSegmentationcli T1" or self.list_Processes_Parameters[0]["Module"]=="AREG_IOS") and platform.system()== "Windows" :
                if self.list_Processes_Parameters[0]["Module"]=="CrownSegmentationcli T1" :
                    self.run_wsl("seg")
                else :
                    self.run_wsl("areg")
                
            self.process = slicer.cli.run(
                self.list_Processes_Parameters[0]["Process"],
                None,
                self.list_Processes_Parameters[0]["Parameter"],
            )
            self.module_name = self.list_Processes_Parameters[0]["Module"]
            self.displayModule = self.list_Processes_Parameters[0]["Display"]
            self.processObserver = self.process.AddObserver(
                "ModifiedEvent", self.onProcessUpdate
            )

            del self.list_Processes_Parameters[0]

    def onProcessStarted(self):
        self.ui.label_LibsInstallation.setHidden(True)
        self.startTime = time.time()

        # self.ui.progressBar.setMaximum(self.nb_patient)
        self.ui.progressBar.setValue(0)

        self.ui.LabelProgressPatient.setText(f"Patient : 0 / {self.nb_patient}")
        self.ui.LabelProgressExtension.setText(
            f"Extension : 0 / {self.nb_extension_launch}"
        )
        self.nb_extnesion_did = 0

        self.module_name_before = 0
        self.nb_change_bystep = 0

        self.RunningUI(True)

    def onProcessUpdate(self, caller, event):
        # timer = f"Time : {time.time()-self.startTime:.2f}s"
        currentTime = time.time() - self.startTime
        if currentTime < 60:
            timer = f"Time : {int(currentTime)}s"
        elif currentTime < 3600:
            timer = f"Time : {int(currentTime/60)}min and {int(currentTime%60)}s"
        else:
            timer = f"Time : {int(currentTime/3600)}h, {int(currentTime%3600/60)}min and {int(currentTime%60)}s"

        self.ui.LabelTimer.setText(timer)
        progress = caller.GetProgress()
        # self.module_name = caller.GetModuleTitle() if self.module_name_bis is None else self.module_name_bis
        self.ui.LabelNameExtension.setText(self.module_name)
        # self.displayModule = self.displayModule_bis if self.displayModule_bis is not None else self.display[self.module_name.split(' ')[0]]

        if self.module_name_before != self.module_name:
            self.ui.LabelProgressPatient.setText(f"Patient : 0 / {self.nb_patient}")
            self.nb_extnesion_did += 1
            self.ui.LabelProgressExtension.setText(
                f"Extension : {self.nb_extnesion_did} / {self.nb_extension_launch}"
            )
            self.ui.progressBar.setValue(0)

            # if self.nb_change_bystep == 0 and self.module_name_before:
            #     print(f'Error this module doesn\'t work {self.module_name_before}')

            self.module_name_before = self.module_name
            self.nb_change_bystep = 0

        if progress == 0:
            self.updateProgessBar = False

        if self.displayModule.isProgress(
            progress=progress, updateProgessBar=self.updateProgessBar
        ):
            progress_bar, message = self.displayModule()
            self.ui.progressBar.setValue(progress_bar)
            self.ui.LabelProgressPatient.setText(message)
            self.nb_change_bystep += 1

        if caller.GetStatus() & caller.Completed:
            if caller.GetStatus() & caller.ErrorsMask:
                # error
                print("\n\n ========= PROCESSED ========= \n")

                print(self.process.GetOutputText())
                print("\n\n ========= ERROR ========= \n")
                errorText = self.process.GetErrorText()
                print("CLI execution failed: \n \n" + errorText)
                # error
                # errorText = caller.GetErrorText()
                # print("\n"+ 70*"=" + "\n\n" + errorText)
                # print(70*"=")
                self.onCancel()

            else:
                print("\n\n ========= PROCESSED ========= \n")
                # print("PROGRESS :",self.displayModule.progress)

                print(self.process.GetOutputText())
                try:
                    print("name process : ",self.list_Processes_Parameters[0]["Process"])
                    if self.list_Processes_Parameters[0]["Module"]=="AREG_IOS" and platform.system()== "Windows" :
                        self.run_wsl("areg")
                    self.process = slicer.cli.run(
                        self.list_Processes_Parameters[0]["Process"],
                        None,
                        self.list_Processes_Parameters[0]["Parameter"],
                    )
                    self.module_name = self.list_Processes_Parameters[0]["Module"]
                    self.displayModule = self.list_Processes_Parameters[0]["Display"]
                    self.processObserver = self.process.AddObserver(
                        "ModifiedEvent", self.onProcessUpdate
                    )
                    del self.list_Processes_Parameters[0]
                    # self.displayModule.progress = 0
                except IndexError:
                    self.OnEndProcess()

    def OnEndProcess(self):
        self.ui.LabelProgressPatient.setText(f"Patient : 0 / {self.nb_patient}")
        self.nb_extnesion_did += 1
        self.ui.LabelProgressExtension.setText(
            f"Extension : {self.nb_extnesion_did} / {self.nb_extension_launch}"
        )
        self.ui.progressBar.setValue(0)

        # if self.nb_change_bystep == 0:
        #     print(f'Erreur this module didnt work {self.module_name_before}')

        self.module_name_before = self.module_name
        self.nb_change_bystep = 0
        total_time = time.time() - self.startTime
        average_time = total_time / self.nb_patient
        print("PROCESS DONE.")
        print(
            "Done in {} min and {} sec".format(
                int(total_time / 60), int(total_time % 60)
            )
        )
        print(
            "Average time per patient : {} min and {} sec".format(
                int(average_time / 60), int(average_time % 60)
            )
        )
        self.RunningUI(False)

        stopTime = time.time()

        logging.info(f"Processing completed in {stopTime-self.startTime:.2f} seconds")

        s = PopUpWindow(
            title="Process Done",
            text="Successfully done in {} min and {} sec \nAverage time per Patient: {} min and {} sec".format(
                int(total_time / 60),
                int(total_time % 60),
                int(average_time / 60),
                int(average_time % 60),
            ),
        )
        s.exec_()

        file_path = os.path.abspath(__file__)
        folder_path = os.path.dirname(file_path)
        csv_file = os.path.join(folder_path,"AREG_Method","liste_csv_file_T1.csv")
        print("csv_file : ",csv_file)
        if os.path.exists(csv_file):
          os.remove(csv_file)

        csv_file = os.path.join(folder_path,"AREG_Method","liste_csv_file_T2.csv")
        print("csv_file : ",csv_file)
        if os.path.exists(csv_file):
          os.remove(csv_file)

    def onCancel(self):
        self.process.Cancel()

        self.RunningUI(False)

    def RunningUI(self, run=False):
        self.ui.ButtonOriented.setVisible(not run)

        self.ui.progressBar.setVisible(run)
        self.ui.LabelTimer.setVisible(run)

        self.HideComputeItems(run)
        
        
    def run_wsl(self,type):
        if type=="seg":
            output_command = self.conda_wsl.condaRunCommand(["which","dentalmodelseg"],"shapeaxi").strip()
            clean_output = re.search(r"Result: (.+)", output_command)
            dentalmodelseg_path = clean_output.group(1).strip()
            dentalmodelseg_path_clean = dentalmodelseg_path.replace("\\n","")
            for i in range(2):
                name_env = "shapeaxi"
                args = self.list_Processes_Parameters[0]["Parameter"]
                print("args : ",args)
                conda_exe = self.conda_wsl.getCondaExecutable()
                command = [conda_exe, "run", "-n", name_env, "python" ,"-m", f"CrownSegmentationcli"]
                for key, value in args.items():
                    if key in ["out","input_csv","vtk_folder","dentalmodelseg_path"]:
                        value = self.windows_to_linux_path(value)
                    if key == "dentalmodelseg_path" :
                        value = dentalmodelseg_path_clean
                    command.append(f"\"{value}\"")
                print("*"*50)
                print("command : ",command)

                # running in // to not block Slicer
                process = threading.Thread(target=self.conda_wsl.condaRunCommand, args=(command,))
                process.start()
                self.ui.LabelTimer.setHidden(False)
                self.ui.LabelTimer.setText(f"Time : 0.00s")
                previous_time = self.startTime
                while process.is_alive():
                    slicer.app.processEvents()
                    current_time = time.time()
                    gap=current_time-previous_time
                    if gap>0.3:
                        currentTime = time.time() - self.startTime
                        previous_time = currentTime
                        if currentTime < 60:
                            timer = f"Time : {int(currentTime)}s"
                        elif currentTime < 3600:
                            timer = f"Time : {int(currentTime/60)}min and {int(currentTime%60)}s"
                        else:
                            timer = f"Time : {int(currentTime/3600)}h, {int(currentTime%3600/60)}min and {int(currentTime%60)}s"
                        
                        self.ui.LabelTimer.setText(timer)

                del self.list_Processes_Parameters[0]
        elif type=="areg":
            name_env = "shapeaxi"
            args = self.list_Processes_Parameters[0]["Parameter"]
            print("args : ",args)
            conda_exe = self.conda_wsl.getCondaExecutable()
            command = [conda_exe, "run", "-n", name_env, "python" ,"-m", f"AREG_IOS"]
            for key, value in args.items():
                print("key : ",key)
                if Path(value).is_file() or Path(value).is_dir() :
                    value = self.windows_to_linux_path(value)
                command.append(f"\"{value}\"")
            print("command : ",command)

            # running in // to not block Slicer
            process = threading.Thread(target=self.conda_wsl.condaRunCommand, args=(command,))
            process.start()
            self.ui.LabelTimer.setHidden(False)
            self.ui.LabelTimer.setText(f"time : 0.00s")
            previous_time = self.startTime
            while process.is_alive():
                slicer.app.processEvents()
                current_time = time.time()
                gap=current_time-previous_time
                if gap>0.3:
                    currentTime = time.time() - self.startTime
                    previous_time = currentTime
                    if currentTime < 60:
                        timer = f"Time : {int(currentTime)}s"
                    elif currentTime < 3600:
                        timer = f"Time : {int(currentTime/60)}min and {int(currentTime%60)}s"
                    else:
                        timer = f"Time : {int(currentTime/3600)}h, {int(currentTime%3600/60)}min and {int(currentTime%60)}s"
                    
                    self.ui.LabelTimer.setText(timer)

            del self.list_Processes_Parameters[0]
            

    """

            8888888888 888     888 888b    888  .d8888b.      8888888 888b    888 8888888 88888888888
            888        888     888 8888b   888 d88P  Y88b       888   8888b   888   888       888
            888        888     888 88888b  888 888    888       888   88888b  888   888       888
            8888888    888     888 888Y88b 888 888              888   888Y88b 888   888       888
            888        888     888 888 Y88b888 888              888   888 Y88b888   888       888
            888        888     888 888  Y88888 888    888       888   888  Y88888   888       888
            888        Y88b. .d88P 888   Y8888 Y88b  d88P       888   888   Y8888   888       888
            888         "Y88888P"  888    Y888  "Y8888P"      8888888 888    Y888 8888888     888




    """

    def initCheckBoxCBCT(self, Method, layout, tohide: qt.QLabel):
        # self.ui.advancedCollapsibleButton.setMaximumHeight(180)
        if not tohide is None:
            tohide.setHidden(True)
        dic = Method.DicLandmark()
        # status = Method.existsLandmark('','')
        # Create a checkbox
        # self.ldmk_reg_checkbox = qt.QCheckBox()
        # self.ldmk_reg_checkbox.setText("Register Landmark")
        # self.ldmk_reg_checkbox.setEnabled(False)
        # layout.addWidget(self.ldmk_reg_checkbox)

        dicchebox = {}
        for i, (title, liste) in enumerate(dic.items()):
            Tab = QTabWidget()
            layout.addWidget(Tab)
            listcheckboxlandmark = []
            tab = self.CreateMiniTab(Tab, title, 0, len(liste))
            for struct in liste:
                checkbox = qt.QCheckBox()
                checkbox.setText(struct)
                # if struct in ['Cranial Base','Mandible','Maxilla']:
                #     checkbox.setChecked(True)
                tab.addWidget(checkbox)
                listcheckboxlandmark.append(checkbox)

            dicchebox[title] = listcheckboxlandmark

        Method.setcheckbox(dicchebox)

        Method.merge_seg_checkbox = qt.QCheckBox()
        Method.merge_seg_checkbox.setText("Merge Segmentations")
        Method.merge_seg_checkbox.setChecked(True)
        layout.addWidget(Method.merge_seg_checkbox)

    def CreateMiniTab(
        self, tabWidget: QTabWidget, name: str, index: int, numberItems=None
    ):
        new_widget = QWidget()
        # new_widget.setMinimumHeight(150)
        # new_widget.resize(tabWidget.size)
        # tabWidget.setMaximumHeight(10)
        if numberItems is not None:
            tabWidget.setMinimumHeight(46 * numberItems)

        layout = QGridLayout(new_widget)

        scr_box = QScrollArea(new_widget)
        # scr_box.setMaximumHeight(100)
        # scr_box.resize(tabWidget.size)

        layout.addWidget(scr_box, 0, 0)

        new_widget2 = QWidget(scr_box)
        layout2 = QVBoxLayout(new_widget2)

        scr_box.setWidgetResizable(True)
        scr_box.setWidget(new_widget2)

        tabWidget.insertTab(index, new_widget, name)

        return layout2

    def HideComputeItems(self, run=False):
        self.ui.ButtonOriented.setVisible(not run)

        self.ui.ButtonCancel.setVisible(run)

        self.ui.LabelProgressPatient.setVisible(run)
        self.ui.LabelProgressExtension.setVisible(run)
        self.ui.LabelNameExtension.setVisible(run)
        self.ui.progressBar.setVisible(run)

        self.ui.LabelTimer.setVisible(run)

    def initCheckboxIOS(self, tohide):
        if not tohide is None:
            tohide.hide()

    """
                          .d88888b.  88888888888 888    888 8888888888 8888888b.   .d8888b.
                         d88P" "Y88b     888     888    888 888        888   Y88b d88P  Y88b
                         888     888     888     888    888 888        888    888 Y88b.
                         888     888     888     8888888888 8888888    888   d88P  "Y888b.
                         888     888     888     888    888 888        8888888P"      "Y88b.
                         888     888     888     888    888 888        888 T88b         "888
                         Y88b. .d88P     888     888    888 888        888  T88b  Y88b  d88P
                          "Y88888P"      888     888    888 8888888888 888   T88b  "Y8888P"
    """

    def check_lib_wsl(self)->bool:
        '''
        Check if wsl contains the require librairies
        '''
        result1 = subprocess.run("wsl -- bash -c \"dpkg -l | grep libxrender1\"", capture_output=True, text=True)
        output1 = result1.stdout.encode('utf-16-le').decode('utf-8')
        clean_output1 = output1.replace('\x00', '')

        result2 = subprocess.run("wsl -- bash -c \"dpkg -l | grep libgl1-mesa-glx\"", capture_output=True, text=True)
        output2 = result2.stdout.encode('utf-16-le').decode('utf-8')
        clean_output2 = output2.replace('\x00', '')

        return "libxrender1" in clean_output1 and "libgl1-mesa-glx" in clean_output2
  
    def check_wsl_environment(self):
            self.conda_wsl = CondaSetUpCallWsl()  
            wsl = self.conda_wsl.testWslAvailable()
            ready = True
            self.ui.label_LibsInstallation.setHidden(False)
            self.ui.label_LibsInstallation.setText(f"Checking if wsl is installed, this task may take a moments")
            slicer.app.processEvents()
            
            if wsl : # if wsl is install
              lib = self.check_lib_wsl()
              if not lib : # if lib required are not install
                  self.ui.label_LibsInstallation.setText(f"Checking if the required librairies are installed, this task may take a moments")
                  messageBox = qt.QMessageBox()
                  text = "Code can't be launch. \nWSL doen't have all the necessary libraries, please download the installer and follow the instructin here : https://github.com/DCBIA-OrthoLab/SlicerAutomatedDentalTools/releases/download/wsl2_windows/installer_wsl2.zip\nDownloading may be blocked by Chrome, this is normal, just authorize it."
                  ready = False
                  messageBox.information(None, "Information", text)
            else : # if wsl not install, ask user to install it ans stop process
              messageBox = qt.QMessageBox()
              text = "Code can't be launch. \nWSL is not installed, please download the installer and follow the instructin here : https://github.com/DCBIA-OrthoLab/SlicerAutomatedDentalTools/releases/download/wsl2_windows/installer_wsl2.zip\nDownloading may be blocked by Chrome, this is normal, just authorize it."
              ready = False
              messageBox.information(None, "Information", text)
            
            if ready : # checking if miniconda installed on wsl
              self.ui.label_LibsInstallation.setText(f"Checking if miniconda is installed")
              if "Error" in self.conda_wsl.condaRunCommand([self.conda_wsl.getCondaExecutable(),"--version"]): # if conda is setup
                    messageBox = qt.QMessageBox()
                    text = "Code can't be launch. \nConda is not setup in WSL. Please go the extension CondaSetUp in SlicerConda to do it."
                    ready = False
                    messageBox.information(None, "Information", text)
            
            if ready : # checking if environment 'shapeaxi' exist on wsl and if no ask user permission to create and install required lib in it
              self.ui.label_LibsInstallation.setText(f"Checking if environnement exist")
              name_env = "shapeaxi"     
              if not self.conda_wsl.condaTestEnv(name_env) : # check is environnement exist, if not ask user the permission to do it
                userResponse = slicer.util.confirmYesNoDisplay("The environnement to run the segmentation doesn't exist, do you want to create it ? ", windowTitle="Env doesn't exist")
                if userResponse :
                  start_time = time.time()
                  previous_time = start_time
                  self.ui.label_LibsInstallation.setText(f"Creation of the new environment. This task may take a few minutes.\ntime: 0.0s")
                  name_env = "shapeaxi"
                  process = threading.Thread(target=self.conda_wsl.condaCreateEnv, args=(name_env,"3.9",["shapeaxi"],)) #run in paralle to not block slicer
                  process.start()
                  
                  while process.is_alive():
                    slicer.app.processEvents()
                    current_time = time.time()
                    gap=current_time-previous_time
                    if gap>0.3:
                        previous_time = current_time
                        elapsed_time = current_time - start_time
                        self.ui.label_LibsInstallation.setText(f"Creation of the new environment. This task may take a few minutes.\ntime: {elapsed_time:.1f}s")
              
                  start_time = time.time()
                  previous_time = start_time
                  self.ui.label_LibsInstallation.setText(f"Installation of librairies into the new environnement. This task may take a few minutes.\ntime: 0.0s")
                  
                  name_env = "shapeaxi"
                  # result_pythonpath = self.check_pythonpath_windows(name_env,"ALI_IOS_utils.requirement") # THIS LINE IS WORKING
                  result_pythonpath = self.check_pythonpath_windows(name_env,"CrownSegmentation_utils.install_pytorch")
                  if not result_pythonpath : 
                    self.give_pythonpath_windows(name_env)
                    # result_pythonpath = self.check_pythonpath_windows(name_env,"ALI_IOS_utils.requirement") # THIS LINE IS WORKING
                    result_pythonpath = self.check_pythonpath_windows(name_env,"CrownSegmentation_utils.install_pytorch")
                    
                  if result_pythonpath : 
                    conda_exe = self.conda_wsl.getCondaExecutable()
                    path_pip = self.conda_wsl.getCondaPath()+f"/envs/{name_env}/bin/pip"
                    # command = [conda_exe, "run", "-n", name_env, "python" ,"-m", f"ALI_IOS_utils.requirement",path_pip] # THIS LINE IS WORKING
                    command = [conda_exe, "run", "-n", name_env, "python" ,"-m", f"CrownSegmentation_utils.install_pytorch",path_pip]
                    print("command : ",command)
                  
                    process = threading.Thread(target=self.conda_wsl.condaRunCommand, args=(command,)) # launch install_pythorch.py with the environnement ali_ios to install pytorch3d on it
                    process.start()
                    
                    while process.is_alive():
                      slicer.app.processEvents()
                      current_time = time.time()
                      gap=current_time-previous_time
                      if gap>0.3:
                          previous_time = current_time
                          elapsed_time = current_time - start_time
                          self.ui.label_LibsInstallation.setText(f"Installation of librairies into the new environnement. This task may take a few minutes.\ntime: {elapsed_time:.1f}s")
                          
                  ready = True
                else :
                  ready = False
                  
              if ready : #check if wsl know the path to Crownsegmentationcli and AREG_IOS. If no it's trying to give it and check again.
                print("CHECK AREG_IOS ET CROWNSEGMENTATIONCLI")
                result_pythonpath = self.check_pythonpath_windows(name_env,"CrownSegmentationcli")
                if not result_pythonpath : 
                    self.give_pythonpath_windows(name_env)
                    result_pythonpath = self.check_pythonpath_windows(name_env,"CrownSegmentationcli")
                    
                if result_pythonpath:
                    ready = True
                    print("WSL know the path to CrownSegmentationcli")
                else :
                    ready = False
                    print("WSL don't know the path to CrownSegmentationcli")
                    
                result_pythonpath = self.check_pythonpath_windows(name_env,"AREG_IOS")
                if not result_pythonpath : 
                    self.give_pythonpath_windows(name_env)
                    result_pythonpath = self.check_pythonpath_windows(name_env,"AREG_IOS")
                    
                if result_pythonpath:
                    ready = True
                    print("WSL know the path to AREG_IOS")
                else :
                    ready = False
                    print("WSL don't know the path to AREG_IOS")
                  
                

            # if not self.conda_wsl.condaTestEnv('ali_ios') : # check if the environnement ali_ios exist
            #     userResponse = slicer.util.confirmYesNoDisplay("The environnement to run the landmarks identification  doesn't exist, do you want to create it ? ", windowTitle="Env doesn't exist") # ask the persimission to create it
            #     if userResponse : #create it in parallele to not blocking slicer
                
            #         process = threading.Thread(target=self.creation_env_ali_ios_wsl, args=())
            #         process.start()
                    
            #         start_time = time.time()
            #         previous_time = start_time
            #         current_time = start_time
                    
            #         self.ui.label_LibsInstallation.setText(f"The environnement doesn't exist, creation of the environnement\ntime: : {current_time-start_time:.2f}s")

            #         while process.is_alive():
            #             slicer.app.processEvents()
            #             current_time = time.time()
            #             if current_time - previous_time > 0.3 :
            #                     previous_time = current_time
            #                     self.ui.label_LibsInstallation.setText(f"The environnement doesn't exist, creation of the environnement\ntime: : {current_time-start_time:.2f}s")

            #     else :
            #             self.ui.label_LibsInstallation.setText(f"The environnement doesn't exist, code can't be launch")
            #             ready = False        
            return ready
        
    # def creation_env_ali_ios_wsl(self):
    #     '''
    #     Create the environnement on wsl to run landmarks identification of ios files
    #     '''
    #     name_env = "ali_ios"
    #     self.conda_wsl.condaCreateEnv(name_env,'3.9')
    #     result_pythonpath = self.check_pythonpath_windows(name_env,"ALI_IOS_utils.requirement")
    #     print("result_pythonpath : ",result_pythonpath)
    #     if not result_pythonpath : 
    #         self.give_pythonpath_windows(name_env)
    #         # result_pythonpath = self.check_pythonpath_windows(name_env,"ALI_IOS_utils.requirement") # THIS LINE IS WORKING
    #         result_pythonpath = self.check_pythonpath_windows(name_env,"ALI_IOS_utils.requirement")
    #         print("result_pythonpath : ",result_pythonpath)
            
    #     if result_pythonpath : 
    #         conda_exe = self.conda_wsl.getCondaExecutable()
    #         path_pip = self.conda_wsl.getCondaPath()+f"/envs/{name_env}/bin/pip"
    #         # command = [conda_exe, "run", "-n", name_env, "python" ,"-m", f"ALI_IOS_utils.requirement",path_pip] # THIS LINE IS WORKING
    #         command = [conda_exe, "run", "-n", name_env, "python" ,"-m", f"ALI_IOS_utils.requirement",path_pip]
    #         print("command : ",command)
            
    #         result = self.conda_wsl.condaRunCommand(command)
        
    #         print("RESULT OF ALI IOS WSL REQUIREMENT : ",result)
    
   
    def check_import_wsl(self, name_env, file, class_to_import):
        conda_exe = self.conda_wsl.getCondaExecutable()
        command = [
            conda_exe, "run", "-n", name_env, "python", "-c",
            f"\"from {file} import {class_to_import}; print(\"True\")\""
        ]
        print("command:", command)
        result = self.conda_wsl.condaRunCommand(command)
        print("result =", result)
        if "Result:" in result:
            return True
        return False
            
    def check_pythonpath_windows(self,name_env,file):
        '''
        Check is wsl now a specifique path (ex : ALI_IOS_utils.requirement) in a specific environment
        return : bool
        '''
        conda_exe = self.conda_wsl.getCondaExecutable()
        command = [conda_exe, "run", "-n", name_env, "python" ,"-c", f"\"import {file} as check;import os; print(os.path.isfile(check.__file__))\""]
        print("command : ",command)
        result = self.conda_wsl.condaRunCommand(command)
        print("result = ",result)
        if "True" in result :
            return True
        return False
    
    def give_pythonpath_windows(self,name_env):
        '''
        give all the path of slicer to wsl
        '''
        paths = slicer.app.moduleManager().factoryManager().searchPaths
        mnt_paths = []
        for path in paths :
            mnt_paths.append(f"\"{self.windows_to_linux_path(path)}\"")
        pythonpath_arg = 'PYTHONPATH=' + ':'.join(mnt_paths)
        conda_exe = self.conda_wsl.getCondaExecutable()
        # print("Conda_exe : ",conda_exe)
        argument = [conda_exe, 'env', 'config', 'vars', 'set', '-n', name_env, pythonpath_arg]
        print("arguments : ",argument)
        self.conda_wsl.condaRunCommand(argument)
        
    def windows_to_linux_path(self,windows_path):
        '''
        convert a windows path to a wsl path
        '''
        windows_path = windows_path.strip()

        path = windows_path.replace('\\', '/')

        if ':' in path:
            drive, path_without_drive = path.split(':', 1)
            path = "/mnt/" + drive.lower() + path_without_drive

        return path

    def cleanup(self):
        """
        Called when the application closes and the module widget is destroyed.
        """
        if self.logic.cliNode is not None:
            # if self.logic.cliNode.GetStatus() & self.logic.cliNode.Running:
            self.logic.cliNode.Cancel()

        self.removeObservers()

    def enter(self):
        """
        Called each time the user opens this module.
        """
        # Make sure parameter node exists and observed
        self.initializeParameterNode()

    def exit(self):
        """
        Called each time the user opens a different module.
        """
        # Do not react to parameter node changes (GUI wlil be updated when the user enters into the module)
        self.removeObserver(
            self._parameterNode,
            vtk.vtkCommand.ModifiedEvent,
            self.updateGUIFromParameterNode,
        )

    def onSceneStartClose(self, caller, event):
        """
        Called just before the scene is closed.
        """
        # Parameter node will be reset, do not use it anymore
        self.setParameterNode(None)

    def onSceneEndClose(self, caller, event):
        """
        Called just after the scene is closed.
        """
        # If this module is shown while the scene is closed then recreate a new parameter node immediately
        if self.parent.isEntered:
            self.initializeParameterNode()

    def initializeParameterNode(self):
        """
        Ensure parameter node exists and observed.
        """
        # Parameter node stores all user choices in parameter values, node selections, etc.
        # so that when the scene is saved and reloaded, these settings are restored.

    def setParameterNode(self, inputParameterNode):
        """
        Set and observe parameter node.
        Observation is needed because when the parameter node is changed then the GUI must be updated immediately.
        """

        # if inputParameterNode:
        self.setParameterNode(self.logic.getParameterNode())

        # Unobserve previously selected parameter node and add an observer to the newly selected.
        # Changes of parameter node are observed so that whenever parameters are changed by a script or any other module
        # those are reflected immediately in the GUI.
        if self._parameterNode is not None:
            self.removeObserver(
                self._parameterNode,
                vtk.vtkCommand.ModifiedEvent,
                self.updateGUIFromParameterNode,
            )
        self._parameterNode = inputParameterNode
        if self._parameterNode is not None:
            self.addObserver(
                self._parameterNode,
                vtk.vtkCommand.ModifiedEvent,
                self.updateGUIFromParameterNode,
            )

        # Initial GUI update
        self.updateGUIFromParameterNode()

    def updateGUIFromParameterNode(self, caller=None, event=None):
        """
        This method is called whenever parameter node is changed.
        The module GUI is updated to show the current state of the parameter node.
        """

        if self._parameterNode is None or self._updatingGUIFromParameterNode:
            return

        # Make sure GUI changes do not call updateParameterNodeFromGUI (it could cause infinite loop)
        self._updatingGUIFromParameterNode = True

        # Update node selectors and sliders
        self.ui.inputSelector.setCurrentNode(
            self._parameterNode.GetNodeReference("InputVolume")
        )
        self.ui.outputSelector.setCurrentNode(
            self._parameterNode.GetNodeReference("OutputVolume")
        )
        self.ui.invertedOutputSelector.setCurrentNode(
            self._parameterNode.GetNodeReference("OutputVolumeInverse")
        )
        # self.ui.imageThresholdSliderWidget.value = float(self._parameterNode.GetParameter("Threshold"))
        self.ui.invertOutputCheckBox.checked = (
            self._parameterNode.GetParameter("Invert") == "true"
        )

        # Update buttons states and tooltips
        # if self._parameterNode.GetNodeReference("InputVolume") and self._parameterNode.GetNodeReference("OutputVolume"):
        #   self.ui.applyButton.toolTip = "Compute output volume"
        #   self.ui.applyButton.enabled = True
        # else:
        #   self.ui.applyButton.toolTip = "Select input and output volume nodes"
        #   self.ui.applyButton.enabled = False

        # All the GUI updates are done
        self._updatingGUIFromParameterNode = False

    def updateParameterNodeFromGUI(self, caller=None, event=None):
        """
        This method is called when the user makes any change in the GUI.
        The changes are saved into the parameter node (so that they are restored when the scene is saved and loaded).
        """

        if self._parameterNode is None or self._updatingGUIFromParameterNode:
            return

        wasModified = (
            self._parameterNode.StartModify()
        )  # Modify all properties in a single batch

        self._parameterNode.SetNodeReferenceID(
            "InputVolume", self.ui.inputSelector.currentNodeID
        )
        self._parameterNode.SetNodeReferenceID(
            "OutputVolume", self.ui.outputSelector.currentNodeID
        )
        # self._parameterNode.SetParameter("Threshold", str(self.ui.imageThresholdSliderWidget.value))
        self._parameterNode.SetParameter(
            "Invert", "true" if self.ui.invertOutputCheckBox.checked else "false"
        )
        self._parameterNode.SetNodeReferenceID(
            "OutputVolumeInverse", self.ui.invertedOutputSelector.currentNodeID
        )

        self._parameterNode.EndModify(wasModified)


class AREGLogic(ScriptedLoadableModuleLogic):
    """This class should implement all the actual
    computation done by your module.  The interface
    should be such that other python code can import
    this class and make use of the functionality without
    requiring an instance of the Widget.
    Uses ScriptedLoadableModuleLogic base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self):
        """
        Called when the logic class is instantiated. Can be used for initializing member variables.
        """
        ScriptedLoadableModuleLogic.__init__(self)

        self.cliNode = None

    def process(self, parameters):
        """
        Run the processing algorithm.
        Can be used without GUI widget.
        :param inputVolume: volume to be thresholded

        """

        # import time
        # startTime = time.time()

        logging.info("Processing started")

        PredictProcess = slicer.modules.aso_ios

        self.cliNode = slicer.cli.run(PredictProcess, None, parameters)

        return PredictProcess

    def iterillimeted(self, iter):
        out = []
        if isinstance(iter, dict):
            iter = list(iter.values())

        for thing in iter:
            if isinstance(thing, (dict, list, set)):
                out += self.iterillimeted(thing)
            else:
                out.append(thing)

        return out
