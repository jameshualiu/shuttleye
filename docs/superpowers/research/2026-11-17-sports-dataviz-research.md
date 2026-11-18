# How sports data platforms present player data: what works and what doesn't

Research for the ShuttlEye pro player profile pages (issue to be created). Collected 2026-11-17.

**Evidence quality:** most sources are product pages, press coverage and practitioner blogs. A few are academic. No platform published its own design rationale, so the "why it works" parts are inferred from how users and reviewers describe these products.

## What works

### 1. Rank every stat against the rest of the league (Baseball Savant)
- Savant's player page shows each stat as a **percentile bubble from 0 to 100 against the rest of the league**, coloured from blue (low) to red (high). ([MLB.com](https://www.mlb.com/news/baseball-savant-statcast-player-pages-new-look), [TDA Baseball](https://www.tdabaseball.com/post/how-to-analyze-a-hitter-s-baseball-savant-page))
- Users credit it with showing **strengths and weaknesses at a glance**, and it puts every stat on one shared scale. MLB calls it "the back of a Statcast baseball card".
- Savant's 2026 comparison tool reuses the same visual style for comparing players side by side. ([Savant changelog](https://baseballsavant.mlb.com/changelog/2026-07-20-player-comparison-tool))

**For ShuttlEye:** rank each player's stats against the other 26 ShuttleSet pros instead of showing raw percentages.

### 2. Draw stats on the real playing surface, encoding both volume and success (Goldsberry shot charts)
- Kirk Goldsberry's NBA hexbin shot charts put shots on the court itself. **Hexagon size shows how often a shot was taken, and colour shows its efficiency against the league.** One mark carries location, volume and success. ([ballr](https://toddwschneider.com/posts/ballr-interactive-nba-shot-charts-with-r-and-shiny/), [Wikipedia](https://en.wikipedia.org/wiki/Kirk_Goldsberry), [McCombs](https://news.mccombs.utexas.edu/magazine/charting-a-course-on-the-courts/))

**For ShuttlEye:** use court maps by hitting area or landing area, where size means "how often" and colour means "point win rate compared with other pros", not a plain density heatmap.

### 3. Let every number open the video behind it (Hudl)
- Hudl Assist lets coaches "click any total to watch video of those moments". Sportscode advertises "interactive player reports linked directly to video". ([Hudl Assist](https://cwww.hudl.com/products/assist), [Sportscode](https://jp.hudl.com/en/products/sportscode))
- This is the standard workflow in professional video analysis. A number can be checked and learned from only when you can watch what's behind it.

**For ShuttlEye:** every stat and every pattern opens the matching rallies in an embedded BWF YouTube video at the right time.

### 4. Split rallies into length bands (ATP / Infosys)
- ATP's Rally Analysis groups points into **0–4 shots ("first strike"), 5–8 ("patterns of play") and 9+ ("extended rallies")**, and shows winners and errors in each band. ([ATP / Infosys on Sinner](https://www.atptour.com/en/news/infosys-btn-sinner-march-2024))
- That produces stories like "Sinner played 59% of his points in 0–4 shot rallies and won 57% of them".
- ATP's Stroke Summary shows success rates, winners and errors for each stroke type.

**For ShuttlEye:** this carries straight over to badminton, since ShuttleSet has the shot order, who won the point and how the rally ended.

### 5. Few numbers, chosen for one decision
- Dashboard guidance converges on **3–5 key metrics, or 5–9 charts at most** per view. Start from the decision the view supports, not from the data you happen to have. ([Harvard Science Review](https://harvardsciencereview.org/2025/08/08/visualizing-sports-metrics-transforming-data-into-winning-decisions/), [Domo](https://www.domo.com/learn/article/top-10-dashboard-design-mistakes-and-what-to-do-about-them))
- One anecdote: a hockey team tracked 30+ stats, the coaches couldn't tell where to focus, and they stopped using it. ([Data Engineer Insights](https://www.emilingemarkarlsson.com/blog/post-14/))
- "Too simple and analysts revolt, too complex and coaches ignore it." The suggested fix is separate views for separate audiences. ([Shakuro](https://shakuro.com/blog/sports-analytics-software-development))

**For ShuttlEye:** the casual player's first screen shows only a few things. Deeper tabs are optional.

### 6. Always give a benchmark
- A number on its own means little. Compare it with the league, a peer or the player's own past. ([Harvard Science Review](https://harvardsciencereview.org/2025/08/08/visualizing-sports-metrics-transforming-data-into-winning-decisions/))
- Strava shows each effort against your own 3-week average and a 12-week trend. Live Segments compare you with your PR or a friend. ([Bikerumor](https://bikerumor.com/2018/04/23/strava-adds-new-mobile-relative-effort-training-metric-for-premium-members/), [Bicycling](https://www.bicycling.co.za/training/this-strava-feature-helped-me-crush-my-most-elusive-pr/))

### 7. Combine stats across many matches
- SwingVision's most common complaint: "so many useful stats, but it is difficult to view those stats in the aggregate", meaning per game only, never across games. ([App Store reviews](https://apps.apple.com/au/app/swing-tennis/id989461317), [Tennis.com](https://prod.tennis.com/news/articles/swingvision-delivers-pro-level-insights-for-recreational-players))
- A forum post on reviewing your own matches put it as "four patterns that happened six times each" being what you want. ([TableTennisDaily](https://www.tabletennisdaily.com/forum/goto/post?id=374477))

**For ShuttlEye:** a profile is a summary across matches by nature. Filters by match or opponent let you narrow it down.

## What doesn't work

### 1. Radar and pizza charts
- The shape a reader sees depends on **the order of the axes and how the scales were chosen**, not just the data. Values that aren't next to each other are hard to compare, while a bar chart makes the same difference obvious. ([PyMC Labs, "Radar Plots Must Die"](https://www.pymc-labs.com/blog-posts/radar-plots-must-die))
- Even the people defending radars accept these flaws. StatsBomb now shows each metric's full distribution next to the radar to reduce misreading. ([CannonStats](https://www.cannonstats.com/p/do-radar-plots-need-to-die))

**For ShuttlEye:** use percentile strips or bars, not radars.

### 2. Heatmaps read as "where they were good"
- A heatmap shows **where things happened, not whether they worked**. "A red-hot area doesn't mean the player was effective there." ([The Football Analyst](https://the-footballanalyst.com/heatmaps-in-football-what-they-really-tell-you/), [SSANZ](https://ssanz.org.nz/heat-maps-in-football-how-to-read-them))
- A single-match heatmap is skewed by the context of that match, so aggregate over several matches. ([Kiqiq](https://kiqiq.com/blog/football-heatmaps))

**For ShuttlEye:** always pair a location with its outcome (win rate) and a sample count.

### 3. Hiding small samples
- Small samples produce extreme values in both directions. Sports stats rarely show uncertainty, unlike science. ([Data Colada](https://datacolada.org/?p=671), [Chad Orzel](https://chadorzel.com/principles/wp-json/wp/v2/posts/8143))

**For ShuttlEye:** show the sample size beside every stat ("from 46 rallies"), and grey out or hide stats built on too few shots.

### 4. Too many stats on one screen
- See "What works" #5. Overloaded dashboards get ignored.

## Design principles for the profile page

1. **Compare everything with the other pros.** Show stats as percentiles or as "vs pro average", like Savant.
2. **Court maps encode two things:** marker size = how often, colour = how well. Never a plain heatmap.
3. **Every number opens its rallies.** Clicking a stat or pattern plays the example rallies from BWF's YouTube video.
4. **Use rally-length bands** (0–4 / 5–8 / 9+) for how points are won.
5. **3–5 things on the first screen** for the casual player. Deeper tabs are optional.
6. **Show the sample size everywhere.** Grey out stats with too few shots.
7. **No radar charts.** Use percentile strips and bars.
