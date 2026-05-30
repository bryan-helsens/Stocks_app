import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// The mandatory educational disclaimer shown on every analysis / AI / FIRE /
/// tax screen and in reports (business rule BR9). Reused app-wide for
/// consistency.
class DisclaimerStrip extends StatelessWidget {
  const DisclaimerStrip({super.key, this.text = defaultText});

  static const defaultText =
      'Informatief en educatief — geen financieel, fiscaal of juridisch advies. '
      'Voorspellingen en scores zijn geen garanties.';

  final String text;

  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    final color = dark ? AppColors.warningDark : AppColors.warning;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.info_outline, size: 16, color: color),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              text,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(color: color),
            ),
          ),
        ],
      ),
    );
  }
}
