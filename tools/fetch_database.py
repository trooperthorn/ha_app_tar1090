"""Download and verify the pinned public database only during image builds."""
import hashlib
import io
import json
from pathlib import Path
import sys
import urllib.request
import zipfile

versions = json.loads((Path(__file__).resolve().parents[1]/'tar1090/versions.json').read_text())
url = 'https://codeload.github.com/wiedehopf/tar1090-db/zip/' + versions['database']
with urllib.request.urlopen(url, timeout=120) as response:
    data = response.read(100 * 1024 * 1024)
if hashlib.sha256(data).hexdigest() != versions['database_archive_sha256']:
    raise ValueError('database archive checksum mismatch')
destination = Path(sys.argv[1]).resolve()
with zipfile.ZipFile(io.BytesIO(data)) as archive:
    for member in archive.infolist():
        relative = Path(*Path(member.filename).parts[1:])
        target = (destination/relative).resolve()
        if not target.is_relative_to(destination): raise ValueError('unsafe archive path')
        if member.is_dir(): target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(member))
