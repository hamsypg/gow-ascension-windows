"""Paths, the settings and the choices the pages offer."""

import json
import os
import sys
from pathlib import Path


VERSION = '0.1'
APP_NAME = 'God of War: Ascension'
WINDOWS = sys.platform == 'win32'
MAC = sys.platform == 'darwin'
SHOT = '--shot' in sys.argv     # development: screenshot each page, then quit (no music)

FROZEN = bool(getattr(sys, 'frozen', False))    # packaged with PyInstaller (packaging/windows)
if FROZEN:
    # The .exe runs from a temp extraction folder (sys._MEIPASS), not from
    # beside the repository, so __file__ cannot find launcher/ or ascension/
    # from there. AscensionLauncher.exe itself is meant to sit at the
    # repository's root, next to build/, mods/, docs/ and launcher/ (which
    # keeps its lang/*.json, fonts and assets/ as loose files either way).
    ROOT = Path(sys.executable).resolve().parent        # ascension/
    HERE = ROOT / 'launcher'
else:
    HERE = Path(__file__).resolve().parent.parent          # launcher/
    ROOT = HERE.parent                                   # ascension/
WORK = ROOT.parent / 'work'
ASSET_DIRS = [HERE / 'assets', WORK / 'data' / 'launcher']
if WINDOWS:
    CONFIG_DIR = Path(os.environ.get('APPDATA', Path.home())) / 'ascension-launcher'
elif MAC:
    CONFIG_DIR = Path.home() / 'Library' / 'Application Support' / 'ascension-launcher'
else:
    CONFIG_DIR = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'ascension-launcher'
CONFIG_FILE = CONFIG_DIR / 'settings.json'


# The PS3 console languages the disc has text and voices for (CELL_SYSUTIL_LANG_*).
# Greek is not a console language: the game itself offers it at first start.
LANGUAGES = [
    ('18', 'English (UK)'), ('1', 'English (US)'), ('7', 'Português (Portugal)'),
    ('17', 'Português (Brasil)'), ('2', 'Español'), ('3', 'Français'), ('4', 'Deutsch'),
    ('5', 'Italiano'), ('8', 'Русский'), ('16', 'Polski'), ('19', 'Türkçe'),
]
DISPLAY_MODES = [('window', 'Window'), ('fullscreen', 'Full screen (borderless)')]
WINDOW_SIZES = [(s, s.replace('x', ' x ')) for s in
                ('1280x720', '1600x900', '1920x1080', '2560x1440', '3840x2160')]
ENTER_BUTTONS = [('cross', 'X confirms (West)'), ('circle', 'O confirms (Japan)')]
ON_OFF = [('1', 'On'), ('0', 'Off')]

# Video. The renderer: RPCS3's RSX (ps3recomp gpu/, a build with
# -DASCENSION_RPCS3_RSX=ON) or live draw. On macOS, Vulkan is MoltenVK and
# live draw is Metal; the GL backend is WGL, so it is not offered there.
RENDERERS = ([('rpcs3-vulkan', 'RPCS3 · Vulkan (MoltenVK)'),
              ('metal', 'Live draw · Metal')] if MAC else
             [('rpcs3-vulkan', 'RPCS3 · Vulkan'), ('rpcs3-opengl', 'RPCS3 · OpenGL'),
              ('livedraw', 'Live draw · Direct3D 12')] if WINDOWS else
             [('rpcs3-vulkan', 'RPCS3 · Vulkan'), ('rpcs3-opengl', 'RPCS3 · OpenGL')])
RENDER_SCALES = [('100', 'HD · 1280 x 720 (original)'), ('150', 'Full HD · 1920 x 1080'),
                 ('200', '2K · 2560 x 1440'), ('300', '4K · 3840 x 2160')]
ASPECTS = [('keep', 'Keep 16:9 (black bars)'), ('stretch', 'Stretch to the window')]
SCALE_FILTERS = [('linear', 'Smooth (bilinear)'), ('nearest', 'Sharp (pixel)'),
                 ('fsr', 'AMD FSR 1 (RPCS3)')]
VSYNC_MODES = [('auto', "Automatic (the renderer's)"), ('1', 'On'), ('0', 'Off')]
ANISO_LEVELS = [('0', "The game's"), ('2', '2x'), ('4', '4x'), ('8', '8x'), ('16', '16x')]

# Controls: the PS3 pad's controls, grouped as the Controls page shows them,
# with what they do in the game where that is certain. The ids are
# ps3recomp's (PS3_KEYMAP / PS3_PADMAP, libs/input/pad_keymap.h).
CONTROL_GROUPS = [
    ('Left stick · walk', [('ls_up', 'Up'), ('ls_down', 'Down'), ('ls_left', 'Left'),
                                     ('ls_right', 'Right')]),
    ('Right stick · evade', [('rs_up', 'Up'), ('rs_down', 'Down'), ('rs_left', 'Left'),
                                      ('rs_right', 'Right')]),
    ('Buttons', [('cross', '✕  Jump'), ('square', '□  Light attack'), ('triangle', '△  Heavy attack'),
                ('circle', '○  Grab')]),
    ('Shoulders and triggers', [('l1', 'L1  Block'), ('r1', 'R1'), ('l2', 'L2'), ('r2', 'R2'),
                           ('l3', 'L3 (stick click)'), ('r3', 'R3 (stick click)')]),
    ('D-pad', [('up', '↑  Up'), ('down', '↓  Down'), ('left', '←  Left'), ('right', '→  Right')]),
    ('System', [('start', 'START  Pause'), ('select', 'SELECT')]),
]
PAD_CONTROLS = [c for _, items in CONTROL_GROUPS for c, _ in items if not c.startswith(('ls_', 'rs_'))]

KEY_PRESETS = {
    'pc': {   # WASD to walk, arrows to evade, the face buttons under the right hand and the mouse
        'ls_up': ['W'], 'ls_down': ['S'], 'ls_left': ['A'], 'ls_right': ['D'],
        'rs_up': ['Up'], 'rs_down': ['Down'], 'rs_left': ['Left'], 'rs_right': ['Right'],
        'cross': ['Space', 'K'], 'square': ['J', 'Mouse1'], 'triangle': ['I', 'Mouse2'], 'circle': ['L', 'C'],
        'l1': ['LShift', 'Q'], 'r1': ['E', 'Mouse4'], 'l2': ['Z'], 'r2': ['R', 'Mouse5'],
        'l3': ['LCtrl'], 'r3': ['V'],
        'up': ['T'], 'down': ['G'], 'left': ['F'], 'right': ['H'],
        'start': ['Enter', 'Escape'], 'select': ['Tab', 'Backspace'],
    },
    'classic': {   # the runtime's old fixed map: arrows, Z/X/A/S
        'up': ['Up'], 'down': ['Down'], 'left': ['Left'], 'right': ['Right'],
        'ls_up': ['Up'], 'ls_down': ['Down'], 'ls_left': ['Left'], 'ls_right': ['Right'],
        'cross': ['Z'], 'circle': ['X'], 'square': ['A'], 'triangle': ['S'],
        'l1': ['Q'], 'r1': ['W'], 'l2': ['1'], 'r2': ['2'], 'start': ['Enter'], 'select': ['Tab'],
    },
}
PAD_DEFAULTS = {'up': 'up', 'down': 'down', 'left': 'left', 'right': 'right', 'cross': 'a', 'circle': 'b',
                'square': 'x', 'triangle': 'y', 'l1': 'lb', 'r1': 'rb', 'l2': 'lt', 'r2': 'rt',
                'l3': 'ls', 'r3': 'rs', 'start': 'start', 'select': 'back'}
PAD_BUTTONS = [('a', 'A  ·  ✕'), ('b', 'B  ·  ○'), ('x', 'X  ·  □'), ('y', 'Y  ·  △'),
               ('lb', 'LB  ·  L1'), ('rb', 'RB  ·  R1'), ('lt', 'LT  ·  L2'), ('rt', 'RT  ·  R2'),
               ('ls', 'Left click  ·  L3'), ('rs', 'Right click  ·  R3'),
               ('back', 'View / Back  ·  Share'), ('start', 'Menu / Start  ·  Options'),
               ('guide', 'Xbox / PS'), ('up', 'D-pad ↑'), ('down', 'D-pad ↓'),
               ('left', 'D-pad ←'), ('right', 'D-pad →'), ('none', '(none)')]
DEADZONES = [(str(v), f'{v}%' + (' (default)' if v == 24 else '')) for v in (0, 5, 10, 15, 20, 24, 30, 40, 50)]

# Key names as ps3recomp reads them, from Tk's keysyms.
TK_KEYS = {
    'space': 'Space', 'Return': 'Enter', 'KP_Enter': 'Enter', 'Tab': 'Tab', 'ISO_Left_Tab': 'Tab',
    'BackSpace': 'Backspace', 'Escape': 'Escape', 'Up': 'Up', 'Down': 'Down', 'Left': 'Left', 'Right': 'Right',
    'Shift_L': 'LShift', 'Shift_R': 'RShift', 'Control_L': 'LCtrl', 'Control_R': 'RCtrl',
    'Alt_L': 'LAlt', 'Alt_R': 'RAlt', 'Option_L': 'LAlt', 'Option_R': 'RAlt',
    'comma': 'Comma', 'period': 'Period', 'slash': 'Slash', 'semicolon': 'Semicolon',
    'apostrophe': 'Quote', 'quoteright': 'Quote', 'bracketleft': 'LBracket', 'bracketright': 'RBracket',
    'minus': 'Minus', 'equal': 'Equals', 'grave': 'Grave', 'quoteleft': 'Grave', 'backslash': 'Backslash',
    'Insert': 'Insert', 'Delete': 'Delete', 'Home': 'Home', 'End': 'End', 'Prior': 'PageUp',
    'Next': 'PageDown', 'Caps_Lock': 'CapsLock',
    **{f'KP_{i}': f'Num{i}' for i in range(10)}, **{f'F{i}': f'F{i}' for i in range(1, 13)},
}
KEY_LABELS = {
    'Space': 'Space', 'Escape': 'Esc', 'Up': '↑', 'Down': '↓', 'Left': '←', 'Right': '→',
    'LShift': 'Left Shift', 'RShift': 'Right Shift', 'LCtrl': 'Left Control', 'RCtrl': 'Right Control',
    'LAlt': 'Left Option' if MAC else 'Left Alt', 'RAlt': 'Right Option' if MAC else 'Right Alt',
    'Comma': ',', 'Period': '.', 'Slash': '/', 'Semicolon': ';', 'Quote': "'", 'LBracket': '[',
    'RBracket': ']', 'Minus': '-', 'Equals': '=', 'Grave': '`', 'Backslash': '\\',
    'PageUp': 'Page Up', 'PageDown': 'Page Down', 'CapsLock': 'Caps Lock',
    'Mouse1': '🖱 Left', 'Mouse2': '🖱 Right', 'Mouse3': '🖱 Middle', 'Mouse4': '🖱 Button 4',
    'Mouse5': '🖱 Button 5', **{f'Num{i}': f'Num {i}' for i in range(10)},
}


def key_label(name):
    return KEY_LABELS.get(name, name) if name else '—'


GAME_EXE = ROOT / 'build' / 'win' / 'AscensionRecomp.exe' if WINDOWS else ROOT / 'build' / 'mac' / 'AscensionRecomp'
# On macOS the disc stays an .iso, mounted read-only at work/disc when the game
# starts; the decrypted EBOOT.ELF sits in ascension/input/.
EBOOT = (WORK / 'disc' / 'PS3_GAME' / 'USRDIR' / 'EBOOT.ELF') if WINDOWS else ROOT / 'input' / 'EBOOT.ELF'

DEFAULTS = {
    'display_mode': 'window', 'window_size': '1280x720', 'perf_overlay': '1',
    'renderer': RENDERERS[0][0], 'render_scale': '100', 'aspect': 'keep', 'scale_filter': 'linear',
    'vsync': 'auto', 'aniso': '0',
    'esc_quits': '0', 'language': '18', 'enter_button': 'cross', 'subtitles': '1',
    'keymap': KEY_PRESETS['pc'], 'padmap': PAD_DEFAULTS, 'pad_deadzone': '24',
    'mods_dir': str(ROOT / 'mods'), 'mods_enabled': [], 'mods_order': [],
    'game_exe': str(GAME_EXE), 'eboot': str(EBOOT),
    'disc_dir': '' if WINDOWS else str(WORK / 'disc'), 'disc_iso': '',
    'backup_saves': '1', 'music': '1', 'discord_rpc': '0', 'extra_env': '', 'ui_language': 'auto',
}


def asset(name):
    for folder in ASSET_DIRS:
        if (folder / name).is_file():
            return folder / name
    return None


def load_settings():
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        data = {}
    s = {**DEFAULTS, **data}
    keymap = s['keymap'] if isinstance(s['keymap'], dict) else {}
    s['keymap'] = {c: [k for k in keymap.get(c, [])][:2] for _, items in CONTROL_GROUPS for c, _ in items}
    padmap = s['padmap'] if isinstance(s['padmap'], dict) else {}
    s['padmap'] = {c: padmap.get(c, PAD_DEFAULTS[c]) for c in PAD_CONTROLS}
    if s['renderer'] not in dict(RENDERERS):
        s['renderer'] = RENDERERS[0][0]
    return s


def save_settings(values):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(values, indent=2, ensure_ascii=False), encoding='utf-8')
    tmp.replace(CONFIG_FILE)
