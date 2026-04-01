// Driver for saving screenshots to disk.
//
// This driver receives screenshot bytes from the integration test
// and writes them as PNG files to the screenshots/ directory.

import 'dart:io';

import 'package:integration_test/integration_test_driver_extended.dart';

Future<void> main() async {
  // Get output directory from environment or use default
  final outputDir = Platform.environment['SCREENSHOT_DIR'] ?? 'screenshots';

  await integrationDriver(
    onScreenshot: (String screenshotName, List<int> screenshotBytes,
        [Map<String, Object?>? args]) async {
      final file =
          await File('$outputDir/$screenshotName.png').create(recursive: true);
      file.writeAsBytesSync(screenshotBytes);
      print('  Saved: $outputDir/$screenshotName.png');
      return true;
    },
  );
}
