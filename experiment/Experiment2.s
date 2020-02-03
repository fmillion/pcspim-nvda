# SPIM Research Project 
# Experiment 2

# Participant Instructions:
# Run the code.
# After entering a number and pressing Enter, locate the requested register in the registers view.
# Open Notepad and write down both the number you entered and the (hex) representation of the register.
# You do not have to translate hex into decimal nor do you have to actually figure out and write down what 
# transformation(s) occurred on the data.
# Save this file under some name.

.data
prompt1: .asciiz "Please input a number: "
out1: .asciiz "Thank you. Now go check the value of register k0.\nCan you tell what we did?\nRemember, the registers are in hex!\n"

.text
main:

# Print the initial prompt and gather input from the user
li $v0, 4
la $a0, prompt1
syscall
li $v0, 5
syscall
move $t0, $v0

# Do some work on that number
li $t1, 5
mul $t2, $t0, $t1
move $k0, $t2

# clear the other registers
li $t0, 0
li $t1, 0
li $t2, 0

# Print the final message.
li $v0, 4
la $a0, out1
syscall

# Exit program
li $v0, 10
syscall
