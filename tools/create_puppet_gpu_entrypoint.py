"""Create a process-local CPython entry point for Windows per-app GPU routing.

Windows venv redirectors execute the shared base python.exe, which can bypass
the venv executable's GPU preference. This private executable uses the same
venv/site-packages without changing GPU preferences for unrelated Python apps.
Run with the destination venv's Python. Recreate after a base Python upgrade.
"""
from pathlib import Path
import shutil
import sys


def main():
    if sys.platform!='win32' or sys.prefix==sys.base_prefix:
        raise RuntimeError('Run this with the isolated Windows puppet venv Python')
    destination=Path(sys.prefix)/'rtx'
    if destination.exists(): raise FileExistsError('GPU entry point already exists; do not overwrite it')
    base=Path(sys._base_executable).parent
    files=['python.exe','python3.dll',f'python{sys.version_info.major}{sys.version_info.minor}.dll',
           'vcruntime140.dll','vcruntime140_1.dll']
    if not all((base/name).is_file() for name in files):
        raise RuntimeError('The base CPython runtime is incomplete')
    destination.mkdir()
    for name in files: shutil.copy2(base/name,destination/name)
    print(destination/'python.exe')


if __name__=='__main__': main()
