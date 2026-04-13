"""
Ren'Py Translator Pro — entry point.
"""

import sys
import os

# Add project root to path
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def main():
    try:
        import customtkinter  # noqa: F401
    except ImportError:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Missing Dependency",
            "CustomTkinter is not installed.\n"
            "Please run: pip install customtkinter"
        )
        sys.exit(1)

    from gui.main_window import MainWindow
    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
