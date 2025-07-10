import sys

if sys.prefix != sys.base_prefix:
    print("You are in a Python virtual environment.")
else:
    print("You are not in a Python virtual environment.")