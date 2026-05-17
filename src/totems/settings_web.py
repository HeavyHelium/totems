from __future__ import annotations

import json
import errno
import threading
import signal
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from .config import BLOCK_PALETTE_KEYS, Config, ConfigError, parse_block_palette_values
from .content import ContentError
from .settings_window import (
    SettingsState,
    duty_source_kinds_for_google_urls,
    editor_text_to_items,
    google_urls_text_to_tuple,
    items_to_editor_text,
    load_settings_state,
    save_settings_state,
)


DEFAULT_SETTINGS_WEB_PORT = 8421
SETTINGS_WEB_PORT_ATTEMPTS = 20


def run_settings_web(
    config_dir: Path,
    *,
    host: str = "127.0.0.1",
    port: int = DEFAULT_SETTINGS_WEB_PORT,
    open_browser: bool = True,
) -> None:
    server = make_settings_server(config_dir, host=host, port=port)
    previous_signal_handlers = _install_shutdown_signal_handlers()
    url = f"http://{server.server_address[0]}:{server.server_address[1]}/"
    print(f"totems settings: {url}")
    if open_browser:
        threading.Timer(0.2, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\ntotems settings: stopped")
    finally:
        _restore_signal_handlers(previous_signal_handlers)
        server.server_close()


def make_settings_server(config_dir: Path, *, host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    class SettingsRequestHandler(_SettingsRequestHandler):
        pass

    SettingsRequestHandler.config_dir = config_dir
    ports = [port] if port == 0 else range(port, port + SETTINGS_WEB_PORT_ATTEMPTS)
    last_error: OSError | None = None
    for candidate in ports:
        try:
            return ThreadingHTTPServer((host, candidate), SettingsRequestHandler)
        except OSError as e:
            if e.errno != errno.EADDRINUSE or port == 0:
                raise
            last_error = e
    raise OSError(
        errno.EADDRINUSE,
        f"no free localhost settings port in {port}-{port + SETTINGS_WEB_PORT_ATTEMPTS - 1}",
    ) from last_error


def _install_shutdown_signal_handlers() -> dict[signal.Signals, signal.Handlers]:
    signals = [signal.SIGINT, signal.SIGTERM, signal.SIGHUP]
    if hasattr(signal, "SIGTSTP"):
        signals.append(signal.SIGTSTP)
    previous = {}
    for sig in signals:
        previous[sig] = signal.getsignal(sig)
        signal.signal(sig, _raise_keyboard_interrupt)
    return previous


def _restore_signal_handlers(previous: dict[signal.Signals, signal.Handlers]) -> None:
    for sig, handler in previous.items():
        signal.signal(sig, handler)


def _raise_keyboard_interrupt(_signum: int, _frame: object) -> None:
    raise KeyboardInterrupt


def state_to_payload(state: SettingsState) -> dict[str, Any]:
    cfg = state.config
    return {
        "ritual_phrase": cfg.ritual_phrase,
        "work_minutes": cfg.work_minutes,
        "block_minutes": cfg.block_minutes,
        "timebox_duties": cfg.timebox_duties,
        "timebox_phrase": cfg.timebox_phrase,
        "timebox_lead_minutes": cfg.timebox_lead_minutes,
        "timebox_reminder_seconds": cfg.timebox_reminder_seconds,
        "content_mode": cfg.content_mode,
        "google_calendar_urls": "\n".join(cfg.google_calendar_urls),
        "colors": cfg.block_palette.as_dict(),
        "quotes": state.quotes,
        "wisdom": state.wisdom,
        "duties": state.duties,
        "quotes_text": items_to_editor_text(state.quotes),
        "wisdom_text": items_to_editor_text(state.wisdom),
        "duties_text": items_to_editor_text(state.duties),
    }


def payload_to_state(payload: dict[str, Any], current: SettingsState) -> SettingsState:
    colors_raw = payload.get("colors", {})
    if not isinstance(colors_raw, dict):
        raise ConfigError("colors must be an object")

    google_urls = google_urls_text_to_tuple(_string_field(payload, "google_calendar_urls"))
    kinds = duty_source_kinds_for_google_urls(current.config.duty_source_kinds, google_urls)
    return SettingsState(
        config=Config(
            ritual_phrase=_string_field(payload, "ritual_phrase").strip(),
            work_minutes=_positive_int_field(payload, "work_minutes", "Work minutes"),
            block_minutes=_positive_int_field(payload, "block_minutes", "Block minutes"),
            duty_source_kinds=kinds,
            google_calendar_urls=google_urls,
            timebox_duties=_bool_field(payload, "timebox_duties"),
            timebox_phrase=_string_field(payload, "timebox_phrase").strip(),
            timebox_lead_minutes=_positive_int_field(
                payload,
                "timebox_lead_minutes",
                "Timebox lead minutes",
            ),
            timebox_reminder_seconds=_positive_int_field(
                payload,
                "timebox_reminder_seconds",
                "Reminder seconds",
            ),
            content_mode=_string_field(payload, "content_mode"),
            block_palette=parse_block_palette_values(colors_raw),
        ),
        quotes=_items_field(payload, "quotes", "quotes_text"),
        wisdom=_items_field(payload, "wisdom", "wisdom_text"),
        duties=_items_field(payload, "duties", "duties_text"),
    )


def _string_field(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key, "")
    if not isinstance(value, str):
        raise ConfigError(f"{key} must be a string")
    return value


def _bool_field(payload: dict[str, Any], key: str) -> bool:
    value = payload.get(key, False)
    if type(value) is not bool:
        raise ConfigError(f"{key} must be true or false")
    return value


def _items_field(payload: dict[str, Any], key: str, legacy_text_key: str) -> list[str]:
    if key not in payload:
        return editor_text_to_items(_string_field(payload, legacy_text_key))
    value = payload[key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{key} must be a list of strings")
    return [item.strip() for item in value if item.strip()]


def _positive_int_field(payload: dict[str, Any], key: str, label: str) -> int:
    value = payload.get(key, "")
    if isinstance(value, str):
        try:
            out = int(value)
        except ValueError as e:
            raise ConfigError(f"{label} must be a positive integer") from e
    elif type(value) is int:
        out = value
    else:
        raise ConfigError(f"{label} must be a positive integer")
    if out <= 0:
        raise ConfigError(f"{label} must be a positive integer")
    return out


class _SettingsRequestHandler(BaseHTTPRequestHandler):
    config_dir: Path

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._send_html(SETTINGS_HTML)
            return
        if path == "/api/settings":
            self._send_json({"ok": True, "settings": state_to_payload(load_settings_state(self.config_dir))})
            return
        self.send_error(404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/api/settings":
            self.send_error(404)
            return

        try:
            payload = self._read_json_body()
            current = load_settings_state(self.config_dir)
            next_state = payload_to_state(payload, current)
            save_settings_state(self.config_dir, next_state)
        except (ConfigError, ContentError, ValueError, json.JSONDecodeError) as e:
            self._send_json({"ok": False, "error": str(e)}, status=400)
            return

        self._send_json({"ok": True, "settings": state_to_payload(next_state)})

    def log_message(self, format: str, *args: object) -> None:
        return

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        data = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(data, dict):
            raise ConfigError("request body must be a JSON object")
        return data

    def _send_json(self, payload: dict[str, Any], *, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


COLOR_INPUTS_HTML = "\n".join(
    f'''
          <label class="color-field">
            <span>{key.replace("_", " ")}</span>
            <input type="color" name="color:{key}" data-color-key="{key}">
            <input class="hex" name="hex:{key}" data-hex-key="{key}" maxlength="7">
          </label>'''
    for key in BLOCK_PALETTE_KEYS
)


FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<rect width="64" height="64" rx="12" fill="#f3eadb"/>'
    '<circle cx="32" cy="32" r="22" fill="#fff8ea" stroke="#2f6f5e" stroke-width="4"/>'
    '<path d="M18 34c8-16 20-16 28 0-8 8-20 8-28 0z" fill="#6ca695"/>'
    '<circle cx="32" cy="31" r="6" fill="#ffe66d" stroke="#1f241f" stroke-width="3"/>'
    '<path d="M32 13v9M32 42v9M13 32h9M42 32h9" stroke="#d66b3d" stroke-width="4" stroke-linecap="round"/>'
    "</svg>"
)
FAVICON_HREF = "data:image/svg+xml," + quote(FAVICON_SVG, safe="")


SETTINGS_HTML = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>totems settings</title>
  <link rel="icon" href="{FAVICON_HREF}" type="image/svg+xml">
  <style>
    :root {{
      color-scheme: light;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f3eadb;
      color: #1f241f;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f3eadb; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 22px; }}
    header {{ display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 16px; }}
    h1 {{ margin: 0; color: #2f6f5e; font-size: 24px; }}
    h2 {{ margin: 0 0 12px; color: #2f6f5e; font-size: 14px; text-transform: uppercase; }}
    section {{ background: #fff8ea; border: 1px solid #e0d2bf; padding: 16px; margin-bottom: 14px; }}
    .tabs {{ display: flex; gap: 8px; margin: 0 0 14px; border-bottom: 1px solid #d8c8b3; }}
    .tab {{ background: transparent; color: #756f65; border: 1px solid transparent; border-bottom: 0; padding: 10px 16px; }}
    .tab.active {{ background: #fff8ea; color: #2f6f5e; border-color: #d8c8b3; }}
    .tab-panel[hidden] {{ display: none; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }}
    label {{ display: grid; gap: 6px; font-size: 14px; color: #756f65; font-weight: 650; }}
    input, textarea, select {{ width: 100%; border: 1px solid #d8c8b3; background: #fffdf6; color: #1f241f; padding: 9px; font: inherit; }}
    input[type="checkbox"] {{ width: auto; }}
    textarea {{ min-height: 160px; resize: vertical; line-height: 1.4; }}
    .wide {{ grid-column: 1 / -1; }}
    .check {{ display: flex; align-items: center; gap: 8px; padding-top: 22px; }}
    .colors {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }}
    .color-field {{ grid-template-columns: 1fr auto 86px; align-items: center; gap: 8px; background: #f7efe3; border: 1px solid #e0d2bf; padding: 10px; }}
    input[type="color"] {{ width: 42px; height: 34px; padding: 2px; }}
    .preview {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 14px; }}
    .preview-card {{ border: 1px solid var(--border); padding: 14px; min-height: 72px; }}
    .preview-symbol {{ background: var(--totem-panel); color: #fff8ea; }}
    .preview-quote {{ background: var(--quote); }}
    .preview-wisdom {{ background: var(--wisdom); }}
    .preview-today {{ background: var(--today); }}
    .preview-ritual {{ background: var(--ritual); }}
    .marker {{ display: inline-block; width: 22px; height: 16px; margin-right: 8px; vertical-align: -2px; border: 1px solid var(--border); }}
    .preview-wisdom .marker {{ background: var(--wisdom-bullet); }}
    .preview-today .marker {{ background: var(--today-bullet); }}
    .highlight {{ background: var(--highlight); padding: 2px 4px; }}
    .subtabs {{ display: flex; gap: 6px; margin: 0 0 12px; border-bottom: 1px solid #d8c8b3; }}
    .subtab {{ background: transparent; color: #756f65; border: 1px solid transparent; border-bottom: 0; padding: 8px 14px; }}
    .subtab.active {{ color: #1f241f; border-color: #d8c8b3; }}
    .subtab[data-content-tab="quotes"].active {{ background: var(--quote-tab, #fff4cf); }}
    .subtab[data-content-tab="wisdom"].active {{ background: var(--wisdom-tab, #e4f0df); }}
    .subtab[data-content-tab="duties"].active {{ background: var(--duties-tab, #f9dfca); }}
    .content-panel[hidden] {{ display: none; }}
    .record-card {{ border: 1px solid #e0d2bf; padding: 12px; min-width: 0; }}
    [data-content-panel="quotes"] .record-card {{ background: var(--quote-tab, #fff4cf); }}
    [data-content-panel="wisdom"] .record-card {{ background: var(--wisdom-tab, #e4f0df); }}
    [data-content-panel="duties"] .record-card {{ background: var(--duties-tab, #f9dfca); }}
    .record-card h3 {{ margin: 0 0 8px; color: #756f65; font-size: 14px; }}
    .record-layout {{ display: grid; grid-template-columns: minmax(220px, 0.8fr) minmax(360px, 1.4fr); gap: 12px; align-items: stretch; }}
    .record-list {{ min-height: 360px; }}
    .record-text {{ min-height: 360px; }}
    .record-actions {{ display: flex; gap: 6px; margin-top: 10px; }}
    .record-actions button {{ padding: 8px; background: #fffdf6; color: #1f241f; border: 1px solid #d8c8b3; font-weight: 650; }}
    .record-actions button:not(.icon-button) {{ flex: 1; }}
    .icon-button {{ width: 44px; min-width: 44px; font-size: 22px; line-height: 1; }}
    .content-note {{ color: #756f65; margin: 0 0 12px; }}
    .actions {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; position: sticky; bottom: 0; background: #f3eadb; padding: 12px 0 0; }}
    button {{ background: #2f6f5e; color: #fff8ea; border: 0; padding: 10px 20px; font: inherit; font-weight: 700; cursor: pointer; }}
    #status {{ color: #756f65; min-height: 1.2em; }}
    #status.error {{ color: #9b2f28; }}
    @media (max-width: 900px) {{
      .grid, .colors, .preview, .record-layout {{ grid-template-columns: 1fr; }}
      header, .actions, .tabs, .subtabs {{ align-items: stretch; flex-direction: column; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>totems settings</h1>
      <span id="status"></span>
    </header>

    <form id="settings-form">
      <nav class="tabs" aria-label="Settings sections">
        <button class="tab active" type="button" data-tab="timing">Timing</button>
        <button class="tab" type="button" data-tab="colors">Colors</button>
        <button class="tab" type="button" data-tab="calendar">Calendar</button>
        <button class="tab" type="button" data-tab="content">Content</button>
      </nav>

      <section class="tab-panel active" data-panel="timing">
        <h2>Timing</h2>
        <div class="grid">
          <label>Ritual phrase <input name="ritual_phrase" autocomplete="off"></label>
          <label>Content mode
            <select name="content_mode">
              <option value="merge">Merge with defaults</option>
              <option value="replace">Use only my pools</option>
            </select>
          </label>
          <label>Work minutes <input name="work_minutes" type="number" min="1" step="1"></label>
          <label>Block minutes <input name="block_minutes" type="number" min="1" step="1"></label>
          <label class="check"><input name="timebox_duties" type="checkbox"> Timebox duties</label>
          <label>Timebox phrase <input name="timebox_phrase" autocomplete="off"></label>
          <label>Lead minutes <input name="timebox_lead_minutes" type="number" min="1" step="1"></label>
          <label>Reminder seconds <input name="timebox_reminder_seconds" type="number" min="1" step="1"></label>
        </div>
      </section>

      <section class="tab-panel" data-panel="colors" hidden>
        <h2>Block Window Colors</h2>
        <div class="colors">{COLOR_INPUTS_HTML}
        </div>
        <div class="preview" id="preview">
          <div class="preview-card preview-symbol">totem check</div>
          <div class="preview-card preview-quote">Quote card</div>
          <div class="preview-card preview-wisdom"><span class="marker"></span>Wisdom item</div>
          <div class="preview-card preview-today"><span class="marker"></span><span class="highlight">09:00 standup</span></div>
          <div class="preview-card preview-ritual wide">Ritual card</div>
        </div>
      </section>

      <section class="tab-panel" data-panel="calendar" hidden>
        <h2>Google Calendar</h2>
        <label>Private iCal URLs, one per line
          <textarea name="google_calendar_urls" spellcheck="false"></textarea>
        </label>
      </section>

      <section class="tab-panel" data-panel="content" hidden>
        <h2>Content</h2>
        <p class="content-note">Select a record to edit it. Records can contain line breaks.</p>
        <nav class="subtabs" aria-label="Content pools">
          <button class="subtab active" type="button" data-content-tab="quotes">Quotes</button>
          <button class="subtab" type="button" data-content-tab="wisdom">Wisdom</button>
          <button class="subtab" type="button" data-content-tab="duties">Duties</button>
        </nav>
        <div class="content-panel active" data-content-panel="quotes">
          <div class="record-card" data-record-editor="quotes">
            <h3>Quotes</h3>
            <div class="record-layout">
              <select class="record-list" data-record-list size="14"></select>
              <textarea class="record-text" data-record-text></textarea>
            </div>
            <div class="record-actions">
              <button class="icon-button" type="button" data-action="add" aria-label="Add record" title="Add record">+</button>
              <button type="button" data-action="delete">Delete</button>
              <button type="button" data-action="clear">Clear editor</button>
            </div>
          </div>
        </div>
        <div class="content-panel" data-content-panel="wisdom" hidden>
          <div class="record-card" data-record-editor="wisdom">
            <h3>Wisdom</h3>
            <div class="record-layout">
              <select class="record-list" data-record-list size="14"></select>
              <textarea class="record-text" data-record-text></textarea>
            </div>
            <div class="record-actions">
              <button class="icon-button" type="button" data-action="add" aria-label="Add record" title="Add record">+</button>
              <button type="button" data-action="delete">Delete</button>
              <button type="button" data-action="clear">Clear editor</button>
            </div>
          </div>
        </div>
        <div class="content-panel" data-content-panel="duties" hidden>
          <div class="record-card" data-record-editor="duties">
            <h3>Duties</h3>
            <div class="record-layout">
              <select class="record-list" data-record-list size="14"></select>
              <textarea class="record-text" data-record-text></textarea>
            </div>
            <div class="record-actions">
              <button class="icon-button" type="button" data-action="add" aria-label="Add record" title="Add record">+</button>
              <button type="button" data-action="delete">Delete</button>
              <button type="button" data-action="clear">Clear editor</button>
            </div>
          </div>
        </div>
      </section>

      <div class="actions">
        <span>Saved changes apply to the next block window.</span>
        <button type="submit">Save</button>
      </div>
    </form>
  </main>

  <script>
    const form = document.querySelector("#settings-form");
    const status = document.querySelector("#status");
    const preview = document.querySelector("#preview");
    const tabButtons = [...document.querySelectorAll("[data-tab]")];
    const tabPanels = [...document.querySelectorAll("[data-panel]")];
    const contentTabButtons = [...document.querySelectorAll("[data-content-tab]")];
    const contentPanels = [...document.querySelectorAll("[data-content-panel]")];
    const colorInputs = [...document.querySelectorAll("[data-color-key]")];
    const hexInputs = [...document.querySelectorAll("[data-hex-key]")];
    const colorKeys = {json.dumps(BLOCK_PALETTE_KEYS)};
    let autosaveJob = null;
    let loading = true;
    const fields = {{
      ritual_phrase: form.querySelector('[name="ritual_phrase"]'),
      work_minutes: form.querySelector('[name="work_minutes"]'),
      block_minutes: form.querySelector('[name="block_minutes"]'),
      timebox_duties: form.querySelector('[name="timebox_duties"]'),
      timebox_phrase: form.querySelector('[name="timebox_phrase"]'),
      timebox_lead_minutes: form.querySelector('[name="timebox_lead_minutes"]'),
      timebox_reminder_seconds: form.querySelector('[name="timebox_reminder_seconds"]'),
      content_mode: form.querySelector('[name="content_mode"]'),
      google_calendar_urls: form.querySelector('[name="google_calendar_urls"]'),
    }};
    const recordEditors = {{
      quotes: makeRecordEditor("quotes"),
      wisdom: makeRecordEditor("wisdom"),
      duties: makeRecordEditor("duties"),
    }};

    function setStatus(text, isError = false) {{
      status.textContent = text;
      status.classList.toggle("error", isError);
    }}

    function activateTab(name) {{
      for (const button of tabButtons) {{
        button.classList.toggle("active", button.dataset.tab === name);
      }}
      for (const panel of tabPanels) {{
        panel.hidden = panel.dataset.panel !== name;
        panel.classList.toggle("active", panel.dataset.panel === name);
      }}
    }}

    function activateContentTab(name) {{
      for (const button of contentTabButtons) {{
        button.classList.toggle("active", button.dataset.contentTab === name);
      }}
      for (const panel of contentPanels) {{
        panel.hidden = panel.dataset.contentPanel !== name;
        panel.classList.toggle("active", panel.dataset.contentPanel === name);
      }}
    }}

    function summarizeRecord(item) {{
      const firstLine = item.trim().split(/\\n/)[0] || "(empty)";
      return firstLine.length <= 48 ? firstLine : `${{firstLine.slice(0, 45)}}...`;
    }}

    function makeRecordEditor(name) {{
      const root = document.querySelector(`[data-record-editor="${{name}}"]`);
      const list = root.querySelector("[data-record-list]");
      const text = root.querySelector("[data-record-text]");
      let items = [];
      let selected = -1;

      function refresh() {{
        list.replaceChildren();
        items.forEach((item, index) => {{
          const option = document.createElement("option");
          option.value = String(index);
          option.textContent = `${{index + 1}}. ${{summarizeRecord(item)}}`;
          list.append(option);
        }});
        if (selected >= items.length) selected = items.length - 1;
        if (selected >= 0) list.value = String(selected);
      }}

      function syncCurrent() {{
        if (selected < 0) return;
        const value = text.value.trim();
        if (value) {{
          items[selected] = value;
        }} else {{
          items.splice(selected, 1);
          selected = -1;
          text.value = "";
        }}
        refresh();
      }}

      function select(index) {{
        syncCurrent();
        selected = index;
        text.value = items[selected] || "";
        refresh();
        scheduleAutosave();
      }}

      function add() {{
        syncCurrent();
        items.push(text.value.trim() || "New item");
        selected = items.length - 1;
        text.value = items[selected];
        refresh();
        text.focus();
        scheduleAutosave(100);
      }}

      function remove() {{
        if (selected >= 0) {{
          items.splice(selected, 1);
          selected = items.length ? Math.min(selected, items.length - 1) : -1;
          text.value = selected >= 0 ? items[selected] : "";
          refresh();
        }} else {{
          text.value = "";
        }}
        scheduleAutosave(100);
      }}

      root.querySelector('[data-action="add"]').addEventListener("click", add);
      root.querySelector('[data-action="delete"]').addEventListener("click", remove);
      root.querySelector('[data-action="clear"]').addEventListener("click", () => {{
        text.value = "";
        text.focus();
        scheduleAutosave(100);
      }});
      list.addEventListener("change", () => select(Number(list.value)));

      return {{
        setItems(records) {{
          items = Array.isArray(records)
            ? records.map(item => String(item).trim()).filter(Boolean)
            : [];
          selected = items.length ? 0 : -1;
          text.value = selected >= 0 ? items[selected] : "";
          refresh();
        }},
        items() {{
          syncCurrent();
          return items.slice();
        }},
      }};
    }}

    function colorsFromForm() {{
      const out = {{}};
      for (const key of colorKeys) out[key] = form.elements[`hex:${{key}}`].value.trim();
      return out;
    }}

    function applyPreview() {{
      const colors = colorsFromForm();
      document.documentElement.style.setProperty("--quote-tab", colors.quote);
      document.documentElement.style.setProperty("--wisdom-tab", colors.wisdom);
      document.documentElement.style.setProperty("--duties-tab", colors.today);
      preview.style.setProperty("--quote", colors.quote);
      preview.style.setProperty("--wisdom", colors.wisdom);
      preview.style.setProperty("--today", colors.today);
      preview.style.setProperty("--ritual", colors.ritual);
      preview.style.setProperty("--totem-panel", colors.totem_panel);
      preview.style.setProperty("--wisdom-bullet", colors.wisdom_bullet);
      preview.style.setProperty("--today-bullet", colors.today_bullet);
      preview.style.setProperty("--highlight", colors.highlight);
      preview.style.setProperty("--border", colors.border);
    }}

    function fillForm(settings) {{
      fields.ritual_phrase.value = settings.ritual_phrase ?? "";
      fields.work_minutes.value = settings.work_minutes ?? "";
      fields.block_minutes.value = settings.block_minutes ?? "";
      fields.timebox_duties.checked = settings.timebox_duties === true;
      fields.timebox_phrase.value = settings.timebox_phrase ?? "";
      fields.timebox_lead_minutes.value = settings.timebox_lead_minutes ?? 1;
      fields.timebox_reminder_seconds.value = settings.timebox_reminder_seconds ?? 60;
      fields.content_mode.value = settings.content_mode ?? "merge";
      fields.google_calendar_urls.value = settings.google_calendar_urls ?? "";
      recordEditors.quotes.setItems(settings.quotes ?? []);
      recordEditors.wisdom.setItems(settings.wisdom ?? []);
      recordEditors.duties.setItems(settings.duties ?? []);
      for (const key of colorKeys) {{
        const value = settings.colors[key];
        form.elements[`color:${{key}}`].value = value;
        form.elements[`hex:${{key}}`].value = value;
      }}
      applyPreview();
    }}

    function collectPayload() {{
      return {{
        ritual_phrase: fields.ritual_phrase.value,
        work_minutes: fields.work_minutes.value,
        block_minutes: fields.block_minutes.value,
        timebox_duties: fields.timebox_duties.checked,
        timebox_phrase: fields.timebox_phrase.value,
        timebox_lead_minutes: fields.timebox_lead_minutes.value,
        timebox_reminder_seconds: fields.timebox_reminder_seconds.value,
        content_mode: fields.content_mode.value,
        google_calendar_urls: fields.google_calendar_urls.value,
        colors: colorsFromForm(),
        quotes: recordEditors.quotes.items(),
        wisdom: recordEditors.wisdom.items(),
        duties: recordEditors.duties.items(),
      }};
    }}

    function scheduleAutosave(delayMs = 800) {{
      if (loading) return;
      if (autosaveJob !== null) clearTimeout(autosaveJob);
      setStatus("Unsaved changes...");
      autosaveJob = setTimeout(() => saveSettings({{manual: false}}), delayMs);
    }}

    async function loadSettings() {{
      const response = await fetch("/api/settings", {{cache: "no-store"}});
      const data = await response.json();
      if (!data.ok) throw new Error(data.error || "Could not load settings");
      fillForm(data.settings);
      loading = false;
      setStatus("");
    }}

    async function saveSettings({{manual = true}} = {{}}) {{
      if (autosaveJob !== null) {{
        clearTimeout(autosaveJob);
        autosaveJob = null;
      }}
      setStatus(manual ? "Saving..." : "Autosaving...");
      const payload = collectPayload();
      const response = await fetch("/api/settings", {{
        method: "POST",
        headers: {{"Content-Type": "application/json"}},
        body: JSON.stringify(payload),
      }});
      const data = await response.json();
      if (!data.ok) {{
        setStatus(data.error || "Could not save settings", true);
        return;
      }}
      setStatus(manual ? "Saved." : "Autosaved.");
    }}

    for (const button of tabButtons) {{
      button.addEventListener("click", () => activateTab(button.dataset.tab));
    }}

    for (const button of contentTabButtons) {{
      button.addEventListener("click", () => activateContentTab(button.dataset.contentTab));
    }}

    for (const input of colorInputs) {{
      input.addEventListener("input", () => {{
        form.elements[`hex:${{input.dataset.colorKey}}`].value = input.value;
        applyPreview();
      }});
    }}
    for (const input of hexInputs) {{
      input.addEventListener("input", () => {{
        const value = input.value.trim();
        if (/^#[0-9a-fA-F]{{6}}$/.test(value)) {{
          form.elements[`color:${{input.dataset.hexKey}}`].value = value;
          applyPreview();
        }}
      }});
    }}

    form.addEventListener("input", () => scheduleAutosave());
    form.addEventListener("change", () => scheduleAutosave(100));
    form.addEventListener("submit", event => {{
      event.preventDefault();
      saveSettings({{manual: true}});
    }});
    loadSettings().catch(error => setStatus(error.message, true));
  </script>
</body>
</html>
"""
