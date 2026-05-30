import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/auth_repository.dart';

enum AuthStatus { unknown, authenticated, unauthenticated, needs2fa }

@immutable
class AuthState {
  const AuthState({this.status = AuthStatus.unknown, this.pendingUserId, this.user});

  final AuthStatus status;
  final String? pendingUserId;
  final Map<String, dynamic>? user;

  AuthState copyWith({AuthStatus? status, String? pendingUserId, Map<String, dynamic>? user}) =>
      AuthState(
        status: status ?? this.status,
        pendingUserId: pendingUserId ?? this.pendingUserId,
        user: user ?? this.user,
      );
}

/// Holds the authentication state and drives login / 2FA / logout flows.
class AuthController extends StateNotifier<AuthState> {
  AuthController(this._repo) : super(const AuthState()) {
    _bootstrap();
  }

  final AuthRepository _repo;

  Future<void> _bootstrap() async {
    if (await _repo.hasSession()) {
      try {
        final user = await _repo.me();
        state = state.copyWith(status: AuthStatus.authenticated, user: user);
        return;
      } catch (_) {
        await _repo.logout();
      }
    }
    state = state.copyWith(status: AuthStatus.unauthenticated);
  }

  Future<void> register(String email, String password, String? fullName) async {
    await _repo.register(email, password, fullName);
    await login(email, password);
  }

  Future<void> login(String email, String password) async {
    final outcome = await _repo.login(email, password);
    if (outcome.requires2fa) {
      state = state.copyWith(status: AuthStatus.needs2fa, pendingUserId: outcome.userId);
    } else {
      final user = await _repo.me();
      state = state.copyWith(status: AuthStatus.authenticated, user: user);
    }
  }

  Future<void> verify2fa(String code) async {
    final userId = state.pendingUserId;
    if (userId == null) return;
    await _repo.verify2fa(userId, code);
    final user = await _repo.me();
    state = state.copyWith(status: AuthStatus.authenticated, user: user);
  }

  Future<void> logout() async {
    await _repo.logout();
    state = const AuthState(status: AuthStatus.unauthenticated);
  }
}

final authControllerProvider = StateNotifierProvider<AuthController, AuthState>(
  (ref) => AuthController(ref.watch(authRepositoryProvider)),
);
