from setuptools import setup, find_packages

setup(name='timecard',
      version='0.6',
      packages=find_packages(),
      install_requires=['selenium', 'keyring', 'asciimatics'],
      entry_points={
          'console_scripts': ['timecard = timecard.tui_main:main']
      }
      )
