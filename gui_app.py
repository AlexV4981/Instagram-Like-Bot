"""
gui_app.py — Tkinter GUI for the Instagram bot.

No browser window — everything runs through API calls.
Window 1: Login / Restore saved session
Window 2: Control panel (profile URL, begin/pause/stop, delay, log)
"""

import tkinter as tk
from tkinter import scrolledtext, messagebox
import threading
import sys
import os
import io
from datetime import datetime
from urllib.request import urlopen, Request

sys.path.insert(0, os.path.dirname(__file__))

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

import session_manager as sm
from bot_engine import InstagramBot

# ── palette ───────────────────────────────────────────────────
BG       = "#1a1a2e"
BG_PANEL = "#16213e"
FG       = "#e0e0e0"
FG_DIM   = "#8892b0"
ACCENT   = "#e94560"
ACCENT2  = "#0f3460"
BTN_BG   = "#0f3460"
BTN_FG   = "#e0e0e0"
ENTRY_BG = "#16213e"
ENTRY_FG = "#e0e0e0"
LOG_BG   = "#0d1117"
LOG_FG   = "#c9d1d9"
FONT     = ("Segoe UI", 11)
FONT_SM  = ("Segoe UI", 10)
FONT_LG  = ("Segoe UI", 14, "bold")
FONT_MONO = ("Consolas", 10)


class App:
    def __init__(self):
        self.bot = InstagramBot(
            log_callback=self._log,
            status_callback=self._set_status,
            image_callback=self._set_post_image,
        )
        self.root = tk.Tk()
        self.root.withdraw()
        sm.ensure_dirs()
        self._build_login_window()

    # ──────────────────────────────────────────────────────────
    #  WINDOW 1 — LOGIN
    # ──────────────────────────────────────────────────────────
    def _build_login_window(self):
        self.login_win = tk.Toplevel(self.root)
        self.login_win.title("Instagram Bot \u2014 Login")
        self.login_win.geometry("440x400")
        self.login_win.configure(bg=BG)
        self.login_win.resizable(False, False)
        self.login_win.protocol("WM_DELETE_WINDOW", self._on_close_all)

        tk.Label(self.login_win, text="Instagram Bot",
                 font=("Segoe UI", 20, "bold"), bg=BG, fg=ACCENT).pack(pady=(25, 2))
        tk.Label(self.login_win, text="No browser required \u2014 Pure API",
                 font=("Segoe UI", 10, "italic"), bg=BG, fg=FG_DIM).pack(pady=(0, 15))

        frame = tk.Frame(self.login_win, bg=BG)
        frame.pack(pady=5)

        tk.Label(frame, text="Username", font=FONT, bg=BG, fg=FG
                 ).grid(row=0, column=0, sticky="w", padx=10, pady=5)
        self.ent_user = tk.Entry(frame, font=FONT, width=28, bg=ENTRY_BG,
                                  fg=ENTRY_FG, insertbackground=FG, relief="flat",
                                  highlightthickness=1, highlightcolor=ACCENT)
        self.ent_user.grid(row=0, column=1, padx=10, pady=5)

        tk.Label(frame, text="Password", font=FONT, bg=BG, fg=FG
                 ).grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self.ent_pass = tk.Entry(frame, font=FONT, width=28, show="\u2022",
                                  bg=ENTRY_BG, fg=ENTRY_FG, insertbackground=FG,
                                  relief="flat", highlightthickness=1,
                                  highlightcolor=ACCENT)
        self.ent_pass.grid(row=1, column=1, padx=10, pady=5)

        # prefill from .env
        env = sm.load_env()
        if env["username"]:
            self.ent_user.insert(0, env["username"])
        if env["password"]:
            self.ent_pass.insert(0, env["password"])

        # buttons
        bf = tk.Frame(self.login_win, bg=BG)
        bf.pack(pady=18)

        self.btn_login = tk.Button(
            bf, text="Login", font=FONT, width=14,
            bg=ACCENT, fg="white", activebackground="#c0392b",
            relief="flat", cursor="hand2", command=self._on_login)
        self.btn_login.grid(row=0, column=0, padx=8)

        self.btn_session = tk.Button(
            bf, text="Use Saved Session", font=FONT, width=16,
            bg=BTN_BG, fg=BTN_FG, activebackground=ACCENT2,
            relief="flat", cursor="hand2", command=self._on_session_login)
        self.btn_session.grid(row=0, column=1, padx=8)

        self.login_status = tk.Label(self.login_win, text="", font=FONT_SM,
                                      bg=BG, fg=FG_DIM)
        self.login_status.pack(pady=5)

        # session indicator
        has = sm.session_exists()
        txt = "\u2713 Encrypted session found" if has else "\u2717 No saved session"
        clr = "#2ecc71" if has else ACCENT
        tk.Label(self.login_win, text=txt, font=FONT_SM, bg=BG, fg=clr).pack()
        tk.Label(self.login_win,
                 text="Uses Instagram Private API (no browser needed)",
                 font=("Segoe UI", 9), bg=BG, fg=FG_DIM).pack(pady=(12, 0))

    def _on_login(self):
        user = self.ent_user.get().strip()
        pw   = self.ent_pass.get().strip()
        if not user or not pw:
            messagebox.showwarning("Missing Info", "Enter both username and password.")
            return
        self.login_status.config(text="Logging in via API...", fg="#f1c40f")
        self.btn_login.config(state="disabled")
        self.btn_session.config(state="disabled")

        def task():
            if self.bot.login(user, pw):
                self.root.after(0, self._transition_to_main)
            else:
                self._reset_login("Login failed. Check credentials or verify on phone.")

        threading.Thread(target=task, daemon=True).start()

    def _on_session_login(self):
        if not sm.session_exists():
            messagebox.showinfo("No Session", "No saved session. Please login normally.")
            return
        self.login_status.config(text="Decrypting & validating session...", fg="#f1c40f")
        self.btn_login.config(state="disabled")
        self.btn_session.config(state="disabled")

        def task():
            if self.bot.try_session_login():
                self.root.after(0, self._transition_to_main)
            else:
                self._reset_login("Session expired. Login with credentials.")

        threading.Thread(target=task, daemon=True).start()

    def _reset_login(self, msg):
        self.root.after(0, lambda: self.login_status.config(text=msg, fg=ACCENT))
        self.root.after(0, lambda: self.btn_login.config(state="normal"))
        self.root.after(0, lambda: self.btn_session.config(state="normal"))

    def _transition_to_main(self):
        self.login_win.destroy()
        self._build_main_window()

    # ──────────────────────────────────────────────────────────
    #  WINDOW 2 — CONTROL PANEL
    # ──────────────────────────────────────────────────────────
    def _build_main_window(self):
        self.main_win = tk.Toplevel(self.root)
        self.main_win.title("Instagram Bot \u2014 Control Panel")
        self.main_win.geometry("920x680")
        self.main_win.configure(bg=BG)
        self.main_win.resizable(True, True)
        self.main_win.minsize(750, 550)
        self.main_win.protocol("WM_DELETE_WINDOW", self._on_close_all)

        # ── top half ──────────────────────────────────────────
        top = tk.Frame(self.main_win, bg=BG)
        top.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        top.columnconfigure(0, weight=1)
        top.columnconfigure(1, weight=0)
        top.columnconfigure(2, weight=2)
        top.rowconfigure(0, weight=1)

        # LEFT — controls
        left = tk.Frame(top, bg=BG_PANEL)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 2))
        il = tk.Frame(left, bg=BG_PANEL)
        il.pack(fill="both", expand=True, padx=15, pady=15)

        tk.Label(il, text="Profile URL or @username", font=FONT,
                 bg=BG_PANEL, fg=FG).pack(anchor="w")
        self.ent_profile = tk.Entry(il, font=FONT, bg=ENTRY_BG, fg=ENTRY_FG,
                                     insertbackground=FG, relief="flat",
                                     highlightthickness=1, highlightcolor=ACCENT)
        self.ent_profile.pack(fill="x", pady=(2, 12))
        self.ent_profile.insert(0, "https://www.instagram.com/username/")

        tk.Label(il, text="Posts to like", font=FONT, bg=BG_PANEL, fg=FG).pack(anchor="w")
        num_row = tk.Frame(il, bg=BG_PANEL)
        num_row.pack(anchor="w", pady=(2, 12))

        self.ent_num = tk.Entry(num_row, font=FONT, width=8, bg=ENTRY_BG, fg=ENTRY_FG,
                                 insertbackground=FG, relief="flat",
                                 highlightthickness=1, highlightcolor=ACCENT)
        self.ent_num.pack(side="left")
        self.ent_num.insert(0, "10")

        self.btn_all = tk.Button(num_row, text="All", font=FONT_SM, width=6,
                                  bg=ACCENT2, fg="white", activebackground="#2980b9",
                                  relief="flat", cursor="hand2", command=self._on_all)
        self.btn_all.pack(side="left", padx=(8, 0))

        self.btn_begin = tk.Button(il, text="\u25B6  Begin", font=FONT_LG, width=18,
                                    bg="#27ae60", fg="white", activebackground="#2ecc71",
                                    relief="flat", cursor="hand2", command=self._on_begin)
        self.btn_begin.pack(pady=(5, 6))

        self.btn_pause = tk.Button(il, text="\u23F8  Pause", font=FONT, width=18,
                                    bg="#f39c12", fg="white", activebackground="#f1c40f",
                                    relief="flat", cursor="hand2", state="disabled",
                                    command=self._on_pause)
        self.btn_pause.pack(pady=4)

        self.btn_stop = tk.Button(il, text="\u25A0  Stop", font=FONT, width=18,
                                   bg=ACCENT, fg="white", activebackground="#c0392b",
                                   relief="flat", cursor="hand2", state="disabled",
                                   command=self._on_stop)
        self.btn_stop.pack(pady=4)

        # delay row
        df = tk.Frame(il, bg=BG_PANEL)
        df.pack(fill="x", pady=(12, 0))
        tk.Label(df, text="Random Delay (sec)", font=FONT_SM,
                 bg=BG_PANEL, fg=FG_DIM).pack(anchor="w")
        dr = tk.Frame(df, bg=BG_PANEL)
        dr.pack(fill="x", pady=4)

        tk.Label(dr, text="Min:", font=FONT_SM, bg=BG_PANEL, fg=FG).pack(side="left")
        self.ent_dmin = tk.Entry(dr, font=FONT_SM, width=5, bg=ENTRY_BG,
                                  fg=ENTRY_FG, insertbackground=FG, relief="flat")
        self.ent_dmin.pack(side="left", padx=(2, 10))
        self.ent_dmin.insert(0, "2")

        tk.Label(dr, text="Max:", font=FONT_SM, bg=BG_PANEL, fg=FG).pack(side="left")
        self.ent_dmax = tk.Entry(dr, font=FONT_SM, width=5, bg=ENTRY_BG,
                                  fg=ENTRY_FG, insertbackground=FG, relief="flat")
        self.ent_dmax.pack(side="left", padx=(2, 10))
        self.ent_dmax.insert(0, "5")

        self.delay_on = True
        self.btn_dtoggle = tk.Button(dr, text="ON", font=FONT_SM, width=5,
                                      bg="#27ae60", fg="white", relief="flat",
                                      cursor="hand2", command=self._toggle_delay)
        self.btn_dtoggle.pack(side="left", padx=4)

        # VERTICAL DIVIDER
        tk.Frame(top, bg="#111", width=4).grid(row=0, column=1, sticky="ns")

        # RIGHT — image preview + status
        right = tk.Frame(top, bg=BG_PANEL)
        right.grid(row=0, column=2, sticky="nsew", padx=(2, 0))
        ir = tk.Frame(right, bg=BG_PANEL)
        ir.pack(fill="both", expand=True, padx=15, pady=15)

        # Status row
        status_row = tk.Frame(ir, bg=BG_PANEL)
        status_row.pack(fill="x")
        self.lbl_status = tk.Label(status_row, text="Status: Idle", font=FONT,
                                    bg=BG_PANEL, fg="#2ecc71")
        self.lbl_status.pack(side="left")
        self.lbl_liked = tk.Label(status_row, text="Liked: 0", font=FONT,
                                   bg=BG_PANEL, fg=FG)
        self.lbl_liked.pack(side="right")

        # ── Image preview area ──
        self.preview_frame = tk.Frame(ir, bg="#000000", relief="flat",
                                       highlightbackground=ACCENT2,
                                       highlightthickness=1)
        self.preview_frame.pack(fill="both", expand=True, pady=(8, 5))

        self.img_label = tk.Label(self.preview_frame, bg="#000000",
                                   text="Post preview will appear here",
                                   font=FONT_SM, fg=FG_DIM)
        self.img_label.pack(fill="both", expand=True)
        self._current_photo = None  # prevent garbage collection

        self.lbl_caption = tk.Label(ir, text="", font=FONT_SM,
                                     bg=BG_PANEL, fg=FG_DIM, anchor="w",
                                     wraplength=400)
        self.lbl_caption.pack(fill="x", pady=(0, 5))

        # ── Liked links list ──
        tk.Label(ir, text="Liked Post Links", font=FONT_SM,
                 bg=BG_PANEL, fg=FG_DIM).pack(anchor="w", pady=(3, 2))
        self.links_list = tk.Listbox(ir, font=FONT_MONO, bg=LOG_BG, fg=LOG_FG,
                                      selectbackground=ACCENT2, relief="flat",
                                      height=5)
        self.links_list.pack(fill="both")

        # HORIZONTAL DIVIDER
        tk.Frame(self.main_win, bg="#111", height=4).pack(fill="x", padx=8, pady=4)

        # BOTTOM — log
        lf = tk.Frame(self.main_win, bg=BG)
        lf.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        log_header = tk.Frame(lf, bg=BG)
        log_header.pack(fill="x")
        tk.Label(log_header, text="Activity Log", font=FONT_SM, bg=BG, fg=FG_DIM).pack(side="left")

        self.head_on = False
        self.btn_head = tk.Button(
            log_header, text="Show Head: OFF", font=("Segoe UI", 9, "bold"),
            width=16, bg=ACCENT, fg="white", activebackground="#c0392b",
            relief="flat", cursor="hand2", command=self._toggle_head)
        self.btn_head.pack(side="right")
        self.log_box = scrolledtext.ScrolledText(
            lf, font=FONT_MONO, bg=LOG_BG, fg=LOG_FG,
            insertbackground=FG, relief="flat", height=10,
            state="disabled", wrap="word")
        self.log_box.pack(fill="both", expand=True, pady=(3, 0))
        self.log_box.tag_config("error",   foreground="#e74c3c")
        self.log_box.tag_config("success", foreground="#2ecc71")
        self.log_box.tag_config("info",    foreground="#3498db")
        self.log_box.tag_config("heart",   foreground="#e94560")
        self.log_box.tag_config("head",    foreground="#9b59b6")

        self._log("[+] Ready. Enter a profile URL or @username and click Begin.")

    # ── button handlers ───────────────────────────────────────
    def _on_begin(self):
        url = self.ent_profile.get().strip()
        if not url or url == "https://www.instagram.com/username/":
            messagebox.showwarning("Missing", "Enter a profile URL or @username.")
            return
        try:
            num = int(self.ent_num.get().strip())
            if num < 1: raise ValueError
        except ValueError:
            messagebox.showwarning("Invalid", "Posts to like must be \u2265 1.")
            return
        try:
            mn = float(self.ent_dmin.get().strip())
            mx = float(self.ent_dmax.get().strip())
            if mn < 0 or mx < mn: raise ValueError
            self.bot.delay_min = mn
            self.bot.delay_max = mx
        except ValueError:
            messagebox.showwarning("Invalid", "Check delay values (min < max, both \u2265 0).")
            return
        self.bot.use_random_delay = self.delay_on

        self.btn_begin.config(state="disabled")
        self.btn_pause.config(state="normal")
        self.btn_stop.config(state="normal")

        def task():
            self.bot.like_profile_posts(url, num_posts=num)
            self.root.after(0, self._on_bot_done)

        threading.Thread(target=task, daemon=True).start()

    def _on_all(self):
        """Like all posts on the profile in randomized batches."""
        url = self.ent_profile.get().strip()
        if not url or url == "https://www.instagram.com/username/":
            messagebox.showwarning("Missing", "Enter a profile URL or @username.")
            return
        try:
            mn = float(self.ent_dmin.get().strip())
            mx = float(self.ent_dmax.get().strip())
            if mn < 0 or mx < mn:
                raise ValueError
            self.bot.delay_min = mn
            self.bot.delay_max = mx
        except ValueError:
            messagebox.showwarning("Invalid", "Check delay values (min < max, both ≥ 0).")
            return

        self.bot.use_random_delay = self.delay_on

        self.btn_begin.config(state="disabled")
        self.btn_pause.config(state="normal")
        self.btn_stop.config(state="normal")
        self.btn_all.config(state="disabled")

        def task():
            self.bot.like_profile_posts(url, num_posts=0, like_all=True)
            self.root.after(0, self._on_bot_done)

        threading.Thread(target=task, daemon=True).start()

    def _on_pause(self):
        if self.bot.paused:
            self.bot.resume()
            self.btn_pause.config(text="\u23F8  Pause", bg="#f39c12")
        else:
            self.bot.pause()
            self.btn_pause.config(text="\u25B6  Resume", bg="#27ae60")

    def _on_stop(self):
        self.bot.stop()
        self.btn_pause.config(state="disabled", text="\u23F8  Pause", bg="#f39c12")
        self.btn_stop.config(state="disabled")
        self.btn_begin.config(state="normal")

    def _on_bot_done(self):
        self.btn_begin.config(state="normal")
        self.btn_pause.config(state="disabled", text="\u23F8  Pause", bg="#f39c12")
        self.btn_stop.config(state="disabled")
        self._refresh_links()

    def _set_post_image(self, url, caption=""):
        """Download and display the current post's thumbnail."""
        def _do_image():
            try:
                if not HAS_PIL:
                    self.img_label.config(text="Install Pillow for previews:\npip install Pillow")
                    return
                if not hasattr(self, "img_label"):
                    return
                # fetch image from CDN
                req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
                raw = urlopen(req, timeout=8).read()
                img = Image.open(io.BytesIO(raw))

                # resize to fit the preview frame, maintaining aspect ratio
                frame_w = self.preview_frame.winfo_width() or 350
                frame_h = self.preview_frame.winfo_height() or 280
                img.thumbnail((frame_w, frame_h), Image.LANCZOS)

                photo = ImageTk.PhotoImage(img)
                self.img_label.config(image=photo, text="")
                self._current_photo = photo  # prevent GC

                if caption:
                    self.lbl_caption.config(text=f"\u201C{caption}\u201D")
                else:
                    self.lbl_caption.config(text="")
            except Exception as e:
                self.img_label.config(text=f"Could not load preview\n{e}")
        try:
            self.root.after(0, _do_image)
        except Exception:
            pass

    def _toggle_delay(self):
        self.delay_on = not self.delay_on
        self.btn_dtoggle.config(
            text="ON" if self.delay_on else "OFF",
            bg="#27ae60" if self.delay_on else "#95a5a6")
        self.bot.use_random_delay = self.delay_on

    def _toggle_head(self):
        self.head_on = not self.head_on
        if self.head_on:
            self.btn_head.config(text="Show Head: ON", bg="#27ae60")
            self.bot.set_head_mode(True)
        else:
            self.btn_head.config(text="Show Head: OFF", bg=ACCENT)
            self.bot.set_head_mode(False)

    # ── logging (thread-safe) ─────────────────────────────────
    def _log(self, msg):
        def _do():
            ts = datetime.now().strftime("%H:%M:%S")
            line = f"[{ts}] {msg}\n"
            try:
                if not hasattr(self, "log_box"):
                    print(line, end="")
                    return
                self.log_box.config(state="normal")
                tag = None
                if "[ERROR]" in msg or "[!]" in msg:
                    tag = "error"
                elif "[+]" in msg or "[\u2713]" in msg:
                    tag = "success"
                elif "[\u2665]" in msg:
                    tag = "heart"
                elif "[HEAD]" in msg:
                    tag = "head"
                elif "[~]" in msg:
                    tag = "info"
                self.log_box.insert("end", line, tag)
                self.log_box.see("end")
                self.log_box.config(state="disabled")
            except tk.TclError:
                pass
            self._refresh_links()
        try:
            self.root.after(0, _do)
        except Exception:
            print(msg)

    def _set_status(self, text):
        try:
            if not hasattr(self, "lbl_status"):
                return
            self.root.after(0, lambda: self.lbl_status.config(text=f"Status: {text}"))
        except Exception:
            pass

    def _refresh_links(self):
        try:
            if not hasattr(self, "lbl_liked"):
                return
            self.lbl_liked.config(text=f"Posts liked: {self.bot.liked_count}")
            links = sm.load_liked_links()
            self.links_list.delete(0, "end")
            for lnk in links[-20:]:
                self.links_list.insert("end", lnk)
        except Exception:
            pass

    # ── cleanup ───────────────────────────────────────────────
    def _on_close_all(self):
        self.bot.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
