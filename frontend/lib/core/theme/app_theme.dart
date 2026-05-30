import 'package:flutter/material.dart';

/// Design tokens and Material 3 light/dark themes for DivTrack.
///
/// Colours mirror the wireframe design tokens (deliverable 4): a calm,
/// data-dense look inspired by TradingView / Snowball / Simply Wall St.
class AppColors {
  AppColors._();

  // Brand & semantic
  static const primary = Color(0xFF1F6FEB);
  static const primaryDark = Color(0xFF4C8DFF);
  static const positive = Color(0xFF16A34A); // gains
  static const positiveDark = Color(0xFF34D399);
  static const negative = Color(0xFFDC2626); // losses
  static const negativeDark = Color(0xFFF87171);
  static const warning = Color(0xFFD97706);
  static const warningDark = Color(0xFFFBBF24);

  // Light surfaces / text
  static const surfaceLight = Color(0xFFFFFFFF);
  static const surfaceAltLight = Color(0xFFF4F6F8);
  static const textLight = Color(0xFF0F172A);
  static const mutedLight = Color(0xFF64748B);

  // Dark surfaces / text
  static const surfaceDark = Color(0xFF121417);
  static const surfaceAltDark = Color(0xFF1B1F24);
  static const textDark = Color(0xFFE5E7EB);
  static const mutedDark = Color(0xFF94A3B8);
}

/// Resolves a profit/loss colour for the active brightness.
Color pnlColor(BuildContext context, num value) {
  final dark = Theme.of(context).brightness == Brightness.dark;
  if (value > 0) return dark ? AppColors.positiveDark : AppColors.positive;
  if (value < 0) return dark ? AppColors.negativeDark : AppColors.negative;
  return Theme.of(context).colorScheme.onSurfaceVariant;
}

class AppTheme {
  AppTheme._();

  static const _radius = 12.0;

  static ThemeData light() => _base(
        brightness: Brightness.light,
        primary: AppColors.primary,
        surface: AppColors.surfaceLight,
        surfaceAlt: AppColors.surfaceAltLight,
        text: AppColors.textLight,
        muted: AppColors.mutedLight,
      );

  static ThemeData dark() => _base(
        brightness: Brightness.dark,
        primary: AppColors.primaryDark,
        surface: AppColors.surfaceDark,
        surfaceAlt: AppColors.surfaceAltDark,
        text: AppColors.textDark,
        muted: AppColors.mutedDark,
      );

  static ThemeData _base({
    required Brightness brightness,
    required Color primary,
    required Color surface,
    required Color surfaceAlt,
    required Color text,
    required Color muted,
  }) {
    final scheme = ColorScheme.fromSeed(
      seedColor: primary,
      brightness: brightness,
      surface: surface,
    ).copyWith(onSurfaceVariant: muted);

    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: scheme,
      scaffoldBackgroundColor: surfaceAlt,
      fontFamily: 'Roboto',
      cardTheme: CardThemeData(
        elevation: 0,
        color: surface,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(_radius),
          side: BorderSide(color: muted.withValues(alpha: 0.15)),
        ),
        margin: EdgeInsets.zero,
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: surfaceAlt,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(_radius),
          borderSide: BorderSide.none,
        ),
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size.fromHeight(48),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(_radius),
          ),
        ),
      ),
      navigationRailTheme: NavigationRailThemeData(
        backgroundColor: surface,
        selectedIconTheme: IconThemeData(color: primary),
      ),
    );
  }
}
