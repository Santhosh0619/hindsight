import { describe, expect, it } from "vitest";

import { buildHighlightSegments } from "@/lib/highlight-text";

describe("buildHighlightSegments", () => {
  it("splits text into plain and highlighted segments around a single range", () => {
    const text = "The pool was exhausted after the deploy.";
    const segments = buildHighlightSegments(text, [
      { char_start: 4, char_end: 22, fact_type: "root_cause" },
    ]);

    expect(segments).toEqual([
      { text: "The ", factType: null, factIndex: null },
      { text: "pool was exhausted", factType: "root_cause", factIndex: 0 },
      { text: " after the deploy.", factType: null, factIndex: null },
    ]);
  });

  it("returns the whole text as one plain segment with no ranges", () => {
    const text = "Nothing extracted yet.";
    expect(buildHighlightSegments(text, [])).toEqual([{ text, factType: null, factIndex: null }]);
  });

  it("resolves an overlap by letting the earlier-starting range win", () => {
    const text = "abcdefghij";
    const segments = buildHighlightSegments(text, [
      { char_start: 0, char_end: 5, fact_type: "trigger" },
      { char_start: 3, char_end: 8, fact_type: "root_cause" },
    ]);

    // The second range's claim on [3,5) is already covered by the first --
    // it only contributes [5,8).
    expect(segments).toEqual([
      { text: "abcde", factType: "trigger", factIndex: 0 },
      { text: "fgh", factType: "root_cause", factIndex: 1 },
      { text: "ij", factType: null, factIndex: null },
    ]);
  });

  it("clips a range whose end exceeds the text length instead of throwing", () => {
    const text = "short";
    const segments = buildHighlightSegments(text, [
      { char_start: 2, char_end: 100, fact_type: "remediation" },
    ]);

    expect(segments).toEqual([
      { text: "sh", factType: null, factIndex: null },
      { text: "ort", factType: "remediation", factIndex: 0 },
    ]);
  });

  it("orders out-of-order ranges by their start position", () => {
    const text = "0123456789";
    const segments = buildHighlightSegments(text, [
      { char_start: 6, char_end: 9, fact_type: "detection_gap" },
      { char_start: 0, char_end: 3, fact_type: "trigger" },
    ]);

    expect(segments.map((s) => s.text)).toEqual(["012", "345", "678", "9"]);
    expect(segments[0]?.factType).toBe("trigger");
    expect(segments[2]?.factType).toBe("detection_gap");
  });
});
