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

    # The uploaded archive already implements website approval; do not run
    # the retired pairing-code rewrite against this newer screen.
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

    if args.windows7:
        theme = ROOT / "lib/theme/app_theme.dart"
        source = theme.read_text(encoding="utf-8")
        updated = source.replace("scheme.surfaceContainerLow", "scheme.surface")
        if updated != source:
            theme.write_text(updated, encoding="utf-8")
            print("Applied Flutter 3.19 theme compatibility.")
        else:
            print("No newer surfaceContainerLow API found; theme is already compatible.")

if __name__ == "__main__":
    main()
