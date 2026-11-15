import 'package:cat_id_app/server_store.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('normalizeAddress', () {
    test('plain HTTP addresses default to port 8000', () {
      expect(normalizeAddress('192.168.1.116'), '192.168.1.116:8000');
      expect(normalizeAddress(' http://192.168.1.116:8000/ '), '192.168.1.116:8000');
      expect(normalizeAddress('192.168.1.116:9000'), '192.168.1.116:9000');
    });

    test('https keeps its scheme and defaults to 443', () {
      expect(normalizeAddress('https://cat-id.tail1234.ts.net/'),
          'https://cat-id.tail1234.ts.net');
      expect(normalizeAddress('HTTPS://cat-id.tail1234.ts.net:443'),
          'https://cat-id.tail1234.ts.net');
      expect(normalizeAddress('https://example.com:8443'), 'https://example.com:8443');
    });

    test('a .ts.net name without a scheme is HTTPS', () {
      expect(normalizeAddress('cat-id.tail1234.ts.net'), 'https://cat-id.tail1234.ts.net');
      // An explicit http:// is respected.
      expect(normalizeAddress('http://cat-id.tail1234.ts.net'), 'cat-id.tail1234.ts.net:8000');
    });

    test('rejects junk', () {
      expect(normalizeAddress(''), isNull);
      expect(normalizeAddress('not an address'), isNull);
      expect(normalizeAddress('192.168.1.116:70000'), isNull);
    });
  });

  group('Server.baseUri', () {
    test('old host:port entries stay plain HTTP', () {
      final s = Server(id: '1', name: '', address: '192.168.1.116:8000');
      expect(s.isHttps, isFalse);
      expect(s.baseUri.toString(), 'http://192.168.1.116:8000');
      expect(s.baseUri.replace(path: '/health').toString(), 'http://192.168.1.116:8000/health');
    });

    test('https entries use HTTPS', () {
      final s = Server(id: '2', name: '', address: 'https://cat-id.tail1234.ts.net');
      expect(s.isHttps, isTrue);
      expect(s.baseUri.replace(path: '/health').toString(),
          'https://cat-id.tail1234.ts.net/health');
    });
  });
}
