# `author_entry_point` consistency review queue

_Generated 2026-05-04 from `Library_Catalog.sqlite`._

Implements RECOMPOSITION_PLAN §6.5.  Three suspect classes,
none auto-fixed.  Each row is for the maintainer to confirm
(keep / change / annotate).

**115 flags total** (8 misaligned, 102 pub_year regression, 5 zero-entry-point authors).

## 1. Series misalignment (8)

`author_entry_point=true` on a book whose `series_role` or
`series_position` says it's not actually a sensible starting
point.  These are the Smiley's People / Murder on the Orient
Express shape — high-confidence flags.

| Title | Author | Series | Position | Role | Reason |
|---|---|---|---|---|---|
| Chasm City | Alastair Reynolds | Revelation Space | Book 0.5 | loose-entry | series_position parses to Book 0.5 (sub-1, likely prequel) |
| The Last Wish | Andrzej Sapkowski | The Witcher | Book 0.5 | loose-entry | series_position parses to Book 0.5 (sub-1, likely prequel) |
| The Pawns of Havoc | Dave Lawson | The Envoys of Chaos | Book 0.5 | first | series_position parses to Book 0.5 (sub-1, likely prequel) |
| The Lions of Al-Rassan | Guy Gavriel Kay | Sarantine Universe | Book 4 | standalone | series_role='standalone' but series_position parses to Book 4 |
| The Warrior's Apprentice | Lois McMaster Bujold | Vorkosigan Saga | Book 3 | first | series_role='first' but series_position parses to Book 3 |
| Roman Blood | Steven Saylor | Roma Sub Rosa | Book 4 | first | series_role='first' but series_position parses to Book 4 |
| The Elfstones of Shannara | Terry Brooks | The Sword of Shannara | Book 2 | mid | series_role='mid' (mid-series — not a sensible entry) |
| Path of Deceit | Tessa Gratton & Justina Ireland | The High Republic | Book 7 | first | series_role='first' but series_position parses to Book 7 |

## 2. pub_year regression on standalone-only authors (102)

Author has ≥2 standalone books, the entry-point flag is on
a book published *after* an earlier standalone by the same
author.  **Soft signal — many flags will be intentional**
(e.g. "And Then There Were None" is a better Christie
on-ramp than her 1929 obscurity).  Sorted by gap years
descending; bigger gaps deserve more scrutiny.

| Author | Entry-point title | EP year | Earliest title | Earliest year | Gap |
|---|---|---|---|---|---|
| Charles Dickens | A Christmas Carol | 2026 | Oliver Twist; or, The Parish Boy's Progress | 1838 | 188 |
| H. G. Wells | The Time Machine and the Invisible Man | 2007 | The War of the Worlds | 1898 | 109 |
| William Faulkner | As I Lay Dying | 2026 | The Sound and the Fury | 1929 | 97 |
| James A. Michener | Hawaii | 2014 | The Source | 1965 | 49 |
| Barbara W. Tuchman | The Guns of August | 2009 | The Proud Tower | 1965 | 44 |
| Stephen King | 11/22/63 | 2011 | Carrie | 1974 | 37 |
| Harlan Ellison | I Have No Mouth and I Must Scream | 2002 | Dangerous Visions | 1967 | 35 |
| Victor Hugo | Les Misérables | 1862 | The Hunchback of Notre Dame | 1831 | 31 |
| David McCullough | 1776 | 2005 | The Path Between the Seas | 1977 | 28 |
| Philip K. Dick | Selected Stories of Philip K. Dick | 1982 | Eye in the Sky | 1957 | 25 |
| David McCullough | John Adams | 2001 | The Path Between the Seas | 1977 | 24 |
| Charles Dickens | Great Expectations | 1861 | Oliver Twist; or, The Parish Boy's Progress | 1838 | 23 |
| Dean Koontz | Intensity | 1995 | Demon Seed | 1973 | 22 |
| Charles Dickens | A Tale of Two Cities | 1859 | Oliver Twist; or, The Parish Boy's Progress | 1838 | 21 |
| Agatha Christie | Crooked House | 1949 | The Seven Dials Mystery | 1929 | 20 |
| Tom Wolfe | The Bonfire of the Vanities | 1987 | The Electric Kool-Aid Acid Test | 1968 | 19 |
| Kurt Vonnegut Jr. | Slaughterhouse-Five | 1969 | Player Piano | 1952 | 17 |
| Neil Gaiman | The Ocean at the End of the Lane | 2013 | Neverwhere | 1996 | 17 |
| Susanna Clarke | Piranesi | 2020 | Jonathan Strange & Mr Norrell | 2004 | 16 |
| Carl Sagan | The Demon-Haunted World: Science as a Candle in the Dark | 1995 | Cosmos | 1980 | 15 |
| Edith Wharton | The Age of Innocence | 1920 | The House of Mirth | 1905 | 15 |
| Joseph Kanon | Istanbul Passage | 2012 | Los Alamos | 1997 | 15 |
| Barack Obama | A Promised Land | 2020 | The Audacity of Hope: Thoughts on Reclaiming the American Dream | 2006 | 14 |
| Cormac McCarthy | The Road | 2006 | All the Pretty Horses | 1992 | 14 |
| Dean Koontz | Watchers | 1987 | Demon Seed | 1973 | 14 |
| qntm | There Is No Antimemetics Division | 2020 | Valuable Humans in Transit and Other Stories | 2006 | 14 |
| Bill Bryson | A Short History of Nearly Everything 2.0 | 2003 | The Mother Tongue: English and How It Got That Way | 1990 | 13 |
| Cormac McCarthy | No Country for Old Men | 2005 | All the Pretty Horses | 1992 | 13 |
| Patrick Radden Keefe | Say Nothing: A True Story of Murder and Memory in Northern Ireland | 2018 | Chatter | 2005 | 13 |
| Stephen King | Misery | 1987 | Carrie | 1974 | 13 |
| Brom | Slewfoot | 2021 | The Child Thief | 2009 | 12 |
| Charles Dickens | David Copperfield | 1850 | Oliver Twist; or, The Parish Boy's Progress | 1838 | 12 |
| Clifford D. Simak | Way Station | 1963 | Time and Again | 1951 | 12 |
| Harlan Coben | Tell No One/Gone for Good | 2002 | Play Dead | 1990 | 12 |
| James Luceno | Darth Plagueis | 2012 | Cloak of Deception | 2000 | 12 |
| Neil Gaiman | The Graveyard Book | 2008 | Neverwhere | 1996 | 12 |
| Stephen King | It | 1986 | Carrie | 1974 | 12 |
| Harlan Coben | Tell No One | 2001 | Play Dead | 1990 | 11 |
| Tom Wolfe | The Right Stuff | 1979 | The Electric Kool-Aid Acid Test | 1968 | 11 |
| William Shakespeare | Hamlet | 1601 | Romeo and Juliet | 1590 | 11 |
| Agatha Christie | And Then There Were None | 1939 | The Seven Dials Mystery | 1929 | 10 |
| David Foster Wallace | Consider the Lobster and Other Essays | 2005 | Infinite Jest | 1996 | 9 |
| Erik Larson | The Devil in the White City: Murder, Magic, and Madness at the Fair That Changed America | 2003 | Lethal Passage: The Story of a Gun | 1994 | 9 |
| James A. Michener | Centennial | 1974 | The Source | 1965 | 9 |
| Leo Tolstoy | Anna Karenina | 1878 | War and Peace | 1869 | 9 |
| Mark Twain | Adventures of Huckleberry Finn | 1885 | The Adventures of Tom Sawyer | 1876 | 9 |
| Ben Macintyre | The Spy and the Traitor: The Greatest Espionage Story of the Cold War | 2018 | Operation Mincemeat | 2010 | 8 |
| Tim Powers | On Stranger Tides | 1987 | The Drawing of the Dark | 1979 | 8 |
| Victor LaValle | The Changeling | 2017 | Big Machine | 2009 | 8 |
| Blake Crouch | Dark Matter | 2016 | Abandon | 2009 | 7 |
| John Green | The Fault in Our Stars | 2012 | Looking for Alaska | 2005 | 7 |
| Nevil Shute | On the Beach | 1957 | A Town Like Alice | 1950 | 7 |
| Stephen King | Cujo | 1981 | Carrie | 1974 | 7 |
| Victor Lavalle | The Ballad of Black Tom | 2016 | Big Machine | 2009 | 7 |
| Charlie Jane Anders | All the Birds in the Sky | 2016 | The Fermi Paradox Is Our Business Model | 2010 | 6 |
| Gary Taubes | Why We Get Fat: And What to Do About It | 2010 | Good Calories, Bad Calories: Challenging the Conventional Wisdom on Diet, Weight Control, and Disease | 2004 | 6 |
| Gillian Flynn | Gone Girl | 2012 | Sharp Objects | 2006 | 6 |
| Robert Crais | The Two Minute Rule | 2006 | Demolition Angel | 2000 | 6 |
| Ronald Malfi | Come With Me | 2021 | Little Girls | 2015 | 6 |
| Stephen King | Firestarter | 1980 | Carrie | 1974 | 6 |
| Hunter S. Thompson | Fear and Loathing in Las Vegas: A Savage Journey to the Heart of the American Dream | 1971 | Hell's Angels: A Strange and Terrible Saga | 1966 | 5 |
| Michael Pollan | The Omnivore's Dilemma: A Natural History of Four Meals | 2006 | The Botany of Desire: A Plant's-Eye View of the World | 2001 | 5 |
| V. E. Schwab | Bury Our Bones in the Midnight Soil | 2025 | The Invisible Life of Addie LaRue | 2020 | 5 |
| Ania Ahlborn | Brother | 2015 | Seed | 2011 | 4 |
| George Orwell | 1984 | 1949 | Animal Farm | 1945 | 4 |
| George Saunders | Lincoln in the Bardo | 2017 | Tenth of December | 2013 | 4 |
| John Steinbeck | The Grapes of Wrath | 1939 | Tortilla Flat | 1935 | 4 |
| Joseph Kanon | The Good German | 2001 | Los Alamos | 1997 | 4 |
| Pat Murphy | The Falling Woman | 1986 | The Shadow Hunter | 1982 | 4 |
| Robert Louis Stevenson | Strange Case of Dr. Jekyll and Mr. Hyde | 1886 | Treasure Island | 1882 | 4 |
| Robert McCammon | Boy's Life | 1991 | Swan Song | 1987 | 4 |
| Ruth Ware | The Turn of the Key | 2019 | In a Dark, Dark Wood | 2015 | 4 |
| Stephen Graham Jones | The Only Good Indians | 2020 | Mongrels | 2016 | 4 |
| Stephen King | Night Shift | 1978 | Carrie | 1974 | 4 |
| Tim Powers | The Anubis Gates | 1983 | The Drawing of the Dark | 1979 | 4 |
| Alfred Bester | The Stars My Destination | 1956 | The Demolished Man | 1953 | 3 |
| Charlie Huston | Sleepless | 2010 | The Shotgun Rule | 2007 | 3 |
| Dan Jones | The Plantagenets: The Warrior Kings and Queens Who Made England | 2012 | Summer of Blood: The Peasants' Revolt of 1381 | 2009 | 3 |
| David Sedaris | Me Talk Pretty One Day | 2000 | Naked | 1997 | 3 |
| John Dickson Carr | The Hollow Man | 1935 | Poison in Jest | 1932 | 3 |
| Max Brooks | World War Z: An Oral History of the Zombie War | 2006 | The Zombie Survival Guide: Complete Protection from the Living Dead | 2003 | 3 |
| Naomi Novik | Spinning Silver | 2018 | Uprooted | 2015 | 3 |
| Nick Hornby | High Fidelity | 1995 | Fever Pitch | 1992 | 3 |
| Ray Bradbury | Fahrenheit 451 | 1953 | The Martian Chronicles | 1950 | 3 |
| Richard Preston | The Hot Zone: The Terrifying True Story of the Origins of the Ebola Virus | 1994 | The Cobra Event | 1991 | 3 |
| Shaun Paul Stevens | Nether Light | 2021 | Deliverance at Van Demon's Deep | 2018 | 3 |
| Thomas Pynchon | The Crying of Lot 49 | 1966 | V. | 1963 | 3 |
| Greg Egan | Permutation City | 1994 | Quarantine | 1992 | 2 |
| John Jackson Miller | Kenobi | 2013 | Knight Errant | 2011 | 2 |
| John Steinbeck | Of Mice and Men | 1937 | Tortilla Flat | 1935 | 2 |
| Jon Krakauer | Into Thin Air | 1998 | Into the Wild | 1996 | 2 |
| Matt Taibbi | Griftopia: Bubble Machines, Vampire Squids, and the Long Con That Is Breaking America | 2010 | The Great Derangement: A Terrifying True Story of War, Politics, and Religion at the Twilight of the American Empire | 2008 | 2 |
| T. Kingfisher | Nettle & Bone | 2022 | A Wizard's Guide to Defensive Baking | 2020 | 2 |
| T. R. Napper | 36 Streets | 2022 | Neon Leviathan | 2020 | 2 |
| Taylor Jenkins Reid | Daisy Jones & the Six | 2019 | The Seven Husbands of Evelyn Hugo | 2017 | 2 |
| Wick Welker | Saint Elspeth | 2023 | Refraction | 2021 | 2 |
| Charlie Huston | The Mystic Arts of Erasing All Signs of Death | 2008 | The Shotgun Rule | 2007 | 1 |
| Christopher Buehlman | Between Two Fires | 2012 | Those Across the River | 2011 | 1 |
| Clifford D. Simak | City | 1952 | Time and Again | 1951 | 1 |
| Robert Crais | Hostage | 2001 | Demolition Angel | 2000 | 1 |
| Robert J. Sawyer | Flashforward | 1999 | Factoring Humanity | 1998 | 1 |
| Silvia Moreno-Garcia | Mexican Gothic | 2020 | Gods of Jade and Shadow | 2019 | 1 |

## 3. Zero entry-point authors with ≥3 books (5)

Author has 3+ books in the catalog, none flagged
`author_entry_point=true`, and no book has a
`series_role` of standalone/first/loose-entry/entry-point.
Likely an oversight — pick one as the entry point or
annotate why none qualifies.

| Author | Book count | series_role values | Sample titles |
|---|---|---|---|
| Troy Denning | 8 | late, mid | Abyss; Apocalypse; Inferno |
| Wilbur Smith & Tom Harper | 4 | late, loose-mid, mid | Ghost Fire; Nemesis; The Tiger's Prey |
| Greg Keyes | 3 | late, mid | Edge of Victory I: Conquest; Edge of Victory II: Rebirth; The Final Prophecy |
| Robert Jordan & Brandon Sanderson | 3 | late | A Memory of Light; The Gathering Storm; Towers of Midnight |
| Sean Williams & Shane Dix | 3 | mid | Force Heretic II: Refugee; Force Heretic III: Reunion; Remnant |
