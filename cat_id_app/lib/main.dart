import 'package:flutter/material.dart';

import 'screens/home_screen.dart';
import 'screens/welcome_screen.dart';
import 'server_store.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final store = await ServerStore.load();
  runApp(CatIdApp(store: store));
}

class CatIdApp extends StatelessWidget {
  const CatIdApp({super.key, required this.store});

  final ServerStore store;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Cat ID',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFFD62828),
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
      ),
      // No saved server yet: ask for one. Otherwise show the app.
      home: ListenableBuilder(
        listenable: store,
        builder: (context, _) => store.selected == null
            ? WelcomeScreen(store: store)
            : HomeScreen(store: store),
      ),
    );
  }
}
