#!/usr/bin/env python3
"""
iTANTRA — Judge-Ready Packager
Drop this script into your itantra project folder (the one with app.py)
and run it. It will:
  1. Download the Vosk Hindi + English models if missing
  2. Verify the project structure
  3. Pack EVERYTHING (including models) into one ZIP
  4. Leave you with a judge-ready, fully-offline package.
"""
import os, sys, io, time, zipfile, shutil, socket, urllib.request

# =====================================================================
#  CONFIG
# =====================================================================
ZIP_NAME   = 'iTANTRA_JUDGE_READY.zip'
OUTER_DIR  = 'iTANTRA_SIH2026_PS173'

MODELS = [
    ('en',
     'https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip',
     'English (en) — vosk-model-small-en-us-0.15  [~40 MB]'),
    ('hi',
     'https://alphacephei.com/vosk/models/vosk-model-small-hi-0.22.zip',
     'Hindi (hi)   — vosk-model-small-hi-0.22      [~42 MB]'),
]

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR   = os.path.join(PROJECT_ROOT, 'models')
ZIP_PATH     = os.path.join(PROJECT_ROOT, ZIP_NAME)

# Folders that must exist in the final package (created empty if needed)
RUNTIME_DIRS = ['uploads', 'generated_audio', 'data', 'models']

# Folders/files we do NOT want inside the ZIP
EXCLUDE_DIRS  = {'.venv', '__pycache__', '.git', '.idea', '.vscode'}
EXCLUDE_FILES = {ZIP_NAME, 'MAKE_JUDGE_ZIP.py', 'build_itantra.py'}

# =====================================================================
#  1. VERIFY WE'RE IN THE RIGHT FOLDER
# =====================================================================
def verify_project():
    required = ['app.py', 'run.bat', 'requirements.txt', 'templates']
    missing  = [r for r in required
                if not os.path.exists(os.path.join(PROJECT_ROOT, r))]
    if missing:
        print('=' * 66)
        print('  [ERROR] Wrong folder.')
        print('=' * 66)
        print('  This script must sit next to  app.py  and  run.bat .')
        print('  Missing:', ', '.join(missing))
        print()
        print('  Current folder:', PROJECT_ROOT)
        print('  Move MAKE_JUDGE_ZIP.py into the itantra project folder')
        print('  (the one containing app.py) and run it again.')
        print('=' * 66)
        sys.exit(1)
    print(f'  [OK] Project root: {PROJECT_ROOT}')

# =====================================================================
#  2. DOWNLOAD MODELS
# =====================================================================
def model_present(code):
    p = os.path.join(MODELS_DIR, code)
    if not os.path.isdir(p):
        return False
    return (os.path.exists(os.path.join(p, 'am', 'final.mdl')) or
            os.path.exists(os.path.join(p, 'conf', 'mfcc.conf')))

def human_mb(n):
    return f'{n / (1024 * 1024):.1f} MB'

def download(url, dest_zip):
    print(f'    downloading {url}')
    start = time.time()
    last_print = [0.0]
    def hook(block_num, block_size, total_size):
        if total_size <= 0:
            return
        done = block_num * block_size
        pct  = min(100, int(done * 100 / total_size))
        now  = time.time()
        # print at most 5 times per second
        if now - last_print[0] > 0.2 or pct >= 100:
            last_print[0] = now
            bar_len = 30
            filled  = int(bar_len * pct / 100)
            bar = '#' * filled + '-' * (bar_len - filled)
            speed = done / max(0.001, now - start)
            sys.stdout.write(
                f'\r    [{bar}] {pct:3d}%  '
                f'{human_mb(done)} / {human_mb(total_size)}  '
                f'({human_mb(speed)}/s)   ')
            sys.stdout.flush()
    urllib.request.urlretrieve(url, dest_zip, reporthook=hook)
    sys.stdout.write('\n')

def extract_into(zip_path, target_dir):
    os.makedirs(target_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(target_dir)
    # Vosk archives unpack into a subfolder; hoist contents up
    entries = os.listdir(target_dir)
    subdirs = [e for e in entries if e.startswith('vosk-model')]
    if subdirs:
        src = os.path.join(target_dir, subdirs[0])
        for item in os.listdir(src):
            shutil.move(os.path.join(src, item),
                        os.path.join(target_dir, item))
        os.rmdir(src)

def ensure_models():
    print()
    print('-' * 66)
    print('  STEP 1/3 · Downloading offline STT models')
    print('-' * 66)
    os.makedirs(MODELS_DIR, exist_ok=True)
    for code, url, label in MODELS:
        print(f'  {label}')
        if model_present(code):
            print(f'    [OK] already present in models/{code}/')
            continue
        try:
            # download to a temp zip next to models dir
            tmp_zip = os.path.join(MODELS_DIR, f'_tmp_{code}.zip')
            download(url, tmp_zip)
            print(f'    extracting into models/{code}/ ...')
            extract_into(tmp_zip, os.path.join(MODELS_DIR, code))
            try: os.remove(tmp_zip)
            except Exception: pass
            if model_present(code):
                print(f'    [OK] {code} ready.')
            else:
                print(f'    [WARN] {code} extracted but structure looks off.')
        except Exception as e:
            print(f'    [FAILED] {e}')
            print(f'    You can manually place the model folder into models/{code}/')
        print()

    print('  Model status:')
    for code, _, label in MODELS:
        status = 'READY' if model_present(code) else 'MISSING'
        print(f'    models/{code}/  ->  {status}')
    print('-' * 66)

# =====================================================================
#  3. VERIFY MODELS LOAD (optional, best-effort)
# =====================================================================
def verify_vosk():
    try:
        import vosk
        vosk.SetLogLevel(-1)
    except Exception:
        print('  [SKIP] Vosk not installed locally — cannot verify models.')
        return
    print('  Verifying that Vosk can load each model ...')
    for code, _, _ in MODELS:
        if not model_present(code):
            print(f'    {code}: MISSING — skipping')
            continue
        try:
            m = vosk.Model(os.path.join(MODELS_DIR, code))
            print(f'    {code}: LOADED OK')
            del m
        except Exception as e:
            print(f'    {code}: FAILED — {e}')

# =====================================================================
#  4. ZIP IT UP
# =====================================================================
def should_skip_dir(name):
    return name in EXCLUDE_DIRS

def build_zip():
    print()
    print('-' * 66)
    print('  STEP 3/3 · Building judge-ready ZIP')
    print('-' * 66)
    if os.path.exists(ZIP_PATH):
        print(f'  removing old {ZIP_NAME}')
        os.remove(ZIP_PATH)

    # ensure runtime dirs exist and are non-empty (so they survive zip)
    for d in RUNTIME_DIRS:
        full = os.path.join(PROJECT_ROOT, d)
        os.makedirs(full, exist_ok=True)
        if not os.listdir(full):
            with open(os.path.join(full, '.gitkeep'), 'w') as f:
                f.write('')

    total_files = 0
    total_bytes = 0

    with zipfile.ZipFile(ZIP_PATH, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for root, dirs, files in os.walk(PROJECT_ROOT):
            # prune excluded directories in-place
            dirs[:] = [d for d in dirs if not should_skip_dir(d)]
            for fn in files:
                if fn in EXCLUDE_FILES:
                    continue
                full = os.path.join(root, fn)
                rel  = os.path.relpath(full, PROJECT_ROOT)
                # skip any leftover .zip files inside models/
                if rel.startswith('models' + os.sep) and rel.endswith('.zip'):
                    continue
                arc = os.path.join(OUTER_DIR, rel)
                try:
                    z.write(full, arcname=arc)
                    total_files += 1
                    total_bytes += os.path.getsize(full)
                except Exception as e:
                    print(f'  [WARN] could not add {rel}: {e}')

    size_mb = os.path.getsize(ZIP_PATH) / (1024 * 1024)
    print(f'  Files packed : {total_files}')
    print(f'  Raw size     : {human_mb(total_bytes)}')
    print(f'  ZIP size     : {size_mb:.1f} MB')
    print(f'  ZIP path     : {ZIP_PATH}')
    print('-' * 66)

# =====================================================================
#  5. FINAL NOTE + DROP A START-HERE FILE
# =====================================================================
def write_start_here():
    """Write a plain START_HERE.txt into the project root so it ends
    up inside the ZIP. Judges see it first thing."""
    content = """============================================================
  iTANTRA  -  SIH 2026  -  Problem Statement 173
  JUDGE DEMONSTRATION PACKAGE  (OFFLINE-READY)
============================================================

  QUICK START
  -----------
  1. Extract this ZIP to any folder.
  2. Double-click  run.bat
  3. Wait ~30-60 seconds (models are already bundled — no
     internet needed at all).
  4. The SOLO DEMO page opens automatically in your browser.
  5. Follow the numbered steps on the page.

  The SOLO DEMO shows BOTH Phone A and Phone B side-by-side on
  ONE screen. No second phone required.

  WORKS WITHOUT INTERNET. Works with Wi-Fi off.
  Full instructions in JUDGE_GUIDE.md.

  Requirements: Windows 10/11 + Python 3.10+ installed.
============================================================
"""
    with open(os.path.join(PROJECT_ROOT, 'START_HERE.txt'), 'w',
              encoding='utf-8') as f:
        f.write(content)

# =====================================================================
#  MAIN
# =====================================================================
def main():
    os.system('cls' if os.name == 'nt' else 'clear')
    print('=' * 66)
    print('  iTANTRA — Judge-Ready Packager')
    print('  (offline-ready: models are bundled inside the ZIP)')
    print('=' * 66)
    print()

    verify_project()
    ensure_models()
    verify_vosk()
    write_start_here()
    build_zip()

    print()
    print('=' * 66)
    print('  DONE')
    print('=' * 66)
    print()
    print('  Send this file to the judges:')
    print(f'    {ZIP_PATH}')
    print()
    print('  Share it via Google Drive / OneDrive / USB.')
    print('  (Too large for email — around 85-95 MB.)')
    print()
    print('  Judges do:')
    print('    1. Extract the ZIP.')
    print('    2. Double-click  run.bat  inside.')
    print('    3. Wait ~30-60 seconds. Browser opens SOLO DEMO.')
    print()
    print('  Internet required for judges:  NO')
    print('  Python required:               YES (3.10+)')
    print('=' * 66)
    input('\nPress Enter to exit ...')

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\n[!] cancelled by user')
        sys.exit(1)
    except Exception as e:
        print()
        print('=' * 66)
        print(f'  [ERROR] {e}')
        print('=' * 66)
        import traceback
        traceback.print_exc()
        input('\nPress Enter to exit ...')