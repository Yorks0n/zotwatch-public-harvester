export type FacetPayload = {
  totals: { all: number; preprint: number; published: number };
  sources: Record<string, number>;
  candidate_types: Record<string, number>;
  candidate_groups: Record<string, number>;
};

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isCount(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

function isCountMap(value: unknown): value is Record<string, number> {
  return isObject(value) && Object.values(value).every(isCount);
}

function sumCounts(value: Record<string, number>): number {
  return Object.values(value).reduce((sum, count) => sum + count, 0);
}

function hasExactKeys(value: Record<string, unknown>, keys: string[]): boolean {
  const actual = Object.keys(value).sort();
  return actual.length === keys.length && actual.every((key, index) => key === keys[index]);
}

export function resolveFacetRpcResult(data: unknown, error: unknown): FacetPayload {
  if (error || !isObject(data) ||
      !hasExactKeys(data, ["candidate_groups", "candidate_types", "sources", "totals"]) ||
      !isObject(data.totals) ||
      !hasExactKeys(data.totals, ["all", "preprint", "published"]) ||
      !isCount(data.totals.all) ||
      !isCount(data.totals.preprint) ||
      !isCount(data.totals.published) ||
      !isCountMap(data.sources) ||
      !isCountMap(data.candidate_types) ||
      !isCountMap(data.candidate_groups)) {
    throw new Error("Facet aggregation unavailable");
  }

  const result: FacetPayload = {
    totals: {
      all: data.totals.all as number,
      preprint: data.totals.preprint as number,
      published: data.totals.published as number,
    },
    sources: data.sources as Record<string, number>,
    candidate_types: data.candidate_types as Record<string, number>,
    candidate_groups: data.candidate_groups as Record<string, number>,
  };
  if (result.totals.preprint + result.totals.published !== result.totals.all ||
      sumCounts(result.sources) !== result.totals.all ||
      sumCounts(result.candidate_types) !== result.totals.all ||
      sumCounts(result.candidate_groups) !== result.totals.all) {
    throw new Error("Facet aggregation unavailable");
  }
  return result;
}
