"""The disc, mods, saves and environment the game starts with."""

import json
import os
import shutil
import struct
import subprocess
import threading
import time
from pathlib import Path
from .config import CONFIG_DIR, HERE, LANGUAGES, MAC, ROOT, WINDOWS, asset
from .i18n import current, tr


def save_dir():
    return ROOT / 'gamedata' / 'dev_hdd0' / 'home' / '00000001' / 'savedata'


DEFAULT_ICON_ICO = ROOT / 'packaging' / 'windows' / 'ascension.ico'
DEFAULT_ICON_PNG = ROOT / 'packaging' / 'icon.png'


def icon_file():
    """icon-2.png as an .ico (window, taskbar and the game's window); on
    macOS the .png itself (the game's Dock icon). Without that optional
    artwork, falls back to Ascension's own emblem under packaging/ (already
    built as an .ico there) instead of leaving Tk's default feather icon."""
    src = asset('icon-2.png')
    if not src:
        default = DEFAULT_ICON_ICO if WINDOWS else DEFAULT_ICON_PNG
        return default if default.is_file() else None
    if not WINDOWS:
        return src
    ico = CONFIG_DIR / 'icon.ico'
    try:
        if not ico.is_file() or ico.stat().st_mtime < src.stat().st_mtime:
            from PIL import Image
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with Image.open(src) as im:
                im.convert('RGBA').save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        return ico
    except OSError:
        return None


BUILTIN_MODS = ROOT / 'mods-builtin'
GENERATED_DIR = CONFIG_DIR / 'generated'


def read_mod_json(folder):
    try:
        data = json.loads((Path(folder) / 'mod.json').read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def mod_text(meta, field):
    """A mod.json field in the launcher's language: "translations": {"en":
    {"name": ..., "description": ...}} beside the field itself."""
    lang = current()
    table = meta.get('translations') if isinstance(meta.get('translations'), dict) else {}
    for code in (lang, lang.split('-')[0]):
        value = (table.get(code) or {}).get(field) if isinstance(table.get(code), dict) else None
        if value:
            return str(value)
    return str(meta.get(field, ''))


def all_mods(s):
    """Every mod the launcher knows, in priority order (first wins): the ones
    that come with Ascension (mods-builtin, ids '@<folder>') and the user's
    (the mods folder, ids = folder names). Each is a dict: id, path, name,
    description, builtin, meta (its mod.json)."""
    found = {}
    if BUILTIN_MODS.is_dir():
        for d in sorted(BUILTIN_MODS.iterdir()):
            if d.is_dir():
                found['@' + d.name] = (d, True)
    user = Path(s['mods_dir'])
    if user.is_dir():
        for d in sorted(user.iterdir()):
            if d.is_dir() and d.name not in found:
                found[d.name] = (d, False)
    order = [m for m in s.get('mods_order', []) if m in found]
    order += [m for m in found if m not in order]
    mods = []
    for mid in order:
        path, builtin = found[mid]
        meta = read_mod_json(path)
        mods.append({'id': mid, 'path': path, 'builtin': builtin, 'meta': meta,
                     'name': mod_text(meta, 'name') or path.name,
                     'description': mod_text(meta, 'description')})
    return mods


def enabled_mod_list(s):
    on = set(s.get('mods_enabled', []))
    return [m for m in all_mods(s) if m['id'] in on]


def ptbr_mod(s):
    """An enabled mod that brings Brazilian Portuguese (tools/make_ptbr_mod.py
    builds one from the US disc): BR_PORTUGUESE.PSARC, the US voices, and the
    language-table entry "17 pt-br BR_PORTUGUESE" (the text, R_LANG_PT-BR, is
    already on the European disc)."""
    for m in enabled_mod_list(s):
        if (m['path'] / 'BR_PORTUGUESE.PSARC').is_file() or str(m['meta'].get('language', '')).lower() == 'pt-br':
            return m
    return None


def language_options(s):
    """Brazilian Portuguese is offered only with a mod that brings it."""
    if ptbr_mod(s):
        return LANGUAGES
    return [o for o in LANGUAGES if o[0] != '17']


def effective_language(s):
    lang = s['language']
    if lang == '17' and not ptbr_mod(s):
        return '7'
    return lang


def apply_text_ops(data, ops):
    """One archive file changed by a mod: {"text": "..."} replaces it,
    {"insert_after": "<line>", "line": "<new line>"} adds a line (once)."""
    for op in ops:
        if 'text' in op:
            data = op['text'].encode('utf-8')
        elif 'insert_after' in op and 'line' in op:
            eol = b'\r\n' if b'\r\n' in data else b'\n'
            anchor, line = op['insert_after'].encode('utf-8'), op['line'].encode('utf-8')
            lines = data.split(eol)
            if line not in lines and anchor in lines:
                i = lines.index(anchor)
                lines.insert(i + 1, line)
                data = eol.join(lines)
    return data


def disc_root(s):
    """The disc's folder (the one holding PS3_GAME) when one is set, else None:
    on Windows the EBOOT.ELF's own disc decides."""
    d = s.get('disc_dir', '')
    return Path(d) if d else None


def disc_usrdir(s):
    root = disc_root(s)
    return root / 'PS3_GAME' / 'USRDIR' if root else Path(s['eboot']).parent


GAME_ID = 'BCES01741'


def read_sfo(path):
    """A PARAM.SFO's entries: {key: text or number}."""
    data = Path(path).read_bytes()
    if data[:4] != b'\0PSF':
        raise ValueError('not a PARAM.SFO')
    keys, values, count = struct.unpack_from('<III', data, 8)
    out = {}
    for i in range(count):
        koff, fmt, length, _cap, voff = struct.unpack_from('<HHIII', data, 20 + 16 * i)
        key = data[keys + koff:data.index(b'\0', keys + koff)].decode('ascii', 'replace')
        raw = data[values + voff:values + voff + length]
        out[key] = int.from_bytes(raw[:4], 'little') if fmt == 0x0404 else raw.rstrip(b'\0').decode('utf-8', 'replace')
    return out


def disc_problem(s):
    """Why the disc found is not the one the game was built from, or None
    (also when there is no disc to look at yet)."""
    root = disc_root(s)
    sfo = (root / 'PS3_GAME' if root else Path(s['eboot']).parent.parent) / 'PARAM.SFO'
    if not sfo.is_file():
        return None
    try:
        info = read_sfo(sfo)
    except (OSError, ValueError, struct.error):
        return tr("the disc's PARAM.SFO could not be read ({path})", path=sfo)
    title = str(info.get('TITLE_ID', ''))
    if title != GAME_ID:
        name = str(info.get('TITLE', '')).replace('\n', ' ')
        title = f'{title or "?"} ({name})' if name else (title or '?')
        return tr('the disc is {title}, not the European release {id}', title=title, id=GAME_ID)
    return None


def ensure_disc(s):
    """macOS: mount the .iso read-only at the disc folder if it is not there yet.
    Returns the folder when this call mounted it (release_disc undoes that)."""
    root = disc_root(s)
    if not root or (root / 'PS3_GAME').is_dir():
        return None
    iso = s.get('disc_iso', '')
    if MAC and iso and Path(iso).is_file():
        root.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(['hdiutil', 'attach', '-readonly', '-nobrowse', '-mountpoint', str(root), iso],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise OSError('hdiutil: ' + (r.stderr or r.stdout).strip())
        return root
    return None


def release_disc(root):
    """Unmount a disc ensure_disc mounted; a busy one stays (nothing is lost)."""
    if root and MAC:
        subprocess.run(['hdiutil', 'detach', str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


MODS_LOCK = threading.Lock()     # PLAY and the build after Save write the same archives


def compose_mods(s, log=lambda m: None):
    with MODS_LOCK:
        return _compose_mods(s, log)


def prebuild_mods(s):
    """The mods' archives built ahead of PLAY, when the disc is there."""
    try:
        if disc_usrdir(s).is_dir():
            compose_mods(s)
    except Exception:       # PLAY builds them again and reports what fails
        pass


def _compose_mods(s, log):
    """The folders for PS3_MODS: first the archives the launcher builds from
    the enabled mods' recipes ("psarc_patches" in mod.json, applied to the
    copy of that archive the highest-priority mod ships, or to the disc's),
    then every enabled mod's own files. Rebuilt only when an input changes."""
    mods = enabled_mod_list(s)
    usrdir = disc_usrdir(s)
    wanted = {}
    for m in mods:
        for archive, files in (m['meta'].get('psarc_patches') or {}).items():
            wanted.setdefault(archive, [])
    dirs = []
    if wanted:
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        import importlib.util
        spec = importlib.util.spec_from_file_location('psarc_replace', ROOT / 'tools' / 'psarc_replace.py')
        pr = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pr)
        for archive in wanted:
            base = next((m['path'] / archive for m in mods if (m['path'] / archive).is_file()), usrdir / archive)
            # lowest priority first, so the first mod in the list has the last word
            ops = {}
            for m in reversed(mods):
                for inner, op in ((m['meta'].get('psarc_patches') or {}).get(archive) or {}).items():
                    ops.setdefault(inner, []).append(op if isinstance(op, dict) else {'text': str(op)})
            st = base.stat()
            key = json.dumps([str(base), st.st_size, int(st.st_mtime), ops], sort_keys=True)
            out = GENERATED_DIR / archive
            keyf = GENERATED_DIR / (archive + '.key')
            if not (out.is_file() and keyf.is_file() and keyf.read_text(encoding='utf-8') == key):
                log(f'montando {archive}')
                src = pr.Psarc(str(base))
                replace = {inner: apply_text_ops(src.read(src.index_of(inner)), oplist)
                           for inner, oplist in ops.items() if inner in src.names}
                pr.write(src, str(out), replace)
                keyf.write_text(key, encoding='utf-8')
        dirs.append(str(GENERATED_DIR))
    dirs += [str(m['path']) for m in mods]
    return dirs


def keymap_env(keymap):
    """PS3_KEYMAP: "cross=Space,K;square=J,Mouse1;..." (libs/input/pad_keymap.h)."""
    return ';'.join(f'{c}=' + ','.join(keys) for c, keys in keymap.items() if keys)


def padmap_env(padmap):
    return ';'.join(f'{c}={b}' for c, b in padmap.items())


def game_environment(s):
    env = dict(os.environ)
    env['PS3_SYS_LANG'] = effective_language(s)
    env['PS3_ENTER_BUTTON'] = s['enter_button']
    env['PS3_WINDOW_SIZE'] = s['window_size']
    env['PS3_FULLSCREEN'] = '1' if s['display_mode'] == 'fullscreen' else '0'
    env['PS3_ESC_QUITS'] = s['esc_quits']
    env['LD_PERF_OVERLAY'] = s['perf_overlay']
    env['PS3_OVERLAY_FONT'] = str(HERE / 'Cinzel-Black.ttf')   # RPCS3's overlay in the launcher's font
    if MAC:
        env['PS3RECOMP_METAL_FPS'] = s['perf_overlay']    # in the window's title
    # Video
    env.pop('PS3_RSX', None)
    env.pop('PS3_RSX_RENDERER', None)
    if s['renderer'].startswith('rpcs3'):
        env['PS3_RSX'] = 'rpcs3'
        env['PS3_RSX_RENDERER'] = 'opengl' if s['renderer'] == 'rpcs3-opengl' else 'vulkan'
        if MAC and s['renderer'] == 'rpcs3-vulkan':
            icd = next((p for p in (
                '/opt/homebrew/opt/molten-vk/etc/vulkan/icd.d/MoltenVK_icd.json',
                '/usr/local/opt/molten-vk/etc/vulkan/icd.d/MoltenVK_icd.json') if Path(p).is_file()), None)
            if icd and not env.get('VK_ICD_FILENAMES'):
                env['VK_ICD_FILENAMES'] = icd
            lib = '/opt/homebrew/lib' if Path('/opt/homebrew/lib').is_dir() else '/usr/local/lib'
            env['DYLD_FALLBACK_LIBRARY_PATH'] = lib + os.pathsep + env.get('DYLD_FALLBACK_LIBRARY_PATH', '')
    env['PS3_RENDER_SCALE'] = s['render_scale']
    env['PS3_ASPECT'] = s['aspect']
    env['PS3_SCALE_FILTER'] = s['scale_filter']
    env['PS3_ANISO'] = s['aniso']
    if s['vsync'] in ('0', '1'):
        env['PS3_VSYNC'] = s['vsync']
    else:
        env.pop('PS3_VSYNC', None)
    # Controls
    env['PS3_KEYMAP'] = keymap_env(s['keymap']) or 'start=Enter'
    env['PS3_PADMAP'] = padmap_env(s['padmap'])
    env['PS3_PAD_DEADZONE'] = s['pad_deadzone']
    root = disc_root(s)
    if root:
        env['PS3_VFS_ROOT'] = str(root)
    # The disc image is mounted read-only, so it reports no free space and the
    # game exits with NOSPACE. Saves and the cache live beside the disc.
    for key, folder in (('PS3_HDD0_ROOT', ROOT / 'gamedata' / 'dev_hdd0'),
                        ('PS3_HDD1_ROOT', ROOT / 'gamedata' / 'dev_hdd1')):
        folder.mkdir(parents=True, exist_ok=True)
        env[key] = str(folder)
    mods = compose_mods(s)
    if mods:
        env['PS3_MODS'] = ';'.join(mods)
    else:
        env.pop('PS3_MODS', None)
    ico = icon_file()
    if ico:
        env['PS3_WINDOW_ICON'] = str(ico)
    for item in s.get('extra_env', '').replace('\n', ';').split(';'):
        if '=' in item:
            k, v = item.split('=', 1)
            if k.strip():
                env[k.strip()] = v.strip()
    return env


def apply_save_settings(s):
    """Language and subtitles into the game's system save (BCES01741-SYSDATA).

    The game asks the console language only when it makes that save, at the
    first start; after that it reads its own copy. SAVEDATA (4 KB, no checksum)
    is a 16-byte header and the options block the boot hands out
    (func_0001A680): +0x0C text language (to func_003963A8), +0x0D voice
    language (to the audio side, func_00396348), +0x18 subtitles (to
    func_00032C74, which -subtitlesOn also drives). With English the game writes
    18 (English UK, the European text) and 1. Returns what it changed."""
    path = save_dir() / 'BCES01741-SYSDATA' / 'SAVEDATA'
    try:
        data = bytearray(path.read_bytes())
    except OSError:
        return None                                  # no save yet: the console language decides
    if len(data) < 0x29 or data[0:4] != bytes((0, 0, 0, 1)):
        return None
    lang = int(effective_language(s))                # 17 only with the PT-BR mod
    if lang in (1, 18):
        text, voice = 18, 1
    else:
        text = voice = lang
    new = bytearray(data)
    new[0x1C], new[0x1D] = text, voice
    new[0x28] = 1 if s.get('subtitles') == '1' else 0
    if new != data:
        path.write_bytes(bytes(new))
        return True
    return False


def tree_signature(folder):
    """Relative path, size and mtime of every file (copytree keeps mtimes)."""
    out = []
    for dirpath, _dirs, files in os.walk(folder):
        for name in files:
            st = (Path(dirpath) / name).stat()
            out.append((os.path.relpath(Path(dirpath) / name, folder), st.st_size, int(st.st_mtime)))
    return sorted(out)


def backup_saves():
    """A copy of the saves, unless the newest backup already has them as they
    are: starting the game ten times without playing keeps the older ones."""
    src = save_dir()
    if not src.is_dir() or not any(src.iterdir()):
        return None
    folder = ROOT / 'gamedata' / 'save-backups'
    backups = sorted(folder.iterdir()) if folder.is_dir() else []
    if backups and tree_signature(backups[-1]) == tree_signature(src):
        return backups[-1]
    dst = folder / time.strftime('%Y%m%d-%H%M%S')
    shutil.copytree(src, dst)
    backups = sorted(folder.iterdir())
    for old in backups[:-10]:                       # keep the last ten
        shutil.rmtree(old, ignore_errors=True)
    return dst


def backup_list():
    """The save backups, newest first."""
    folder = ROOT / 'gamedata' / 'save-backups'
    return sorted((d for d in folder.iterdir() if d.is_dir()), reverse=True) if folder.is_dir() else []


def restore_saves(backup):
    """The saves as they were in `backup`. The current ones are backed up
    first; the copy is taken before that, since it can drop the oldest."""
    dst = save_dir()
    tmp = dst.with_name('savedata.restoring')
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.copytree(backup, tmp)
    backup_saves()
    shutil.rmtree(dst, ignore_errors=True)
    tmp.rename(dst)


def missing(s):
    out = []
    if not Path(s['game_exe']).is_file():
        out.append(tr("the game's executable ({path})", path=s['game_exe']))
    if not Path(s['eboot']).is_file():
        out.append(tr("the disc's EBOOT.ELF ({path})", path=s['eboot']))
    root = disc_root(s)
    if root and not (root / 'PS3_GAME').is_dir() and not (MAC and Path(s.get('disc_iso') or '-').is_file()):
        out.append(tr('the disc ({path}; or the .iso image)' if MAC else 'the disc ({path})', path=root))
    return out


def prepare_game(s, status=lambda m: None):
    """Everything before the game starts (it can take a while: the disc,
    the saves, the mods' archives). Returns the environment and the disc
    folder it mounted, if any."""
    status(tr('Preparing the game…'))
    mounted = ensure_disc(s)
    problem = disc_problem(s)
    if problem:
        release_disc(mounted)
        raise OSError(problem[0].upper() + problem[1:] + '.')
    if s.get('backup_saves') == '1':
        status(tr('Copying the saves…'))
        backup_saves()
    apply_save_settings(s)
    status(tr('Preparing the mods…'))
    return game_environment(s), mounted


def start_game(s, env, log_path, parent=None):
    """Start the game; with `parent` (a window handle) it renders inside that
    window. The previous run's log is kept as last_run.prev.log."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if log_path.is_file():
        log_path.replace(log_path.with_suffix('.prev.log'))
    log = open(log_path, 'w', encoding='utf-8', errors='replace')
    flags = subprocess.CREATE_NO_WINDOW if WINDOWS else 0
    if parent:
        env = {**env, 'PS3_PARENT_HWND': str(parent)}
    try:
        return subprocess.Popen([s['game_exe'], s['eboot']], cwd=str(ROOT), env=env,
                                stdout=log, stderr=subprocess.STDOUT, creationflags=flags), log
    except BaseException:
        log.close()
        raise
