#!/usr/bin/env python3
"""
Downloads the small Vosk offline STT models for Hindi and English
into models/hi/ and models/en/ if they are missing.
Run automatically by run.bat, or manually:  python setup_models.py
"""
import os, sys, zipfile, shutil, tempfile, urllib.request

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, 'models')
os.makedirs(MODELS_DIR, exist_ok=True)

MODELS = [
    ('en', 'https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip',
           'vosk-model-small-en-us-0.15',
           'English (en) — vosk-model-small-en-us-0.15  [~40 MB]'),
    ('hi', 'https://alphacephei.com/vosk/models/vosk-model-small-hi-0.22.zip',
           'vosk-model-small-hi-0.22',
           'Hindi (hi)   — vosk-model-small-hi-0.22      [~42 MB]'),
]

def is_present(code):
    p = os.path.join(MODELS_DIR, code)
    if not os.path.isdir(p): return False
    return (os.path.exists(os.path.join(p, 'am', 'final.mdl')) or
            os.path.exists(os.path.join(p, 'conf', 'mfcc.conf')))

def download(url, dest_zip):
    print(f'  downloading {url}')
    def _hook(block_num, block_size, total_size):
        if total_size > 0:
            done = block_num * block_size
            pct  = min(100, int(done * 100 / total_size))
            sys.stdout.write(f'\r  progress: {pct:3d}%   ')
            sys.stdout.flush()
    urllib.request.urlretrieve(url, dest_zip, reporthook=_hook)
    sys.stdout.write('\r  download complete.              \n')

def extract_into(zip_path, target_dir):
    os.makedirs(target_dir, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(td)
        entries = os.listdir(td)
        src = None
        for e in entries:
            p = os.path.join(td, e)
            if os.path.isdir(p) and e.startswith('vosk-model'):
                src = p; break
        if src is None and entries:
            src = os.path.join(td, entries[0])
        if src is None or not os.path.isdir(src):
            raise RuntimeError('unexpected archive structure')
        for item in os.listdir(src):
            shutil.move(os.path.join(src, item), os.path.join(target_dir, item))

def main():
    print('=' * 66)
    print('  iTANTRA — Offline STT model setup')
    print('=' * 66)
    any_download = False
    for code, url, top, label in MODELS:
        target = os.path.join(MODELS_DIR, code)
        if is_present(code):
            print(f'  [OK]      {label}')
            continue
        print(f'  [MISSING] {label}')
        any_download = True
        try:
            with tempfile.TemporaryDirectory() as td:
                zpath = os.path.join(td, 'model.zip')
                download(url, zpath)
                print(f'  extracting into models/{code}/ ...')
                extract_into(zpath, target)
            print(f'  [DONE]    {label}\n')
        except Exception as e:
            print(f'  [FAILED]  {label}')
            print(f'            {e}')
            print(f'            You can manually extract the model into models/{code}/\n')

    if not any_download:
        print('  All models already present.')

    print('-' * 66)
    print('  Current status:')
    for code, _, _, _ in MODELS:
        print(f'    models/{code}/  {"READY" if is_present(code) else "MISSING"}')
    print('=' * 66)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\n[!] cancelled by user')
        sys.exit(1)