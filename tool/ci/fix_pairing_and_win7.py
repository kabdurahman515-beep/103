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
