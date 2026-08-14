import type { FactType } from "@/lib/types";

export interface TextSegment {
  text: string;
  factType: FactType | null;
  factIndex: number | null;
}

export interface HighlightRange {
  char_start: number;
  char_end: number;
  fact_type: FactType;
}

// Splits `text` into segments so a renderer can wrap each fact's span in a
// highlight without hand-managing overlapping ranges. Ranges are sorted by start
// and clipped against whatever's already been claimed, so two facts that share
// overlapping evidence in the source document never produce nested/broken markup --
// the earlier-starting fact wins the overlap.
export function buildHighlightSegments(text: string, ranges: HighlightRange[]): TextSegment[] {
  const sorted = ranges
    .map((range, index) => ({ ...range, index }))
    .sort((a, b) => a.char_start - b.char_start);

  const segments: TextSegment[] = [];
  let cursor = 0;

  for (const range of sorted) {
    const start = Math.max(range.char_start, cursor);
    const end = Math.max(range.char_end, start);
    if (start >= text.length || end <= start) continue;
    if (start > cursor) {
      segments.push({ text: text.slice(cursor, start), factType: null, factIndex: null });
    }
    segments.push({
      text: text.slice(start, Math.min(end, text.length)),
      factType: range.fact_type,
      factIndex: range.index,
    });
    cursor = Math.min(end, text.length);
  }

  if (cursor < text.length) {
    segments.push({ text: text.slice(cursor), factType: null, factIndex: null });
  }

  return segments;
}
