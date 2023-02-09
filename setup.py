from setuptools import setup, find_packages
from timecard.__init__ import version

setup(name='timecard',
      version=f'{version}',
      packages=find_packages(),
      install_requires=['selenium', 'keyring', 'asciimatics'],
      entry_points={
          'console_scripts': ['timecard = timecard.tui_main:main']
      }
      )
