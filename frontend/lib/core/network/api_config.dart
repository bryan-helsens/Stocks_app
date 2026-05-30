/// API base configuration.
///
/// The base URL is overridable at build time:
///   flutter run --dart-define=API_BASE_URL=https://api.example.com
class ApiConfig {
  const ApiConfig._();

  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8000',
  );

  static const String apiPrefix = '/api/v1';

  static String url(String path) => '$baseUrl$apiPrefix$path';
}
