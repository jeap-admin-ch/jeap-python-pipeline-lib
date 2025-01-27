# jeap-python-pipeline-lib
Das Git-Repository jeap-python-pipeline-lib ist strukturiert, um mehrere Python-Module und -Bibliotheken zu enthalten, die als Library auf PyPI bereitgestellt werden und für CI/CD-Pipelines im jEAP-Kontext verwendet werden können.

## Build

The full documentation can be found here: https://packaging.python.org/en/latest/tutorials/packaging-projects/

Install the build tool via pip. Make sure you have the latest version of PyPA’s build installed:
```bash
pip install build
```
To create the package run this command from the same directory where pyproject.toml is located:
```bash
python -m build
```
This command should generate two files in the dist directory. The tar.gz file is a source distribution whereas the .whl file is a built distribution.

## Upload

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

## Package installation

You can use pip to install your package and verify that it works. Create a virtual environment and install your package from TestPyPI:
```bash
python3 -m pip install -i https://test.pypi.org/simple/ jeap-pipeline==0.1.0
```

