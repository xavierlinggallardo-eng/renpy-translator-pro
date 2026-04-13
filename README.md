# 🎮 Ren'Py Translator Pro

A fully-featured Windows desktop application for translating Ren'Py visual novels.
Handles **all text types** — dialogue, narration, menus, UI, and translate blocks.
Outperforms tools like Zoneplayer/Zenpy through a smarter parser, translation memory, and multi-engine support.

---

## ✨ Features

| Feature | Details |
|---|---|
| **Parser** | Dialogue, narration, menus, UI text, translate blocks |
| **Engines** | Argos (offline), LibreTranslate, Gemini, OpenAI, DeepL |
| **Translation memory** | `cache.json` — avoids re-translating identical strings |
| **Token preservation** | `{variables}`, `[player_name]`, `%s`, `\n`, `{p}`, `{w}` are kept intact |
| **GUI** | Modern CustomTkinter dark-mode UI |
| **Input** | Folder or `.zip` |
| **Output** | Complete translated project copy |
| **Build** | Single `.exe` via PyInstaller |

---

## 🏗 Project Structure

```
renpy_translator/
├── main.py                   ← Entry point
├── requirements.txt
├── RenPyTranslator.spec      ← PyInstaller spec
├── build.bat                 ← One-click Windows build
├── build.sh                  ← Linux/macOS build
├── core/
│   ├── parser.py             ← .rpy parser (all text types)
│   ├── translator.py         ← Pipeline orchestrator
│   ├── memory.py             ← Translation cache
│   └── reinserter.py         ← Translation reinsertion
├── engines/
│   ├── base.py               ← Base engine + token protection
│   ├── argos_engine.py       ← Argos Translate (offline)
│   ├── libre_engine.py       ← LibreTranslate
│   ├── gemini_engine.py      ← Google Gemini API
│   ├── openai_engine.py      ← OpenAI GPT
│   ├── deepl_engine.py       ← DeepL
│   └── registry.py           ← Engine factory
├── gui/
│   └── main_window.py        ← Full GUI (main + settings windows)
├── utils/
│   ├── config.py             ← config.json management
│   └── zip_handler.py        ← ZIP extraction
└── tests/
    └── test_parser.py        ← Unit tests
```

---

## 🚀 Run from Source

### 1. Prerequisites
- Python 3.10 or newer
- Windows / Linux / macOS

### 2. Install dependencies

```bash
cd renpy_translator
pip install customtkinter requests
# For Argos offline translation:
pip install argostranslate
# For Gemini (free tier):
pip install google-generativeai
# For OpenAI (optional):
pip install openai
# For DeepL (optional):
pip install deepl
```

### 3. Launch

```bash
python main.py
```

---

## 🔨 Build the .exe (Windows)

### Option A — One-click batch file

1. Open `renpy_translator/` in File Explorer
2. Double-click **`build.bat`**
3. Wait for the build (1–3 minutes)
4. Find your executable at **`dist\RenPyTranslator.exe`**

### Option B — Manual

```bat
pip install pyinstaller customtkinter requests google-generativeai argostranslate
pyinstaller RenPyTranslator.spec --noconfirm
```

Output: `dist\RenPyTranslator.exe`

---

## ⚙️ Translation Engines

### 🥇 Argos Translate (Best free, offline)
- **No API key needed**
- Fully offline — works without internet
- First use: click "Extract Text" and Argos will auto-download the language pack
- Quality: moderate (OPUS-MT models)

### 🌐 LibreTranslate
- **No API key needed** (public endpoint)
- Or self-host for unlimited use
- URL configurable in Settings

### 💎 Google Gemini (Best quality, free tier)
- Free tier: 15 req/min, 1M tokens/day
- Get key: https://aistudio.google.com/apikey
- Enter in **Settings → Gemini API Key**
- Best quality for context-aware VN translation

### 🤖 OpenAI GPT (Paid)
- GPT-3.5/4 quality
- Enter key in **Settings → OpenAI API Key**

### 📘 DeepL (Freemium)
- 500k chars/month free
- Enter key in **Settings → DeepL API Key**

---

## 📋 Example Usage

1. Launch `RenPyTranslator.exe`
2. Click **"Select Folder"** → choose your Ren'Py game folder
3. Select engine: **"Argos Translate (Offline)"** (no key needed)
4. Select language: **"Spanish"**
5. Click **"⚡ Full Auto (Recommended)"**
6. Wait for completion
7. Find translated project next to original with `_translated` suffix

---

## 🔧 Config

Settings are stored at:
- **Windows:** `%APPDATA%\RenPyTranslatorPro\config.json`
- **Linux/macOS:** `<project_dir>/config.json`

Translation cache: same directory as config, `cache.json`

---

## 🧪 Tests

```bash
cd renpy_translator
pip install pytest
python -m pytest tests/ -v
```

---

## 📝 Supported .rpy Text Types

| Type | Example |
|---|---|
| Dialogue | `e "Hello world"` |
| Multi-char dialogue | `mcth "Thinking..."` |
| Narration | `"This is narration."` |
| Menu choice | `"Yes":` inside `menu:` block |
| UI text | `text "Start"`, `textbutton "Play"` |
| UI label | `label "Settings"` |
| Translate block (active line) | `e "Hola"` inside `translate spanish:` |

**Always preserved:**
- `{variable}`, `[player_name]`, `%s`, `%d`
- `\n`, `\t`, `{p}`, `{w}`, `{fast}` (Ren'Py text tags)
- Indentation and syntax structure
- All Ren'Py `.rpyc` and non-text files

---

## ⚠️ Important Notes

- Source language is assumed to be **English**
- The parser works on `.rpy` source files only (not `.rpyc` compiled files)
- After applying translation, test in Ren'Py to verify correctness
- Translate-block lines: only the **active** line is modified; original `#` comment lines are always preserved
