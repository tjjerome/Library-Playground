# `comparable_books` quality review queue

_Generated 2026-05-04 from `Library_Catalog.sqlite`._

Implements RECOMPOSITION_PLAN §6.7.  Comp links pre-filtered
to: comp resolves to a catalog book AND the two books share
**zero** taste vectors AND **zero** combined signal/theme
overlap.  Suggested action is rule-based:

- **drop**: zero overlap of any kind AND primary_genre
  doesn't even match.  Almost certainly the wrong comp.
- **review**: zero overlap but same primary_genre.  Often a
  weak genre-only comp — maintainer judgement on whether to
  drop or revise.

**418 flags total** (81 drop-suggested, 337 review-suggested).

Sort: drop-suggested first, then by combined Goodreads rating
ascending (weakest-rated pairs surface first).  Comps where
the cited book itself isn't catalogued are excluded — those
can't be quality-scored without per-book signals.

## Drop-suggested (genre mismatch + zero overlap) (81)

| Source book | Comp | Source genre | Comp genre | Ratings (a/b) |
|---|---|---|---|---|
| From a Buick 8 — Stephen King | The Tommyknockers — Stephen King | Horror | Science Fiction | 3.5 / 3.6 |
| The Tommyknockers — Stephen King | From a Buick 8 — Stephen King | Science Fiction | Horror | 3.6 / 3.5 |
| Mexico — James A. Michener | The Old Man and the Sea — Ernest Hemingway | Historical Fiction | Literary Fiction | 3.7 / 3.8 |
| Among Others — Jo Walton | My Real Children — Jo Walton | Fantasy | Science Fiction | 3.7 / 3.8 |
| My Real Children — Jo Walton | Among Others — Jo Walton | Science Fiction | Fantasy | 3.8 / 3.7 |
| Dinner at Deviant's Palace — Tim Powers | On Stranger Tides — Tim Powers | Science Fiction | Fantasy | 3.7 / 3.8 |
| On Stranger Tides — Tim Powers | Dinner at Deviant's Palace — Tim Powers | Fantasy | Science Fiction | 3.8 / 3.7 |
| Dogs of War — Frederick Forsyth | Congo — Michael Crichton | Crime Fiction | Science Fiction | 4.0 / 3.6 |
| Congo — Michael Crichton | Dogs of War — Frederick Forsyth | Science Fiction | Crime Fiction | 3.6 / 4.0 |
| Dinner at Deviant's Palace — Tim Powers | The Anubis Gates — Tim Powers | Science Fiction | Fantasy | 3.7 / 3.9 |
| The Anubis Gates — Tim Powers | Dinner at Deviant's Palace — Tim Powers | Fantasy | Science Fiction | 3.9 / 3.7 |
| Ra — qntm | The Magicians — Lev Grossman | Science Fiction | Fantasy | 4.1 / 3.5 |
| The War of the Worlds — H. G. Wells | Frankenstein — Mary Shelley | Science Fiction | Horror | 3.8 / 3.9 |
| Frankenstein — Mary Shelley | The War of the Worlds — H. G. Wells | Horror | Science Fiction | 3.9 / 3.8 |
| Deeper — Jeff Long | The Road — Cormac McCarthy | Horror | Literary Fiction | 3.7 / 4.0 |
| Evil at Heart — Chelsea Cain | American Psycho — Bret Easton Ellis | Crime Fiction | Literary Fiction | 4.0 / 3.8 |
| Intensity — Dean Koontz | Sole Survivor — Dean Koontz | Horror | Crime Fiction | 4.0 / 3.8 |
| Sole Survivor — Dean Koontz | Intensity — Dean Koontz | Crime Fiction | Horror | 3.8 / 4.0 |
| Angelmaker — Nick Harkaway | Tigerman — Nick Harkaway | Science Fiction | Literary Fiction | 3.9 / 3.9 |
| Tigerman — Nick Harkaway | Angelmaker — Nick Harkaway | Literary Fiction | Science Fiction | 3.9 / 3.9 |
| Babel — R. F. Kuang | Yellowface — R. F. Kuang | Fantasy | Literary Fiction | 4.1 / 3.7 |
| Yellowface — R. F. Kuang | Babel — R. F. Kuang | Literary Fiction | Fantasy | 3.7 / 4.1 |
| Never Flinch — Stephen King | The Outsider — Stephen King | Crime Fiction | Horror | 3.8 / 4.0 |
| The Outsider — Stephen King | Never Flinch — Stephen King | Horror | Crime Fiction | 4.0 / 3.8 |
| Vengeful — V. E. Schwab | Warm Up — V. E. Schwab | Fantasy | Science Fiction | 4.1 / 3.7 |
| Warm Up — V. E. Schwab | Vengeful — V. E. Schwab | Science Fiction | Fantasy | 3.7 / 4.1 |
| Conspiracies — F. Paul Wilson | Blood Music — Greg Bear | Horror | Science Fiction | 4.1 / 3.8 |
| Blood Music — Greg Bear | Conspiracies — F. Paul Wilson | Science Fiction | Horror | 3.8 / 4.1 |
| I Have No Mouth and I Must Scream — Harlan Ellison | The Nothing That Is — Kyle Winkler | Science Fiction | Horror | 4.0 / 3.9 |
| The Nothing That Is — Kyle Winkler | I Have No Mouth and I Must Scream — Harlan Ellison | Horror | Science Fiction | 3.9 / 4.0 |
| Angelmaker — Nick Harkaway | Declare — Tim Powers | Science Fiction | Crime Fiction | 3.9 / 4.0 |
| Dreamsongs, Volume I — George R. R. Martin | Night Shift — Stephen King | Science Fiction | Horror | 4.0 / 4.0 |
| Dreamsongs, Volume II — George R. R. Martin | Night Shift — Stephen King | Science Fiction | Horror | 4.0 / 4.0 |
| Crash — J.G. Ballard | Altered Carbon — Richard K. Morgan | Literary Fiction | Science Fiction | 4.0 / 4.0 |
| The Gunslinger — Stephen King | Blood Meridian — Cormac McCarthy | Fantasy | Literary Fiction | 3.9 / 4.1 |
| The Long Walk — Stephen King (as Richard Bachman) | The Road — Cormac McCarthy | Horror | Literary Fiction | 4.0 / 4.0 |
| The Shotgun Rule — Charlie Huston | Trainspotting — Irvine Welsh | Crime Fiction | Literary Fiction | 4.0 / 4.1 |
| Infinite Jest — David Foster Wallace | Valis — Philip K. Dick | Literary Fiction | Science Fiction | 4.2 / 3.9 |
| Hellmouth — Giles Kristian | Lancelot — Giles Kristian | Horror | Historical Fiction | 3.9 / 4.2 |
| Lancelot — Giles Kristian | Hellmouth — Giles Kristian | Historical Fiction | Horror | 4.2 / 3.9 |
| Shift — Hugh Howey | The Road — Cormac McCarthy | Science Fiction | Literary Fiction | 4.1 / 4.0 |
| Trainspotting — Irvine Welsh | The Shotgun Rule — Charlie Huston | Literary Fiction | Crime Fiction | 4.1 / 4.0 |
| Wicked Problems — Max Gladstone | This Is How You Lose the Time War — Amal El-Mohtar & Max Gladstone | Fantasy | Science Fiction | 4.3 / 3.8 |
| How Green This Land, How Blue This Sea — Mira Grant | All Systems Red — Martha Wells | Horror | Science Fiction | 4.0 / 4.1 |
| Valis — Philip K. Dick | Infinite Jest — David Foster Wallace | Science Fiction | Literary Fiction | 3.9 / 4.2 |
| Pet Sematary — Stephen King | The Road — Cormac McCarthy | Horror | Literary Fiction | 4.1 / 4.0 |
| Fever Dream — Douglas Preston & Lincoln Child | The Alienist — Caleb Carr | Crime Fiction | Historical Fiction | 4.1 / 4.1 |
| The Children of Eve — John Connolly | Doctor Sleep — Stephen King | Crime Fiction | Horror | 4.1 / 4.1 |
| The River of Souls — Robert McCammon | The Alienist — Caleb Carr | Crime Fiction | Historical Fiction | 4.1 / 4.1 |
| Doctor Sleep — Stephen King | The Children of Eve — John Connolly | Horror | Crime Fiction | 4.1 / 4.1 |
| The Lathe of Heaven — Ursula K. Le Guin | There Is No Antimemetics Division — qntm | Science Fiction | Horror | 4.1 / 4.1 |
| There Is No Antimemetics Division — qntm | The Lathe of Heaven — Ursula K. Le Guin | Horror | Science Fiction | 4.1 / 4.1 |
| Room — Emma Donoghue | Misery — Stephen King | Literary Fiction | Horror | 4.1 / 4.2 |
| The Art of Racing in the Rain — Garth Stein | Water for Elephants — Sara Gruen | Literary Fiction | Historical Fiction | 4.2 / 4.1 |
| Dust — Hugh Howey | Station Eleven — Emily St. John Mandel | Science Fiction | Literary Fiction | 4.2 / 4.1 |
| Wool — Hugh Howey | Station Eleven — Emily St. John Mandel | Science Fiction | Literary Fiction | 4.2 / 4.1 |
| Lie Down With Lions — Ken Follett | The Kite Runner — Khaled Hosseini | Crime Fiction | Historical Fiction | 3.9 / 4.4 |
| Wildcard — Marie Lu | All the Light We Cannot See — Anthony Doerr | Science Fiction | Historical Fiction | 4.0 / 4.3 |
| Parable of the Sower — Octavia E. Butler | Station Eleven — Emily St. John Mandel | Science Fiction | Literary Fiction | 4.2 / 4.1 |
| Water for Elephants — Sara Gruen | The Art of Racing in the Rain — Garth Stein | Historical Fiction | Literary Fiction | 4.1 / 4.2 |
| Misery — Stephen King | Room — Emma Donoghue | Horror | Literary Fiction | 4.2 / 4.1 |
| Unreconciled — W. Michael Gear | The Road — Cormac McCarthy | Science Fiction | Literary Fiction | 4.3 / 4.0 |
| The Peacekeeper — B. L. Blanchard | Lonesome Dove — Larry McMurtry | Crime Fiction | Historical Fiction | 3.8 / 4.6 |
| The Alienist — Caleb Carr | The Queen of Bedlam — Robert McCammon | Historical Fiction | Crime Fiction | 4.1 / 4.3 |
| The Alienist — Caleb Carr | The Cabinet of Curiosities — Douglas Preston & Lincoln Child | Historical Fiction | Crime Fiction | 4.1 / 4.3 |
| The Cabinet of Curiosities — Douglas Preston & Lincoln Child | The Alienist — Caleb Carr | Crime Fiction | Historical Fiction | 4.3 / 4.1 |
| Four Roads Cross — Max Gladstone | A Memory Called Empire — Arkady Martine | Fantasy | Science Fiction | 4.3 / 4.1 |
| The Queen of Bedlam — Robert McCammon | The Alienist — Caleb Carr | Crime Fiction | Historical Fiction | 4.3 / 4.1 |
| The Expert System's Brother — Adrian Tchaikovsky | Tomb of Merellien — J. R. Snyder | Science Fiction | Fantasy | 3.9 / 4.5 |
| Tomb of Merellien — J. R. Snyder | The Expert System's Brother — Adrian Tchaikovsky | Fantasy | Science Fiction | 4.5 / 3.9 |
| Different Seasons — Stephen King | If It Bleeds — Stephen King | Literary Fiction | Horror | 4.4 / 4.0 |
| If It Bleeds — Stephen King | Different Seasons — Stephen King | Horror | Literary Fiction | 4.0 / 4.4 |
| Where the Heart Is — Billie Letts | The Help — Kathryn Stockett | Literary Fiction | Historical Fiction | 4.0 / 4.5 |
| Sooley — John Grisham | The Kite Runner — Khaled Hosseini | Literary Fiction | Historical Fiction | 4.1 / 4.4 |
| The Help — Kathryn Stockett | Where the Heart Is — Billie Letts | Historical Fiction | Literary Fiction | 4.5 / 4.0 |
| Wolves of the Calla — Stephen King | The Stand — Stephen King | Fantasy | Horror | 4.2 / 4.3 |
| Empire of Silence — Christopher Ruocchio | A Memory of Light — Robert Jordan & Brandon Sanderson | Science Fiction | Fantasy | 4.0 / 4.6 |
| Suelen — Rachel Neumeier | A Memory Called Empire — Arkady Martine | Fantasy | Science Fiction | 4.5 / 4.1 |
| Seal of the Worm — Adrian Tchaikovsky | Children of Time — Adrian Tchaikovsky | Fantasy | Science Fiction | 4.4 / 4.3 |
| Blood Meridian — Cormac McCarthy | Lonesome Dove — Larry McMurtry | Literary Fiction | Historical Fiction | 4.1 / 4.6 |
| Morning Star — Pierce Brown | The Name of the Wind — Patrick Rothfuss | Science Fiction | Fantasy | 4.5 / 4.5 |

## Review-suggested (same genre, zero overlap) (337)

| Source book | Comp | Source genre | Comp genre | Ratings (a/b) |
|---|---|---|---|---|
| Live and Let Die — Ian Fleming | The Spy Who Loved Me — Ian Fleming | Crime Fiction | Crime Fiction | 3.6 / 3.4 |
| The Spy Who Loved Me — Ian Fleming | Live and Let Die — Ian Fleming | Crime Fiction | Crime Fiction | 3.4 / 3.6 |
| For Your Eyes Only — Ian Fleming | The Spy Who Loved Me — Ian Fleming | Crime Fiction | Crime Fiction | 3.7 / 3.4 |
| The Spy Who Loved Me — Ian Fleming | For Your Eyes Only — Ian Fleming | Crime Fiction | Crime Fiction | 3.4 / 3.7 |
| The Subtle Art of Folding Space — John Chu | This Is How You Lose the Time War — Amal El-Mohtar & Max Gladstone | Science Fiction | Science Fiction | 3.3 / 3.8 |
| The Magicians — Lev Grossman | Katabasis — R. F. Kuang | Fantasy | Fantasy | 3.5 / 3.7 |
| Katabasis — R. F. Kuang | The Magicians — Lev Grossman | Fantasy | Fantasy | 3.7 / 3.5 |
| The Man With the Golden Gun — Ian Fleming | You Only Live Twice — Ian Fleming | Crime Fiction | Crime Fiction | 3.6 / 3.7 |
| You Only Live Twice — Ian Fleming | The Man With the Golden Gun — Ian Fleming | Crime Fiction | Crime Fiction | 3.7 / 3.6 |
| Fated — Benedict Jacka | The Magicians — Lev Grossman | Fantasy | Fantasy | 3.9 / 3.5 |
| Six Months, Three Days — Charlie Jane Anders | The Fermi Paradox Is Our Business Model — Charlie Jane Anders | Science Fiction | Science Fiction | 3.7 / 3.7 |
| The Fermi Paradox Is Our Business Model — Charlie Jane Anders | Six Months, Three Days — Charlie Jane Anders | Science Fiction | Science Fiction | 3.7 / 3.7 |
| The Death Cure — James Dashner | Allegiant — Veronica Roth | Science Fiction | Science Fiction | 3.8 / 3.6 |
| Red Claw — Philip Palmer | Annihilation — Jeff VanderMeer | Science Fiction | Science Fiction | 3.6 / 3.8 |
| The Preacher — Rob J. Hayes | Never Die — Rob J. Hayes | Fantasy | Fantasy | 3.5 / 3.9 |
| Murder in the House of Omari — Taku Ashibe | Death on the Nile — Agatha Christie | Crime Fiction | Crime Fiction | 3.4 / 4.0 |
| Allegiant — Veronica Roth | The Death Cure — James Dashner | Science Fiction | Science Fiction | 3.6 / 3.8 |
| Dead Man's Folly — Agatha Christie | Third Girl — Agatha Christie | Crime Fiction | Crime Fiction | 3.8 / 3.7 |
| Third Girl — Agatha Christie | Dead Man's Folly — Agatha Christie | Crime Fiction | Crime Fiction | 3.7 / 3.8 |
| The Incandescent — Emily Tesh | The Magicians — Lev Grossman | Fantasy | Fantasy | 4.0 / 3.5 |
| Gamechanger — L. X. Beckett | Rainbows End — Vernor Vinge | Science Fiction | Science Fiction | 3.7 / 3.8 |
| Destiny's Way — Walter Jon Williams | Ylesia — Walter Jon Williams | Science Fiction | Science Fiction | 3.9 / 3.6 |
| Ylesia — Walter Jon Williams | Destiny's Way — Walter Jon Williams | Science Fiction | Science Fiction | 3.6 / 3.9 |
| Sad Cypress — Agatha Christie | Taken at the Flood — Agatha Christie | Crime Fiction | Crime Fiction | 3.9 / 3.7 |
| Taken at the Flood — Agatha Christie | Sad Cypress — Agatha Christie | Crime Fiction | Crime Fiction | 3.7 / 3.9 |
| Rebel Rising — Beth Revis | The Princess and the Scoundrel — Beth Revis | Science Fiction | Science Fiction | 3.9 / 3.7 |
| The Princess and the Scoundrel — Beth Revis | Rebel Rising — Beth Revis | Science Fiction | Science Fiction | 3.7 / 3.9 |
| Incensed — Ed Lin | The Devotion of Suspect X — Keigo Higashino | Crime Fiction | Crime Fiction | 3.4 / 4.2 |
| Edge of Victory I: Conquest — Greg Keyes | Edge of Victory II: Rebirth — Greg Keyes | Science Fiction | Science Fiction | 3.8 / 3.8 |
| Edge of Victory II: Rebirth — Greg Keyes | Edge of Victory I: Conquest — Greg Keyes | Science Fiction | Science Fiction | 3.8 / 3.8 |
| Edge of Victory II: Rebirth — Greg Keyes | The Final Prophecy — Greg Keyes | Science Fiction | Science Fiction | 3.8 / 3.8 |
| The Final Prophecy — Greg Keyes | Edge of Victory II: Rebirth — Greg Keyes | Science Fiction | Science Fiction | 3.8 / 3.8 |
| Fire, Burn! — John Dickson Carr | The Bride of Newgate — John Dickson Carr | Crime Fiction | Crime Fiction | 3.8 / 3.8 |
| The Bride of Newgate — John Dickson Carr | Fire, Burn! — John Dickson Carr | Crime Fiction | Crime Fiction | 3.8 / 3.8 |
| The Bacta War — Michael A. Stackpole | Assault at Selonia — Roger Macbride Allen | Science Fiction | Science Fiction | 4.0 / 3.6 |
| Assault at Selonia — Roger Macbride Allen | The Bacta War — Michael A. Stackpole | Science Fiction | Science Fiction | 3.6 / 4.0 |
| Camp Damascus — Chuck Tingle | The Haunting of Hill House — Shirley Jackson | Horror | Horror | 3.9 / 3.8 |
| Wise Blood — Flannery O'Connor | The Sound and the Fury — William Faulkner | Literary Fiction | Literary Fiction | 3.8 / 3.9 |
| The Final Prophecy — Greg Keyes | Destiny's Way — Walter Jon Williams | Science Fiction | Science Fiction | 3.8 / 3.9 |
| What We Can Know — Ian McEwan | Never Let Me Go — Kazuo Ishiguro | Literary Fiction | Literary Fiction | 3.9 / 3.8 |
| Labyrinth of Evil — James Luceno | The Rise of Darth Vader — James Luceno | Science Fiction | Science Fiction | 3.8 / 3.9 |
| The Rise of Darth Vader — James Luceno | Labyrinth of Evil — James Luceno | Science Fiction | Science Fiction | 3.9 / 3.8 |
| Kenobi — John Jackson Miller | Knight Errant — John Jackson Miller | Science Fiction | Science Fiction | 4.1 / 3.6 |
| Knight Errant — John Jackson Miller | Kenobi — John Jackson Miller | Science Fiction | Science Fiction | 3.6 / 4.1 |
| Destiny's Way — Walter Jon Williams | The Final Prophecy — Greg Keyes | Science Fiction | Science Fiction | 3.9 / 3.8 |
| Startide Rising — David Brin | Sundiver — David Brin | Science Fiction | Science Fiction | 4.0 / 3.7 |
| Sundiver — David Brin | Startide Rising — David Brin | Science Fiction | Science Fiction | 3.7 / 4.0 |
| Beside the Syrian Sea — James Wolff | Slow Horses — Mick Herron | Crime Fiction | Crime Fiction | 3.7 / 4.0 |
| A Passage of Stars — Kate Elliott | Revelation Space — Alastair Reynolds | Science Fiction | Science Fiction | 3.7 / 4.0 |
| A Thread of Grace — Mary Doria Russell | Dreamers of the Day — Mary Doria Russell | Historical Fiction | Historical Fiction | 4.0 / 3.7 |
| Dreamers of the Day — Mary Doria Russell | A Thread of Grace — Mary Doria Russell | Historical Fiction | Historical Fiction | 3.7 / 4.0 |
| Curtain: Poirot's Last Case — Agatha Christie | The Clocks — Agatha Christie | Crime Fiction | Crime Fiction | 4.1 / 3.7 |
| Evil Under the Sun — Agatha Christie | The Hollow — Agatha Christie | Crime Fiction | Crime Fiction | 4.0 / 3.8 |
| The Clocks — Agatha Christie | Curtain: Poirot's Last Case — Agatha Christie | Crime Fiction | Crime Fiction | 3.7 / 4.1 |
| The Hollow — Agatha Christie | Evil Under the Sun — Agatha Christie | Crime Fiction | Crime Fiction | 3.8 / 4.0 |
| Ascension — Christie Golden | Omen — Christie Golden | Science Fiction | Science Fiction | 3.9 / 3.9 |
| Omen — Christie Golden | Outcast — Aaron Allston | Science Fiction | Science Fiction | 3.9 / 3.9 |
| Omen — Christie Golden | Abyss — Troy Denning | Science Fiction | Science Fiction | 3.9 / 3.9 |
| Omen — Christie Golden | Ascension — Christie Golden | Science Fiction | Science Fiction | 3.9 / 3.9 |
| For Whom the Bell Tolls — Ernest Hemingway | The Sun Also Rises — Ernest Hemingway | Literary Fiction | Literary Fiction | 4.0 / 3.8 |
| The Sun Also Rises — Ernest Hemingway | For Whom the Bell Tolls — Ernest Hemingway | Literary Fiction | Literary Fiction | 3.8 / 4.0 |
| Airframe — Michael Crichton | The Hunt for Red October — Tom Clancy | Crime Fiction | Crime Fiction | 3.7 / 4.1 |
| Manslayer — Nathan Long | Giantslayer — William King | Fantasy | Fantasy | 3.9 / 3.9 |
| I Married a Communist — Philip Roth | The Human Stain — Philip Roth | Literary Fiction | Literary Fiction | 3.9 / 3.9 |
| The Human Stain — Philip Roth | I Married a Communist — Philip Roth | Literary Fiction | Literary Fiction | 3.9 / 3.9 |
| The Thursday Murder Club — Richard Osman | Magpie Murders — Anthony Horowitz | Crime Fiction | Crime Fiction | 3.9 / 3.9 |
| The Trespasser — Tana French | In the Woods — Tana French | Crime Fiction | Crime Fiction | 4.0 / 3.8 |
| Abyss — Troy Denning | Omen — Christie Golden | Science Fiction | Science Fiction | 3.9 / 3.9 |
| As I Lay Dying — William Faulkner | Blood Meridian — Cormac McCarthy | Literary Fiction | Literary Fiction | 3.7 / 4.1 |
| Giantslayer — William King | Manslayer — Nathan Long | Fantasy | Fantasy | 3.9 / 3.9 |
| The Late Show — Michael Connelly | In the Woods — Tana French | Crime Fiction | Crime Fiction | 4.1 / 3.8 |
| And Put Away Childish Things — Adrian Tchaikovsky | Piranesi — Susanna Clarke | Fantasy | Fantasy | 3.7 / 4.2 |
| Ascension — Christie Golden | Apocalypse — Troy Denning | Science Fiction | Science Fiction | 3.9 / 4.0 |
| Time and Again — Clifford D. Simak | Way Station — Clifford D. Simak | Science Fiction | Science Fiction | 3.9 / 4.0 |
| Way Station — Clifford D. Simak | Time and Again — Clifford D. Simak | Science Fiction | Science Fiction | 4.0 / 3.9 |
| Backcloth for a Crown Additional — Dan Abnett | Malleus — Dan Abnett | Science Fiction | Science Fiction | 3.7 / 4.2 |
| Malleus — Dan Abnett | Backcloth for a Crown Additional — Dan Abnett | Science Fiction | Science Fiction | 4.2 / 3.7 |
| Drowned Country — Emily Tesh | A Deadly Education — Naomi Novik | Fantasy | Fantasy | 4.0 / 3.9 |
| Assassins of Brush and Blade — J. C. Kang | The Bone Shard Daughter — Andrea Stewart | Fantasy | Fantasy | 3.9 / 4.0 |
| Among Others — Jo Walton | Piranesi — Susanna Clarke | Fantasy | Fantasy | 3.7 / 4.2 |
| A Confederacy of Dunces — John Kennedy Toole | Catch-22 — Joseph Heller | Literary Fiction | Literary Fiction | 3.9 / 4.0 |
| Catch-22 — Joseph Heller | A Confederacy of Dunces — John Kennedy Toole | Literary Fiction | Literary Fiction | 4.0 / 3.9 |
| The Daughter of Time — Josephine Tey | The Singing Sands — Josephine Tey | Crime Fiction | Crime Fiction | 3.9 / 4.0 |
| The Singing Sands — Josephine Tey | The Daughter of Time — Josephine Tey | Crime Fiction | Crime Fiction | 4.0 / 3.9 |
| Prosper's Demon — K. J. Parker | Piranesi — Susanna Clarke | Fantasy | Fantasy | 3.7 / 4.2 |
| Red Mars — Kim Stanley Robinson | The Time Door — Shannon McDermott | Science Fiction | Science Fiction | 3.9 / 4.0 |
| The Beekeeper's Apprentice — Laurie R. King | The Thursday Murder Club — Richard Osman | Crime Fiction | Crime Fiction | 4.0 / 3.9 |
| The City, Not Long After — Pat Murphy | The Shadow Hunter — Pat Murphy | Science Fiction | Science Fiction | 3.9 / 4.0 |
| The Shadow Hunter — Pat Murphy | The City, Not Long After — Pat Murphy | Science Fiction | Science Fiction | 4.0 / 3.9 |
| The Thursday Murder Club — Richard Osman | The Beekeeper's Apprentice — Laurie R. King | Crime Fiction | Crime Fiction | 3.9 / 4.0 |
| The Time Door — Shannon McDermott | Red Mars — Kim Stanley Robinson | Science Fiction | Science Fiction | 4.0 / 3.9 |
| Last Call — Tim Powers | The Drawing of the Dark — Tim Powers | Fantasy | Fantasy | 4.0 / 3.9 |
| The Drawing of the Dark — Tim Powers | Last Call — Tim Powers | Fantasy | Fantasy | 3.9 / 4.0 |
| Apocalypse — Troy Denning | Ascension — Christie Golden | Science Fiction | Science Fiction | 4.0 / 3.9 |
| Inferno — Troy Denning | Invincible — Troy Denning | Science Fiction | Science Fiction | 3.9 / 4.0 |
| Invincible — Troy Denning | Inferno — Troy Denning | Science Fiction | Science Fiction | 4.0 / 3.9 |
| Gunmetal Gods — Zamil Akhtar | Lightblade — Zamil Akhtar | Fantasy | Fantasy | 3.9 / 4.0 |
| Lightblade — Zamil Akhtar | Gunmetal Gods — Zamil Akhtar | Fantasy | Fantasy | 4.0 / 3.9 |
| The Ballad of the Borag-I — A. P. Beswick | Piranesi — Susanna Clarke | Fantasy | Fantasy | 3.8 / 4.2 |
| Cage of Souls — Adrian Tchaikovsky | Day of Ascension — Adrian Tchaikovsky | Science Fiction | Science Fiction | 4.1 / 3.9 |
| Day of Ascension — Adrian Tchaikovsky | Cage of Souls — Adrian Tchaikovsky | Science Fiction | Science Fiction | 3.9 / 4.1 |
| The Ten Thousand Doors of January — Alix E. Harrow | The Bone Shard Daughter — Andrea Stewart | Fantasy | Fantasy | 4.0 / 4.0 |
| The Bone Shard Daughter — Andrea Stewart | The Ten Thousand Doors of January — Alix E. Harrow | Fantasy | Fantasy | 4.0 / 4.0 |
| Dragonsteel Prime — Brandon Sanderson | Elantris — Brandon Sanderson | Fantasy | Fantasy | 3.8 / 4.2 |
| Elantris — Brandon Sanderson | Dragonsteel Prime — Brandon Sanderson | Fantasy | Fantasy | 4.2 / 3.8 |
| Even Greater Mistakes — Charlie Jane Anders | Stories of Your Life and Others — Ted Chiang | Science Fiction | Science Fiction | 3.8 / 4.2 |
| Ilium — Dan Simmons | Blindsight — Peter Watts | Science Fiction | Science Fiction | 4.0 / 4.0 |
| The Martians: The True Story of an Alien Craze That Captured Turn-Of-The-Century America — David Baron | The Radium Girls — Kate Moore | Nonfiction | Nonfiction | 3.8 / 4.2 |
| Monk's Hood — Ellis Peters | Mistress of the Art of Death — Ariana Franklin | Crime Fiction | Crime Fiction | 4.1 / 3.9 |
| The Confession of Brother Haluin — Ellis Peters | Mistress of the Art of Death — Ariana Franklin | Crime Fiction | Crime Fiction | 4.1 / 3.9 |
| The Devil's Novice — Ellis Peters | Mistress of the Art of Death — Ariana Franklin | Crime Fiction | Crime Fiction | 4.1 / 3.9 |
| Untethered Sky — Fonda Lee | The Goblin Emperor — Katherine Addison | Fantasy | Fantasy | 3.9 / 4.1 |
| Uncle Tom's Cabin; or, Life Among the Lowly — Harriet Beecher Stowe | The Underground Railroad — Colson Whitehead | Historical Fiction | Historical Fiction | 3.9 / 4.1 |
| The Starless Crown — James Rollins | The Blade Itself — Joe Abercrombie | Fantasy | Fantasy | 3.8 / 4.2 |
| Honor Among Thieves — James S. A. Corey | Heir to the Empire — Timothy Zahn | Science Fiction | Science Fiction | 3.8 / 4.2 |
| The Radium Girls — Kate Moore | The Martians: The True Story of an Alien Craze That Captured Turn-Of-The-Century America — David Baron | Nonfiction | Nonfiction | 4.2 / 3.8 |
| Red Sister — Mark Lawrence | The Girl and the Stars — Mark Lawrence | Fantasy | Fantasy | 4.2 / 3.8 |
| The Girl and the Stars — Mark Lawrence | Red Sister — Mark Lawrence | Fantasy | Fantasy | 3.8 / 4.2 |
| World War Z: An Oral History of the Zombie War — Max Brooks | The Passage — Justin Cronin | Horror | Horror | 4.0 / 4.0 |
| Dark Sacred Night — Michael Connelly | In the Woods — Tana French | Crime Fiction | Crime Fiction | 4.2 / 3.8 |
| Aching God — Mike Shel | Prince of Thorns — Mark Lawrence | Fantasy | Fantasy | 4.2 / 3.8 |
| Echoes of the Tomb — Sandy Mitchell | The Beguiling — Sandy Mitchell | Science Fiction | Science Fiction | 4.0 / 4.0 |
| The Beguiling — Sandy Mitchell | Echoes of the Tomb — Sandy Mitchell | Science Fiction | Science Fiction | 4.0 / 4.0 |
| Heir to the Empire — Timothy Zahn | Scoundrels — Timothy Zahn | Science Fiction | Science Fiction | 4.2 / 3.8 |
| Scoundrels — Timothy Zahn | Heir to the Empire — Timothy Zahn | Science Fiction | Science Fiction | 3.8 / 4.2 |
| The Hamlet — William Faulkner | Blood Meridian — Cormac McCarthy | Literary Fiction | Literary Fiction | 3.9 / 4.1 |
| Of Thieves and Shadows — B. S. H. Garcia | A Deadly Education — Naomi Novik | Fantasy | Fantasy | 4.2 / 3.9 |
| The Horse and His Boy — C. S. Lewis | The Lion, the Witch and the Wardrobe — C.S. Lewis | Fantasy | Fantasy | 3.9 / 4.2 |
| The Lion, the Witch and the Wardrobe — C.S. Lewis | The Horse and His Boy — C. S. Lewis | Fantasy | Fantasy | 4.2 / 3.9 |
| Blood Meridian — Cormac McCarthy | Absalom, Absalom! — William Faulkner | Literary Fiction | Literary Fiction | 4.1 / 4.0 |
| The Hunters — David Wragg | The Blade Itself — Joe Abercrombie | Fantasy | Fantasy | 3.9 / 4.2 |
| Mary Russell's War — Laurie R. King | A Study in Scarlet — Arthur Conan Doyle | Crime Fiction | Crime Fiction | 4.0 / 4.1 |
| The Black Wolf — Louise Penny | The Thursday Murder Club — Richard Osman | Crime Fiction | Crime Fiction | 4.2 / 3.9 |
| Sing No Suns, Sing the Night: Stories — Michael Michel | The Price of Power — Michael Michel | Fantasy | Fantasy | 3.9 / 4.2 |
| Sing No Suns, Sing the Night: Stories — Michael Michel | War Song: A Dreams of Dust and Steel Saga — Michael Michel | Fantasy | Fantasy | 3.9 / 4.2 |
| The Price of Power — Michael Michel | Sing No Suns, Sing the Night: Stories — Michael Michel | Fantasy | Fantasy | 4.2 / 3.9 |
| War Song: A Dreams of Dust and Steel Saga — Michael Michel | Sing No Suns, Sing the Night: Stories — Michael Michel | Fantasy | Fantasy | 4.2 / 3.9 |
| Shadow of the Giant — Orson Scott Card | Speaker for the Dead — Orson Scott Card | Science Fiction | Science Fiction | 4.0 / 4.1 |
| Silverthorn — Raymond E. Feist | The Dragonbone Chair — Tad Williams | Fantasy | Fantasy | 4.1 / 4.0 |
| Order of the Shadow Dragon — Steven McKinnon | Senlin Ascends — Josiah Bancroft | Fantasy | Fantasy | 4.0 / 4.1 |
| Children of the Black — W J Long III | Annihilation — Jeff VanderMeer | Science Fiction | Science Fiction | 4.3 / 3.8 |
| Outpost — W. Michael Gear | Old Man's War — John Scalzi | Science Fiction | Science Fiction | 3.9 / 4.2 |
| Absalom, Absalom! — William Faulkner | Blood Meridian — Cormac McCarthy | Literary Fiction | Literary Fiction | 4.0 / 4.1 |
| Revelation Space — Alastair Reynolds | Use of Weapons — Iain M. Banks | Science Fiction | Science Fiction | 4.0 / 4.2 |
| The Everlasting — Alix E. Harrow | Jonathan Strange & Mr Norrell — Susanna Clarke | Fantasy | Fantasy | 4.3 / 3.9 |
| The Book Burner's Fall — Anthony Ryan | Bauchelain and Korbal Broach — Steven Erikson | Fantasy | Fantasy | 4.2 / 4.0 |
| Mistress of the Art of Death — Ariana Franklin | Brother Cadfael's Penance — Ellis Peters | Crime Fiction | Crime Fiction | 3.9 / 4.3 |
| Childhood's End — Arthur C. Clarke | The Left Hand of Darkness — Ursula K. Le Guin | Science Fiction | Science Fiction | 4.1 / 4.1 |
| The March of Folly — Barbara W. Tuchman | Thinking, Fast and Slow — Daniel Kahneman | Nonfiction | Nonfiction | 4.0 / 4.2 |
| The Child Thief — Brom | The Graveyard Book — Neil Gaiman | Fantasy | Fantasy | 4.1 / 4.1 |
| Tales of the Sun Eater, Volume 2 — Christopher Ruocchio | Dune — Frank Herbert | Science Fiction | Science Fiction | 3.9 / 4.3 |
| Playing Patience — Dan Abnett | Xenos — Dan Abnett | Science Fiction | Science Fiction | 4.1 / 4.1 |
| Xenos — Dan Abnett | Playing Patience — Dan Abnett | Science Fiction | Science Fiction | 4.1 / 4.1 |
| Interception: The Secrets of Modern Sports Betting — Ed Miller & Matthew Davidow | The Logic of Sports Betting — Ed Miller & Matthew Davidow | Nonfiction | Nonfiction | 4.2 / 4.0 |
| The Logic of Sports Betting — Ed Miller & Matthew Davidow | Interception: The Secrets of Modern Sports Betting — Ed Miller & Matthew Davidow | Nonfiction | Nonfiction | 4.0 / 4.2 |
| Brother Cadfael's Penance — Ellis Peters | Mistress of the Art of Death — Ariana Franklin | Crime Fiction | Crime Fiction | 4.3 / 3.9 |
| Use of Weapons — Iain M. Banks | Revelation Space — Alastair Reynolds | Science Fiction | Science Fiction | 4.2 / 4.0 |
| Foundation and Earth — Isaac Asimov | The Left Hand of Darkness — Ursula K. Le Guin | Science Fiction | Science Fiction | 4.1 / 4.1 |
| The Well of Lost Plots — Jasper Fforde | The Library at Mount Char — Scott Hawkins | Fantasy | Fantasy | 4.1 / 4.1 |
| Necessity — Jo Walton | Small Gods — Terry Pratchett | Fantasy | Fantasy | 3.9 / 4.3 |
| The Ruins of Gorlan — John Flanagan | The Alchemyst — Michael Scott | Fantasy | Fantasy | 4.3 / 3.9 |
| The Great Influenza: The Story of the Deadliest Pandemic in History — John M. Barry | The Hot Zone: The Terrifying True Story of the Origins of the Ebola Virus — Richard Preston | Nonfiction | Nonfiction | 4.0 / 4.2 |
| The Graveyard Book — Neil Gaiman | The Child Thief — Brom | Fantasy | Fantasy | 4.1 / 4.1 |
| Speaker for the Dead — Orson Scott Card | A Memory Called Empire — Arkady Martine | Science Fiction | Science Fiction | 4.1 / 4.1 |
| The Last Unicorn — Peter S. Beagle | The Eyes of the Dragon — Stephen King | Fantasy | Fantasy | 4.3 / 3.9 |
| The Bullet That Missed — Richard Osman | Magpie Murders — Anthony Horowitz | Crime Fiction | Crime Fiction | 4.3 / 3.9 |
| The Hot Zone: The Terrifying True Story of the Origins of the Ebola Virus — Richard Preston | The Great Influenza: The Story of the Deadliest Pandemic in History — John M. Barry | Nonfiction | Nonfiction | 4.2 / 4.0 |
| Shorefall — Robert Jackson Bennett | Piranesi — Susanna Clarke | Fantasy | Fantasy | 4.0 / 4.2 |
| Fight or Flight — Sandy Mitchell | The Beguiling — Sandy Mitchell | Science Fiction | Science Fiction | 4.2 / 4.0 |
| The Beguiling — Sandy Mitchell | Fight or Flight — Sandy Mitchell | Science Fiction | Science Fiction | 4.0 / 4.2 |
| The Library at Mount Char — Scott Hawkins | The Well of Lost Plots — Jasper Fforde | Fantasy | Fantasy | 4.1 / 4.1 |
| Song of Susannah — Stephen King | The Waste Lands — Stephen King | Fantasy | Fantasy | 4.0 / 4.2 |
| The Eyes of the Dragon — Stephen King | The Last Unicorn — Peter S. Beagle | Fantasy | Fantasy | 3.9 / 4.3 |
| The Waste Lands — Stephen King | Song of Susannah — Stephen King | Fantasy | Fantasy | 4.2 / 4.0 |
| Lord Foul's Bane — Stephen R. Donaldson | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 3.7 / 4.5 |
| Bauchelain and Korbal Broach — Steven Erikson | The Book Burner's Fall — Anthony Ryan | Fantasy | Fantasy | 4.0 / 4.2 |
| Mockingjay — Suzanne Collins | Divergent — Veronica Roth | Science Fiction | Science Fiction | 4.1 / 4.1 |
| Legacy of Bronze — T. L. Greylock & Bryce O'Connor | Shadows of Ivory — T.L. Greylock & Bryce O'Connor | Fantasy | Fantasy | 4.3 / 3.9 |
| Shadows of Ivory — T.L. Greylock & Bryce O'Connor | Legacy of Bronze — T. L. Greylock & Bryce O'Connor | Fantasy | Fantasy | 3.9 / 4.3 |
| The Elfstones of Shannara — Terry Brooks | The Blade Itself — Joe Abercrombie | Fantasy | Fantasy | 4.0 / 4.2 |
| Small Gods — Terry Pratchett | Necessity — Jo Walton | Fantasy | Fantasy | 4.3 / 3.9 |
| Divergent — Veronica Roth | Mockingjay — Suzanne Collins | Science Fiction | Science Fiction | 4.1 / 4.1 |
| Elysium Fire — Alastair Reynolds | Use of Weapons — Iain M. Banks | Science Fiction | Science Fiction | 4.1 / 4.2 |
| The Martian — Andy Weir | The Calculating Stars — Mary Robinette Kowal | Science Fiction | Science Fiction | 4.4 / 3.9 |
| Sweetheart — Chelsea Cain | The Silence of the Lambs — Thomas Harris | Crime Fiction | Crime Fiction | 4.0 / 4.3 |
| Slow Gods — Claire North | Children of Time — Adrian Tchaikovsky | Science Fiction | Science Fiction | 4.0 / 4.3 |
| First and Only — Dan Abnett | The Forever War — Joe Haldeman | Science Fiction | Science Fiction | 4.2 / 4.1 |
| Hereticus — Dan Abnett | The Strange Demise of Titus Endor — Dan Abnett | Science Fiction | Science Fiction | 4.2 / 4.1 |
| The Strange Demise of Titus Endor — Dan Abnett | Hereticus — Dan Abnett | Science Fiction | Science Fiction | 4.1 / 4.2 |
| Redemption — David Baldacci | Walk the Wire — David Baldacci | Crime Fiction | Crime Fiction | 4.2 / 4.1 |
| Walk the Wire — David Baldacci | Redemption — David Baldacci | Crime Fiction | Crime Fiction | 4.1 / 4.2 |
| Infinite Jest — David Foster Wallace | Breakfast of Champions — Kurt Vonnegut Jr. | Literary Fiction | Literary Fiction | 4.2 / 4.1 |
| The Eye of Darkness — George Mann | Path of Deceit — Tessa Gratton & Justina Ireland | Science Fiction | Science Fiction | 4.2 / 4.1 |
| Kushiel's Avatar — Jacqueline Carey | Jonathan Strange & Mr Norrell — Susanna Clarke | Fantasy | Fantasy | 4.4 / 3.9 |
| Stormfire — Jasmine Young | An Ember in the Ashes — Sabaa Tahir | Fantasy | Fantasy | 4.1 / 4.2 |
| Into Thin Air — Jon Krakauer | Into the Wild — Jon Krakauer | Nonfiction | Nonfiction | 4.3 / 4.0 |
| Into the Wild — Jon Krakauer | Into Thin Air — Jon Krakauer | Nonfiction | Nonfiction | 4.0 / 4.3 |
| The Witness for the Dead — Katherine Addison | Piranesi — Susanna Clarke | Fantasy | Fantasy | 4.1 / 4.2 |
| Legacy of the Brightwash — Krystle Matar | The City of Brass — S. A. Chakraborty | Fantasy | Fantasy | 4.2 / 4.1 |
| Breakfast of Champions — Kurt Vonnegut Jr. | Infinite Jest — David Foster Wallace | Literary Fiction | Literary Fiction | 4.1 / 4.2 |
| The Calculating Stars — Mary Robinette Kowal | The Martian — Andy Weir | Science Fiction | Science Fiction | 3.9 / 4.4 |
| To Shape a Dragon's Breath — Moniquill Blackgoose | The Priory of the Orange Tree — Samantha Shannon | Fantasy | Fantasy | 4.1 / 4.2 |
| American Gods: The Tenth Anniversary Edition — Neil Gaiman | Good Omens: The Nice and Accurate Prophecies of Agnes Nutter, Witch — Neil Gaiman & Terry Pratchett | Fantasy | Fantasy | 4.1 / 4.2 |
| Good Omens: The Nice and Accurate Prophecies of Agnes Nutter, Witch — Neil Gaiman & Terry Pratchett | American Gods: The Tenth Anniversary Edition — Neil Gaiman | Fantasy | Fantasy | 4.2 / 4.1 |
| Babel — R. F. Kuang | The Poppy War — R.F. Kuang | Fantasy | Fantasy | 4.1 / 4.2 |
| The Poppy War — R.F. Kuang | Babel — R. F. Kuang | Fantasy | Fantasy | 4.2 / 4.1 |
| The Martian Chronicles — Ray Bradbury | The Left Hand of Darkness — Ursula K. Le Guin | Science Fiction | Science Fiction | 4.2 / 4.1 |
| A River Enchanted — Rebecca Ross | The Witchwood Crown — Tad Williams | Fantasy | Fantasy | 4.1 / 4.2 |
| Caves of Ice — Sandy Mitchell | The Traitor's Hand — Sandy Mitchell | Science Fiction | Science Fiction | 4.1 / 4.2 |
| The Traitor's Hand — Sandy Mitchell | Caves of Ice — Sandy Mitchell | Science Fiction | Science Fiction | 4.2 / 4.1 |
| Piranesi — Susanna Clarke | The Witness for the Dead — Katherine Addison | Fantasy | Fantasy | 4.2 / 4.1 |
| Path of Deceit — Tessa Gratton & Justina Ireland | The Eye of Darkness — George Mann | Science Fiction | Science Fiction | 4.1 / 4.2 |
| A Fire Upon the Deep — Vernor Vinge | Use of Weapons — Iain M. Banks | Science Fiction | Science Fiction | 4.1 / 4.2 |
| Children of the Black — W J Long III | Blindsight — Peter Watts | Science Fiction | Science Fiction | 4.3 / 4.0 |
| The Naturalist — Andrew Mayne | The Silence of the Lambs — Thomas Harris | Crime Fiction | Crime Fiction | 4.1 / 4.3 |
| To Dream and Die as a Taniwha Girl — Benedict Patrick | The Goblin Emperor — Katherine Addison | Fantasy | Fantasy | 4.3 / 4.1 |
| Bloodline — Claudia Gray | Lost Stars — Claudia Gray | Science Fiction | Science Fiction | 4.1 / 4.3 |
| Leia: Princess of Alderaan — Claudia Gray | Lost Stars — Claudia Gray | Science Fiction | Science Fiction | 4.1 / 4.3 |
| Lost Stars — Claudia Gray | Bloodline — Claudia Gray | Science Fiction | Science Fiction | 4.3 / 4.1 |
| Lost Stars — Claudia Gray | Leia: Princess of Alderaan — Claudia Gray | Science Fiction | Science Fiction | 4.3 / 4.1 |
| The Sword Unbound — Gareth Ryder-Hanrahan | Kings of the Wyld — Nicholas Eames | Fantasy | Fantasy | 4.1 / 4.3 |
| Seeds of War — João F. Silva | Kings of the Wyld — Nicholas Eames | Fantasy | Fantasy | 4.1 / 4.3 |
| World Without End — Ken Follett | Sarum — Edward Rutherfurd | Historical Fiction | Historical Fiction | 4.3 / 4.1 |
| The Fated Sky — Mary Robinette Kowal | A Memory Called Empire — Arkady Martine | Science Fiction | Science Fiction | 4.3 / 4.1 |
| An Astronaut's Guide to Life on Earth — Chris Hadfield | Riding Rockets: The Outrageous Tales of a Space Shuttle Astronaut — Mike Mullane | Nonfiction | Nonfiction | 4.2 / 4.2 |
| A Betrayal in Winter — Daniel Abraham | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 3.9 / 4.5 |
| The Burial — Drew Montgomery | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 3.9 / 4.5 |
| Sabriel — Garth Nix | Thick as Thieves — Megan Whalen Turner | Fantasy | Fantasy | 4.2 / 4.2 |
| The Hydrogen Sonata — Iain M. Banks | Use of Weapons — Iain M. Banks | Science Fiction | Science Fiction | 4.2 / 4.2 |
| An Emperor's Gamble — J. D. L. Rosell | The Dragonbone Chair — Tad Williams | Fantasy | Fantasy | 4.4 / 4.0 |
| Talonsister — Jen Williams | The Priory of the Orange Tree — Samantha Shannon | Fantasy | Fantasy | 4.2 / 4.2 |
| Legacy of the Brightwash — Krystle Matar | The Priory of the Orange Tree — Samantha Shannon | Fantasy | Fantasy | 4.2 / 4.2 |
| Shadow and Bone — Leigh Bardugo | Six of Crows — Leigh Bardugo | Fantasy | Fantasy | 3.9 / 4.5 |
| Paladin of Souls — Lois McMaster Bujold | Spinning Silver — Naomi Novik | Fantasy | Fantasy | 4.2 / 4.2 |
| Thick as Thieves — Megan Whalen Turner | Sabriel — Garth Nix | Fantasy | Fantasy | 4.2 / 4.2 |
| War Song: A Dreams of Dust and Steel Saga — Michael Michel | The Price of Power — Michael Michel | Fantasy | Fantasy | 4.2 / 4.2 |
| War Song: A Dreams of Dust and Steel Saga — Michael Michel | Kings of Paradise — Richard Nell | Fantasy | Fantasy | 4.2 / 4.2 |
| Riding Rockets: The Outrageous Tales of a Space Shuttle Astronaut — Mike Mullane | An Astronaut's Guide to Life on Earth — Chris Hadfield | Nonfiction | Nonfiction | 4.2 / 4.2 |
| Spinning Silver — Naomi Novik | Paladin of Souls — Lois McMaster Bujold | Fantasy | Fantasy | 4.2 / 4.2 |
| Throne of Jade — Naomi Novik | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 3.9 / 4.5 |
| An Altar on the Village Green — Nathan Hall | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 3.9 / 4.5 |
| The Warded Man — Peter V. Brett | The Blade Itself — Joe Abercrombie | Fantasy | Fantasy | 4.2 / 4.2 |
| The Harlequin Tartan — Raymond St. Elmo | The Night Circus — Erin Morgenstern | Fantasy | Fantasy | 4.4 / 4.0 |
| Kings of Paradise — Richard Nell | War Song: A Dreams of Dust and Steel Saga — Michael Michel | Fantasy | Fantasy | 4.2 / 4.2 |
| Duty Calls — Sandy Mitchell | The Traitor's Hand — Sandy Mitchell | Science Fiction | Science Fiction | 4.2 / 4.2 |
| The Traitor's Hand — Sandy Mitchell | Duty Calls — Sandy Mitchell | Science Fiction | Science Fiction | 4.2 / 4.2 |
| India Muerte and the Hunt for Black Atlantis — Set Sytes | Piranesi — Susanna Clarke | Fantasy | Fantasy | 4.2 / 4.2 |
| Legacy of Ghosts — Alicia Wanstall-Burke | Kings of the Wyld — Nicholas Eames | Fantasy | Fantasy | 4.2 / 4.3 |
| The Carpet Makers — Andreas Eschbach | Hyperion — Dan Simmons | Science Fiction | Science Fiction | 4.2 / 4.3 |
| Sabriel — Garth Nix | Howl's Moving Castle — Diana Wynne Jones | Fantasy | Fantasy | 4.2 / 4.3 |
| The Works of Vermin — Hiron Ennes | Piranesi — Susanna Clarke | Fantasy | Fantasy | 4.3 / 4.2 |
| Look to Windward — Iain M. Banks | The Player of Games — Iain M. Banks | Science Fiction | Science Fiction | 4.2 / 4.3 |
| The Player of Games — Iain M. Banks | Look to Windward — Iain M. Banks | Science Fiction | Science Fiction | 4.3 / 4.2 |
| The Blinding End — Ian Lewis | NOS4A2 — Joe Hill | Horror | Horror | 4.4 / 4.1 |
| A Threat of Shadows — J. A. Andrews | The Sword of Kaigen — M. L. Wang | Fantasy | Fantasy | 4.1 / 4.4 |
| The Titan Revenant — J. D. L. Rosell | The Blade Itself — Joe Abercrombie | Fantasy | Fantasy | 4.3 / 4.2 |
| Kushiel's Dart — Jacqueline Carey | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.0 / 4.5 |
| Heaven's Chains — Jeremy Bruce Adams | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.0 / 4.5 |
| NOS4A2 — Joe Hill | The Blinding End — Ian Lewis | Horror | Horror | 4.1 / 4.4 |
| The Citrine Key — L. L. MacRae | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.0 / 4.5 |
| The Sword of Kaigen — M. L. Wang | A Threat of Shadows — J. A. Andrews | Fantasy | Fantasy | 4.4 / 4.1 |
| Prince of Fools — Mark Lawrence | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.0 / 4.5 |
| Four Roads Cross — Max Gladstone | Piranesi — Susanna Clarke | Fantasy | Fantasy | 4.3 / 4.2 |
| Sin Eater — Mike Shel | Kings of the Wyld — Nicholas Eames | Fantasy | Fantasy | 4.2 / 4.3 |
| The Immortal War — N J Franco | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.0 / 4.5 |
| Design of Darkness — R. D. Pires | A Deadly Education — Naomi Novik | Fantasy | Fantasy | 4.6 / 3.9 |
| The Bone Ships — R. J. Barker | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.0 / 4.5 |
| Mythos — Stephen Fry | Circe — Madeline Miller | Fantasy | Fantasy | 4.3 / 4.2 |
| Parallax — Amber Toro | Ancillary Sword — Ann Leckie | Science Fiction | Science Fiction | 4.5 / 4.1 |
| Blood of Elves — Andrzej Sapkowski | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.1 / 4.5 |
| Ancillary Sword — Ann Leckie | Parallax — Amber Toro | Science Fiction | Science Fiction | 4.1 / 4.5 |
| Murtagh — Christopher Paolini | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.1 / 4.5 |
| A Threat of Shadows — J. A. Andrews | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.1 / 4.5 |
| Victory of Eagles — Naomi Novik | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.1 / 4.5 |
| Unreconciled — W. Michael Gear | Children of Time — Adrian Tchaikovsky | Science Fiction | Science Fiction | 4.3 / 4.3 |
| Roots — Alex Haley | When the Lion Feeds — Wilbur Smith | Historical Fiction | Historical Fiction | 4.4 / 4.2 |
| Blood Song — Anthony Ryan | The Warded Man — Peter V. Brett | Fantasy | Fantasy | 4.4 / 4.2 |
| From the Depths — B. S. H. Garcia | Piranesi — Susanna Clarke | Fantasy | Fantasy | 4.4 / 4.2 |
| Honour Guard — Dan Abnett | Necropolis — Dan Abnett | Science Fiction | Science Fiction | 4.2 / 4.4 |
| Necropolis — Dan Abnett | Honour Guard — Dan Abnett | Science Fiction | Science Fiction | 4.4 / 4.2 |
| Night — Elie Wiesel | The Rape of Nanking — Iris Chang | Nonfiction | Nonfiction | 4.4 / 4.2 |
| The Rape of Nanking — Iris Chang | Night — Elie Wiesel | Nonfiction | Nonfiction | 4.2 / 4.4 |
| Memory's Legion — James S. A. Corey | Stories of Your Life and Others — Ted Chiang | Science Fiction | Science Fiction | 4.4 / 4.2 |
| A King in Waiting — Michael Cronk | Piranesi — Susanna Clarke | Fantasy | Fantasy | 4.4 / 4.2 |
| Murder on Hunter's Eve — Morgan Stang | Piranesi — Susanna Clarke | Fantasy | Fantasy | 4.4 / 4.2 |
| The Warded Man — Peter V. Brett | Blood Song — Anthony Ryan | Fantasy | Fantasy | 4.2 / 4.4 |
| Percy Jackson's Greek Gods — Rick Riordan | Circe — Madeline Miller | Fantasy | Fantasy | 4.4 / 4.2 |
| An Ember in the Ashes — Sabaa Tahir | Crown of Midnight — Sarah J. Maas | Fantasy | Fantasy | 4.2 / 4.4 |
| Crown of Midnight — Sarah J. Maas | An Ember in the Ashes — Sabaa Tahir | Fantasy | Fantasy | 4.4 / 4.2 |
| When the Lion Feeds — Wilbur Smith | Roots — Alex Haley | Historical Fiction | Historical Fiction | 4.2 / 4.4 |
| The Air War — Adrian Tchaikovsky | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.2 / 4.5 |
| Fool's Promise — Angela Boord | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.2 / 4.5 |
| The Pariah — Anthony Ryan | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.2 / 4.5 |
| Excalibur — Bernard Cornwell | The Last Kingdom — Bernard Cornwell | Historical Fiction | Historical Fiction | 4.4 / 4.3 |
| The Powder Mage Novella Collection #1: Stories From the Powder Mage Universe — Brian McClellan | The Lies of Locke Lamora — Scott Lynch | Fantasy | Fantasy | 4.4 / 4.3 |
| Blood Pact — Dan Abnett | Only in Death — Dan Abnett | Science Fiction | Science Fiction | 4.3 / 4.4 |
| Only in Death — Dan Abnett | Blood Pact — Dan Abnett | Science Fiction | Science Fiction | 4.4 / 4.3 |
| Shield of the Mothership: Turn Seven of the Hybrid Helix — J. C. M. Berne | A Fire Upon the Deep — Vernor Vinge | Science Fiction | Science Fiction | 4.6 / 4.1 |
| Texas — James A. Michener | Lonesome Dove — Larry McMurtry | Historical Fiction | Historical Fiction | 4.1 / 4.6 |
| Heaven and Hell — John Jakes | Lonesome Dove — Larry McMurtry | Historical Fiction | Historical Fiction | 4.1 / 4.6 |
| Free the Darkness — Kel Kade | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.2 / 4.5 |
| Nolyn — Michael J. Sullivan | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.2 / 4.5 |
| A Gathering of Shadows — V. E. Schwab | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.2 / 4.5 |
| To Kill a God — Ben Galley | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.3 / 4.5 |
| Warlock's Sun Rising — Damien Black | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.3 / 4.5 |
| A Knight of the Seven Kingdoms — George R. R. Martin | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.3 / 4.5 |
| Dragon's Reach — J. A. Andrews | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.3 / 4.5 |
| Knights of the Dead God — James Jakins | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.3 / 4.5 |
| Leviathan Falls — James S. A. Corey | Hyperion — Dan Simmons | Science Fiction | Science Fiction | 4.5 / 4.3 |
| Holy Sister — Mark Lawrence | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.3 / 4.5 |
| Age of Death — Michael J. Sullivan | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.3 / 4.5 |
| A Day of Fallen Night — Samantha Shannon | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.3 / 4.5 |
| A Conjuring of Light — V. E. Schwab | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.3 / 4.5 |
| World's End — Christopher Mitchell | The Last Wish — Andrzej Sapkowski | Fantasy | Fantasy | 4.8 / 4.1 |
| Centennial — James A. Michener | Lonesome Dove — Larry McMurtry | Historical Fiction | Historical Fiction | 4.3 / 4.6 |
| Of War and Ruin — Ryan Cahill | Empire of the Vampire — Jay Kristoff | Fantasy | Fantasy | 4.6 / 4.3 |
| Blood Song — Anthony Ryan | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.4 / 4.5 |
| The Traitor — Anthony Ryan | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.4 / 4.5 |
| Winter's King — Bryce O'Connor | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.4 / 4.5 |
| The Librarian — Casey White | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.4 / 4.5 |
| Jade War — Fonda Lee | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.4 / 4.5 |
| Rise of Empire — Michael J. Sullivan | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.4 / 4.5 |
| The Death of Dulgath — Michael J. Sullivan | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.4 / 4.5 |
| Mistress of the Empire — Raymond E. Feist & Janny Wurts | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.4 / 4.5 |
| Hammerfall: A God Eater Saga Story — Rob J. Hayes | The Blade Itself — Joe Abercrombie | Fantasy | Fantasy | 4.7 / 4.2 |
| The Blood That Burns the Winter Snow — Ryan Cahill | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.4 / 4.5 |
| Kingdom of Ash — Sarah J. Maas | An Ember in the Ashes — Sabaa Tahir | Fantasy | Fantasy | 4.7 / 4.2 |
| Conspiracy — A. C. Cobble | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.5 / 4.5 |
| A Blood of Kings — Bryce O'Connor & Luke Chmilenko | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.5 / 4.5 |
| Raven's Ruin — J. A. Andrews | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.5 / 4.5 |
| A Battle Between Blood: A Legend of Tal Novella — J. D. L. Rosell | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.5 / 4.5 |
| Ride the Wind — Lucia St. Clair Robson | Lonesome Dove — Larry McMurtry | Historical Fiction | Historical Fiction | 4.4 / 4.6 |
| The Return of the King — J. R. R. Tolkien | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.6 / 4.5 |
| Esrahaddon — Michael J. Sullivan | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.6 / 4.5 |
| Age of the King — Philip C. Quaintrell | The Name of the Wind — Patrick Rothfuss | Fantasy | Fantasy | 4.6 / 4.5 |
| Esrahaddon — Michael J. Sullivan | Farilane — Michael J. Sullivan | Fantasy | Fantasy | 4.6 / 4.6 |
| Farilane — Michael J. Sullivan | Esrahaddon — Michael J. Sullivan | Fantasy | Fantasy | 4.6 / 4.6 |
