# PC Spim Interface Module
# App Module for NVDA
# by Flint Million <flint.million@mnsu.edu>

# Supporting SPIM Braille extensions in NVDA Braille display drivers
#  last update 12-03-2015

# RESEARCH ENABLED MODULE
# Use NVDA+Shift+Equals to start or stop a research study.
# A CSV file will be created in %AppData%\Roaming\NVDA\Research for the study.

# Python system imports
import re, time, random, os.path, threading, tempfile, subprocess

# WXWidgets
import wx

# Win32
import win32clipboard, win32con

# NVDA-specific imports
from NVDAObjects.IAccessible import IAccessible, ContentGenericClient
import appModuleHandler, ui, api, tones, braille, config, gui, textInfos
from logHandler import log
from gui import settingsDialogs

# Static variables

# Help text
HELP_TEXT = """\
PC Spim NVDA Add-On Keyboard Reference
--------------------------------------

All commands are "NVDA+Shift+key". Example: "X" means press NVDA+Shift+X.

Braille Modes

F - Freeze Mode. Stops updating the display, keeping the current register values in place.
L - Live mode. Starts periodically updating the Braille display with the current values of system registers.
R - Reveal mode. Displays in each region of the display what register is being displayed there.

Braille configuration

C - Open Display Configuration. Allows you to set which registers will be displayed in which regions of the Braille display.

Code Readability

I - Recite (and provide in Braille) information about the current line of code. Note: you should be focused on the Code window when you use this command.
X - Make All Code Readable. Produces and opens a text file displaying all of the code in the Code window, processed for easy readability.
Z - Make All Code Readable (Verbose). Produces and opens a text file displaying all of the code in the Code window, processed for easy readability with verbose output. More details are given for each instruction.

User Interface

1 - Set focus to the Code window.
2 - Set focus to the Registers window.
3 - Set focus to the Memory window.
4 - Set focus to the Status window.
5 - Set focus to the Console.
P - Copy the contents of the Console to the system clipboard.

Braille Commands

All of the above commands except for the Focus Window commands are entered on the Braille display by pressing Dot 7 + Space + the letter in question. For example, to get info on the current line of code, you press Dot 2 + Dot 4 + Dot 7 + Space.
To move focus between windows, press the given dot plus dot 7 plus Space. For example, for the Code window, press Dot 1 + Dot 7 + space; for the Console press Dot 1 + Dot 5 + Space.

The following additional commands are available in Braille:

R-Chord (Dots 1-2-3-5) - Run the code. (Same as the F5 key)
ST-Chord (Dots 3-4) - Step to the next statement of code. (Same as the F10 key)
FOR+7 Chord (Dots 1-2-3-4-5-6-7) - Randomize the display in the register cells. (Debug option only)
app++"""


# Identifiers for edit fields in SPIM application
EF_CODE = 1
EF_REGISTERS = 2
EF_MEMORY = 3
EF_STATUS = 4
EF_CONSOLE = 5

# BRAILLE TRANSLATOR CODE

# In NVDA, braille is represented as 8-bit bytes. This turns out to work very well since Braille cells on a Braille display
# are 8 dots. Therefore, each bit in an 8 bit byte specifies whether one dot is on or off.

# This is a very basic Braille output translation table. It contains only the 26 lowercase letters, numbers, space and period.
# We *could* use something like liblouis, but that's a bit overkill for our purposes.
simpleBrailleMap = {
	'a': 0x01, 'b': 0x03, 'c': 0x09, 'd': 0x19, 'e': 0x11,
	'f': 0x0b, 'g': 0x1b, 'h': 0x13, 'i': 0x0a, 'j': 0x1a,
	'k': 0x05, 'l': 0x07, 'm': 0x0d, 'n': 0x1d, 'o': 0x15,
	'p': 0x0f, 'q': 0x1f, 'r': 0x17, 's': 0x0e, 't': 0x1e,
	'u': 0x25, 'v': 0x27, 'w': 0x3a, 'x': 0x2d, 'y': 0x3d,
	'z': 0x35,
	'1': 0x02, '2': 0x06, '3': 0x12, '4': 0x32,
	'5': 0x22, '6': 0x16, '7': 0x36, '8': 0x26,
	'9': 0x14, '0': 0x34,
	' ': 0x00, '.': 0x28 }

def simpleTranslateToBrl(text):
	"""Use the simple Braille translation map to translate a string into equivalent Braille bytes"""

	# initialize output
	out = ""

	log.debug("translating %d characters into Braille" % len(text))
	log.debug("using map: %s" % str(simpleBrailleMap))

	# iterate through entire string and setup a Braille character string
	for c in text.lower():
		try:
			ch = simpleBrailleMap[c]
			out += chr(ch) # append found character
		except KeyError:
			# An unknown character was found. Log and replace with a full cell.
			log.debug("the character '%s' was not found." % c)
			out += "\xff" # full cell
	return out

# MISC GLOBAL FUNCTIONS

def error_tone():
	"""Generate error tone using NVDA tones module"""
	tones.beep(880,250)
	time.sleep(0.15)
	
def toHex(num,length=8):
	"""Convert integer to length-position hex string"""
	return hex(num)[2:].lower()[-length:].zfill(length)

def getTempPath():
	"""Get a string containing the path to the user's temp directory."""
	os.path.join(os.path.expanduser("~"),"AppData\Local\Temp")

# APP MODULE

# noinspection PyInterpreter
class AppModule(appModuleHandler.AppModule):
	"""PC Spim application access module."""

	# This switch determines if researching is currently occurring.
	researchFlag = False
	# This holds the handle to the research study log file.
	researchFileHandle = None

	viewMode = 0 # default to freeze mode
	updateThreadDieFlag = 0 # this gets set when the update thread should stop
	updateThread = None # this will hold the actual update thread object
	
	# Init override
	def __init__(self, processID,appName=None):

		# Play tone to indicate the driver was loaded.  ( Mostly for debugging use here. )
		tones.beep(440,450) # LOL, it sounds like a BrailleNote!

		# Provide local access to the braille display instance
		self.brl = braille.handler.display

		log.info("PCSpim: Loaded the PC Spim access driver.")

		# Call superclass init handler
		appModuleHandler.AppModule.__init__(self, processID, appName)

		# Check braille driver
		if ("hasSPIM" not in dir( self.brl )):
			self.clearGestureBindings() # destroy all gestures
			log.warn("PCSpim ERROR: Not using a supported Braille driver!")
			ui.message("PC Spim access support cannot be enabled because a SPIM Braille compliant driver is not being used. Please switch to a SPIM Braille driver and restart PC Spim.")
		elif (braille.handler.display.hasSPIM == False):
			# If an error occurred with SpimBraille, DO NOT proceed with loading the module.
			# Instead unload everything - PCSpim will work as if it has no app module since all the bindings are being cleared.
			error_tone()
			self.clearGestureBindings() # destroy all gestures
			log.warn("PCSpim ERROR: Braille driver reports SPIM support not available!")
			ui.message("PC Spim access support cannot be enabled because the SPIM Braille driver currently loaded indicated it is not presently able to support SPIM features. Please contact developer, or try a different SPIM Braille driver and restart PC Spim.")
		else:
			log.info("PCSpim: Using supported Braille output device %s with %d registers." % ( self.brl.name, self.brl.getRegisterCount() ) )

		# DEBUG: display a list of all registered gestures to the debug log
		gMap = "%d gesture mappings, as follows:\n"%len(self._gestureMap)
		for g in sorted(self._gestureMap.keys()):
			gMap += "%s: function %s\n" % (g, self._gestureMap[g].__name__)
		log.debug(gMap)
		
	# Notify on module unload (mostly for debug purpose at this point)
	def __del__(self):
		self.updateThreadDieFlag = 1 # close the thread if it's cycling
		log.info("Closing PC Spim access driver.")

	# Parsers
	def parseGPRegisters(self, text):
		"""Parse general purpose registers from SPIM raw window content"""
		gpRegisters = dict ( re.findall(r"R[0-9]{1,2} {1,2}\(([a-z0-9]{2})\) = ([0-9a-f]{8})", text) )
		gpRegisters.update((x, int(y,16)) for x, y in gpRegisters.items())
		return gpRegisters

	def parseCodeLine(self, text):
		"""Parse a line of code from PCSpim's Code window and organize into logical components"""
		codeRegex = re.compile(r"^\[0x([0-9a-f]{8})\]\t0x([0-9a-f]{8})  (.+)$")
		# attempt to match the code
		m = codeRegex.match(text)
		# If no match found, return None.
		if (m is None): return None
		result = {}
		result['encoded_instruction'] = int(m.group(2),16)
		result['address'] = int(m.group(1),16)
		# Do we have a comment?
		instr = m.group(3)
		if (";" in instr):
			pos = instr.index(";")
			comment = instr[pos+1:].strip()
			instr = instr[:pos].strip()
		else:
			instr = instr.strip()
			comment = ""
		result['comment'], result['instruction'] = comment, instr
		return result

	# UI control functions
	def getSpimThreadID(self):
		"""Attempt to get the thread ID of the main PCSpim window. Used to later find the console window, which will share the thread ID."""

		try:
			app = api.getDesktopObject()

			# Eliminate items with a "None" name - these cause the list comprehension to fail.
			app = filter(lambda x: x.name != None, app.children)
			app = filter(lambda x: x.name[0:6] == "PCSpim", app)[0] # Drill down to the app itself

			return app.windowThreadID
		except:
			return -1 # failure
	
	def findEditField(self, whichField):
		"""Attempt to find the edit field specified by the whichField parameter. Returns None if the edit field could not be found"""

		# There is unfortunately no easy way to do this!
		# The PC Spim application is somehow set up such that each of the sections of the main window all have the same ID!
		# This technically isn't even supposed to happen, but, it does. So we have to work with it.
		
		# When all else fails, look for patterns and use regex. That's what we're doing here.
		
		if (whichField == EF_REGISTERS):

			# The registers field is populated with the contents of the simulation's registers.
			# The field will contain the words "General Registers".
			e = self.getEditFields()
			for ef in e:
				if ("General Registers" in ef.value):
					# found it
					return ef
			return None # didn't find it.

		elif (whichField == EF_CODE):
			# The code field contains all of the executable code to be executed by the
			# simulator.
			# The lines in the code window all generally follow the same pattern, so this regex should capture them.
			e = self.getEditFields()
			for ef in e:
				test = len(re.findall(r"^\[0x[0-9a-f]{8}\]\t0x[0-9a-f]{8}  ", ef.value, re.M))
				if (test > 20):
					# Safe to assume if we get 20 lines of code, we have found the code field.
					return ef
			return None

		elif (whichField == EF_MEMORY):
			# The memory field shows the contents of various regions of memory.
			# It contains many lines matching a specific regex.
			e = self.getEditFields()
			for ef in e:
				test = len(re.findall(r"^\[0x[0-9a-f]{8}\](\s*0x[0-9a-f]{8}){4}", ef.value, re.M))
				if (test > 10):
					# Safe to assume if we get 10 lines of data, we have found the memory field.
					return ef
			return None

		elif (whichField == EF_STATUS):
			# The status field prints status messages.
			# It's pretty straightforward, it will always start out containing an identifier banner.
			# (Obviously if the user changes the banner or tampers with the field contents this
			# won't work, but it's the best we can do for now.)
			e = self.getEditFields()
			for ef in e:
				if ("SPIM Version" in ef.value):
					return ef # we probably found it

		elif (whichField == EF_CONSOLE):
			# The console is in a completely separate desktop window. To find it, we first must get the
			# thread ID of the main SPIM window, so we can match it.
			tid = self.getSpimThreadID()
			if (tid == -1): return None # error occurred getting the thread ID.
			
			# Find all windows matching this thread.
			all =  filter( lambda x: x.windowThreadID==tid, api.getDesktopObject().children )
			
			# Search for items starting with "console"...
			all = filter( lambda x: x.name.startswith("Console") == True, all )
			
			# We should have one result. If not, a failure occurred.
			if (len(all) < 1): return None
			
			consWindow = all[0]
			
			# Now we have to drill down through these and find one with a rich edit box as its child.
			# (This app's class names are endlessly confusing! Luckily there's a diamond in the rough...)
			rtfParent = None
			for obj in consWindow.children:
				#log.info([x.windowClassName for x in obj.children])
				if ("RichEdit20A" in [x.windowClassName for x in obj.children]):
					rtfParent = obj
					break
			if (rtfParent == None):
				return None # didn't find a rich edit field
			
			# We found it!
			return rtfParent.children[0]
			
		else:
			return None # placeholder

	def getEditFields(self):
		"""Navigate system API to locate the PCSpim window and access its four edit regions"""

		# This attempts to find the edit fields in the PCSpim application.
		# It will return the NVDA object for each box.
		
		# Start at the desktop; look for the PCSpim application.
		try:
			app = api.getDesktopObject()

			# Eliminate items with a "None" name - these cause the list comprehension to fail.
			app = filter(lambda x: x.name != None, app.children)
			app = filter(lambda x: x.name[0:6] == "PCSpim", app)[0] # Drill down to the app itself

			app = filter(lambda x: x.name != None, app.children)
			app = filter(lambda x: x.name[0:6] == "PCSpim", app)[0] # Drill down to the app main window

			app = filter(lambda x: x.windowClassName.startswith("AfxFrame"), app.children)[0] # Drill into the frame

		except:
			log.warn("Could not find PC Spim edit fields!",exc_info=True)
			return None # Error finding the main app window.

		# we found the edit fields.
		# Now extract text from all four edits, and put into lists.
		outputEdits = []
		for o in app.children:
			if (o.windowClassName == "Edit"):
				outputEdits.append(o)

		return outputEdits

	def getAvailableRegisters(self):
		"""Parse the Registers window and get a list of all registers available for display"""

		ef = self.findEditField(EF_REGISTERS).value
		if (ef is None):  return {}
		regs = self.parseGPRegisters(ef)
		if (len(regs) == 0):
			error_tone()
			log.warn("PCSpim Interface ERROR: Found edit fields, but could not find registers.")
			return {}
		return regs

	def updateRegisters(self):
		"""Actually perform an update of the registers to the Braille device"""
		# This is the payload function - it is what actually handles displaying registers on the Braille display.
		# Each time it is called, registers will be parsed and sent to the display driver for display.
		
		if (self.revealMode == True): return # do not execute if reveal mode is on.
		regs = self.getAvailableRegisters()
		outRegs = [None]*self.brl.getRegisterCount()
		for r in range(len(outRegs)):
			try:
				whichReg = config.conf['pcspim']['r%d' % r]
				outRegs[r] = regs[whichReg]
			except KeyError:
				pass # this is OK, it just means we have no value at this register.
				outRegs[r] = None
			except:
				log.warn("Exception updating register.",exc_info=True)
				outRegs[r] = None
		self.brl.setAllRegisters(outRegs)

	def _updateThread(self):
		# This function will be started on another thread to update the display on a regular basis.
		log.debug("update thread is starting.")
		while (True):
			log.debug("update thread is updating registers.")
			if (self.updateThreadDieFlag == 1):
				self.updateThreadDieFlag = 2 # indicate that we just died
				return # stop updating
			time.sleep(1) # delay is 1 second between live register updates
			#ui.message("x")
			self.updateRegisters()

	def updateMode(self):
		# This handles changes the display mode
		if (self.viewMode == 0):
			ui.message("Freeze mode")
			self.revealMode = False
			self.updateRegisters()
			self.updateThreadDieFlag = 1
		elif (self.viewMode == 1):
			ui.message("Live mode")
			self.revealMode = False
			# Do initial display of registers
			self.updateRegisters()
			# Check for a thread
			if (self.updateThread != None):
				if (self.updateThread.isAlive() == True):
					log.warn("thread still alive, trying to kill")
					self.updateThreadFlag = 1
					waitTimeout = 0
					while (self.updateThreadFlag != 2):
						waitTimeout += 1
						if (waitTimeout > 20):
							log.warn("Update thread indicated alive, but did not respond to die request! Things may get ugly.")
							break
						time.sleep(0.1)
			self.updateThreadDieFlag = 0
			self.updateThread = threading.Thread(target=self._updateThread)
			self.updateThread.start()
		else:
			ui.message("Reveal mode")
			self.revealMode = True
			for r in range(self.brl.getRegisterCount()):
				try:
					whichReg = config.conf['pcspim']['r%d' % r]
				except KeyError:
					# No register is assigned to this field - simply display it as "none"
					whichReg = "none"
				self.brl.setRegister(r,simpleTranslateToBrl(whichReg.strip().center(8,' ')))


	## RESEARCH ##
	def research_log(self, action, gesture, comment=""):
		if (self.researchFlag==True):
			self.researchFileHandle.write('%.2f,"%s","%s","%s"\r\n' % (time.time(), action, gesture, comment))
			self.researchFileHandle.flush()

	def script_toggleStudy(self, gesture):
		if (self.researchFlag==False):
			tones.beep(660,120)
			time.sleep(0.12)
			tones.beep(880,120)
			time.sleep(0.06)
			ui.message("Research study has begun.")
			researchFilename =  os.path.join(os.path.expanduser("~"),"AppData","Roaming","nvda","research","study-" + str(int(time.time()))+".csv")
			self.researchFileHandle = open(researchFilename,"w")
			self.researchFlag=True
			self.researchFileHandle.write('"TIME","EVENT","GESTURE","INFO"\n')
			self.research_log("START","")
		else:
			tones.beep(880,120)
			time.sleep(0.12)
			tones.beep(660,120)
			time.sleep(0.06)
			ui.message("Research study has concluded.")
			self.research_log("FINISH","")
			self.researchFileHandle.close()
			self.researchFlag=False

	## SCRIPTS ##
	# This is the code that directly executes when a user presses various keystrokes.
	# These scripts call into the other code provided.
	
	def script_configure(self, gesture):

		self.research_log("configure",str(gesture._get_displayName()))

		error_tone()
		try:
			ssd = SpimSettingsDialog(gui.mainFrame, self.getAvailableRegisters().keys(), self.brl.getRegisterCount())
		except gui.settingsDialogs.SettingsDialog.MultiInstanceError:
			ui.message("Config dialog already open.")
			return
		# Do everything possible to bring the settings dialog to the front.
		ssd.Show()
		ssd.SetFocus()
		ssd.Raise()

	def script_setFreeze(self, gesture):

		self.research_log("setFreeze",str(gesture._get_displayName()))

		"""Notify user which registers are being shown in which cells. Toggles between this and actual register display."""
		if (self.viewMode == 0): # already in freeze mode
			ui.message("Already in freeze mode")
			return
		self.viewMode = 0
		self.updateMode()

	def script_setLive(self, gesture):

		self.research_log("setLive",str(gesture._get_displayName()))

		"""Notify user which registers are being shown in which cells. Toggles between this and actual register display."""
		if (self.viewMode == 1): # already in live mode
			ui.message("Already in live mode")
			return
		self.viewMode = 1
		self.updateMode()

	def script_setReveal(self, gesture):

		self.research_log("setReveal",str(gesture._get_displayName()))

		"""Notify user which registers are being shown in which cells. Toggles between this and actual register display."""
		if (self.viewMode == 2): # already in freeze mode
			ui.message("Already in Reveal mode")
			return
		self.viewMode = 2
		self.updateMode()

	def script_makeCodeReadable(self, gesture):

		self.research_log("makeCodeReadable",str(gesture._get_displayName()))

		tones.beep(440,50)

		# test code: get the code box
		e = self.findEditField(EF_CODE) # We have the edit field object.

		if (e == None): return # can't do anything
		
		data = e.value
		out = "PCSpim Instruction Output\r\n\r\n"
		for l in data.split("\n"):
			# try to parse the code
			info = self.parseCodeLine(l.strip())
			if (info is None):
				out += l.strip("\r\n") + "\r\n"
			else:
				out += "%s %s (instruction %s at %s)\r\n" % (
					info['instruction'],
					"; " + info['comment'] if info['comment'] != "" else "",
					"0x" + hex(info['encoded_instruction'])[2:].zfill(8).lower(),
					"0x" + hex(info['address'])[2:].zfill(8).lower()
					)

		tempFileName = os.path.join(tempfile.gettempdir(), "PCSpim-code-%d.txt" % int(time.time()))
		open(tempFileName,"w").write(out)
		
		subprocess.Popen(["notepad", tempFileName])
		#os.system('notepad "%s"' % tempFileName)
		tones.beep(880,50)

	def script_makeCodeReadable2(self, gesture):

		self.research_log("makeCodeReadable2",str(gesture._get_displayName()))

		tones.beep(440,50)

		# test code: get the code box
		e = self.findEditField(EF_CODE) # We have the edit field object.

		if (e == None): return # can't do anything
		
		data = e.value
		out = "PCSpim Instruction Output (Extended)\r\n\r\n"
		for l in data.split("\n"):
			# try to parse the code
			info = self.parseCodeLine(l.strip())
			if (info is None):
				out += l.strip("\r\n") + "\r\n"
			else:
				out += "Actual Assembly instruction : %s\r\n" % info['instruction']
				out += "Your Instruction (comment)  : %s\r\n" % info['comment'] if info['comment'] else "<none>"
				out += "Encoded Instruction (hex)   : %s\r\n" % hex(info['encoded_instruction'])[2:].zfill(8).lower()
				out += "Memory Address (hex)        : %s\r\n\r\n" % hex(info['address'])[2:].zfill(8).lower()

		tempFileName = os.path.join(tempfile.gettempdir(), "PCSpim-code-%d.txt" % int(time.time()))
		open(tempFileName,"w").write(out)
		
		subprocess.Popen(["notepad", tempFileName])
		#os.system('notepad "%s"' % tempFileName)
		tones.beep(880,50)

	def script_getCodeInfo(self, gesture):

		# test code: get the code box
		# test code - are we in the edit box?

		e = self.findEditField(EF_CODE) # We have the edit field object.

		try:
			if (api.getFocusObject().value != e.value):
				log.warn("Code info requested but caret is not in code edit box.")
				ui.message("Warning, focus is not on code edit box. Try n v d a plus shift plus 1.")
				self.research_log("getCodeInfo","","Request made without being in the code edit field.")
		except:
			log.warn("Code info requested but focus object has no caret.")
			ui.message("Warning, focus is not on code edit box. Try n v d a plus shift plus 1.")
			self.research_log("getCodeInfo","","Request made without being in the code edit field.")
		
		# Log cursor position for debug purposes
		pos = e.makeTextInfo(textInfos.POSITION_CARET).bookmark.startOffset
		log.info("Code caret is at position %d" % pos)

		# Retrieve the current line of text
		line = e.makeTextInfo(textInfos.POSITION_CARET)
		line.expand(textInfos.UNIT_LINE)
		line = line.text.strip()

		self.research_log("getCodeInfo",str(gesture._get_displayName()), "Line parsed: '"+line+"'")

		info = self.parseCodeLine(line)

		if (info is None):
			ui.message("Not on a code line.")
			self.research_log("getCodeInfo","", "Not on a code line.")
			return

		# Speak the instruction first.
		out = "Instruction: %s. " % info['instruction']
		# Comment, speak it.
		if (info['comment'] != ""):
			out += "Comment: %s. " % info['comment']
		# Instruction encoded
		out += "Encoded instruction: %s. " % " ".join(hex(info['encoded_instruction'])[2:].zfill(8).upper())
		# Memory location
		out += "Memory address: %s. " % " ".join(hex(info['address'])[2:].zfill(8).upper())

		ui.message(out)

	def script_setFocusTo(self, gesture):
		try:
			gKey = int(gesture.mainKeyName)
			log.debug("setFocusTo is reacting to key %s" % gesture.mainKeyName)
			self.research_log("setFocusTo",str(gesture._get_displayName()), "")
			log.info("The current focus object is: " + str(api.getFocusObject()))
		except ValueError:
			log.warn("setFocusTo couldn't turn %s into an int!" % str(gesture.mainKeyName))
			return

		if (gKey in (EF_CODE, EF_MEMORY, EF_REGISTERS, EF_STATUS, EF_CONSOLE)):
			try:
				ef = self.findEditField(gKey)
				ef.setFocus() 
				if (gKey == EF_CODE): ui.message("Code Window")
				if (gKey == EF_MEMORY): ui.message("Memory Window")
				if (gKey == EF_REGISTERS): ui.message("Registers Window")
				if (gKey == EF_STATUS): ui.message("Status Window")
				# No need to announce the console.
				api.setFocusObject(ef)
				api.setNavigatorObject(ef)
				#ef.setFocus() # try twice
			except:
				ui.message("couldn't set focus.")
				log.warn("Couldn't set focus!",exc_info=True)
				self.research_log("setFocusTo",str(gesture._get_displayName()), "Failed to set focus!")

	def script_copyConsoleToClipboard(self, gesture):

		self.research_log("copyConsoleToClipboard",str(gesture._get_displayName()), "")

		# Get the console window
		ef = self.findEditField(EF_CONSOLE)
		if (ef == None):
			ui.message("Error accessing the console window.")
			return
		if (ef.value == None):
			ui.message("There is nothing on the console to copy to the clipboard.")
			return
		theText = ef.value.replace("\r","\r\n")
		log.info([str(ord(c)) for c in theText])		
		win32clipboard.OpenClipboard()
		win32clipboard.EmptyClipboard()
		win32clipboard.SetClipboardText(theText)
		win32clipboard.CloseClipboard()
		ui.message("Console copied to the clipboard.")
		
	def script_setFocusBrl(self, gesture):
		self.research_log("setFocusBrl",str(gesture.dots), "")
		print str( gesture.keyLabels )
		print str( gesture.dots )

	def script_debug_randomizeRegisters(self, gesture):
		self.script_setFreeze(None)
		ui.message("Randomizing")
		for i in range(self.brl.getRegisterCount()):
			self.brl.setRegister(i,random.randrange(2**32))

	## OVERLAY ASSIGNER
	def chooseNVDAObjectOverlayClasses(self, obj, clsList):
		windowClassName=obj.windowClassName
		windowControlID=obj.windowControlID
		#log.info("Scanning '%s', %s" % ( windowClassName, str(windowControlID)))
		if (windowClassName==u"RichEdit20A"):
			log.debug("Assign %s, %s as console edit box." % ( windowClassName, str(windowControlID)))
			clsList.insert(0, ConsoleEditBox)

	## GESTURES

	gestureMap = {
		"kb:f5": "br(spim_focus):dot1+dot2+dot3+dot5+brailleSpaceBar",
		"kb:f10": "br(spim_focus):dot3+dot4+brailleSpaceBar",
	}

	__gestures = {
		"kb:NVDA+shift+c": "configure",
		"br(spim_focus):dot1+dot4+dot7+brailleSpaceBar": "configure",

		"kb:NVDA+shift+f": "setFreeze",
		"br(spim_focus):dot1+dot2+dot4+dot7+brailleSpaceBar": "setFreeze",
		
		"kb:NVDA+shift+l": "setLive",
		"br(spim_focus):dot1+dot2+dot3+dot7+brailleSpaceBar": "setLive",
		
		"kb:NVDA+shift+r": "setReveal",
		"br(spim_focus):dot1+dot2+dot3+dot5+dot7+brailleSpaceBar": "setReveal",

		"kb:NVDA+shift+i": "getCodeInfo",
		"br(spim_focus):dot2+dot4+dot7+brailleSpaceBar": "getCodeInfo",
		
		"kb:NVDA+shift+x": "makeCodeReadable",
		"kb:NVDA+shift+z": "makeCodeReadable2",
		"br(spim_focus):dot1+dot3+dot4+dot6+dot7+brailleSpaceBar": "makeCodeReadable",
		"br(spim_focus):dot1+dot3+dot5+dot6+dot7+brailleSpaceBar": "makeCodeReadable2",

		"kb:NVDA+shift+p": "copyConsoleToClipboard",
		"br(spim_focus):dot1+dot2+dot3+dot4+dot7+brailleSpaceBar": "copyConsoleToClipboard",
		
		"kb:NVDA+shift+1": "setFocusTo",
		"kb:NVDA+shift+2": "setFocusTo",
		"kb:NVDA+shift+3": "setFocusTo",
		"kb:NVDA+shift+4": "setFocusTo",
		"kb:NVDA+shift+5": "setFocusTo",

		"kb:NVDA+shift+=": "toggleStudy",

		"br(spim_focus):dot7+dot2+brailleSpaceBar": "setFocusBrl",
		"br(spim_focus):dot7+dot1+brailleSpaceBar": "setFocusBrl",
		"br(spim_focus):dot7+dot4+brailleSpaceBar": "setFocusBrl",
		"br(spim_focus):dot7+dot5+brailleSpaceBar": "setFocusBrl",
		"br(spim_focus):dot7+dot8+brailleSpaceBar": "setFocusBrl",
		
		"br(spim_focus):dot1+dot2+dot3+dot4+dot5+dot6+dot7+brailleSpaceBar": "debug_randomizeRegisters",
		
		}
		


# Configuration dialog
class SpimSettingsDialog(settingsDialogs.SettingsDialog):
	# Translators: This is the label for the synthesizer dialog.
	title = _("PCSpim Access Configuration")

	def __init__(self, parent, regs, numOfRegs):

		self.numOfRegs = numOfRegs
		self.Regs = ['none']
		self.Regs.extend( sorted(regs) )

		super(SpimSettingsDialog, self).__init__(parent)

	def makeSettings(self, settingsSizer):
		# Translators: This is a label for the select
		# synthesizer combobox in the synthesizer dialog.
		regs = {}
		self.lists = {}
		for r in range(self.numOfRegs):
			# create dictionary subdir
			regs[r] = {}

			# create sizer for register line
			regs[r]['ListSizer']=wx.BoxSizer(wx.HORIZONTAL)
			regs[r]['Label']=wx.StaticText(self,-1,label=_("Register #&%d:" % r))
			regs[r]['ListID']=wx.NewId()
			self.lists[r]=wx.Choice(self,regs[r]['ListID'],choices=self.Regs)
			try:
				index=self.Regs.index(config.conf['pcspim']["r%d" % r])
				self.lists[r].SetSelection(index)
			except:
				pass
			regs[r]['ListSizer'].Add(regs[r]['Label'])
			regs[r]['ListSizer'].Add(self.lists[r])
			settingsSizer.Add(regs[r]['ListSizer'],border=10,flag=wx.BOTTOM)

	def postInit(self):
		try:
			self.lists[0].SetFocus()
		except:
			pass

	def onOk(self,evt):
		#Does the config file contain SPIM data already?
		if ("pcspim" not in config.conf.keys()):
			config.conf["pcspim"] = {}

		for r in range(self.numOfRegs):
			config.conf["pcspim"]["r%d" % r]=self.lists[r].GetStringSelection()
			if (self.lists[r].GetStringSelection() in ('none','')):
				del config.conf['pcspim']["r%d" % r]

		super(SpimSettingsDialog, self).onOk(evt)

# CONSOLE EDITBOX MODULE

class ConsoleEditBox(IAccessible):
	# This overrides the class used to represent the Console edit box.
	# It allows us to read aloud new text as it appears in the dialog.
	
	# Recite new text on arrival
	def event_valueChange(self):

		tones.beep(330,50)	
		curTextLength=len(self.value)
		try:
			test = self.appModule.lastTextLength
		except AttributeError:
			self.appModule.lastTextLength = 0

		log.info("The currently expected last length is %d" % self.appModule.lastTextLength)		
		if (self.appModule.lastTextLength != curTextLength):

			# If the new length is greater, simply announce the new text.
			if (self.appModule.lastTextLength < curTextLength):
				newStr = self.value[self.appModule.lastTextLength:]
			# Otherwise, announce the entire thing
			else:
				newStr = self.value
			log.info("Console updated: %s" % newStr)
			ui.message(newStr)

			log.info("the new length is %d" % curTextLength)
			self.appModule.lastTextLength=curTextLength
			log.info("The new last length is %d" % self.appModule.lastTextLength)

		super(ConsoleEditBox,self).event_valueChange()
