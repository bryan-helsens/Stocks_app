import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/auth/presentation/auth_controller.dart';
import '../theme/theme_provider.dart';

/// Responsive navigation shell: a [NavigationRail] on wide screens (desktop /
/// tablet) and a [NavigationBar] on phones, matching the wireframes.
class AppShell extends ConsumerWidget {
  const AppShell({super.key, required this.state, required this.child});

  final GoRouterState state;
  final Widget child;

  static const _destinations = <_Dest>[
    _Dest('/dashboard', Icons.dashboard_outlined, Icons.dashboard, 'Dashboard'),
    _Dest('/portfolio', Icons.work_outline, Icons.work, 'Portfolio'),
    _Dest('/import', Icons.upload_file_outlined, Icons.upload_file, 'Import'),
    _Dest('/dividends', Icons.euro_outlined, Icons.euro, 'Dividend'),
    _Dest('/fire', Icons.local_fire_department_outlined, Icons.local_fire_department, 'FIRE'),
    _Dest('/ai', Icons.auto_awesome_outlined, Icons.auto_awesome, 'AI'),
    _Dest('/tax', Icons.receipt_long_outlined, Icons.receipt_long, 'Belasting'),
  ];

  int get _index {
    final loc = state.matchedLocation;
    final i = _destinations.indexWhere((d) => loc.startsWith(d.path));
    return i < 0 ? 0 : i;
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final wide = MediaQuery.sizeOf(context).width >= 760;
    final title = _destinations[_index].label;

    final appBar = AppBar(
      title: Text('DivTrack · $title'),
      actions: [
        IconButton(
          icon: const Icon(Icons.brightness_6_outlined),
          tooltip: 'Thema',
          onPressed: () => ref.read(themeModeProvider.notifier).cycle(),
        ),
        IconButton(
          icon: const Icon(Icons.logout),
          tooltip: 'Uitloggen',
          onPressed: () => ref.read(authControllerProvider.notifier).logout(),
        ),
      ],
    );

    if (wide) {
      return Scaffold(
        appBar: appBar,
        body: Row(
          children: [
            NavigationRail(
              selectedIndex: _index,
              labelType: NavigationRailLabelType.all,
              onDestinationSelected: (i) => context.go(_destinations[i].path),
              destinations: [
                for (final d in _destinations)
                  NavigationRailDestination(
                    icon: Icon(d.icon),
                    selectedIcon: Icon(d.selectedIcon),
                    label: Text(d.label),
                  ),
              ],
            ),
            const VerticalDivider(width: 1),
            Expanded(child: child),
          ],
        ),
      );
    }

    return Scaffold(
      appBar: appBar,
      body: child,
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => context.go(_destinations[i].path),
        destinations: [
          for (final d in _destinations)
            NavigationDestination(
              icon: Icon(d.icon),
              selectedIcon: Icon(d.selectedIcon),
              label: d.label,
            ),
        ],
      ),
    );
  }
}

class _Dest {
  const _Dest(this.path, this.icon, this.selectedIcon, this.label);
  final String path;
  final IconData icon;
  final IconData selectedIcon;
  final String label;
}
