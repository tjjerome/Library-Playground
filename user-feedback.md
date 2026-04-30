# User Feedback — Recommendation Pipeline Smoke Test

Raw reader notes from a smoke-test session of the librarian skill. Captured in the reader's voice without editorial framing.

---

1. During the taste interview, the agent did not wait for a response to its open-ended question before opening the question block with a different question. This made me unable to answer the first question.

2. It's also repeating questions pretty often.

3. It's almost a little too formal and snappy when adding books to the list. It should remain conversational. It should ask for direction from the user and think about responses to see if they warrant any changes to the profile or recommendation set.

4. It keeps missing that I've read Salem's Lot already. It might be a fuzzy search issue.

5. The recommendations inside the answers of the question blocks are getting cut off when viewing on mobile. It makes it hard to see all of the context prior to selecting answers. I'm not sure how to fix that but it's worth thinking about.

6. It has missed a couple of series entries like the Three Body Problem and A Memory Called Empire. It should have asked me if I wanted to add the whole series or just a subset.

7. It just recommended me Assassin's Apprentice and called it a standalone.

8. It's also resurfacing a lot of books that are already on the list later in the cycle.

9. Related to 3 and 5 — most of the time it's purely giving the book descriptions. I want it to tell me why it thinks I would like the book alongside what it's about. It should feel more personal.

10. Most of the recommendations also feel very safe. I want it to take more shots on obscure books. It shouldn't overpower me with unknown recommendations but I do want it to challenge me. Not an overall target — just make sure at least 1 of the four recommendations in each batch is a deep cut. Don't label it a deep cut, keep it silent so it doesn't bias the decision. Randomize the placement in the choice block as well.

11. It's taking the authority to resurface rejected picks a little too seriously. Each rejection should count as a soft negative against the recommendation weight. If the model really believes in the recommendation it can resurface it, but each subsequent rejection should count more negatively. If it's truly a surprise, that should trigger a conversation and perhaps an update to the reader profile. When I skipped a whole batch, it didn't probe deeper — it just moved on to a different genre.

12. It's also not interspersing the indie and classics recommendations with the other genres. Those are cross-cutting so they need to show up in the genre recommendations or we're going to get to the situation I'm in now where we're full up on fantasy but barely have any indie. That's a problem since most of the indie in this catalog is fantasy, so it will be nearly impossible to fill that gap without sacrificing recommendation quality. I would also pivot to viewing the goal for indie and classics as a minimum and not a range to hit. That feels more appropriate.

13. It just tried to trigger Phase 4 at 94 books instead of the full 100. I believe this was caused by reducing the goal for horror books in the middle of Phase 3 by 6 books but not redistributing those to get us back to 100.

14. I want the librarian to keep author entry points in mind when recommending an author I haven't read before. For series recommendations, the book should be the first in a series. If the author has multiple series, make sure this series is a good place to start and doesn't rely on other material or is generally considered weaker than other books by the author. For standalone recommendations, make sure the book is considered a good place to start with the author. This is especially true for the "series of standalone" books common in crime fiction. Double check that the specific book is actually recommended as a good place to start and doesn't rely on context established elsewhere.

15. It's falling back on books I've read before as we get later into the list. It should be excluding those by rule but something is going wrong. It got worse when I specifically asked for more indie picks.

16. When looking for new releases, it only looked for upcoming releases from authors I follow. I want to see those, but I also want to see highly anticipated releases in my favorite genres as well. Sometimes those can be the best way to find a new author.

17. Move the final review stage — where we discuss removing borderline books and adding in any I feel we've missed — to *after* the upcoming releases discussion.

18. I never once saw it surface the remaining Book of the New Sun books as recommendations, despite that being a highly rated series for me that I'm halfway through.

19. Once we're locked in after the swap pass, I want to get a final "Top 5 — read these ASAP" list.
