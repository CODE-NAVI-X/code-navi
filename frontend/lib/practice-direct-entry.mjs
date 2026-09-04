/**
 * Keep the direct-entry state rules independent from the page shell so they
 * remain executable without mounting the whole Next application.
 */
export function directEntryRequestKey(context, learnerId) {
  return JSON.stringify({
    learnerId,
    sourceSessionId: context.source_session_id,
    knowledgePoints: context.knowledge_points.map((point) => [
      point.name,
      point.source_ref,
      point.mastery,
    ]),
    objective: context.objective,
    notesSummary: context.notes_summary,
  });
}

/**
 * React Strict Mode replays mount effects in development. Coalesce the
 * catalog/gateway load for the same immutable context while still allowing a
 * changed context to start a fresh request.
 */
export function createDirectEntryRequestCache() {
  /** @type {{ key: string, value: unknown } | null} */
  let activeRequest = null;

  return {
    /**
     * @template T
     * @param {string} key
     * @param {() => T} createRequest
     * @returns {T}
     */
    getOrCreate(key, createRequest) {
      if (!activeRequest || activeRequest.key !== key) {
        activeRequest = { key, value: createRequest() };
      }
      return /** @type {T} */ (activeRequest.value);
    },
  };
}

export function shouldShowDirectStructureView({
  view,
  hasDirectContext,
  directEntryDismissed,
}) {
  return view === "structure" || (hasDirectContext && !directEntryDismissed);
}

export function canAdvanceContextStructureItem({ hasNext, explainOnly, graded }) {
  return hasNext && (explainOnly || graded);
}
