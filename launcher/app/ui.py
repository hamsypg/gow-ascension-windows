"""The launcher's window."""

import ctypes
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from .config import (ANISO_LEVELS, APP_NAME, ASPECTS, CONTROL_GROUPS, DEADZONES, DEFAULTS, DISPLAY_MODES,
    ENTER_BUTTONS, FROZEN, HERE, KEY_PRESETS, MAC, ON_OFF, PAD_BUTTONS, PAD_CONTROLS, PAD_DEFAULTS, RENDERERS,
    RENDER_SCALES, ROOT, SCALE_FILTERS, SHOT, TK_KEYS, VERSION, VSYNC_MODES, WINDOWS, WINDOW_SIZES, asset,
    key_label, load_settings, save_settings)
from .discord_presence import Presence
from .game import (all_mods, backup_list, disc_problem, icon_file, language_options, missing,
    prebuild_mods, prepare_game, release_disc, restore_saves, save_dir, start_game)
from .i18n import available, set_language, tr
from .music import Music
from .native import mac_dock, register_font


BACKGROUNDS = ['background.jpg', 'background-2.jpg', 'background-3.jpg', 'background-4.png']


# Colours: the bronze and fire of Ascension's logo over near black, with
# Kratos' red for what can be pressed.
BG, PANEL, CARD, LINE = '#0b0908', '#14100e', '#1e1814', '#2e2620'
TEXT, MUTED, GOLD = '#ece2d4', '#91857a', '#e2b86a'
ACCENT, ACCENT_HI = '#9e1b16', '#c9271f'


def translated(options):
    """[(value, label)] with the labels in the launcher's language."""
    return [(value, tr(label)) for value, label in options]


def tr_key(name):
    return tr(key_label(name))


class Launcher:
    FADE_STEPS, FADE_MS, HOLD_MS = 30, 40, 7000

    def __init__(self, root):
        import tkinter as tk
        from tkinter import ttk, filedialog, messagebox
        self.tk, self.ttk, self.filedialog, self.messagebox = tk, ttk, filedialog, messagebox
        self.root = root
        self.s = load_settings()
        self.ui_language = self.s['ui_language']       # the one this window was built in
        set_language(self.ui_language)
        self.vars = {}
        self.dynamic = {}
        self.mod_vars = {}
        self.mod_order = list(self.s['mods_order'])
        self.keymap = {c: list(k) for c, k in self.s['keymap'].items()}
        self.padmap = dict(self.s['padmap'])
        self.capturing = None
        self.process = None
        self.preparing = False
        self.mounted = None        # the disc folder the launcher mounted (macOS)
        self.discord = Presence()  # Discord Rich Presence, started only while playing
        if MAC:   # Tk on macOS counts 72 points to the inch: the sizes below assume Windows' 96
            root.tk.call('tk', 'scaling', 1.33)
        self.heading = 'Georgia'
        if register_font(HERE / 'Cinzel-Black.ttf'):
            from tkinter import font as tkfont
            families = set(tkfont.families(root))
            self.heading = next((f for f in ('Cinzel Black', 'Cinzel') if f in families), 'Georgia')
        self.ui = 'Segoe UI' if WINDOWS else 'Helvetica Neue' if MAC else 'DejaVu Sans'
        root.title(f'{APP_NAME} (PC)')
        root.configure(bg=BG)
        w, h = 1180, 740
        root.geometry(f'{w}x{h}+{(root.winfo_screenwidth() - w) // 2}+{(root.winfo_screenheight() - h) // 3}')
        root.minsize(1000, 660)
        ico = icon_file()
        if ico:
            try:
                if WINDOWS:
                    root.iconbitmap(default=str(ico))
                else:
                    self.icon_photo = tk.PhotoImage(file=str(ico))
                    root.iconphoto(True, self.icon_photo)
            except tk.TclError:
                pass
        self.style()
        self.bg_sources = [p for p in (asset(n) for n in BACKGROUNDS) if p]
        self.bg_index, self.bg_cache, self.bg_size = 0, {}, None
        self.logo_src = asset('logo.png')
        self.music = Music() if not SHOT else Music.__new__(Music)
        if SHOT:
            self.music.ok = False
            self.music.error = ''
        self.build()
        self.show('home')
        self.saved = self.gather()
        if self.s.get('music') == '1':
            self.music.play()
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(400, self.watch_changes)
        root.after(self.HOLD_MS, self.next_background)

    # ---- look -------------------------------------------------------------------------------
    def style(self):
        ttk = self.ttk
        s = ttk.Style(self.root)
        s.theme_use('clam')
        base = (self.ui, 10)
        self.root.option_add('*TCombobox*Listbox.background', CARD)
        self.root.option_add('*TCombobox*Listbox.foreground', TEXT)
        self.root.option_add('*TCombobox*Listbox.selectBackground', ACCENT)
        self.root.option_add('*TCombobox*Listbox.font', base)
        s.configure('.', background=PANEL, foreground=TEXT, fieldbackground=CARD, bordercolor=LINE,
                    lightcolor=LINE, darkcolor=LINE, troughcolor=CARD, focuscolor=ACCENT, font=base)
        s.configure('TFrame', background=PANEL)
        s.configure('TLabel', background=PANEL, foreground=TEXT)
        s.configure('Muted.TLabel', background=PANEL, foreground=MUTED, font=(self.ui, 9))
        s.configure('Section.TLabel', background=PANEL, foreground=GOLD, font=(self.heading, 12))
        s.configure('Page.TLabel', background=PANEL, foreground=TEXT, font=(self.heading, 20))
        s.configure('TCheckbutton', background=PANEL, foreground=TEXT, indicatorcolor=CARD,
                    indicatorbackground=CARD, padding=(0, 3))
        s.map('TCheckbutton', background=[('active', PANEL)],
              indicatorbackground=[('selected', ACCENT_HI), ('active', LINE)],
              indicatorforeground=[('selected', '#fbf1e2')])
        s.configure('TCombobox', arrowcolor=GOLD, foreground=TEXT, padding=5, arrowsize=14)
        s.map('TCombobox', fieldbackground=[('readonly', CARD)], foreground=[('readonly', TEXT)],
              selectbackground=[('readonly', CARD)], selectforeground=[('readonly', TEXT)])
        s.configure('TEntry', foreground=TEXT, insertcolor=TEXT, padding=5)
        s.configure('TButton', background=CARD, foreground=TEXT, padding=(14, 6), borderwidth=1)
        s.map('TButton', background=[('active', LINE), ('disabled', PANEL)], foreground=[('disabled', MUTED)])
        s.configure('Play.TButton', background=ACCENT, foreground='#fbf1e2', font=(self.heading, 16),
                    padding=(44, 10), borderwidth=0)
        s.map('Play.TButton', background=[('active', ACCENT_HI), ('disabled', '#2e1c1c')],
              foreground=[('disabled', '#8a7a78')])
        s.configure('Vertical.TScrollbar', background=CARD, arrowcolor=MUTED, troughcolor=PANEL, bordercolor=PANEL)

    # ---- settings widgets -------------------------------------------------------------------
    def var(self, key):
        if key not in self.vars:
            self.vars[key] = self.tk.StringVar(value=str(self.s.get(key, DEFAULTS.get(key, ''))))
        return self.vars[key]

    def choice(self, parent, key, options, width=28):
        """A read-only combobox showing labels for stored values. `options` may
        be a function, re-read by refresh_choices when what it depends on changes."""
        source = options
        options = translated(source() if callable(source) else source)
        shown = self.tk.StringVar()
        box = self.ttk.Combobox(parent, textvariable=shown, state='readonly', width=width)
        box.maps = (dict(options), {label: value for value, label in options})
        box.configure(values=[label for _, label in options])
        shown.set(box.maps[0].get(self.var(key).get(), options[0][1]))
        shown.trace_add('write', lambda *_: box.maps[1].get(shown.get()) and self.var(key).set(box.maps[1][shown.get()]))
        box.bind('<MouseWheel>', lambda e: 'break')
        if callable(source):
            self.dynamic.setdefault(key, []).append((box, shown, source))
        return box

    def refresh_choices(self, key, fallback):
        for box, shown, source in self.dynamic.get(key, []):
            options = translated(source())
            box.maps = (dict(options), {label: value for value, label in options})
            box.configure(values=[label for _, label in options])
            if self.var(key).get() not in box.maps[0]:
                self.var(key).set(fallback)
            shown.set(box.maps[0].get(self.var(key).get(), options[0][1]))

    def page(self, name, title, subtitle):
        tk, ttk = self.tk, self.ttk
        outer = tk.Frame(self.content, bg=PANEL)
        canvas = tk.Canvas(outer, bg=PANEL, highlightthickness=0, bd=0, yscrollincrement=1)   # scroll in pixels
        inner = ttk.Frame(canvas, padding=(34, 26, 34, 26))
        inner.bind('<Configure>', lambda _e: canvas.configure(scrollregion=canvas.bbox('all')))
        win = canvas.create_window(0, 0, window=inner, anchor='nw')
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(win, width=e.width))
        canvas.pack(side='left', fill='both', expand=True)
        outer.scroll = lambda px: canvas.yview_scroll(int(px), 'units')
        ttk.Label(inner, text=title, style='Page.TLabel').grid(row=0, column=0, columnspan=3, sticky='w')
        ttk.Label(inner, text=subtitle, style='Muted.TLabel').grid(row=1, column=0, columnspan=3, sticky='w', pady=(2, 8))
        inner.columnconfigure(2, weight=1)
        inner.next_row = 2
        self.pages[name] = outer
        return inner

    def section(self, f, title):
        r = f.next_row
        self.ttk.Label(f, text=title.upper(), style='Section.TLabel').grid(row=r, column=0, columnspan=3, sticky='w', pady=(18, 0))
        self.tk.Frame(f, bg=LINE, height=1).grid(row=r + 1, column=0, columnspan=3, sticky='we', pady=(3, 8))
        f.next_row += 2

    def row(self, f, title, widget, hint=None):
        r = f.next_row
        self.ttk.Label(f, text=title).grid(row=r, column=0, sticky='w', pady=6, padx=(0, 24))
        widget.grid(row=r, column=1, sticky='w')
        if hint:
            self.ttk.Label(f, text=hint, style='Muted.TLabel', wraplength=360, justify='left').grid(
                row=r, column=2, sticky='w', padx=(18, 0))
        f.next_row += 1

    def note(self, f, text):
        self.ttk.Label(f, text=text, style='Muted.TLabel', wraplength=760, justify='left').grid(
            row=f.next_row, column=0, columnspan=3, sticky='w', pady=(6, 0))
        f.next_row += 1

    def path_row(self, f, key, title, folder=False, hint=None):
        holder = self.ttk.Frame(f)
        self.ttk.Entry(holder, textvariable=self.var(key), width=58).pack(side='left')

        def browse():
            current = self.var(key).get()
            if folder:
                p = self.filedialog.askdirectory(initialdir=current or str(ROOT))
            else:
                p = self.filedialog.askopenfilename(initialdir=str(Path(current).parent) if current else str(ROOT))
            if p:
                self.var(key).set(str(Path(p)))
        self.ttk.Button(holder, text=tr('Browse…'), command=browse).pack(side='left', padx=(8, 0))
        self.row(f, title, holder, hint)

    # ---- layout -----------------------------------------------------------------------------
    def build(self):
        tk = self.tk
        side = self.side = tk.Frame(self.root, bg=BG, width=230)
        side.pack(side='left', fill='y')
        side.pack_propagate(False)
        self.side_logo = tk.Label(side, bg=BG, bd=0)
        self.side_logo.pack(anchor='w', padx=18, pady=(22, 18))
        self.side_logo_image = self.scaled_logo(196)
        if self.side_logo_image:
            self.side_logo.configure(image=self.side_logo_image)
        else:
            self.side_logo.configure(text='GOD OF WAR\nASCENSION', fg=GOLD, font=(self.heading, 15), justify='left')
        self.nav, self.current = {}, None
        for name, title in (('home', tr('Home')), ('video', tr('Video')), ('controls', tr('Controls')), ('game', tr('Game')),
                            ('mods', tr('Mods')), ('advanced', tr('Advanced')), ('about', tr('About'))):
            item = tk.Label(side, text='    ' + title, bg=BG, fg=TEXT, anchor='w', font=(self.heading, 12),
                            pady=11, cursor='hand2')
            item.pack(fill='x')
            item.bind('<Button-1>', lambda _e, n=name: self.show(n))
            item.bind('<Enter>', lambda _e, n=name: n != self.current and self.nav[n].configure(bg='#1a1411'))
            item.bind('<Leave>', lambda _e, n=name: n != self.current and self.nav[n].configure(bg=BG))
            self.nav[name] = item
        tk.Frame(side, bg=BG).pack(fill='both', expand=True)
        self.music_label = tk.Label(side, text='', bg=BG, fg=MUTED, font=(self.ui, 9), cursor='hand2')
        self.music_label.pack(anchor='w', padx=22, pady=(0, 6))
        self.music_label.bind('<Button-1>', lambda _e: self.toggle_music())
        self.refresh_music_label()
        tk.Label(side, text=tr('{keys} in game:\nfull screen', keys=self.fullscreen_keys()), bg=BG, fg=MUTED, font=(self.ui, 9),
                 justify='left').pack(anchor='w', padx=22, pady=(0, 4))
        tk.Label(side, text=tr('v{version} · PS3 → PC recompilation', version=VERSION), bg=BG, fg=MUTED, font=(self.ui, 9)).pack(
            anchor='w', padx=22, pady=(0, 18))

        right = self.right = tk.Frame(self.root, bg=PANEL)
        right.pack(side='left', fill='both', expand=True)
        bar = tk.Frame(right, bg=BG, height=76)
        bar.pack(fill='x', side='bottom')
        bar.pack_propagate(False)
        self.status = tk.Label(bar, text='', bg=BG, fg=MUTED, font=(self.ui, 10), anchor='w', justify='left')
        self.status.pack(side='left', padx=24)
        self.play_button = self.ttk.Button(bar, text='JOGAR', style='Play.TButton', command=self.play)
        self.play_button.pack(side='right', padx=(10, 24), pady=12)
        self.save_button = self.ttk.Button(bar, text=tr('Save'), command=self.save, state='disabled')
        self.save_button.pack(side='right', pady=12)
        self.content = tk.Frame(right, bg=PANEL)
        self.content.pack(fill='both', expand=True)

        self.pages = {}
        self.build_home()
        self.build_video()
        self.build_controls()
        self.build_game()
        self.build_mods()
        self.build_advanced()
        self.build_about()
        self.refresh_choices('language', '7')   # PT-BR only while its mod is on
        self.root.bind_all('<MouseWheel>', self.wheel)
        if self.tk.TkVersion >= 8.7:     # trackpads: their own event, in pixels
            self.root.bind_all('<TouchpadScroll>', self.touchpad)
        if not (WINDOWS or MAC) and self.tk.TkVersion < 8.7:   # X11 before Tk 8.7: the wheel is buttons 4 and 5
            self.root.bind_all('<Button-4>', lambda e: self.wheel(e, -1))
            self.root.bind_all('<Button-5>', lambda e: self.wheel(e, 1))
        self.refresh_status()

    def fullscreen_keys(self):
        return 'F11 ' + tr('or') + (' Ctrl+Cmd+F' if MAC else ' Alt+Enter')

    WHEEL_STEP = 40     # pixels per wheel notch

    def page_scroll(self, event):
        page = self.pages.get(self.current)
        if hasattr(page, 'scroll') and 'combobox' not in str(event.widget).lower():
            return page.scroll
        return None

    def wheel(self, event, notches=None):
        """A wheel notch is 120 from Tk 8.7 on, and on Windows; Tk 8.6 on
        macOS counts 1 per notch."""
        scroll = self.page_scroll(event)
        if not scroll:
            return
        if notches is None:
            notches = -event.delta / 120 if WINDOWS or self.tk.TkVersion >= 8.7 else -event.delta
        scroll(round(notches * self.WHEEL_STEP))

    def touchpad(self, event):
        scroll = self.page_scroll(event)
        if scroll:
            _dx, dy = (int(v) for v in self.root.tk.splitlist(self.root.tk.call('tk::PreciseScrollDeltas', event.delta)))
            if dy:
                scroll(-dy)

    def show(self, name):
        self.cancel_capture()
        for p in self.pages.values():
            p.pack_forget()
        self.pages[name].pack(fill='both', expand=True)
        self.current = name
        for n, item in self.nav.items():
            item.configure(bg=PANEL if n == name else BG, fg=GOLD if n == name else TEXT)
        if name == 'mods':
            self.refresh_mods()
        elif name == 'game':
            self.refresh_backups()

    # ---- home: backgrounds that cross-fade, the logo, quick settings --------------------------
    def build_home(self):
        tk, ttk = self.tk, self.ttk
        page = tk.Frame(self.content, bg=PANEL)
        self.pages['home'] = page
        self.banner = tk.Canvas(page, bg=BG, highlightthickness=0, bd=0)
        self.banner.pack(fill='both', expand=True)
        self.banner_item = self.banner.create_image(0, 0, anchor='nw')
        self.banner.bind('<Configure>', lambda _e: self.root.after_idle(self.draw_banner))
        quick = ttk.Frame(page, padding=(30, 12, 30, 14))
        quick.pack(fill='x')
        ttk.Label(quick, text=tr('QUICK SETTINGS'), style='Section.TLabel').grid(row=0, column=0, columnspan=4, sticky='w')
        tk.Frame(quick, bg=LINE, height=1).grid(row=1, column=0, columnspan=4, sticky='we', pady=(3, 8))
        items = ((tr('Display mode'), 'display_mode', DISPLAY_MODES), (tr('Window size'), 'window_size', WINDOW_SIZES),
                 (tr('Language'), 'language', self.languages), (tr('FPS counter'), 'perf_overlay', ON_OFF))
        for i, (title, key, options) in enumerate(items):
            r, c = 2 + i // 2, (i % 2) * 2
            ttk.Label(quick, text=title).grid(row=r, column=c, sticky='w', pady=5, padx=(0, 14))
            self.choice(quick, key, options, width=24).grid(row=r, column=c + 1, sticky='w', padx=(0, 46))

    def cover(self, path, w, h):
        """The image scaled to cover w x h, darkened toward the left and bottom."""
        from PIL import Image
        key = (path, w, h)
        if key in self.bg_cache:
            return self.bg_cache[key]
        with Image.open(path) as im:
            im = im.convert('RGB')
            scale = max(w / im.width, h / im.height)
            im = im.resize((max(w, round(im.width * scale)), max(h, round(im.height * scale))), Image.LANCZOS)
            left, top = (im.width - w) // 2, max(0, (im.height - h) // 3)
            im = im.crop((left, top, left + w, top + h))
        from PIL import ImageChops
        # Left: dark behind the logo. Bottom: into the panel below.
        left = Image.new('L', (256, 1))
        left.putdata([max(40, 200 - int(320 * x / 256)) for x in range(256)])
        bottom = Image.new('L', (1, 256))
        bottom.putdata([int(255 * max(0.0, (y - 141) / 115) ** 1.6) for y in range(256)])
        shade = ImageChops.lighter(left.resize((w, h), Image.BILINEAR), bottom.resize((w, h), Image.BILINEAR))
        dark = Image.new('RGB', (w, h), PANEL)
        im = Image.composite(dark, im, shade)
        if len(self.bg_cache) > 12:
            self.bg_cache.clear()
        self.bg_cache[key] = im
        return im

    def scaled_logo(self, width):
        if not self.logo_src:
            return None
        try:
            from PIL import Image, ImageTk
            with Image.open(self.logo_src) as im:
                im = im.convert('RGBA')
                return ImageTk.PhotoImage(im.resize((width, round(im.height * width / im.width)), Image.LANCZOS))
        except OSError:
            return None

    def banner_frame(self, index, w, h):
        from PIL import Image
        im = self.cover(self.bg_sources[index], w, h).copy()
        if self.logo_src:
            if self.bg_size != (w, h):
                with Image.open(self.logo_src) as lg:
                    lg = lg.convert('RGBA')
                    lw = min(560, int(w * 0.48))
                    self.logo_banner = lg.resize((lw, round(lg.height * lw / lg.width)), Image.LANCZOS)
            im.paste(self.logo_banner, (int(w * 0.04), int(h * 0.08)), self.logo_banner)
        return im

    def draw_banner(self, blend=None):
        if not self.bg_sources:
            return
        from PIL import Image, ImageTk
        w, h = self.banner.winfo_width(), self.banner.winfo_height()
        if w < 50 or h < 50:
            return
        if self.bg_size != (w, h):
            self.frames = {}
        if self.bg_index not in self.frames:
            self.frames[self.bg_index] = self.banner_frame(self.bg_index, w, h)
        self.bg_size = (w, h)
        im = self.frames[self.bg_index]
        if blend:
            nxt, t = blend
            if nxt not in self.frames:
                self.frames[nxt] = self.banner_frame(nxt, w, h)
            im = Image.blend(im, self.frames[nxt], t)
        self.banner_photo = ImageTk.PhotoImage(im)
        self.banner.itemconfigure(self.banner_item, image=self.banner_photo)

    def next_background(self):
        if len(self.bg_sources) < 2 or self.current != 'home' or self.process:
            self.root.after(self.HOLD_MS, self.next_background)
            return
        nxt = (self.bg_index + 1) % len(self.bg_sources)

        def step(i):
            if i > self.FADE_STEPS:
                self.bg_index = nxt
                self.draw_banner()
                self.root.after(self.HOLD_MS, self.next_background)
                return
            t = i / self.FADE_STEPS
            self.draw_banner((nxt, t * t * (3 - 2 * t)))    # smoothstep
            self.root.after(self.FADE_MS, step, i + 1)
        step(1)

    # ---- pages ------------------------------------------------------------------------------
    def build_video(self):
        f = self.page('video', tr('Video'), tr("Renderer, window and the game's picture."))
        rpcs3 = tr('RPCS3 renderer only.')
        self.section(f, tr('Renderer'))
        if MAC:
            hint = (tr('RPCS3 · Vulkan uses MoltenVK (the game needs RPCS3=1 scripts/mac/build.sh, after '
                       'scripts/mac/build-gpu.sh). Live draw draws with Metal.'))
        elif WINDOWS:
            hint = (tr("RPCS3: RPCS3's renderer (needs the game built with -DASCENSION_RPCS3_RSX=ON). Live "
                       "draw: ps3recomp's own drawing."))
        else:
            hint = tr('RPCS3: Vulkan or OpenGL (the game built with -DASCENSION_RPCS3_RSX=ON).')
        self.row(f, tr('Renderer'), self.choice(f, 'renderer', RENDERERS), hint)
        self.row(f, tr('Internal resolution'), self.choice(f, 'render_scale', RENDER_SCALES),
                 tr('The game draws at 1280 x 720; above that it is sharper and heavier on the GPU. ') + rpcs3)
        self.row(f, tr('Anisotropic filtering'), self.choice(f, 'aniso', ANISO_LEVELS),
                 tr('Sharper textures seen at an angle. ') + rpcs3)
        self.section(f, tr('Display'))
        self.row(f, tr('Display mode'), self.choice(f, 'display_mode', DISPLAY_MODES),
                 tr('In game, {keys} switches between window and full screen.', keys=self.fullscreen_keys()))
        self.row(f, tr('Window size'), self.choice(f, 'window_size', WINDOW_SIZES),
                 tr("The size of the game's window") + (tr(' (in pixels; on a Retina display it takes half that in points).') if MAC else '.'))
        self.row(f, tr('Aspect ratio'), self.choice(f, 'aspect', ASPECTS),
                 tr('Stretching distorts the picture in a window that is not 16:9.') + ('' if MAC else ' ' + rpcs3))
        self.row(f, tr('Image scaling'), self.choice(f, 'scale_filter', SCALE_FILTERS),
                 tr('How the picture is enlarged to the window.') + ('' if MAC else ' ' + rpcs3))
        self.row(f, tr('VSync'), self.choice(f, 'vsync', VSYNC_MODES),
                 tr('On: no tearing, but a little more latency. Automatic: Metal and live draw turn it on, '
                    'RPCS3 turns it off.'))
        self.section(f, tr('On-screen information'))
        self.row(f, tr('FPS counter'), self.choice(f, 'perf_overlay', ON_OFF),
                 tr("On macOS, FPS and frame time in the window's title.") if MAC else
                 tr('FPS, frame time, speed, CPU and GPU in the top right corner.'))

    # ---- controls: keyboard and mouse, controller ---------------------------------------------
    def build_controls(self):
        tk = self.tk
        f = self.page('controls', tr('Controls'),
                      tr('Keyboard, mouse and controller work together; whatever is connected responds.'))
        self.section(f, tr('General'))
        self.row(f, tr('Confirm button'), self.choice(f, 'enter_button', ENTER_BUTTONS),
                 tr('Which button accepts in the system menus.'))
        self.row(f, tr('Esc closes the game'), self.choice(f, 'esc_quits', ON_OFF),
                 tr('On, Esc closes the game instead of reaching it (by default Esc is START).'))

        bar = tk.Frame(f, bg=PANEL)
        bar.grid(row=f.next_row, column=0, columnspan=3, sticky='we', pady=(22, 0))
        tk.Frame(f, bg=LINE, height=1).grid(row=f.next_row + 1, column=0, columnspan=3, sticky='we')
        f.next_row += 2
        self.control_tabs, self.control_tab_frames = {}, {}
        for name, title in (('keyboard', tr('KEYBOARD AND MOUSE')), ('pad', tr('CONTROLLER'))):
            holder = tk.Frame(bar, bg=PANEL)
            holder.pack(side='left', padx=(0, 6))
            label = tk.Label(holder, text=title, bg=PANEL, fg=TEXT, font=(self.heading, 11), padx=16, pady=8,
                             cursor='hand2')
            label.pack()
            mark = tk.Frame(holder, bg=PANEL, height=3)
            mark.pack(fill='x')
            label.bind('<Button-1>', lambda _e, n=name: self.show_control_tab(n))
            self.control_tabs[name] = (label, mark)
        for name in ('keyboard', 'pad'):
            frame = tk.Frame(f, bg=PANEL)
            frame.grid(row=f.next_row, column=0, columnspan=3, sticky='we', pady=(10, 0))
            frame.columnconfigure(3, weight=1)
            self.control_tab_frames[name] = frame
        f.next_row += 1
        self.build_keyboard_tab(self.control_tab_frames['keyboard'])
        self.build_pad_tab(self.control_tab_frames['pad'])
        self.show_control_tab('keyboard')

    def show_control_tab(self, name):
        self.cancel_capture()
        for n, (label, mark) in self.control_tabs.items():
            label.configure(fg=GOLD if n == name else MUTED)
            mark.configure(bg=ACCENT_HI if n == name else PANEL)
            if n == name:
                self.control_tab_frames[n].grid()
            else:
                self.control_tab_frames[n].grid_remove()

    def build_keyboard_tab(self, f):
        tk, ttk = self.tk, self.ttk
        top = tk.Frame(f, bg=PANEL)
        top.grid(row=0, column=0, columnspan=4, sticky='we', pady=(0, 6))
        tk.Label(top, text=tr('Click a key and press the new key or mouse button. Esc cancels; × clears.'),
                 bg=PANEL, fg=MUTED, font=(self.ui, 9)).pack(side='left')
        ttk.Button(top, text=tr('Classic (arrows)'), command=lambda: self.key_preset('classic')).pack(side='right')
        ttk.Button(top, text=tr('Default (WASD)'), command=lambda: self.key_preset('pc')).pack(side='right', padx=(0, 8))
        self.key_cells = {}
        r = 1
        for group, items in CONTROL_GROUPS:
            tk.Label(f, text=tr(group).upper(), bg=PANEL, fg=GOLD, font=(self.heading, 10)).grid(
                row=r, column=0, columnspan=4, sticky='w', pady=(14, 4))
            if r == 1:
                for col, head in ((1, tr('PRIMARY')), (2, tr('ALTERNATE'))):
                    tk.Label(f, text=head, bg=PANEL, fg=MUTED, font=(self.ui, 8)).grid(row=r, column=col, sticky='sw',
                                                                                    pady=(14, 4))
            r += 1
            for control, title in items:
                tk.Label(f, text=tr(title), bg=PANEL, fg=TEXT, font=(self.ui, 10), anchor='w', width=26).grid(
                    row=r, column=0, sticky='w', pady=2)
                for slot in (0, 1):
                    self.key_cells[(control, slot)] = self.key_cell(f, control, slot, r, 1 + slot)
                r += 1
        self.refresh_keys()

    def key_cell(self, parent, control, slot, row, column):
        tk = self.tk
        cell = tk.Frame(parent, bg=CARD, highlightthickness=1, highlightbackground=LINE)
        cell.grid(row=row, column=column, sticky='w', padx=(0, 10), pady=2)
        label = tk.Label(cell, text='', bg=CARD, fg=TEXT, font=(self.ui, 10), width=16, pady=4, cursor='hand2')
        label.pack(side='left')
        clear = tk.Label(cell, text='×', bg=CARD, fg=MUTED, font=(self.ui, 11), padx=6, cursor='hand2')
        clear.pack(side='left')
        label.bind('<Button-1>', lambda _e: self.start_capture(control, slot))
        clear.bind('<Button-1>', lambda _e: self.set_key(control, slot, None))
        for w in (label, clear):
            w.bind('<Enter>', lambda _e: cell.configure(highlightbackground=MUTED)
                   if self.capturing != (control, slot) else None)
            w.bind('<Leave>', lambda _e: cell.configure(highlightbackground=LINE)
                   if self.capturing != (control, slot) else None)
        return cell, label

    def refresh_keys(self):
        for (control, slot), (cell, label) in self.key_cells.items():
            keys = self.keymap.get(control, [])
            name = keys[slot] if slot < len(keys) else None
            capturing = self.capturing == (control, slot)
            label.configure(text=tr('Press…') if capturing else tr_key(name),
                            fg=GOLD if capturing else (TEXT if name else MUTED))
            cell.configure(highlightbackground=GOLD if capturing else LINE)

    def set_key(self, control, slot, name):
        """Put `name` in a control's slot; a key used elsewhere leaves that place."""
        self.cancel_capture(refresh=False)
        note = None
        if name:
            for other, keys in self.keymap.items():
                if name in keys and (other, keys.index(name)) != (control, slot):
                    keys.remove(name)
                    note = tr('{key} was removed from {control}.', key=tr_key(name), control=self.control_title(other))
        keys = [k for k in self.keymap.get(control, []) if k]
        while len(keys) <= slot:
            keys.append(None)
        keys[slot] = name
        self.keymap[control] = [k for k in keys if k]
        self.refresh_keys()
        self.refresh_status(note or ' ')

    def control_title(self, control):
        for group, items in CONTROL_GROUPS:
            for c, title in items:
                if c == control:
                    group, title = tr(group), tr(title)
                    return (group.split(' · ')[0] + ' ' + title.lower()) if c.startswith(('ls_', 'rs_')) else title.split('  ')[0]
        return control

    def key_preset(self, name):
        self.cancel_capture(refresh=False)
        self.keymap = {c: list(KEY_PRESETS[name].get(c, [])) for _, items in CONTROL_GROUPS for c, _ in items}
        self.refresh_keys()

    def start_capture(self, control, slot):
        self.cancel_capture(refresh=False)
        self.capturing = (control, slot)
        self.refresh_keys()
        self.refresh_status(tr('Press a key or mouse button for {control} (Esc cancels).', control=self.control_title(control)))
        # Armed a moment later, so the click that started it is not taken as Mouse1.
        self.root.after(250, self.arm_capture, (control, slot))

    def arm_capture(self, which):
        if self.capturing != which:
            return
        self.root.bind_all('<KeyPress>', self.capture_key)
        self.root.bind_all('<ButtonPress>', self.capture_mouse)

    def cancel_capture(self, refresh=True):
        if not getattr(self, 'capturing', None):
            return
        self.capturing = None
        self.root.unbind_all('<KeyPress>')
        self.root.unbind_all('<ButtonPress>')
        if refresh:
            self.refresh_keys()
            self.refresh_status()

    def capture_key(self, event):
        if not self.capturing:
            return None
        if event.keysym == 'Escape':
            self.cancel_capture()
            return 'break'
        sym = event.keysym
        name = TK_KEYS.get(sym)
        if not name and len(sym) == 1 and sym.isascii() and sym.isalnum():
            name = sym.upper()
        if name:
            self.set_key(*self.capturing, name)
        else:
            self.refresh_status(tr('The key "{key}" cannot be used; choose another (Esc cancels).', key=sym))
        return 'break'

    def capture_mouse(self, event):
        if not self.capturing:
            return None
        old_aqua = MAC and self.tk.TkVersion < 8.7          # Tk 8.6 on macOS: 2 is the right button
        names = {1: 'Mouse1', 2: 'Mouse2' if old_aqua else 'Mouse3', 3: 'Mouse3' if old_aqua else 'Mouse2',
                 8: 'Mouse4', 9: 'Mouse5'}
        if WINDOWS and self.tk.TkVersion < 8.7:
            names.update({4: 'Mouse4', 5: 'Mouse5'})
        name = names.get(event.num)
        if name:
            self.set_key(*self.capturing, name)
        return 'break'

    def build_pad_tab(self, f):
        tk, ttk = self.tk, self.ttk
        top = tk.Frame(f, bg=PANEL)
        top.grid(row=0, column=0, columnspan=4, sticky='we', pady=(0, 6))
        tk.Label(top, text=tr('Xbox, PlayStation and other controllers the system recognises. Which '
                              'controller button does each PS3 button:'),
                 bg=PANEL, fg=MUTED, font=(self.ui, 9)).pack(side='left')
        ttk.Button(top, text=tr('Restore defaults'), command=self.pad_defaults).pack(side='right')
        self.pad_vars = {}
        r = 1
        for group, items in CONTROL_GROUPS:
            items = [(c, t) for c, t in items if c in PAD_CONTROLS]
            if not items:
                continue
            tk.Label(f, text=tr(group).upper(), bg=PANEL, fg=GOLD, font=(self.heading, 10)).grid(
                row=r, column=0, columnspan=4, sticky='w', pady=(14, 4))
            r += 1
            for control, title in items:
                tk.Label(f, text=tr(title), bg=PANEL, fg=TEXT, font=(self.ui, 10), anchor='w', width=26).grid(
                    row=r, column=0, sticky='w', pady=2)
                v = self.tk.StringVar(value=self.padmap.get(control, PAD_DEFAULTS[control]))
                v.trace_add('write', lambda *_a, c=control, var=v: self.padmap.__setitem__(c, var.get()))
                self.pad_vars[control] = v
                self.choice_var(f, v, PAD_BUTTONS, width=26).grid(row=r, column=1, sticky='w', pady=2)
                r += 1
        tk.Label(f, text=tr('STICKS'), bg=PANEL, fg=GOLD, font=(self.heading, 10)).grid(
            row=r, column=0, columnspan=4, sticky='w', pady=(14, 4))
        r += 1
        tk.Label(f, text=tr('Dead zone'), bg=PANEL, fg=TEXT, font=(self.ui, 10), anchor='w', width=26).grid(
            row=r, column=0, sticky='w', pady=2)
        self.choice(f, 'pad_deadzone', DEADZONES, width=26).grid(row=r, column=1, sticky='w', pady=2)
        tk.Label(f, text=tr("How much of the sticks' centre is ignored; raise it if the character walks on its own."),
                 bg=PANEL, fg=MUTED, font=(self.ui, 9), wraplength=320, justify='left').grid(
            row=r, column=2, columnspan=2, sticky='w', padx=(18, 0))

    def pad_defaults(self):
        for control, v in self.pad_vars.items():
            v.set(PAD_DEFAULTS[control])
        self.var('pad_deadzone').set('24')

    def choice_var(self, parent, var, options, width=28):
        """A read-only combobox over a StringVar of its own (not a setting key)."""
        options = translated(options)
        shown = self.tk.StringVar()
        box = self.ttk.Combobox(parent, textvariable=shown, state='readonly', width=width,
                                values=[label for _, label in options])
        to_label, to_value = dict(options), {label: value for value, label in options}
        shown.set(to_label.get(var.get(), options[0][1]))
        shown.trace_add('write', lambda *_: shown.get() in to_value and var.set(to_value[shown.get()]))
        var.trace_add('write', lambda *_: shown.get() != to_label.get(var.get()) and shown.set(to_label.get(var.get(), '')))
        box.bind('<MouseWheel>', lambda e: 'break')
        return box

    def build_game(self):
        f = self.page('game', tr('Game'), tr('Language, subtitles and saves.'))
        self.section(f, tr('Language'))
        self.row(f, tr('Game language'), self.choice(f, 'language', self.languages),
                 tr("Text, subtitles and voices follow the PS3's system language. Greek voices: the game itself offers them at first start."))
        sub = self.choice(f, 'subtitles', ON_OFF)
        self.row(f, tr('Subtitles'), sub, tr('Subtitles for dialogue and cinematics.'))
        self.note(f, tr('The game keeps the language and subtitles in its system save; the launcher sets '
                        'them there before each start, so they hold after the first start too.'))
        self.section(f, tr('Saves'))
        self.row(f, tr('Back up before playing'), self.choice(f, 'backup_saves', ON_OFF),
                 tr('Copies the saves to gamedata/save-backups (the last 10 are kept).'))
        holder = self.ttk.Frame(f)
        self.ttk.Button(holder, text=tr('Open saves folder'), command=lambda: self.open_path(save_dir())).pack(side='left')
        self.ttk.Button(holder, text=tr('Open backups'), command=lambda: self.open_path(ROOT / 'gamedata' / 'save-backups')).pack(
            side='left', padx=(8, 0))
        self.row(f, '', holder)
        holder = self.ttk.Frame(f)
        self.backup_box = self.ttk.Combobox(holder, state='readonly', width=30)
        self.backup_box.bind('<MouseWheel>', lambda e: 'break')
        self.backup_box.pack(side='left')
        self.restore_button = self.ttk.Button(holder, text=tr('Restore'), command=self.restore_backup)
        self.restore_button.pack(side='left', padx=(8, 0))
        self.row(f, tr('Restore a backup'), holder, tr('The current saves become a backup first, so nothing is lost.'))
        self.refresh_backups()

    def refresh_backups(self):
        self.backups = backup_list()
        labels = []
        for d in self.backups:
            try:
                labels.append(time.strftime('%d/%m/%Y  %H:%M:%S', time.strptime(d.name, '%Y%m%d-%H%M%S')))
            except ValueError:
                labels.append(d.name)
        self.backup_box.configure(values=labels)
        self.backup_box.set(labels[0] if labels else tr('No backups'))
        busy = self.process or self.preparing or not labels
        self.restore_button.configure(state='disabled' if busy else 'normal')

    def restore_backup(self):
        i = self.backup_box.current()
        if i < 0 or self.process or self.preparing:
            return
        label = self.backup_box.get()
        if not self.messagebox.askyesno(APP_NAME, tr('Put the saves back to {label}?', label=label)):
            return
        try:
            restore_saves(self.backups[i])
        except OSError as e:
            self.messagebox.showerror(APP_NAME, tr('Could not restore:\n{error}', error=e))
            return
        self.refresh_backups()
        self.refresh_status(tr('Saves restored from {label}.', label=label))

    def build_mods(self):
        f = self.page('mods', tr('Mods'), tr('Turn them on and off, and order them. The first in the list wins when two change the same file.'))
        self.section(f, tr('Mods'))
        self.mods_frame = self.tk.Frame(f, bg=PANEL)
        self.mods_frame.grid(row=f.next_row, column=0, columnspan=3, sticky='we')
        self.mods_frame.columnconfigure(0, weight=1)
        f.next_row += 1
        self.section(f, tr('Brazilian Portuguese'))
        self.note(f, tr('The European disc already has the Brazilian Portuguese text; the voices come from '
                        'the US disc. Choose the image (.iso) of your US disc, or its extracted folder, and '
                        'the launcher builds the PT-BR mod in your mods folder. With it on, Português '
                        '(Brasil) shows up under Language.'))
        holder = self.ttk.Frame(f)
        self.ttk.Button(holder, text=tr('Create PT-BR mod from the US disc (.iso)…'),
                        command=lambda: self.make_ptbr(folder=False)).pack(side='left')
        self.ttk.Button(holder, text=tr('…or from the extracted folder'), command=lambda: self.make_ptbr(folder=True)).pack(
            side='left', padx=(8, 0))
        holder.grid(row=f.next_row, column=0, columnspan=3, sticky='w', pady=(8, 0))
        f.next_row += 1
        self.section(f, tr('Mods folder'))
        self.path_row(f, 'mods_dir', tr('Folder'), folder=True)
        self.note(f, tr("Each mod is a subfolder that mirrors the game's USRDIR (a mod that replaces "
                        'GAME.PSARC carries <mod>/GAME.PSARC), or a mod.json with a recipe the launcher '
                        "applies to your disc's files when playing. The included mods come with Ascension "
                        'and carry nothing from the game.'))
        holder = self.ttk.Frame(f)
        self.ttk.Button(holder, text=tr('Refresh list'), command=self.refresh_mods).pack(side='left')
        self.ttk.Button(holder, text=tr('Open folder'),
                        command=lambda: self.open_path(Path(self.var('mods_dir').get()), make=True)).pack(side='left', padx=(8, 0))
        holder.grid(row=f.next_row, column=0, columnspan=3, sticky='w', pady=(10, 0))
        f.next_row += 1
        self.var('mods_dir').trace_add('write', lambda *_: self.refresh_mods())
        self.mod_order = list(self.s['mods_order'])
        self.mod_vars = {}
        self.refresh_mods()

    def current_mod_settings(self):
        enabled = [m for m, v in self.mod_vars.items() if v.get()] if self.mod_vars else list(self.s['mods_enabled'])
        return {**self.s, 'mods_dir': self.var('mods_dir').get(), 'mods_enabled': enabled,
                'mods_order': list(getattr(self, 'mod_order', self.s['mods_order']))}

    def switch(self, parent, var, command):
        """An on/off switch: a pill that is red-gold when on."""
        tk = self.tk
        c = tk.Canvas(parent, width=46, height=24, bg=CARD, highlightthickness=0, bd=0, cursor='hand2')

        def draw(*_):
            c.delete('all')
            on = var.get()
            fill = ACCENT_HI if on else '#3a302a'
            c.create_oval(2, 2, 22, 22, fill=fill, outline=fill)
            c.create_oval(24, 2, 44, 22, fill=fill, outline=fill)
            c.create_rectangle(12, 2, 34, 22, fill=fill, outline=fill)
            x = 26 if on else 4
            c.create_oval(x, 4, x + 16, 20, fill='#fbf1e2' if on else '#8a7f76', outline='')

        def toggle(_e=None):
            var.set(not var.get())
            draw()
            command()
        c.bind('<Button-1>', toggle)
        var.trace_add('write', draw)
        draw()
        return c

    def refresh_mods(self):
        tk, ttk = self.tk, self.ttk
        for w in self.mods_frame.winfo_children():
            w.destroy()
        s = self.current_mod_settings()
        mods = all_mods({**s, 'mods_order': self.mod_order})
        self.mod_order = [m['id'] for m in mods]
        enabled = set(s['mods_enabled'])
        if not mods:
            ttk.Label(self.mods_frame, text=tr('No mods.'), style='Muted.TLabel').grid(row=0, column=0, sticky='w')
        for i, m in enumerate(mods):
            v = self.mod_vars.get(m['id']) or tk.BooleanVar(value=m['id'] in enabled)
            self.mod_vars[m['id']] = v
            card = tk.Frame(self.mods_frame, bg=CARD, highlightthickness=1, highlightbackground=LINE)
            card.grid(row=i, column=0, sticky='we', pady=4)
            card.columnconfigure(1, weight=1)
            self.switch(card, v, self.mods_changed).grid(row=0, column=0, rowspan=2, padx=(14, 14), pady=12)
            head = tk.Frame(card, bg=CARD)
            head.grid(row=0, column=1, sticky='w', pady=(10, 0))
            tk.Label(head, text=m['name'], bg=CARD, fg=TEXT, font=(self.heading, 11)).pack(side='left')
            if m['builtin']:
                tk.Label(head, text=tr(' INCLUDED '), bg='#3a2a14', fg=GOLD, font=(self.ui, 7, 'bold')).pack(side='left', padx=(10, 0))
            tk.Label(card, text=m['description'] or str(m['path']), bg=CARD, fg=MUTED, font=(self.ui, 9),
                     wraplength=620, justify='left').grid(row=1, column=1, sticky='w', pady=(2, 10))
            arrows = tk.Frame(card, bg=CARD)
            arrows.grid(row=0, column=2, rowspan=2, padx=12)
            for txt, step in (('▲', -1), ('▼', 1)):
                b = tk.Label(arrows, text=txt, bg=CARD, fg=MUTED if (step < 0 and i == 0) or (step > 0 and i == len(mods) - 1) else TEXT,
                             font=(self.ui, 10), cursor='hand2', padx=6)
                b.pack(side='top')
                b.bind('<Button-1>', lambda _e, mid=m['id'], st=step: self.move_mod(mid, st))
        self.mods_changed()

    def languages(self):
        return language_options(self.current_mod_settings())

    def mods_changed(self):
        self.refresh_choices('language', '7')

    def make_ptbr(self, folder):
        if folder:
            src = self.filedialog.askdirectory(title=tr('US disc folder (with PS3_GAME)'))
        else:
            src = self.filedialog.askopenfilename(title=tr('US disc image'),
                                                  filetypes=[(tr('Disc image'), '*.iso'), (tr('All'), '*.*')])
        if not src:
            return
        out = Path(self.var('mods_dir').get()) / 'PT-BR'
        eu = Path(self.var('eboot').get()).parent
        self.refresh_status(tr('Creating the PT-BR mod… (copies ~140 MB)'))

        def work():
            import importlib.util
            try:
                spec = importlib.util.spec_from_file_location('make_ptbr_mod', ROOT / 'tools' / 'make_ptbr_mod.py')
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                us, unmount = Path(src), None
                if us.suffix.lower() == '.iso':
                    us, unmount = mod.mount_iso(us)
                elif (us / 'PS3_GAME' / 'USRDIR').is_dir():
                    us = us / 'PS3_GAME' / 'USRDIR'
                try:
                    mod.build(us, eu, out, log=lambda m: None)
                finally:
                    if unmount:
                        unmount()
                self.root.after(0, self.ptbr_done, None)
            except BaseException as e:   # SystemExit carries the reason
                self.root.after(0, self.ptbr_done, str(e) or type(e).__name__)
        threading.Thread(target=work, daemon=True).start()

    def ptbr_done(self, error):
        if error:
            self.refresh_status(tr('The PT-BR mod was not created.'))
            self.messagebox.showerror(APP_NAME, tr('Could not create the PT-BR mod:\n{error}', error=error))
            return
        if 'PT-BR' not in self.mod_order:
            self.mod_order.insert(0, 'PT-BR')
        self.mod_vars['PT-BR'] = self.tk.BooleanVar(value=True)
        self.refresh_mods()
        self.var('language').set('17')
        self.refresh_choices('language', '7')
        self.refresh_status(tr('PT-BR mod created and turned on; language: Português (Brasil). Click Save.'))

    def move_mod(self, name, step):
        i = self.mod_order.index(name)
        j = i + step
        if 0 <= j < len(self.mod_order):
            self.mod_order[i], self.mod_order[j] = self.mod_order[j], self.mod_order[i]
            self.refresh_mods()

    def build_advanced(self):
        f = self.page('advanced', tr('Advanced'), tr("Paths, the launcher's music and runtime variables."))
        self.section(f, tr('Game files'))
        self.path_row(f, 'game_exe', tr('Executable'))
        self.path_row(f, 'eboot', 'EBOOT.ELF')
        self.path_row(f, 'disc_dir', tr('Disc folder'), folder=True,
                      hint=tr('The folder with PS3_GAME.') + (tr(' With the image below, the launcher mounts it here.') if MAC else
                                                       tr(" Empty: the EBOOT.ELF's own.")))
        if MAC:
            self.path_row(f, 'disc_iso', tr('Disc image (.iso)'),
                          hint=tr('Mounted read-only at the disc folder when playing.'))
        self.section(f, tr('Launcher'))
        self.row(f, tr('Background music'), self.choice(f, 'music', ON_OFF))
        self.row(f, tr('Discord Rich Presence'), self.choice(f, 'discord_rpc', ON_OFF),
                 tr('Shows only the game name and how long you have played on your Discord profile.'))
        self.row(f, tr('Launcher language'), self.choice(f, 'ui_language', [('auto', "Automatic (the system's)")] + available()),
                 tr("The launcher's own text only; the game's language is under Game."))
        self.var('ui_language').trace_add('write', lambda *_: self.root.after_idle(self.language_changed))
        self.section(f, tr('Runtime'))
        entry = self.ttk.Entry(f, textvariable=self.var('extra_env'), width=70)
        self.row(f, tr('Extra variables'), entry)
        self.note(f, tr('Separated by ";", for example  PS3_VERBOSE=1;VDEC_TIMELOG=1.  For debugging.'))
        self.section(f, tr('Log'))
        holder = self.ttk.Frame(f)
        self.ttk.Button(holder, text=tr('Open last log'), command=lambda: self.open_path(self.log_path())).pack(side='left')
        self.ttk.Button(holder, text=tr('Game folder'), command=lambda: self.open_path(ROOT)).pack(side='left', padx=(8, 0))
        self.row(f, '', holder)

    def language_changed(self):
        """A new launcher language takes a new window: restart now, or on the next start."""
        code = self.var('ui_language').get()
        if code == self.ui_language or getattr(self, 'asking_language', False):
            return
        if self.process or self.preparing:
            self.var('ui_language').set(self.ui_language)
            self.refresh_status(tr("Close the game before changing the launcher's language."))
            return
        self.asking_language = True
        restart = self.messagebox.askyesno(APP_NAME, tr('Restart the launcher now to change the language?'))
        self.asking_language = False
        if not restart:
            self.refresh_status(tr('The language changes the next time the launcher opens (click Save).'))
            return
        self.save()
        self.music.close()
        release_disc(self.mounted)
        # Frozen (packaging/windows/AscensionLauncher.exe): sys.argv already
        # starts with the exe's own path. Running from source: it is the
        # script's argv, which needs the interpreter in front of it.
        subprocess.Popen(sys.argv if FROZEN else [sys.executable] + sys.argv, cwd=os.getcwd())
        self.root.destroy()

    def build_about(self):
        f = self.page('about', tr('About'), f'{APP_NAME} (PC) · launcher v{VERSION}')
        self.section(f, tr('The project'))
        self.note(f, tr("God of War: Ascension (PS3) recompiled to run natively on a PC. The game's PowerPC "
                        'code is translated to C and compiled for x86-64; the SPU code is recompiled too, '
                        "and what the PS3's system did (RSX video, audio, files, SPURS) is reimplemented by "
                        'the ps3recomp runtime. It is not an emulator and carries nothing from the game: '
                        'you need your own disc.'))
        self.note(f, tr('Status: experiment. The game goes from boot to the first level, but still slowly '
                        '(main menu at ~30 fps, first level at ~16-17 fps). See the progress in the repository.'))
        self.section(f, tr('Links'))
        for title, url in ((tr('This project'), 'https://github.com/arnaldolima1/gow-ascension-pc'),
                           (tr('Milestones'), 'https://github.com/arnaldolima1/gow-ascension-pc/blob/main/docs/MILESTONES.md'),
                           ('ps3recomp (sp00nznet)', 'https://github.com/sp00nznet/ps3recomp')):
            link = self.tk.Label(f, text=url, bg=PANEL, fg=GOLD, cursor='hand2', font=(self.ui, 10, 'underline'))
            link.bind('<Button-1>', lambda _e, u=url: webbrowser.open(u))
            self.row(f, title, link)
        self.section(f, tr('Credits'))
        self.note(f, tr('By Arnaldo Lima, with the ps3recomp runtime by sp00nznet and contributors. '
                        "Launcher in the style of gow3_pc's (FelipePrado0). Cinzel typeface (SIL Open Font "
                        'License).'))
        self.note(f, tr('God of War is a trademark of Sony Interactive Entertainment. A non-profit fan '
                        'project, not affiliated with Sony or Santa Monica Studio.'))

    # ---- state ------------------------------------------------------------------------------
    def gather(self):
        values = {k: v.get() for k, v in self.vars.items()}
        values['keymap'] = {c: list(k) for c, k in self.keymap.items()}
        values['padmap'] = dict(self.padmap)
        values['mods_order'] = list(getattr(self, 'mod_order', self.s['mods_order']))
        if getattr(self, 'mod_vars', None):
            values['mods_enabled'] = [m for m, v in self.mod_vars.items() if v.get()]
        else:
            values['mods_enabled'] = list(self.s['mods_enabled'])
        return values

    def watch_changes(self):
        dirty = self.gather() != self.saved
        self.save_button.configure(state='normal' if dirty else 'disabled')
        if self.var('music').get() != ('1' if self.music_on() else '0'):
            self.set_music(self.var('music').get() == '1')
        self.refresh_music_label()
        paths = tuple(self.vars[k].get() for k in ('game_exe', 'eboot', 'disc_dir', 'disc_iso') if k in self.vars)
        if paths != getattr(self, 'watched_paths', paths) and not (self.process or self.preparing):
            self.refresh_status()
        self.watched_paths = paths
        self.root.after(400, self.watch_changes)

    def save(self):
        self.s.update(self.gather())
        save_settings(self.s)
        self.saved = self.gather()
        self.save_button.configure(state='disabled')
        self.refresh_status(tr('Settings saved.'))
        threading.Thread(target=prebuild_mods, args=(dict(self.s),), daemon=True).start()

    def refresh_status(self, text=None):
        if text is None:
            s = {**self.s, **self.gather()}
            gone, problem = missing(s), disc_problem(s)
            text = (tr('Missing {items}', items=tr(' and ').join(gone)) if gone else
                    tr('Warning: {problem}.', problem=problem) if problem else tr('Ready to play.'))
        self.status.configure(text=text)

    # ---- music ------------------------------------------------------------------------------
    def music_on(self):
        return getattr(self, '_music_on', self.s.get('music') == '1')

    def set_music(self, on):
        self._music_on = on
        if on and not self.process:
            self.music.play()
        else:
            self.music.pause()
        self.var('music').set('1' if on else '0')
        self.refresh_music_label()

    def toggle_music(self):
        self.set_music(not self.music_on())

    def refresh_music_label(self):
        if not hasattr(self, 'music_label'):
            return
        err = getattr(getattr(self, 'music', None), 'error', '')
        if err and self.music_on():
            text = tr('♪ Music: ') + err
        else:
            text = tr('♪ Music: on') if self.music_on() else tr('♪ Music: off')
        self.music_label.configure(text=text)

    # ---- actions ----------------------------------------------------------------------------
    def log_path(self):
        return ROOT / 'build' / 'logs' / 'last_run.log'

    def open_path(self, path, make=False):
        path = Path(path)
        if make:
            path.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            self.messagebox.showinfo(APP_NAME, tr('Does not exist yet:\n{path}', path=path))
            return
        if WINDOWS:
            os.startfile(str(path))
        else:
            subprocess.Popen(['open' if MAC else 'xdg-open', str(path)])

    def play(self):
        """The slow part (disc, saves, mods) runs in a thread with its steps in
        the status bar; the window gives way to the game only once it starts."""
        if self.process or self.preparing:
            return
        if self.gather() != self.saved:
            self.save()
        gone = missing(self.s)
        if gone:
            self.messagebox.showerror(APP_NAME, tr('Could not find {items}.\nSet it in Advanced.', items=tr(' and ').join(gone)))
            return
        problem = disc_problem(self.s)
        if problem:
            self.messagebox.showerror(APP_NAME, tr('This game was built from the European release, but {problem}.', problem=problem))
            return
        self.preparing = True
        self.play_button.configure(state='disabled')
        s = dict(self.s)

        def work():
            try:
                env, mounted = prepare_game(s, status=lambda m: self.root.after(0, self.refresh_status, m))
                self.root.after(0, self.launch, env, mounted)
            except Exception as e:
                self.root.after(0, self.launch_failed, str(e) or type(e).__name__)
        threading.Thread(target=work, daemon=True).start()

    def launch(self, env, mounted):
        self.mounted = self.mounted or mounted
        host = self.enter_game_view()
        try:
            self.process, self.log = start_game(self.s, env, self.log_path(),
                                                parent=host.winfo_id() if host else None)
        except Exception as e:
            self.leave_game_view()
            self.launch_failed(str(e) or type(e).__name__)
            return
        self.preparing = False
        self.music.pause()
        if self.s.get('discord_rpc') == '1':
            self.discord.start()
        self.refresh_backups()
        self.refresh_status(tr('Game running…'))
        threading.Thread(target=self.wait_game, daemon=True).start()

    def launch_failed(self, error):
        self.preparing = False
        self.play_button.configure(state='normal')
        self.refresh_status()
        self.messagebox.showerror(APP_NAME, tr('The game did not start:\n{error}', error=error))

    def enter_game_view(self):
        """The launcher's window becomes the game's: the pages give way to a
        black area the game renders into, at the chosen size or full screen.
        Elsewhere the game opens a window of its own and the launcher hides."""
        root = self.root
        if not WINDOWS:
            root.withdraw()
            root.update_idletasks()
            root.update()
            mac_dock(False)
            return None
        self.prev_geometry, self.prev_minsize = root.geometry(), root.minsize()
        self.side.pack_forget()
        self.right.pack_forget()
        self.game_host = self.tk.Frame(root, bg='black', highlightthickness=0, bd=0)
        self.game_host.pack(fill='both', expand=True)
        root.minsize(320, 180)
        if self.s['display_mode'] == 'fullscreen':
            root.attributes('-fullscreen', True)
        else:
            w, h = self.s['window_size'].split('x')
            root.geometry(f'{w}x{h}+{max(0, root.winfo_x())}+{max(0, root.winfo_y())}')
        root.update_idletasks()
        root.update()
        return self.game_host

    def leave_game_view(self):
        root = self.root
        if not WINDOWS:
            mac_dock(True)
            root.deiconify()
            root.lift()
            return
        root.attributes('-fullscreen', False)
        if WINDOWS:   # the game's F11 may have left the frame borderless
            try:
                frame = int(root.wm_frame(), 16)
                u = ctypes.windll.user32
                u.SetWindowLongW(frame, -16, 0x00CF0000 | 0x10000000)   # GWL_STYLE: WS_OVERLAPPEDWINDOW | WS_VISIBLE
                u.SetWindowPos(frame, 0, 0, 0, 0, 0, 0x0027)           # NOSIZE|NOMOVE|NOZORDER|FRAMECHANGED
            except (AttributeError, OSError, ValueError):
                pass
        if getattr(self, 'game_host', None):
            self.game_host.destroy()
            self.game_host = None
        root.minsize(*self.prev_minsize)
        root.geometry(self.prev_geometry)
        self.side.pack(side='left', fill='y')
        self.right.pack(side='left', fill='both', expand=True)

    def wait_game(self):
        code = self.process.wait()
        try:
            self.root.after(0, self.game_ended, code)
        except RuntimeError:     # the launcher closed first
            pass

    def game_ended(self, code):
        self.discord.stop()
        self.log.close()
        self.process = None
        self.play_button.configure(state='normal')
        self.leave_game_view()
        self.refresh_backups()
        if self.music_on():
            self.music.play()
        if code == 0:
            self.refresh_status(tr('Game closed.'))
            return
        self.refresh_status(tr('The game ended with code {code}.', code=code))
        if self.messagebox.askyesno(APP_NAME, tr("The game ended with code {code}.\nOpen this run's log?", code=code)):
            self.open_path(self.log_path())

    def close(self):
        if self.process:
            if not self.messagebox.askyesno(APP_NAME, tr('Close the game?')):
                return
            self.discord.stop()
            self.process.terminate()
            try:
                self.process.wait(5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.log.close()
        if self.gather() != self.saved and self.messagebox.askyesno(APP_NAME, tr('Save the changes before leaving?')):
            self.save()
        self.music.close()
        release_disc(self.mounted)
        self.root.destroy()
