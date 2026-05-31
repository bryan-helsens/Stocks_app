import 'package:dio/dio.dart';

import '../storage/secure_store.dart';
import 'api_config.dart';

/// Signals that authentication failed irrecoverably (forces re-login).
class SessionExpired implements Exception {}

/// A typed wrapper around the backend's uniform error envelope.
class ApiException implements Exception {
  ApiException(this.code, this.message, {this.statusCode});

  final String code;
  final String message;
  final int? statusCode;

  @override
  String toString() => message;
}

/// Configured Dio client with auth + transparent token-refresh.
///
/// On a 401 the client attempts a single refresh using the stored refresh
/// token and replays the original request. If refresh fails it clears tokens
/// and surfaces [SessionExpired] so the router can redirect to login.
class ApiClient {
  ApiClient(this._store) {
    _dio = Dio(
      BaseOptions(
        baseUrl: ApiConfig.url(''),
        connectTimeout: const Duration(seconds: 15),
        receiveTimeout: const Duration(seconds: 30),
        contentType: 'application/json',
      ),
    );
    _dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: _onRequest,
        onError: _onError,
      ),
    );
  }

  final SecureStore _store;
  late final Dio _dio;
  bool _refreshing = false;

  Dio get raw => _dio;

  Future<void> _onRequest(RequestOptions options, RequestInterceptorHandler handler) async {
    final token = await _store.accessToken;
    if (token != null) {
      options.headers['Authorization'] = 'Bearer $token';
    }
    handler.next(options);
  }

  Future<void> _onError(DioException error, ErrorInterceptorHandler handler) async {
    final response = error.response;
    if (response?.statusCode == 401 && !_refreshing && !_isAuthPath(error.requestOptions.path)) {
      try {
        await _refresh();
        final clone = await _retry(error.requestOptions);
        return handler.resolve(clone);
      } on SessionExpired {
        await _store.clear();
        return handler.reject(error);
      } catch (_) {
        await _store.clear();
        return handler.reject(error);
      }
    }
    handler.next(_mapError(error));
  }

  bool _isAuthPath(String path) =>
      path.contains('/auth/login') || path.contains('/auth/refresh');

  Future<void> _refresh() async {
    _refreshing = true;
    try {
      final refresh = await _store.refreshToken;
      if (refresh == null) throw SessionExpired();
      final res = await Dio().post(
        ApiConfig.url('/auth/refresh'),
        data: {'refresh_token': refresh},
      );
      final data = res.data as Map<String, dynamic>;
      await _store.saveTokens(
        access: data['access_token'] as String,
        refresh: data['refresh_token'] as String,
      );
    } on DioException {
      throw SessionExpired();
    } finally {
      _refreshing = false;
    }
  }

  Future<Response<dynamic>> _retry(RequestOptions options) async {
    final token = await _store.accessToken;
    return _dio.request<dynamic>(
      options.path,
      data: options.data,
      queryParameters: options.queryParameters,
      options: Options(
        method: options.method,
        headers: {...options.headers, 'Authorization': 'Bearer $token'},
      ),
    );
  }

  DioException _mapError(DioException error) {
    final data = error.response?.data;
    if (data is Map && data['error'] is Map) {
      final env = data['error'] as Map;
      error.error = ApiException(
        env['code']?.toString() ?? 'error',
        env['message']?.toString() ?? 'Er ging iets mis.',
        statusCode: error.response?.statusCode,
      );
    } else {
      error.error = ApiException(
        'network_error',
        'Geen verbinding met de server.',
        statusCode: error.response?.statusCode,
      );
    }
    return error;
  }
}
