"""Install pinned CodeBuddy runtime in user cache, not the source directory."""
import argparse
import base64
import hashlib
import io
import json
import pathlib
import shutil
import tarfile
import urllib.request
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.runtime_paths import physical_file, runtime_cache
VERSION = '2.164.0'
parser = argparse.ArgumentParser()
parser.add_argument('--reuse', type=pathlib.Path)
args = parser.parse_args()
runtime = runtime_cache()/'codebuddy'/VERSION
if not (runtime/'bin/codebuddy').exists():
    if args.reuse and (args.reuse/'bin/codebuddy').is_file():
        package = json.loads((args.reuse/'package.json').read_text(encoding='utf-8'))
        if package.get('version') != VERSION or package.get('name') != '@tencent-ai/codebuddy-code':
            raise RuntimeError('Unexpected runtime package')
        shutil.copytree(args.reuse, runtime, dirs_exist_ok=True)
    else:
        metadata = json.load(urllib.request.urlopen('https://registry.npmjs.org/@tencent-ai%2fcodebuddy-code/'+VERSION, timeout=30))
        blob = urllib.request.urlopen(metadata['dist']['tarball'], timeout=90).read()
        integrity = 'sha512-'+base64.b64encode(hashlib.sha512(blob).digest()).decode()
        if integrity != metadata['dist']['integrity']:
            raise RuntimeError('Runtime integrity mismatch')
        target = runtime.parent/'download'
        target.mkdir(parents=True,exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(blob)) as tar:
            tar.extractall(target,filter='data')
        shutil.copytree(target/'package',runtime,dirs_exist_ok=True)
        # Preserve package in cache; never copy credentials.

icons = ['user-circle','chat-circle-text','arrows-left-right','check-circle','folder-open','gear-six','plus','paper-plane-tilt',
    'stop','file-text','arrow-square-out','magnifying-glass','dots-three','sun','moon','download-simple',
    'clipboard-text','clock','robot','sparkle','arrow-right','x','check','caret-down','sidebar-simple',
    'paperclip','archive','arrow-counter-clockwise','copy','list-checks','arrow-clockwise','shield-check',
    'faders-horizontal','note-pencil','arrow-bend-up-right','lightning','coins','chart-donut','trash','info']
asset_dir = ROOT/'web/assets/icons'
asset_dir.mkdir(parents=True,exist_ok=True)
metadata = json.load(urllib.request.urlopen('https://registry.npmjs.org/@phosphor-icons%2fcore/2.1.1',timeout=30))
blob = urllib.request.urlopen(metadata['dist']['tarball'],timeout=90).read()
integrity = 'sha512-'+base64.b64encode(hashlib.sha512(blob).digest()).decode()
if integrity != metadata['dist']['integrity']:
    raise RuntimeError('Icon package integrity mismatch')
with tarfile.open(fileobj=io.BytesIO(blob)) as tar:
    for name in icons:
        member = tar.getmember('package/assets/regular/'+name+'.svg')
        (asset_dir/(name+'.svg')).write_bytes(tar.extractfile(member).read())
    license_member = next(m for m in tar.getmembers() if m.name.lower()=='package/license')
    (ROOT/'web/assets/PHOSPHOR-LICENSE.txt').write_bytes(tar.extractfile(license_member).read())
physical_runtime = physical_file(runtime/'bin/codebuddy').parents[1]
manifest = {'runtime':{'package':'@tencent-ai/codebuddy-code','version':VERSION,'path':str(physical_runtime)},
    'icons':{'package':'@phosphor-icons/core','version':'2.1.1','integrity_verified':True,'files':icons}}
(ROOT/'runtime-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'runtime_ready':True,'runtime':str(runtime),'icons':len(icons)},ensure_ascii=False))
