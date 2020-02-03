# SPIM Research Project 
# Experiment 1

# Participant Instructions:
# Run the code, retrieve the output from the console, and paste it into a Notepad document.
# Save the Notepad document in the Documents folder on the machine as "Program Output.txt".

.data 
# ASCII variables containing strings for output
starting: .asciiz "Once upon a time there was a program called SPIM Version "
ending: .asciiz "It lived accessibly ever after.\nYou've completed Experiment 1."
newLine: .asciiz "\n" 

.text 

main: 
li $v0, 4
la $a0, starting
syscall 
li $v0, 1
li $a0, 9
syscall 
li $v0, 4
la $a0, newLine
syscall
la $a0, ending
syscall 
li $v0, 5 
syscall 

# Exit program
li $v0, 10 
syscall 