import base64
import hashlib
import io
import json
from pathlib import Path
import tarfile
import urllib.request

root=Path(__file__).resolve().parents[1]
metadata=json.load(urllib.request.urlopen('https://registry.npmjs.org/markdown-it/14.1.0',timeout=30))
blob=urllib.request.urlopen(metadata['dist']['tarball'],timeout=60).read()
assert 'sha512-'+base64.b64encode(hashlib.sha512(blob).digest()).decode()==metadata['dist']['integrity']
target=root/'web/vendor'
target.mkdir(parents=True,exist_ok=True)
with tarfile.open(fileobj=io.BytesIO(blob)) as tar:
    for name in ('dist/markdown-it.min.js','LICENSE'):
        (target/('MARKDOWN-IT-LICENSE.txt' if name=='LICENSE' else 'markdown-it.min.js')).write_bytes(tar.extractfile('package/'+name).read())
print('markdown-it 14.1.0 integrity verified; browser asset and license installed')
