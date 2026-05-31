import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../../../core/providers.dart';
import '../../../core/storage/secure_store.dart';

/// Result of a login attempt: either tokens were issued, or 2FA is required.
class LoginOutcome {
  const LoginOutcome({required this.requires2fa, required this.userId, this.authenticated = false});

  final bool requires2fa;
  final String userId;
  final bool authenticated;
}

/// Talks to the backend auth endpoints and persists tokens securely.
class AuthRepository {
  AuthRepository(this._client, this._store);

  final ApiClient _client;
  final SecureStore _store;

  Future<void> register(String email, String password, String? fullName) async {
    await _client.raw.post('/auth/register', data: {
      'email': email,
      'password': password,
      if (fullName != null && fullName.isNotEmpty) 'full_name': fullName,
    });
  }

  Future<LoginOutcome> login(String email, String password) async {
    final res = await _client.raw.post('/auth/login', data: {
      'email': email,
      'password': password,
    });
    final data = res.data as Map<String, dynamic>;
    final requires2fa = data['requires_2fa'] as bool;
    if (!requires2fa && data['tokens'] != null) {
      final tokens = data['tokens'] as Map<String, dynamic>;
      await _store.saveTokens(
        access: tokens['access_token'] as String,
        refresh: tokens['refresh_token'] as String,
      );
      return LoginOutcome(requires2fa: false, userId: data['user_id'] as String, authenticated: true);
    }
    return LoginOutcome(requires2fa: true, userId: data['user_id'] as String);
  }

  Future<void> verify2fa(String userId, String code) async {
    final res = await _client.raw.post('/auth/2fa/verify', data: {
      'user_id': userId,
      'code': code,
    });
    final tokens = res.data as Map<String, dynamic>;
    await _store.saveTokens(
      access: tokens['access_token'] as String,
      refresh: tokens['refresh_token'] as String,
    );
  }

  Future<Map<String, dynamic>> me() async {
    final res = await _client.raw.get('/auth/me');
    return res.data as Map<String, dynamic>;
  }

  Future<void> logout() => _store.clear();

  Future<bool> hasSession() async => (await _store.accessToken) != null;
}

final authRepositoryProvider = Provider<AuthRepository>(
  (ref) => AuthRepository(ref.watch(apiClientProvider), ref.watch(secureStoreProvider)),
);
