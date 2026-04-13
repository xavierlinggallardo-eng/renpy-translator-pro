# Ren'Py Translator Pro — Project Summary

## Files Delivered

```
renpy_translator/
├── main.py                        ← App entry point
├── requirements.txt               ← All pip dependencies
├── RenPyTranslator.spec           ← PyInstaller one-file build spec
├── build.bat                      ← Windows one-click build
├── build.sh                       ← Linux/macOS build
├── README.md                      ← Full documentation
│
├── core/
│   ├── __init__.py
│   ├── parser.py                  ← Regex-based .rpy parser
│   │   ├── Dialogue:     e "Hello"
│   │   ├── Narration:    "Hello"
│   │   ├── Menu:         "Choice":
│   │   ├── UI:           text/textbutton/label "..."
│   │   └── Translate blocks (comment=original, active=translate)
│   ├── translator.py              ← Extract→Translate→Apply pipeline
│   ├── memory.py                  ← cache.json translation memory
│   └── reinserter.py              ← Write translations back to .rpy files
│
├── engines/
│   ├── __init__.py
│   ├── base.py                    ← Base class + token {var} protection
│   ├── argos_engine.py            ← Argos Translate (offline, free)
│   ├── libre_engine.py            ← LibreTranslate (free/self-host)
│   ├── gemini_engine.py           ← Google Gemini (free tier)
│   ├── openai_engine.py           ← OpenAI GPT (paid)
│   ├── deepl_engine.py            ← DeepL (freemium)
│   └── registry.py                ← Engine factory
│
├── gui/
│   ├── __init__.py
│   └── main_window.py             ← Full CustomTkinter GUI
│       ├── MainWindow             ← Main app window
│       └── SettingsWindow         ← API keys / preferences
│
├── utils/
│   ├── __init__.py
│   ├── config.py                  ← config.json load/save
│   └── zip_handler.py             ← .zip extraction
│
└── tests/
    ├── __init__.py
    └── test_parser.py             ← 20+ unit tests
```

## Build Instructions

### Run from Source
```bash
pip install customtkinter requests
python main.py
```

### Build .exe (Windows)
```
Double-click build.bat
→ dist\RenPyTranslator.exe
```

### Build .exe (manual)
```bash
pip install pyinstaller customtkinter requests
pyinstaller RenPyTranslator.spec --noconfirm
# Output: dist/RenPyTranslator.exe  (Windows)
#         dist/RenPyTranslator       (Linux/macOS)
```

## Engine Quick-Start

| Engine | API Key? | Install |
|--------|----------|---------|
| Argos (offline) | No | `pip install argostranslate` |
| LibreTranslate | No (or optional) | `pip install requests` (already included) |
| Gemini | Yes (free at aistudio.google.com) | `pip install google-generativeai` |
| OpenAI | Yes (paid) | `pip install openai` |
| DeepL | Yes (500k/mo free) | `pip install deepl` |
