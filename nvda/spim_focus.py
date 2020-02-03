#brailleDisplayDrivers/freedomScientific-SPIM.py
#A part of NonVisual Desktop Access (NVDA)
#This file is covered by the GNU General Public License.
#See the file COPYING for more details.
#Copyright (C) 2008-2011 Michael Curran <mick@kulgan.net>, James Teh <jamie@jantrid.net>

# SPIM Braille Additions (C) 2013 Flint Million <flint.million@mnsu.edu> 
# Minnesota State University-Mankato

# SPIM Braille is an interface to allow software (NVDA scripts) to directly control 
# the Braille Display, displaying blocks of 32-bit hex digits in sections of the 
# display.

# This driver duplicates the function of the freedomScientific driver, but adds
# the ability to do this control of the display.

from ctypes import *
from ctypes.wintypes import *
from collections import OrderedDict
import itertools
import hwPortUtils
import braille
import inputCore
from baseObject import ScriptableObject
from winUser import WNDCLASSEXW, WNDPROC, LRESULT, HCURSOR
from logHandler import log
import brailleInput

#ADDED (fmillion) Bring in the SPIM Braille support
import SPIMBraille

import re, socket

#ADDED(fmillion) ---UDP DEBUGGER---

# This flag will enable or disable UDP debgging of SPIM Braille.
# The UDP debugger is a separate Python script. 
# In ALL enduser cases, this should be OFF.
enableUdp = False

# Stores socket for local use
udpSock = None

# Debug function - has to go here so it's defined first.
def _spimDebug(st,warn=False):

	# If we are using the UDP debugger, send the message to the UDP socket.
	global udpSock
	global enableUdp
	if (enableUdp == True):
		try:
			if (warn == True):
				log.warn(st)
			udpSock.sendto(st, ('127.0.0.1',6287))
		except:
			# If we got some kind of error logging to UDP, stop using UDP and instead fallback to the standard NVDA logger.
			enableUdp = False
			udpSock.close()
			_spimDebug("ERROR - couldn't send data to socket! Falling back to NVDA logging.")
	# Otherwise, log to the standard NVDA logging facility.
	else:
		if (warn == True):
			log.warn(st)
		else:
			log.debug("SPIMBraille: " + st)

# Procedural code

log.debug("Testing udp socket enable set to %s." % str(enableUdp))
if (enableUdp == True):

	log.debug("UDP is on. Trying to create a socket.")
	try:
		udpSock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
		_spimDebug("SPIM Braille UDP socket opened and running.")
	except Exception, e:
		enableUdp = False
		_spimDebug("Could not start the SPIM Braille debug socket! Reverting to NVDA log debugging.")

#Original code.

#Try to load the fs braille dll
try:
	fsbLib=windll.fsbrldspapi
except:
	fsbLib=None

#Map the needed functions in the fs braille dll
if fsbLib:
	fbOpen=getattr(fsbLib,'_fbOpen@12')
	fbGetCellCount=getattr(fsbLib,'_fbGetCellCount@4')
	fbWrite=getattr(fsbLib,'_fbWrite@16')
	fbClose=getattr(fsbLib,'_fbClose@4')
	fbConfigure=getattr(fsbLib, '_fbConfigure@8')
	fbGetDisplayName=getattr(fsbLib, "_fbGetDisplayName@12")
	fbGetFirmwareVersion=getattr(fsbLib,  "_fbGetFirmwareVersion@12")
	fbBeep=getattr(fsbLib, "_fbBeep@4")

FB_INPUT=1
FB_DISCONNECT=2
FB_EXT_KEY=3

LRESULT=c_long
HCURSOR=c_long

appInstance=windll.kernel32.GetModuleHandleW(None)

nvdaFsBrlWm=windll.user32.RegisterWindowMessageW(u"nvdaFsBrlWm")

inputType_keys=3
inputType_routing=4
inputType_wizWheel=5

# Names of freedom scientific bluetooth devices
bluetoothNames = (
	"F14", "Focus 14 BT",
	"Focus 40 BT",
	"Focus 80 BT",
)

keysPressed=0
extendedKeysPressed=0
@WNDPROC
def nvdaFsBrlWndProc(hwnd,msg,wParam,lParam):
	global keysPressed, extendedKeysPressed
	keysDown=0
	extendedKeysDown=0
	if msg==nvdaFsBrlWm and wParam in (FB_INPUT, FB_EXT_KEY):
		if wParam==FB_INPUT:
			inputType=lParam&0xff
			if inputType==inputType_keys:
				keyBits=lParam>>8
				keysDown=keyBits
				keysPressed |= keyBits
			elif inputType==inputType_routing:
				routingIndex=(lParam>>8)&0xff
				isRoutingPressed=bool((lParam>>16)&0xff)
				isTopRoutingRow=bool((lParam>>24)&0xff)
				if isRoutingPressed:
					gesture=RoutingGesture(routingIndex,isTopRoutingRow)
					try:
						inputCore.manager.executeGesture(gesture)
					except inputCore.NoInputGestureAction:
						pass
			elif inputType==inputType_wizWheel:
				numUnits=(lParam>>8)&0x7
				isRight=bool((lParam>>12)&1)
				isDown=bool((lParam>>11)&1)
				#Right's up and down are rversed, but NVDA does not want this
				if isRight: isDown=not isDown
				for unit in xrange(numUnits):
					gesture=WizWheelGesture(isDown,isRight)
					try:
						inputCore.manager.executeGesture(gesture)
					except inputCore.NoInputGestureAction:
						pass
		elif wParam==FB_EXT_KEY:
			keyBits=lParam>>4
			extendedKeysDown=keyBits
			extendedKeysPressed|=keyBits
		if keysDown==0 and extendedKeysDown==0 and (keysPressed!=0 or extendedKeysPressed!=0):
			gesture=KeyGesture(keysPressed,extendedKeysPressed)
			#log.info(str(keysPressed) +" "+ str(extendedKeysPressed))
			keysPressed=extendedKeysPressed=0
			try:
				inputCore.manager.executeGesture(gesture)
			except inputCore.NoInputGestureAction:
				pass
		return 0
	else:
		return windll.user32.DefWindowProcW(hwnd,msg,wParam,lParam)

nvdaFsBrlWndCls=WNDCLASSEXW()
nvdaFsBrlWndCls.cbSize=sizeof(nvdaFsBrlWndCls)
nvdaFsBrlWndCls.lpfnWndProc=nvdaFsBrlWndProc
nvdaFsBrlWndCls.hInstance=appInstance
nvdaFsBrlWndCls.lpszClassName=u"nvdaFsBrlWndCls"

log.info("Init done.")

class BrailleDisplayDriver(SPIMBraille.SPIMBrailleDisplayDriver,ScriptableObject):

	#ADDED(fmillion) Add the necessary SPIM Braille info and change the driver's name
	# so it won't clash with the original FS driver.
	
	# Expose that we support SPIM Braille
	hasSPIM = True
	
	# Name of display driver
	name="spim_focus"

	# Translators: Names of braille displays.
	description=_("SPIM Braille (FS Focus 14/40/80 Displays)")

	@classmethod
	def check(cls):
		return bool(fsbLib)

	@classmethod
	def getPossiblePorts(cls):
		ports = OrderedDict([cls.AUTOMATIC_PORT, ("USB", "USB",)])
		try:
			cls._getBluetoothPorts().next()
			ports["bluetooth"] = "Bluetooth"
		except StopIteration:
			pass
		return ports

	@classmethod
	def _getBluetoothPorts(cls):
		for p in hwPortUtils.listComPorts():
			try:
				btName = p["bluetoothName"]
			except KeyError:
				continue
			if not any(btName == prefix or btName.startswith(prefix + " ") for prefix in bluetoothNames):
				continue
			yield p["port"].encode("mbcs")

	wizWheelActions=[
		# Translators: The name of a key on a braille display, that scrolls the display to show previous/next part of a long line.
		(_("display scroll"),("globalCommands","GlobalCommands","braille_scrollBack"),("globalCommands","GlobalCommands","braille_scrollForward")),
		# Translators: The name of a key on a braille display, that scrolls the display to show the next/previous line.
		(_("line scroll"),("globalCommands","GlobalCommands","braille_previousLine"),("globalCommands","GlobalCommands","braille_nextLine")),
	]

	def __init__(self, port="auto"):
		self.leftWizWheelActionCycle=itertools.cycle(self.wizWheelActions)
		action=self.leftWizWheelActionCycle.next()
		self.gestureMap.add("br(spim_focus):leftWizWheelUp",*action[1])
		self.gestureMap.add("br(spim_focus):leftWizWheelDown",*action[2])
		self.rightWizWheelActionCycle=itertools.cycle(self.wizWheelActions)
		action=self.rightWizWheelActionCycle.next()
		self.gestureMap.add("br(spim_focus):rightWizWheelUp",*action[1])
		self.gestureMap.add("br(spim_focus):rightWizWheelDown",*action[2])
		super(BrailleDisplayDriver,self).__init__()
		self._messageWindowClassAtom=windll.user32.RegisterClassExW(byref(nvdaFsBrlWndCls))
		self._messageWindow=windll.user32.CreateWindowExW(0,self._messageWindowClassAtom,u"nvdaFsBrlWndCls window",0,0,0,0,0,None,None,appInstance,None)
		if port == "auto":
			portsToTry = itertools.chain(["USB"], self._getBluetoothPorts())
		elif port == "bluetooth":
			portsToTry = self._getBluetoothPorts()
		else: # USB
			portsToTry = [port]
		fbHandle=-1
		for port in portsToTry:
			fbHandle=fbOpen(port,self._messageWindow,nvdaFsBrlWm)
			if fbHandle!=-1:
				break
		if fbHandle==-1:
			raise RuntimeError("No display found")
		self.fbHandle=fbHandle
		self._configureDisplay()

		numCells = self._get_numCells() # get number of cells
		
		# SPIM Code
		# Handle different display sizes...
		
		# Protocol is: 1 splitter cell of all dots ON, and a number of register
		# cells each 8 cells wide separated by splitter cells.
		# Exception: 14 cell display does not have a splitter cell.
		# 14 cell displays generally not recommended!
		
		# Store actual cell count
		self.actualNumCells = self._get_numCells()

		# Mappings:
		# 14 cell-
		# ......--------
        # 6 std 1 reg NO separator
		# 40 cell-
		# .....................#--------#--------#
        #    22 cells std.        2 registers
		# 80 cell-
		# ............................................#--------#--------#--------#--------
        #    44 cells standard                           4 registers
		
		# 14 cells
		if (numCells == 14):
			self.registers = [None]
			self.numCells = 6
			log.warn("14 cell displays are generally not recommended.")
		elif (numCells == 40):
			self.registers = [None,None]
			self.numCells = 21
		elif (numCells == 80):
			self.registers = [None,None,None,None]
			self.numCells = 43
		else:
			self.registers = []
			log.warn("Unknown Focus display found - reporting %d cells! Disabling SPIM functionality." % self.numCells)
			self.hasSPIM=False # disable SPIM support
			
		log.info("SPIM Braille for Freedom Scientific Focus loaded with %d main cells and %d register blocks." % (self.numCells,len(self.registers)))
		
		self.gestureMap.add("br(spim_focus):topRouting1","globalCommands","GlobalCommands","braille_scrollBack")
		self.gestureMap.add("br(spim_focus):topRouting%d"%self.actualNumCells,"globalCommands","GlobalCommands","braille_scrollForward")

	def terminate(self):
		super(BrailleDisplayDriver,self).terminate()
		fbClose(self.fbHandle)
		windll.user32.DestroyWindow(self._messageWindow)
		windll.user32.UnregisterClassW(self._messageWindowClassAtom,appInstance)

	def _get_numCells(self):
		return fbGetCellCount(self.fbHandle)

	def display(self,cells):
		_spimDebug("Got %d cells to write from NVDA." % len(cells))

		# Call up to the superclass to append the registers to the cells we're displaying
		cells = super(BrailleDisplayDriver,self).display(cells, True if self.actualNumCells < 15 else False)
		
		# Convert from list to string
		cells="".join([chr(x) for x in cells]) 

		# Go ahead and actually display the cells!
		_spimDebug("Writing %d cells: %s" % (len(cells)," ".join([str(ord(cell)) for cell in cells])))
		fbWrite(self.fbHandle,0,len(cells),cells)

	# Back to original code.
	# Everything from here on to the end is original.
	
	def _configureDisplay(self):
		# See what display we are connected to
		displayName= firmwareVersion=""
		buf = create_string_buffer(16)
		if fbGetDisplayName(self.fbHandle, buf, 16):
			displayName=buf.value
		if fbGetFirmwareVersion(self.fbHandle, buf, 16):
			firmwareVersion=buf.value
		if displayName and firmwareVersion and displayName=="Focus" and ord(firmwareVersion[0])>=ord('3'):
			# Focus 2 or later. Make sure extended keys support is enabled.
			log.debug("Activating extended keys on freedom Scientific display. Display name: %s, firmware version: %s.", displayName, firmwareVersion)
			fbConfigure(self.fbHandle, 0x02)

	def script_toggleLeftWizWheelAction(self,gesture):
		action=self.leftWizWheelActionCycle.next()
		self.gestureMap.add("br(spim_focus):leftWizWheelUp",*action[1],replace=True)
		self.gestureMap.add("br(spim_focus):leftWizWheelDown",*action[2],replace=True)
		braille.handler.message(action[0])

	def script_toggleRightWizWheelAction(self,gesture):
		action=self.rightWizWheelActionCycle.next()
		self.gestureMap.add("br(spim_focus):rightWizWheelUp",*action[1],replace=True)
		self.gestureMap.add("br(spim_focus):rightWizWheelDown",*action[2],replace=True)
		braille.handler.message(action[0])

	__gestures={
		"br(spim_focus):leftWizWheelPress":"toggleLeftWizWheelAction",
		"br(spim_focus):rightWizWheelPress":"toggleRightWizWheelAction",
	}

	gestureMap=inputCore.GlobalGestureMap({
		"globalCommands.GlobalCommands" : {
			"braille_routeTo":("br(spim_focus):routing",),
			"braille_scrollBack" : ("br(spim_focus):leftAdvanceBar", "br(fsSpim]:leftBumperBarUp","br(spim_focus):rightBumperBarUp",),
			"braille_scrollForward" : ("br(spim_focus):rightAdvanceBar","br(spim_focus):leftBumperBarDown","br(spim_focus):rightBumperBarDown",),
			"braille_previousLine" : ("br(spim_focus):leftRockerBarUp", "br(spim_focus):rightRockerBarUp",),
			"braille_nextLine" : ("br(spim_focus):leftRockerBarDown", "br(spim_focus):rightRockerBarDown",),
			"kb:backspace" : ("br(spim_focus):dot7",),
			"kb:enter" : ("br(spim_focus):dot8",),
			"kb:shift+tab": ("br(spim_focus):dot1+dot2+brailleSpaceBar",),
			"kb:tab" : ("br(spim_focus):dot4+dot5+brailleSpaceBar",),
			"kb:upArrow" : ("br(spim_focus):dot1+brailleSpaceBar",),
			"kb:downArrow" : ("br(spim_focus):dot4+brailleSpaceBar",),
			"kb:leftArrow" : ("br(spim_focus):dot3+brailleSpaceBar",),
			"kb:rightArrow" : ("br(spim_focus):dot6+brailleSpaceBar",),
			"kb:control+leftArrow" : ("br(spim_focus):dot2+brailleSpaceBar",),
			"kb:control+rightArrow" : ("br(spim_focus):dot5+brailleSpaceBar",),
			"kb:home" : ("br(spim_focus):dot1+dot3+brailleSpaceBar",),
			"kb:control+home" : ("br(spim_focus):dot1+dot2+dot3+brailleSpaceBar",),
			"kb:end" : ("br(spim_focus):dot4+dot6+brailleSpaceBar",),
			"kb:control+end" : ("br(spim_focus):dot4+dot5+dot6+brailleSpaceBar",),
			"kb:alt" : ("br(spim_focus):dot1+dot3+dot4+brailleSpaceBar",),
			"kb:alt+tab" : ("br(spim_focus):dot2+dot3+dot4+dot5+brailleSpaceBar",),
			"kb:escape" : ("br(spim_focus):dot1+dot5+brailleSpaceBar",),
			"kb:windows" : ("br(spim_focus):dot2+dot4+dot5+dot6+brailleSpaceBar",),
			"kb:windows+d" : ("br(spim_focus):dot1+dot2+dot3+dot4+dot5+dot6+brailleSpaceBar",),
			"reportCurrentLine" : ("br(spim_focus):dot1+dot4+brailleSpaceBar",),
			"showGui" :("br(spim_focus):dot1+dot3+dot4+dot5+brailleSpaceBar",),
			"braille_toggleTether" : ("br(spim_focus):leftGDFButton+rightGDFButton",),
		}
	})
	
class InputGesture(braille.BrailleDisplayGesture):
	source = BrailleDisplayDriver.name

class KeyGesture(InputGesture, brailleInput.BrailleInputGesture):

	keyLabels=[
		#Braille keys (byte 1)
		'dot1','dot2','dot3','dot4','dot5','dot6','dot7','dot8',
		#Assorted keys (byte 2)
		'leftWizWheelPress','rightWizWheelPress',
		'leftShiftKey','rightShiftKey',
		'leftAdvanceBar','rightAdvanceBar',
		None,
		'brailleSpaceBar',
		#GDF keys (byte 3)
		'leftGDFButton','rightGDFButton',
		None,
		'leftBumperBarUp','leftBumperBarDown','rightBumperBarUp','rightBumperBarDown',
	]
	extendedKeyLabels = [
	# Rocker bar keys.
	"leftRockerBarUp", "leftRockerBarDown", "rightRockerBarUp", "rightRockerBarDown",
	]

	def __init__(self,keyBits, extendedKeyBits):
		super(KeyGesture,self).__init__()
		keys=[self.keyLabels[num] for num in xrange(24) if (keyBits>>num)&1]
		extendedKeys=[self.extendedKeyLabels[num] for num in xrange(4) if (extendedKeyBits>>num)&1]
		allKeys = keys + extendedKeys
		#log.info("gesture parts: %s, %s" % (keys, extendedKeys))
		#log.info("All gesture parts: %s" % allKeys)
		allKeys=frozenset(allKeys)
		#log.info("Frozenset: %s" % str(allKeys))
		self.id="+".join(allKeys)
		# Don't say is this a dots gesture if some keys either from dots and space are pressed.
		if not extendedKeyBits and not keyBits & ~(0xff | (1 << 0xf)):
			self.dots = keyBits & 0xff
			# Is space?
			if keyBits & (1 << 0xf):
				self.space = True
		#log.info(self.id)
		
class RoutingGesture(InputGesture):

	def __init__(self,routingIndex,topRow=False):
		if topRow:
			self.id="topRouting%d"%(routingIndex+1)
		else:
			self.id="routing"
			self.routingIndex=routingIndex
		super(RoutingGesture,self).__init__()

class WizWheelGesture(InputGesture):

	def __init__(self,isDown,isRight):
		which="right" if isRight else "left"
		direction="Down" if isDown else "Up"
		self.id="%sWizWheel%s"%(which,direction)
		super(WizWheelGesture,self).__init__()

