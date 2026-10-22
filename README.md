# DeskSpace

A puzzle, set in a small spaceship cabin parked at Saturn, and the whole site is that one page. You're the administrator of a ship registry, alone out here. Drag to look around, scroll or pinch to move closer, click things. The laptop is a locked registry terminal (messages, the registry, settings, Snake), the phone is a radio (on a stand, its screen showing what's playing), the guitar plays, and a light outside the window is trying to say something.

## Run it

```sh
npm install
npm run dev
```

`npm run build` writes the static site to `dist/`. Publish that folder anywhere that serves static files.

## How the homepage loads

1. The HTML arrives with the still (`public/cabin-still.webp`) and a menu that appears when you press Tab. Without JavaScript, that's the homepage.
2. `src/scripts/ui.js` adds hotspots over the props in the still, the dialogs, sound, the radio, the guitar and the puzzle.
3. Once the page has loaded, devices with WebGL 2 on a real GPU load `src/scripts/cabin.js` and three.js, which draw the same view live and fade in over the still. Meanwhile you're waking up at the desk: black, and the eyes opening a little, blurred, as the still and then the scene's code arrive; once the scene is drawn they open for good. Blinks still to come are dropped once it's ready, so a fast load is one blink. A click (or Enter or Space) wakes you as soon as it's ready and turns the sound on. With reduced motion it's a fade from black; it gives up after 20 seconds whatever happens. From then on the cabin is a 3D room: drag to look around, scroll or pinch to zoom in towards the pointer (far enough to read the Morse card from the chair), and clicking a prop flies the camera to it before its dialog opens. The room also moves a little: steam off the coffee, dust in the lamp's beam, haze drifting under the ceiling, film grain over everything, and a bare bulb that flickers every 8 to 16 seconds (never more than three dips a second, and never more than 9% darker). With reduced motion asked for, all of that stays still. The look is low-key and industrial: grimy walls with rust run down from the viewport, services run in the open beside it, and the room lit mostly by the desk lamp, the bulb and the screens. The lever under the desk's edge (also in the Tab menu) switches the gravity off: the loose things on the desk lift, hover and slowly turn. Grab one and throw it: it tumbles, bounces off the walls, ceiling, desk and the props that stay put, and drifts back to its spot after a few seconds. Switched on again, everything drops (or hops, from across the room) back into place. With reduced motion, things go straight to where they end up, and a thing you drag stays where you let go. `?plain=1` skips this step and keeps the still, and has no gravity switch.

## The laptop

The laptop's terminal is plain HTML (`src/components/Laptop.astro`, run by `src/scripts/laptop.js`), so it can be typed into, read aloud and played with the keyboard. In the live scene it's laid exactly over the 3D screen, which is cut out of the render so it shows through; click the laptop and the camera goes up to it, and Escape steps back. On a narrow screen, or without the live scene, it opens in a dialog instead. Snake's rules are in `src/scripts/snake.js`. Progress is kept in the browser (`src/scripts/progress.js`); Settings has a Reset.

The password is what the light in the window blinks (`SIGNAL` in `src/pages/index.astro`); the terminal keeps only its SHA-256. All the words in the terminal are drafts.

## The puzzle so far

The story: the administrator is a front-end developer who lost the job to AI and took a minimum-wage post out by Saturn. The AI isn't the villain; the point is that a person still has something to offer beside it. All the words are drafts.

1. The light in the window blinks the laptop's password in Morse; the card on the wall is the key. Messages from old colleagues set the scene.
2. Three tracks open, in any order:
   - The song: a message about a snake bite points at Snake. Eat three dots, then bite yourself, and Major Tom arrives. The guitar's G string has slipped flat (the tuner and G peg are in its panel), and the songbook gives the chords.
   - Gravity: the control panel under the desk (SYNC) flashes a pattern to play back; then Settings can enable the lever. With the gravity off, the plectrum floats out from under the mug, and the crack in the window starts to whistle: its draught takes the DO NOT LOSE disc case up out of the pile and along the glass until it sticks over the crack. Grab it and it comes back and turns over: the backup's password is on a sticker underneath, readable zoomed in. Clicking the crack tapes it (the "fix the crack" post-it points at it), and the leak stops for good. Each post-it has its own line, most of them a nudge. Also with the gravity off, squeezing the water pouch on the desk lets out wobbling blobs of water to throw at the snake plant, which bounces when one reaches it; that's only for fun.
   - Worth: Settings restores BACKUP 2009 and PHOTOS 2011 with that password, bringing back the administrator's portfolio (the bezel.js docs and a post on units) and his photos: Mum, Barry next door, Jess and Marco, and the bezel.js launch, whose slide reads "Every panel should have a way back to a person." The photos are one-bit stand-ins drawn in `laptop.js`.
3. Play C Em C Em in tune, and a ship's AI hears the only human voice out there. Its ship glides in and stops left of Saturn. Zoomed in from the window, its hull reads 715120; the registry takes four letters, and 7-15-1-20 is GOAT. Checking it shows the owner, GOAT Capital, and opens a channel: the AI is stuck between the investors' orders and the ship is sinking toward Saturn.
4. The ship link on the laptop, in three steps: free the crew's manual controls from a bezel.js notice (HTML, with a live preview; press the button once it's free), fix the units in the flight code (JavaScript, run in the browser; pound-force seconds to newton-seconds), then choose what to jettison. Only the GPU racks work, and only a person can break the investors' order to keep them.
5. The ship climbs away once you step back from the laptop. Its engines tell the story: a steady burn as it glides in, a low idle when it stops, cold while it sinks (only its attitude thrusters puff), and a full burn as it climbs away. Once it's clear, the AI's last message says why it called you: your name is in bezel.js's credits, and it quotes your slide back to you. Then the phone buzzes with a voice message from Earth, sent 79 minutes earlier (light's travel time): the Frontend Developer Conference wants you for its closing keynote, on Earth, on Tuesday. GOAT heard it, comes back for you and waits in the window, and the end card says part two starts at Jupiter. With reduced motion, the ship leaves as you step back from the laptop.

Now and then a shooting star crosses the window, and something drifts past it, once each and never again (`seen-*` in progress): a lost teddy bear in a scarf, and Voyager 1, almost a light-day from home and very lost. Their pictures are drawn by `scene/cabin.py` (`teddy.webp`, `voyager.webp`); `window.cabin.visit('teddy')`, `'voyager'` or `'star'` brings one on now.

Each step is saved as you go (`progress.js`).

## The cabin

`scene/cabin.py` builds the whole scene in Blender and writes everything the site uses:

| File | What it is |
|---|---|
| `public/cabin-still.webp` | 1920×1080 render, the first paint |
| `public/og.jpg` | 1200×630 share card |
| `public/scene/cabin.glb` | the live scene: the cabin with its lighting baked into one texture, the laptop screen, the window glass (smudges and the crack, painted into one see-through picture), three sheets of haze, the bare bulb, the loose things that float without gravity (`float-*`, baked into the same texture) and the gravity lever and lamp, Saturn and the passing ship as sharp transparent pictures far outside, invisible boxes for picking props, where the beacon, steam and dust go, and the camera. Geometry is Meshopt-compressed. |
| `public/scene/screen-smudge.webp` | the fingerprints and smears on the laptop screen, laid over the terminal as they are in the still |
| `public/scene/ship.webp` | the passing ship, loaded only once it comes |
| `public/scene/sky.webp` | a 360° panorama of everything else outside (stars, nebula, the Milky Way, Saturn's six largest moons), drawn as the live scene's background |
| `src/data/cabin.json` | where each prop sits in the still, for the hotspots, and the room's bounds for things thrown about |

```sh
sh scene/fetch-assets.sh
blender -b --factory-startup -P scene/cabin.py
```

`scene/fetch-assets.sh` downloads the textures and fonts into `scene/assets/` (about 70 MB, not in git); it only needs running once. The textures are 15 photo sets from ambientCG, all CC0. The fonts are Caveat and Anton (SIL Open Font License) and Permanent Marker (Apache 2.0), from Google Fonts, each saved with its licence. Only the baked result ships with the site.

A full run takes about 20 minutes. `FAST=1` in front of it gives a rougher result in about 3. Change the script, not `scene/cabin.blend`: every run rebuilds the .blend.

Small things survive close zoom for two reasons. The script raises the glTF exporter's position precision from 12 to 16 bits: at 12, everything snaps to a 2 mm grid, so lettering 1 mm in front of a card merges with it. That setting isn't an export option, so the build fails if a Blender update moves it. And small lettering painted in the same material as a big surface gets its own material, so `island_scale` can give it more of the texture; otherwise its letters take colour from their neighbours and break up.

Saturn's size and ring edges, and the moons' sizes and distances, come from NASA's fact sheets. The Morse table is the ITU one, in `src/data/morse.json`, shared by the card on the wall and the chart on the page. Sounds are generated in the browser.

## Still to do

- Rewrite the draft copy. All of it is in `src/data/copy.json`; the words under `painted` (post-its, poster, labels) need a new render to show.
- Add real music to the radio. It plays generated music for now.
