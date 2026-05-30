import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/ai/presentation/ai_page.dart';
import '../../features/auth/presentation/auth_controller.dart';
import '../../features/auth/presentation/login_page.dart';
import '../../features/dashboard/presentation/dashboard_page.dart';
import '../../features/dividends/presentation/dividends_page.dart';
import '../../features/fire/presentation/fire_page.dart';
import '../../features/import/presentation/import_page.dart';
import '../../features/portfolio/presentation/portfolio_page.dart';
import '../../features/tax/presentation/tax_page.dart';
import '../widgets/app_shell.dart';

/// App routing with an auth guard. Unauthenticated users are redirected to
/// /login; the shell hosts the main feature pages behind a nav rail/bottom bar.
final routerProvider = Provider<GoRouter>((ref) {
  final auth = ref.watch(authControllerProvider);

  return GoRouter(
    initialLocation: '/dashboard',
    redirect: (context, state) {
      final status = auth.status;
      final loggingIn = state.matchedLocation == '/login';
      if (status == AuthStatus.unknown) return null;
      final authed = status == AuthStatus.authenticated;
      if (!authed && !loggingIn) return '/login';
      if (authed && loggingIn) return '/dashboard';
      return null;
    },
    routes: [
      GoRoute(path: '/login', builder: (_, __) => const LoginPage()),
      ShellRoute(
        builder: (context, state, child) => AppShell(state: state, child: child),
        routes: [
          GoRoute(path: '/dashboard', builder: (_, __) => const DashboardPage()),
          GoRoute(path: '/portfolio', builder: (_, __) => const PortfolioPage()),
          GoRoute(path: '/import', builder: (_, __) => const ImportPage()),
          GoRoute(path: '/dividends', builder: (_, __) => const DividendsPage()),
          GoRoute(path: '/fire', builder: (_, __) => const FirePage()),
          GoRoute(path: '/ai', builder: (_, __) => const AiPage()),
          GoRoute(path: '/tax', builder: (_, __) => const TaxPage()),
        ],
      ),
    ],
  );
});
