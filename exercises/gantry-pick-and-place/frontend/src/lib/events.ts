import type { Event } from "../types";

const DEFAULT_LIMIT = 100;

/** Merge events by id, newest first, and cap the list. */
export function mergeEvents(
  current: Event[],
  incoming: Event[],
  limit = DEFAULT_LIMIT,
): Event[] {
  const byId = new Map<number, Event>();
  for (const event of [...current, ...incoming]) {
    if (event.id > 0) byId.set(event.id, event);
  }
  return [...byId.values()]
    .sort((left, right) => right.id - left.id)
    .slice(0, limit);
}

export function mergeEvent(
  current: Event[],
  event: Event,
  limit = DEFAULT_LIMIT,
): Event[] {
  return mergeEvents(current, [event], limit);
}
