import tkinter as tk
from tkinter import messagebox
import json
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / 'config.json'


def save_config(url: str):
    cfg = {'slack_webhook_url': url}
    with CONFIG_PATH.open('w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2)


def load_config():
    if CONFIG_PATH.exists():
        try:
            with CONFIG_PATH.open('r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def on_save():
    url = entry.get().strip()
    if not url:
        messagebox.showwarning("Missing URL", "Please enter your Slack Incoming Webhook URL.")
        return
    save_config(url)
    messagebox.showinfo("Saved", f"Saved webhook to {CONFIG_PATH}")
    root.destroy()


cfg = load_config()

root = tk.Tk()
root.title('WS Slack Translator - Configure Slack Webhook')

tk.Label(root, text='Slack Incoming Webhook URL:').pack(padx=10, pady=(10, 0))
entry = tk.Entry(root, width=80)
entry.pack(padx=10, pady=5)
if cfg.get('slack_webhook_url'):
    entry.insert(0, cfg.get('slack_webhook_url'))

btn = tk.Button(root, text='Save', command=on_save)
btn.pack(padx=10, pady=(5, 10))

root.mainloop()
