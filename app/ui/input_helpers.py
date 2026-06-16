import sys


def switch_to_english_input() -> None:
    """Best-effort switch to English keyboard layout on Windows.

    Barcode scanners usually behave like keyboards. Chinese IME composition can
    corrupt scan text, so scanner fields call this before focusing/processing.
    """
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        user32 = ctypes.windll.user32
        layout = user32.LoadKeyboardLayoutW("00000409", 1)
        user32.ActivateKeyboardLayout(layout, 0)
    except Exception:
        pass


def focus_scanner_entry(entry) -> None:
    switch_to_english_input()
    try:
        entry.focus_set()
        entry.icursor("end")
    except Exception:
        pass
