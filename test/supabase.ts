export function createClient() {
  return {
    from() {
      return {
        select: () => ({ data: [], error: null }),
        gte: () => this,
        lte: () => this,
        order: () => this,
        range: () => this,
      } as any;
    },
  } as any;
}
