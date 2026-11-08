import { describe, expect, it } from "vitest";

import {
  formatNumber,
  formatPercent,
  formatTime,
  levelTone,
  positionText,
  stateLabel,
  stateTone,
} from "./format";
import { position } from "../test/fixtures";

describe("state labels and tones", () => {
  it("maps known and unknown states", () => {
    expect(stateLabel("Cycle_moveToPick")).toBe("Moving to cube");
    expect(stateLabel("ready")).toBe("Ready");
    expect(stateLabel("Some_new_state")).toBe("Some_new_state");
  });

  it("prioritizes fault, then busy, then ready", () => {
    expect(stateTone("fault", true, "boom")).toBe("fault");
    expect(stateTone("ready", true, "")).toBe("active");
    expect(stateTone("ready", false, "")).toBe("ready");
    expect(stateTone("Positioning_move", true, "")).toBe("active");
    expect(stateTone("Positioning_move", false, "")).toBe("idle");
  });
});

describe("number and position formatting", () => {
  it("formats numbers defensively", () => {
    expect(formatNumber(1.234)).toBe("1.2");
    expect(formatNumber(1.25, 2)).toBe("1.25");
    expect(formatNumber(undefined)).toBe("—");
    expect(formatNumber(Number.NaN)).toBe("—");
    expect(formatNumber(Number.POSITIVE_INFINITY)).toBe("—");
  });

  it("formats positions", () => {
    expect(positionText(position(-750, 750, 0))).toBe("X -750.0  Y 750.0  Z 0.0");
    expect(positionText(undefined)).toBe("—");
  });

  it("formats time and invalid timestamps", () => {
    expect(formatTime("2026-11-03T12:34:56+00:00")).toMatch(/\d{1,2}:\d{2}:\d{2}/);
    expect(formatTime("not-a-date")).toBe("not-a-date");
    expect(formatTime("")).toBe("—");
  });

  it("clamps progress percentages", () => {
    expect(formatPercent(0)).toBe("0%");
    expect(formatPercent(0.5)).toBe("50%");
    expect(formatPercent(1)).toBe("100%");
    expect(formatPercent(-1)).toBe("0%");
    expect(formatPercent(2)).toBe("100%");
    expect(formatPercent(Number.NaN)).toBe("0%");
  });

  it("maps event levels", () => {
    expect(levelTone("info")).toBe("info");
    expect(levelTone("warning")).toBe("warning");
    expect(levelTone("error")).toBe("error");
    expect(levelTone("other")).toBe("info");
  });
});
