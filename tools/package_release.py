"""Stage the standalone exe, notices and checksums for GitHub Releases."""
import hashlib
from pathlib import Path
import shutil
import zipfile

root = Path(__file__).resolve().parent.parent
output = root/'release'/'v1.0.0'
output.mkdir(parents=True, exist_ok=True)
executable = root/'dist'/'WeChatJumpAssistant-Windows-x64.exe'
notices = root/'build'/'license-notices'
if not executable.is_file() or not notices.is_dir():
    raise SystemExit('Run build-release.cmd first.')
shutil.copy2(executable, output/executable.name)
archive = output/'THIRD_PARTY_LICENSES.zip'
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
    for file in sorted(notices.rglob('*')):
        if file.is_file():
            bundle.write(file, Path('THIRD_PARTY_LICENSES')/file.relative_to(notices))
with zipfile.ZipFile(archive) as bundle:
    assert bundle.testzip() is None
files = [output/executable.name, archive]
checksums = ''.join(hashlib.sha256(file.read_bytes()).hexdigest()+'  '+file.name+'\n' for file in files)
(output/'SHA256SUMS.txt').write_text(checksums, encoding='ascii')
for file in files:
    print(file.name, file.stat().st_size, 'bytes')
print(checksums, end='')
