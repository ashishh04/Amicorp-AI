import { seedCards } from './mock-data';

describe('mock data', () => {
  it('gives every sample card its own ID', () => {
    const ids = seedCards().map((c) => c.id);
    const repeated = ids.filter((id, i) => ids.indexOf(id) !== i);
    expect(repeated).toEqual([]);
  });
});
