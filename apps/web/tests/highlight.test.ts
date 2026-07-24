import {
  findExcerptRanges,
  highlightParamValue,
  renderTextItemWithHighlight,
} from '../src/utils/highlight';

function highlightedText(items: readonly string[], excerpt: string): string {
  const ranges = findExcerptRanges(items, excerpt);
  if (!ranges) return '';
  return ranges
    .map((range) => items[range.itemIndex].slice(range.start, range.end))
    .join(' ')
    .replace(/\s+/g, ' ')
    .trim();
}

test('finds an exact excerpt inside a single text-layer item', () => {
  const items = ['The pilot measured a 37 percent efficiency gain across teams.'];
  const ranges = findExcerptRanges(items, 'measured a 37 percent efficiency gain');
  expect(ranges).not.toBeNull();
  expect(ranges).toHaveLength(1);
  expect(items[0].slice(ranges![0].start, ranges![0].end)).toBe(
    'measured a 37 percent efficiency gain',
  );
});

test('matches across items despite mangled whitespace and casing', () => {
  const items = ['THE PILOT  MEASURED', 'a  37   percent', 'efficiency gain.'];
  expect(highlightedText(items, 'the pilot measured a 37 percent efficiency gain')).toBe(
    'THE PILOT MEASURED a 37 percent efficiency gain',
  );
});

test('matches through a hyphenated line break', () => {
  const items = ['The measured effi-', 'ciency gain was 37 percent.'];
  expect(highlightedText(items, 'The measured efficiency gain was 37 percent.')).toBe(
    'The measured effi ciency gain was 37 percent.',
  );
});

test('ignores the ellipsis appended to truncated excerpts', () => {
  const items = ['Pilot findings summary: throughput improved by 37 percent overall.'];
  expect(highlightedText(items, 'throughput improved by 37 percent…')).toBe(
    'throughput improved by 37 percent',
  );
});

test('falls back to the longest shared run when the excerpt edges disagree', () => {
  const items = ['Section 4. The measured efficiency gain was 37 percent during the pilot.'];
  const excerpt = 'HEADER ARTIFACT The measured efficiency gain was 37 percent TRAILING NOISE';
  const text = highlightedText(items, excerpt);
  expect(text).toContain('efficiency gain was 37 percent');
});

test('rejects a short shared run that covers too little of a long excerpt', () => {
  // ~22 normalized characters overlap, but the excerpt normalizes to ~270
  // characters; a fallback below half the excerpt must not highlight anything.
  const shared = 'The efficiency gain was 37';
  const items = [`Appendix C. ${shared} percent in the second cohort study.`];
  const filler =
    'Entirely different subject matter covering harbor logistics and alpine weather routines. ';
  const excerpt = `${shared} ${filler.repeat(4)}`.slice(0, 320);
  expect(findExcerptRanges(items, excerpt)).toBeNull();
});

test('returns null when the excerpt is absent or too short', () => {
  const items = ['The measured efficiency gain was 37 percent.'];
  expect(findExcerptRanges(items, 'orbital speed of Neptune in kilometers per second')).toBeNull();
  expect(findExcerptRanges(items, 'gain')).toBeNull();
  expect(findExcerptRanges([], 'The measured efficiency gain was 37 percent.')).toBeNull();
});

test('renders highlight markup with HTML escaping', () => {
  expect(renderTextItemWithHighlight('a < b & "c"', { start: 4, end: 5 })).toBe(
    'a &lt; <mark class="evidence-highlight">b</mark> &amp; &quot;c&quot;',
  );
  expect(renderTextItemWithHighlight('<script>', undefined)).toBe('&lt;script&gt;');
});

test('truncates the highlight parameter at a word boundary', () => {
  const excerpt = `${'evidence '.repeat(30)}end`;
  const value = highlightParamValue(excerpt);
  expect(value.length).toBeLessThanOrEqual(160);
  expect(value.endsWith('evidence')).toBe(true);
  expect(highlightParamValue('short  excerpt\nwith breaks')).toBe('short excerpt with breaks');
});
