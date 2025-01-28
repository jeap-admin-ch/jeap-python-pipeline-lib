import subprocess
import check_licenses

# Step 1: Update requirements.txt
subprocess.run(["pip", "install", "-r", "requirements.txt", "--upgrade"], check=True)

# Step 2: Build the project using python -m build
subprocess.run(["python", "-m", "build"], check=True)

# Step 3: Run tests
subprocess.run(["pytest"], check=True)

# Step 4: Check licenses
check_licenses.check_licenses()
