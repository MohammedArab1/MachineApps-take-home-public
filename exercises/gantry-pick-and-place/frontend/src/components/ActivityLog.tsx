import type { Event } from "../types";
import { formatTime, levelTone } from "../lib/format";

interface ActivityLogProps {
  events: Event[];
  onClear: () => void;
}

export function ActivityLog({ events, onClear }: ActivityLogProps) {
  return (
    <section className="panel activity" aria-labelledby="activity-heading">
      <div className="panel-heading">
        <div>
          <h2 id="activity-heading">Activity</h2>
          <p className="panel-subtitle">Newest first · last 100 events</p>
        </div>
        <button
          type="button"
          className="button button--ghost button--small"
          onClick={onClear}
          disabled={events.length === 0}
        >
          Clear
        </button>
      </div>

      {events.length === 0 ? (
        <p className="empty-state" data-testid="activity-empty">
          No events yet. Start the sequence or home the robot.
        </p>
      ) : (
        <ol className="event-list" data-testid="activity-list">
          {events.map((event) => (
            <li
              className={`event event--${levelTone(event.level)}`}
              key={event.id}
            >
              <span className="event-level">{event.level}</span>
              <span className="event-time">{formatTime(event.timestamp)}</span>
              <div className="event-body">
                <strong>{event.message}</strong>
                {event.detail && <p>{event.detail}</p>}
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
