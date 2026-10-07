export type ImportanceRanking = { rank: number; feature: string; importance: number; std: number }

export const TOP_FEATURE_COUNT = 10

export function visibleImportanceRankings(rankings: readonly ImportanceRanking[], showAll: boolean): readonly ImportanceRanking[] {
  return showAll ? rankings : rankings.slice(0, TOP_FEATURE_COUNT)
}
