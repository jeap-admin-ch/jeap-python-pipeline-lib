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

    # List of packages to ignore
    # Jeepney is licensed under MIT (https://pypi.org/project/jeepney/), but cannot be seen by pip-licenses
    # typing_extensions is licensed under PSFL (https://pypi.org/project/typing-extensions/)
    # urllib3 is licensed under MIT (https://pypi.org/project/urllib3/)
    ignored_packages = ["Jeepney", "typing_extensions", "urllib3"]

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
