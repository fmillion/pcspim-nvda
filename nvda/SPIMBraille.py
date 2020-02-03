# SPIM Braille Extensions for NVDA
# v0.01.3 
# last update 11/14/2013

# Idiot-proofing - prevent script from being run directly.
# This is placed first because if being directly executed, NVDA imports
#   will be unavailable and will cause an exception.
if (__name__ == "__main__"):
	print "SPIM Braille Support v0.01.3"
	print
	print "This is not a standalone script. Exiting."
	exit()

# Python imports
import socket, re

# NVDA imports
import braille
from logHandler import log

# Log loading of driver
log.info("Loading SPIM Braille support")

# This class extends the existing Braille driver to add the extended SPIM
# functionality.
# Drivers can essentially be copied and modified slightly to add this support.
# TODO: allow this driver to wrap other drivers, negating the need to rewrite
# any existing Braille driver code.
class SPIMBrailleDisplayDriver(braille.BrailleDisplayDriver):
	"""Braille display driver supporting SPIM Braille extensions for display of 32-bit hex registers"""
	name = ""
	description = _("SPIM Braille")

	# SPIM Braille support will default to being available. A derived class
	# can set this to False during its init method if SPIM Braille isn't
	# going to work. (i.e. 'self.hasSPIM = False')
	# This will signal to any app module using the extension that it should not
	# make any use of SpimBraille.
	hasSPIM = True

	@classmethod
	def check(cls):
		# In the superclass, this will return false to prevent NVDA from thinking the superclass is an actual available driver.
		# You MUST override this in any subclass and return True to enable the display.
		return False

	def getRegisterCount(self):
		"""Returns the number of registers available for display."""
		# The self.registers variable MUST be initialized as a list of Nones with a length being the number of available registers.
		return len(self.registers)
	
	# This method emulates the existing Braille driver "display" method, but adds in
	# the register displays prior to feeding data back to the actual display driver.
	# A class working with this driver can call this method with the same data it has been
	# passed by NVDA to prepare output data containing the registers.
	# That data can then be actually put up on the display.
	def display(self,cells, noSeparators=False):
		self.lastCells = cells[:] # Store the cells for later display (upon register changes)
		
		# Now, we append the register cells...
		if (self.hasSPIM == True):
			for r in self.registers:
				if (noSeparators == False): cells.extend([255])
				if (type(r) is str):
					cells.extend([ord(x) for x in r[0:8]])
				elif (r is None):
					# Default to a list of 8 blank cells
					cells.extend([0]*8)
				else:
					# If a number is contained in the variable, display it.
					cells.extend( numToBraille(r) )
			if (noSeparators == False):  cells.extend([255])

		# Extremely verbose logging. Don't use debug level with this unless you need to.
		log.debug("Displaying %d cells: %s" % (len(cells),[str(x) for x in cells]))

		return cells

	def setAllRegisters(self, regs):
		"""Sets all registers at the same time. Accepts a list which must be the same length as the number of registers for this display."""

		if (self.hasSPIM == False): return # If we have no SpimBrl support, do nothing.

		# Determine length of regs and cause error if invalid
		if (len(regs) > len(self.registers)):
			raise ValueError("Too many registers provided")

		# If we got nothing, do nothing. :-)
		if (len(regs) == 0):
			return # do nothing
		
		# Examine each register, and place it into a local register
		for i in range(len(regs)):
			self.setRegister(i, regs[i], False)
		
		# Finally, update all registers
		# 'lastcells' contains the last thing the display was requested to display from NVDA.
		self.display(self.lastCells)
		
	def setRegister(self, regNum, data, updateNow=True):

		if (self.hasSPIM == False): return # If we have no SpimBrl support, do nothing.

		# If we got nothing, store nothing.
		if (data is None): 
			self.registers[regNum] = None

		elif (type(data) is int): # We only process ints here; use setRegister_raw for actual cell bytes.
			# Set register data to a value

			# If we can't set this register, log a warning.
			if (regNum >= (len(self.registers))):
				log.warn("SpimBraille ERROR: application tried to set register %d, but only %d registers available." % (regNum, len(self.registers)))
				return
		
			# All data seems to have checked out - go ahead and update register.
			self.registers[regNum] = data

		else:
			# Got a string. Hopefully it contains 8 raw bytes of data representing the contents of the register. :-)
			# TODO: maybe some typechecking/data verification?
			
			data = str(data) # convert to a string explicitly, also eliminate unicode

			# Cleanse the data - prepend 0's and chop off strings that are too long
			data = data[:8].ljust(8,'\x00')
		
			# Set the register
			self.registers[regNum] = data 
		
		# Call a display to update the display with a new register.
		if (updateNow==True):
			self.display(self.lastCells)
	
def numToBraille(num,desiredLength=8):
	"""Convenience method to translate an integer into a set of characters representing Braille cells"""

	# Convert number to hex
	num = hex(num)[2:]
	
	# Create a string by taking only up to 8 characters and then padding on the left out with 0's.
	s = num[0:8].zfill(8)

	# Braille map...
	numMap = { '1': 0x02, '2': 0x06, '3': 0x12, '4': 0x32, 
			   '5': 0x22, '6': 0x16, '7': 0x36, '8': 0x26,
			   '9': 0x14, '0': 0x34, 'a': 0x01, 'b': 0x03, 
			   'c': 0x09, 'd': 0x19, 'e': 0x11, 'f': 0x0b}
	out = []

	# Iterate through the string and apply the Braille map to get the desired output characters.	
	for c in s:
		if (c in numMap.keys()):
			out.append(numMap[c])
		else:
			out.append(252) # A Braille "for" sign will be used for invalid characters.

	# VERBOSE - debug  is only for the faint of heart.
	log.debug("Converted '%s' to: %s" % (s, " ".join([str(hex(x)) for x in [ord(y) for y in out]]) ) ) 		

	return out
