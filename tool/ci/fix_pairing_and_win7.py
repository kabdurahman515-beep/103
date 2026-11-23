from pathlib import Path
import argparse

ROOT = Path("shared_app")


def patch_pairing_network_retries() -> None:
    api_client = ROOT / "lib/protocol/api_client.dart"
    source = api_client.read_text(encoding="utf-8")
    source = source.replace(
        "import 'dart:io' show Platform;",
        "import 'dart:io' show Platform, SocketException;",
        1,
    )
    old = """    // Poll while the owner reviews the request. The 24h request window is
    // independent of the credential lifetime selected by the owner.
    while (true) {
      await Future<void>.delayed(const Duration(seconds: 5));
      final response = await _http.get(
        _u('/devices/registration/$registrationId'),
        headers: {'Authorization':'Bearer $pollSecret', 'Cache-Control':'no-store'},
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw ApiException.fromResponse(response.statusCode, response.body);
      }
      final result = jsonDecode(response.body) as Map<String, dynamic>;
      final status = result['status'];
      if (status == 'approved') return result;
      if (status == 'rejected') throw ApiException(403, 'REGISTRATION_REJECTED', 'Website owner ne device request reject kar di.');
      if (status == 'revoked') throw ApiException(403, 'REGISTRATION_REVOKED', 'Website owner ne device access revoke kar diya.');
      if (status == 'expired') throw ApiException(410, 'REGISTRATION_EXPIRED', 'Approval request expire ho gayi. Dobara request bhejein.');
    }
"""
    new = """    // Poll while the owner reviews the request. Temporary mobile DNS/network
    // failures must not abandon an already-created registration. The server
    // keeps the request for 24h, so retry with bounded backoff until a real
    // terminal status is returned.
    var nextPollDelay = const Duration(seconds: 5);
    var networkRetryDelay = const Duration(seconds: 5);
    while (true) {
      await Future<void>.delayed(nextPollDelay);
      nextPollDelay = const Duration(seconds: 5);
      try {
        final response = await _http.get(
          _u('/devices/registration/$registrationId'),
          headers: {'Authorization':'Bearer $pollSecret', 'Cache-Control':'no-store'},
        ).timeout(const Duration(seconds: 20));
        if (response.statusCode == 429) {
          final retryAfter = int.tryParse(response.headers['retry-after'] ?? '');
          nextPollDelay = Duration(seconds: (retryAfter ?? 10).clamp(5, 120).toInt());
          continue;
        }
        if (response.statusCode < 200 || response.statusCode >= 300) {
          throw ApiException.fromResponse(response.statusCode, response.body);
        }
        networkRetryDelay = const Duration(seconds: 5);
        final result = jsonDecode(response.body) as Map<String, dynamic>;
        final status = result['status'];
        if (status == 'approved') return result;
        if (status == 'rejected') throw ApiException(403, 'REGISTRATION_REJECTED', 'Website owner ne device request reject kar di.');
        if (status == 'revoked') throw ApiException(403, 'REGISTRATION_REVOKED', 'Website owner ne device access revoke kar diya.');
        if (status == 'expired') throw ApiException(410, 'REGISTRATION_EXPIRED', 'Approval request expire ho gayi. Dobara request bhejein.');
      } catch (error) {
        if (error is! SocketException && error is! http.ClientException && error is! TimeoutException) {
          rethrow;
        }
        nextPollDelay = networkRetryDelay;
        final nextSeconds = (networkRetryDelay.inSeconds * 2).clamp(5, 60).toInt();
        networkRetryDelay = Duration(seconds: nextSeconds);
      }
    }
"""
    if "var networkRetryDelay = const Duration(seconds: 5);" in source:
        print("Pairing network retry patch already applied.")
    elif old in source:
        source = source.replace(old, new, 1)
        api_client.write_text(source, encoding="utf-8")
        print("Added transient DNS/network retry and 429 backoff to approval polling.")
    else:
        raise SystemExit("Could not find the expected approval polling loop in api_client.dart")




def patch_approval_waiting_screen() -> None:
    """Move approval polling to a dedicated status page after request submission."""
    screen = ROOT / "lib/dashboard/pairing_screen.dart"
    source = screen.read_text(encoding="utf-8")
    old_signature = "final Future<void> Function(String deviceName) onPaired;"
    new_signature = "final Future<void> Function(String deviceName, VoidCallback onRequestSent) onPaired;"
    if old_signature in source:
        source = source.replace(old_signature, new_signature, 1)
    elif new_signature not in source:
        raise SystemExit("Could not find PairingScreen onPaired callback signature.")

    old_continue = """    try {
      await widget.onPaired(name);
    } finally {
      if (mounted) setState(() => _pairing = false);
    }
"""
    new_continue = """    try {
      await Navigator.of(context).push<void>(
        MaterialPageRoute<void>(
          builder: (_) => ApprovalWaitingScreen(
            onPaired: (onRequestSent) => widget.onPaired(name, onRequestSent),
          ),
        ),
      );
    } finally {
      if (mounted) setState(() => _pairing = false);
    }
"""
    if old_continue in source:
        source = source.replace(old_continue, new_continue, 1)
    elif "ApprovalWaitingScreen(" not in source:
        raise SystemExit("Could not find PairingScreen submit handler.")

    if "class ApprovalWaitingScreen" not in source:
        source += r'''

/// Separate page for the website-owner approval process. The server polling
/// continues quietly; the user does not remain on the device-name form.
class ApprovalWaitingScreen extends StatefulWidget {
  final Future<void> Function(VoidCallback onRequestSent) onPaired;

  const ApprovalWaitingScreen({super.key, required this.onPaired});

  @override
  State<ApprovalWaitingScreen> createState() => _ApprovalWaitingScreenState();
}

class _ApprovalWaitingScreenState extends State<ApprovalWaitingScreen> {
  bool _requestSent = false;
  bool _submitting = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _submit());
  }

  Future<void> _submit() async {
    if (_submitting) return;
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      await widget.onPaired(() {
        if (mounted) setState(() => _requestSent = true);
      });
      if (mounted) Navigator.of(context).pop();
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Approval Status')),
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(28),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  _error == null ? Icons.mark_email_read_outlined : Icons.error_outline,
                  size: 76,
                  color: _error == null ? colors.primary : colors.error,
                ),
                const SizedBox(height: 22),
                Text(
                  _error != null
                      ? 'Request send nahi ho saki'
                      : _requestSent ? 'Request received' : 'Sending approval request',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.headlineSmall,
                ),
                const SizedBox(height: 14),
                Text(
                  _error != null
                      ? _error!
                      : _requestSent
                          ? 'Aapki approval request website owner tak pahunch gayi hai.'
                          : 'Aapki request website par bheji ja rahi hai. Thora intezar karein.',
                  textAlign: TextAlign.center,
                ),
                if (_error == null) ...[
                  const SizedBox(height: 26),
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(18),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Icon(Icons.hourglass_top, color: colors.primary),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text('Waiting for owner approval',
                                    style: TextStyle(fontWeight: FontWeight.w600)),
                                const SizedBox(height: 6),
                                Text(_requestSent
                                    ? 'Owner approve karega to device automatically connect ho jayega.'
                                    : 'Request submit hote hi approval status yahan dikhai dega.'),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
                if (_error != null) ...[
                  const SizedBox(height: 20),
                  FilledButton(onPressed: _submit, child: const Text('Retry request')),
                  TextButton(
                    onPressed: () => Navigator.of(context).pop(),
                    child: const Text('Back to device name'),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
'''
    screen.write_text(source, encoding="utf-8")

    main = ROOT / "lib/main.dart"
    source = main.read_text(encoding="utf-8")
    old_main_signature = "Future<void> _onPaired(String deviceName) async {"
    new_main_signature = "Future<void> _onPaired(String deviceName, VoidCallback onRequestSent) async {"
    if old_main_signature in source:
        source = source.replace(old_main_signature, new_main_signature, 1)
    elif new_main_signature not in source:
        raise SystemExit("Could not find main pairing callback.")

    old_call = """        deviceName: deviceName,
      );"""
    new_call = """        deviceName: deviceName,
        onRequestSent: onRequestSent,
      );"""
    if old_call in source:
        source = source.replace(old_call, new_call, 1)
    elif "onRequestSent: onRequestSent" not in source:
        raise SystemExit("Could not find pairDevice call in main.dart.")

    old_catch = """    } catch (e) {
      if (!mounted) return;
      setState(() => _pairingError = 'Pairing server se connect nahi ho saka: $e');
    } finally {
"""
    if old_catch in source:
        source = source.replace(old_catch, "    } finally {\n", 1)
    main.write_text(source, encoding="utf-8")

    api = ROOT / "lib/protocol/api_client.dart"
    source = api.read_text(encoding="utf-8")
    old_api_signature = "Future<Map<String, dynamic>> pairDevice({required String deviceName}) async {"
    new_api_signature = "Future<Map<String, dynamic>> pairDevice({required String deviceName, void Function()? onRequestSent}) async {"
    if old_api_signature in source:
        source = source.replace(old_api_signature, new_api_signature, 1)
    elif new_api_signature not in source:
        raise SystemExit("Could not find pairDevice API signature.")

    marker = "    final pollSecret = reg['poll_secret'] as String;\n"
    if marker in source:
        source = source.replace(marker, marker + "    onRequestSent?.call();\n", 1)
    elif "onRequestSent?.call();" not in source:
        raise SystemExit("Could not find server registration accepted marker.")
    api.write_text(source, encoding="utf-8")
    print("Added dedicated approval status screen; name form no longer shows an endless spinner.")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--windows7", action="store_true")
    args = parser.parse_args()

    screen = ROOT / "lib/dashboard/pairing_screen.dart"
    main_dart = ROOT / "lib/main.dart"
    screen_text = screen.read_text(encoding="utf-8")
    main_text = main_dart.read_text(encoding="utf-8")
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
    patch_pairing_network_retries()
    patch_approval_waiting_screen()

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
        source = theme.read_text(encoding="utf-8")
        old = "cardTheme: CardThemeData("
        new = "cardTheme: CardTheme("
        if old not in source:
            raise SystemExit("Could not find CardThemeData for the Flutter 3.19 conversion.")
        theme.write_text(source.replace(old, new, 1), encoding="utf-8")
        print("Converted cardTheme to the Flutter 3.19 CardTheme API.")
        source = theme.read_text(encoding="utf-8")
        updated = source.replace("scheme.surfaceContainerLow", "scheme.surface")
        if updated != source:
            theme.write_text(updated, encoding="utf-8")
            print("Applied Flutter 3.19 surface color compatibility.")


if __name__ == "__main__":
    main()
