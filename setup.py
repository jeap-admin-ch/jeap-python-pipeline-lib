# **setup.py**

from setuptools import setup, find_packages

setup(
    name='jeap-python-pipeline-lib',
    version='0.1.0',
    packages=find_packages(),
    install_requires=[],
    author='Dein Name',
    author_email='laris.jacobs@bit.admin.ch',
    description='Eine Sammlung von Python-Modulen und -Bibliotheken für CI/CD-Pipelines im jEAP-Kontext.',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    url='https://github.com/jeap-admin-ch/jeap-python-pipeline-lib',
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.6',
)
