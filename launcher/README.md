# Launcher

`ascension_launcher.py` (Python 3 with Tk, and Pillow) sets up the game and starts it. Open it with `scripts\windows\launcher.ps1`, `scripts/mac/launcher.sh` or `scripts/linux/launcher.sh`, or `python launcher/ascension_launcher.py`; `--play` starts the game with the saved settings and no window. The code is in `app/`: `config.py` (paths, settings, the pages' choices), `game.py` (disc, mods, saves, environment), `music.py`, `native.py` (macOS Dock, fonts) and `ui.py` (the window).

On macOS (paused, like the rest of the macOS support): `brew install python@3.12 python-tk@3.12`, a venv with `pip install pillow`, then `scripts/mac/launcher.sh`. The game opens a window of its own (the launcher hides until it closes), the disc `.iso` set in Advanced is mounted read-only at `work/disc` when needed, the executable is `build/mac/AscensionRecomp` (`scripts/mac/build.sh`) and the `EBOOT.ELF` is read from `input/`. Music plays through `/usr/bin/afplay`.

Pages: Home (cross-fading artwork, quick settings), Video, Controls, Game, Mods, Advanced. Settings are kept in `%APPDATA%\ascension-launcher\settings.json` (macOS: `~/Library/Application Support/ascension-launcher/settings.json`, Linux: `~/.config/ascension-launcher/settings.json`) and reach the game as ps3recomp environment switches:

| Setting | Switch |
|---|---|
| Renderer | `PS3_RSX=rpcs3` and `PS3_RSX_RENDERER=vulkan`/`opengl` (RPCS3's RSX, a build with `-DASCENSION_RPCS3_RSX=ON`), or neither (live draw). macOS: Vulkan through MoltenVK, or live draw's Metal. OpenGL is not offered on macOS |
| Internal resolution, anisotropic filter | `PS3_RENDER_SCALE` (percent), `PS3_ANISO` (RPCS3 only) |
| Display mode, window size | `PS3_FULLSCREEN`, `PS3_WINDOW_SIZE` (F11 or Alt+Enter toggles in game; macOS F11 or Ctrl+Cmd+F) |
| Aspect ratio, image scaling | `PS3_ASPECT=keep`/`stretch`, `PS3_SCALE_FILTER=linear`/`nearest`/`fsr` (RPCS3 and Metal) |
| VSync | `PS3_VSYNC=1`/`0`, unset for each renderer's own (Metal and live draw on, RPCS3 off) |
| Keyboard and mouse | `PS3_KEYMAP` (`cross=Space,K;square=J,Mouse1;...`, two keys per control) |
| Controller | `PS3_PADMAP` (`cross=a;circle=b;...`), `PS3_PAD_DEADZONE` (percent) |
| Disc folder | `PS3_VFS_ROOT` (when set; on macOS `work/disc`) |
| Language | `PS3_SYS_LANG` (the console language, read when the game makes its system save), and bytes `0x1C` (text) / `0x1D` (voices) of `BCES01741-SYSDATA/SAVEDATA` afterwards |
| Subtitles | byte `0x28` of the same file (the game's `-subtitlesOn` drives the same switch) |
| Confirm button | `PS3_ENTER_BUTTON` |
| Esc closes the game | `PS3_ESC_QUITS` |
| FPS counter | `LD_PERF_OVERLAY` (macOS: `PS3RECOMP_METAL_FPS`, in the window's title) |
| Embedded | `PS3_PARENT_HWND` (the game renders inside the launcher's window) |
| Mods | `PS3_MODS` (enabled folders, first wins; each mirrors `USRDIR`) |
| Icon | `PS3_WINDOW_ICON` (`icon-2.png` as an `.ico`; the `.png` on macOS) |

Discord Rich Presence (Advanced → Launcher, off by default) is launcher-only, not an environment switch: while the game runs, the launcher shows its name and how long it has been running on the player's Discord profile, nothing else, by talking to the local Discord client's IPC pipe directly (`app/discord_presence.py`, no extra package). It uses the project's own Discord application id, set in `CLIENT_ID` at the top of that file (one from <https://discord.com/developers/applications>, free); clearing that constant turns it back into a no-op.

Mods come from two places, listed together in one priority order (first wins): `mods-builtin/` in this repository (shown as included) and the user's mods folder. A mod is a folder that mirrors `USRDIR` (its files replace the disc's), and/or a `mod.json`:

```json
{"name": "Skip intro", "description": "...",
 "translations": {"pt-BR": {"name": "Pular intro", "description": "..."}},
 "psarc_patches": {"GAME.PSARC": {"/INTRO/BOOT_BCES01741.TXT": {"text": ""}}}}
```

`psarc_patches` are recipes for files inside an archive: `{"text": ...}` replaces one, `{"insert_after": <line>, "line": <new line>}` adds a line. At PLAY the launcher builds each patched archive once from the disc's copy (or from the copy the highest-priority mod ships) into `%APPDATA%\ascension-launcher\generated\`, applying every enabled mod's recipes, lowest priority first, and puts that folder first in `PS3_MODS`. `translations` (optional) gives the name and description in the launcher's other languages. Included: **Skip intro** (an empty boot-screen list).

Brazilian Portuguese needs the PT-BR mod, which the Mods page builds from your own US disc (an `.iso` or its extracted folder) with `tools/make_ptbr_mod.py`; with it on, the language list offers Português (Brasil).

Saves are copied to `gamedata\save-backups\` before each start, unless the newest copy already matches them (the last ten are kept). The Game page restores any of them (the current saves become a backup first). The run's output goes to `build\logs\last_run.log`, the run before it to `last_run.prev.log`; when the game ends with an error the launcher offers to open the log. PLAY prepares the disc, saves and mods in the background, with each step in the status bar, and refuses a disc whose `PARAM.SFO` is not `BCES01741`. Saving the settings also builds the mods' archives ahead of time when the disc is there; on macOS the `.iso` the launcher mounted is unmounted when it closes.

The artwork and music are not in the repository. The launcher reads `background*.jpg/png`, `logo.png`, `icon-2.png` and `music.mp3` from `launcher\assets\` or `..\work\data\launcher\`; without them it still works, plainer. `Cinzel-Black.ttf` is the Cinzel typeface (SIL Open Font License, `OFL-Cinzel.txt`).

## Languages

The launcher's own text is in English, Brazilian Portuguese or Spanish: Advanced → Launcher language, **Automatic** by default (the system's language, else English); changing it restarts the launcher. The game's language is a separate setting, on the Game page.

The code is written in English and passes each text through `tr()` (`app/i18n.py`). A language is a file in `lang/` named by its code (`pt-BR.json`, `es.json`) mapping each English text to its translation, with `"_name"` as the language's own name; `{name}` fields are kept as they are. Text missing from a file stays in English. Adding a language is adding a file.

## Controls

The Controls page has two tabs. **Keyboard and mouse:** every PS3 control (both sticks' four directions, the buttons, the shoulders and triggers, L3/R3, the d-pad, START and SELECT) takes two keys or mouse buttons; click one and press the new key or button (Esc cancels, × clears it), and a key taken from another control leaves that one. Two presets: **Default (WASD)** (WASD walks, the arrows evade, Space/J/I/L or the mouse for the face buttons, Shift blocks, Esc or Enter pauses) and **Classic (arrows)** (the runtime's old fixed map: arrows, Z/X/A/S, Q/W, 1/2). **Controller:** which controller button acts as each PS3 button, and the sticks' dead zone. Keyboard, mouse and controller all work at once, on the first pad.
