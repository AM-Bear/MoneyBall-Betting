# MLB Stats API curl transcripts — verified 2026-08-20 from inside Replit

Every endpoint the v2 data layer actually uses, with a truncated real response.

## 1. Team hitting (season aggregates, all 30 teams)
```
$ curl -s "https://statsapi.mlb.com/api/v1/teams/stats?season=2026&group=hitting&stats=season&sportId=1"
splits: 30
{
  "team": "Tampa Bay Rays",
  "obp": ".332",
  "slg": ".408",
  "runs": 578
}
```

## 2. Team pitching (season aggregates — OBP/SLG-against = live OOBP/OSLG)
```
$ curl -s "https://statsapi.mlb.com/api/v1/teams/stats?season=2026&group=pitching&stats=season&sportId=1"
splits: 30
{
  "team": "New York Yankees",
  "obp_against": ".295",
  "slg_against": ".362",
  "runs_allowed": 470
}
```

## 3a. League-wide player pool — hitting, qualified
```
$ curl -s "https://statsapi.mlb.com/api/v1/stats?stats=season&group=hitting&season=2026&sportId=1&playerPool=qualified&limit=2000"
qualified hitters: 140
{
  "player_id": 650333,
  "name": "Luis Arraez",
  "team": "Philadelphia Phillies",
  "pa": 533,
  "obp": ".353",
  "slg": ".440",
  "avg": ".319",
  "hr": 6
}
```

## 3b. League-wide player pool — pitching, qualified
```
$ curl -s "https://statsapi.mlb.com/api/v1/stats?stats=season&group=pitching&season=2026&sportId=1&playerPool=qualified&limit=2000"
qualified pitchers: 53
{
  "player_id": 694819,
  "name": "Jacob Misiorowski",
  "ip": "139.0",
  "era": "1.75",
  "whip": "0.75",
  "obp_against": ".215",
  "slg_against": ".245",
  "gamesStarted": 23
}
```

## 4. Schedule + probable pitchers + linescore (slate pricing + grading source)
```
$ curl -s "https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=2026-08-20&hydrate=probablePitcher,linescore"
games today: 9
{
  "gamePk": 824474,
  "away": "St. Louis Cardinals",
  "away_probable": "Michael McGreevy",
  "home": "Cincinnati Reds",
  "home_probable": "Brady Singer",
  "status": "In Progress"
}
```

## 4b. Yesterday's finals via the same endpoint (grading)
```
$ curl -s "https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=2026-08-19&hydrate=probablePitcher,linescore"
games: 15 finals: 15
{
  "gamePk": 823342,
  "away": "Detroit Tigers",
  "away_score": 3,
  "home": "Pittsburgh Pirates",
  "home_score": 4
}
```

## 5. Standings (W-L, RS/RA, games played → remaining schedule count)
```
$ curl -s "https://statsapi.mlb.com/api/v1/standings?leagueId=103,104&season=2026&standingsTypes=regularSeason"
division records: 6 teams: 30
{
  "team": "Rays",
  "w": 76,
  "l": 50,
  "rs": 578,
  "ra": 529,
  "gp": 126,
  "divisionRank": "1"
}
```

## 6. 40-man roster + IL status (injury flags)
```
$ curl -s "https://statsapi.mlb.com/api/v1/teams/147/roster?rosterType=40Man&season=2026"
roster size: 42 on IL: 6
{"player_id": 592450, "name": "Aaron Judge", "status": "Injured 60-Day"}
{"player_id": 657376, "name": "Clarke Schmidt", "status": "Injured 60-Day"}
{"player_id": 641355, "name": "Cody Bellinger", "status": "Injured 10-Day"}
{"player_id": 519317, "name": "Giancarlo Stanton", "status": "Injured 10-Day"}
```

## 7. Transactions (trades, signings, IL moves)
```
$ curl -s "https://statsapi.mlb.com/api/v1/transactions?startDate=2026-08-13&endDate=2026-08-20"
transactions past 7 days: 1105
{
  "id": 937385,
  "date": "2026-08-13",
  "typeDesc": "Status Change",
  "description": "Toronto Blue Jays placed LHP Brendon Little on the paternity list."
}
```

## 8. MLB.com RSS news headlines
```
$ curl -s "https://www.mlb.com/feeds/news/rss.xml"
items: 25
title: 30 big questions for stretch run -- 1 for each team
link: https://www.mlb.com/news/big-questions-facing-mlb-teams-down-the-stretch-2026
pubDate: Thu, 20 Aug 2026 15:30:00 GMT
```

## 9. ESPN public JSON (optional second source) — tried once per spec
```
$ curl -s -o /dev/null -w "%{http_code}" "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/news"
HTTP 200
articles: 6
```

## 10. Per-team season stats (v1 slate pricing inputs — used per team id)
```
$ curl -s "https://statsapi.mlb.com/api/v1/teams/139/stats?stats=season&group=hitting&season=2026"
{
  "obp": ".332",
  "slg": ".408",
  "runs": 578,
  "plateAppearances": 4770
}
```

## 11. Live game feed (v1 grading source, kept in v2)
```
$ curl -s "https://statsapi.mlb.com/api/v1.1/game/823342/feed/live"
{
  "state": "Final",
  "away": "Detroit Tigers",
  "home": "Pittsburgh Pirates",
  "away_runs": 3,
  "home_runs": 4
}
```

## 12. Season dates (regular-season end date for the rest-of-season sim)
```
$ curl -s "https://statsapi.mlb.com/api/v1/seasons?season=2026&sportId=1"
{
  "seasonId": "2026",
  "regularSeasonStartDate": "2026-03-25",
  "regularSeasonEndDate": "2026-09-27"
}
```

## 13. Remaining regular-season schedule range (sim input)
```
$ curl -s "https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate=2026-08-20&endDate=2026-09-27&gameType=R"
dates: 39 remaining regular-season games: 520
```

## 14. Deep player pools (playerPool=all, floor applied app-side: ≥100 PA or ≥30 IP)
```
$ curl -s "https://statsapi.mlb.com/api/v1/stats?stats=season&group=hitting&season=2026&sportId=1&playerPool=all&limit=2000&offset=0"
splits returned: 710 totalSplits: 710
$ curl -s "https://statsapi.mlb.com/api/v1/stats?stats=season&group=pitching&season=2026&sportId=1&playerPool=all&limit=2000&offset=0"
splits returned: 812 totalSplits: 812
```
