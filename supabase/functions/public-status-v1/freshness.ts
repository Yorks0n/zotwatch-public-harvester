export type Run = {
  source: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  window_start: string | null;
  window_end: string | null;
};

export function sourceRunStatus(runs: Run[], nowMs: number) {
  const latestRunBySource = new Map<string, Run>();
  const latestSuccessBySource = new Map<string, Run>();
  for (const run of runs) {
    const previous = latestRunBySource.get(run.source);
    if (!previous || (run.started_at ?? "") > (previous.started_at ?? "")) {
      latestRunBySource.set(run.source, run);
    }
    const previousSuccess = latestSuccessBySource.get(run.source);
    if (run.status === "success" && run.window_end &&
        (!previousSuccess || run.window_end > (previousSuccess.window_end ?? ""))) {
      latestSuccessBySource.set(run.source, run);
    }
  }
  return (sourceId: string) => {
    const latestRun = latestRunBySource.get(sourceId) ?? null;
    const lastSuccessfulRun = latestSuccessBySource.get(sourceId) ?? null;
    const freshThrough = lastSuccessfulRun?.window_end ?? null;
    const lagSeconds = freshThrough === null ? null : Math.max(
      0, Math.floor((nowMs - Date.parse(freshThrough)) / 1000),
    );
    return {
      latest_run: latestRun,
      last_successful_run: lastSuccessfulRun,
      freshness: {
        state: freshThrough === null ? "no_success" : "covered",
        fresh_through: freshThrough,
        lag_seconds: lagSeconds,
      },
    };
  };
}
