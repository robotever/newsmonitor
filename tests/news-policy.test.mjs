import test from 'node:test'
import assert from 'node:assert/strict'
import {
  ACTIVE_SOURCE_IDS,
  NEWS_ITEM_LIMIT,
  limitNewsItems,
} from '../src/api/news-policy.mjs'

test('inactive sources exclude Cailian and Yahoo Finance', () => {
  assert.equal(ACTIVE_SOURCE_IDS.has('cailian'), false)
  assert.equal(ACTIVE_SOURCE_IDS.has('yahoo'), false)
})

test('every source is limited to ten news items', () => {
  const items = Array.from({ length: 15 }, (_, index) => ({ id: index }))

  assert.equal(NEWS_ITEM_LIMIT, 10)
  assert.deepEqual(limitNewsItems(items), items.slice(0, 10))
})
