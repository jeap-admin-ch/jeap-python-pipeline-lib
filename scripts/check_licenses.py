import json
import subprocess


def check_licenses():
    # List of licenses compatible with Apache 2.0
    compatible_licenses = [
        "Apache-2.0", "MIT", "MIT License", "BSD-2-Clause", "BSD-3-Clause", "ISC", "Zlib",
        "Apache Software License", "Python Software Foundation License",
        "Historical Permission Notice and Disclaimer (HPND)", "Mozilla Public License 2.0 (MPL 2.0)",
        "ISC License (ISCL)", "Public Domain", "BSD License", "GNU Library or Lesser General Public License (LGPL)"
    ]

    # Run pip-licenses and save the output to a JSON file
    subprocess.run(["pip-licenses", "--from=mixed", "--format=json", "--output-file=licenses.json"], check=True)

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
