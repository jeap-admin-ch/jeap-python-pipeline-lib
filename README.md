# jeap-python-pipeline-lib

Welcome to the project documentation.
This is a collection of Python modules and libraries for CI/CD pipelines with jEAP context.
For more details about the library, please refer to the [modules documentation](docs/index.md).

## Local Development

### Setup

1. Clone the repository:
    ```bash
    git clone https://github.com/jeap-admin-ch/jeap-python-pipeline-lib.git
    cd jeap-python-pipeline-lib
    ```

2. Create a virtual environment and activate it:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3. Install the dependencies:
    ```bash
    pip install -r requirements.txt
    ```

4. Or to install just the tools use:
    ```bash
    pip install build twine pip-licenses pytest
    ```

### Development basics

* **Adding New Modules**:
    - Create a new Python file in the `src/jeap_pipeline/` directory.
    - Ensure the new module has a corresponding test file in the `tests/` directory.
    - Follow the naming conventions and structure of existing modules.

* **Writing Documentation**:
    - Add docstrings to all public classes and functions.
    - Update the `CHANGELOG.md` with any new features or changes.
    - If necessary, add detailed documentation in the `docs/` directory.

* **Changing the Version**:
    - Update the version number in the `pyproject.toml` file.
    - Ensure the version number complies with semantic versioning and the PEP 440 standard.

* **Add new dependencies**:
    - Add the dependency to the `requirements.txt` file.
    - Ensure the license of the dependency is compatible with the project's license.
    - Keep the THIRD-PARTY-LICENSES.md file up to date.

### Build

To combine the build with automated testing and the generation of the THIRD-PARTY-LICENSES.md file, run the following command:

```bash
python3 scripts/full_build.py
```
If you did like to execute single steps, you can use the following commands.
A more comprehensive documentation can be found here: https://packaging.python.org/en/latest/tutorials/packaging-projects/

Install the build tool via pip. Make sure you have the latest version of PyPA’s build installed:
```bash
pip install build
```
To create the package run this command from the same directory where pyproject.toml is located:
```bash
python -m build
```
This command should generate two files in the dist directory. The tar.gz file is a source distribution whereas the .whl file is a built distribution.

### Test

To run the tests, use the following command:
```bash
python3 -m pytest
```

### Upload

It should be noted that the publishing process takes place automatically in the pipeline. The following steps are only necessary for manual publishing.

First install twine via pip:
```bash
python3 -m pip install --upgrade twine
```

Once installed, run Twine to upload all the archives under dist:
```bash
python3 -m twine upload --repository testpypi dist/*
```
Use testpypi to upload the package to test instance of PyPI. To upload to the real PyPI repository, use pypi instead of testpypi.
You will be prompted for an API token. Use the token value, including the pypi- prefix.

### Package installation

You can use pip to install your package and verify that it works. Create a virtual environment and install your package from TestPyPI:
```bash
python3 -m pip install -i https://test.pypi.org/simple/ jeap-pipeline==0.1.0
```

### Check licenses of dependencies and generate THIRD-PARTY-LICENSES.md

To check the licenses of the dependencies and generate the THIRD-PARTY-LICENSES.md file, run the following command:
```bash
python3 scripts/check_licenses.py
```

## Publishing

### Versioning
The version can be set in the pyproject.toml file. The version number has to comply with semantic versioning and the PEP 440 standard.
On every push a CI pipeline is triggered, which builds and uploads the artifact to the (test)-pypi repository.
* On the main branch, the version number remains unchanged and the artifact is published as a stable release to pypi.
* On feature branches, a valid development release suffix (.dev<timestamp>) is added to the version. The artifact is published to TestPyPI.

### Publishing via GitHub Actions
The publishing process is automated using GitHub Actions. The CI pipeline is defined in the `.github/workflows/publish.yml` file. The key steps involved are:

1. **Setup Python Environment**: The pipeline sets up the Python environment using the specified version in the `pyproject.toml` file.
2. **Install Dependencies**: All necessary dependencies are installed using `pip`.
3. **Run Tests**: The test suite is executed to ensure the code is functioning as expected.
4. **Generate Version**: The version number is generated based on the branch name.
5. **Generate License File**: The license file is generated using the `third_party_license_file_generator` tool.
6. **Build Package**: The package is built using `python -m build`.
7. **Upload to PyPI**: The built package is uploaded to PyPI or TestPyPI using `twine`.

## Project Files

* `LICENSE`
Contains the license information for the project.

* `MANIFEST.in`
Specifies additional files to include in the distribution package.

* `pyproject.toml`
Modern configuration file for build systems. Contains metadata and dependencies of the project.

* `requirements.txt`
Lists the dependencies for development and testing.

* `THIRD-PARTY-LICENSES.md`
Generated file that lists the licenses of third-party dependencies.

