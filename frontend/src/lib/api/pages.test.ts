import { expect, it, vi } from 'vitest';

import { allPages } from './pages';

it('follows the cursor to the last page', async () => {
  const load = vi
    .fn()
    .mockResolvedValueOnce({ results: [1, 2], next: 'https://x.test/api/s/?cursor=abc' })
    .mockResolvedValueOnce({ results: [3], next: null });
  await expect(allPages<number>(load)).resolves.toEqual([1, 2, 3]);
  expect(load).toHaveBeenNthCalledWith(1, undefined);
  expect(load).toHaveBeenNthCalledWith(2, 'abc');
});
