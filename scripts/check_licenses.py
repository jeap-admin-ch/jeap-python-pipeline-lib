import json
import subprocess
import argparse

def add_args(command: list[str], ignored_packages: list[str], target_python):
    # Add optional --python argument
    if target_python:
        print("Checking licenses using target python {}".format(target_python))
        command.append(f"--python={target_python}")

    if ignored_packages:
        command.append("--ignore-packages")
        command.extend(ignored_packages)


def check_licenses(target_python=None):
    # List of licenses compatible with Apache 2.0
    compatible_licenses = [
        "Apache Software License",
        "Apache-2.0",
        "BSD License",
        "GNU General Public License (GPL)",
        "MIT",
        "MIT License",
        "Mozilla Public License 2.0 (MPL 2.0)",
        "Public Domain",
    ]

    # List of packages to ignore
    ignored_packages = [
        'SecretStorage',        # BSD License – PyPI und GitHub
        'cffi',                 # MIT No Attribution – GitHub LICENSE-Datei
        'cryptography',         # Dual-Lizenz: Apache License 2.0 oder BSD License – GitHub
        'jaraco.functools',     # MIT License – SUSE Package Hub und GitHub
        'jeepney',              # MIT License – SUSE und GitLab
        'more-itertools',       # MIT License – GitHub und MSYS2
        'typing_extensions',    # Python Software Foundation License Version 2 – GitHub
        'urllib3',              # MIT License – GitHub LICENSE.txt
        'zipp',                 # MIT License – PyPI und GitHub
        'idna',                 # BSD 3
        'python-debian'         # GNU General Public License v2 or later – Debian Policy
    ]

    # Run pip-licenses and save the output to a JSON file
    command = ["pip-licenses", "--partial-match", "--from=mixed", "--format=json", "--output-file=licenses.json"]
    add_args(command, ignored_packages, target_python)

    subprocess.run(command, check=True)

    # Load the JSON file
    with open('licenses.json', 'r') as file:
        data = json.load(file)

    # Check the licenses
    for package in data:
        print(f"Checking package: {package['Name']} with license: {package['License']}")
        license_text = package['License']
        licenses = [lic.strip() for lic in license_text.split(';')]

        if not any(any(compatible in lic for compatible in compatible_licenses) for lic in licenses):
            print(f"Incompatible license found: {package['Name']} - {license_text}")
            exit(1)

    print("All licenses are compatible.")

    # Generate the THIRD-PARTY-LICENSES.md file
    markdown_command = ["pip-licenses", "--from=mixed", "--format=markdown", "--output-file=THIRD-PARTY-LICENSES.md"]
    add_args(markdown_command, ignored_packages, target_python)
    subprocess.run(markdown_command, check=True)

    # Dump contents of THIRD-PARTY-LICENSES.md to console
    with open('THIRD-PARTY-LICENSES.md', 'r') as md_file:
        print(md_file.read())

    print("THIRD-PARTY-LICENSES.md has been successfully created.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check licenses for Python dependencies.")
    parser.add_argument(
        "--target-python",
        dest="target_python",
        help="Path to the target Python interpreter (e.g. .venv/bin/python)",
        required=False
    )
    args = parser.parse_args()

    check_licenses(args.target_python)
