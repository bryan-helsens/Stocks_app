import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Thin wrapper over [FlutterSecureStorage] for tokens and device flags.
///
/// Tokens never touch shared preferences or plain files — only the OS keystore
/// (Keychain / Keystore / libsecret) via flutter_secure_storage.
class SecureStore {
  SecureStore([FlutterSecureStorage? storage])
      : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;

  static const _kAccess = 'access_token';
  static const _kRefresh = 'refresh_token';
  static const _kBiometric = 'biometric_enabled';

  Future<void> saveTokens({required String access, required String refresh}) async {
    await _storage.write(key: _kAccess, value: access);
    await _storage.write(key: _kRefresh, value: refresh);
  }

  Future<void> saveAccess(String access) => _storage.write(key: _kAccess, value: access);

  Future<String?> get accessToken => _storage.read(key: _kAccess);
  Future<String?> get refreshToken => _storage.read(key: _kRefresh);

  Future<void> setBiometric(bool enabled) =>
      _storage.write(key: _kBiometric, value: enabled.toString());
  Future<bool> get biometricEnabled async =>
      (await _storage.read(key: _kBiometric)) == 'true';

  Future<void> clear() async {
    await _storage.delete(key: _kAccess);
    await _storage.delete(key: _kRefresh);
  }
}
