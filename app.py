#!/usr/bin/env python3
"""
iTANTRA — Offline Neural Transceiver
SIH 2026 · Problem Statement 173
Local prototype: browser UI + laptop-side offline STT/TTS.

Communication demo:  VOICE -> TEXT -> LOW-BANDWIDTH TEXT PACKET -> VOICE
Raw audio is NEVER transmitted between phones.
"""
import os, io, json, time, uuid, wave, shutil, socket, threading, subprocess
from datetime import datetime
from flask import (Flask, request, jsonify, render_template, send_file,
                   send_from_directory, abort)

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR  = os.path.join(BASE_DIR, 'uploads')
AUDIO_DIR   = os.path.join(BASE_DIR, 'generated_audio')
DATA_DIR    = os.path.join(BASE_DIR, 'data')
MODELS_DIR  = os.path.join(BASE_DIR, 'models')
STATIC_DIR  = os.path.join(BASE_DIR, 'static')
HISTORY_FILE = os.path.join(DATA_DIR, 'messages.json')
for d in (UPLOAD_DIR, AUDIO_DIR, DATA_DIR, MODELS_DIR, STATIC_DIR):
    os.makedirs(d, exist_ok=True)

# --------------------------------------------------------------------------
# Optional dependencies (guarded — server never crashes if one is missing)
# --------------------------------------------------------------------------
try:
    import qrcode
    QR_OK = True
except Exception:
    QR_OK = False

try:
    import vosk
    vosk.SetLogLevel(-1)
    VOSK_OK = True
except Exception as e:
    print(f'[WARN] vosk not available: {e}')
    VOSK_OK = False

try:
    import pyttsx3
    PYTTSX3_OK = True
except Exception as e:
    print(f'[WARN] pyttsx3 not available: {e}')
    PYTTSX3_OK = False

FFMPEG_PATH = shutil.which('ffmpeg')
try:
    import imageio_ffmpeg
    FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    pass

ESPEAK_PATH = shutil.which('espeak-ng') or shutil.which('espeak')

# --------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024   # 32 MB

# --------------------------------------------------------------------------
# Languages (PS-173 target list)
# --------------------------------------------------------------------------
LANGUAGES = [
    ('hi', 'Hindi',      'हिन्दी'),
    ('en', 'English',    'English'),
    ('gu', 'Gujarati',   'ગુજરાતી'),
    ('mr', 'Marathi',    'मराठी'),
    ('kn', 'Kannada',    'ಕನ್ನಡ'),
    ('ml', 'Malayalam',  'മലയാളം'),
    ('ta', 'Tamil',      'தமிழ்'),
    ('te', 'Telugu',     'తెలుగు'),
    ('or', 'Odia',       'ଓଡ଼ିଆ'),
    ('bn', 'Bengali',    'বাংলা'),
]
LANG_CODES = [c for c, _, _ in LANGUAGES]

# --------------------------------------------------------------------------
# Vosk model cache (lazy)
# --------------------------------------------------------------------------
_vosk_lock   = threading.Lock()
_vosk_models = {}

def model_dir(code):
    return os.path.join(MODELS_DIR, code)

def model_present(code):
    p = model_dir(code)
    if not os.path.isdir(p):
        return False
    return (os.path.exists(os.path.join(p, 'am', 'final.mdl')) or
            os.path.exists(os.path.join(p, 'conf', 'mfcc.conf')))

def get_vosk_model(code):
    if not VOSK_OK or not model_present(code):
        return None
    with _vosk_lock:
        if code in _vosk_models:
            return _vosk_models[code]
        try:
            print(f'[VOSK] loading model for "{code}" ...')
            m = vosk.Model(model_dir(code))
            _vosk_models[code] = m
            print(f'[VOSK] model "{code}" ready.')
            return m
        except Exception as e:
            print(f'[VOSK] failed to load {code}: {e}')
            return None

def language_status():
    out = []
    for code, name, native in LANGUAGES:
        stt_ready = VOSK_OK and model_present(code)
        out.append({
            'code':   code,
            'name':   name,
            'native': native,
            'stt':    'READY' if stt_ready else 'MODEL REQUIRED',
        })
    return out

# --------------------------------------------------------------------------
# Offline TTS (espeak-ng preferred, pyttsx3 fallback)
# --------------------------------------------------------------------------
_tts_lock = threading.Lock()

def tts_generate(text, lang_code, out_path):
    """Generate WAV at out_path. Returns (engine_name | None, error | None)."""
    text = (text or '').strip()
    if not text:
        return (None, 'empty text')

    # 1. espeak-ng (excellent Hindi / English offline)
    if ESPEAK_PATH:
        voice = {'hi': 'hi', 'en': 'en'}.get(lang_code, 'en')
        try:
            r = subprocess.run(
                [ESPEAK_PATH, '-v', voice, '-s', '150', '-p', '50',
                 '-w', out_path, text],
                capture_output=True, timeout=30
            )
            if r.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 44:
                return ('espeak-ng', None)
            else:
                print(f'[TTS] espeak-ng returned {r.returncode}: {r.stderr[:200]}')
        except Exception as e:
            print(f'[TTS] espeak-ng error: {e}')

    # 2. pyttsx3 (Windows SAPI5 / macOS NSSpeech / Linux espeak)
    if PYTTSX3_OK:
        with _tts_lock:
            try:
                engine = pyttsx3.init()
                voices = engine.getProperty('voices') or []
                targets = {'hi': ['hi', 'hindi'], 'en': ['en', 'english']}.get(lang_code, ['en'])
                chosen = None
                for v in voices:
                    langs = ' '.join(getattr(v, 'languages', []) or []).lower()
                    name  = (getattr(v, 'name', '') or '').lower()
                    hay   = langs + ' ' + name
                    if any(t in hay for t in targets):
                        chosen = v.id
                        break
                if chosen:
                    engine.setProperty('voice', chosen)
                engine.setProperty('rate', 150)
                engine.setProperty('volume', 1.0)
                engine.save_to_file(text, out_path)
                engine.runAndWait()
                try: engine.stop()
                except Exception: pass
                if os.path.exists(out_path) and os.path.getsize(out_path) > 44:
                    return ('pyttsx3', None)
            except Exception as e:
                return (None, f'pyttsx3: {e}')

    return (None, 'No offline TTS engine available. Install espeak-ng or run on Windows with pyttsx3.')

# --------------------------------------------------------------------------
# Audio conversion to 16 kHz mono PCM WAV (for Vosk)
# --------------------------------------------------------------------------
def to_wav16k_mono(in_path, out_path):
    if FFMPEG_PATH:
        try:
            r = subprocess.run(
                [FFMPEG_PATH, '-y', '-hide_banner', '-loglevel', 'error',
                 '-i', in_path, '-ar', '16000', '-ac', '1',
                 '-c:a', 'pcm_s16le', '-f', 'wav', out_path],
                capture_output=True, timeout=90
            )
            if r.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 44:
                return True
            else:
                print(f'[FFMPEG] rc={r.returncode} err={r.stderr[:200]}')
        except Exception as e:
            print(f'[FFMPEG] {e}')

    # Fallback: if already a 16 kHz mono WAV, copy through
    try:
        with wave.open(in_path, 'rb') as w:
            if w.getframerate() == 16000 and w.getnchannels() == 1 and w.getsampwidth() == 2:
                shutil.copy(in_path, out_path)
                return True
    except Exception:
        pass
    return False

# --------------------------------------------------------------------------
# Offline STT (Vosk)
# --------------------------------------------------------------------------
def transcribe(wav16k, code):
    m = get_vosk_model(code)
    if m is None:
        return (None, 'STT MODEL NOT AVAILABLE')
    try:
        wf = wave.open(wav16k, 'rb')
    except Exception as e:
        return (None, f'invalid audio: {e}')
    try:
        rec = vosk.KaldiRecognizer(m, wf.getframerate())
        rec.SetWords(False)
        parts = []
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                j = json.loads(rec.Result())
                if j.get('text'):
                    parts.append(j['text'])
        j = json.loads(rec.FinalResult())
        if j.get('text'):
            parts.append(j['text'])
        return (' '.join(parts).strip(), None)
    except Exception as e:
        return (None, f'STT failed: {e}')
    finally:
        try: wf.close()
        except Exception: pass

# --------------------------------------------------------------------------
# Shared state
# --------------------------------------------------------------------------
HEARTBEAT_TIMEOUT = 10.0

STATE_LOCK = threading.Lock()
STATE = {
    'phone_a': {'last_seen': 0.0, 'language': 'hi', 'role': 'transmitter'},
    'phone_b': {'last_seen': 0.0, 'role': 'receiver'},
    'messages': [],
    'seq': 0,
    'started_at': time.time(),
    'demo_started': False,
}
LAST_LATENCY = {
    'stt_ms': None, 'net_ms': None, 'tts_ms': None, 'total_ms': None,
    'audio_kb': None, 'original_kb': None, 'text_bytes': None,
    'reduction_pct': None, 'ts': None, 'seq': None,
}

def now_ts(): return time.time()
def hhmmss(ts=None):
    return datetime.fromtimestamp(ts if ts else time.time()).strftime('%H:%M:%S')

def load_history():
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            STATE['messages'] = (data.get('messages') or [])[-200:]
            STATE['seq']      = data.get('seq') or 0
    except Exception:
        pass

def save_history():
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump({'messages': STATE['messages'][-200:], 'seq': STATE['seq']},
                      f, ensure_ascii=False)
    except Exception as e:
        print(f'[HISTORY] save failed: {e}')

load_history()

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try: return socket.gethostbyname(socket.gethostname())
        except Exception: return '127.0.0.1'

# --------------------------------------------------------------------------
# Routes — pages
# --------------------------------------------------------------------------
@app.route('/')
def index():        return render_template('index.html')

@app.route('/transmitter')
def transmitter():  return render_template('transmitter.html')

@app.route('/receiver')
def receiver():     return render_template('receiver.html')

@app.route('/admin')
def admin():        return render_template('admin.html')

# ---- SOLO DEMO (single-device, judge-safe) --------------------------------
@app.route('/solo')
def solo():
    """Single-device SOLO DEMO: Phone A + Phone B side-by-side.
    Used when judges run the prototype alone without two phones."""
    return render_template('solo.html')

@app.route('/solo_embed')
def solo_embed():
    """Compact version embedded inside /solo iframes."""
    return render_template('solo_embed.html')

@app.route('/static/<path:p>')
def static_files(p):
    return send_from_directory(STATIC_DIR, p)

@app.route('/audio/<path:name>')
def audio_files(name):
    safe = os.path.basename(name)
    fp = os.path.join(AUDIO_DIR, safe)
    if not os.path.isfile(fp):
        abort(404)
    return send_file(fp, mimetype='audio/wav')

@app.route('/qr.png')
def qr_png():
    if not QR_OK:
        abort(503)
    ip = get_local_ip()
    img = qrcode.make(f'http://{ip}:8000')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

# --------------------------------------------------------------------------
# Routes — API
# --------------------------------------------------------------------------
@app.route('/api/server_info')
def api_server_info():
    ip = get_local_ip()
    return jsonify({
        'ip': ip, 'port': 8000, 'url': f'http://{ip}:8000',
        'vosk': VOSK_OK, 'pyttsx3': PYTTSX3_OK,
        'ffmpeg': bool(FFMPEG_PATH), 'espeak': bool(ESPEAK_PATH),
    })

@app.route('/api/languages')
def api_languages():
    return jsonify({'languages': language_status()})

@app.route('/api/heartbeat', methods=['POST'])
def api_heartbeat():
    data = request.get_json(silent=True) or {}
    dev  = data.get('device')
    if dev not in ('phone_a', 'phone_b'):
        return jsonify({'ok': False, 'error': 'unknown device'}), 400
    with STATE_LOCK:
        STATE[dev]['last_seen'] = now_ts()
        if dev == 'phone_a' and data.get('language'):
            STATE[dev]['language'] = data['language']
        if data.get('role'):
            STATE[dev]['role'] = data['role']
    return jsonify({'ok': True, 'server_time': now_ts()})

@app.route('/api/status')
def api_status():
    with STATE_LOCK:
        a = (now_ts() - STATE['phone_a']['last_seen']) < HEARTBEAT_TIMEOUT
        b = (now_ts() - STATE['phone_b']['last_seen']) < HEARTBEAT_TIMEOUT
        ip = get_local_ip()
        return jsonify({
            'phone_a_connected': a,
            'phone_b_connected': b,
            'phone_a_language':  STATE['phone_a']['language'],
            'server_ip':   ip,
            'server_url':  f'http://{ip}:8000',
            'demo_started': STATE['demo_started'],
            'messages_count': len(STATE['messages']),
        })

@app.route('/api/transcribe', methods=['POST'])
def api_transcribe():
    if 'audio' not in request.files:
        return jsonify({'ok': False, 'error': 'no audio file'}), 400
    f = request.files['audio']
    if not f or not f.filename:
        return jsonify({'ok': False, 'error': 'empty upload'}), 400

    lang = (request.form.get('language') or 'hi').strip()
    if lang not in LANG_CODES:
        lang = 'hi'

    uid = uuid.uuid4().hex[:12]
    ext = os.path.splitext(f.filename)[1].lower() or '.bin'
    raw_path = os.path.join(UPLOAD_DIR, f'{uid}{ext}')
    wav_path = os.path.join(UPLOAD_DIR, f'{uid}.wav')

    try:
        f.save(raw_path)
        raw_size = os.path.getsize(raw_path)
        if raw_size == 0:
            return jsonify({'ok': False, 'error': 'zero-byte upload'}), 400
    except Exception as e:
        return jsonify({'ok': False, 'error': f'save failed: {e}'}), 500

    if not to_wav16k_mono(raw_path, wav_path):
        return jsonify({'ok': False,
                        'error': 'Audio conversion failed. Install ffmpeg or record WAV.'}), 500

    if not model_present(lang):
        return jsonify({
            'ok': False,
            'error': f'STT model for "{lang}" not installed. Add it under models/{lang}/ or use DEMO MODE.',
            'original_bytes': raw_size,
        }), 503

    t0 = time.time()
    text, err = transcribe(wav_path, lang)
    stt_ms = (time.time() - t0) * 1000.0

    if err:
        return jsonify({'ok': False, 'error': err, 'original_bytes': raw_size}), 500
    if not text:
        return jsonify({'ok': False, 'error': 'No speech detected. Try again or use DEMO MODE.',
                        'original_bytes': raw_size,
                        'stt_ms': round(stt_ms, 1)}), 200

    return jsonify({
        'ok': True, 'text': text, 'language': lang,
        'original_bytes': raw_size,
        'original_kb': round(raw_size / 1024.0, 2),
        'stt_ms': round(stt_ms, 1),
    })

@app.route('/api/send', methods=['POST'])
def api_send():
    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').strip()
    lang = (data.get('language') or 'hi').strip()
    priority = bool(data.get('priority'))
    demo     = bool(data.get('demo'))
    original_bytes = int(data.get('original_bytes') or 0)
    stt_ms = data.get('stt_ms')

    if not text:
        return jsonify({'ok': False, 'error': 'empty message'}), 400
    if lang not in LANG_CODES:
        lang = 'hi'

    text_bytes = len(text.encode('utf-8'))

    # --- TTS generation (offline, on laptop) ---
    tts_t0 = time.time()
    audio_name = f'{uuid.uuid4().hex[:12]}.wav'
    audio_path = os.path.join(AUDIO_DIR, audio_name)
    engine, tts_err = tts_generate(text, lang, audio_path)
    tts_ms = (time.time() - tts_t0) * 1000.0
    audio_kb = None
    if engine:
        try: audio_kb = round(os.path.getsize(audio_path) / 1024.0, 2)
        except Exception: audio_kb = None
    else:
        audio_name = None

    packet = {
        'id':             uuid.uuid4().hex[:12],
        'seq':            None,
        'type':           'priority' if priority else 'normal',
        'text':           text,
        'language':       lang,
        'sender':         'PHONE A',
        'timestamp':      now_ts(),
        'time_str':       hhmmss(),
        'bytes':          text_bytes,
        'original_bytes': original_bytes,
        'original_kb':    round(original_bytes / 1024.0, 2) if original_bytes else None,
        'stt_ms':         round(stt_ms, 1) if isinstance(stt_ms, (int, float)) else None,
        'tts_ms':         round(tts_ms, 1),
        'tts_engine':     engine,
        'tts_error':      tts_err,
        'audio_url':      f'/audio/{audio_name}' if audio_name else None,
        'audio_kb':       audio_kb,
        'demo':           demo,
        'sent_at':        now_ts(),
        'delivered_at':   None,
        'net_ms':         None,
    }

    with STATE_LOCK:
        STATE['seq'] += 1
        packet['seq'] = STATE['seq']
        STATE['messages'].append(packet)

    save_history()

    reduction = None
    if original_bytes:
        reduction = round((1 - text_bytes / max(1, original_bytes)) * 100, 2)

    with STATE_LOCK:
        LAST_LATENCY.update({
            'stt_ms': packet['stt_ms'], 'net_ms': None, 'tts_ms': packet['tts_ms'],
            'total_ms': None, 'audio_kb': packet['audio_kb'],
            'original_kb': packet['original_kb'],
            'text_bytes': text_bytes, 'reduction_pct': reduction,
            'ts': now_ts(), 'seq': packet['seq'],
        })

    return jsonify({
        'ok': True, 'packet': packet,
        'text_bytes': text_bytes, 'original_bytes': original_bytes,
        'reduction_pct': reduction,
        'tts_engine': engine, 'tts_error': tts_err,
    })

@app.route('/api/incoming')
def api_incoming():
    try: since = int(request.args.get('since', '0'))
    except Exception: since = 0

    out = []
    with STATE_LOCK:
        candidates = [m for m in STATE['messages'] if m['seq'] > since]
        candidates.sort(key=lambda m: (0 if m['type'] == 'priority' else 1, m['seq']))
        for m in candidates:
            mcopy = dict(m)
            if mcopy.get('delivered_at') is None:
                mcopy['delivered_at'] = now_ts()
                mcopy['net_ms'] = round((mcopy['delivered_at'] - mcopy['sent_at']) * 1000.0, 1)
                for sm in STATE['messages']:
                    if sm['id'] == m['id']:
                        sm['delivered_at'] = mcopy['delivered_at']
                        sm['net_ms']       = mcopy['net_ms']
                        break
            out.append(mcopy)

    if out:
        newest = out[-1]
        stt, net, tts = newest.get('stt_ms'), newest.get('net_ms'), newest.get('tts_ms')
        total = round(stt + net + tts, 1) if None not in (stt, net, tts) else None
        reduction = (round((1 - newest['bytes'] / max(1, newest['original_bytes'])) * 100, 2)
                     if newest.get('original_bytes') else None)
        with STATE_LOCK:
            LAST_LATENCY.update({
                'stt_ms': stt, 'net_ms': net, 'tts_ms': tts, 'total_ms': total,
                'audio_kb': newest.get('audio_kb'),
                'original_kb': newest.get('original_kb'),
                'text_bytes': newest['bytes'],
                'reduction_pct': reduction,
                'ts': now_ts(), 'seq': newest['seq'],
            })

    return jsonify({'ok': True, 'messages': out, 'server_time': now_ts()})

@app.route('/api/history')
def api_history():
    try: limit = int(request.args.get('limit', '40'))
    except Exception: limit = 40
    with STATE_LOCK:
        items = list(STATE['messages'])[-limit:]
    items.sort(key=lambda m: m['seq'])
    return jsonify({'messages': items})

@app.route('/api/latency')
def api_latency():
    with STATE_LOCK:
        return jsonify(dict(LAST_LATENCY))

@app.route('/api/alerts')
def api_alerts():
    return jsonify({'alerts': [
        'Emergency communication required.',
        'Please respond immediately.',
        'Communication link status required.',
    ]})

@app.route('/api/reset', methods=['POST'])
def api_reset():
    with STATE_LOCK:
        STATE['messages'] = []
        STATE['seq'] = 0
        STATE['demo_started'] = False
        STATE['phone_a']['last_seen'] = 0.0
        STATE['phone_b']['last_seen'] = 0.0
        for k in LAST_LATENCY: LAST_LATENCY[k] = None
    save_history()
    try:
        for f in os.listdir(AUDIO_DIR):
            try: os.remove(os.path.join(AUDIO_DIR, f))
            except Exception: pass
    except Exception: pass
    return jsonify({'ok': True})

@app.route('/api/demo_start', methods=['POST'])
def api_demo_start():
    with STATE_LOCK:
        STATE['demo_started'] = True
    return jsonify({'ok': True})

# --------------------------------------------------------------------------
# Error handlers
# --------------------------------------------------------------------------
@app.errorhandler(413)
def too_large(e):  return jsonify({'ok': False, 'error': 'Audio file too large (max 32 MB).'}), 413

@app.errorhandler(500)
def srv_err(e):    return jsonify({'ok': False, 'error': 'server error'}), 500

@app.errorhandler(404)
def nf(e):         return jsonify({'ok': False, 'error': 'not found'}), 404

# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def print_banner():
    ip = get_local_ip()
    print('=' * 66)
    print('  iTANTRA — Offline Neural Transceiver')
    print('  SIH 2026 · Problem Statement 173')
    print('=' * 66)
    print(f'  SOLO DEMO      http://{ip}:8000/solo')
    print(f'  ADMIN          http://{ip}:8000/admin')
    print(f'  Phone A        http://{ip}:8000/transmitter')
    print(f'  Phone B        http://{ip}:8000/receiver')
    print('-' * 66)
    print(f'  VOSK       {"OK" if VOSK_OK else "NOT INSTALLED"}')
    print(f'  pyttsx3    {"OK" if PYTTSX3_OK else "NOT INSTALLED"}')
    print(f'  ffmpeg     {"OK" if FFMPEG_PATH else "NOT FOUND"}')
    print(f'  espeak-ng  {"OK" if ESPEAK_PATH else "NOT FOUND"}')
    print('-' * 66)
    print('  Language STT readiness:')
    for code, name, _ in LANGUAGES:
        st = 'READY' if (VOSK_OK and model_present(code)) else 'MODEL REQUIRED'
        print(f'    {name:12s} {st}')
    print('=' * 66)
    print()

if __name__ == '__main__':
    # Allow PORT override for cloud platforms (Render sets this env var)
    port = int(os.environ.get('PORT', 8000))
    print_banner()
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True, use_reloader=False)