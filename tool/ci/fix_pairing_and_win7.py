from pathlib import Path
import argparse

ROOT = Path("shared_app")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--windows7", action="store_true")
    args = parser.parse_args()

    screen = ROOT / "lib/dashboard/pairing_screen.dart"
    main_dart = ROOT / "lib/main.dart"
    screen_text = screen.read_text(encoding="utf-8")
    main_text = main_dart.read_text(encoding="utf-8")

    # Validate the uploaded website-approval flow; never revive legacy pairing codes.
    required_screen_markers = (
        "Website owner approval required",
        "Request website approval",
        "Future<void> Function(String deviceName) onPaired",
    )
    missing = [marker for marker in required_screen_markers if marker not in screen_text]
    if missing:
        raise SystemExit("Approval pairing screen validation failed: " + ", ".join(missing))
    if "Future<void> _onPaired(String deviceName)" not in main_text:
        raise SystemExit("Approval callback signature validation failed")
    print("Verified website-approval pairing flow; legacy pairing-code patch skipped.")

    # Flutter 3.47+ expects CardThemeData for ThemeData.cardTheme.
    theme = ROOT / "lib/theme/app_theme.dart"
    source = theme.read_text(encoding="utf-8")
    old = "cardTheme: CardTheme("
    new = "cardTheme: CardThemeData("
    if old in source:
        source = source.replace(old, new, 1)
        theme.write_text(source, encoding="utf-8")
        print("Patched ThemeData.cardTheme to CardThemeData for modern Flutter.")
    elif new in source:
        print("ThemeData.cardTheme already uses CardThemeData.")
    else:
        raise SystemExit("Could not find the expected ThemeData.cardTheme constructor.")

    if args.windows7:
        # Flutter 3.19 uses CardTheme rather than CardThemeData.
        source = theme.read_text(encoding="utf-8")
        old = "cardTheme: CardThemeData("
        new = "cardTheme: CardTheme("
        if old not in source:
            raise SystemExit("Could not find CardThemeData for the Windows 7 Flutter 3.19 conversion.")
        theme.write_text(source.replace(old, new, 1), encoding="utf-8")
        print("Converted cardTheme to the Flutter 3.19 CardTheme API.")

        source = theme.read_text(encoding="utf-8")
        updated = source.replace("scheme.surfaceContainerLow", "scheme.surface")
        if updated != source:
            theme.write_text(updated, encoding="utf-8")
            print("Applied Flutter 3.19 surface color compatibility.")

if __name__ == "__main__":
    main()
