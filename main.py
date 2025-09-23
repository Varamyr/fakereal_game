import os
import sys
import json
import random
import pygame
from datetime import datetime
from PIL import Image, ExifTags

# -----------------------------
# Config
# -----------------------------
CANVAS_WIDTH = 1600
CANVAS_HEIGHT = 900
TOP_BAR_H = 80
FPS = 60
SESSION_TIME_SEC = 60.0
PASS_BTN_SIZE = (320, 110)
MIDDLE_GAP = PASS_BTN_SIZE[0] + 60  # space between left/right images so PASS fits in the middle
DATA_DIRNAME = "data"
LEADERBOARD_FILE = "leaderboard.json"
# Use separate leaderboards per difficulty
LEADERBOARD_FILE_NORMAL = "leaderboard_normal.json"
LEADERBOARD_FILE_HARD = "leaderboard_hard.json"
ALLOWED_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}

# Toggle: if True, real and fake can come from different random categories
RANDOM_CATEGORY = True

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GRAY = (160, 160, 160)
DARK_GRAY = (50, 50, 50)
GREEN = (50, 180, 90)
RED = (200, 60, 60)
YELLOW = (245, 220, 40)
SEMI_BLACK = (0, 0, 0, 170)


# -----------------------------
# Helpers
# -----------------------------

def resource_path(*parts: str) -> str:
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, *parts)


def load_leaderboard(path: str):
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def save_leaderboard(path: str, entries: list):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Failed to save leaderboard: {e}")


def index_dataset(data_root: str):
    real_root = os.path.join(data_root, "real")
    fake_root = os.path.join(data_root, "fake")

    def list_categories(root):
        cats = []
        if not os.path.isdir(root):
            return cats
        for name in os.listdir(root):
            p = os.path.join(root, name)
            if os.path.isdir(p):
                cats.append(name)
        return cats

    def list_images(folder):
        files = []
        if not os.path.isdir(folder):
            return files
        for name in os.listdir(folder):
            lower = name.lower()
            _, ext = os.path.splitext(lower)
            if ext in ALLOWED_EXTS:
                files.append(os.path.join(folder, name))
        return files

    real_cats = set(list_categories(real_root))
    fake_cats = set(list_categories(fake_root))
    cats = sorted(list(real_cats.intersection(fake_cats)))

    real_map = {}
    fake_map = {}

    for c in cats:
        r_list = list_images(os.path.join(real_root, c))
        f_list = list_images(os.path.join(fake_root, c))
        if r_list and f_list:
            real_map[c] = r_list
            fake_map[c] = f_list

    return real_map, fake_map


def scale_to_cover(image: pygame.Surface, target_w: int, target_h: int) -> pygame.Surface:
    iw, ih = image.get_width(), image.get_height()
    if iw == 0 or ih == 0:
        return pygame.Surface((target_w, target_h)).convert()
    scale = max(target_w / iw, target_h / ih)
    new_w, new_h = int(iw * scale), int(ih * scale)
    scaled = pygame.transform.smoothscale(image, (new_w, new_h))
    # Create target surface and blit centered (crop overflow)
    target = pygame.Surface((target_w, target_h)).convert()
    x = (target_w - new_w) // 2
    y = (target_h - new_h) // 2
    target.blit(scaled, (x, y))
    return target


def scale_to_fill_width_centered(image: pygame.Surface, target_w: int, target_h: int) -> pygame.Surface:
    """Scale image so it fills the target width, then vertically center within target_h.
    Crops if taller than target_h; leaves letterbox if shorter.
    """
    iw, ih = image.get_width(), image.get_height()
    if iw == 0 or ih == 0:
        return pygame.Surface((target_w, target_h), pygame.SRCALPHA).convert_alpha()
    scale = target_w / iw
    new_w = target_w
    new_h = max(1, int(ih * scale))
    scaled = pygame.transform.smoothscale(image, (new_w, new_h))
    target = pygame.Surface((target_w, target_h), pygame.SRCALPHA).convert_alpha()
    y = (target_h - new_h) // 2
    target.blit(scaled, (0, y))
    return target


# -----------------------------
# Game
# -----------------------------
class FakeRealGame:
    def __init__(self):
        pygame.init()
        # Init audio mixer for music/SFX
        try:
            pygame.mixer.init()
        except Exception as e:
            print(f"Mixer init failed: {e}")
        pygame.display.set_caption("Fake vs Real")
        self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        self.screen_w, self.screen_h = self.screen.get_size()

        self.canvas = pygame.Surface((CANVAS_WIDTH, CANVAS_HEIGHT)).convert()

        # Preload audio assets
        self.music_path = resource_path("assets", "background_music.mp3")
        self.music_idle_path = resource_path("assets", "background_music_2.mp3")
        try:
            self.snd_right = pygame.mixer.Sound(resource_path("assets", "right.mp3"))
            self.snd_wrong = pygame.mixer.Sound(resource_path("assets", "wrong.mp3"))
        except Exception as e:
            self.snd_right = None
            self.snd_wrong = None
            print(f"Failed to load SFX: {e}")

        # Fonts
        font_path = resource_path("assets", "grand9k_pixel.ttf")
        try:
            if os.path.exists(font_path):
                self.font_small = pygame.font.Font(font_path, 20)
                self.font = pygame.font.Font(font_path, 22)
                self.font_large = pygame.font.Font(font_path, 24)
                self.font_xlarge = pygame.font.Font(font_path, 36)
            else:
                print(f"Custom font not found at {font_path}, using default font.")
                self.font_small = pygame.font.Font(None, 36)
                self.font = pygame.font.Font(None, 48)
                self.font_large = pygame.font.Font(None, 96)
                self.font_xlarge = pygame.font.Font(None, 180)
        except Exception as e:
            print(f"Failed to load custom font: {e}")
            self.font_small = pygame.font.Font(None, 36)
            self.font = pygame.font.Font(None, 48)
            self.font_large = pygame.font.Font(None, 96)
            self.font_xlarge = pygame.font.Font(None, 180)

        # Preload logos for intro
        try:
            self.logo_main = pygame.image.load(resource_path("assets", "game_logo.png")).convert_alpha()
            self.logo_imp = pygame.image.load(resource_path("assets", "imp_logo.png")).convert_alpha()
        except Exception as e:
            print(f"Logo load failed: {e}")
            self.logo_main = None
            self.logo_imp = None

        # Layout rects on canvas
        left_w = (CANVAS_WIDTH - MIDDLE_GAP) // 2
        play_h = CANVAS_HEIGHT - TOP_BAR_H
        self.left_rect = pygame.Rect(0, TOP_BAR_H, left_w, play_h)
        self.right_rect = pygame.Rect(left_w + MIDDLE_GAP, TOP_BAR_H, left_w, play_h)
        self.pass_rect = pygame.Rect(0, 0, PASS_BTN_SIZE[0], PASS_BTN_SIZE[1])
        # center PASS in the middle gap and vertically within the playable area
        self.pass_rect.center = (CANVAS_WIDTH // 2, TOP_BAR_H + play_h // 2)

        # Start prompt rectangle (centered)
        prompt_w, prompt_h = 1400, 800
        self.start_prompt_rect = pygame.Rect(0, 0, prompt_w, prompt_h)
        self.start_prompt_rect.center = (CANVAS_WIDTH // 2, CANVAS_HEIGHT // 2)

        # Difficulty prompt rectangles
        self.diff_prompt_rect = pygame.Rect(0, 0, 1200, 500)
        self.diff_prompt_rect.center = (CANVAS_WIDTH // 2, CANVAS_HEIGHT // 2)
        btn_w, btn_h = 460, 160
        gap = 80
        bx_left = self.diff_prompt_rect.centerx - (btn_w + gap // 2)
        bx_right = self.diff_prompt_rect.centerx + (gap // 2)
        by = self.diff_prompt_rect.centery + 40
        self.diff_normal_rect = pygame.Rect(bx_left, by, btn_w, btn_h)
        self.diff_hard_rect = pygame.Rect(bx_right, by, btn_w, btn_h)

        # Rules text
        self.start_rules = [
            "Fake/Real game:",
            "Una delle due foto mostrate non è reale. ",
            "Scegli quella REALE per fare punti!",
            "Se sbagli perdi punti, quindi se sei indeciso vai alla PROSSIMA.",
            "",
            "** Comandi: **",
            "- Premi Destra o Sinistra (o clicca sull'immagine) per selezionare l'immagine reale",
            "- Premi Su o Giù (o clicca su PROSSIMA) per saltare il round.",
            "**************",
            "",
            "- Ottieni +1 punti se indovini, -0.5 se non indovini e 0 punti se salti il round.",
            "Prova a scalare la classifica!",
            "",
            "",
            "Per iniziare, premi Invio/Spazio o clicca qui sopra.",
        ]

        # Dataset
        self.data_root = resource_path(DATA_DIRNAME)
        self.real_map, self.fake_map = index_dataset(self.data_root)
        self.categories = [c for c in self.real_map.keys() if c in self.fake_map and self.real_map[c] and self.fake_map[c]]

        if not self.categories:
            print("No valid dataset found in ./data with matching categories under real/ and fake/.")
            print("Exiting.")
            pygame.quit()
            sys.exit(1)

        # Game state
        # start with intro -> start_prompt -> difficulty_prompt -> countdown -> playing -> enter_name -> leaderboard
        self.state = "intro"
        self.intro_start_ms = pygame.time.get_ticks()
        self.INTRO_FADE_MS = 1500
        self.INTRO_HOLD_MS = 1500
        self.score = 0.0
        self.round_index = 0
        self.session_start_ms = 0
        self.time_left = SESSION_TIME_SEC
        self.player_name = ""
        self.just_qualified = False
        self.latest_score = 0.0
        # Difficulty toggle (session-level): default from global
        self.random_category = RANDOM_CATEGORY
        self.last_action_time = 0  # Cooldown for choices
        self.music_mode = None  # 'idle' or 'game'

        # current round
        self.left_image = None
        self.right_image = None
        self.left_is_real = False
        self.left_label = ""
        self.right_label = ""

        self.clock = pygame.time.Clock()
        self.running = True
        self.countdown_sequence = [("3", 800), ("2", 800), ("1", 800), ("GO", 600)]  # in ms

        # Leaderboard: default to NORMAL until a difficulty is chosen
        self.leaderboard_path = resource_path(LEADERBOARD_FILE_NORMAL)

        # Start idle music on intro
        try:
            self.set_music("idle")
        except Exception:
            pass

    # -------------------------
    # Music control
    # -------------------------
    def set_music(self, mode: str):
        if getattr(self, 'music_mode', None) == mode:
            return
        try:
            path = self.music_path if mode == 'game' else self.music_idle_path
            if os.path.exists(path):
                pygame.mixer.music.load(path)
                pygame.mixer.music.play(-1)
                self.music_mode = mode
            else:
                print(f"Music file not found: {path}")
        except Exception as e:
            print(f"Failed to switch music: {e}")

    # -------------------------
    # Dataset and rounds
    # -------------------------
    def pick_random_paths(self):
        if self.random_category:
            real_cat = random.choice(self.categories)
            fake_cat = random.choice(self.categories)
            real_path = random.choice(self.real_map[real_cat])
            fake_path = random.choice(self.fake_map[fake_cat])
        else:
            cat = random.choice(self.categories)
            real_path = random.choice(self.real_map[cat])
            fake_path = random.choice(self.fake_map[cat])
        return real_path, fake_path

    def load_image_scaled(self, path: str, rect: pygame.Rect):
        try:
            # Use Pillow to open, handle EXIF orientation, then convert to Pygame surface
            img_pil = Image.open(path)

            try:
                for orientation in ExifTags.TAGS.keys():
                    if ExifTags.TAGS[orientation] == 'Orientation':
                        break
                
                exif = img_pil._getexif()

                if exif is not None and orientation in exif:
                    if exif[orientation] == 3:
                        img_pil = img_pil.rotate(180, expand=True)
                    elif exif[orientation] == 6:
                        img_pil = img_pil.rotate(270, expand=True)
                    elif exif[orientation] == 8:
                        img_pil = img_pil.rotate(90, expand=True)
            except (AttributeError, KeyError, IndexError):
                # cases: image don't have getexif
                pass

            # Convert PIL image to Pygame surface
            mode = img_pil.mode
            size = img_pil.size
            data = img_pil.tobytes()

            if mode == 'RGB':
                img = pygame.image.fromstring(data, size, mode)
            elif mode == 'RGBA':
                img = pygame.image.fromstring(data, size, mode)
            else: # L, P, etc. Convert to RGB to be safe.
                img_pil = img_pil.convert('RGB')
                data = img_pil.tobytes()
                img = pygame.image.fromstring(data, size, 'RGB')

            if img.get_alpha() is not None:
                img = img.convert_alpha()
            else:
                img = img.convert()
            return scale_to_fill_width_centered(img, rect.width, rect.height)
        except Exception as e:
            print(f"Failed to load image {path}: {e}")
            # Fallback placeholder
            surf = pygame.Surface((rect.width, rect.height))
            surf.fill(DARK_GRAY)
            return surf

    def load_new_pair(self):
        real_path, fake_path = self.pick_random_paths()
        # Randomly assign sides
        if random.random() < 0.5:
            left_path, right_path = real_path, fake_path
            self.left_is_real = True
        else:
            left_path, right_path = fake_path, real_path
            self.left_is_real = False
        self.left_image = self.load_image_scaled(left_path, self.left_rect)
        self.right_image = self.load_image_scaled(right_path, self.right_rect)
        # Store labels for debugging (use filenames)
        self.left_label = os.path.basename(left_path)
        self.right_label = os.path.basename(right_path)

    # -------------------------
    # Drawing helpers
    # -------------------------
    def draw_top_bar(self):
        # Background bar
        pygame.draw.rect(self.canvas, BLACK, pygame.Rect(0, 0, CANVAS_WIDTH, TOP_BAR_H))
        # Score
        score_text = f"Score: {self.score:.1f}"
        score_surf = self.font.render(score_text, True, WHITE)
        self.canvas.blit(score_surf, (20, (TOP_BAR_H - score_surf.get_height()) // 2))
        # Timer
        time_text = f"Time: {int(max(0, self.time_left))}s"
        time_surf = self.font.render(time_text, True, YELLOW if self.time_left <= 10 else WHITE)
        self.canvas.blit(time_surf, (CANVAS_WIDTH - time_surf.get_width() - 20, (TOP_BAR_H - time_surf.get_height()) // 2))

    def draw_pass_button(self, hover: bool):
        color = (230, 230, 230) if hover else (210, 210, 210)
        border = (90, 90, 90)
        pygame.draw.rect(self.canvas, color, self.pass_rect, border_radius=16)
        pygame.draw.rect(self.canvas, border, self.pass_rect, width=3, border_radius=16)
        label = self.font_large.render("PASS", True, BLACK)
        self.canvas.blit(label, (self.pass_rect.centerx - label.get_width() // 2, self.pass_rect.centery - label.get_height() // 2))

    def draw_center_message(self, text: str, subtext: str | None = None, color=WHITE):
        msg = self.font_large.render(text, True, color)
        self.canvas.blit(msg, (CANVAS_WIDTH // 2 - msg.get_width() // 2, CANVAS_HEIGHT // 2 - msg.get_height() // 2))
        if subtext:
            sub = self.font.render(subtext, True, color)
            self.canvas.blit(sub, (CANVAS_WIDTH // 2 - sub.get_width() // 2, CANVAS_HEIGHT // 2 + msg.get_height() // 2 + 20))

    def draw_text_center(self, text: str, y: int, color=WHITE, font=None):
        f = font or self.font
        surf = f.render(text, True, color)
        self.canvas.blit(surf, (CANVAS_WIDTH // 2 - surf.get_width() // 2, y))

    def draw_image_label(self, rect: pygame.Rect, text: str):
        if not text:
            return
        label = self.font_small.render(text, True, WHITE)
        pad_x, pad_y = 8, 4
        bg_w, bg_h = label.get_width() + pad_x * 2, label.get_height() + pad_y * 2
        bg_x = rect.centerx - bg_w // 2
        bg_y = rect.bottom - bg_h - 10
        bg = pygame.Surface((bg_w, bg_h), pygame.SRCALPHA)
        bg.fill((0, 0, 0, 160))
        self.canvas.blit(bg, (bg_x, bg_y))
        self.canvas.blit(label, (bg_x + pad_x, bg_y + pad_y))

    # -------------------------
    # Input mapping
    # -------------------------
    def canvas_target_rect_on_screen(self):
        scale = min(self.screen_w / CANVAS_WIDTH, self.screen_h / CANVAS_HEIGHT)
        w = int(CANVAS_WIDTH * scale)
        h = int(CANVAS_HEIGHT * scale)
        x = (self.screen_w - w) // 2
        y = (self.screen_h - h) // 2
        return pygame.Rect(x, y, w, h)

    def screen_to_canvas(self, sx: int, sy: int):
        target = self.canvas_target_rect_on_screen()
        if not target.collidepoint(sx, sy):
            return None
        scale_x = CANVAS_WIDTH / target.width
        scale_y = CANVAS_HEIGHT / target.height
        cx = int((sx - target.x) * scale_x)
        cy = int((sy - target.y) * scale_y)
        return cx, cy

    # -------------------------
    # State transitions
    # -------------------------
    def start_countdown(self):
        self.state = "countdown"
        self.countdown_index = 0
        self.countdown_phase_start = pygame.time.get_ticks()
        # Load first pair *after* difficulty is set
        self.load_new_pair()
        # Start background music (loop)
        try:
            self.set_music('game')
        except Exception:
            pass

    def start_play(self):
        self.state = "playing"
        self.score = 0.0
        self.round_index = 0
        self.session_start_ms = pygame.time.get_ticks()
        self.time_left = SESSION_TIME_SEC
        # Ensure we have a pair ready
        if self.left_image is None or self.right_image is None:
            self.load_new_pair()

    def end_play(self):
        self.latest_score = self.score
        self.state = "enter_name"
        self.player_name = ""
        # Switch back to idle music when session ends
        try:
            self.set_music('idle')
        except Exception:
            pass

    # -------------------------
    # Leaderboard logic
    # -------------------------
    def update_leaderboard(self):
        entries = load_leaderboard(self.leaderboard_path)
        pre_sorted = sorted(entries, key=lambda e: e.get("score", 0), reverse=True)
        # Check if current score would qualify
        qualifies = len(pre_sorted) < 10 or (self.latest_score > pre_sorted[-1].get("score", -1e9))
        self.just_qualified = qualifies
        new_entry = {
            "name": self.player_name or "Player",
            "score": float(self.latest_score),
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        entries.append(new_entry)
        entries = sorted(entries, key=lambda e: e.get("score", 0), reverse=True)[:10]
        save_leaderboard(self.leaderboard_path, entries)
        return entries

    # -------------------------
    # Event handling per state
    # -------------------------
    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                # Skip intro on key
                if self.state == "intro" and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                    self.state = "start_prompt"
                    continue
                # Close start prompt with Enter or Space -> go to difficulty selection
                if self.state == "start_prompt":
                    if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                        self.state = "difficulty_prompt"
                    continue

                if self.state == "difficulty_prompt":
                    # Keyboard shortcuts for difficulty selection
                    if event.key in (pygame.K_n, pygame.K_LEFT):  # NORMALE
                        self.random_category = False
                        self.leaderboard_path = resource_path(LEADERBOARD_FILE_NORMAL)
                        self.start_countdown()
                    elif event.key in (pygame.K_d, pygame.K_RIGHT):  # DIFFICILE
                        self.random_category = True
                        self.leaderboard_path = resource_path(LEADERBOARD_FILE_HARD)
                        self.start_countdown()
                    continue

                if self.state == "countdown":
                    # optional: skip countdown? Not requested; keep it running.
                    pass
                elif self.state == "playing":
                    now = pygame.time.get_ticks()
                    if now - self.last_action_time < 500:
                        continue
                    # Keyboard controls: left/right choose, up/down pass
                    if event.key == pygame.K_LEFT:
                        self.handle_guess(is_left=True)
                        self.last_action_time = now
                    elif event.key == pygame.K_RIGHT:
                        self.handle_guess(is_left=False)
                        self.last_action_time = now
                    elif event.key in (pygame.K_UP, pygame.K_DOWN):
                        # Pass
                        self.round_index += 1
                        self.load_new_pair()
                        self.last_action_time = now
                    pass
                elif self.state == "enter_name":
                    if event.key == pygame.K_RETURN:
                        # commit name and move to leaderboard
                        self.leaderboard_entries = self.update_leaderboard()
                        self.state = "leaderboard"
                    elif event.key == pygame.K_BACKSPACE:
                        self.player_name = self.player_name[:-1]
                    else:
                        if len(self.player_name) < 24:
                            ch = event.unicode
                            if ch.isprintable():
                                self.player_name += ch
                elif self.state == "leaderboard":
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        # Restart flow: show rules then difficulty again
                        self.state = "start_prompt"

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                # Skip intro on click
                if self.state == "intro":
                    self.state = "start_prompt"
                    continue
                m = self.screen_to_canvas(*event.pos)
                if m is None:
                    continue
                mx, my = m
                # Click to close start prompt -> open difficulty prompt
                if self.state == "start_prompt" and self.start_prompt_rect.collidepoint(mx, my):
                    self.state = "difficulty_prompt"
                    continue
                # Click on difficulty buttons
                if self.state == "difficulty_prompt":
                    if self.diff_normal_rect.collidepoint(mx, my):
                        self.random_category = False
                        self.leaderboard_path = resource_path(LEADERBOARD_FILE_NORMAL)
                        self.start_countdown()
                        continue
                    if self.diff_hard_rect.collidepoint(mx, my):
                        self.random_category = True
                        self.leaderboard_path = resource_path(LEADERBOARD_FILE_HARD)
                        self.start_countdown()
                        continue
                if self.state == "playing":
                    now = pygame.time.get_ticks()
                    if now - self.last_action_time < 500:
                        continue
                    if self.pass_rect.collidepoint(mx, my):
                        # Pass
                        self.round_index += 1
                        self.load_new_pair()
                        self.last_action_time = now
                    elif self.left_rect.collidepoint(mx, my):
                        self.handle_guess(is_left=True)
                        self.last_action_time = now
                    elif self.right_rect.collidepoint(mx, my):
                        self.handle_guess(is_left=False)
                        self.last_action_time = now

    def handle_guess(self, is_left: bool):
        correct = (is_left and self.left_is_real) or ((not is_left) and (not self.left_is_real))
        if correct:
            self.score += 1.0
            if getattr(self, 'snd_right', None):
                try:
                    self.snd_right.play()
                except Exception:
                    pass
        else:
            self.score -= 0.5
            if getattr(self, 'snd_wrong', None):
                try:
                    self.snd_wrong.play()
                except Exception:
                    pass
        self.round_index += 1
        self.load_new_pair()

    # -------------------------
    # Update & Render per state
    # -------------------------
    def update(self, dt_ms: int):
        if self.state == "intro":
            # Transition to start prompt after animation
            total = self.INTRO_FADE_MS * 2 + self.INTRO_HOLD_MS
            if pygame.time.get_ticks() - self.intro_start_ms >= total:
                self.state = "start_prompt"
                # Ensure idle music after intro
                try:
                    self.set_music('idle')
                except Exception:
                    pass
                return
        if self.state == "countdown":
            now = pygame.time.get_ticks()
            label, dur = self.countdown_sequence[self.countdown_index]
            if now - self.countdown_phase_start >= dur:
                self.countdown_index += 1
                self.countdown_phase_start = now
                if self.countdown_index >= len(self.countdown_sequence):
                    self.start_play()
        elif self.state == "playing":
            elapsed = (pygame.time.get_ticks() - self.session_start_ms) / 1000.0
            self.time_left = max(0.0, SESSION_TIME_SEC - elapsed)
            if self.time_left <= 0:
                self.end_play()

    def render(self):
        # Clear canvas
        self.canvas.fill((25, 25, 25))

        # Intro animation (black background with fading logos)
        if self.state == "intro":
            self.canvas.fill(BLACK)
            # Compute alpha
            t = pygame.time.get_ticks() - self.intro_start_ms
            fade = self.INTRO_FADE_MS
            hold = self.INTRO_HOLD_MS
            total = fade * 2 + hold
            if t < fade:
                alpha = int(255 * (t / fade))
            elif t < fade + hold:
                alpha = 255
            elif t < total:
                alpha = int(255 * (1 - (t - fade - hold) / fade))
            else:
                alpha = 0

            if self.logo_main is not None:
                # Determine sizes to fit
                max_main_w = int(CANVAS_WIDTH * 0.7)
                max_imp_w = int(CANVAS_WIDTH * 0.35)
                gap = 24
                # Start with requested widths
                lm_w, lm_h = self.logo_main.get_size()
                scale_main = min(1.0, max_main_w / max(1, lm_w))
                main_w = int(lm_w * scale_main)
                main_h = int(lm_h * scale_main)

                if self.logo_imp is not None:
                    li_w, li_h = self.logo_imp.get_size()
                    scale_imp = 0.5
                    imp_w = int(li_w * scale_imp)
                    imp_h = int(li_h * scale_imp)
                else:
                    imp_w = imp_h = 0

                # If total too tall, scale both down
                total_h = main_h + (gap if imp_h else 0) + imp_h
                avail_h = int(CANVAS_HEIGHT * 0.7)
                if total_h > avail_h and total_h > 0:
                    k = avail_h / total_h
                    main_w = int(main_w * k)
                    main_h = int(main_h * k)
                    imp_w = int(imp_w * k)
                    imp_h = int(imp_h * k)

                layer = pygame.Surface((CANVAS_WIDTH, CANVAS_HEIGHT), pygame.SRCALPHA)
                # Blit main logo centered
                x_main = CANVAS_WIDTH // 2 - main_w // 2
                y_main = CANVAS_HEIGHT // 2 - (main_h + (gap if imp_h else 0) + imp_h) // 2
                main_scaled = pygame.transform.smoothscale(self.logo_main, (max(1, main_w), max(1, main_h)))
                layer.blit(main_scaled, (x_main, y_main))
                # Blit imp logo under
                if self.logo_imp is not None and imp_w and imp_h:
                    x_imp = CANVAS_WIDTH // 2 - imp_w // 2
                    y_imp = y_main + main_h + gap
                    imp_scaled = pygame.transform.smoothscale(self.logo_imp, (max(1, imp_w), max(1, imp_h)))
                    layer.blit(imp_scaled, (x_imp, y_imp))
                layer.set_alpha(max(0, min(255, alpha)))
                self.canvas.blit(layer, (0, 0))
            # Note: do not return here; let the common blit/flip run below

        # Top bar
        if self.state != "intro":
            self.draw_top_bar()

        # Draw images only during playing (hide during countdown)
        if self.state == "playing":
            if self.left_image is not None:
                self.canvas.blit(self.left_image, self.left_rect.topleft)
            if self.right_image is not None:
                self.canvas.blit(self.right_image, self.right_rect.topleft)

        # Pass button (only when playing)
        mouse_pos = pygame.mouse.get_pos()
        cm = self.screen_to_canvas(*mouse_pos)
        hover = False
        if cm is not None:
            hover = self.pass_rect.collidepoint(*cm)
        if self.state == "playing":
            self.draw_pass_button(hover)

        # Debug labels under images
        if self.state == "playing":
            self.draw_image_label(self.left_rect, getattr(self, "left_label", ""))
            self.draw_image_label(self.right_rect, getattr(self, "right_label", ""))

        if self.state == "countdown":
            # Overlay countdown
            overlay = pygame.Surface((CANVAS_WIDTH, CANVAS_HEIGHT), pygame.SRCALPHA)
            overlay.fill(SEMI_BLACK)
            self.canvas.blit(overlay, (0, 0))
            label, _ = self.countdown_sequence[self.countdown_index]
            color = GREEN if label == "GO" else WHITE
            surf = self.font_xlarge.render(label, True, color)
            self.canvas.blit(surf, (CANVAS_WIDTH // 2 - surf.get_width() // 2, CANVAS_HEIGHT // 2 - surf.get_height() // 2))

        # Start prompt rendering (fancier panel)
        if self.state == "start_prompt":
            # Dim background
            overlay = pygame.Surface((CANVAS_WIDTH, CANVAS_HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 200))
            self.canvas.blit(overlay, (0, 0))
            # Shadow
            shadow = self.start_prompt_rect.copy()
            shadow.move_ip(8, 8)
            pygame.draw.rect(self.canvas, (0, 0, 0, 120), shadow, border_radius=18)
            # Panel
            pygame.draw.rect(self.canvas, (245, 245, 245), self.start_prompt_rect, border_radius=18)
            pygame.draw.rect(self.canvas, (30, 30, 30), self.start_prompt_rect, width=4, border_radius=18)
            # Accent header
            header = pygame.Rect(self.start_prompt_rect.x, self.start_prompt_rect.y, self.start_prompt_rect.width, 64)
            pygame.draw.rect(self.canvas, (29, 41, 81), header, border_radius=18)
            pygame.draw.line(self.canvas, (49, 61, 101), (self.start_prompt_rect.x + 12, header.bottom - 4), (self.start_prompt_rect.right - 12, header.bottom - 4), 3)
            # Render rules lines (unchanged text)
            y = self.start_prompt_rect.y + 84
            for i, line in enumerate(self.start_rules):
                font = self.font_large if i == 0 else self.font
                color = BLACK if i == 0 else DARK_GRAY
                surf = font.render(line, True, color)
                x = self.start_prompt_rect.x + (self.start_prompt_rect.width - surf.get_width()) // 2
                self.canvas.blit(surf, (x, y))
                y += surf.get_height() + (16 if i == 0 else 12)

        # Difficulty prompt rendering (fancier)
        if self.state == "difficulty_prompt":
            overlay = pygame.Surface((CANVAS_WIDTH, CANVAS_HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 200))
            self.canvas.blit(overlay, (0, 0))

            # Shadow + Panel
            shadow = self.diff_prompt_rect.copy()
            shadow.move_ip(8, 8)
            pygame.draw.rect(self.canvas, (0, 0, 0, 120), shadow, border_radius=18)
            pygame.draw.rect(self.canvas, (245, 245, 245), self.diff_prompt_rect, border_radius=18)
            pygame.draw.rect(self.canvas, (30, 30, 30), self.diff_prompt_rect, width=4, border_radius=18)

            # Title and description (text unchanged)
            title = self.font_large.render("Seleziona Modalità", True, BLACK)
            tx = self.diff_prompt_rect.centerx - title.get_width() // 2
            ty = self.diff_prompt_rect.y + 30
            self.canvas.blit(title, (tx, ty))

            desc_lines = [
                "Modalità 1: le due foto appartengono alla stessa categoria (più difficile).",
                "Modalità 2: le due foto appartengono a categorie diverse.",
                "Clicca una modalità per iniziare.",
            ]
            y = ty + title.get_height() + 16
            for line in desc_lines:
                s = self.font.render(line, True, DARK_GRAY)
                x = self.diff_prompt_rect.centerx - s.get_width() // 2
                self.canvas.blit(s, (x, y))
                y += s.get_height() + 6

            # Buttons with hover
            def draw_btn(rect: pygame.Rect, text: str):
                mouse_pos = pygame.mouse.get_pos()
                cm = self.screen_to_canvas(*mouse_pos)
                hovered = bool(cm and rect.collidepoint(*cm))
                btn_color = (235, 235, 235) if hovered else (220, 220, 220)
                pygame.draw.rect(self.canvas, btn_color, rect, border_radius=16)
                pygame.draw.rect(self.canvas, BLACK, rect, width=3, border_radius=16)
                t = self.font_large.render(text, True, BLACK)
                self.canvas.blit(t, (rect.centerx - t.get_width() // 2, rect.centery - t.get_height() // 2))

            draw_btn(self.diff_normal_rect, "Modalità 1")
            draw_btn(self.diff_hard_rect, "Modalità 2")

        elif self.state == "enter_name":
            # Result screen and name input (improved visuals)
            self.draw_text_center("Il tempo è finito!", 150, color=YELLOW, font=self.font_large)
            self.draw_text_center(f"Il tuo punteggio è: {self.latest_score:.1f}", 230, color=WHITE, font=self.font_large)
            self.draw_text_center("Digita il tuo nome e premi INVIO:", 320, color=WHITE)
            # Input panel with shadow
            panel = pygame.Rect(0, 0, 800, 160)
            panel.center = (CANVAS_WIDTH // 2, 500)
            shadow = panel.copy(); shadow.move_ip(8, 8)
            pygame.draw.rect(self.canvas, (0, 0, 0, 120), shadow, border_radius=14)
            pygame.draw.rect(self.canvas, (245, 245, 245), panel, border_radius=14)
            pygame.draw.rect(self.canvas, (30, 30, 30), panel, width=4, border_radius=14)
            # Input box inside
            box = pygame.Rect(panel.x + 40, panel.centery - 40, panel.width - 80, 80)
            pygame.draw.rect(self.canvas, WHITE, box, border_radius=10)
            pygame.draw.rect(self.canvas, BLACK, box, width=3, border_radius=10)
            name_display = self.player_name if (pygame.time.get_ticks() // 500) % 2 == 0 else self.player_name + "|"
            txt = self.font.render(name_display, True, BLACK)
            self.canvas.blit(txt, (box.x + 16, box.y + (box.height - txt.get_height()) // 2))
            # Hint
            self.draw_text_center("(Usa Backspace per correggere)", panel.bottom + 20, color=GRAY)

        elif self.state == "leaderboard":
            difficolta = "Modalità 2" if self.random_category else "Modalità 1"
            self.draw_text_center(f"Classifica ({difficolta})", 100, color=YELLOW, font=self.font_large)
            entries = getattr(self, "leaderboard_entries", [])
            # Fancy list: only position and name, with alternating row shades
            y = 200
            rank = 1
            for e in entries:
                name = e.get("name", "?")
                score = e.get("score", "err")
                row = pygame.Rect(CANVAS_WIDTH // 2 - 500, y - 8, 1000, 56)
                shade = (245, 245, 245) if rank % 2 == 0 else (230, 230, 230)
                pygame.draw.rect(self.canvas, shade, row, border_radius=10)
                pygame.draw.rect(self.canvas, (200, 200, 200), row, width=2, border_radius=10)
                line = f"{rank:2d}.  {name[:32]} : {score}"
                s = self.font.render(line, True, BLACK)
                self.canvas.blit(s, (row.x + 20, row.y + (row.height - s.get_height()) // 2))
                y += 64
                rank += 1
            if self.just_qualified:
                self.draw_text_center("Congratulazioni! Sei arrivato in Top 10!", y + 30, color=GREEN, font=self.font)
            self.draw_text_center("Premi Invio per giocare ancora, oppure Esc per uscire.", CANVAS_HEIGHT - 80, color=GRAY, font=self.font)

        # Blit canvas to screen (letterboxed)
        target = self.canvas_target_rect_on_screen()
        scaled = pygame.transform.smoothscale(self.canvas, (target.width, target.height))
        self.screen.fill(BLACK)
        self.screen.blit(scaled, target.topleft)
        pygame.display.flip()

    # -------------------------
    # Main loop
    # -------------------------
    def run(self):
        while self.running:
            dt = self.clock.tick(FPS)
            self.handle_events()
            self.update(dt)
            self.render()
        pygame.quit()


if __name__ == "__main__":
    game = FakeRealGame()
    game.run()
