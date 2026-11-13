import 'dart:math' as math;

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../api.dart';
import '../server_store.dart';
import 'cough_screen.dart';

// Same colours as the label page (ui/label.css), the Cough form and the Vet tab.
const _littenColor = Color(0xFFD62828);
const _shinxColor = Color(0xFFF4C20D);

Color _catColor(String cat) => cat == 'Shinx' ? _shinxColor : _littenColor;

const _catArt = {'Litten': 'litten_pokemon.png', 'Shinx': 'shinx_pokemon.png'};
const _cats = ['Litten', 'Shinx'];

const _weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const _months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

String _shortDate(DateTime d) => '${_months[d.month - 1]} ${d.day}';
String _niceDate(DateTime d) => '${_weekdays[d.weekday - 1]}, ${_months[d.month - 1]} ${d.day}, ${d.year}';
DateTime _day(DateTime d) => DateTime(d.year, d.month, d.day);

/// The date presets in the Dates dropdown.
enum DateRangeChoice { today, last7, last30, thisMonth, custom }

extension on DateRangeChoice {
  String get label => switch (this) {
        DateRangeChoice.today => 'Today',
        DateRangeChoice.last7 => 'Last 7 days',
        DateRangeChoice.last30 => 'Last 30 days',
        DateRangeChoice.thisMonth => 'This month',
        DateRangeChoice.custom => 'Custom range…',
      };
}

/// (from, to) days for a preset, ending today. [custom] is used for the custom choice.
(DateTime, DateTime) rangeFor(DateRangeChoice c, DateTime now, DateTimeRange? custom) {
  final today = _day(now);
  return switch (c) {
    DateRangeChoice.today => (today, today),
    DateRangeChoice.last7 => (today.subtract(const Duration(days: 6)), today),
    DateRangeChoice.last30 => (today.subtract(const Duration(days: 29)), today),
    DateRangeChoice.thisMonth => (DateTime(today.year, today.month, 1), today),
    DateRangeChoice.custom => custom == null
        ? (today.subtract(const Duration(days: 6)), today)
        : (_day(custom.start), _day(custom.end)),
  };
}

String _rangeText(DateTime from, DateTime to) {
  if (from == to) return _shortDate(from);
  final days = to.difference(from).inDays + 1;
  final span = from.year == to.year
      ? '${_shortDate(from)} – ${_shortDate(to)}'
      : '${_shortDate(from)}, ${from.year} – ${_shortDate(to)}, ${to.year}';
  return days > 31 ? '$span ($days days)' : span;
}

/// The Events tab: litterbox visits and coughs, filtered by cat, event type and dates,
/// with totals, a chart per event type (swipe between them) and the list. View only.
/// "Add cough" opens the cough form (this tab replaced the Cough tab).
class EventsScreen extends StatefulWidget {
  const EventsScreen({super.key, required this.store, required this.server});

  final ServerStore store;
  final Server server;

  @override
  State<EventsScreen> createState() => _EventsScreenState();
}

class _EventsScreenState extends State<EventsScreen> {
  /// null = Both cats / All types.
  String? _cat;
  String? _type;
  DateRangeChoice _range = DateRangeChoice.last7;
  DateTimeRange? _custom;

  List<EventType>? _types;
  EventsPage? _first;
  final List<CatEvent> _events = [];
  String? _next;
  bool _loading = false;
  bool _loadingMore = false;
  String? _error;
  CatApi? _api;

  /// Bumped on every new load, so an older, slower answer is ignored.
  int _loadGen = 0;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<CatApi> _getApi() async =>
      _api ??= CatApi(widget.server, await widget.store.keyFor(widget.server.id));

  (DateTime, DateTime) get _dates => rangeFor(_range, DateTime.now(), _custom);

  Future<void> _load() async {
    final gen = ++_loadGen;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final api = await _getApi();
      _types ??= await api.eventTypes();
      final (from, to) = _dates;
      final page = await api.events(cat: _cat, type: _type, from: from, to: to);
      if (!mounted || gen != _loadGen) return;
      setState(() {
        _first = page;
        _events
          ..clear()
          ..addAll(page.events);
        _next = page.next;
      });
    } on ApiException catch (e) {
      if (mounted && gen == _loadGen) setState(() => _error = e.message);
    } catch (e) {
      if (mounted && gen == _loadGen) setState(() => _error = 'Something went wrong: $e');
    } finally {
      if (mounted && gen == _loadGen) setState(() => _loading = false);
    }
  }

  Future<void> _loadMore() async {
    final next = _next;
    if (next == null || _loadingMore) return;
    final gen = _loadGen;
    setState(() => _loadingMore = true);
    try {
      final (from, to) = _dates;
      final page = await (await _getApi())
          .events(cat: _cat, type: _type, from: from, to: to, before: next);
      if (!mounted || gen != _loadGen) return;
      setState(() {
        _events.addAll(page.events);
        _next = page.next;
      });
    } on ApiException catch (e) {
      if (mounted) _toast(e.message);
    } catch (e) {
      if (mounted) _toast('Something went wrong: $e');
    } finally {
      if (mounted) setState(() => _loadingMore = false);
    }
  }

  void _toast(String text) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));

  Future<void> _pickRange(DateRangeChoice c) async {
    if (c == DateRangeChoice.custom) {
      final (from, to) = _dates;
      final picked = await showDateRangePicker(
        context: context,
        firstDate: DateTime(2023),
        lastDate: _day(DateTime.now()),
        initialDateRange: DateTimeRange(start: from, end: to),
        helpText: 'Choose dates',
      );
      if (picked == null) return;
      _custom = picked;
    }
    setState(() => _range = c);
    _load();
  }

  Future<void> _addCough() async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      showDragHandle: true,
      builder: (context) => FractionallySizedBox(
        heightFactor: 0.85,
        child: CoughScreen(store: widget.store, server: widget.server),
      ),
    );
    if (mounted) _load(); // show the cough that was just sent
  }

  void _openPhoto(CatEvent e) {
    final api = _api;
    if (api == null) return;
    Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => _PhotoPage(event: e, api: api)));
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final first = _first;
    final (from, to) = _dates;
    final cats = _cat == null ? _cats : [_cat!];

    return Scaffold(
      backgroundColor: Colors.transparent,
      floatingActionButton: FloatingActionButton.extended(
        heroTag: 'add-cough',
        icon: const Icon(Icons.add),
        label: const Text('Add cough'),
        onPressed: _addCough,
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 96),
          children: [
            _FilterRow(
              label: 'Cat',
              child: SegmentedButton<String>(
                segments: const [
                  ButtonSegment(value: '', label: Text('Both')),
                  ButtonSegment(value: 'Litten', label: Text('Litten')),
                  ButtonSegment(value: 'Shinx', label: Text('Shinx')),
                ],
                selected: {_cat ?? ''},
                showSelectedIcon: false,
                onSelectionChanged: (s) {
                  setState(() => _cat = s.single.isEmpty ? null : s.single);
                  _load();
                },
              ),
            ),
            const SizedBox(height: 10),
            _FilterRow(
              label: 'Event',
              child: SegmentedButton<String>(
                segments: [
                  const ButtonSegment(value: '', label: Text('All')),
                  for (final t in _types ?? const <EventType>[])
                    ButtonSegment(value: t.type, label: Text(t.name)),
                ],
                selected: {_type ?? ''},
                showSelectedIcon: false,
                onSelectionChanged: (s) {
                  setState(() => _type = s.single.isEmpty ? null : s.single);
                  _load();
                },
              ),
            ),
            const SizedBox(height: 10),
            _FilterRow(
              label: 'Dates',
              child: PopupMenuButton<DateRangeChoice>(
                tooltip: 'Choose the date range',
                onSelected: _pickRange,
                itemBuilder: (context) => [
                  for (final c in DateRangeChoice.values)
                    PopupMenuItem(
                      value: c,
                      child: Row(
                        children: [
                          Expanded(child: Text(c == _range ? '✓ ${c.label}' : c.label)),
                          if (c != DateRangeChoice.custom)
                            Text(_rangeText(rangeFor(c, DateTime.now(), null).$1,
                                    rangeFor(c, DateTime.now(), null).$2),
                                style: theme.textTheme.bodySmall),
                        ],
                      ),
                    ),
                ],
                child: InputDecorator(
                  decoration: const InputDecoration(
                    border: OutlineInputBorder(),
                    isDense: true,
                    contentPadding: EdgeInsets.fromLTRB(14, 10, 8, 10),
                  ),
                  child: Row(
                    children: [
                      Text(_range == DateRangeChoice.custom ? 'Custom' : _range.label,
                          style: const TextStyle(fontWeight: FontWeight.w500)),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(_rangeText(from, to),
                            overflow: TextOverflow.ellipsis, style: theme.textTheme.bodySmall),
                      ),
                      const Icon(Icons.arrow_drop_down),
                    ],
                  ),
                ),
              ),
            ),
            const SizedBox(height: 14),
            if (_loading && first == null) const Center(child: CircularProgressIndicator()),
            if (_error != null)
              Card(
                color: theme.colorScheme.errorContainer,
                child: ListTile(
                  leading: Icon(Icons.error_outline, color: theme.colorScheme.onErrorContainer),
                  title: Text(_error!, style: TextStyle(color: theme.colorScheme.onErrorContainer)),
                  trailing: IconButton(icon: const Icon(Icons.refresh), onPressed: _load),
                ),
              ),
            if (first != null) ...[
              _Summary(total: first.total ?? 0, byCat: first.byCat, cats: cats),
              const SizedBox(height: 12),
              if (first.chart != null && (_types?.isNotEmpty ?? false))
                _Charts(
                  // a new set of charts (back to the first page) for each new answer
                  key: ObjectKey(first),
                  chart: first.chart!,
                  types: [
                    for (final t in _types!)
                      if (first.chart!.series.containsKey(t.type)) t
                  ],
                  byType: first.byType,
                  cats: cats,
                ),
              const SizedBox(height: 12),
              if (_events.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 24),
                  child: Text('No events in this range.', textAlign: TextAlign.center),
                ),
              for (final e in _events)
                _EventCard(event: e, api: _api, onOpenPhoto: () => _openPhoto(e)),
              if (_next != null)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Center(
                    child: _loadingMore
                        ? const CircularProgressIndicator()
                        : OutlinedButton(onPressed: _loadMore, child: const Text('Load more')),
                  ),
                ),
            ],
          ],
        ),
      ),
    );
  }
}

class _FilterRow extends StatelessWidget {
  const _FilterRow({required this.label, required this.child});

  final String label;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        SizedBox(width: 48, child: Text(label, style: Theme.of(context).textTheme.bodySmall)),
        Expanded(child: child),
      ],
    );
  }
}

String _catCounts(Map<String, int> counts, List<String> cats) =>
    [for (final c in cats) '$c ${counts[c] ?? 0}'].join(' · ');

class _Summary extends StatelessWidget {
  const _Summary({required this.total, required this.byCat, required this.cats});

  final int total;
  final Map<String, int> byCat;
  final List<String> cats;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    // Wrap, not Row: on a narrow phone the per-cat counts move under the total.
    return Wrap(
      spacing: 8,
      crossAxisAlignment: WrapCrossAlignment.end,
      children: [
        Text('$total ${total == 1 ? 'event' : 'events'}', style: theme.textTheme.titleMedium),
        if (cats.length > 1) Text(_catCounts(byCat, cats), style: theme.textTheme.bodyMedium),
      ],
    );
  }
}

/// One chart per event type; swipe between them. Swiping changes only the chart.
class _Charts extends StatefulWidget {
  const _Charts({
    super.key,
    required this.chart,
    required this.types,
    required this.byType,
    required this.cats,
  });

  final EventChart chart;
  final List<EventType> types;
  final Map<String, Map<String, int>> byType;
  final List<String> cats;

  @override
  State<_Charts> createState() => _ChartsState();
}

class _ChartsState extends State<_Charts> {
  int _page = 0;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final types = widget.types;
    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 12, 12, 8),
        child: Column(
          children: [
            SizedBox(
              height: 250,
              child: PageView(
                onPageChanged: (i) => setState(() => _page = i),
                children: [
                  for (final t in types)
                    _ChartPage(
                      type: t,
                      chart: widget.chart,
                      totals: widget.byType[t.type] ?? const {},
                      cats: widget.cats,
                      swipeHint: types.length > 1,
                    ),
                ],
              ),
            ),
            if (types.length > 1)
              Semantics(
                label: 'Chart ${_page + 1} of ${types.length}',
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    for (var i = 0; i < types.length; i++)
                      Container(
                        width: 7,
                        height: 7,
                        margin: const EdgeInsets.symmetric(horizontal: 3),
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: i == _page ? theme.colorScheme.primary : theme.colorScheme.outlineVariant,
                        ),
                      ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}

/// The start of chart bucket [i] as a wall-clock date (and hour, for hour buckets).
DateTime bucketStart(EventChart c, int i) {
  final b = c.buckets[i];
  final d = DateTime.parse(b.substring(0, 10));
  return c.bucket == 'hour' ? DateTime(d.year, d.month, d.day, int.parse(b.substring(11, 13))) : d;
}

String _hourText(int h) => h == 0 ? '12a' : (h < 12 ? '${h}a' : (h == 12 ? '12p' : '${h - 12}p'));

/// The axis label under bucket [i].
String axisLabel(EventChart c, int i) {
  final d = bucketStart(c, i);
  if (c.bucket == 'hour') return _hourText(d.hour);
  if (c.bucket == 'day' && c.buckets.length <= 7) return _weekdays[d.weekday - 1];
  return '${d.month}/${d.day}';
}

/// The tapped bucket's heading, e.g. "Wed, Nov 11" or "Fri, Nov 13 · 8 AM" or "Week of Nov 2".
String bucketTitle(EventChart c, int i) {
  final d = bucketStart(c, i);
  return switch (c.bucket) {
    'hour' => '${_weekdays[d.weekday - 1]}, ${_shortDate(d)} · '
        '${d.hour % 12 == 0 ? 12 : d.hour % 12} ${d.hour < 12 ? 'AM' : 'PM'}',
    'week' => 'Week of ${_shortDate(d)}',
    _ => '${_weekdays[d.weekday - 1]}, ${_shortDate(d)}',
  };
}

class _ChartPage extends StatefulWidget {
  const _ChartPage({
    required this.type,
    required this.chart,
    required this.totals,
    required this.cats,
    required this.swipeHint,
  });

  final EventType type;
  final EventChart chart;
  final Map<String, int> totals;
  final List<String> cats;
  final bool swipeHint;

  @override
  State<_ChartPage> createState() => _ChartPageState();
}

class _ChartPageState extends State<_ChartPage> {
  int? _selected;

  Map<String, List<int>> get _series => widget.chart.series[widget.type.type] ?? const {};

  void _select(int? i) {
    if (i != null && i >= 0 && i < widget.chart.buckets.length && i != _selected) {
      setState(() => _selected = i);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final chart = widget.chart;
    final n = chart.buckets.length;
    final maxCount = [
      for (final c in widget.cats) ...(_series[c] ?? const <int>[]),
    ].fold<int>(0, math.max);
    final maxY = math.max(1, maxCount).toDouble();
    final yStep = maxY <= 5 ? 1.0 : (maxY / 4).ceilToDouble();
    final xStep = math.max(1, (n / 7).ceil());
    final grid = theme.colorScheme.outlineVariant;
    final labelStyle = theme.textTheme.labelSmall;
    final sel = _selected;

    final titles = FlTitlesData(
      topTitles: const AxisTitles(),
      rightTitles: const AxisTitles(),
      leftTitles: AxisTitles(
        sideTitles: SideTitles(
          showTitles: true,
          reservedSize: 24,
          interval: yStep,
          getTitlesWidget: (v, meta) => SideTitleWidget(
            meta: meta,
            child: Text(v == v.roundToDouble() ? v.toInt().toString() : '', style: labelStyle),
          ),
        ),
      ),
      bottomTitles: AxisTitles(
        sideTitles: SideTitles(
          showTitles: true,
          reservedSize: 22,
          interval: 1,
          getTitlesWidget: (v, meta) {
            final i = v.round();
            final show = v == i && i >= 0 && i < n && i % xStep == 0;
            return SideTitleWidget(meta: meta, child: Text(show ? axisLabel(chart, i) : '', style: labelStyle));
          },
        ),
      ),
    );
    final gridData = FlGridData(
      drawVerticalLine: false,
      horizontalInterval: yStep,
      getDrawingHorizontalLine: (_) => FlLine(color: grid, strokeWidth: 1),
    );

    final Widget graph;
    if (chart.kind == 'line') {
      graph = LineChart(LineChartData(
        minX: 0,
        maxX: math.max(1, n - 1).toDouble(),
        minY: 0,
        maxY: maxY,
        titlesData: titles,
        gridData: gridData,
        borderData: FlBorderData(show: false),
        lineBarsData: [
          for (final c in widget.cats)
            LineChartBarData(
              spots: [
                for (var i = 0; i < n; i++) FlSpot(i.toDouble(), (_series[c]?[i] ?? 0).toDouble()),
              ],
              color: _catColor(c),
              barWidth: 2,
              dotData: const FlDotData(show: false),
            ),
        ],
        extraLinesData: ExtraLinesData(verticalLines: [
          if (sel != null)
            VerticalLine(x: sel.toDouble(), color: theme.colorScheme.onSurface, strokeWidth: 1, dashArray: [3, 3]),
        ]),
        lineTouchData: LineTouchData(
          handleBuiltInTouches: false,
          touchCallback: (event, response) {
            final spots = response?.lineBarSpots;
            if (event.isInterestedForInteractions && spots != null && spots.isNotEmpty) {
              _select(spots.first.x.round());
            }
          },
        ),
      ));
    } else {
      final barWidth = n <= 8 ? 12.0 : (n <= 24 ? 5.0 : 3.0);
      graph = BarChart(BarChartData(
        maxY: maxY,
        alignment: BarChartAlignment.spaceAround,
        titlesData: titles,
        gridData: gridData,
        borderData: FlBorderData(show: false),
        barGroups: [
          for (var i = 0; i < n; i++)
            BarChartGroupData(
              x: i,
              barsSpace: 1,
              barRods: [
                for (final c in widget.cats)
                  BarChartRodData(
                    toY: (_series[c]?[i] ?? 0).toDouble(),
                    color: _catColor(c),
                    width: barWidth,
                    borderRadius: const BorderRadius.vertical(top: Radius.circular(2)),
                    borderSide: i == sel
                        ? BorderSide(color: theme.colorScheme.onSurface, width: 1.5)
                        : BorderSide.none,
                  ),
              ],
            ),
        ],
        barTouchData: BarTouchData(
          handleBuiltInTouches: false,
          touchCallback: (event, response) {
            if (event.isInterestedForInteractions) _select(response?.spot?.touchedBarGroupIndex);
          },
        ),
      ));
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.baseline,
          textBaseline: TextBaseline.alphabetic,
          children: [
            Text(widget.type.name, style: theme.textTheme.titleSmall),
            const SizedBox(width: 8),
            Expanded(child: Text(_catCounts(widget.totals, widget.cats), style: theme.textTheme.bodySmall)),
            if (widget.swipeHint) Text('swipe →', style: labelStyle),
          ],
        ),
        const SizedBox(height: 10),
        Expanded(child: graph),
        const SizedBox(height: 6),
        SizedBox(
          height: 20,
          child: Center(
            child: Text(
              sel == null
                  ? 'Tap the chart to see ${chart.bucket == 'hour' ? 'an hour' : 'a ${chart.bucket}'}'
                  : '${bucketTitle(chart, sel)} · ${[
                      for (final c in widget.cats) '$c ${_series[c]?[sel] ?? 0}'
                    ].join(' · ')}',
              style: sel == null ? labelStyle : theme.textTheme.bodySmall?.copyWith(fontWeight: FontWeight.w500),
            ),
          ),
        ),
      ],
    );
  }
}

class _EventCard extends StatelessWidget {
  const _EventCard({required this.event, required this.api, required this.onOpenPhoto});

  final CatEvent event;
  final CatApi? api;
  final VoidCallback onOpenPhoto;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final e = event;
    final pic = e.picture;
    final sent = [
      if (e.reporter != null) 'Sent by ${e.reporter}',
      if (pic?.labeledBy != null) 'labeled by ${pic!.labeledBy}',
    ].join(' · ');
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: _catColor(e.cat), width: 2),
      ),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('${e.typeName} · ${e.cat}', style: theme.textTheme.titleSmall),
                  const SizedBox(height: 2),
                  Text('${_niceDate(e.when)} · ${TimeOfDay.fromDateTime(e.when).format(context)}',
                      style: theme.textTheme.bodySmall),
                  if (e.notes != null) ...[
                    const SizedBox(height: 2),
                    Text('“${e.notes}”'),
                  ],
                  if (sent.isNotEmpty) ...[
                    const SizedBox(height: 2),
                    Text(sent, style: theme.textTheme.bodySmall),
                  ],
                ],
              ),
            ),
            const SizedBox(width: 12),
            _Thumb(event: e, api: api, onTap: onOpenPhoto),
          ],
        ),
      ),
    );
  }
}

/// The event's photo, or its cat's art dimmed with "No photo".
class _Thumb extends StatelessWidget {
  const _Thumb({required this.event, required this.api, required this.onTap});

  final CatEvent event;
  final CatApi? api;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final api = this.api;
    final pic = event.picture;
    final placeholder = _NoPhoto(cat: event.cat, api: api);
    if (api == null || pic == null || !pic.hasImage) return placeholder;
    return Semantics(
      button: true,
      label: 'Open photo',
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: onTap,
        child: ClipRRect(
          borderRadius: BorderRadius.circular(8),
          child: Image.network(
            api.pictureUri(pic.id).toString(),
            headers: api.imageHeaders,
            width: 64,
            height: 64,
            fit: BoxFit.cover,
            errorBuilder: (_, _, _) => placeholder,
          ),
        ),
      ),
    );
  }
}

class _NoPhoto extends StatelessWidget {
  const _NoPhoto({required this.cat, required this.api});

  final String cat;
  final CatApi? api;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final art = _catArt[cat];
    final api = this.api;
    return Container(
      width: 64,
      height: 64,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(8),
        color: theme.colorScheme.surfaceContainerHighest,
      ),
      padding: const EdgeInsets.all(4),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          if (art != null && api != null)
            Flexible(
              // the art shrinks to whatever room the label leaves
              child: Opacity(
                opacity: 0.4,
                child: Image.network(api.assetUri(art).toString(),
                    fit: BoxFit.contain, errorBuilder: (_, _, _) => const SizedBox.shrink()),
              ),
            ),
          Text('No photo', style: theme.textTheme.labelSmall, maxLines: 1, overflow: TextOverflow.clip),
        ],
      ),
    );
  }
}

/// Full-screen photo with what the model and the labeler said about it.
class _PhotoPage extends StatelessWidget {
  const _PhotoPage({required this.event, required this.api});

  final CatEvent event;
  final CatApi api;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final e = event;
    final pic = e.picture!;
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(backgroundColor: Colors.black, title: Text('${e.typeName} · ${e.cat}')),
      body: Column(
        children: [
          Expanded(
            child: InteractiveViewer(
              maxScale: 5,
              child: Center(
                child: Image.network(
                  api.pictureUri(pic.id).toString(),
                  headers: api.imageHeaders,
                  errorBuilder: (_, _, _) => const Text("Couldn't load the photo."),
                ),
              ),
            ),
          ),
          Card(
            margin: const EdgeInsets.fromLTRB(12, 0, 12, 16),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(16),
              side: BorderSide(color: _catColor(e.cat), width: 2),
            ),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('${_niceDate(e.when)} · ${TimeOfDay.fromDateTime(e.when).format(context)}',
                      style: theme.textTheme.titleSmall),
                  if (pic.bestGuess != null)
                    Text('Model guessed ${pic.bestGuess}'
                        '${pic.confidence != null ? ', ${(pic.confidence! * 100).round()}% sure' : ''}'),
                  if (pic.labeledBy != null) Text('Labeled ${e.cat} by ${pic.labeledBy}'),
                  if (e.reporter != null) Text('Sent by ${e.reporter}'),
                  if (e.notes != null) Text('“${e.notes}”'),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
