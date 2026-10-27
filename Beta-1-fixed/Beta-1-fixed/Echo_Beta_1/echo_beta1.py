"""Echo Beta 1 — Tkinter desktop study assistant prototype.

Uses only the Python standard library. Connected chat is optional and requires
an API key in the environment; offline commands continue to work without it.
"""
from __future__ import annotations

import ast
import json
import math
import os
import re
import threading
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, scrolledtext, simpledialog, ttk

APP_NAME = "ECHO"
VERSION = "Beta 1 · patched"
DATA_DIR = Path.home() / ".echo_beta1"
HISTORY_FILE = DATA_DIR / "history.json"
NOTES_FILE = DATA_DIR / "notes.json"
# Keep personal API credentials in config.json beside this script. Environment
# variables take precedence so deployments can override local configuration.
CONFIG_FILE = Path(__file__).resolve().parent / "config.json"


def _read_api_config(path: Path = CONFIG_FILE) -> dict[str, str]:
    """Read optional API settings from JSON without crashing on a bad config."""
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(config, dict):
        return {}
    result: dict[str, str] = {}
    for key in ("api_key", "api_url", "model"):
        value = config.get(key)
        if isinstance(value, str):
            result[key] = value.strip()
    return result


_API_CONFIG = _read_api_config()
DEFAULT_API_URL = (
    os.getenv("ECHO_API_URL") or _API_CONFIG.get("api_url")
    or "https://api.openai.com/v1/chat/completions"
).strip()
DEFAULT_MODEL = (
    os.getenv("ECHO_MODEL") or _API_CONFIG.get("model") or "gpt-4o-mini"
).strip()
API_KEY = (os.getenv("ECHO_API_KEY") or _API_CONFIG.get("api_key") or "").strip()
USER_AGENT = "Echo-Beta1/1.1 (+https://github.com/cjisdabest19-rgb/Beta-1; Python-urllib)"
SYSTEM_PROMPT = (
    "You are Echo, a general-purpose study assistant. Be accurate, concise, and clear. "
    "If you are unsure, say so. For schoolwork, explain the reasoning and help the "
    "student learn rather than merely encouraging copying. Do not claim to have "
    "performed actions you did not perform."
)


def safe_calculate(expression: str):
    """Evaluate basic arithmetic using a small, restricted AST whitelist."""
    if not isinstance(expression, str) or not expression.strip():
        raise ValueError("Enter an arithmetic expression.")
    if len(expression) > 250:
        raise ValueError("Expression is too long.")
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, ValueError) as exc:
        raise ValueError("That is not a valid arithmetic expression.") from exc

    allowed_binops = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)
    allowed_unary = (ast.UAdd, ast.USub)
    visited = 0

    def visit(node):
        nonlocal visited
        visited += 1
        if visited > 100:
            raise ValueError("Expression is too complex.")
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            value = node.value
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("Use finite numbers only.")
            return value
        if isinstance(node, ast.BinOp) and isinstance(node.op, allowed_binops):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow):
                if abs(right) > 8:
                    raise ValueError("Exponent is too large (maximum absolute exponent is 8).")
                if abs(left) > 1_000_000:
                    raise ValueError("Base is too large for exponentiation.")
            operation = {
                ast.Add: lambda: left + right,
                ast.Sub: lambda: left - right,
                ast.Mult: lambda: left * right,
                ast.Div: lambda: left / right,
                ast.FloorDiv: lambda: left // right,
                ast.Mod: lambda: left % right,
                ast.Pow: lambda: left ** right,
            }[type(node.op)]
            result = operation()
            if isinstance(result, complex):
                raise ValueError("Complex results are not supported.")
            if isinstance(result, int) and result.bit_length() > 256:
                raise ValueError("Result is too large for this calculator.")
            if isinstance(result, float) and not math.isfinite(result):
                raise ValueError("Result is outside the supported range.")
            return result
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, allowed_unary):
            value = visit(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        raise ValueError("Use numbers and basic operators only: + - * / // % ** and parentheses.")

    return visit(tree)


def load_json(path: Path, fallback):
    """Read JSON data; return a safe fallback for missing or malformed files."""
    try:
        if path.exists():
            value = json.loads(path.read_text(encoding="utf-8"))
            return value
    except (OSError, json.JSONDecodeError):
        pass
    return fallback


def save_json(path: Path, data) -> None:
    """Write JSON atomically so an interrupted write is less likely to corrupt it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    temp_path.replace(path)


def _command_name(text: str) -> str | None:
    cleaned = text.strip()
    if not cleaned:
        return None
    match = re.match(r"^/?(help|calc|study|summarize)\b", cleaned, flags=re.IGNORECASE)
    return match.group(1).lower() if match else None


def _is_local_command(text: str) -> bool:
    return _command_name(text) is not None


def local_reply(text: str) -> str:
    """Predictable offline commands; this is not a substitute for an AI model."""
    cleaned = text.strip()
    low = cleaned.lower()
    command = _command_name(cleaned)

    if command == "calc":
        argument = re.sub(r"^/?calc\b", "", cleaned, count=1, flags=re.IGNORECASE).strip()
        if not argument:
            return "Usage: /calc 12 * (4 + 3)"
        try:
            return f"Result: {safe_calculate(argument)}"
        except (ValueError, ArithmeticError, TypeError) as exc:
            return f"Calculator error: {exc}"

    if command == "help":
        return (
            "Echo Beta 1 commands:\n"
            "• /calc EXPRESSION — calculate arithmetic, e.g. /calc 12 * (4 + 3)\n"
            "• /study TOPIC — create a study checklist\n"
            "• /summarize TEXT — create a basic outline from supplied text\n"
            "• /help — show this help\n\n"
            "Use Save note to save a note. Open-ended AI chat requires an API key."
        )

    if command == "study":
        topic = re.sub(r"^/?study\b", "", cleaned, count=1, flags=re.IGNORECASE).strip()
        if not topic:
            return "Usage: /study TOPIC"
        return (
            f"Study plan: {topic}\n\n"
            "1. Read or watch one reliable explanation (10–20 minutes).\n"
            "2. Write 5–8 notes in your own words.\n"
            "3. Close the source and recall the main ideas from memory.\n"
            "4. Answer 5 practice questions without looking at your notes.\n"
            "5. Check mistakes and retry the missed questions."
        )

    if command == "summarize":
        body = re.sub(r"^/?summarize\b", "", cleaned, count=1, flags=re.IGNORECASE).strip()
        if not body:
            return "Usage: /summarize Paste text here"
        sentences = re.split(r"(?<=[.!?])\s+", body)
        excerpt = " ".join(sentences[:3])
        if len(excerpt) > 700:
            excerpt = excerpt[:697] + "..."
        return (
            "Offline text outline (basic extraction, not AI):\n\n"
            f"{excerpt}\n\nInput length: {len(body)} characters. Review the source to "
            "make sure the excerpt preserves the important details."
        )

    if any(greeting in low for greeting in ("hello", "hi echo", "hey echo")):
        return "Echo Beta 1 is ready. Type /help to see the available offline tools."
    return (
        "Echo is in offline fallback mode, so it cannot reliably answer open-ended questions yet. "
        "Try /help, /calc, /study, or /summarize, or configure ECHO_API_KEY for connected chat."
    )


def _clean_provider_error(detail: str, api_key: str = "") -> str:
    """Reduce provider error bodies to a short, key-redacted diagnostic string."""
    stripped = (detail or "").strip()
    if not stripped:
        return ""
    # Keep security-gateway markers even if the response is an HTML page.
    low = stripped.lower()
    if "1010" in low and "cloudflare" in low:
        result = "Cloudflare Error 1010: request blocked by a security rule."
    else:
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            # Avoid dumping a whole HTML challenge page into the chat.
            if "<html" in low or "<!doctype html" in low:
                result = "The server returned an HTML error/challenge page instead of a JSON API response."
            else:
                result = stripped[:300]
        else:
            result = ""
            if isinstance(parsed, dict):
                error = parsed.get("error")
                if isinstance(error, dict):
                    for key in ("message", "type", "code"):
                        if error.get(key):
                            result = str(error[key])
                            break
                if not result:
                    for key in ("message", "detail", "error"):
                        value = parsed.get(key)
                        if isinstance(value, str) and value:
                            result = value
                            break
                        if isinstance(value, list) and value and isinstance(value[0], dict):
                            result = str(value[0].get("message") or value[0].get("detail") or "")
                            if result:
                                break
            if not result:
                result = stripped[:300]
    if api_key:
        result = result.replace(api_key, "[REDACTED API KEY]")
    return result[:300]


def _describe_api_error(code: int, detail: str = "", url: str = "") -> str:
    """Explain likely categories without pretending to know provider-side causes."""
    text = (detail or "").lower()
    if "1010" in text and "cloudflare" in text:
        return (
            "The request was blocked with Cloudflare Error 1010. Cloudflare documents this as a "
            "request blocked based on the client's browser/request signature. This does not by itself "
            "prove the API key is wrong, and changing application code may not bypass the block. "
            "Verify ECHO_API_URL is the provider's official API endpoint, try a descriptive User-Agent "
            "(already sent by Echo), and ask the provider/network administrator if the block continues."
        )
    if code == 401:
        return (
            "Authentication failed (HTTP 401). Check that ECHO_API_KEY is present, active, and issued "
            "by the same provider used by ECHO_API_URL."
        )
    if code == 403:
        return (
            "Access was forbidden (HTTP 403). Possible causes include provider/account permissions, "
            "endpoint policy, network filtering, or a security gateway. The status code alone does not "
            "identify which cause applies. Verify the endpoint and account access."
        )
    if code == 404:
        return "Endpoint not found (HTTP 404). Check ECHO_API_URL and its chat-completions path."
    if code == 400:
        return (
            "The provider rejected the request (HTTP 400). Check the model name and whether the provider "
            "supports the requested chat-completions parameters."
        )
    if code == 429:
        return "Rate limit or quota reached (HTTP 429). Check the provider's rate limits, credits, and quota."
    if 500 <= code < 600:
        return f"The model provider returned a server error (HTTP {code}); retry later or check its status page."
    if detail:
        return f"The API request failed (HTTP {code}). Provider detail: {detail[:220]}"
    return f"The API request failed (HTTP {code}). Check the endpoint, API key, account access, and provider status."


def _read_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


def call_model(messages: list[dict], *, api_key: str | None = None,
               api_url: str | None = None, model: str | None = None) -> str:
    """Answer via local commands or an OpenAI-compatible Chat Completions API."""
    if not messages:
        return "No messages available."

    user_text = next(
        (str(item.get("content", "")).strip() for item in reversed(messages)
         if item.get("role") == "user" and str(item.get("content", "")).strip()),
        "",
    )
    if user_text and _is_local_command(user_text):
        # Explicitly route local commands before checking API credentials/network.
        return local_reply(user_text)

    key = API_KEY if api_key is None else api_key.strip()
    endpoint = DEFAULT_API_URL if api_url is None else api_url.strip()
    model_name = DEFAULT_MODEL if model is None else model.strip()
    if not key:
        return local_reply(user_text or str(messages[-1].get("content", "")))
    if not endpoint.startswith(("https://", "http://")) or not model_name:
        return "API configuration error: ECHO_API_URL must be an HTTP(S) URL and ECHO_MODEL must not be empty."

    payload = {
        "model": model_name,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages[-20:],
        "temperature": 0.4,
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
        choices = data.get("choices") if isinstance(data, dict) else None
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ValueError("The provider response did not contain a non-empty choices list.")
        message = choices[0].get("message", {})
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise ValueError("The provider response did not contain text in choices[0].message.content.")
        return content.strip()
    except urllib.error.HTTPError as exc:
        raw_body = _read_error_body(exc)
        detail = _clean_provider_error(raw_body, key)
        explanation = _describe_api_error(exc.code, detail or raw_body, endpoint)
        # Redact accidental echoes of the secret in all returned error text.
        explanation = explanation.replace(key, "[REDACTED API KEY]") if key else explanation
        if detail and detail.lower() not in explanation.lower() and "1010" not in detail.lower():
            explanation += f"\nProvider detail: {detail}"
        return f"Model API error: {explanation}"
    except urllib.error.URLError as exc:
        reason = str(getattr(exc, "reason", exc))
        if key:
            reason = reason.replace(key, "[REDACTED API KEY]")
        return (
            "Could not reach the model API. Check the internet connection, DNS/proxy settings, "
            f"and ECHO_API_URL. Technical detail: {reason[:220]}"
        )
    except (TimeoutError, json.JSONDecodeError, ValueError, TypeError, KeyError, IndexError) as exc:
        detail = str(exc).replace(key, "[REDACTED API KEY]") if key else str(exc)
        return f"Could not process the model API response: {detail[:250]}"


class EchoApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{APP_NAME} — {VERSION}")
        self.root.geometry("1000x680")
        self.root.minsize(760, 520)
        self.root.configure(bg="#101820")

        history = load_json(HISTORY_FILE, [])
        notes = load_json(NOTES_FILE, [])
        self.history = history if isinstance(history, list) else []
        self.notes = notes if isinstance(notes, list) else []
        self.messages: list[dict] = []
        self.current_history_id: str | None = None
        self.busy = False
        self._build_style()
        self._build_ui()
        mode = "API key configured" if API_KEY else "Offline tools · no API key"
        self._append_message(
            "Echo",
            "System ready. Beta 1 is running.\n" + mode +
            "\nType /help to see the offline commands."
        )
        self._render_history()

    def _build_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TButton", padding=7, font=("Segoe UI", 10))
        style.configure("TLabel", background="#101820", foreground="#e8eef2", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"), foreground="#8be9fd")
        style.configure("Muted.TLabel", foreground="#9aabb6", font=("Segoe UI", 9), background="#101820")

    def _build_ui(self):
        outer = tk.Frame(self.root, bg="#101820")
        outer.pack(fill="both", expand=True, padx=18, pady=14)
        header = tk.Frame(outer, bg="#101820")
        header.pack(fill="x", pady=(0, 12))
        ttk.Label(header, text="ECHO", style="Title.TLabel").pack(side="left")
        self.status_var = tk.StringVar(value=f"{VERSION}  •  {'API configured' if API_KEY else 'Offline tools'}")
        ttk.Label(header, textvariable=self.status_var, style="Muted.TLabel").pack(side="right", pady=8)

        body = tk.Frame(outer, bg="#101820")
        body.pack(fill="both", expand=True)
        sidebar = tk.Frame(body, bg="#182630", width=205)
        sidebar.pack(side="left", fill="y", padx=(0, 12))
        sidebar.pack_propagate(False)
        tk.Label(sidebar, text="WORKSPACE", bg="#182630", fg="#8be9fd", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(14, 8))
        ttk.Button(sidebar, text="＋ New chat", command=self.new_chat).pack(fill="x", padx=10, pady=4)
        ttk.Button(sidebar, text="Save note", command=self.save_note_dialog).pack(fill="x", padx=10, pady=4)
        ttk.Button(sidebar, text="View notes", command=self.view_notes).pack(fill="x", padx=10, pady=4)
        ttk.Button(sidebar, text="Calculator", command=self.calculator_dialog).pack(fill="x", padx=10, pady=4)
        ttk.Button(sidebar, text="Study helper", command=self.study_dialog).pack(fill="x", padx=10, pady=4)
        ttk.Button(sidebar, text="Clear chat", command=self.clear_chat).pack(fill="x", padx=10, pady=4)
        tk.Label(sidebar, text="RECENT CHATS", bg="#182630", fg="#8be9fd", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=12, pady=(18, 6))
        self.history_list = tk.Listbox(sidebar, bg="#101820", fg="#d9e3e8", selectbackground="#315568", relief="flat", highlightthickness=0, font=("Segoe UI", 9), activestyle="none")
        self.history_list.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.history_list.bind("<<ListboxSelect>>", self.load_selected_history)

        chat = tk.Frame(body, bg="#101820")
        chat.pack(side="left", fill="both", expand=True)
        self.transcript = scrolledtext.ScrolledText(chat, wrap="word", state="disabled", bg="#17232c", fg="#e8eef2", insertbackground="#ffffff", relief="flat", borderwidth=0, font=("Segoe UI", 11), padx=16, pady=14)
        self.transcript.pack(fill="both", expand=True)
        self.transcript.tag_config("speaker", foreground="#8be9fd", font=("Segoe UI", 10, "bold"))
        self.transcript.tag_config("user", foreground="#ffd580", font=("Segoe UI", 10, "bold"))
        self.transcript.tag_config("body", foreground="#e8eef2", font=("Segoe UI", 11))
        quick = tk.Frame(chat, bg="#101820")
        quick.pack(fill="x", pady=(10, 0))
        self.entry = tk.Text(quick, height=3, wrap="word", bg="#22313b", fg="#f4f7f9", insertbackground="#ffffff", relief="flat", font=("Segoe UI", 11), padx=10, pady=9)
        self.entry.pack(side="left", fill="both", expand=True, padx=(0, 8))
        self.entry.bind("<Control-Return>", self._send_shortcut)
        ttk.Button(quick, text="Send", command=self.send_message).pack(side="right", fill="y")
        ttk.Label(chat, text="Send with Ctrl+Enter • Local notes and history stay on this device", style="Muted.TLabel").pack(anchor="w", pady=(6, 0))

    def _append_message(self, speaker: str, text: str):
        self.transcript.configure(state="normal")
        tag = "user" if speaker == "You" else "speaker"
        self.transcript.insert("end", f"{speaker}\n", tag)
        self.transcript.insert("end", text + "\n\n", "body")
        self.transcript.see("end")
        self.transcript.configure(state="disabled")

    def _send_shortcut(self, _event):
        self.send_message()
        return "break"

    def send_message(self):
        if self.busy:
            return
        text = self.entry.get("1.0", "end").strip()
        if not text:
            return
        self.entry.delete("1.0", "end")
        self._append_message("You", text)
        self.messages.append({"role": "user", "content": text})
        self.busy = True
        self.status_var.set("Working…")
        # A detached snapshot avoids another UI submission mutating the worker's input list.
        snapshot = [dict(message) for message in self.messages]
        threading.Thread(target=self._get_reply, args=(snapshot,), daemon=True).start()

    def _get_reply(self, messages_snapshot):
        try:
            reply = call_model(messages_snapshot)
        except Exception as exc:  # Keep unexpected worker errors from leaving the UI stuck.
            reply = f"Unexpected error while getting a reply: {type(exc).__name__}: {exc}"
        self.root.after(0, self._finish_reply, reply)

    def _finish_reply(self, reply: str):
        self.messages.append({"role": "assistant", "content": reply})
        self._append_message("Echo", reply)
        self.busy = False
        self.status_var.set(f"{VERSION}  •  {'API configured' if API_KEY else 'Offline tools'}")
        self._save_current_history()

    def _save_current_history(self):
        if not self.messages:
            return
        record = {
            "id": self.current_history_id or str(uuid.uuid4()),
            "updated": datetime.now().isoformat(timespec="minutes"),
            "title": next((str(m.get("content", ""))[:36] for m in self.messages if m.get("role") == "user"), "New chat"),
            "messages": self.messages,
        }
        self.current_history_id = record["id"]
        existing = next((i for i, item in enumerate(self.history) if item.get("id") == self.current_history_id), None)
        if existing is not None:
            self.history.pop(existing)
        self.history.insert(0, record)
        self.history = self.history[:30]
        try:
            save_json(HISTORY_FILE, self.history)
            self._render_history()
        except OSError as exc:
            messagebox.showerror("Save history", f"Could not save conversation history:\n{exc}", parent=self.root)

    def _render_history(self):
        self.history_list.delete(0, "end")
        for item in self.history[:30]:
            title = str(item.get("title", "Chat"))
            updated = str(item.get("updated", ""))
            self.history_list.insert("end", f"{title}  ·  {updated}")

    def load_selected_history(self, _event=None):
        selected = self.history_list.curselection()
        if not selected:
            return
        record = self.history[selected[0]]
        self.current_history_id = record.get("id")
        messages = record.get("messages", [])
        self.messages = [m for m in messages if isinstance(m, dict) and m.get("role") in {"user", "assistant", "system"}]
        self.transcript.configure(state="normal")
        self.transcript.delete("1.0", "end")
        self.transcript.configure(state="disabled")
        for msg in self.messages:
            role = "You" if msg.get("role") == "user" else "Echo"
            self._append_message(role, str(msg.get("content", "")))

    def new_chat(self):
        self._save_current_history()
        self.messages = []
        self.current_history_id = None
        self.transcript.configure(state="normal")
        self.transcript.delete("1.0", "end")
        self.transcript.configure(state="disabled")
        self._append_message("Echo", "New chat started. Type /help for commands.")
        self.entry.focus_set()

    def clear_chat(self):
        if messagebox.askyesno("Clear chat", "Clear the visible conversation?", parent=self.root):
            self.messages = []
            self.current_history_id = None
            self.transcript.configure(state="normal")
            self.transcript.delete("1.0", "end")
            self.transcript.configure(state="disabled")
            self._append_message("Echo", "Conversation cleared.")

    def save_note_dialog(self):
        title = simpledialog.askstring("Save note", "Note title:", parent=self.root)
        if not title or not title.strip():
            return
        content = simpledialog.askstring("Save note", "Note content:", parent=self.root)
        if content is None:
            return
        self.notes.insert(0, {"title": title.strip(), "content": content, "saved": datetime.now().isoformat(timespec="minutes")})
        try:
            save_json(NOTES_FILE, self.notes)
            messagebox.showinfo("Echo notes", "Note saved locally.", parent=self.root)
        except OSError as exc:
            messagebox.showerror("Echo notes", f"Could not save the note:\n{exc}", parent=self.root)

    def view_notes(self):
        win = tk.Toplevel(self.root)
        win.title("Echo — Notes")
        win.geometry("560x440")
        win.configure(bg="#101820")
        area = scrolledtext.ScrolledText(win, wrap="word", font=("Segoe UI", 10), bg="#17232c", fg="#e8eef2", padx=12, pady=12)
        area.pack(fill="both", expand=True, padx=12, pady=12)
        if not self.notes:
            area.insert("end", "No notes saved yet. Use Save note to add one.")
        else:
            for note in self.notes:
                if not isinstance(note, dict):
                    continue
                area.insert("end", f"{note.get('title', 'Untitled')}\n", "title")
                area.insert("end", f"{note.get('saved', '')}\n{note.get('content', '')}\n\n")
            area.tag_config("title", font=("Segoe UI", 11, "bold"), foreground="#8be9fd")
        area.configure(state="disabled")

    def calculator_dialog(self):
        expression = simpledialog.askstring("Echo calculator", "Arithmetic expression (e.g. (12 * 4) / 3):", parent=self.root)
        if expression is None:
            return
        try:
            result = safe_calculate(expression)
            messagebox.showinfo("Calculator result", f"{expression} = {result}", parent=self.root)
        except (ValueError, ArithmeticError, TypeError) as exc:
            messagebox.showerror("Calculator error", str(exc), parent=self.root)

    def study_dialog(self):
        topic = simpledialog.askstring("Study helper", "What topic are you studying?", parent=self.root)
        if not topic or not topic.strip():
            return
        self.entry.insert("end", f"/study {topic.strip()}")
        self.entry.focus_set()


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    EchoApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
