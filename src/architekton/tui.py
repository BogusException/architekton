"""Curses-based config editor driven by config/schema.json.

Keyboard (main screen):
  arrows / j / k    move between fields
  space / enter     toggle bool, cycle enum, begin text edit
  s                 save (floating confirm dialog)
  b                 browse and restore from a saved backup
  r                 restore factory defaults (floating confirm dialog)
  q                 quit (floating dialog: s=save+quit, d=discard, esc=cancel)
  ESC               cancel text edit
"""

import binascii
import curses
import datetime
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from architekton import config as _cfg
from architekton.schema_validator import _load_schema, _resolve_ref


# ── field model ────────────────────────────────────────────────────────────

@dataclass
class _Section:
    name: str


@dataclass
class _Field:
    path: list
    label: str
    section: str
    ftype: str
    enum: Any
    minimum: Any
    maximum: Any
    default: Any
    is_object: bool


@dataclass
class _BackupEntry:
    path: Path
    dt: Any        # datetime.datetime or None
    size: int
    crc32: str


# ── schema flattening ──────────────────────────────────────────────────────

def _flatten(schema: dict) -> list:
    root = schema

    def ref(node):
        if "$ref" not in node:
            return node
        resolved = _resolve_ref(node["$ref"], root)
        merged = dict(resolved)
        for k, v in node.items():
            if k != "$ref":
                merged[k] = v
        return merged

    def walk(node, path, parent_section):
        node = ref(node)
        section = node.get("x-section", parent_section) or "general"
        label = node.get("x-label")
        ftype = node.get("type", "string")

        if ftype == "object":
            props = node.get("properties", {})
            if props:
                for k, child in props.items():
                    yield from walk(child, path + [k], section)
                return
            if label:
                yield _Field(path=path, label=label, section=section,
                             ftype="string", enum=None, minimum=None,
                             maximum=None, default=node.get("default"),
                             is_object=True)
            return

        if not label:
            return

        enums = node.get("enum")
        if enums is None and "anyOf" in node:
            enums = []
            for branch in node["anyOf"]:
                b = ref(branch)
                if "enum" in b:
                    enums.extend(b["enum"])
                elif b.get("type") == "string" and "" not in enums:
                    enums.insert(0, "")

        yield _Field(
            path=path, label=label, section=section, ftype=ftype,
            enum=enums, minimum=node.get("minimum"),
            maximum=node.get("maximum"), default=node.get("default"),
            is_object=False,
        )

    items: list = []
    current_section = None
    for key, prop in schema.get("properties", {}).items():
        for item in walk(prop, [key], prop.get("x-section")):
            if item.section != current_section:
                current_section = item.section
                items.append(_Section(item.section))
            items.append(item)
    return items


# ── backup helpers ─────────────────────────────────────────────────────────

def _load_backups() -> list:
    entries = []
    for p in _cfg.list_config_backups():
        try:
            data = p.read_bytes()
            stem = p.stem
            ts = stem.split(".", 1)[1] if "." in stem else ""
            try:
                dt = datetime.datetime.strptime(ts, "%Y%m%d%H%M%S")
            except ValueError:
                dt = None
            crc = f"{binascii.crc32(data) & 0xFFFFFFFF:08x}"
            entries.append(_BackupEntry(path=p, dt=dt, size=len(data), crc32=crc))
        except Exception:
            continue
    return entries


# ── value helpers ──────────────────────────────────────────────────────────

def _get(values: dict, path: list, default=None) -> Any:
    node = values
    for key in path:
        if isinstance(node, dict) and key in node:
            node = node[key]
        else:
            return default
    return node


def _set(values: dict, path: list, value: Any) -> None:
    node = values
    for key in path[:-1]:
        node = node.setdefault(key, {})
    node[path[-1]] = value


def _display(value: Any, ftype: str, is_object: bool) -> str:
    if is_object:
        if isinstance(value, dict):
            return "  ".join(f"{k}={v}" for k, v in sorted(value.items()))
        return str(value) if value is not None else ""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _parse(s: str, ftype: str, is_object: bool):
    s = s.strip()
    if is_object:
        result = {}
        for token in s.split():
            if "=" in token:
                k, v = token.split("=", 1)
                result[k.strip()] = v.strip()
        return result
    if ftype == "boolean":
        return s.lower() in ("true", "1", "yes", "on")
    if ftype == "integer":
        try:
            return int(s)
        except ValueError:
            return None
    if ftype == "number":
        try:
            return float(s)
        except ValueError:
            return None
    return s


# ── color pair IDs ─────────────────────────────────────────────────────────

_C_SECTION     = 1
_C_SEL         = 2
_C_VAL         = 3
_C_ERR         = 4
_C_EDIT        = 5
_C_DIALOG_BG   = 6   # dialog interior: white-on-blue
_C_DIALOG_TTL  = 7   # dialog title: yellow-on-blue
_C_DIALOG_HINT = 8   # dialog hint bar: cyan-on-blue
_C_BACKUP_SEL  = 9   # selected row in backup list


# ── TUI ───────────────────────────────────────────────────────────────────

_HELP = "s:save  b:backups  r:factory-reset  q:quit  ↑↓/jk:move  sp/enter:edit  esc:cancel"


class _TUI:
    def __init__(self, screen):
        self._scr = screen
        self._schema = _load_schema()
        self._items = _flatten(self._schema)
        self._fields = [i for i, it in enumerate(self._items) if isinstance(it, _Field)]
        self._cursor = 0
        self._scroll = 0
        self._values = self._load_file()
        self._saved  = json.dumps(self._values, sort_keys=True)
        self._edit   = False
        self._buf    = ""
        self._msg    = ""

        curses.curs_set(0)
        try:
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(_C_SECTION,     curses.COLOR_CYAN,   -1)
            curses.init_pair(_C_SEL,         curses.COLOR_GREEN,  -1)
            curses.init_pair(_C_VAL,         curses.COLOR_YELLOW, -1)
            curses.init_pair(_C_ERR,         curses.COLOR_RED,    -1)
            curses.init_pair(_C_EDIT,        curses.COLOR_WHITE,  curses.COLOR_BLUE)
            curses.init_pair(_C_DIALOG_BG,   curses.COLOR_WHITE,  curses.COLOR_BLUE)
            curses.init_pair(_C_DIALOG_TTL,  curses.COLOR_YELLOW, curses.COLOR_BLUE)
            curses.init_pair(_C_DIALOG_HINT, curses.COLOR_CYAN,   curses.COLOR_BLUE)
            curses.init_pair(_C_BACKUP_SEL,  curses.COLOR_BLACK,  curses.COLOR_CYAN)
        except curses.error:
            pass

    def _load_file(self) -> dict:
        path = _cfg.get_global_config_path()
        try:
            return _cfg.read_json(path)
        except _cfg.ConfigError:
            return {}

    def _dirty(self) -> bool:
        return json.dumps(self._values, sort_keys=True) != self._saved

    def _h(self) -> int:
        return self._scr.getmaxyx()[0]

    def _w(self) -> int:
        return self._scr.getmaxyx()[1]

    def _content_rows(self) -> int:
        return self._h() - 4

    def _sel_idx(self) -> int:
        return self._fields[self._cursor]

    def _ensure_visible(self):
        item_idx = self._sel_idx()
        rows = self._content_rows()
        if item_idx < self._scroll:
            self._scroll = item_idx
            return
        display_row = sum(1 for i in range(self._scroll, item_idx))
        if display_row >= rows:
            self._scroll = max(0, item_idx - rows + 1)

    def _draw(self):
        scr, h, w = self._scr, self._h(), self._w()
        scr.erase()

        mark = " *" if self._dirty() else ""
        try:
            scr.addstr(0, 0, f" architekton config{mark}".ljust(w - 1), curses.A_BOLD)
            scr.addstr(1, 0, "─" * (w - 1))
        except curses.error:
            pass

        label_w = max(w // 2, 28)
        row = 2
        max_row = h - 2

        for i, item in enumerate(self._items):
            if i < self._scroll:
                continue
            if row >= max_row:
                break

            if isinstance(item, _Section):
                bar = f"  ── {item.name} " + "─" * max(0, w - len(item.name) - 7)
                try:
                    scr.addstr(row, 0, bar[:w - 1], curses.color_pair(_C_SECTION))
                except curses.error:
                    pass
            else:
                is_sel = (i == self._sel_idx())
                raw = _get(self._values, item.path, item.default)
                disp = self._buf if (is_sel and self._edit) else _display(raw, item.ftype, item.is_object)
                marker = ">" if is_sel else " "
                lattr = curses.color_pair(_C_SEL) | curses.A_BOLD if is_sel else 0
                vattr = curses.color_pair(_C_SEL) if is_sel else curses.color_pair(_C_VAL)
                try:
                    scr.addstr(row, 0, f"  {marker} {item.label}"[:label_w].ljust(label_w), lattr)
                    scr.addstr(row, label_w, disp[:w - label_w - 1], vattr)
                except curses.error:
                    pass
            row += 1

        try:
            if self._edit:
                item = self._items[self._sel_idx()]
                hint = f"  Editing {item.ftype}: {self._buf}_  (enter=confirm  esc=cancel)"
                scr.addstr(h - 2, 0, hint[:w - 1], curses.color_pair(_C_EDIT))
            elif self._msg:
                attr = curses.color_pair(_C_ERR) if self._msg.startswith("Error") else 0
                scr.addstr(h - 2, 0, self._msg[:w - 1], attr)
            else:
                scr.addstr(h - 2, 0, "─" * (w - 1))
            scr.addstr(h - 1, 0, _HELP[:w - 1])
        except curses.error:
            pass

        scr.refresh()

    # ── floating dialog ────────────────────────────────────────────────────

    def _dialog(self, title: str, body: list, hint: str) -> int:
        """Draw a floating modal box over the current screen. Returns the key pressed.

        body is a list of strings (blank strings become blank lines).
        hint is the keys/instruction line shown at the bottom of the box.
        """
        h, w = self._h(), self._w()

        inner_w = max(
            len(title) + 4,
            max((len(line) for line in body), default=0) + 2,
            len(hint) + 4,
            30,
        )
        # 2 border cols + 2 padding cols each side = 4 overhead; cap at screen width
        box_w = min(inner_w + 4, w - 4)
        # top/bottom border + blank row after title border + body + separator + hint + bottom border
        box_h = len(body) + 5

        top  = max(1, (h - box_h) // 2)
        left = max(2, (w - box_w) // 2)

        # Drop shadow: one column right + one row down from box edges
        shadow_attr = curses.A_DIM
        for dy in range(1, box_h + 1):
            sy = top + dy
            sx = left + box_w
            if 0 <= sy < h and 0 <= sx < w - 1:
                try:
                    self._scr.addch(sy, sx, ' ', shadow_attr)
                except curses.error:
                    pass
        for dx in range(2, box_w + 2):
            sy = top + box_h
            sx = left + dx
            if 0 <= sy < h and 0 <= sx < w - 1:
                try:
                    self._scr.addch(sy, sx, ' ', shadow_attr)
                except curses.error:
                    pass
        self._scr.refresh()

        # Floating window
        try:
            win = curses.newwin(box_h, box_w, top, left)
        except curses.error:
            # Terminal too small -- fall back to status bar
            self._msg = body[0] if body else hint
            self._draw()
            return self._scr.getch()

        bg = curses.color_pair(_C_DIALOG_BG)
        win.bkgd(' ', bg)
        win.erase()
        for _y in range(box_h):
            try:
                win.addstr(_y, 0, ' ' * box_w, bg)
            except curses.error:
                pass
        win.box()

        # Title centered in top border line
        title_disp = f" {title} "
        if len(title_disp) > box_w - 2:
            title_disp = title_disp[:box_w - 3] + " "
        tx = max(1, (box_w - len(title_disp)) // 2)
        try:
            win.addstr(0, tx, title_disp,
                       curses.color_pair(_C_DIALOG_TTL) | curses.A_BOLD)
        except curses.error:
            pass

        # Body lines (left-padded, not centered, so they read naturally)
        for i, line in enumerate(body):
            y = i + 2
            if y >= box_h - 3:
                break
            try:
                win.addstr(y, 3, line[:box_w - 6], bg)
            except curses.error:
                pass

        # Separator above hint
        sep_y = box_h - 3
        try:
            win.addch(sep_y, 0,         curses.ACS_LTEE)
            win.hline(sep_y, 1,         curses.ACS_HLINE, box_w - 2)
            win.addch(sep_y, box_w - 1, curses.ACS_RTEE)
        except curses.error:
            pass

        # Hint centered above bottom border
        hint_disp = hint[:box_w - 4]
        hx = max(2, (box_w - len(hint_disp)) // 2)
        try:
            win.addstr(box_h - 2, hx, hint_disp,
                       curses.color_pair(_C_DIALOG_HINT) | curses.A_BOLD)
        except curses.error:
            pass

        win.refresh()
        ch = win.getch()
        del win

        # Repaint main screen (curses doesn't restore what was behind a window)
        self._draw()
        return ch

    # ── edit ───────────────────────────────────────────────────────────────

    def _field(self) -> _Field:
        return self._items[self._sel_idx()]

    def _activate(self):
        item = self._field()
        raw = _get(self._values, item.path, item.default)

        if item.ftype == "boolean":
            _set(self._values, item.path, not bool(raw))
            return

        if item.enum:
            vals = item.enum
            try:
                idx = vals.index(raw)
            except ValueError:
                idx = -1
            _set(self._values, item.path, vals[(idx + 1) % len(vals)])
            return

        self._edit = True
        self._buf = _display(raw, item.ftype, item.is_object)
        self._msg = ""

    def _commit(self):
        item = self._field()
        val = _parse(self._buf, item.ftype, item.is_object)
        if val is None and item.ftype in ("integer", "number"):
            self._msg = f"Error: '{self._buf}' is not a valid {item.ftype}"
            return
        _set(self._values, item.path, val)
        self._edit = False
        self._buf = ""
        self._msg = ""

    # ── save / quit / restore ──────────────────────────────────────────────

    def _do_save(self) -> bool:
        try:
            _cfg.save_global_config(self._values)
            self._saved = json.dumps(self._values, sort_keys=True)
            self._msg = "Saved."
            return True
        except _cfg.ConfigError as e:
            self._msg = f"Error: {e}"
            return False

    def _save(self) -> bool:
        ch = self._dialog(
            "Save config",
            ["Write current values to ~/.claude/architekton/config.json?", ""],
            "y = save    any other key = cancel",
        )
        if ch not in (ord("y"), ord("Y")):
            self._msg = "Save cancelled."
            return False
        return self._do_save()

    def _prompt_quit(self) -> bool:
        if self._dirty():
            ch = self._dialog(
                "Unsaved changes",
                ["You have unsaved changes.", ""],
                "s = save & quit    d = discard & quit    esc = cancel",
            )
            if ch in (ord("s"), ord("S")):
                self._do_save()
                return True
            if ch in (ord("d"), ord("D")):
                return True
            return False
        ch = self._dialog(
            "Quit",
            ["No unsaved changes.", ""],
            "q/enter = quit    esc = cancel",
        )
        return ch in (ord("q"), ord("Q"), 10, 13)

    def _prompt_restore(self):
        ch = self._dialog(
            "Factory reset",
            [
                "Replace the current config with the factory defaults.",
                "All unsaved changes will be lost.",
                "",
                "This creates a backup before overwriting.",
            ],
            "y = reset to factory defaults    any other key = cancel",
        )
        if ch not in (ord("y"), ord("Y")):
            return
        try:
            _cfg.restore_config(backup_path=None)
            self._values = self._load_file()
            self._saved = json.dumps(self._values, sort_keys=True)
            self._msg = "Factory defaults restored."
        except _cfg.ConfigError as e:
            self._msg = f"Error: {e}"

    # ── backup picker ──────────────────────────────────────────────────────

    def _show_backups(self):
        entries = _load_backups()
        if not entries:
            self._dialog(
                "Backups",
                ["No backups found.", "", "Backups are created automatically on each save."],
                "any key to close",
            )
            return

        h, w = self._h(), self._w()
        box_h = min(len(entries) + 7, h - 4)
        box_w = min(74, w - 4)
        top   = max(1, (h - box_h) // 2)
        left  = max(2, (w - box_w) // 2)

        cursor = 0
        scroll = 0
        list_rows = box_h - 6   # rows available for the list

        while True:
            h, w = self._h(), self._w()

            # Drop shadow
            shadow_attr = curses.A_DIM
            for dy in range(1, box_h + 1):
                if 0 <= top + dy < h and left + box_w < w - 1:
                    try:
                        self._scr.addch(top + dy, left + box_w, ' ', shadow_attr)
                    except curses.error:
                        pass
            for dx in range(2, box_w + 2):
                if top + box_h < h and 0 <= left + dx < w - 1:
                    try:
                        self._scr.addch(top + box_h, left + dx, ' ', shadow_attr)
                    except curses.error:
                        pass
            self._scr.refresh()

            try:
                win = curses.newwin(box_h, box_w, top, left)
            except curses.error:
                break

            bg  = curses.color_pair(_C_DIALOG_BG)
            win.bkgd(' ', bg)
            win.erase()
            for _y in range(box_h):
                try:
                    win.addstr(_y, 0, ' ' * box_w, bg)
                except curses.error:
                    pass
            win.box()

            title_disp = f" Backups ({len(entries)}) "
            tx = max(1, (box_w - len(title_disp)) // 2)
            try:
                win.addstr(0, tx, title_disp,
                           curses.color_pair(_C_DIALOG_TTL) | curses.A_BOLD)
            except curses.error:
                pass

            # Column header
            hdr = f"  {'Date / time':<20}  {'Size':>8}   CRC32"
            try:
                win.addstr(1, 1, hdr[:box_w - 2], curses.color_pair(_C_DIALOG_HINT))
            except curses.error:
                pass

            # Adjust scroll
            if cursor < scroll:
                scroll = cursor
            elif cursor >= scroll + list_rows:
                scroll = cursor - list_rows + 1

            for i, e in enumerate(entries):
                row = i - scroll + 2
                if row < 2 or row >= box_h - 4:
                    continue
                dt_str = e.dt.strftime("%Y-%m-%d  %H:%M:%S") if e.dt else "unknown"
                size_str = (f"{e.size / 1024:.1f} KB" if e.size >= 1024
                            else f"{e.size} B")
                line = f"  {'>' if i == cursor else ' '}  {dt_str:<20}  {size_str:>8}   {e.crc32}"
                attr = (curses.color_pair(_C_BACKUP_SEL) | curses.A_BOLD
                        if i == cursor else bg)
                try:
                    win.addstr(row, 1, line[:box_w - 2], attr)
                except curses.error:
                    pass

            # Separator
            sep_y = box_h - 3
            try:
                win.addch(sep_y, 0,         curses.ACS_LTEE)
                win.hline(sep_y, 1, curses.ACS_HLINE, box_w - 2)
                win.addch(sep_y, box_w - 1, curses.ACS_RTEE)
            except curses.error:
                pass

            hint = "enter:restore  ↑↓/jk:move  esc/q:cancel"
            hx = max(2, (box_w - len(hint)) // 2)
            try:
                win.addstr(box_h - 2, hx, hint[:box_w - 4],
                           curses.color_pair(_C_DIALOG_HINT) | curses.A_BOLD)
            except curses.error:
                pass

            win.refresh()
            ch = win.getch()
            del win

            if ch in (curses.KEY_UP, ord("k")):
                cursor = max(0, cursor - 1)
            elif ch in (curses.KEY_DOWN, ord("j")):
                cursor = min(len(entries) - 1, cursor + 1)
            elif ch in (curses.KEY_ENTER, 10, 13):
                e = entries[cursor]
                label = (e.dt.strftime("%Y-%m-%d %H:%M:%S")
                         if e.dt else str(e.path.name))
                conf = self._dialog(
                    "Restore backup",
                    [
                        f"Restore config from:",
                        f"  {label}",
                        "",
                        "The current config will be backed up first.",
                        "All unsaved TUI changes will be replaced.",
                    ],
                    "y = restore    any other key = cancel",
                )
                if conf in (ord("y"), ord("Y")):
                    try:
                        _cfg.restore_config(backup_path=e.path)
                        self._values = self._load_file()
                        self._saved = json.dumps(self._values, sort_keys=True)
                        self._msg = f"Restored from {label}."
                    except _cfg.ConfigError as ex:
                        self._msg = f"Error: {ex}"
                self._draw()
                return
            elif ch in (27, ord("q")):
                self._draw()
                return
            elif ch == curses.KEY_RESIZE:
                h, w = self._h(), self._w()
                box_h = min(len(entries) + 7, h - 4)
                box_w = min(74, w - 4)
                top   = max(1, (h - box_h) // 2)
                left  = max(2, (w - box_w) // 2)
                list_rows = box_h - 6

            # Redraw main screen behind the picker on each iteration
            self._draw()

    # ── main loop ──────────────────────────────────────────────────────────

    def run(self) -> int:
        while True:
            self._ensure_visible()
            self._draw()
            try:
                ch = self._scr.getch()
            except KeyboardInterrupt:
                break

            self._msg = ""

            if self._edit:
                if ch in (curses.KEY_ENTER, 10, 13):
                    self._commit()
                elif ch == 27:
                    self._edit = False
                    self._buf = ""
                elif ch in (curses.KEY_BACKSPACE, 127, 8):
                    self._buf = self._buf[:-1]
                elif 32 <= ch < 127:
                    self._buf += chr(ch)
                continue

            if ch in (curses.KEY_UP, ord("k")):
                self._cursor = max(0, self._cursor - 1)
            elif ch in (curses.KEY_DOWN, ord("j")):
                self._cursor = min(len(self._fields) - 1, self._cursor + 1)
            elif ch in (ord(" "), curses.KEY_ENTER, 10, 13):
                self._activate()
            elif ch == ord("s"):
                self._save()
            elif ch == ord("b"):
                self._show_backups()
            elif ch == ord("r"):
                self._prompt_restore()
            elif ch == ord("q"):
                if self._prompt_quit():
                    break
            elif ch == curses.KEY_RESIZE:
                self._scr.clear()

        self._scr.clear()
        self._scr.refresh()
        return 0


def run() -> int:
    try:
        return curses.wrapper(lambda scr: _TUI(scr).run())
    except curses.error as e:
        print(f"architekton tui: terminal error: {e}", file=sys.stderr)
        return 1
