"""Collect verbatim redistribution notices for the frozen Windows bundle."""
from importlib import metadata
import json
from pathlib import Path
import shutil
import sys
import tkinter

root = Path(__file__).resolve().parent.parent
output = root/'build'/'license-notices'
output.mkdir(parents=True, exist_ok=True)
manifest = {}

for package in ('numpy', 'opencv-python', 'Pillow', 'pyinstaller', 'pyinstaller-hooks-contrib'):
    distribution = metadata.distribution(package)
    copied = []
    for item in distribution.files or ():
        relative = Path(str(item))
        if '..' in relative.parts:
            continue
        lower = relative.as_posix().lower()
        basename = relative.name.lower()
        if not ('/licenses/' in lower or basename.startswith(('license', 'copying', 'notice', 'copyright'))):
            continue
        source = Path(distribution.locate_file(item))
        if source.is_file() and source.suffix.lower() not in ('.pyc', '.dll', '.exe', '.pyd'):
            destination = output/package/relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied.append(relative.as_posix())
    if not copied:
        raise RuntimeError('No license found for '+package)
    manifest[package] = {'version': distribution.version, 'files': copied}

python_license = Path(sys.base_prefix)/'LICENSE.txt'
if not python_license.is_file():
    raise RuntimeError('CPython license not found')
(output/'Python').mkdir(exist_ok=True)
shutil.copy2(python_license, output/'Python'/'LICENSE.txt')
manifest['Python'] = {'version': sys.version.split()[0]}

tcl_root = Path(tkinter.Tcl().eval('info library')).parent
tcl_notices = list(tcl_root.rglob('license.terms'))
if not tcl_notices:
    raise RuntimeError('Tcl/Tk licenses not found')
for source in tcl_notices:
    destination = output/'Tcl-Tk'/source.relative_to(tcl_root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)

for relative in ('LICENSE', 'NOTICE', 'third_party/LICENSE', 'third_party/NOTICE', 'third_party/SOURCE.txt'):
    destination = output/'project'/relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root/relative, destination)

(output/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
(output/'README.txt').write_text(
    'WeChat Jump Assistant - bundled runtime and dependency notices\n\n'
    'Original notice texts are retained under each component directory.\n'
    'Project source: https://github.com/Casie-Liu/wechat-jump-assistant\n'
    'Python: https://www.python.org/\n'
    'NumPy: https://numpy.org/\n'
    'OpenCV Python: https://github.com/opencv/opencv-python\n'
    'Pillow: https://github.com/python-pillow/Pillow\n'
    'Tcl/Tk: https://www.tcl.tk/\n'
    'PyInstaller bootloader source and exception: https://github.com/pyinstaller/pyinstaller/tree/v6.22.3\n',
    encoding='utf-8')
print('Collected', len(list(output.rglob('*'))), 'notice files/directories')
