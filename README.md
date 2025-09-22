# Fake vs Real - Image Guessing Game

A fullscreen Pygame app: two images (left/right), a big PASS button in the center, top bar with score and countdown timer. You guess which image is real. +1 for correct, -0.5 for wrong, 0 for PASS. 60s per session. Leaderboard (top 10) saved to `leaderboard.json`.

## Dataset Download
The dataset is composed by few datasets collected on huggingface and kaggle.
The fake images comprise generated images from both diffusion models and GANs.
There are around 100 samples per category in both fake and real folders.

Link: https://drive.google.com/file/d/1I_sexKgiOlPHn3yJGp9LPzUtDLKjc9We/view?usp=sharing

You can extend the dataset as you wish or use your own.

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
