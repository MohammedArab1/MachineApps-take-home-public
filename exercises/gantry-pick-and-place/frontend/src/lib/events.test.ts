import { describe, expect, it } from "vitest";

import { mergeEvent, mergeEvents } from "./events";
import { eventFixture } from "../test/fixtures";

describe("mergeEvents", () => {
  it("deduplicates by id and sorts newest first", () => {
    const first = eventFixture({ id: 1, message: "first" });
    const second = eventFixture({ id: 2, message: "second" });
    const secondUpdated = eventFixture({ id: 2, message: "second updated" });

    const merged = mergeEvents([first, second], [secondUpdated, eventFixture({ id: 3 })]);

    expect(merged.map((event) => event.id)).toEqual([3, 2, 1]);
    expect(merged[1].message).toBe("second updated");
  });

  it("ignores events without an id", () => {
    const merged = mergeEvents([], [eventFixture({ id: 0 }), eventFixture({ id: 4 })]);
    expect(merged.map((event) => event.id)).toEqual([4]);
  });

  it("caps the list", () => {
    const events = Array.from({ length: 10 }, (_, index) =>
      eventFixture({ id: index + 1 }),
    );
    expect(mergeEvents([], events, 3)).toHaveLength(3);
  });
});

describe("mergeEvent", () => {
  it("adds one event to the front", () => {
    const merged = mergeEvent([eventFixture({ id: 1 })], eventFixture({ id: 2 }));
    expect(merged.map((event) => event.id)).toEqual([2, 1]);
  });
});
