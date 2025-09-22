import os
import sys
import json
import random
import pygame
from datetime import datetime

# -----------------------------
# Config
# -----------------------------
CANVAS_WIDTH = 1600
CANVAS_HEIGHT = 900
TOP_BAR_H = 80
FPS = 60
SESSION_TIME_SEC = 60.0
PASS_BTN_SIZE = (320, 110)
DATA_DIRNAME = "data"
LEADERBOARD_FILE = "leaderboard.json"
ALLOWED_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}

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


# -----------------------------
# Game
# -----------------------------
class FakeRealGame:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Fake vs Real")
        self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        self.screen_w, self.screen_h = self.screen.get_size()

        self.canvas = pygame.Surface((CANVAS_WIDTH, CANVAS_HEIGHT)).convert()

        # Fonts
        self.font_small = pygame.font.Font(None, 36)
        self.font = pygame.font.Font(None, 48)
        self.font_large = pygame.font.Font(None, 96)
        self.font_xlarge = pygame.font.Font(None, 180)

        # Layout rects on canvas
        self.left_rect = pygame.Rect(0, TOP_BAR_H, CANVAS_WIDTH // 2, CANVAS_HEIGHT - TOP_BAR_H)
        self.right_rect = pygame.Rect(CANVAS_WIDTH // 2, TOP_BAR_H, CANVAS_WIDTH // 2, CANVAS_HEIGHT - TOP_BAR_H)
        self.pass_rect = pygame.Rect(0, 0, PASS_BTN_SIZE[0], PASS_BTN_SIZE[1])
        self.pass_rect.center = (CANVAS_WIDTH // 2, CANVAS_HEIGHT // 2)

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
        self.state = "countdown"  # countdown -> playing -> enter_name -> leaderboard
        self.score = 0.0
        self.round_index = 0
        self.session_start_ms = 0
        self.time_left = SESSION_TIME_SEC
        self.player_name = ""
        self.just_qualified = False
        self.latest_score = 0.0

        # current round
        self.left_image = None
        self.right_image = None
        self.left_is_real = False

        # Preload first pair before countdown ends
        self.load_new_pair()

        self.clock = pygame.time.Clock()
        self.running = True
        self.countdown_sequence = [("3", 800), ("2", 800), ("1", 800), ("GO", 600)]  # in ms
        self.countdown_index = 0
        self.countdown_phase_start = pygame.time.get_ticks()

        # Leaderboard
        self.leaderboard_path = resource_path(LEADERBOARD_FILE)

    # -------------------------
    # Dataset and rounds
    # -------------------------
    def pick_random_paths(self):
        cat = random.choice(self.categories)
        real_path = random.choice(self.real_map[cat])
        fake_path = random.choice(self.fake_map[cat])
        return real_path, fake_path

    def load_image_scaled(self, path: str, rect: pygame.Rect):
        try:
            img = pygame.image.load(path)
            if img.get_alpha() is not None:
                img = img.convert_alpha()
            else:
                img = img.convert()
            return scale_to_cover(img, rect.width, rect.height)
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
                if self.state == "countdown":
                    # optional: skip countdown? Not requested; keep it running.
                    pass
                elif self.state == "playing":
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
                        # Start a new session -> countdown reset
                        self.state = "countdown"
                        self.countdown_index = 0
                        self.countdown_phase_start = pygame.time.get_ticks()
                        self.load_new_pair()
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self.state == "playing":
                    m = self.screen_to_canvas(*event.pos)
                    if m is None:
                        continue
                    mx, my = m
                    # Give PASS button precedence when overlapping image areas
                    if self.pass_rect.collidepoint(mx, my):
                        # Pass
                        self.round_index += 1
                        self.load_new_pair()
                    elif self.left_rect.collidepoint(mx, my):
                        self.handle_guess(is_left=True)
                    elif self.right_rect.collidepoint(mx, my):
                        self.handle_guess(is_left=False)

    def handle_guess(self, is_left: bool):
        correct = (is_left and self.left_is_real) or ((not is_left) and (not self.left_is_real))
        if correct:
            self.score += 1.0
        else:
            self.score -= 0.5
        self.round_index += 1
        self.load_new_pair()

    # -------------------------
    # Update & Render per state
    # -------------------------
    def update(self, dt_ms: int):
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

        if self.state in ("countdown", "playing"):
            # Draw images
            if self.left_image is not None:
                self.canvas.blit(self.left_image, self.left_rect.topleft)
            if self.right_image is not None:
                self.canvas.blit(self.right_image, self.right_rect.topleft)

            # Top bar
            self.draw_top_bar()

            # Pass button
            mouse_pos = pygame.mouse.get_pos()
            cm = self.screen_to_canvas(*mouse_pos)
            hover = False
            if cm is not None:
                hover = self.pass_rect.collidepoint(*cm)
            self.draw_pass_button(hover)

            if self.state == "countdown":
                # Overlay countdown
                overlay = pygame.Surface((CANVAS_WIDTH, CANVAS_HEIGHT), pygame.SRCALPHA)
                overlay.fill(SEMI_BLACK)
                self.canvas.blit(overlay, (0, 0))
                label, _ = self.countdown_sequence[self.countdown_index]
                color = GREEN if label == "GO" else WHITE
                surf = self.font_xlarge.render(label, True, color)
                self.canvas.blit(surf, (CANVAS_WIDTH // 2 - surf.get_width() // 2, CANVAS_HEIGHT // 2 - surf.get_height() // 2))
        elif self.state == "enter_name":
            # Result screen and name input
            self.draw_text_center("Time's up!", 170, color=YELLOW, font=self.font_large)
            self.draw_text_center(f"Your score: {self.latest_score:.1f}", 260, color=WHITE, font=self.font_large)
            self.draw_text_center("Enter your name and press Enter:", 360, color=WHITE)
            # Input box
            box_w, box_h = 700, 70
            box = pygame.Rect(0, 0, box_w, box_h)
            box.center = (CANVAS_WIDTH // 2, 470)
            pygame.draw.rect(self.canvas, WHITE, box, border_radius=10)
            pygame.draw.rect(self.canvas, BLACK, box, width=3, border_radius=10)
            name_display = self.player_name if (pygame.time.get_ticks() // 500) % 2 == 0 else self.player_name + "|"
            txt = self.font.render(name_display, True, BLACK)
            self.canvas.blit(txt, (box.x + 16, box.y + (box_h - txt.get_height()) // 2))
        elif self.state == "leaderboard":
            self.draw_text_center("Leaderboard (Top 10)", 100, color=YELLOW, font=self.font_large)
            entries = getattr(self, "leaderboard_entries", [])
            y = 200
            rank = 1
            for e in entries:
                name = e.get("name", "?")
                score = e.get("score", 0)
                line = f"{rank:2d}. {name[:24]:<24}  {score:.1f}"
                self.draw_text_center(line, y, color=WHITE, font=self.font)
                y += 46
                rank += 1
            if self.just_qualified:
                self.draw_text_center("Congratulations! You made it into the Top 10!", y + 30, color=GREEN, font=self.font)
            self.draw_text_center("Press Enter to play again, or Esc to quit.", CANVAS_HEIGHT - 80, color=GRAY, font=self.font)

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
