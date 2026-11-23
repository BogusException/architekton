"""Curses-based config editor driven by config/schema.json.

Keyboard (main screen):
  arrows / j / k    move between fields
  space / enter     toggle bool, cycle enum, begin text edit
  s                 save (confirms before writing)
  b                 browse and restore from a saved backup
  r                 restore factory defaults (confirms)
  q                 quit (s=save+quit, d=discard+quit, esc=cancel if dirty)
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
    ftype: str          # boolean | string | number | integer
    enum: Any           # list of allowed values, or None
    minimum: Any
    maximum: Any
    default: Any
    is_object: bool     # True for dict-valued fields (thinking_map)


@dataclass
class _BackupEntry:
    path: Path
    dt: Any             # datetime.datetime or None
    size: int
    crc32: str


# ── schema flattening ──────────────────────────────────────────────────────

def _flatten(schema: dict) -> list:
    """Return ordered list of _Section / _Field items from the schema."""
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
    """Return list of _BackupEntry, newest first."""
    entries = []
    for p in _cfg.list_config_backups():
        try:
            data = p.read_bytes()
            stem = p.stem  # config.20261123013218
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
    """Parse a string into a typed value. Returns None on parse failure."""
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


# ── TUI ───────────────────────────────────────────────────────────────────

_HELP = "s:save  b:backups  r:factory-reset  q:quit  ↑↓/jk:move  sp/enter:edit  esc:cancel"

_C_SECTION = 1
_C_SEL     = 2
_C_VAL     = 3
_C_ERR     = 4
_C_EDIT    = 5
_C_BACKUP  = 6   # selected row in backup picker


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
            curses.init_pair(_C_SECTION, curses.COLOR_CYAN,   -1)
            curses.init_pair(_C_SEL,     curses.COLOR_GREEN,  -1)
            curses.init_pair(_C_VAL,     curses.COLOR_YELLOW, -1)
            curses.init_pair(_C_ERR,     curses.COLOR_RED,    -1)
            curses.init_pair(_C_EDIT,    curses.COLOR_WHITE,  curses.COLOR_BLUE)
            curses.init_pair(_C_BACKUP,  curses.COLOR_BLACK,  curses.COLOR_CYAN)
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

    def _field(self) -> _Field:
        return self._items[self._sel_idx()]

    # ── confirmation gate ──────────────────────────────────────────────────

    def _confirm(self, msg: str) -> bool:
        """Show msg at the status bar and return True only if user presses y/Y."""
        self._msg = msg
        self._draw()
        ch = self._scr.getch()
        self._msg = ""
        return ch in (ord("y"), ord("Y"))

    # ── edit ───────────────────────────────────────────────────────────────

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
        """Write config without prompting. Called after confirmation."""
        try:
            _cfg.save_global_config(self._values)
            self._saved = json.dumps(self._values, sort_keys=True)
            self._msg = "Saved."
            return True
        except _cfg.ConfigError as e:
            self._msg = f"Error: {e}"
            return False

    def _save(self) -> bool:
        if not self._confirm("Save changes? (y/N)"):
            self._msg = "Save cancelled."
            return False
        return self._do_save()

    def _prompt_quit(self) -> bool:
        """Return True if the caller should exit."""
        if not self._dirty():
            return True
        self._msg = "Unsaved changes: (s)ave and quit  (d)iscard and quit  (esc) cancel"
        self._draw()
        ch = self._scr.getch()
        self._msg = ""
        if ch in (ord("s"), ord("S")):
            self._do_save()
            return True
        if ch in (ord("d"), ord("D")):
            return True
        return False

    def _prompt_restore(self):
        if not self._confirm("Reset to factory defaults? All unsaved changes will be lost. (y/N)"):
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
            self._msg = "No backups found."
            return

        cursor = 0
        scroll = 0

        while True:
            scr, h, w = self._scr, self._h(), self._w()
            scr.erase()

            try:
                scr.addstr(0, 0, f" architekton config -- backups ({len(entries)})".ljust(w - 1), curses.A_BOLD)
                scr.addstr(1, 0, "─" * (w - 1))
            except curses.error:
                pass

            visible = h - 4
            if cursor < scroll:
                scroll = cursor
            elif cursor >= scroll + visible:
                scroll = cursor - visible + 1

            for i, e in enumerate(entries):
                row = i - scroll + 2
                if row < 2 or row >= h - 2:
                    continue
                dt_str = e.dt.strftime("%Y-%m-%d  %H:%M:%S") if e.dt else "unknown date"
                size_str = f"{e.size / 1024:.1f} KB" if e.size >= 1024 else f"{e.size} B"
                line = f"  {'>' if i == cursor else ' '}  {dt_str}   {size_str:>8}   CRC: {e.crc32}"
                attr = curses.color_pair(_C_BACKUP) | curses.A_BOLD if i == cursor else 0
                try:
                    scr.addstr(row, 0, line[:w - 1], attr)
                except curses.error:
                    pass

            try:
                scr.addstr(h - 2, 0, "─" * (w - 1))
                scr.addstr(h - 1, 0, "enter:restore  ↑↓/jk:move  esc/q:cancel"[:w - 1])
            except curses.error:
                pass

            scr.refresh()
            ch = scr.getch()

            if ch in (curses.KEY_UP, ord("k")):
                cursor = max(0, cursor - 1)
            elif ch in (curses.KEY_DOWN, ord("j")):
                cursor = min(len(entries) - 1, cursor + 1)
            elif ch in (curses.KEY_ENTER, 10, 13):
                e = entries[cursor]
                label = e.dt.strftime("%Y-%m-%d %H:%M:%S") if e.dt else str(e.path.name)
                msg = f"Restore from {label}? All current config will be replaced. (y/N)"
                scr.addstr(h - 2, 0, msg[:w - 1], curses.color_pair(_C_ERR))
                scr.refresh()
                conf = scr.getch()
                if conf in (ord("y"), ord("Y")):
                    try:
                        _cfg.restore_config(backup_path=e.path)
                        self._values = self._load_file()
                        self._saved = json.dumps(self._values, sort_keys=True)
                        self._msg = f"Restored from {label}."
                    except _cfg.ConfigError as ex:
                        self._msg = f"Error: {ex}"
                return
            elif ch in (27, ord("q")):
                return
            elif ch == curses.KEY_RESIZE:
                scr.clear()

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

        return 0


def run() -> int:
    """Launch the TUI. Returns an exit code."""
    try:
        return curses.wrapper(lambda scr: _TUI(scr).run())
    except curses.error as e:
        print(f"architekton tui: terminal error: {e}", file=sys.stderr)
        return 1
