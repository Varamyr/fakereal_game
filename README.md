# Fake vs Real - Image Guessing Game

A fullscreen Pygame app: two images (left/right), a big PASS button in the center, top bar with score and countdown timer. You guess which image is real. +1 for correct, -0.5 for wrong, 0 for PASS. 60s per session. Leaderboard (top 10) saved to `leaderboard.json`.

## Dataset Layout

Place your dataset under `./data` with the following structure:

```
data/
  real/
    <category1>/
      image1.png
      ...
  fake/
    <category1>/
      imageA.png
      ...
```

Categories must match between `real/` and `fake/` and contain images.

Supported extensions: `.png, .jpg, .jpeg, .bmp, .webp`.

## Install & Run

1. Create and activate a virtual environment (optional but recommended)
2. Install dependencies
3. Run the game

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

- Fullscreen is used by default. Press `Esc` to quit.
- Use mouse to click left/right image or the PASS button.

## Notes

- Images are scaled with cover strategy to fill the left/right panes.
- Countdown (3,2,1,GO) before each session.
- After time ends, enter your name and press Enter to save to leaderboard.
- If you made Top 10, you will see a congratulations message.
- Press Enter on the leaderboard to start another session.
