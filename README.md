# Zombie Outbreak V7

A free zombie shooter made with Godot 4. Hold the street against endless waves, take down giant bosses, tune your guns in the Gunsmith and fight 5v5 team battles.

## Play

- **In your browser:** https://exibel95-rgb.github.io/zombieoutbreak/play/ (best in Chrome, Edge or Firefox on a computer)
- **Android client:** https://exibel95-rgb.github.io/zombieoutbreak/#client (Android 7+, 64-bit)

The project page is https://exibel95-rgb.github.io/zombieoutbreak/

## What's in this repository

| Folder | What it is |
| --- | --- |
| `docs/` | The website (GitHub Pages): landing page, the browser build in `docs/play/` and the Android APK in `docs/client/` |
| `docs/play/pck/` | The game data, split into parts under 100 MB (GitHub's file limit); the page joins them in the browser |
| `docs/client/` | The Android APK in 4 parts; the "Download APK" button joins them into one file |
| `server/relay.py` | The online relay server used for worldwide multiplayer rooms (pure Python, no packages) |

Join the APK parts by hand (Termux, Linux or macOS):

```sh
cat apk_part0.bin apk_part1.bin apk_part2.bin apk_part3.bin > ZombieOutbreak_V7.apk
```

## Online relay server

`server/relay.py` lets players anywhere connect to each other without port forwarding. It runs on any host that gives you one web port; it reads the port from `$PORT`:

```sh
PORT=8080 python3 server/relay.py
```

`render.yaml` deploys it as a free web service on Render (New > Blueprint > pick this repo).

## Credits

- "Zombie (Rigged & Animated)" by Aiden Studios, CC BY 4.0: https://sketchfab.com/3d-models/zombie-rigged-animated-131688807ad444609ed9b2ed572dc4aa
- "CREATURE MONSTER 3D BY Oscar Creativo" by OSCAR CREATIVO, CC BY 4.0, resized for mobile: https://sketchfab.com/3d-models/creature-monster-3d-by-oscar-creativo-03bff460ebdc4103b42a14d56131db78
- "werewolf" by silvercrow101, CC BY 4.0, reduced, recoloured, animations retargeted: https://sketchfab.com/3d-models/werewolf-2dd83cb880f047d3bb2085f13e1efc08
- "Yeti" by orioltron, CC BY 4.0, rigged onto the werewolf skeleton: https://sketchfab.com/3d-models/yeti-daa4e743128f44c7859c5c34588518a7
- Public domain (CC0): Stein Games weapons pack; Quaternius guns, spider and animation library; Flat Guns (OpenGameArt); Lava Golem by gavlig; Forest Monster by CDmir; Cethiel's Dragon by Drummyfish; textures and props from Poly Haven and ambientCG; boss conversions from the ymmo project.
- "Giang 20" toad monster by asset-animated (CGTrader, Royalty Free licence).
- "Military zombie set 3" by dima-dyl (CGTrader, Royalty Free licence), the regular zombies.
- Made with the Godot Engine (MIT licence), https://godotengine.org

CC BY 4.0: https://creativecommons.org/licenses/by/4.0/
