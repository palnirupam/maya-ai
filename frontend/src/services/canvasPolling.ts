export interface CanvasLatestResponse {
  session_id?: string | null;
  updated_at?: number;
}

/**
 * Tracks canvas updates seen by one frontend instance.
 *
 * The backend returns filesystem mtimes in Unix seconds. Seeding the tracker
 * from the frontend mount time prevents a canvas left on disk by an earlier
 * app instance from being treated as a fresh update after restart.
 */
export function createCanvasPollTracker(startedAtMs = Date.now()) {
  let lastMtime = startedAtMs / 1000;

  return {
    accept(update: CanvasLatestResponse): string | null {
      const { session_id: sessionId, updated_at: updatedAt } = update;
      if (
        !sessionId
        || typeof updatedAt !== 'number'
        || !Number.isFinite(updatedAt)
        || updatedAt <= lastMtime
      ) {
        return null;
      }

      lastMtime = updatedAt;
      return sessionId;
    },
  };
}
