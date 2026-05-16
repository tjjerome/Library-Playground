# Review-count anomalies

Flags books whose `#grvotes` (Goodreads review count) is implausibly low
relative to other books in the same series — the symptom of a scrape that
picked up a foreign-language edition, a standalone-ebook ASIN, or a
freshly-listed edition with split review counts.

## Method

For each `(author, series)` group with ≥3 books and a series-median
`#grvotes` ≥ 2,000, a book is flagged when its count is below 5% of the
median of the *other* books in the series. Hits are then split:

- **A — confirmed errors:** main-sequence volume (integer
  `series_index`), released > 6 months ago. A flagship series entry with
  a few hundred reviews next to siblings with tens/hundreds of thousands
  is a data error, not real.
- **B — recently released (< 6 months):** low count is plausibly real;
  reviews are still accumulating. Recheck after the next scrape.
- **C — novellas / side stories:** fractional `series_index`. Genuinely
  low review volume is expected; listed only to confirm the count wasn't
  zeroed entirely.

## A. Confirmed scrape errors — fix these

| Title | Author | Series | grvotes | series median | ratio | pub date | id | isbn / note |
|---|---|---|---|---|---|---|---|---|
| Dark Age | Pierce Brown | Red Rising #5.0 | 278 | 391,501 | 0.0007 | 2019-07-29 | `4725` | 9782017140337 — French-language edition scraped |
| Siege and Storm | Leigh Bardugo | Shadow and Bone #2.0 | 773 | 850,328 | 0.0009 | 2013-04-09 | `6047` | 9781466842960 — ebook ISBN, split review count |
| Body of Evidence | Patricia Cornwell | Kay Scarpetta #2.0 | 171 | 46,044 | 0.0037 | 2001-11-05 | `1401` | 9780007643516 — UK reissue edition |
| Death on the Nile | Agatha Christie | Hercule Poirot #18.0 | 1,294 | 49,220 | 0.0263 | 2018-01-01 | `2506` | 9780008249687 — HarperCollins reissue, split count |
| Lies Weeping | Glen Cook | Chronicles of The Black Company #10.0 | 459 | 9,791 | 0.0469 | 2025-11-03 | `5173` | 9781250398000 — borderline; recheck if reissue |

## B. Recently released (< 6 months) — low count likely real, recheck later

| Title | Author | Series | grvotes | series median | ratio | pub date | id | isbn |
|---|---|---|---|---|---|---|---|---|
| Children of Strife | Adrian Tchaikovsky | Children of Time #4.0 | 1,147 | 62,152 | 0.0185 | 2026-03-16 | `6952` | 9780316587464 |
| The Keeper | Tana French | Cal Hooper #3.0 | 2,051 | 115,049 | 0.0178 | 2026-03-29 | `7049` | 9780593493472 |
| A Deadly Episode | Anthony Horowitz | A Hawthorne and Horowitz Mystery #6.0 | 1,001 | 45,578 | 0.0220 | 2026-04-27 | `7123` | 9780063305762 |
| A Long and Speaking Silence | Nghi Vo | The Singing Hills Cycle #7.0 | 103 | 9,095 | 0.0113 | 2026-05-05 | `7146` | (none) |
| Platform Decay | Martha Wells | The Murderbot Diaries #8.0 | 1,337 | 151,847 | 0.0088 | 2026-05-05 | `7150` | 9781250827005 |
| Crypt Currency | J. Zachary Pike | The Dark Profit Saga #4.0 | 2 | 7,562 | 0.0003 | 2026-05-12 | `7151` | 9781963158052 |

## C. Novellas / side stories (fractional index) — expected low, verify not zeroed

| Title | Author | Series | grvotes | series median | ratio | pub date | id | isbn |
|---|---|---|---|---|---|---|---|---|
| Out Law | Jim Butcher | The Dresden Files #18.75 | 250 | 117,290 | 0.0021 | 2026-05-05 | `7141` | 9798347030019 |
| The Book Burner's Fall | Anthony Ryan | Raven's Shadow #0.1 | 188 | 31,154 | 0.0060 | 2024-08-06 | `4497` | 1230008224736 |
| Songs of the Dark | Anthony Ryan | Raven's Shadow #3.5 | 251 | 31,154 | 0.0081 | 2020-01-01 | `5790` | 1230004766452 |
| The Lesser Devil and Other Stories | Christopher Ruocchio | Sun Eater #1.5 | 124 | 8,880 | 0.0140 | 2021-01-01 | `2680` | 9781838406301 |
| Escape | James Clavell | Asian Saga #6.5 | 666 | 43,548 | 0.0153 | 2018-09-18 | `5211` | 9781982537708 |
| The Powder Mage Novella Collection #1 | Brian McClellan | Powder Mage #0.5 | 662 | 39,957 | 0.0166 | 2016-07-10 | `5575` | 1230001223279 |
| The Daughter of Odren | Ursula K. le Guin | The Books of Earthsea #6.5 | 2,443 | 93,049 | 0.0263 | 2014-10-13 | `4712` | 9780544358386 |
| Many Are the Dead | Anthony Ryan | Raven's Shadow #0.7 | 926 | 31,154 | 0.0297 | 2018-11-01 | `5797` | 1230002704661 |
| Barren | Peter V. Brett | The Demon Cycle #5.5 | 1,973 | 42,676 | 0.0462 | 2018-09-20 | `5399` | 9780062740625 |

---

Generated 2026-05-16 against `Library.csv`. Bucket A is the actionable
list; B/C are informational. Re-run the grouping check after each scrape
patch to catch regressions.
