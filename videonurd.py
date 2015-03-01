#!/usr/bin/env python
import sys
import os
import re
from PyQt4 import QtGui
from PyQt4 import QtCore
from PyQt4.phonon import Phonon
from time import sleep
import MainWindow
import logging
import random

logging.basicConfig(format='%(levelname)s:%(message)s',level=logging.DEBUG)
logging.debug("Started")

try:
    _fromUtf8 = QtCore.QString.fromUtf8
except AttributeError:
    def _fromUtf8(s):
        return s


class FakeIO(object):
	
	def __init__(self,output,streamType,fileStartSignal,fileProgressSignal,fileCompleteSignal):
		self.output = output
		self.streamType = streamType
		
		self.fileStartSignal    = fileStartSignal
		self.fileProgressSignal = fileProgressSignal
		self.fileCompleteSignal = fileCompleteSignal
		self.lastFile = ''
		self.startMatcher      = re.compile("Writing video (.*)")
		self.progressMatcher   = re.compile("(\d*)/(\d*)\s*(\d*)%\s*\[elapsed:\s(\d\d:\d\d)\sleft:\s(\d\d:\d\d)")
		self.completionMatcher = re.compile("\[MoviePy\] >* Video ready: (.*)")
	

	def write(self,data):
		
		self.output.emit(self.streamType,data)
		for match in self.startMatcher.findall(data):
			self.lastFile = match
			self.fileStartSignal.emit( match[0] )

		for match in self.progressMatcher.findall(data):
			self.fileProgressSignal.emit( self.lastFile, int(match[2]),match[3],match[4] )

		for match in self.completionMatcher.findall(data):
			self.fileCompleteSignal.emit( match )
	def flush(self):
		pass

class MovieWorker(QtCore.QObject):
	statusUpdate = QtCore.pyqtSignal(str,str)
	started      = QtCore.pyqtSignal()
	complete     = QtCore.pyqtSignal()

	fileStart    = QtCore.pyqtSignal(str)
	fileProgress = QtCore.pyqtSignal(str,int,str,str)
	fileComplete = QtCore.pyqtSignal(str)

	mutex 	     = QtCore.QMutex()

	@QtCore.pyqtSlot(list)
	def processClipQueue(self,commandQueue):
		tempio_out = sys.stdout
		tempio_err = sys.stderr
		
		fakeIO = FakeIO(self.statusUpdate,'out',self.fileStart,self.fileProgress,self.fileComplete)
		sys.stdout = fakeIO
		sys.stderr = fakeIO
		from moviepy.editor import VideoFileClip,CompositeVideoClip,concatenate
		self.started.emit()
		
		os.path.exists('outFiles') or os.mkdir('outFiles')

		for e in commandQueue:
			workingDir = os.getcwd()
			print ' '.join([ "Starting ",e['trans']," transformation on",str(len(e['files'])),"files" ])
			if e['trans'] == "Direct output":
				for fn in e['files']:
					fn['filename'] = unicode(fn['filename'])
					print ' '.join([ 'Starting file',fn['filename'] ])
					outfilename = None
					fpass = 0
					orig = os.path.split( fn['filename'] )[-1]
					while outfilename is None:
						fpass += 1
						possible = os.path.join( workingDir,'outFiles', '_'.join([   os.path.split(fn['filename'])[-1]  , str(fpass).zfill(5), ] )+e['outputFormat'] )
						if not os.path.exists(possible):
							outfilename = possible

					v = VideoFileClip(fn['filename'])
					v = v.subclip( fn['timeStart'],fn['timeEnd'])
					v = v.crop( y1=fn['top'], x1=fn['left'], y2=fn['bottom'], x2=fn['right'])

					if e['widthMode'] == "Always Resize" or (e['widthMode'] == "Only Shrink" and v.w > e["outputWidth"] ) or (e['widthMode'] == "Only Enlarge" and v.w < e["outputWidth"] ):
						v = v.resize(width=int(e["outputWidth"]))


					v.write_videofile(outfilename,fps=e['frameRate'],bitrate= str(round(e['bitRateKb']/1000.0,4))+'M')

					print "Saved as: "+outfilename#+' ['+str(round(os.stat(outfilename).st_size/1024.0/1024,2))+'MB]'
			elif e['trans'] == "Join":
				outvideo = [] 
				for fn in e['files']:
					fn['filename'] = unicode(fn['filename'])
					outfilename = None
					fpass = 0
					orig = os.path.split( fn['filename'] )[-1]
					while outfilename is None:
						fpass += 1
						possible = os.path.join( workingDir,'outFiles', '_'.join([   "Joined", 
													     str(len(e['files'])), 
													     "files_output"  , 
													     str(fpass).zfill(5), 
													 ] )+e['outputFormat'] )
						if not os.path.exists(possible):
							outfilename = possible

					v = VideoFileClip(fn['filename'])
					v = v.subclip( fn['timeStart'],fn['timeEnd'])
					v = v.crop( y1=fn['top'], x1=fn['left'], y2=fn['bottom'], x2=fn['right'])
					
					if e['widthMode'] == "Always Resize" or (e['widthMode'] == "Only Shrink" and v.w > e["outputWidth"] ) or (e['widthMode'] == "Only Enlarge" and v.w < e["outputWidth"] ):
						v = v.resize(width=int(e["outputWidth"]))


					outvideo.append(v)
	
				concatenate(outvideo).write_videofile(outfilename,fps=e['frameRate'],bitrate= str(round(e['bitRateKb']/1000.0,4))+'M')
				print "Saved as: "+outfilename#+' ['+str(round(os.stat(outfilename).st_size/1024.0/1024,2))+'MB]'
			elif e['trans'] == "Slice":
				for fn in e['files']:
					fn['filename'] = unicode(fn['filename'])
					print fn['filename']
					v = VideoFileClip(fn['filename'])
					v = v.subclip( fn['timeStart'],fn['timeEnd'])
					v = v.crop( y1=fn['top'], x1=fn['left'], y2=fn['bottom'], x2=fn['right'])
					if e['widthMode'] == "Always Resize" or (e['widthMode'] == "Only Shrink" and v.w > e["outputWidth"] ) or (e['widthMode'] == "Only Enlarge" and v.w < e["outputWidth"] ):
						v = v.resize(width=int(e["outputWidth"]))
					targetRanges = []
					for i in xrange(0,int(v.duration),e['maximumSliceDuration']):
						end = i+e['maximumSliceDuration']
						if end > v.duration:
							end = v.duration
						targetRanges.append( (v.subclip(i, end ),i,end)  )
					if e['sliceDiscardMethod'] == 'Choose slices at random':
						random.shuffle(targetRanges)
					elif e['sliceDiscardMethod'] == 'Prefer slices from the start of each clip':
						pass
					elif e['sliceDiscardMethod'] == 'Prefer slices from the end of each clip':
						targetRanges = targetRanges[::-1]
					targetRanges = targetRanges[:e['maximumSliceCount']]

					for video,start,end in targetRanges:
						outfilename = None
						fpass = 0
						orig = os.path.split( fn['filename'] )[-1]
						while outfilename is None:
							fpass += 1
							possible = os.path.join( workingDir,'outFiles', '_'.join([   orig,
														     str(fpass).zfill(5), 
														     str(start),str(end) 
														 ] )+e['outputFormat'] )
							if not os.path.exists(possible):
								outfilename = possible
								print "Generating",outfilename,start,end
						video.write_videofile(outfilename,fps=e['frameRate'],bitrate= str(round(e['bitRateKb']/1000.0,4))+'M')
						print "Saved as: "+outfilename#+' ['+str(round(os.stat(outfilename).st_size/1024.0/1024,2))+'MB]'
			elif e['trans'] == "SuperCut":
				outvideo = []
				for fn in e['files']:
					v = VideoFileClip(fn['filename'])
					v = v.subclip( fn['timeStart'],fn['timeEnd'])
					v = v.crop( y1=fn['top'], x1=fn['left'], y2=fn['bottom'], x2=fn['right'])
					if e['widthMode'] == "Always Resize" or (e['widthMode'] == "Only Shrink" and v.w > e["outputWidth"] ) or (e['widthMode'] == "Only Enlarge" and v.w < e["outputWidth"] ):
						v = v.resize(width=int(e["outputWidth"]))
					clipped = set()
					for i in xrange(0,e['superCutsPerFile']):
						for i in xrange(20): 
							s = random.randint(0,int(int(v.duration)-e['superCutDuration']))
							if s not in clipped:
								clipped.add(s)
								break
						outvideo.append( v.subclip(s,s+e['superCutDuration']) )
				outfilename = None
				fpass = 0
				orig = os.path.split( fn['filename'] )[-1]
				while outfilename is None:
					fpass += 1
					possible = os.path.join( workingDir,'outFiles', '_'.join([   'Supercut', 
												      str(fpass).zfill(5),
												 ] )+e['outputFormat'] )
					if not os.path.exists(possible):
						outfilename = possible
				random.shuffle(outvideo)
				concatenate(outvideo).write_videofile(outfilename,fps=e['frameRate'],bitrate= str(round(e['bitRateKb']/1000.0,4))+'M')
	
			elif e['trans'] == "VideoWall":
				pass

		self.complete.emit()

		sys.stdout = tempio_out 
		sys.stderr = tempio_err 

class Worker(QtCore.QObject):
	finished  = QtCore.pyqtSignal()
    	dataReady = QtCore.pyqtSignal(list)
	ioerror   = QtCore.pyqtSignal(list)

	@QtCore.pyqtSlot(str)
    	def processFolder(self,newFile):
		from moviepy.editor import VideoFileClip
		v = None
		import glob
		import mimetypes
		depth = 3
		root = str(newFile)
		fnl = []
		for i in xrange(0,depth):
			if root[-1] == os.sep:
				root += '*'
			else:
				root += os.sep+'*'
			print "Adding from", root
			count = 0
			for f in glob.glob(root):
				if os.path.isfile(f):
					mg = mimetypes.guess_type(f)
					if mg[0] is not None and 'video' in mg[0]:
						try:
							v = VideoFileClip(unicode(f))
							self.dataReady.emit([f,v.duration,v.size])
						except IOError as e:
							self.ioerror.emit([f])
						except AttributeError as e:
							self.ioerror.emit([f])
						
						del v

	@QtCore.pyqtSlot(str)
    	def processB(self,newFile):
		from moviepy.editor import VideoFileClip
		v = None

		try:
			v = VideoFileClip(unicode(newFile))
			self.dataReady.emit([newFile,v.duration,v.size])
		except IOError as e:
			self.ioerror.emit([newFile])
		except AttributeError as e:
			self.ioerror.emit([newFile])
		
		del v
        	#self.finished.emit()

class IOMoviePyChecker(object):
	
	def __init__(self,messageSignal):
		self.messageSignal = messageSignal

	def write(self,data):
		self.messageSignal.emit(data.strip())

	def flush(self):
		pass

class MoviePyChecker(QtCore.QObject):
	message = QtCore.pyqtSignal(str)
	finished = QtCore.pyqtSignal()

	@QtCore.pyqtSlot()
	def check(self):
		
		t_stdout = sys.stdout
		t_stderr = sys.stderr 
	
		sys.stdout = IOMoviePyChecker(self.message)
		sys.stderr = IOMoviePyChecker(self.message)
		print "",
		sys.stdout.write("...Checking MoviePy dependencies")
		from moviepy.editor import VideoFileClip
		sys.stdout.write("...Check complete")
		
		sys.stdout = t_stdout
		sys.stderr = t_stderr  
		self.finished.emit()

	

class MyMainWindow(QtGui.QMainWindow):

	def closeEvent(self,evt):
		self.obj.finished.emit()
		self.thread.wait(2000)
		
		self.movieThread.exit()
		self.movieThread.wait(2000)
		evt.accept()
	
	def movieStatus(self,source,message):
		msg = unicode(message)
		if msg.strip() != '' and (not msg.startswith('[MoviePy')) and ('elapsed' not in msg):
			self.ui.plainTextEdit.appendPlainText(unicode(message).strip())

	def moviePyCheckerIO(self,message):
		if "..." not in unicode(message) and len(message) > 4:
			self.ui.tabWidget.setCurrentIndex(2)
		self.ui.plainTextEdit.appendPlainText(unicode(message).strip())

	def movieStart(self,evt):
		currentTrans = str(self.ui.comboBoxTransformationType.currentText().split('-')[0]).strip()

		jobDef = {	
				'trans':currentTrans,
				'files':[],
				"outputWidth":self.ui.spinBoxOutputWidth.value(),
				"widthMode":str(self.ui.comboBoxWidthMode.currentText()),
				"bitRateKb":self.ui.doubleSpinBoxBitRateKB.value(),
				"frameRate":self.ui.spinBoxFrameRate.value(),
				"outputFormat":str(self.ui.comboBoxOutputFormat.currentText()),

				"maximumSliceDuration":self.ui.spinBoxSliceDuration.value(),
				"maximumSliceCount":self.ui.spinBoxMaxSlicePerVideo.value(),
				"sliceDiscardMethod":str(self.ui.comboBoxSliceDiscardMethod.currentText()),
				
				"superCutDuration":self.ui.doubleSpinBoxSuperCutCutDuration.value(),
				"superCutsPerFile":self.ui.spinBoxSuperCutsPerFile.value(),
				"superCutAspectRatioMode":str(self.ui.comboBoxSuperCutAspectRatioMode.currentText()),
				"superCutFileName":str(self.ui.comboBoxSuperCutFileNameStamp.currentText()),
				
				"wallWidth":self.ui.spinBoxVideoWallWidth.value(),
				"wallHeight":self.ui.spinBoxVideoWallHeight.value(),
				"wallDurationMatching":str(self.ui.comboBoxWallDurationMatching.currentText()),
				"wallAspectRatio":str(self.ui.comboBoxWallAspectRatioMode.currentText())


							
			}

		if currentTrans == "Direct output":
			pass
		elif currentTrans == "Join":
			pass
		elif currentTrans == "Slice":
			pass
		elif currentTrans == "SuperCut":
			pass
		elif currentTrans == "VideoWall":
			pass
		
		for i in xrange(self.ui.listWidgetFileListing.count()):
			c = self.ui.listWidgetFileListing.item(i)
			job = {
					'timeStart':c.timeSliceStart,
					'timeEnd':c.timeSliceEnd,
					'filename':unicode(c.fileName),
					'top':c.cropTop,
					'left':c.cropLeft,
					'bottom':c.cropBottom,
					'right':c.cropRight
				}
			jobDef['files'].append(job)

		QtCore.QMetaObject.invokeMethod(self.movieObj, 'processClipQueue', QtCore.Qt.QueuedConnection,QtCore.Q_ARG(list, [jobDef]))

	def progressStart(self,filename):
		self.ui.labelProgress.setText('Status Starting processing  of '+filename   )
		self.ui.progressBar.setValue(0)
	
	def progressUpdate(self,filename,percent,elapsed,remaining):
		self.ui.labelProgress.setText('Status Processing '+filename+', time elapsed:'+elapsed+' reamining:'+remaining   )
		self.ui.progressBar.setValue(percent)
	
	def progressComplete(self,filename):
		self.ui.labelProgress.setText('Comeplete saved as '+filename  )
		self.ui.progressBar.setValue(100)

	def __init__(self,parent=None):
		super(MyMainWindow, self).__init__(parent)
		self.ui = MainWindow.Ui_MainWindow()
		self.ui.setupUi(self)
		
		import glob
		for tempFile in glob.glob("*TEMP*.ogg"):
			os.remove(tempFile)		


		self.moviePyCheckerThread = QtCore.QThread()
		self.moviePyChecker = MoviePyChecker()
		self.moviePyChecker.finished.connect(self.moviePyCheckerThread.exit)
		self.moviePyCheckerThread.started.connect(self.moviePyChecker.check)
		self.moviePyChecker.message.connect(self.moviePyCheckerIO)
		self.moviePyChecker.moveToThread(self.moviePyCheckerThread)
		self.moviePyCheckerThread.start()
		

		self.movieThread = QtCore.QThread()
		self.movieObj = MovieWorker()

		self.movieObj.statusUpdate.connect(self.movieStatus)
		self.movieObj.fileProgress.connect(self.progressUpdate)	
		self.movieObj.fileStart.connect(self.progressStart)
		self.movieObj.fileComplete.connect(self.progressComplete)	

		self.movieObj.moveToThread(self.movieThread)
		#self.movieObj.complete.connect(self.movieThread.exit)
		self.movieThread.start()		
		self.ui.buttonProcess.clicked.connect(self.movieStart)

		self.thread = QtCore.QThread() 
		self.obj = Worker()
		self.obj.dataReady.connect(self.tprint)
		self.obj.moveToThread(self.thread)
		self.obj.finished.connect(self.thread.exit)
		self.thread.start()

		#Phonon Shit
		placeholderParent = self.ui.phonon.parent()
		self.ui.phonon.setParent(None)
		self.ui.phonon = Phonon.VideoWidget(placeholderParent)
        	self.ui.phonon.setObjectName(_fromUtf8("phonon"))
		self.ui.phonon.setMinimumSize(QtCore.QSize(10, 10))
        	sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Ignored, QtGui.QSizePolicy.Ignored)
        	sizePolicy.setHorizontalStretch(0)
        	sizePolicy.setVerticalStretch(0)
        	sizePolicy.setHeightForWidth(self.ui.phonon.sizePolicy().hasHeightForWidth())
        	self.ui.phonon.setSizePolicy(sizePolicy)
        	self.ui.horizontalLayout_5.addWidget(self.ui.phonon)

		#self.cropmask = QtGui.QRegion(200,200,200,200,QtGui.QRegion.Rectangle)
		#self.ui.phonon.setMask(self.cropmask)

		self.media_obj = Phonon.MediaObject()
		self.media_obj.currentfileName = None
		Phonon.createPath(self.media_obj, self.ui.phonon)
		self.destroyed.connect( self.media_obj.clear )

		self.media_obj.ab_mode = True

		self.audio_out = Phonon.AudioOutput(Phonon.VideoCategory)
		Phonon.createPath(self.media_obj, self.audio_out)
		self.audio_out.setMuted(1)
		self.ui.buttonMute.setText("Unmute")

		self.ui.buttonPlayPause.clicked.connect(self.playpause)

		#Phonon Shit

		self.ui.tabWidget.currentChanged.connect(self.leavePlayerTab)

		self.ui.buttonOpenFile.clicked.connect(self.addNewFile)
		self.ui.buttonImportFolder.clicked.connect(self.addNewFolder)

		self.ui.buttonMute.clicked.connect(self.toggleMute)

		self.ui.buttonSetStart.clicked.connect(self.setStart)
		self.ui.buttonSetEnd.clicked.connect(self.setEnd)

		self.ui.doubleSpinBoxSectionStart.valueChanged.connect(self.videoRangeUpdated)
		self.ui.doubleSpinBoxSectionEnd.valueChanged.connect(self.videoRangeUpdated)

		self.ui.spinBoxCropTop.valueChanged.connect(self.setCrop_Top)
		self.ui.spinBoxCropLeft.valueChanged.connect(self.setCrop_Left)
		self.ui.spinBoxCropBottom.valueChanged.connect(self.setCrop_Bottom)
		self.ui.spinBoxCropRight.valueChanged.connect(self.setCrop_Right)

		self.ui.listWidgetFileListing.itemSelectionChanged.connect(self.loadPreview)

		self.media_obj.totalTimeChanged.connect( self.setSliderMax )
		self.ui.horizontalSliderSeek.valueChanged.connect(self.setSeek)
		self.media_obj.setTickInterval(200)
		self.media_obj.tick.connect(self.updateVideoTick)

		self.ui.buttonSeekForward.clicked.connect(self.seekForwards)
		self.ui.buttonSeekBack.clicked.connect(self.seekBackwards)
	
		#self.p = QtGui.QProgressDialog("Checking for MoviePy dependencies","Skip",0,2,parent=self)
		#self.p.exec_()
	
	def seekForwards(self,evt):
		self.media_obj.seek( self.media_obj.currentTime() + 500  )

	def seekBackwards(self,evt):
		self.media_obj.seek( self.media_obj.currentTime() - 500  )

	def cropUpdated(self,evt):
		selected = self.ui.listWidgetFileListing.selectedItems()
		if len(selected) > 0:
			selected = selected[0]

	def setStart(self,evt):
		self.ui.doubleSpinBoxSectionStart.setValue( self.media_obj.currentTime()/1000.0 )
	
	def setEnd(self,evt):
		self.ui.doubleSpinBoxSectionEnd.setValue( self.media_obj.currentTime()/1000.0 )

	def setSliderMax(self,maximum):
		self.ui.horizontalSliderSeek.setMaximum(maximum/500.0)

	def videoRangeUpdated(self,evt):
		phononSize = self.ui.phonon.size()
		selected = self.ui.listWidgetFileListing.selectedItems()
		if len(selected) > 0:
			selected = selected[0]
			print selected

			selected.timeSliceStart = self.ui.doubleSpinBoxSectionStart.value()
			selected.timeSliceEnd   = self.ui.doubleSpinBoxSectionEnd.value()

	
	def leavePlayerTab(self,event):
		self.media_obj.pause()


	def updateVideoTick(self,tick):
		self.ui.CurrentPosition.setText( str(round(tick/1000.0,3))   )
		self.ui.horizontalSliderSeek.blockSignals(1)
		self.ui.horizontalSliderSeek.setValue(tick/500.0)
		self.ui.horizontalSliderSeek.blockSignals(0)

		if self.media_obj.ab_mode:
			if tick/1000 > self.ui.doubleSpinBoxSectionEnd.value():
				self.media_obj.seek(self.ui.doubleSpinBoxSectionStart.value()*1000.0)
			if tick/1000 < self.ui.doubleSpinBoxSectionStart.value()-1:
				self.media_obj.seek(self.ui.doubleSpinBoxSectionStart.value()*1000.0)

		selected = self.ui.listWidgetFileListing.selectedItems()
		if len(selected) < 1:
			return
		else:
			selected = selected[0]
		
			w1 = self.ui.phonon.width()+0.0
			h1 = self.ui.phonon.height()+0.0
			w2 = selected.width+0.0
			h2 = selected.height+0.0
			
			fatness1 = w1 / h1
			fatness2 = w2 / h2
		
			if fatness2 >= fatness1:
			    #scale for a snug width
			    scaleRatio = w1 / w2
			else:
			    #scale for a snug height
			    scaleRatio = h1 / h2
			w3 = w2 * scaleRatio
			h3 = h2 * scaleRatio
			x3 = (w3 / 2)
			y3 = (h3 / 2)
			
			xCenterOf1 = (w1 / 2)
			yCenterOf1 = (h1 / 2)

			x3 = xCenterOf1 - (w3 / 2)
			y3 = yCenterOf1 - (h3 / 2)



			self.ui.phonon.setMask( 
					QtGui.QRegion( 	
						x3+(self.ui.spinBoxCropLeft.value()*scaleRatio),
						y3+(self.ui.spinBoxCropTop.value()*scaleRatio),
						self.ui.spinBoxCropRight.value()*scaleRatio-(self.ui.spinBoxCropLeft.value()*scaleRatio),
						(self.ui.spinBoxCropBottom.value()*scaleRatio)-(self.ui.spinBoxCropTop.value()*scaleRatio)
						) 
					)
				

	def setSeek(self,time):
		if self.media_obj.isSeekable():
			self.media_obj.seek(time*500.0)

	def toggleMute(self):
		if self.audio_out.isMuted():
			self.audio_out.setMuted(0)
			self.ui.buttonMute.setDown(0)
			self.ui.buttonMute.setText("Mute")
		else:
			self.audio_out.setMuted(1)
			self.ui.buttonMute.setDown(1)
			self.ui.buttonMute.setText("Unmute")

	def playpause(self):
		if self.media_obj.state() in [4,1]:
			self.media_obj.play()
		else:
			self.media_obj.pause()
	
	def tprint(self,fileProps):
		print fileProps
		fileName = fileProps[0]
		newItem  = QtGui.QListWidgetItem(fileName.split(os.sep)[-1])

		newItem.fileName = fileName

		newItem.timeSliceStart = 0.0
		newItem.timeSliceEnd   = fileProps[1]
		newItem.duration       = fileProps[1]

		newItem.width          = fileProps[2][0]
		newItem.height         = fileProps[2][1]
		newItem.cropTop	       = 0
		newItem.cropLeft       = 0
		newItem.cropBottom     = fileProps[2][1]
		newItem.cropRight      = fileProps[2][0]

		self.ui.listWidgetFileListing.addItem(newItem)

	def setCrop_Top(self,value):
		selected = self.ui.listWidgetFileListing.selectedItems()
		if len(selected) > 0:
			selected[0].cropTop = value
	def setCrop_Left(self,value):
		selected = self.ui.listWidgetFileListing.selectedItems()
		if len(selected) > 0:
			selected[0].cropLeft = value
	def setCrop_Bottom(self,value):
		selected = self.ui.listWidgetFileListing.selectedItems()
		if len(selected) > 0:
			selected[0].cropBottom = value
	def setCrop_Right(self,value):
		selected = self.ui.listWidgetFileListing.selectedItems()
		if len(selected) > 0:
			selected[0].cropRight = value
		
	
	def loadPreview(self):
		selected = self.ui.listWidgetFileListing.selectedItems()
		if len(selected) > 0:
			self.ui.widget.setEnabled(1)	
			current = selected[0]
			self.media_obj.stop()
			self.media_obj.clear()
			self.media_src = Phonon.MediaSource(current.fileName)
			self.media_obj.fileName = current.fileName

			self.ui.labelPreviewTitle.setText( current.fileName )
			
			self.ui.doubleSpinBoxSectionEnd.blockSignals(1)
			self.ui.doubleSpinBoxSectionStart.blockSignals(1)

			self.ui.doubleSpinBoxSectionStart.setMaximum( current.duration )
			self.ui.doubleSpinBoxSectionEnd.setMaximum( current.duration )
	
			self.ui.doubleSpinBoxSectionEnd.setValue( current.timeSliceEnd )
			self.ui.doubleSpinBoxSectionStart.setValue( current.timeSliceStart )
		
			
			self.ui.doubleSpinBoxSectionStart.blockSignals(0)
			self.ui.doubleSpinBoxSectionEnd.blockSignals(0)


			self.ui.spinBoxCropTop.blockSignals(1)
			self.ui.spinBoxCropLeft.blockSignals(1)
			self.ui.spinBoxCropBottom.blockSignals(1)
			self.ui.spinBoxCropRight.blockSignals(1)

			self.ui.spinBoxCropTop.setMaximum(current.height)
			self.ui.spinBoxCropTop.setValue(current.cropTop)

			self.ui.spinBoxCropLeft.setMaximum(current.width)
			self.ui.spinBoxCropLeft.setValue(current.cropLeft)

			self.ui.spinBoxCropBottom.setMaximum(current.height)
			self.ui.spinBoxCropBottom.setValue(current.cropBottom)
			
			self.ui.spinBoxCropRight.setMaximum(current.width)
			self.ui.spinBoxCropRight.setValue(current.cropRight)

			self.ui.spinBoxCropTop.blockSignals(0)
			self.ui.spinBoxCropLeft.blockSignals(0)
			self.ui.spinBoxCropBottom.blockSignals(0)
			self.ui.spinBoxCropRight.blockSignals(0)

			self.media_obj.setCurrentSource(self.media_src)
			self.media_obj.play()
			self.media_obj.seek(current.timeSliceStart*1000.0)
		else:
			self.ui.widget.setEnabled(0)
			self.media_obj.clear()

	def processNewFiles(self,newFiles):
		for name in newFiles:
			QtCore.QMetaObject.invokeMethod(self.obj, 'processB', QtCore.Qt.QueuedConnection,QtCore.Q_ARG(str, name))
	
	def processNewFolder(self,newFiles):
		for name in newFiles:
			QtCore.QMetaObject.invokeMethod(self.obj, 'processFolder', QtCore.Qt.QueuedConnection,QtCore.Q_ARG(str, name))
		
	def addNewFile(self):
		self.fileDialog = QtGui.QFileDialog()
		self.fileDialog.setFileMode( QtGui.QFileDialog.ExistingFiles )
		self.fileDialog.filesSelected.connect(self.processNewFiles)
		self.fileDialog.show()
	
	def addNewFolder(self):
		self.fileDialog = QtGui.QFileDialog()
		self.fileDialog.setFileMode( QtGui.QFileDialog.Directory )
		self.fileDialog.filesSelected.connect(self.processNewFolder)
		self.fileDialog.show()

if __name__ == "__main__":
	app = QtGui.QApplication(sys.argv)
	self = MyMainWindow()
	self.show()
	
	sys.exit(app.exec_())

