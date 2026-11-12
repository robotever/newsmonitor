import test from 'node:test'
import assert from 'node:assert/strict'
import {
  ACTIVE_SOURCE_IDS,
  NEWS_ITEM_LIMIT,
  limitNewsItems,
} from '../src/api/news-policy.mjs'

test('inactive sources exclude all retired general-interest feeds', () => {
  for (const sourceId of ['cailian', 'yahoo', 'hackernews', 'github', 'producthunt', 'thepaper', '_36kr', 'reddit']) {
    assert.equal(ACTIVE_SOURCE_IDS.has(sourceId), false, sourceId)
  }
})

test('active sources include the stock-focused Sina Finance feed and exclude the blocked STCN feed', () => {
  assert.equal(ACTIVE_SOURCE_IDS.has('sinafinance'), true)
  assert.equal(ACTIVE_SOURCE_IDS.has('stcn'), false)
})

test('every source is limited to ten news items', () => {
  const items = Array.from({ length: 15 }, (_, index) => ({ id: index }))

  assert.equal(NEWS_ITEM_LIMIT, 10)
  assert.deepEqual(limitNewsItems(items), items.slice(0, 10))
})
