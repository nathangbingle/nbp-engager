# NBP Instagram Engager

Automatically likes posts from 78 target school/athletic Instagram accounts 
across Fort Mill SD, Rock Hill SD, Clover SD, Indian Land SD, York County, and CMS.

Runs 3x daily: 8:15am, 12:30pm, 5:45pm ET
Cycles through all 78 accounts — ~8 per run, likes 3 posts each = ~24 likes/run

## Railway Environment Variables Required

| Variable | Value |
|---|---|
| INSTAGRAM_USERNAME | Your Instagram username (no @) |
| INSTAGRAM_PASSWORD | Your Instagram password |
| LIKES_PER_RUN | 8 (default) |
| POSTS_PER_ACCOUNT | 3 (default) |

## Deploy to Railway

1. Push this folder to a GitHub repo named `nbp-engager`
2. New Railway project → Deploy from GitHub → select the repo
3. Add the environment variables above
4. Deploy — it starts cycling immediately

## How it works

- Cycles through all 78 accounts in order, picking up where it left off each run
- Likes the 3 most recent posts per account that haven't been liked yet
- Human-paced delays between likes (12-28s) and between accounts (45-90s)
- Saves state in engager_state.json so it never double-likes
- Logs everything so you can see exactly what it did
