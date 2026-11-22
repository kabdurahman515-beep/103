from pathlib import Path
import argparse

ROOT = Path("shared_app")

def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old in text:
        text = text.replace(old, new, 1)
        path.write_text(text, encoding="utf-8")
        print(f"Patched {label}")
    elif new in text:
        print(f"Already patched: {label}")
    else:
        raise SystemExit(f"Could not safely patch {label}: expected source text not found")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--windows7", action="store_true")
    args = parser.parse_args()

    screen = ROOT / "lib/dashboard/pairing_screen.dart"
    text = screen.read_text(encoding="utf-8")
    text = text.replace("import 'package:qr_flutter/qr_flutter.dart';\n", "")
    text = text.replace("import '../platform_channels/platform_channel_bridge.dart';\n", "")
    text = text.replace("  final _pairingChannel = NativeCapabilityChannel(ChannelNames.pairing);\n", "")
    text = text.replace("  String? _pairingCode;\n", "")
    start = text.find("  Future<void> _startPairing() async {")
    end = text.find("\n  Future<void> _continue() async {", start)
    if start >= 0 and end > start:
        text = text[:start] + """  // Pairing credentials are issued by the server, never generated locally.
  Future<void> _startPairing() async {
    if (!mounted) return;
    setState(() {
      _loading = false;
      _error = null;
    });
  }
""" + text[end:]
    elif "Pairing credentials are issued by the server" not in text:
        raise SystemExit("Could not safely replace the native pairing-code call")
    text = text.replace(
        "    final generated = _pairingCode;\n    final serverCode = _serverCodeController.text.trim();\n    // Server code diya ho to wahi bhejte hain; warna purana (legacy) flow.\n    final code = serverCode.isNotEmpty ? serverCode : generated;",
        "    final serverCode = _serverCodeController.text.trim();\n    final code = serverCode;",
    )
    text = text.replace(
        "    final name = _nameController.text.trim();\n    if (_pairing) return;",
        "    final name = _nameController.text.trim();\n    if (_pairing) return;\n    if (code.isEmpty) {\n      setState(() => _error = 'Website se naya server pairing code le kar yahan enter karein');\n      return;\n    }",
    )
    text = text.replace(
        """                    if (_pairingCode != null)
                      QrImageView(
                        data: _pairingCode!,
                        size: 200,
                        backgroundColor: Colors.white,
                      ),
                    const SizedBox(height: 16),
                    Text('Pairing code: ${_pairingCode ?? '—'}',
                        style: Theme.of(context).textTheme.titleMedium),""",
        """                    const SizedBox(height: 16),
                    Text('Server pairing code (required)',
                        textAlign: TextAlign.center,
                        style: Theme.of(context).textTheme.titleMedium),""",
    )
    old_button = """                    if (_pairingCode == null)
                      FilledButton(
                          onPressed: _startPairing, child: const Text('Retry'))
                    else
                      FilledButton(
                        onPressed: _pairing ? null : _continue,
                        child: _pairing
                            ? const SizedBox(
                                width: 20,
                                height: 20,
                                child:
                                    CircularProgressIndicator(strokeWidth: 2))
                            : const Text("I've scanned it — Continue"),
                      ),"""
    new_button = """                    FilledButton(
                      onPressed: _pairing ? null : _continue,
                      child: _pairing
                          ? const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(strokeWidth: 2))
                          : const Text('Connect device'),
                    ),"""
    if old_button in text:
        text = text.replace(old_button, new_button, 1)
    elif "Connect device" not in text:
        raise SystemExit("Could not safely update the pairing button")
    screen.write_text(text, encoding="utf-8")

    api = ROOT / "lib/protocol/api_client.dart"
    main = ROOT / "lib/main.dart"
    replace_once(
        main,
        "Future<void> _onPaired(String? pairingCode, String deviceName) async {",
        "Future<void> _onPaired(String pairingCode, String deviceName) async {",
        "nullable pairing callback",
    )

    if args.windows7:
        theme = ROOT / "lib/theme/app_theme.dart"
        source = theme.read_text(encoding="utf-8")
        updated = source.replace("scheme.surfaceContainerLow", "scheme.surface")
        if updated == source and "scheme.surfaceContainerLow" in source:
            raise SystemExit("Windows 7 surface color compatibility patch did not match expected source")
        theme.write_text(updated, encoding="utf-8")
        print("Applied Flutter 3.19 theme compatibility.")

if __name__ == "__main__":
    main()
