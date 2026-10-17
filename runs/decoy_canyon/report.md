# Mission report: decoy_canyon

- **Outcome:** `rendezvous` after 58 actions (60/110 time units)
- **Battery left:** 19.0/90; cells travelled: 46

## Assessment

- **EVE located:** yes (direct sighting)
- **Inferred location:** (29, 14), confidence 100% within 2 cells; 90% credible region: 1 cells
- **Inferred status:** damaged (100%); posterior active 0%, dormant 0%, damaged 100%

## Recommended next step

EVE is damaged at (29, 14). Stabilise her, then tow her to the nearest charger (11 battery away) and scavenge parts for repairs before the next storm.

## Evidence (in order found)

1. t=0: Initial signal (2805-07-04T05:40:00Z): bearing 118°, strength 0.09, rough fix (22, 11) ±7
2. t=1: Beacon scan at (0, 0): 123° / 0.252 / 1006ms (P(EVE)=0.01); 113° / 0.006 / 1004ms (P(EVE)=0.98); 170° / 0.263 / 1020ms (P(EVE)=0.00)
3. t=7: Beacon scan at (1, 4): 162° / 0.528 / 1025ms (P(EVE)=0.00); 123° / 0.338 / 998ms (P(EVE)=0.89)
4. t=13: Beacon scan at (2, 8): 94° / 0.081 / 999ms (P(EVE)=1.00); 146° / 0.831 / 956ms (P(EVE)=0.00); 85° / 0.401 / 966ms (P(EVE)=0.00)
5. t=20: Beacon scan at (6, 10): 206° / 1.133 / 941ms (P(EVE)=0.00); 114° / 0.747 / 954ms (P(EVE)=0.00); 78° / 0.096 / 1000ms (P(EVE)=1.00)
6. t=26: Beacon scan at (10, 9): 241° / 0.815 / 986ms (P(EVE)=0.00); 90° / 1.085 / 980ms (P(EVE)=0.00); 111° / 0.140 / 1000ms (P(EVE)=1.00)
7. t=32: Beacon scan at (14, 8): 107° / 0.140 / 998ms (P(EVE)=1.00); 243° / 0.422 / 1039ms (P(EVE)=0.00)
8. t=43: Beacon scan at (21, 11): 262° / 0.251 / 952ms (P(EVE)=0.00); 278° / 0.802 / 1022ms (P(EVE)=0.00); 113° / 0.327 / 1001ms (P(EVE)=1.00)
9. t=50: Clue **debris** at (27, 12): White hull fragments, still warm. (freshness=fresh)
10. t=57: Beacon scan at (28, 13): 270° / 0.151 / 1013ms (P(EVE)=0.00); 266° / 0.355 / 1019ms (P(EVE)=0.00)
11. t=59: **EVE sighted** at (29, 14): EVE is grounded, scorched, beacon flickering.

## Strategy changes

| t | at | change | why |
|---|---|---|---|
| 1 | (0, 0) | target → [25, 10] | mass 0.1411 at travel cost 35 |
| 7 | (1, 4) | target → [12, 11] | mass 0.3042 at travel cost 18 |
| 13 | (2, 8) | target → [23, 9] | mass 0.16 at travel cost 26 |
| 32 | (14, 8) | mode → INVESTIGATE | SEARCH -> INVESTIGATE: best target holds 46% of the belief within scan radius |
| 32 | (14, 8) | target → [26, 11] | mass 0.4622 at travel cost 15 |
| 50 | (26, 11) | target → [28, 13] | mass 0.7516 at travel cost 4 |
| 59 | (28, 13) | mode → RENDEZVOUS | INVESTIGATE -> RENDEZVOUS: EVE confirmed at (29, 14) |
| 60 | (28, 14) | mode → DONE | RENDEZVOUS -> DONE: reached EVE |

## Evaluation against ground truth

_Hidden from the agent during the mission._

- True EVE position (29, 14), status damaged
- Location error: 0.0 cells; status correct: True
- Clues found: 1/4; decoys identified: 0/2

## Map

```
+------------------------------+
|S.....~.....#.................|
|*.##..~.....#....~~...........|
|*.##........#....~~.....###...|
|**....###...#...........#.....|
|~**...#.........###.....#.....|
|~~*...#..C......#.......#.....|
|..*.......m..~..#.............|
|..*####......~..#....~~.......|
|..*...#...******....~~~...##..|
|..****#****####*.....t......#.|
|..~..***......#*......C.....#.|
|..~~..........x************...|
|.....x...~~...........###.*D..|
|.....#####.........~.....#***.|
|.............~~~..........#.WE|
|........................t.....|
+------------------------------+
W WALL-E  E EVE  ? inferred  S base  C charger  * path  # wall  ~ rubble  T/D/P/M clue found (t/d/p/m missed)  X decoy found (x missed)  .:-=+*%@ belief
```
