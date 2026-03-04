"""
bot_engine.py — Instagram bot engine using instagrapi (no browser).

Uses Instagram's Private Mobile API to:
 - Log in / restore sessions
 - Fetch a user's posts
 - Like posts with configurable delays
 - Pause / stop gracefully
"""

import time
import random
import traceback
import logging
import http.client

from instagrapi import Client
from instagrapi.exceptions import (
    LoginRequired,
    ChallengeRequired,
    FeedbackRequired,
    PleaseWaitFewMinutes,
    ClientError,
)
import session_manager as sm

logger = logging.getLogger("bot_engine")


class InstagramBot:
    def __init__(self, log_callback=None, status_callback=None, image_callback=None):
        self.cl: Client | None = None
        self.log = log_callback or print
        self.set_status = status_callback or (lambda s: None)
        self.set_image = image_callback or (lambda url, caption: None)
        self.running = False
        self.paused = False
        self.use_random_delay = True
        self.delay_min = 2.0
        self.delay_max = 5.0
        self.liked_count = 0
        self.head_mode = False
        self._log_handler = None

    def set_head_mode(self, enabled: bool):
        """Toggle verbose API logging (the 'head')."""
        self.head_mode = enabled
        if enabled:
            self._enable_verbose_logging()
            self.log("[HEAD] Verbose mode ON — showing API requests & responses")
        else:
            self._disable_verbose_logging()
            self.log("[HEAD] Verbose mode OFF")

    def _enable_verbose_logging(self):
        """Hook into instagrapi + urllib3 + http.client to show traffic."""
        # instagrapi's own logger
        for name in ("instagrapi", "instagrapi.mixins", "urllib3", "urllib3.connectionpool"):
            lg = logging.getLogger(name)
            lg.setLevel(logging.DEBUG)
            if self._log_handler is None:
                self._log_handler = _BotLogHandler(self.log)
                self._log_handler.setFormatter(
                    logging.Formatter("[HEAD] %(name)s: %(message)s")
                )
            if self._log_handler not in lg.handlers:
                lg.addHandler(self._log_handler)
        # http.client debug (shows raw headers)
        http.client.HTTPConnection.debuglevel = 1

    def _disable_verbose_logging(self):
        """Remove verbose hooks."""
        for name in ("instagrapi", "instagrapi.mixins", "urllib3", "urllib3.connectionpool"):
            lg = logging.getLogger(name)
            lg.setLevel(logging.WARNING)
            if self._log_handler and self._log_handler in lg.handlers:
                lg.removeHandler(self._log_handler)
        http.client.HTTPConnection.debuglevel = 0

    # ── helpers ───────────────────────────────────────────────
    def _delay(self, base=2.0):
        t = random.uniform(self.delay_min, self.delay_max) if self.use_random_delay else base
        # sleep in small increments so pause/stop is responsive
        end = time.time() + t
        while time.time() < end:
            if not self.running:
                raise InterruptedError("Bot stopped by user.")
            time.sleep(0.3)

    def _check_state(self):
        while self.paused and self.running:
            time.sleep(0.3)
        if not self.running:
            raise InterruptedError("Bot stopped by user.")

    # ── login ─────────────────────────────────────────────────
    def try_session_login(self) -> bool:
        """Attempt to restore a saved encrypted session."""
        settings = sm.load_session()
        if settings is None:
            self.log("[-] No saved session found.")
            return False
        try:
            self.log("[~] Restoring encrypted session...")
            self.cl = Client()
            self.cl.set_settings(settings)
            self.cl.login(settings.get("username", ""), settings.get("password", ""))
            # validate with a lightweight call
            self.cl.get_timeline_feed()
            self.log("[+] Session restored successfully (no browser needed)!")
            return True
        except LoginRequired:
            self.log("[-] Session expired. Fresh login required.")
            sm.delete_session()
            return False
        except Exception as e:
            self.log(f"[-] Session restore failed: {e}")
            sm.delete_session()
            return False

    def login(self, username: str, password: str) -> bool:
        """Login with username/password via Instagram's Private API."""
        try:
            self.log("[~] Logging in via Instagram Private API...")
            self.cl = Client()
            self.cl.login(username, password)
            # save session
            settings = self.cl.get_settings()
            settings["username"] = username
            settings["password"] = password
            sm.save_session(settings)
            sm.save_env(username, password)
            self.log("[+] Login successful! Session encrypted and saved.")
            return True
        except ChallengeRequired:
            self.log("[ERROR] Instagram requires a challenge (captcha/verification).\n"
                     "        Open Instagram on your phone, verify, then try again.")
            return False
        except Exception as e:
            self.log(f"[ERROR] Login failed: {e}")
            traceback.print_exc()
            return False

    # ── like posts ────────────────────────────────────────────
    def like_profile_posts(self, profile_input: str, num_posts: int = 20, like_all: bool = False):
        """Fetch a user's recent posts and like them."""
        self.running = True
        self.paused = False
        self.liked_count = 0

        try:
            if self.cl is None:
                self.log("[ERROR] Not logged in.")
                self.running = False
                return

            # resolve username
            username = self._extract_username(profile_input)
            self.log(f"[~] Looking up user: @{username}")
            self.set_status("Fetching user info...")

            try:
                user_id = self.cl.user_id_from_username(username)
                user_info = self.cl.user_info(user_id)
                self.log(f"[+] Found: @{user_info.username} "
                         f"({user_info.full_name}) — "
                         f"{user_info.media_count} posts")
            except Exception as e:
                self.log(f"[ERROR] Could not find user @{username}: {e}")
                self.running = False
                return

            self._check_state()

            # fetch recent posts
            self.log(f"[~] Fetching up to {num_posts} recent posts...")
            self.set_status("Fetching posts...")
            try:
                amount = user_info.media_count if like_all else num_posts
                medias = self.cl.user_medias(user_id, amount=amount)
            except Exception as e:
                self.log(f"[ERROR] Could not fetch posts: {e}")
                self.running = False
                return

            if not medias:
                self.log("[!] No posts found for this user.")
                self.running = False
                return

            if like_all:
                self.log(f"[+] Retrieved {len(medias)} posts. Liking all in randomized batches...")
            else:
                self.log(f"[+] Retrieved {len(medias)} posts. Starting likes...")
            self.set_status("Liking posts...")

            batch_threshold = random.randint(5, 15) if like_all else None

            for i, media in enumerate(medias):
                self._check_state()
                self.set_status(f"Processing post {i+1}/{len(medias)}")

                post_url = f"https://www.instagram.com/p/{media.code}/"
                media_id = self.cl.media_id(media.pk)

                # show current post image in GUI
                try:
                    thumb = str(media.thumbnail_url) if media.thumbnail_url else None
                    if not thumb and media.resources:
                        thumb = str(media.resources[0].thumbnail_url)
                    caption_text = (media.caption_text or "")[:80]
                    if thumb:
                        self.set_image(thumb, caption_text)
                except Exception:
                    pass

                # check if already liked
                if media.has_liked:
                    self.log(f"[~] Post {i+1} already liked. Skipping. — {post_url}")
                    continue

                try:
                    self.cl.media_like(media_id)
                    self.liked_count += 1
                    sm.save_liked_link(post_url)
                    self.log(f"[♥] Liked post {self.liked_count} — {post_url}")
                except FeedbackRequired:
                    self.log("[!] Instagram feedback warning — slowing down.")
                    time.sleep(30)
                except PleaseWaitFewMinutes:
                    self.log("[!] Rate limited! Waiting 60 seconds...")
                    time.sleep(60)
                except Exception as e:
                    self.log(f"[!] Failed to like post {i+1}: {e}")

                self._delay(2.5)

                # extra randomized cooldown between batches when liking all posts
                if like_all and (i + 1) < len(medias):
                    if (i + 1) % batch_threshold == 0:
                        cool = random.uniform(20, 60)
                        self.log(f"[~] Cooling down for {cool:.1f}s to mimic human behaviour...")
                        end = time.time() + cool
                        while time.time() < end:
                            self._check_state()
                            time.sleep(0.5)
                        batch_threshold = random.randint(5, 15)

            self.log(f"[✓] Done! Liked {self.liked_count} out of {len(medias)} posts.")
            self.set_status("Finished")

        except InterruptedError:
            self.log(f"[■] Stopped by user. Liked {self.liked_count} posts.")
            self.set_status("Stopped")
        except Exception as e:
            self.log(f"[ERROR] {e}")
            traceback.print_exc()
            self.set_status("Error")
        finally:
            self.running = False

    def _extract_username(self, input_str: str) -> str:
        """Extract username from URL or raw text."""
        input_str = input_str.strip().rstrip("/")
        if "instagram.com" in input_str:
            parts = input_str.split("/")
            # filter empty strings and find the username segment
            for part in reversed(parts):
                if part and part not in ("www.instagram.com", "instagram.com", "https:", "http:", ""):
                    return part
        return input_str.lstrip("@")

    # ── control ───────────────────────────────────────────────
    def stop(self):
        self.running = False
        self.paused = False
        self.log("[■] Stop signal sent.")

    def pause(self):
        self.paused = True
        self.log("[⏸] Paused.")
        self.set_status("Paused")

    def resume(self):
        self.paused = False
        self.log("[▶] Resumed.")

    def logout(self):
        if self.cl:
            try:
                self.cl.logout()
                self.log("[+] Logged out.")
            except Exception:
                pass


class _BotLogHandler(logging.Handler):
    """Routes Python logging messages to the bot's log callback."""
    def __init__(self, log_callback):
        super().__init__()
        self._log = log_callback

    def emit(self, record):
        try:
            msg = self.format(record)
            # truncate very long messages (base64 blobs, etc.)
            if len(msg) > 300:
                msg = msg[:297] + "..."
            self._log(msg)
        except Exception:
            pass
