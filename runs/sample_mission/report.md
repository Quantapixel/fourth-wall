# Mission report: sample_mission

- **Outcome:** `rendezvous` after 56 actions (58/450 time units)
- **Battery left:** 40.0/110; cells travelled: 44

## Assessment

- **EVE located:** yes (direct sighting)
- **Inferred location:** (27, 20), confidence 100% within 2 cells; 90% credible region: 1 cells
- **Inferred status:** active (100%); posterior active 100%, dormant 0%, damaged 0%

## Recommended next step

EVE is active at (27, 20). Hold position beside her, flash the greeting light and let her lead; nearest charger is 8 battery away if she wants to travel.

## Evidence (in order found)

1. t=0: Initial signal (2805-07-04T06:12:00Z): bearing 120.5°, strength 0.0655
2. t=1: Beacon scan at (1, 1): 208° / 0.340 / 974ms (P(EVE)=0.00); 92° / 0.193 / 990ms (P(EVE)=0.91); 123° / 0.054 / 963ms (P(EVE)=0.00)
3. t=8: Beacon scan at (4, 4): 69° / 0.144 / 974ms (P(EVE)=0.00); 125° / 0.106 / 997ms (P(EVE)=1.00); 176° / 0.226 / 983ms (P(EVE)=0.00)
4. t=14: Beacon scan at (8, 5): 35° / 0.235 / 1032ms (P(EVE)=0.00); 118° / 0.208 / 998ms (P(EVE)=1.00); 254° / 0.270 / 942ms (P(EVE)=0.00)
5. t=19: Beacon scan at (12, 5): 132° / 0.192 / 1006ms (P(EVE)=1.00); 216° / 0.242 / 955ms (P(EVE)=0.00); 86° / 0.253 / 920ms (P(EVE)=0.00)
6. t=27: Beacon scan at (14, 9): 123° / 0.191 / 996ms (P(EVE)=1.00); 245° / 0.320 / 1027ms (P(EVE)=0.00); 51° / 0.228 / 1012ms (P(EVE)=0.00)
7. t=33: Beacon scan at (18, 10): 131° / 0.165 / 1004ms (P(EVE)=1.00); 62° / 0.318 / 1019ms (P(EVE)=0.00); 251° / 0.146 / 956ms (P(EVE)=0.00)
8. t=39: Beacon scan at (22, 11): 276° / 0.081 / 991ms (P(EVE)=0.02); 35° / 0.366 / 1066ms (P(EVE)=0.00)
9. t=44: Beacon scan at (26, 11): 41° / 0.428 / 1063ms (P(EVE)=0.00); 178° / 0.517 / 993ms (P(EVE)=1.00); 266° / 0.134 / 983ms (P(EVE)=0.00)
10. t=54: Beacon scan at (26, 18): 160° / 0.866 / 998ms (P(EVE)=1.00); 284° / 0.099 / 1047ms (P(EVE)=0.00); 349° / 0.241 / 978ms (P(EVE)=0.00)
11. t=58: **EVE sighted** at (27, 20): EVE is hovering, scanner sweeping. She sees you.

## Strategy changes

| t | at | change | why |
|---|---|---|---|
| 1 | (1, 1) | target → [19, 6] | mass 0.0963 at travel cost 25 |
| 8 | (4, 4) | target → [21, 10] | mass 0.1169 at travel cost 25 |
| 19 | (12, 5) | target → [24, 12] | mass 0.2658 at travel cost 21 |
| 27 | (14, 9) | target → [27, 14] | mass 0.3055 at travel cost 18 |
| 33 | (18, 10) | target → [28, 17] | mass 0.3494 at travel cost 17 |
| 44 | (26, 11) | mode → INVESTIGATE | SEARCH -> INVESTIGATE: best target holds 61% of the belief within scan radius |
| 44 | (26, 11) | target → [27, 18] | mass 0.6126 at travel cost 8 |
| 54 | (26, 18) | target → [27, 20] | mass 0.9667 at travel cost 3 |
| 58 | (27, 19) | mode → DONE | INVESTIGATE -> DONE: reached EVE |

## Evaluation against ground truth

_Hidden from the agent during the mission._

- True EVE position (27, 20), status active
- Location error: 0.0 cells; status correct: True
- Clues found: 0/6; decoys identified: 0/2

## Map

```
+----------------------------------------+
|.........##~#.~.....~...~~....~.........|
|.S**....##..#.~....~..~....~xm..........|
|..~*....#...#.......~.........#...~.....|
|.~.**...#...###..##~.......##.#.......#.|
|...~*......##.....~..~....~~..........#.|
|....*********....~..~.........~~........|
|..~~....##~.*..#~.~.....##~~..#.~.......|
|...~~..~....***##....##.##...##...##....|
|.......~#.~###*##.....##.~..~#..~.......|
|....~...#.###.*#....~..##.~.............|
|~.~~#...##....*****~....~.t..~.###~.....|
|.#..#.~..........~*********....t........|
|##.........~....~......~.#*.............|
|#...~...........#.#.~##..#*.............|
|#........~..~...####.###.#*....~..~##...|
|#..~............####.#####*.~.C..~~.~..~|
|.....~.....C.~.~..#..####.*.............|
|x..~.~......##~~.~....###.*...~....~....|
|........#...........###..~**....~.....~.|
|#.....###..##......##.#...~W.##........~|
|###..###...##.##...t....p.~E.##~........|
|.#.....#...#..#.........##...#.~........|
|.......#..~.~~#~........##~.....~d......|
|......##~...~.#~...............~..~.....|
|##....##..#~.~..........~........#......|
|#........##~...~......#..........#....##|
+----------------------------------------+
W WALL-E  E EVE  ? inferred  S base  C charger  * path  # wall  ~ rubble  T/D/P/M clue found (t/d/p/m missed)  X decoy found (x missed)  .:-=+*%@ belief
```
