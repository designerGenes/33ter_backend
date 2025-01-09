# when this script is launched, it will:
# 1. fire off the submitToAzure.py script
# 2. when this script finishes, run the submitToOpenAI.py script
# 3. when this script finishes, run the display_solution.py script

import subprocess

# fire off the submitToAzure.py script
subprocess.run(["python3", "scripts/submitToAzure.py"])

# when this script finishes, run the submitToOpenAI.py script
subprocess.run(["python3", "scripts/submitToOpenAI.py"])

