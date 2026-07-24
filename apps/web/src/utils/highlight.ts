/**
 * Locate a cited excerpt inside the PDF.js text layer.
 *
 * The extracted text stored by the API and the strings PDF.js renders in the
 * text layer come from different passes over the same PDF, so they disagree on
 * whitespace, casing, soft line breaks, and end-of-line hyphenation. Matching
 * is therefore performed on an aggressively normalized view of both sides
 * (case-folded, whitespace and hyphens removed, ligatures expanded) while an
 * index map points every normalized character back to its text-layer item and
 * original character position.
 */

/** Minimum normalized characters required before a match is attempted. */
const MIN_NEEDLE_LENGTH = 8;
/** Minimum normalized characters a fallback (partial) match must cover. */
const MIN_FALLBACK_LENGTH = 20;
/** Longest highlight parameter carried in the viewer URL fallback. */
const HIGHLIGHT_PARAM_MAX_LENGTH = 160;

const CHAR_FOLDS: Record<string, string> = {
  '­': '', // soft hyphen
  '-': '',
  '‐': '', // hyphen
  '‑': '', // non-breaking hyphen
  '–': '', // en dash
  '—': '', // em dash
  '…': '', // ellipsis (excerpt truncation)
  '‘': "'",
  '’': "'",
  '“': '"',
  '”': '"',
  ﬀ: 'ff',
  ﬁ: 'fi',
  ﬂ: 'fl',
  ﬃ: 'ffi',
  ﬄ: 'ffl',
};

const WHITESPACE_RE = /\s/;

function foldCharacter(character: string): string {
  if (WHITESPACE_RE.test(character)) return '';
  const folded = CHAR_FOLDS[character] ?? character;
  return folded.toLowerCase();
}

export interface HighlightRange {
  itemIndex: number;
  /** Inclusive character start within the original text-layer item string. */
  start: number;
  /** Exclusive character end within the original text-layer item string. */
  end: number;
}

interface NormalizedPosition {
  itemIndex: number;
  charIndex: number;
}

interface NormalizedHaystack {
  text: string;
  positions: NormalizedPosition[];
}

function normalizeExcerpt(excerpt: string): string {
  let normalized = '';
  for (const character of excerpt) {
    normalized += foldCharacter(character);
  }
  return normalized;
}

function normalizeItems(items: readonly string[]): NormalizedHaystack {
  let text = '';
  const positions: NormalizedPosition[] = [];
  items.forEach((item, itemIndex) => {
    for (let charIndex = 0; charIndex < item.length; charIndex += 1) {
      const folded = foldCharacter(item[charIndex]);
      for (const character of folded) {
        text += character;
        positions.push({ itemIndex, charIndex });
      }
    }
  });
  return { text, positions };
}

/** Longest substring of `needle` present in `haystack`, via binary search on length. */
function longestSharedRun(
  needle: string,
  haystack: string,
): { hayStart: number; length: number } | null {
  let low = MIN_FALLBACK_LENGTH;
  let high = needle.length;
  let best: { hayStart: number; length: number } | null = null;
  while (low <= high) {
    const length = Math.floor((low + high) / 2);
    let found: number | null = null;
    for (let start = 0; start + length <= needle.length; start += 1) {
      const index = haystack.indexOf(needle.slice(start, start + length));
      if (index !== -1) {
        found = index;
        break;
      }
    }
    if (found !== null) {
      best = { hayStart: found, length };
      low = length + 1;
    } else {
      high = length - 1;
    }
  }
  return best;
}

function toRanges(positions: NormalizedPosition[], start: number, end: number): HighlightRange[] {
  const ranges: HighlightRange[] = [];
  for (let index = start; index < end; index += 1) {
    const position = positions[index];
    const last = ranges[ranges.length - 1];
    if (last && last.itemIndex === position.itemIndex) {
      last.start = Math.min(last.start, position.charIndex);
      last.end = Math.max(last.end, position.charIndex + 1);
    } else {
      ranges.push({
        itemIndex: position.itemIndex,
        start: position.charIndex,
        end: position.charIndex + 1,
      });
    }
  }
  return ranges;
}

/**
 * Find the text-layer character ranges covering `excerpt`.
 *
 * Tries an exact normalized match first, then falls back to the longest run
 * the excerpt and the text layer still share (extraction and rendering can
 * disagree at the edges). Returns `null` when nothing trustworthy matches.
 */
export function findExcerptRanges(
  items: readonly string[],
  excerpt: string,
): HighlightRange[] | null {
  const needle = normalizeExcerpt(excerpt);
  if (needle.length < MIN_NEEDLE_LENGTH) return null;
  const haystack = normalizeItems(items);
  if (haystack.text.length === 0) return null;

  const exact = haystack.text.indexOf(needle);
  if (exact !== -1) {
    return toRanges(haystack.positions, exact, exact + needle.length);
  }

  const shared = longestSharedRun(needle, haystack.text);
  if (shared === null) return null;
  return toRanges(haystack.positions, shared.hayStart, shared.hayStart + shared.length);
}

const HTML_ESCAPES: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
};

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (character) => HTML_ESCAPES[character]);
}

/**
 * Render one text-layer item as a markup string for react-pdf's
 * `customTextRenderer`, wrapping the matched range in a highlight mark.
 */
export function renderTextItemWithHighlight(
  str: string,
  range: Pick<HighlightRange, 'start' | 'end'> | undefined,
): string {
  if (!range || range.start >= range.end) return escapeHtml(str);
  const start = Math.max(0, Math.min(range.start, str.length));
  const end = Math.max(start, Math.min(range.end, str.length));
  return (
    escapeHtml(str.slice(0, start)) +
    `<mark class="evidence-highlight">${escapeHtml(str.slice(start, end))}</mark>` +
    escapeHtml(str.slice(end))
  );
}

/** Compact excerpt for the `highlight` search parameter used as a router-state fallback. */
export function highlightParamValue(
  excerpt: string,
  maxLength: number = HIGHLIGHT_PARAM_MAX_LENGTH,
): string {
  const collapsed = excerpt.replace(/\s+/g, ' ').trim();
  if (collapsed.length <= maxLength) return collapsed;
  const cut = collapsed.slice(0, maxLength);
  const lastSpace = cut.lastIndexOf(' ');
  return lastSpace > maxLength / 2 ? cut.slice(0, lastSpace) : cut;
}
