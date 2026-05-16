##
import pandas as pd
from rapidfuzz import process, fuzz
import re

storygraph_df = pd.read_csv("Storygraph.csv")
calibre_df = pd.read_csv("Library.csv")

##
tag_list = []
# Group by series and spread tags within each group
for series, group in calibre_df.groupby('series', dropna=False):
    if series == '' or pd.isna(series):
        continue  # Skip entries without a series
    # Find all tags that exist in this group
    all_tags_in_group = set()
    for tags_str in group['tags']:
        if pd.notna(tags_str):
            # Split tags by comma and strip whitespace
            tags = [tag.strip() for tag in str(tags_str).split(',')]
            all_tags_in_group.update(tags)
    
    # Find tags from tag_list that exist in this group
    tags_to_spread = [tag for tag in tag_list if tag in all_tags_in_group]
    
    # For each tag to spread, add it to members that don't have it
    for tag in tags_to_spread:
        for idx in group.index:
            current_tags = calibre_df.loc[idx, 'tags']
            if pd.notna(current_tags):
                tags_list = [t.strip() for t in str(current_tags).split(',')]
                if tag not in tags_list:
                    # Append the tag
                    calibre_df.loc[idx, 'tags'] = str(current_tags) + ', ' + tag
            else:
                # If tags column is empty, just add the tag
                calibre_df.loc[idx, 'tags'] = tag

    # Spread the genre in the same way
    genre = group['#genre'].mode()
    if not genre.empty:
        genre = genre.iloc[0]
        for idx in group.index:
            calibre_df.loc[idx, '#genre'] = genre

calibre_df.loc[calibre_df.series.isnull(), 'series'] = calibre_df.loc[calibre_df.series.isnull(), 'title']

##
# Fuzzy matching helper
# - Detect probable title/author columns
# - Normalize text (lowercase, remove punctuation, collapse whitespace)
# - Use RapidFuzz to match combined "title | author" strings

sg_title_col = 'Title'
sg_author_col = 'Authors'
cal_title_col = 'title'
cal_author_col = 'authors'

# Normalizer
def normalize(s):
    if pd.isna(s):
        return ''
    
    s = str(s).lower()
    s = s.replace(' & ', ', ')  # standardize ampersands
    s = ", ".join(sorted([part.strip() for part in s.split(',')]))  # sort comma-separated parts
    s = s.split(':')[0]  # remove text after colon
    s = re.sub(r"[^\w\s]", " ", s)  # remove punctuation
    s = re.sub(r"\s+", " ", s).strip()
    return s

# Add normalized columns (keep originals intact)
if sg_title_col:
    storygraph_df['title_norm'] = storygraph_df[sg_title_col].apply(normalize)
else:
    storygraph_df['title_norm'] = ''

if sg_author_col:
    storygraph_df['author_norm'] = storygraph_df[sg_author_col].apply(normalize)
else:
    storygraph_df['author_norm'] = ''

if cal_title_col:
    calibre_df['title_norm'] = calibre_df[cal_title_col].apply(normalize)
else:
    calibre_df['title_norm'] = ''

if cal_author_col:
    calibre_df['author_norm'] = calibre_df[cal_author_col].apply(normalize)
else:
    calibre_df['author_norm'] = ''

# Prepare choices (string -> index) for RapidFuzz
calibre_df = calibre_df.reset_index(drop=True)
cal_titles = calibre_df['title_norm'].fillna('').tolist()
cal_authors = calibre_df['author_norm'].fillna('').tolist()
cal_choice_map = {s: i for i, s in enumerate(cal_titles)}  # keep map if you prefer mapping strings -> idx

##
# Matching function (returns matched calibre index and score)
def match_combined(query, choices, scorer=fuzz.token_set_ratio, score_cutoff=20):
    try:
        match = process.extract(query, choices, limit=None, scorer=scorer, score_cutoff=score_cutoff)
    except TypeError as e:
        # Defensive: print debug info and return no match
        print("TypeError in process.extract:", e)
        print("choices type:", type(choices))
        return None, 0
    if match:
        max_score = match[0][1]  # highest score
        best_matches = [m for m in match if m[1] == max_score]
        return best_matches
    return []

##
# Run matching with adjustable threshold
threshold = 80  # tweak this: higher => fewer matches but more confident
matches = []
scores = []
for i, row in storygraph_df.iterrows():
    author_matches = match_combined(row['author_norm'], cal_authors, score_cutoff=threshold)
    if author_matches:
        author_ids = [idx for _, _, idx in author_matches]
        title_list = [cal_titles[idx] for idx in author_ids]
        title_matches = match_combined(row['title_norm'], title_list)
        if title_matches:
            _, _, idx = author_matches[title_matches[0][2]]
            score = title_matches[0][1]  # title match score
        else:
            idx, score = None, 0
    else:
        idx, score = None, 0
    matches.append(idx)
    scores.append(score)

storygraph_df['matched_cal_index'] = matches
storygraph_df['match_score'] = scores

# Merge matched calibre rows into storygraph rows (keep original merge intact)
merged_df = storygraph_df.merge(calibre_df, left_on='matched_cal_index', right_index=True, how='left', suffixes=("_sg","_cal"))

print(f"Matches at threshold {threshold}:", merged_df['matched_cal_index'].notnull().sum(), "/", len(merged_df))
# Show some examples: good matches and unmatched
print('\nSample high-scoring matches (score >=', threshold,')')
matched = merged_df[merged_df['match_score']>=threshold]

print('\nSample low-score or unmatched rows (score <', threshold,')')
unmatched = merged_df[merged_df['match_score']<threshold]

##
calibre_df[["authors","isbn","id","identifiers","pubdate","series","series_index","tags","title","#pages","#grvotes","#modrating","#genre","#more_tags","#series_type"]].to_csv('Library.csv', index=False)
log_df = matched.loc[matched['Read Status'] == 'read', ["title", "authors", "Last Date Read", "Star Rating", "#genre", "#series_type", "tags", "#more_tags"]].sort_values(by='Last Date Read', ascending=False)
log_df.rename(columns={"Star Rating": "My Rating", "#genre": "genre", "#series_type": "series_type", "tags": "my_tags", "#more_tags": "goodreads_shelves"}, inplace=True)
log_df.to_csv("Reading_Log.csv", index=False)