from setuptools import setup, find_packages

setup(
    name='file_collector_app',
    version='1.0.0',
    packages=find_packages(),
    install_requires=[
        'customtkinter>=5.0.3',
        'watchdog>=2.1.6',
    ],
    entry_points={
        'console_scripts': [
            'file_collector_app=main:main',
        ],
    },
)
