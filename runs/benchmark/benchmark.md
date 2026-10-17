# Benchmark: 100 random missions per tier (seeds 1000..1099)

| tier | agent | success | stranded | mean time (success) | median loc. error | status acc. | clues found |
|---|---|---|---|---|---|---|---|
| easy | belief | 100% | 0% | 30.9 | 0.0 | 100% | 0.95 |
| easy | greedy | 69% | 0% | 77.5 | 0.0 | 69% | 1.42 |
| easy | random | 3% | 0% | 241 | 16.88 | 33% | 0.91 |
| medium | belief | 100% | 0% | 48.5 | 0.0 | 100% | 0.91 |
| medium | greedy | 13% | 0% | 93.2 | 14.32 | 30% | 0.5 |
| medium | random | 1% | 0% | 369 | 25.66 | 31% | 0.34 |
| hard | belief | 100% | 0% | 77.4 | 0.0 | 100% | 1.03 |
| hard | greedy | 10% | 0% | 109.4 | 17.58 | 29% | 0.45 |
| hard | random | 0% | 0% | - | 30.75 | 29% | 0.18 |
| extreme | belief | 52% | 0% | 106.5 | 0.0 | 84% | 0.6 |
| extreme | greedy | 5% | 16% | 88.8 | 25.07 | 34% | 0.13 |
| extreme | random | 0% | 0% | - | 36.42 | 34% | 0.04 |

Tier settings:

```json
{
  "easy": {
    "map": {
      "width": 24,
      "height": 16,
      "obstacle_density": 0.1,
      "rubble_density": 0.08,
      "chargers": 2
    },
    "resources": {
      "battery": 200,
      "time_limit": 400
    },
    "sensors": {
      "bearing_noise_deg": 10,
      "strength_noise": 0.03
    },
    "decoys": {
      "count": 0
    }
  },
  "medium": {
    "map": {
      "width": 32,
      "height": 22,
      "obstacle_density": 0.13,
      "rubble_density": 0.1,
      "chargers": 3
    },
    "resources": {
      "battery": 140,
      "time_limit": 400
    },
    "sensors": {
      "bearing_noise_deg": 15,
      "strength_noise": 0.04
    },
    "decoys": {
      "count": 1
    }
  },
  "hard": {
    "map": {
      "width": 40,
      "height": 26,
      "obstacle_density": 0.15,
      "rubble_density": 0.12,
      "chargers": 3
    },
    "resources": {
      "battery": 100,
      "time_limit": 350
    },
    "sensors": {
      "bearing_noise_deg": 20,
      "strength_noise": 0.06
    },
    "decoys": {
      "count": 2
    }
  },
  "extreme": {
    "map": {
      "width": 48,
      "height": 32,
      "obstacle_density": 0.16,
      "rubble_density": 0.15,
      "chargers": 3
    },
    "resources": {
      "battery": 70,
      "time_limit": 220
    },
    "sensors": {
      "bearing_noise_deg": 25,
      "strength_noise": 0.07
    },
    "clues": {
      "count": 4
    },
    "decoys": {
      "count": 3
    }
  }
}
```
