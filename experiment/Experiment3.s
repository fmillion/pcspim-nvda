# SPIM Research Project 
# Experiment 3

# Participant Instructions:
# When you run the code, instructions will be printed.
# Locate the line of code in the program within PC Spim that is being requested.
# Copy the line of code into a text document, 
# You only want the actual code from the assembly, e.g. "li $t0, 2"

.data
out1: .asciiz "We've done some calculations on a number, and the results are: "
out2: .asciiz "\nSee if you can find what number we started with!\nHint, We loaded the number into the register t0."

.text
main:

# Print the initial prompt and gather input from the user
li $v0, 4
la $a0, out1
syscall

# Do some work on a number
li $t0,92
li $t1, 2
mul $t2, $t0, $t1
li $t1, -12
add $t0, $t2, $t1
li $t1, 0
li $t2, 0

# Print the final message.
li $v0, 1
move $a0, $t0
syscall
li $v0, 4
la $a0, out2
syscall

# Exit program
li $v0, 10
syscall
