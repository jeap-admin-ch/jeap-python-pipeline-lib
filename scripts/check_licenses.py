import json
import subprocess


def check_licenses():
    # List of licenses compatible with Apache 2.0
    compatible_licenses = [
        "Apache-2.0", "MIT", "MIT License", "BSD-2-Clause", "BSD-3-Clause", "ISC", "Zlib",
        "Apache Software License", "Python Software Foundation License",
        "Historical Permission Notice and Disclaimer (HPND)", "Mozilla Public License 2.0 (MPL 2.0)",
        "ISC License (ISCL)", "Public Domain", "BSD License", "GNU Library or Lesser General Public License (LGPL)",
        "Apache-2.0 OR BSD-3-Clause", "LGPL 2.1", "GNU Lesser General Public License v2 or later (LGPLv2+)",
        "Apache License 2.0", "Dual-licensed under GPLv3 or Apache 2.0", "GNU General Public License (GPL)",
        "GNU General Public License v2 (GPLv2)", "GNU Lesser General Public License v3 (LGPLv3)",
        "3-Clause BSD License", "GNU GPL", 'GNU Lesser General Public License v2 (LGPLv2)', 'gpl', 'GPLv3', 'GPL-3',
        'GPL v2 or later', 'UNKNOWN'
    ]

    # List of packages to ignore
    # python-debian has a semicolon in license field which breaks the license check
    ignored_packages = ['python-debian']

    # Run pip-licenses and save the output to a JSON file
    command = ["pip-licenses", "--from=mixed", "--format=json", "--output-file=licenses.json"]

    if ignored_packages:
        command.append("--ignore-packages")
        command.extend(ignored_packages)

    subprocess.run(command, check=True)

    # Load the JSON file
    with open('licenses.json', 'r') as file:
        data = json.load(file)

    # Check the licenses
    for package in data:
        licenses = package['License'].split('; ')
        if not any(license in compatible_licenses for license in licenses):
            print(f"Incompatible license found: {package['Name']} - {package['License']}")
            exit(1)

    print("All licenses are compatible.")

    # Generate the THIRD-PARTY-LICENSES.md file
    subprocess.run(["pip-licenses", "--from=mixed", "--format=markdown", "--output-file=THIRD-PARTY-LICENSES.md"], check=True)

    print("THIRD-PARTY-LICENSES.md has been successfully created.")


if __name__ == "__main__":
    check_licenses()
