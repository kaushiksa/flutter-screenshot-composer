// ignore_for_file: avoid_print

// ============================================================================
// TEMPLATE: App Store Screenshot Generator
//
// Copy this file to screenshot_test.dart and customize the TODOs below
// for your specific Flutter project.
//
// Run with:
//   flutter drive \
//     --driver=test_driver/screenshot_driver.dart \
//     --target=integration_test/screenshot_test.dart \
//     --device-id=<DEVICE_UDID>
// ============================================================================

// TODO: Replace with your app's imports
// import 'package:your_app/main.dart';
// import 'package:your_app/app.dart';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

/// Screens to capture, in order.
/// Format: (filename, route, label)
///   - filename: used as the PNG filename (e.g. "01_home" -> "01_home.png")
///   - route: the navigation route to this screen
///   - label: human-readable label (printed during capture)
///
/// TODO: Define your app's screens here
const _screens = [
  // ('01_home', '/home', 'Home'),
  // ('02_settings', '/settings', 'Settings'),
  // ('03_profile', '/profile', 'Profile'),
];

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  group('App Store Screenshots', () {
    testWidgets('Capture all screens', (tester) async {
      // ── 1. Initialize your app ──────────────────────────────────────
      // TODO: Initialize any required services (Firebase, etc.)
      // e.g.:
      //   await Firebase.initializeApp(
      //     options: DefaultFirebaseOptions.currentPlatform,
      //   );

      // ── 2. Launch app ───────────────────────────────────────────────
      // TODO: Replace with your app's widget tree
      // e.g.:
      //   await tester.pumpWidget(const MyApp());
      //
      // For Riverpod apps:
      //   final container = ProviderContainer();
      //   await tester.pumpWidget(
      //     UncontrolledProviderScope(
      //       container: container,
      //       child: MaterialApp.router(
      //         routerConfig: yourRouter,
      //       ),
      //     ),
      //   );

      await tester.pump(const Duration(seconds: 2));

      // ── 3. Login / setup (if needed) ────────────────────────────────
      // TODO: Authenticate if your app requires login for screenshots
      // e.g.:
      //   await apiClient.devLogin(email: 'screenshots@demo', name: 'Demo');
      //   await tester.pump(const Duration(seconds: 1));

      // ── 4. Navigate to first screen & wait for data ─────────────────
      // TODO: Navigate to initial screen and wait for it to load
      // e.g.:
      //   yourRouter.go('/home');
      //   await tester.pumpAndSettle(const Duration(seconds: 5));

      // ── 5. Capture each screen ──────────────────────────────────────
      for (final (filename, route, label) in _screens) {
        // Navigate (skip if already on this route)
        // TODO: Replace with your navigation method
        // e.g.:
        //   yourRouter.go(route);
        //   await tester.pump(const Duration(seconds: 2));
        //   await _waitForScreenReady(tester);

        // Signal to take_screenshots.sh for native-resolution capture
        print('\u{1f4f8} $label');
        // Take logical screenshot via binding
        await binding.takeScreenshot(filename);
      }

      print('\u{1f389} All screenshots captured!');
    });
  });
}

/// Wait for a screen to be fully rendered.
Future<void> _waitForScreenReady(
  WidgetTester tester, {
  Duration timeout = const Duration(seconds: 15),
}) async {
  try {
    await tester.pumpAndSettle(
      const Duration(milliseconds: 100),
      EnginePhase.sendSemanticsUpdate,
      timeout,
    );
  } catch (_) {
    await tester.pump(const Duration(seconds: 2));
  }
  await tester.pump(const Duration(seconds: 1));
}
