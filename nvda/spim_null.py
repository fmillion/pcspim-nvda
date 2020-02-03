#brailleDisplayDrivers/noBraille.py
#A part of NonVisual Desktop Access (NVDA)
#Copyright (C) 2006-2009 NVDA Contributors <http://www.nvda-project.org/>
#This file is covered by the GNU General Public License.
#See the file COPYING for more details.

import SPIMBraille

class BrailleDisplayDriver(SPIMBraille.SPIMBrailleDisplayDriver):
	"""A dummy braille display driver used to disable braille in NVDA.
	"""
	name = "spim_null"
	# Translators: Is used to indicate that braille support will be disabled.
	description = _("SPIM Braille (Null)")

	@classmethod
	def check(cls):
		return True

	def __init__(self, port="auto"):

		self.actualNumCells = 8		
		self.registers = [None]
		self.numCells = 0
