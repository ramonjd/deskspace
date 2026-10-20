// The live cabin. Loaded only after the homepage has painted, on devices that
// passed the WebGL 2 check in index.astro. It starts from the same view as the
// still and fades in over it; then you can drag to look around, scroll or
// pinch to move closer, and click things. Clicking a prop hands it to ui.js,
// which opens its dialog; the camera flies to the prop first and back after.
// Clicking the window flies up to the glass to look around space. Unless
// reduced motion is asked for, the room keeps quietly moving: steam, dust,
// haze, and a bare bulb that flickers now and then. The lever under the
// desk's edge switches the gravity off and on; with it off, you can grab the
// floating things and throw them about.

import {
	AdditiveBlending,
	Box3,
	BufferAttribute,
	CatmullRomCurve3,
	BufferGeometry,
	CanvasTexture,
	Color,
	EquirectangularReflectionMapping,
	Matrix4,
	Mesh,
	MeshBasicMaterial,
	NoBlending,
	Plane,
	PlaneGeometry,
	Points,
	PointsMaterial,
	Quaternion,
	Raycaster,
	SRGBColorSpace,
	Scene,
	SphereGeometry,
	Sprite,
	SpriteMaterial,
	TextureLoader,
	Vector2,
	Vector3,
	WebGLRenderer,
} from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { CSS3DObject, CSS3DRenderer } from 'three/addons/renderers/CSS3DRenderer.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import cabinData from '../data/cabin.json';
import { progress } from './progress.js';

// The still is shown with object-fit: cover and object-position: 45% 60%.
// The camera crops the same way, so the first frame lines up with it.
const STILL = { width: cabinData.still.width, height: cabinData.still.height, x: 0.45, y: 0.6 };

// The laptop's terminal (src/components/Laptop.astro) is laid out at this
// size in CSS pixels, then scaled onto the 3D screen.
const TERMINAL = { width: 1024, height: 640 };

// Where the camera goes when a prop is clicked: distance is how close it gets
// before the dialog opens, and zoom how far scrolling or pinching can zoom in
// there, beside a side panel. The laptop and the Morse card are different:
// the camera goes square on to the screen or straight up to the card, close
// enough for it to fill this much of the view, and stays until Escape or
// Step back.
const VIEWS = {
	laptop: { screen: true, fill: 0.86 },
	panel: { distance: 1.2, zoom: 3 },
	guitar: { distance: 2.6 },
	phone: { distance: 1.3, zoom: 3 },
	morse: { straight: true, fill: 0.92, zoom: 3 },
};
const FLIGHT_SECONDS = 0.8;
// The passing ship: seconds to glide in and stop, to sink toward Saturn once
// it's in trouble, and to climb away once it's saved. sink is how far it
// goes toward Saturn; away is where it leaves to, from where it stopped.
// burn is how hard its engines burn, 0 to 1, at each of those; sinking, they
// are cold, and only its attitude thrusters puff, every puffs seconds or so.
const SHIP = {
	arrive: 40,
	sinking: 240,
	climb: 30,
	sink: 0.12,
	away: [-6, 5, 0],
	burn: { arriving: 0.55, parked: 0.12, sinking: 0, climbing: 1 },
	puffs: [1.2, 2.8],
};
// Jet trails: glowing exhaust left behind in space, as points that drift
// back from the nozzles at drift metres a second, and fade over seconds.
// rate is how many a second at each stage; none while it sits or sinks.
const TRAIL = { count: 700, seconds: 2.6, drift: 1.4, size: 0.6, rate: { arriving: 25, climbing: 110 } };

// Looking around: the camera circles a point on the desk, and these limits
// keep it inside the cabin, below the ceiling and above the desk. Zoom is far
// enough to read the Morse card from the chair.
const LOOK = {
	zoom: 6,
	azimuth: 0.6,
	minPolar: (68 * Math.PI) / 180,
	maxPolar: (92 * Math.PI) / 180,
};

// A press that moves less than this, in pixels, is a click, not a drag.
const CLICK_SLOP = 6;

// The room moving. Haze is how strongly the haze sheets add their light;
// halo, the bare bulb's glow. The bulb flickers every 8 to 16 seconds: one to
// three dips, starting at least gap seconds apart, so never more than three in
// a second. Steam puffs rise off the coffee, one after another; dust motes
// drift in the desk lamp's beam, out to spread of its width.
const AMBIENT = {
	fps: 30,
	haze: 0.675,
	halo: 0.3,
	flicker: { every: [8, 16], gap: 0.36 },
	steam: { puffs: 6, seconds: 4, rise: 0.4 },
	dust: { motes: 90, spread: 0.55 },
};

// Gravity, when the lever turns it off: things lift one after another over
// stagger seconds, easing up over a few times rise seconds, to hover lift
// metres above their places (pens and the stacked discs have heights of their
// own, in floatFrom). They lean up to lean radians, turn at up to turn radians
// a second (bigger things slower), and wander a centimetre or two. Turned
// back on, they fall at fall metres a second squared (things thrown across
// the room hop home at hop metres a second) and bounce off the desk at bounce
// times the speed they land. The lever swings through swing radians.
const GRAVITY = {
	lift: [0.05, 0.14],
	stagger: 0.8,
	rise: 0.6,
	lean: 0.35,
	turn: 0.25,
	wander: 0.015,
	fall: 9.81,
	bounce: 0.25,
	hop: 2.5,
	swing: (120 * Math.PI) / 180,
};

// Throwing, with the gravity off: a throw is at most fastest metres a second
// and sets a thing turning at up to spin radians a second. The cabin air slows
// it by air a second (its turning by spinAir); it bounces back at restitution
// times the speed it hits; and after home seconds a soft pull draws it back
// to where it was floating.
const THROW = { fastest: 5, spin: 8, air: 0.25, spinAir: 0.2, restitution: 0.5, home: 2.5, pull: 1.5 };

// The crack in the window, leaking while the gravity's off: the draught takes
// DO NOT LOSE to it in seconds, and once there it rattles by rattle metres.
const LEAK = { seconds: 12, rattle: 0.004 };

// Blobs of water from the pouch: radius metres across, at most most of them
// at once. One hitting something faster than splat metres a second splats;
// the plant that drinks one bounces for perk seconds.
const BLOB = { radius: 0.045, most: 6, splat: 0.35, perk: 0.7 };

export async function startCabin(stage, ui, laptop) {
	const canvas = stage.querySelector('.live');
	const still = stage.querySelector('.cabin');
	const label = stage.querySelector('.label');
	const hint = stage.querySelector('.hint');
	const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)');

	// cabin.glb's geometry is Meshopt-compressed by scene/cabin.py. sky.webp is
	// a 360 degree panorama of everything outside except Saturn.
	const [gltf, sky] = await Promise.all([
		new GLTFLoader().setMeshoptDecoder(MeshoptDecoder).loadAsync('/scene/cabin.glb'),
		new TextureLoader().loadAsync('/scene/sky.webp'),
	]);
	// The loader hands back a Group; only a Scene draws a background.
	const scene = new Scene();
	scene.add(gltf.scene);
	const camera = gltf.cameras[0];
	scene.attach(camera);
	sky.mapping = EquirectangularReflectionMapping;
	sky.colorSpace = SRGBColorSpace;
	scene.background = sky;

	// Light and colour grading are baked into these textures, so they're drawn
	// as is: no lights, no tone mapping. Saturn is a picture with a transparent
	// background, far out beyond the window.
	const cabin = scene.getObjectByName('cabin');
	cabin.material = new MeshBasicMaterial({ map: cabin.material.map, toneMapped: false });
	// The window glass: faint smudges and a crack, drawn see-through over whatever is outside.
	const glass = scene.getObjectByName('glass');
	glass.material = new MeshBasicMaterial({ map: glass.material.map, transparent: true, depthWrite: false, toneMapped: false });
	// Haze under the ceiling: sheets that only add light, as in the still.
	const haze = gltf.scene.children.filter((object) => object.name.startsWith('haze-'));
	for (const sheet of haze) {
		sheet.material = new MeshBasicMaterial({
			map: sheet.material.map,
			transparent: true,
			opacity: AMBIENT.haze,
			blending: AdditiveBlending,
			depthWrite: false,
			toneMapped: false,
		});
		sheet.userData.x = sheet.position.x;
	}
	const saturn = scene.getObjectByName('saturn-card');
	saturn.material = new MeshBasicMaterial({ map: saturn.material.map, transparent: true, depthWrite: false, toneMapped: false });

	// The boxes around each prop are only for picking, never drawn.
	const hits = gltf.scene.children.filter((object) => object.name.startsWith('hit-'));
	for (const hit of hits) {
		hit.material = new MeshBasicMaterial({ visible: false });
		hit.userData.prop = hit.name.slice(4);
	}
	const labels = {};
	for (const hotspot of stage.querySelectorAll('.hotspot')) {
		labels[hotspot.dataset.prop] = hotspot.dataset.label;
	}

	// ------------------------------------------------------------ the laptop's screen

	// The laptop runs the page's own HTML terminal (laptop.js). It sits in a
	// layer behind this canvas, placed and turned exactly like the 3D screen,
	// and the screen itself is drawn as a hole, so the terminal shows through
	// and anything in front of the screen still covers it. Its background is
	// the screen's colour in the still, so the two match.
	const sample = document.createElement('canvas').getContext('2d', { willReadFrequently: true });
	sample.canvas.width = sample.canvas.height = 1;
	const [left, top] = cabinData.hotspots.screen[0];
	const [right, bottom] = cabinData.hotspots.screen[2];
	await still.decode();
	sample.drawImage(still, ((left + right) / 200) * STILL.width, ((top + bottom) / 200) * STILL.height, 1, 1, 0, 0, 1, 1);
	const [r, g, b] = sample.getImageData(0, 0, 1, 1).data;
	const os = document.getElementById('laptop-os');
	os.style.setProperty('--os-bg', `rgb(${r} ${g} ${b})`);

	const screen = scene.getObjectByName('laptop-screen');
	screen.material = new MeshBasicMaterial({ color: 0x000000, opacity: 0, blending: NoBlending });
	// Its corners, found by their UVs: (0, 0) is the top left, as the terminal is laid out.
	scene.updateMatrixWorld(true);
	const uvs = screen.geometry.attributes.uv;
	function corner(u, v) {
		let best = 0;
		for (let i = 1; i < uvs.count; i++) {
			if (Math.abs(uvs.getX(i) - u) + Math.abs(uvs.getY(i) - v) < Math.abs(uvs.getX(best) - u) + Math.abs(uvs.getY(best) - v)) best = i;
		}
		return new Vector3().fromBufferAttribute(screen.geometry.attributes.position, best).applyMatrix4(screen.matrixWorld);
	}
	const corners = [corner(0, 0), corner(1, 0), corner(1, 1), corner(0, 1)];
	const screenAcross = corners[1].clone().sub(corners[0]);
	const screenDown = corners[3].clone().sub(corners[0]);
	const screenCentre = corners[0].clone().addScaledVector(screenAcross, 0.5).addScaledVector(screenDown, 0.5);
	const screenNormal = screenDown.clone().cross(screenAcross).normalize();
	const terminal = new CSS3DObject(os);
	terminal.position.copy(screenCentre);
	terminal.quaternion.setFromRotationMatrix(new Matrix4().makeBasis(screenAcross.clone().normalize(), screenDown.clone().negate().normalize(), screenNormal));
	terminal.scale.set(screenAcross.length() / TERMINAL.width, screenDown.length() / TERMINAL.height, 1);
	const terminalScene = new Scene();
	terminalScene.add(terminal);
	const terminalRenderer = new CSS3DRenderer();
	terminalRenderer.domElement.className = 'os-layer';
	// Zoomed in towards an edge, the view reaches past the frame this layer
	// is laid out in, so it mustn't clip; the stage does.
	terminalRenderer.domElement.style.overflow = 'visible';
	stage.insertBefore(terminalRenderer.domElement, canvas);
	// Out of reach of the keyboard and pointer until you're at the laptop.
	os.inert = true;

	// ------------------------------------------------------------ the control panel

	// A colour as it is in the still, at a spot from cabin.json.
	function stillColour(at) {
		sample.drawImage(still, (at.left / 100) * STILL.width, (at.top / 100) * STILL.height, 1, 1, 0, 0, 1, 1);
		const [red, green, blue] = sample.getImageData(0, 0, 1, 1).data;
		return new Color().setRGB(red / 255, green / 255, blue / 255, SRGBColorSpace);
	}
	// The four buttons, dim as in the still and bright when lit; the status
	// lamp, amber until the panel's in sync, then green.
	const PANEL_LIT = { red: '#ff5a45', green: '#5dff7a', blue: '#6a96ff', yellow: '#ffd84a' };
	const panelButtons = {};
	for (const [colour, lit] of Object.entries(PANEL_LIT)) {
		const button = scene.getObjectByName(`simon-${colour}`);
		const dim = stillColour(cabinData.hotspots[`simon-${colour}`]);
		button.material = new MeshBasicMaterial({ color: dim.clone(), toneMapped: false });
		button.userData = { dim, lit: new Color(lit) };
		panelButtons[colour] = button;
	}
	const panelLamp = scene.getObjectByName('simon-lamp');
	const panelGreen = new Color('#5dff8a');
	panelLamp.material = new MeshBasicMaterial({ color: progress.has('panel') ? panelGreen.clone() : stillColour(cabinData.hotspots['simon-lamp']), toneMapped: false });

	// ------------------------------------------------------------ the passing ship

	// Once the song's been played (ui.js), a ship comes past: it glides in
	// from the right, across in front of Saturn, and holds station to the left
	// of it. Its hull number is too small to read without zooming in from the
	// window. Once its registration's been checked (laptop.js) it's in
	// trouble, and sinks slowly toward Saturn. Once it's saved, it climbs away,
	// starting when you're back from the laptop to watch. Its picture loads
	// only when it comes.
	const ship = scene.getObjectByName('ship-card');
	const shipFrom = scene.getObjectByName('ship-start').position.clone();
	const shipTo = ship.position.clone();
	const shipSunk = shipTo.clone().lerp(saturn.position, SHIP.sink);
	const shipGone = shipTo.clone().add(new Vector3(...SHIP.away));
	ship.visible = false;
	const easeOut = (t) => 1 - (1 - t) ** 3;
	const easeIn = (t) => t ** 3;
	let leg = null;
	let climbWaiting = false;

	// Its engines: a plume behind each nozzle, and puffs from its attitude
	// thrusters. Where they are on the ship's card comes from
	// scene/cabin.py: from -0.5 to 0.5 across and down ship.webp. Plumes
	// reach seven nozzle radii at full burn, and flicker.
	const cardSize = ship.scale.clone();
	const NOZZLES = cabinData.ship.nozzles.map(({ x, z, radius }) => ({ x, z, height: radius * 1.8, length: radius * 7 }));
	const THRUSTERS = cabinData.ship.thrusters;
	const plumeTexture = (() => {
		const picture = document.createElement('canvas');
		picture.width = 256;
		picture.height = 64;
		const c = picture.getContext('2d');
		// A cone of light: white-hot at the nozzle (the left edge), cooling
		// to orange and fading behind.
		c.translate(0, 32);
		c.scale(1, 0.25);
		const glow = c.createRadialGradient(0, 0, 0, 0, 0, 256);
		glow.addColorStop(0, 'rgb(240 248 255 / 1)');
		glow.addColorStop(0.12, 'rgb(160 205 255 / 0.9)');
		glow.addColorStop(0.45, 'rgb(255 170 100 / 0.4)');
		glow.addColorStop(1, 'rgb(255 120 60 / 0)');
		c.fillStyle = glow;
		c.fillRect(0, -128, 256, 256);
		const texture = new CanvasTexture(picture);
		texture.colorSpace = SRGBColorSpace;
		return texture;
	})();
	// Flat on the card, facing the camera as it does, starting at its left edge.
	const flat = new PlaneGeometry(1, 1).rotateX(-Math.PI / 2);
	const plumeShape = flat.clone().translate(0.5, 0, 0);
	const glowing = (map) => new MeshBasicMaterial({ map, transparent: true, depthWrite: false, blending: AdditiveBlending, toneMapped: false, opacity: 0 });
	const plumes = NOZZLES.map((nozzle) => {
		const plume = new Mesh(plumeShape, glowing(plumeTexture));
		plume.position.set(nozzle.x, 0.002, nozzle.z);
		plume.renderOrder = 1;
		plume.userData = nozzle;
		ship.add(plume);
		return plume;
	});
	const thrustTexture = spot([
		[0, 'rgb(240 245 255 / 0.9)'],
		[0.5, 'rgb(220 230 245 / 0.35)'],
		[1, 'rgb(220 230 245 / 0)'],
	]);
	const thrusts = THRUSTERS.map((thruster) => {
		const puff = new Mesh(flat, glowing(thrustTexture));
		puff.position.set(thruster.x, 0.003, thruster.z);
		puff.renderOrder = 1;
		puff.userData = { since: -Infinity };
		ship.add(puff);
		return puff;
	});
	// Its navigation lights: red and green glowing steadily, breathing a
	// little; the white strobe flashing twice every 1.6 seconds.
	const LIGHTS = { red: 'rgb(255 70 50', green: 'rgb(80 255 120', white: 'rgb(255 255 255' };
	const lights = cabinData.ship.lights.map(({ x, z, colour }) => {
		const glow = new Mesh(flat, glowing(spot([[0, `${LIGHTS[colour]} / 1)`], [0.3, `${LIGHTS[colour]} / 0.45)`], [1, `${LIGHTS[colour]} / 0)`]])));
		glow.position.set(x, 0.004, z);
		glow.scale.set(0.35 / cardSize.x, 1, 0.35 / cardSize.z);
		glow.renderOrder = 2;
		glow.userData.colour = colour;
		ship.add(glow);
		return glow;
	});
	function blinkLights(now) {
		for (const light of lights) {
			const strobe = now % 1.6;
			light.material.opacity =
				light.userData.colour === 'white' ? (reduceMotion.matches || strobe < 0.07 || (strobe > 0.2 && strobe < 0.27) ? 1 : 0) : reduceMotion.matches ? 0.85 : 0.75 + 0.25 * Math.sin(now * 2);
		}
	}

	// The jet trails, in space rather than on the ship, so they're left behind
	// as it moves: a ring of points reused oldest first.
	const trailPositions = new Float32Array(TRAIL.count * 3);
	const trailColours = new Float32Array(TRAIL.count * 3);
	const trailDrift = Array.from({ length: TRAIL.count }, () => new Vector3());
	const trailAge = new Float32Array(TRAIL.count).fill(Infinity);
	const trailGeometry = new BufferGeometry();
	// Its own arrays, not copies, so writing to them moves the points.
	trailGeometry.setAttribute('position', new BufferAttribute(trailPositions, 3));
	trailGeometry.setAttribute('color', new BufferAttribute(trailColours, 3));
	const trail = new Points(
		trailGeometry,
		new PointsMaterial({
			size: TRAIL.size,
			map: spot([
				[0, 'rgb(255 255 255 / 1)'],
				[1, 'rgb(255 255 255 / 0)'],
			]),
			vertexColors: true,
			transparent: true,
			blending: AdditiveBlending,
			depthWrite: false,
			toneMapped: false,
		}),
	);
	trail.frustumCulled = false;
	scene.add(trail);
	let trailNext = 0;
	let trailOwed = 0;
	const nozzleAt = new Vector3();
	const behind = new Vector3();
	function streamTrail(seconds) {
		const rate = ship.visible && !reduceMotion.matches ? TRAIL.rate[engines] ?? 0 : 0;
		trailOwed += rate * seconds;
		behind.set(1, 0, 0).applyQuaternion(ship.quaternion).normalize();
		for (; trailOwed >= 1; trailOwed -= 1) {
			const nozzle = NOZZLES[Math.floor(Math.random() * NOZZLES.length)];
			ship.localToWorld(nozzleAt.set(nozzle.x, 0, nozzle.z)).toArray(trailPositions, trailNext * 3);
			trailDrift[trailNext].copy(behind).multiplyScalar(TRAIL.drift * (0.6 + Math.random() * 0.8)).add(new Vector3(between(-0.15, 0.15), between(-0.15, 0.15), between(-0.15, 0.15)));
			trailAge[trailNext] = 0;
			trailNext = (trailNext + 1) % TRAIL.count;
		}
		for (let i = 0; i < TRAIL.count; i++) {
			if (trailAge[i] > TRAIL.seconds) {
				trailColours.fill(0, i * 3, i * 3 + 3);
				continue;
			}
			trailAge[i] += seconds;
			nozzleAt.fromArray(trailPositions, i * 3).addScaledVector(trailDrift[i], seconds).toArray(trailPositions, i * 3);
			const left = Math.max(0, 1 - trailAge[i] / TRAIL.seconds) ** 2;
			trailColours[i * 3] = left;
			trailColours[i * 3 + 1] = left * (0.55 + 0.4 * left);
			trailColours[i * 3 + 2] = left * (0.3 + 0.7 * left);
		}
		trailGeometry.attributes.position.needsUpdate = true;
		trailGeometry.attributes.color.needsUpdate = true;
	}

	let engines = 'parked';
	let burn = 0;
	let nextPuff = 0;
	let lastBurn = 0;
	function burnEngines(now) {
		const seconds = Math.min(0.1, now - lastBurn);
		lastBurn = now;
		streamTrail(seconds);
		if (!ship.visible) return;
		blinkLights(now);
		const target = SHIP.burn[engines];
		burn = reduceMotion.matches ? target : burn + (target - burn) * (1 - Math.exp(-seconds * 1.5));
		for (const plume of plumes) {
			const { length, height } = plume.userData;
			const flicker = reduceMotion.matches ? 1 : 1 + 0.1 * Math.sin(now * 37 + length * 9) + 0.06 * Math.sin(now * 61);
			plume.scale.set((length * Math.max(burn, 0.05) * flicker) / cardSize.x, 1, height / cardSize.z);
			plume.material.opacity = Math.min(1, burn * 1.6) * (reduceMotion.matches ? 1 : 0.9 + 0.1 * flicker);
		}
		if (engines === 'sinking' && !reduceMotion.matches && now > nextPuff) {
			thrusts[Math.floor(Math.random() * thrusts.length)].userData.since = now;
			nextPuff = now + SHIP.puffs[0] + Math.random() * (SHIP.puffs[1] - SHIP.puffs[0]);
		}
		for (const puff of thrusts) {
			const age = (now - puff.userData.since) / 0.7;
			const radius = 0.1 + 0.5 * Math.min(1, age);
			puff.scale.set(radius / cardSize.x, 1, radius / cardSize.z);
			puff.material.opacity = age < 1 ? 0.8 * (1 - age) : 0;
		}
	}
	async function showShip(at) {
		const picture = await new TextureLoader().loadAsync('/scene/ship.webp');
		picture.colorSpace = SRGBColorSpace;
		// The card's texture coordinates come from glTF, which doesn't flip images.
		picture.flipY = false;
		ship.material = new MeshBasicMaterial({ map: picture, transparent: true, depthWrite: false, toneMapped: false });
		ship.position.copy(at);
		ship.visible = true;
		requestRender();
	}
	function sail(to, seconds, ease, then) {
		if (reduceMotion.matches) {
			ship.position.copy(to);
			then?.();
			requestRender();
			return;
		}
		leg = { from: ship.position.clone(), to, start: performance.now() / 1000, seconds, ease, then };
	}
	function glideShip(now) {
		burnEngines(now);
		if (climbWaiting && !usingLaptop && !terminalAway) {
			climbWaiting = false;
			engines = 'climbing';
			sail(shipGone, SHIP.climb, easeIn, () => (ship.visible = false));
		}
		if (!leg) return;
		const through = Math.min(1, (now - leg.start) / leg.seconds);
		ship.position.lerpVectors(leg.from, leg.to, leg.ease(through));
		if (through < 1) return;
		const { then } = leg;
		leg = null;
		then?.();
	}
	if (progress.has('goat') && !progress.has('saved')) {
		engines = 'sinking';
		showShip(shipSunk);
	} else if (progress.has('song') && !progress.has('saved')) showShip(shipTo);
	progress.listen(async (step) => {
		if (step === 'song') {
			await showShip(shipFrom);
			engines = 'arriving';
			sail(shipTo, SHIP.arrive, easeOut, () => engines === 'arriving' && (engines = 'parked'));
		}
		if (step === 'goat') {
			engines = 'sinking';
			sail(shipSunk, SHIP.sinking, easeOut);
		}
		if (step === 'saved') climbWaiting = true;
	});

	// ------------------------------------------------------------ the phone's screen

	// What's playing, as a phone's lock screen shows it: the clock and date,
	// then the track with a little cover, a live waveform, LIVE (it's a radio,
	// it doesn't end) and how long it's been on, and the play controls. Before
	// the radio's ever been played, just the clock. Redrawn PHONE.fps times a
	// second while it plays, and whenever anything changes.
	const PHONE = { width: 400, height: 824, fps: 15, ink: '#d6eef2', dim: 'rgb(214 238 242 / 0.55)', accent: '#7fe3f0' };
	const phoneCanvas = document.createElement('canvas');
	phoneCanvas.width = PHONE.width;
	phoneCanvas.height = PHONE.height;
	const phoneTexture = new CanvasTexture(phoneCanvas);
	phoneTexture.flipY = false;
	phoneTexture.colorSpace = SRGBColorSpace;
	const phoneScreen = scene.getObjectByName('phone-screen');
	phoneScreen.material = new MeshBasicMaterial({ map: phoneTexture, toneMapped: false });
	const phoneAt = cabinData.hotspots['phone-screen'];
	sample.drawImage(still, (phoneAt.left / 100) * STILL.width, (phoneAt.top / 100) * STILL.height, 1, 1, 0, 0, 1, 1);
	const [pr, pg, pb] = sample.getImageData(0, 0, 1, 1).data;
	const phoneColour = `rgb(${pr} ${pg} ${pb})`;

	function roundRect(c, x, y, w, h, radius) {
		c.beginPath();
		c.roundRect(x, y, w, h, radius);
	}

	function drawPhone(now = ui.nowPlaying()) {
		const c = phoneCanvas.getContext('2d');
		const { width: w, ink, dim, accent } = PHONE;
		const date = new Date();
		const time = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
		c.fillStyle = phoneColour;
		c.fillRect(0, 0, w, PHONE.height);
		c.textBaseline = 'middle';
		c.font = '600 22px system-ui, sans-serif';
		c.fillStyle = ink;
		c.textAlign = 'left';
		c.fillText(time, 34, 42);
		// Signal bars, and a battery, charging.
		for (let i = 0; i < 4; i++) c.fillRect(w - 128 + i * 9, 50 - 5 - i * 4, 6, 6 + i * 4);
		c.strokeStyle = ink;
		c.lineWidth = 2;
		roundRect(c, w - 80, 33, 36, 18, 4);
		c.stroke();
		c.fillRect(w - 43, 38, 3, 8);
		c.fillRect(w - 77, 36, 21, 12);
		c.beginPath();
		c.moveTo(w - 60, 34);
		c.lineTo(w - 67, 43);
		c.lineTo(w - 61, 43);
		c.lineTo(w - 64, 51);
		c.lineTo(w - 54, 40);
		c.lineTo(w - 60, 40);
		c.closePath();
		c.fillStyle = accent;
		c.fill();
		c.textAlign = 'center';
		c.fillStyle = ink;
		const day = date.toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'long' });
		if (!now.started) {
			c.font = '200 112px system-ui, sans-serif';
			c.fillText(time, w / 2, 300);
			c.font = '500 24px system-ui, sans-serif';
			c.fillStyle = dim;
			c.fillText(day, w / 2, 380);
			phoneTexture.needsUpdate = true;
			return;
		}
		c.font = '200 72px system-ui, sans-serif';
		c.fillText(time, w / 2, 170);
		c.font = '500 20px system-ui, sans-serif';
		c.fillStyle = dim;
		c.fillText(day, w / 2, 222);
		// The card.
		c.fillStyle = 'rgb(255 255 255 / 0.07)';
		roundRect(c, 20, 290, w - 40, 470, 28);
		c.fill();
		// A cover: a ringed planet on dark blue.
		const cover = c.createLinearGradient(44, 316, 140, 412);
		cover.addColorStop(0, '#1d3a5c');
		cover.addColorStop(1, '#0b1626');
		c.fillStyle = cover;
		roundRect(c, 44, 316, 96, 96, 14);
		c.fill();
		c.fillStyle = '#e8d8b0';
		c.beginPath();
		c.arc(92, 364, 18, 0, Math.PI * 2);
		c.fill();
		c.strokeStyle = '#e8d8b0';
		c.lineWidth = 3;
		c.beginPath();
		c.ellipse(92, 364, 36, 10, -0.35, 0, Math.PI * 2);
		c.stroke();
		c.textAlign = 'left';
		c.fillStyle = ink;
		c.font = '700 30px system-ui, sans-serif';
		c.fillText(now.track, 160, 348, w - 220);
		c.font = '500 20px system-ui, sans-serif';
		c.fillStyle = dim;
		c.fillText(now.station, 160, 384, w - 220);
		if (now.headphones) {
			// Headphones: a band and two cups.
			c.strokeStyle = accent;
			c.lineWidth = 3;
			c.beginPath();
			c.arc(w - 64, 372, 13, Math.PI, 0);
			c.stroke();
			c.fillStyle = accent;
			c.fillRect(w - 80, 370, 7, 14);
			c.fillRect(w - 55, 370, 7, 14);
		}
		// The waveform: the radio's sound right now, or a flat line when paused.
		const top = 460;
		const wave = now.wave;
		c.strokeStyle = now.playing ? accent : dim;
		c.lineWidth = 3;
		c.lineJoin = 'round';
		c.beginPath();
		for (let i = 0; i < wave.length; i++) {
			const x = 44 + (i / (wave.length - 1)) * (w - 88);
			const y = top + 60 + ((wave[i] - 128) / 128) * 240;
			if (i) c.lineTo(x, y);
			else c.moveTo(x, y);
		}
		c.stroke();
		// LIVE, and how long it's been on.
		c.strokeStyle = now.playing ? accent : dim;
		c.lineWidth = 2;
		roundRect(c, 44, 612, 64, 28, 14);
		c.stroke();
		c.fillStyle = now.playing ? accent : dim;
		c.font = '700 15px system-ui, sans-serif';
		c.textAlign = 'center';
		c.fillText('LIVE', 76, 627);
		if (now.playing) {
			const seconds = Math.floor((performance.now() - now.since) / 1000);
			c.textAlign = 'right';
			c.fillStyle = dim;
			c.font = '500 18px system-ui, sans-serif';
			c.fillText(`${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`, w - 44, 627);
		}
		// Back, play or pause, forward.
		c.fillStyle = ink;
		const mid = 700;
		for (const [x, flip] of [[w / 2 - 100, -1], [w / 2 + 100, 1]]) {
			for (const shift of [-11, 11]) {
				c.beginPath();
				c.moveTo(x + shift - 11 * flip, mid - 13);
				c.lineTo(x + shift + 11 * flip, mid);
				c.lineTo(x + shift - 11 * flip, mid + 13);
				c.fill();
			}
		}
		c.beginPath();
		c.arc(w / 2, mid, 36, 0, Math.PI * 2);
		c.fill();
		c.fillStyle = phoneColour;
		if (now.playing) {
			c.fillRect(w / 2 - 12, mid - 14, 8, 28);
			c.fillRect(w / 2 + 4, mid - 14, 8, 28);
		} else {
			c.beginPath();
			c.moveTo(w / 2 - 9, mid - 15);
			c.lineTo(w / 2 + 15, mid);
			c.lineTo(w / 2 - 9, mid + 15);
			c.fill();
		}
		phoneTexture.needsUpdate = true;
	}

	// ------------------------------------------------------------ the light in the window

	// A soft round spot, for glows, steam and dust: [offset, colour] stops from the middle out.
	function spot(stops) {
		const picture = document.createElement('canvas');
		picture.width = picture.height = 64;
		const c = picture.getContext('2d');
		const gradient = c.createRadialGradient(32, 32, 0, 32, 32, 32);
		for (const [at, colour] of stops) gradient.addColorStop(at, colour);
		c.fillStyle = gradient;
		c.fillRect(0, 0, 64, 64);
		const spotTexture = new CanvasTexture(picture);
		spotTexture.colorSpace = SRGBColorSpace;
		return spotTexture;
	}

	const beacon = new Sprite(
		new SpriteMaterial({
			map: spot([
				[0, 'rgb(255 240 210 / 1)'],
				[0.25, 'rgb(255 205 140 / 0.8)'],
				[1, 'rgb(255 180 100 / 0)'],
			]),
			blending: AdditiveBlending,
			depthWrite: false,
			toneMapped: false,
		}),
	);
	beacon.position.copy(scene.getObjectByName('beacon').position);
	beacon.scale.setScalar(7);
	scene.add(beacon);

	// The same Morse pattern as the HTML light: steps of [on, units].
	const steps = JSON.parse(document.querySelector('.beacon[data-signal]').dataset.signal);
	let blinkTimer;
	function blink(index = 0) {
		clearTimeout(blinkTimer);
		if (reduceMotion.matches || document.hidden) {
			beacon.material.opacity = 0.6;
			requestRender();
			return;
		}
		const [on, units] = steps[index];
		beacon.material.opacity = on ? 1 : 0.12;
		requestRender();
		blinkTimer = setTimeout(() => blink((index + 1) % steps.length), units * 300);
	}
	document.addEventListener('visibilitychange', () => blink());

	// ------------------------------------------------------------ the room moving

	const between = (low, high) => low + Math.random() * (high - low);

	// The bare bulb, in the colour it has in the still, with a soft glow.
	const bulb = scene.getObjectByName('bulb');
	sample.drawImage(still, (cabinData.hotspots.bulb.left / 100) * STILL.width, (cabinData.hotspots.bulb.top / 100) * STILL.height, 1, 1, 0, 0, 1, 1);
	const [br, bg, bb] = sample.getImageData(0, 0, 1, 1).data;
	const bulbColour = new Color().setRGB(br / 255, bg / 255, bb / 255, SRGBColorSpace);
	bulb.material = new MeshBasicMaterial({ color: bulbColour.clone(), toneMapped: false });
	const halo = new Sprite(
		new SpriteMaterial({
			map: spot([
				[0, 'rgb(255 214 160 / 0.9)'],
				[0.3, 'rgb(255 170 90 / 0.25)'],
				[1, 'rgb(255 150 70 / 0)'],
			]),
			opacity: AMBIENT.halo,
			blending: AdditiveBlending,
			depthWrite: false,
			toneMapped: false,
		}),
	);
	halo.position.copy(bulb.position);
	halo.scale.setScalar(0.9);
	scene.add(halo);

	// The flicker: the bulb dims, and so does the room round it (the .dim
	// layer, centred on wherever the bulb is on screen).
	const dim = stage.querySelector('.dim');
	let dips = [];
	let nextFlicker = null;
	function flicker(now) {
		dips = [];
		let at = now;
		for (let count = Math.floor(between(1, 4)); count > 0; count--) {
			dips.push({ at, seconds: between(0.06, 0.14), depth: between(0.35, 0.7) });
			at += between(AMBIENT.flicker.gap, AMBIENT.flicker.gap + 0.3);
		}
		nextFlicker = at + between(...AMBIENT.flicker.every);
		const onScreen = bulb.position.clone().project(camera);
		dim.style.setProperty('--x', `${((onScreen.x + 1) / 2) * 100}%`);
		dim.style.setProperty('--y', `${((1 - onScreen.y) / 2) * 100}%`);
	}
	// How bright the bulb is now, from 1 (steady) down to 0.3 at the deepest dip.
	function bulbLevel(now) {
		let level = 1;
		for (const dip of dips) {
			const through = (now - dip.at) / dip.seconds;
			if (through > 0 && through < 1) level = Math.min(level, 1 - dip.depth * Math.sin(Math.PI * through));
		}
		return level;
	}

	// Steam off the coffee: soft puffs that rise, spread and fade in turn.
	const steamFrom = scene.getObjectByName('steam').position;
	const puffTexture = spot([
		[0, 'rgb(235 225 215 / 0.9)'],
		[0.5, 'rgb(235 225 215 / 0.35)'],
		[1, 'rgb(235 225 215 / 0)'],
	]);
	const puffs = Array.from({ length: AMBIENT.steam.puffs }, (_, i) => {
		const puff = new Sprite(new SpriteMaterial({ map: puffTexture, depthWrite: false, toneMapped: false, rotation: between(0, 6.3) }));
		puff.userData = { offset: (i / AMBIENT.steam.puffs) * AMBIENT.steam.seconds, round: -1, drift: 0 };
		scene.add(puff);
		return puff;
	});
	function rise(now) {
		const { seconds, rise: height } = AMBIENT.steam;
		for (const puff of puffs) {
			const time = now + puff.userData.offset;
			const round = Math.floor(time / seconds);
			if (round !== puff.userData.round) {
				puff.userData.round = round;
				puff.userData.drift = between(-1, 1);
			}
			const age = (time % seconds) / seconds;
			const drift = puff.userData.drift;
			puff.position.set(
				steamFrom.x + (drift * 0.06 + Math.sin(age * 5 + drift * 3) * 0.03) * age,
				steamFrom.y + age * height,
				steamFrom.z + Math.cos(age * 4 + drift) * 0.02 * age,
			);
			puff.scale.setScalar(0.07 + age * 0.22);
			puff.material.opacity = 0.16 * Math.sin(Math.PI * age) ** 1.5;
			puff.material.rotation += 0.004 * drift;
		}
	}

	// Dust in the desk lamp's beam: motes drift, and fade out towards the
	// beam's edge; one that drifts out of it fades in again somewhere inside.
	const dustFrom = scene.getObjectByName('dust-from').position;
	const beam = scene.getObjectByName('dust-to').position.clone().sub(dustFrom);
	const beamLength = beam.length();
	beam.normalize();
	const across = new Vector3(0, 1, 0).cross(beam).normalize();
	const across2 = beam.clone().cross(across);
	// The lamp's light spreads 35 degrees either side of the beam.
	const widening = Math.tan((35 * Math.PI) / 180) * AMBIENT.dust.spread;
	const { motes } = AMBIENT.dust;
	const motePositions = new Float32Array(motes * 3);
	const moteColours = new Float32Array(motes * 3);
	const moteDrift = Array.from({ length: motes }, () => new Vector3());
	const moteAge = new Float32Array(motes);
	const mote = new Vector3();
	const offset = new Vector3();
	function placeMote(i) {
		const along = between(0.2, 0.85) * beamLength;
		const angle = between(0, Math.PI * 2);
		const radius = Math.sqrt(Math.random()) * along * widening;
		mote.copy(dustFrom)
			.addScaledVector(beam, along)
			.addScaledVector(across, Math.cos(angle) * radius)
			.addScaledVector(across2, Math.sin(angle) * radius);
		mote.toArray(motePositions, i * 3);
		moteDrift[i].set(between(-1, 1), between(-0.6, 1), between(-1, 1)).multiplyScalar(0.012);
		moteAge[i] = 0;
	}
	for (let i = 0; i < motes; i++) placeMote(i);
	const dustGeometry = new BufferGeometry();
	dustGeometry.setAttribute('position', new BufferAttribute(motePositions, 3));
	dustGeometry.setAttribute('color', new BufferAttribute(moteColours, 3));
	const dust = new Points(
		dustGeometry,
		new PointsMaterial({
			size: 0.012,
			map: spot([
				[0, 'rgb(255 255 255 / 1)'],
				[1, 'rgb(255 255 255 / 0)'],
			]),
			vertexColors: true,
			transparent: true,
			blending: AdditiveBlending,
			depthWrite: false,
			toneMapped: false,
		}),
	);
	scene.add(dust);
	function stir(now, seconds) {
		for (let i = 0; i < motes; i++) {
			mote.fromArray(motePositions, i * 3).addScaledVector(moteDrift[i], seconds);
			// A slow draught, the same for every mote.
			mote.x += Math.sin(now * 0.3) * 0.004 * seconds;
			offset.copy(mote).sub(dustFrom);
			const along = offset.dot(beam);
			const out = offset.addScaledVector(beam, -along).length() / (along * widening);
			if (along < 0.15 * beamLength || along > 0.9 * beamLength || out > 1) {
				placeMote(i);
				continue;
			}
			mote.toArray(motePositions, i * 3);
			moteAge[i] += seconds;
			const glint = (1 - out) ** 2 * (0.6 + 0.4 * Math.sin(now * 2 + i)) * Math.min(1, moteAge[i]);
			moteColours[i * 3] = glint;
			moteColours[i * 3 + 1] = glint * 0.82;
			moteColours[i * 3 + 2] = glint * 0.6;
		}
		dustGeometry.attributes.position.needsUpdate = true;
		dustGeometry.attributes.color.needsUpdate = true;
	}

	// The haze breathes: a little thicker and thinner, and drifting sideways.
	function breathe(now) {
		haze.forEach((sheet, i) => {
			sheet.material.opacity = AMBIENT.haze * (1 + 0.15 * Math.sin(now * 0.21 + i * 2.1));
			sheet.position.x = sheet.userData.x + 0.12 * Math.sin(now * 0.05 + i * 1.7);
		});
	}

	// ------------------------------------------------------------ gravity

	// Off, the loose things lift off the desk one after another, hover a
	// little above their places, and drift and turn, slowly. On, they drop
	// back where they were, with a small bounce. A semblance of orbit, not a
	// simulation: nothing floats away. With reduced motion, things go straight
	// to where they'd end up, and stay there.
	const loose = gltf.scene.children.filter((object) => object.name.startsWith('float-'));
	const lever = scene.getObjectByName('gravity-lever');
	for (const thing of [...loose, lever]) thing.material = cabin.material;
	// Each prop's picking box goes with its main piece: the pens' with the cup,
	// the discs' with the loose disc.
	for (const hit of hits) scene.getObjectByName(`float-${hit.userData.prop}-0`)?.attach(hit);
	labels.gravity = 'Gravity: on';

	// The lamp beside the lever: the green it is in the still, or amber.
	const lamp = scene.getObjectByName('gravity-lamp');
	const lampAt = cabinData.hotspots['gravity-lamp'];
	sample.drawImage(still, (lampAt.left / 100) * STILL.width, (lampAt.top / 100) * STILL.height, 1, 1, 0, 0, 1, 1);
	const [lr, lg, lb] = sample.getImageData(0, 0, 1, 1).data;
	const lampOn = new Color().setRGB(lr / 255, lg / 255, lb / 255, SRGBColorSpace);
	const lampOff = new Color().setRGB(1, 0.62, 0.18, SRGBColorSpace);
	lamp.material = new MeshBasicMaterial({ color: lampOn.clone(), toneMapped: false });
	const lampRed = new Color().setRGB(1, 0.12, 0.06, SRGBColorSpace);

	let gravityOn = true;
	const homes = new Map(loose.map((thing) => [thing, pose(thing)]));

	// The lever works only once manual gravity control is enabled on the
	// laptop; until then it clunks and its lamp blinks red, three times.
	function throwLever() {
		if (progress.has('gravity-enabled')) return setGravity(!gravityOn);
		ui.gravityRefused();
		for (let i = 0; i < 6; i++) {
			setTimeout(() => {
				lamp.material.color.copy(i % 2 ? (gravityOn ? lampOn : lampOff) : lampRed);
				requestRender();
			}, i * 220);
		}
	}

	// The plectrum: pinned under the mug while there's gravity; floating free,
	// a click pockets it, and the guitar can be played (ui.js checks for 'pick').
	const plectrum = scene.getObjectByName('float-pick-0');
	labels.plectrum = 'Plectrum';
	function pocket() {
		plectrum.visible = false;
		loose.splice(loose.indexOf(plectrum), 1);
		moves.delete(plectrum);
	}
	function takePlectrum() {
		if (gravityOn) return ui.say("It's pinned under the mug, and the mug won't budge.");
		progress.mark('pick');
		pocket();
		ui.say('You pocket the plectrum.');
		requestRender();
	}
	// What each loose thing is doing, floating or falling, since when, and from where.
	const moves = new Map();
	if (progress.has('pick')) pocket();

	// The crack in the window leaks while the gravity's off, until it's taped.
	// The draught takes DO NOT LOSE: up out of the pile, past the window's lower
	// left and along the glass, faster as it goes, until it sticks over the
	// crack, rattling, its sticker against the glass. A press on it catches it,
	// and it comes back and turns over, sticker out (floatFrom).
	const notLose = scene.getObjectByName('float-discs-1');
	const xAxis = new Vector3(1, 0, 0);
	const tape = ['crack-tape-0', 'crack-tape-1'].map((name) => scene.getObjectByName(name));
	const tapeMaterial = new MeshBasicMaterial({ color: new Color().setRGB(0.36, 0.36, 0.35, SRGBColorSpace) });
	for (const strip of tape) {
		strip.material = tapeMaterial;
		strip.visible = progress.has('taped');
	}
	let leaking = false;
	function leakFrom(thing, at) {
		const home = homes.get(thing);
		const path = new CatmullRomCurve3([
			home.position.clone(),
			home.position.clone().add(new Vector3(0, 0.4, 0.15)),
			new Vector3(...cabinData.leak.via),
			new Vector3(...cabinData.leak.stuck),
		]);
		return { leaking: true, at, path, home: home.quaternion.clone(), tilt: 0 };
	}
	function drift(thing, move, now) {
		const along = Math.min(1, Math.max(0, now - move.at) / LEAK.seconds);
		const pulled = along ** 2;
		move.path.getPoint(pulled, thing.position);
		move.tilt = (Math.PI / 2) * pulled;
		thing.quaternion.copy(leaning.setFromAxisAngle(xAxis, move.tilt)).multiply(move.home);
		if (along < 1) return;
		thing.position.x += LEAK.rattle * Math.sin(now * 61);
		thing.position.y += LEAK.rattle * Math.sin(now * 47);
		if (!move.stuck) {
			move.stuck = true;
			ui.say('DO NOT LOSE is stuck against the crack, rattling. Grab it before it goes.');
		}
	}
	function catchCase(quiet = false) {
		if (!leaking) return;
		leaking = false;
		const float = floatFrom(notLose, performance.now() / 1000);
		float.leanFrom = moves.get(notLose)?.tilt ?? 0;
		float.from.quaternion.copy(homes.get(notLose).quaternion);
		progress.mark('caught');
		if (reduceMotion.matches) {
			notLose.position.copy(float.hover);
			notLose.quaternion.copy(leaning.setFromAxisAngle(float.axis, float.lean)).multiply(float.from.quaternion);
			moves.delete(notLose);
		} else {
			moves.set(notLose, float);
		}
		if (!quiet) ui.say("Caught it: DO NOT LOSE, nearly lost. There's a sticker underneath: 'backup password: flexbox'.");
		requestRender();
	}
	function tapeCrack() {
		catchCase(true);
		for (const strip of tape) strip.visible = true;
		requestRender();
	}

	// With the gravity off, squeezing the pouch lets out a wobbling blob of
	// water. A blob can be grabbed and thrown like anything floating: one that
	// reaches the plant is drunk, and the plant bounces; one that hits anything
	// else hard enough splats.
	const pouch = scene.getObjectByName('float-pouch-0');
	const plant = scene.getObjectByName('float-plant-0');
	const blobs = new Map();
	const blobGeometry = new SphereGeometry(BLOB.radius, 16, 12);
	const blobMaterial = new MeshBasicMaterial({ color: new Color().setRGB(0.7, 0.88, 1, SRGBColorSpace), transparent: true, opacity: 0.75, depthWrite: false });
	const plantBox = new Box3();
	let plantPerk = -Infinity;
	let squeezed = false;
	function squeeze() {
		if (reduceMotion.matches) return ui.say('You squeeze out a blob of water and nudge it over to the plant. It drinks it in.');
		const blob = new Mesh(blobGeometry, blobMaterial);
		blob.position.copy(pouch.position).add(new Vector3(0, 0.1, 0.05));
		scene.add(blob);
		blobs.set(blob, { velocity: new Vector3(between(-0.03, 0.03), 0.06, 0.04), phase: between(0, Math.PI * 2) });
		radii.set(blob, BLOB.radius);
		if (blobs.size > BLOB.most) burst(blobs.keys().next().value);
		if (!squeezed) ui.say('A wobbling blob of water. Throw it at the plant.');
		squeezed = true;
		requestRender();
	}
	function burst(blob) {
		blobs.delete(blob);
		moves.delete(blob);
		radii.delete(blob);
		scene.remove(blob);
		if (held?.thing === blob) held = null;
	}
	function moveBlobs(now, seconds) {
		const perking = (now - plantPerk) / BLOB.perk;
		plant.scale.setScalar(perking < 1 ? 1 + 0.08 * Math.sin(Math.PI * perking) : 1);
		if (!blobs.size) return;
		plantBox.setFromObject(scene.getObjectByName('hit-plant'));
		for (const [blob, state] of blobs) {
			const wobble = now * 7 + state.phase;
			blob.scale.set(1 + 0.12 * Math.sin(wobble), 1 + 0.12 * Math.sin(wobble + 2.1), 1 + 0.12 * Math.sin(wobble + 4.2));
			if (moves.get(blob)?.held) continue;
			state.velocity.multiplyScalar(Math.exp(-THROW.air * seconds));
			blob.position.addScaledVector(state.velocity, seconds);
			if (plantBox.containsPoint(blob.position)) {
				burst(blob);
				plantPerk = now;
				ui.say('The snake plant drinks it in. It looks pleased with itself.');
				continue;
			}
			let hardest = hitRoom(blob.position, state.velocity, BLOB.radius);
			for (const box of fixed) hardest = Math.max(hardest, hitBox(box, blob.position, state.velocity, BLOB.radius));
			if (hardest > BLOB.splat) {
				burst(blob);
				ui.bump(hardest);
				ui.say('Splat.');
			}
		}
	}
	const leverHome = lever.quaternion.clone();
	let leverSwing = { at: 0, from: 0, to: 0, angle: 0 };
	const up = new Vector3(0, 1, 0);
	const hinge = new Vector3(1, 0, 0);
	const turning = new Quaternion();
	const leaning = new Quaternion();

	function pose(thing) {
		return { position: thing.position.clone(), quaternion: thing.quaternion.clone() };
	}

	// How a thing floats: where it hovers, which way it leans, how fast it
	// turns. Pens rise clear of the cup and fan out, and the notebook's pen
	// clear of the notebook; the stacked disc cases and books spread apart in
	// order and stay nearly flat, so they don't pass through each other. The bottom
	// one, DO NOT LOSE, drifts forward out of the stack and turns over, still,
	// so the password stuck underneath (scene/cabin.py) reads from the chair.
	function floatFrom(thing, at, spot) {
		const [, prop, index] = thing.name.match(/^float-(\w+)-(\d+)$/);
		const hover = homes.get(thing).position.clone();
		let lean = between(0, GRAVITY.lean);
		if (prop === 'discs' && index > 0) {
			hover.y += 0.04 + 0.09 * index + between(0, 0.02);
			lean = between(0, 0.06);
		} else if (prop === 'books') {
			hover.y += 0.08 + 0.1 * index + between(0, 0.02);
			lean = between(0, 0.08);
		} else if (spot) {
			hover.copy(spot);
		} else if (index > 0) {
			hover.y += between(0.3, 0.42);
			if (prop === 'pens') {
				const away = hover.clone().sub(homes.get(scene.getObjectByName('float-pens-0')).position).setY(0);
				if (away.lengthSq() < 1e-4) away.set(between(-1, 1), 0, between(-1, 1));
				hover.addScaledVector(away.normalize(), between(0.08, 0.16));
			}
		} else {
			hover.y += between(...GRAVITY.lift);
		}
		thing.geometry.computeBoundingSphere();
		const size = thing.geometry.boundingSphere.radius;
		const heading = between(0, Math.PI * 2);
		const float = {
			at,
			from: pose(thing),
			hover,
			axis: new Vector3(Math.cos(heading), 0, Math.sin(heading)),
			lean,
			turn: between(-1, 1) * GRAVITY.turn * Math.min(1, 0.15 / size),
			wander: Array.from({ length: 6 }, (_, i) => (i < 3 ? between(0.3, 0.6) : between(0, Math.PI * 2))),
		};
		if (prop === 'discs' && index === '1') {
			float.hover.copy(homes.get(thing).position).add(new Vector3(0, 0.45, 0.3));
			// Turned past flat until its underside faces the camera, like a sign held up.
			const toCamera = camera.position.clone().sub(float.hover);
			const rise = Math.atan2(toCamera.y, Math.hypot(toCamera.x, toCamera.z));
			Object.assign(float, { axis: new Vector3(1, 0, 0), lean: -(Math.PI / 2 + rise), turn: 0 });
		}
		return float;
	}

	// Floating: easing up to its hover spot as if just let go, then drifting about it.
	function floatAbout(thing, move, now) {
		const since = now - move.at;
		if (since <= 0) return;
		const risen = 1 - (1 + since / GRAVITY.rise) * Math.exp(-since / GRAVITY.rise);
		const [rx, ry, rz, px, py, pz] = move.wander;
		thing.position.lerpVectors(move.from.position, move.hover, risen);
		thing.position.x += risen * GRAVITY.wander * Math.sin(now * rx + px);
		thing.position.y += risen * GRAVITY.wander * Math.sin(now * ry + py);
		thing.position.z += risen * GRAVITY.wander * Math.sin(now * rz + pz);
		const leanFrom = move.leanFrom ?? 0;
		leaning.setFromAxisAngle(move.axis, leanFrom + (move.lean - leanFrom) * risen);
		turning.setFromAxisAngle(up, move.turn * since * risen);
		thing.quaternion.copy(turning).multiply(leaning).multiply(move.from.quaternion);
	}

	// The arc home from where a thing is now: as long as falling its height
	// takes, or the trip across at GRAVITY.hop, whichever is longer. Things
	// near home just drop; things thrown across the room hop back.
	function fallFrom(thing, now) {
		const home = homes.get(thing).position;
		const from = pose(thing);
		const height = from.position.y - home.y;
		const across = Math.hypot(from.position.x - home.x, from.position.z - home.z);
		const time = Math.max(Math.sqrt((2 * Math.max(0, height)) / GRAVITY.fall), across / GRAVITY.hop);
		const rise = time > 0 ? (0.5 * GRAVITY.fall * time ** 2 - height) / time : 0;
		const impact = GRAVITY.fall * time - rise;
		return { falling: true, at: now, from, time, rise, impact, bounce: (2 * GRAVITY.bounce * impact) / GRAVITY.fall };
	}

	// Falling: along its arc, one small bounce, straightening on the way.
	function fallHome(thing, move, now) {
		const home = homes.get(thing);
		const since = Math.max(0, now - move.at);
		if (since < move.time) {
			const along = since / move.time;
			thing.position.lerpVectors(move.from.position, home.position, along);
			thing.position.y = move.from.position.y + move.rise * since - 0.5 * GRAVITY.fall * since ** 2;
			thing.quaternion.slerpQuaternions(move.from.quaternion, home.quaternion, 1 - (1 - along) ** 2);
		} else if (since < move.time + move.bounce) {
			const rebound = since - move.time;
			thing.position.copy(home.position);
			thing.position.y += GRAVITY.bounce * move.impact * rebound - 0.5 * GRAVITY.fall * rebound ** 2;
			thing.quaternion.copy(home.quaternion);
		} else {
			thing.position.copy(home.position);
			thing.quaternion.copy(home.quaternion);
			moves.delete(thing);
		}
	}

	// What thrown things bounce off: the inside of the room and the desk, from
	// the scene's data, and the picking boxes of the props that stay put.
	gltf.scene.updateMatrixWorld(true);
	const room = new Box3().setFromArray(cabinData.bounds.room.flat());
	const fixed = [
		new Box3().setFromArray(cabinData.bounds.desk.flat()),
		...hits.filter((hit) => hit.parent === gltf.scene).map((hit) => new Box3().setFromObject(hit)),
	];
	// Each thing bounces as a ball: half its thinnest side, or a fifth of its
	// length if that's more, so a pen doesn't go halfway into a wall.
	const radii = new Map(
		loose.map((thing) => {
			thing.geometry.computeBoundingBox();
			const { x, y, z } = thing.geometry.boundingBox.getSize(new Vector3());
			return [thing, Math.max(Math.min(x, y, z) / 2, Math.max(x, y, z) / 5)];
		}),
	);
	const nearest = new Vector3();
	const outward = new Vector3();
	const toward = new Vector3();
	const spinning = new Quaternion();

	// Keeps a ball inside the room, bouncing it off the walls, floor and
	// ceiling. Returns how fast it hit, or 0.
	function hitRoom(position, velocity, radius) {
		let hit = 0;
		for (const axis of ['x', 'y', 'z']) {
			const low = room.min[axis] + radius;
			const high = room.max[axis] - radius;
			const side = position[axis] < low ? -1 : position[axis] > high ? 1 : 0;
			if (!side) continue;
			position[axis] = side < 0 ? low : high;
			if (velocity[axis] * side > 0) {
				hit = Math.max(hit, Math.abs(velocity[axis]));
				velocity[axis] *= -THROW.restitution;
			}
		}
		return hit;
	}

	// Keeps a ball out of a box, bouncing it off. Returns how fast it hit, or 0.
	function hitBox(box, position, velocity, radius) {
		box.clampPoint(position, nearest);
		outward.subVectors(position, nearest);
		let depth = radius - outward.length();
		if (depth <= 0) return 0;
		if (outward.lengthSq() < 1e-12) {
			// The middle is inside the box: out through the nearest face.
			let best = Infinity;
			for (const axis of ['x', 'y', 'z']) {
				for (const side of [-1, 1]) {
					const gap = side < 0 ? position[axis] - box.min[axis] : box.max[axis] - position[axis];
					if (gap < best) {
						best = gap;
						outward.set(0, 0, 0);
						outward[axis] = side;
					}
				}
			}
			depth = best + radius;
		} else {
			outward.normalize();
		}
		position.addScaledVector(outward, depth);
		const into = velocity.dot(outward);
		if (into >= 0) return 0;
		velocity.addScaledVector(outward, -(1 + THROW.restitution) * into);
		return -into;
	}

	// Thrown: on through the cabin air, turning, bouncing off the room and the
	// things fixed in it, until the pull brings it back to its spot and it
	// floats there again.
	function fly(thing, move, now, seconds) {
		const since = now - move.at;
		const pull = THROW.pull * Math.min(1, Math.max(0, (since - THROW.home) / 2));
		const steps = Math.max(1, Math.ceil(seconds * 120));
		const step = seconds / steps;
		let hardest = 0;
		for (let i = 0; i < steps; i++) {
			if (pull > 0) {
				toward.subVectors(move.hover, thing.position).multiplyScalar(pull * step);
				move.velocity.add(toward).multiplyScalar(1 - 2 * Math.sqrt(pull) * step);
			}
			move.velocity.multiplyScalar(Math.exp(-THROW.air * step));
			thing.position.addScaledVector(move.velocity, step);
			toward.copy(move.spin).normalize();
			thing.quaternion.premultiply(spinning.setFromAxisAngle(toward, move.spin.length() * step));
			move.spin.multiplyScalar(Math.exp(-THROW.spinAir * step));
			hardest = Math.max(hardest, hitRoom(thing.position, move.velocity, move.radius));
			for (const box of fixed) hardest = Math.max(hardest, hitBox(box, thing.position, move.velocity, move.radius));
		}
		if (hardest > 0.4) {
			ui.bump(hardest);
			move.spin.add(toward.set(between(-1, 1), between(-1, 1), between(-1, 1)).multiplyScalar(hardest)).clampLength(0, THROW.spin);
		}
		const slow = move.velocity.length() < 0.05;
		if (pull === THROW.pull && slow && (thing.position.distanceTo(move.hover) < 0.03 || since > THROW.home + 8)) {
			moves.set(thing, floatFrom(thing, now, move.hover));
		}
	}

	// The lever snaps over, speeding up as it goes. Returns whether it's still moving.
	function swingLever(now) {
		const { at, from, to } = leverSwing;
		const through = reduceMotion.matches ? 1 : Math.min(1, (now - at) / 0.18);
		leverSwing.angle = from + (to - from) * through ** 2;
		lever.quaternion.copy(leverHome).multiply(turning.setFromAxisAngle(hinge, leverSwing.angle));
		return through < 1;
	}

	function moveLoose(now, seconds) {
		for (const [thing, move] of moves) {
			if (move.falling) fallHome(thing, move, now);
			else if (move.flying) fly(thing, move, now, seconds);
			else if (move.leaking) drift(thing, move, now);
			else if (!move.held) floatAbout(thing, move, now);
		}
		moveBlobs(now, seconds);
		swingLever(now);
	}

	// Things falling or thrown and the lever swinging need every frame;
	// floating is slow enough for AMBIENT.fps.
	const quick = (now) => now - leverSwing.at < 0.2 || blobs.size > 0 || now - plantPerk < BLOB.perk || [...moves.values()].some((move) => move.falling || move.flying);

	function setGravity(on) {
		gravityOn = on;
		labels.gravity = on ? 'Gravity: on' : 'Gravity: off';
		if (labelled === 'gravity') label.textContent = labels.gravity;
		const now = performance.now() / 1000;
		const landings = [];
		// Anything held is let go of.
		held = null;
		canvas.style.cursor = 'grab';
		leaking = !on && !progress.has('taped');
		if (on) for (const blob of [...blobs.keys()]) burst(blob);
		for (const thing of loose) {
			if (on) {
				const move = fallFrom(thing, now);
				moves.set(thing, move);
				if (move.impact > 0.4) landings.push(move.time);
			} else if (thing === notLose && leaking) {
				moves.set(thing, leakFrom(thing, now + between(0, GRAVITY.stagger)));
			} else {
				moves.set(thing, floatFrom(thing, now + between(0, GRAVITY.stagger)));
			}
		}
		leverSwing = { at: now, from: leverSwing.angle, to: on ? 0 : GRAVITY.swing, angle: leverSwing.angle };
		lamp.material.color.copy(on ? lampOn : lampOff);
		if (reduceMotion.matches) {
			// Straight to the end: home, or hovering at full lean, without the drift.
			for (const [thing, move] of moves) {
				if (move.falling) {
					thing.position.copy(homes.get(thing).position);
					thing.quaternion.copy(homes.get(thing).quaternion);
				} else if (move.leaking) {
					move.path.getPoint(1, thing.position);
					thing.quaternion.copy(leaning.setFromAxisAngle(xAxis, Math.PI / 2)).multiply(move.home);
				} else {
					thing.position.copy(move.hover);
					thing.quaternion.copy(leaning.setFromAxisAngle(move.axis, move.lean)).multiply(move.from.quaternion);
				}
			}
			moves.clear();
			swingLever(now);
		}
		ui.gravity(on, landings);
		requestRender();
	}

	// One tick of all of it, AMBIENT.fps times a second. Browsers pause it
	// while the page is hidden; reduced motion stops it, and the room is still.
	let ticking = false;
	let lastTick = 0;
	let lastPhone = 0;
	let darkness = 0;
	function tick(time) {
		if (reduceMotion.matches) {
			ticking = false;
			return;
		}
		requestAnimationFrame(tick);
		if (!quick(time / 1000) && time - lastTick < 1000 / AMBIENT.fps) return;
		const seconds = Math.min(0.1, (time - lastTick) / 1000);
		lastTick = time;
		const now = time / 1000;
		nextFlicker ??= now + between(3, 6);
		if (now > nextFlicker) flicker(now);
		const level = bulbLevel(now);
		bulb.material.color.copy(bulbColour).multiplyScalar(0.3 + 0.7 * level);
		halo.material.opacity = AMBIENT.halo * level;
		const dark = Math.min(1, (1 - level) / 0.7);
		if (dark !== darkness) dim.style.opacity = darkness = dark;
		// The phone's waveform, while the radio plays.
		const playing = ui.nowPlaying();
		if (playing.playing && time - lastPhone >= 1000 / PHONE.fps) {
			drawPhone(playing);
			lastPhone = time;
		}
		rise(now);
		stir(now, seconds);
		breathe(now);
		moveLoose(now, seconds);
		glideShip(now);
		requestRender();
	}
	function startMoving() {
		const calm = reduceMotion.matches;
		for (const puff of puffs) puff.visible = !calm;
		dust.visible = !calm;
		if (calm) {
			bulb.material.color.copy(bulbColour);
			halo.material.opacity = AMBIENT.halo;
			dim.style.opacity = darkness = 0;
			requestRender();
		} else if (!ticking) {
			ticking = true;
			requestAnimationFrame(tick);
		}
	}
	reduceMotion.addEventListener('change', startMoving);

	// ------------------------------------------------------------ drawing

	// See-through (alpha), so the terminal behind shows where the screen is.
	const renderer = new WebGLRenderer({ canvas, antialias: true, alpha: true });
	renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
	// The desk, floor and glass are mostly seen at a slant: anisotropic
	// filtering keeps them sharp there, and steady as the camera moves.
	const anisotropy = renderer.capabilities.getMaxAnisotropy();
	for (const object of [cabin, glass, phoneScreen, ...haze]) object.material.map.anisotropy = anisotropy;
	// The terminal's layer is laid out at the still's full size and moved so
	// its visible part lines up with the canvas, with a camera that sees the
	// whole frame: three's CSS renderer stretches a cropped view instead.
	const terminalCamera = camera.clone();
	terminalCamera.clearViewOffset();
	// Off while the terminal is out in its dialog (see useLaptop): the CSS
	// renderer would take it straight back.
	let terminalAway = false;
	const render = () => {
		renderer.render(scene, camera);
		if (terminalAway) return;
		terminalCamera.position.copy(camera.position);
		terminalCamera.quaternion.copy(camera.quaternion);
		if (terminalCamera.zoom !== camera.zoom) {
			terminalCamera.zoom = camera.zoom;
			terminalCamera.updateProjectionMatrix();
		}
		terminalCamera.updateMatrixWorld();
		terminalRenderer.render(terminalScene, terminalCamera);
	};

	// The still's frame, cropped to the stage, as the camera's view; plus a
	// shift (lens) for zooming in towards a point. The terminal's layer moves
	// by the same crop and shift.
	const frame = {};
	const lens = { x: 0, y: 0 };
	function applyView() {
		camera.setViewOffset(frame.fullWidth, frame.fullHeight, frame.left + lens.x, frame.top + lens.y, frame.width, frame.height);
		camera.updateProjectionMatrix();
		terminalRenderer.domElement.style.left = `${-(frame.left + lens.x)}px`;
		terminalRenderer.domElement.style.top = `${-(frame.top + lens.y)}px`;
		controls.rotateSpeed = 0.5 / camera.zoom;
	}

	function fit() {
		const width = stage.clientWidth;
		const height = stage.clientHeight;
		const scale = Math.max(width / STILL.width, height / STILL.height);
		const fullWidth = STILL.width * scale;
		const fullHeight = STILL.height * scale;
		camera.aspect = STILL.width / STILL.height;
		Object.assign(frame, { fullWidth, fullHeight, left: (fullWidth - width) * STILL.x, top: (fullHeight - height) * STILL.y, width, height });
		applyView();
		renderer.setSize(width, height, false);
		terminalRenderer.setSize(fullWidth, fullHeight);
		Object.assign(terminalRenderer.domElement.style, {
			width: `${fullWidth}px`,
			height: `${fullHeight}px`,
		});
		render();
	}

	// ------------------------------------------------------------ looking around

	const home = camera.position.clone().add(camera.getWorldDirection(new Vector3()).multiplyScalar(6.59));
	const controls = new OrbitControls(camera, canvas);
	controls.target.copy(home);
	controls.enablePan = false;
	// Scrolling zooms the lens instead (see zooming).
	controls.enableZoom = false;
	controls.enableDamping = true;
	controls.dampingFactor = 0.08;
	controls.rotateSpeed = 0.5;
	function setLimits(look) {
		controls.minAzimuthAngle = -look.azimuth;
		controls.maxAzimuthAngle = look.azimuth;
		controls.minPolarAngle = look.minPolar;
		controls.maxPolarAngle = look.maxPolar;
	}
	setLimits(LOOK);
	controls.update();

	// Nothing redraws at rest: frames run only while the camera moves.
	let looping = false;
	let dragging = false;
	function loop() {
		const moved = controls.enabled && controls.update();
		render();
		if (moved || dragging) requestAnimationFrame(loop);
		else looping = false;
	}
	function requestRender() {
		if (!looping) {
			looping = true;
			requestAnimationFrame(loop);
		}
	}
	controls.addEventListener('start', () => {
		dragging = true;
		hideHint();
		requestRender();
	});
	controls.addEventListener('end', () => {
		dragging = false;
		requestRender();
	});
	controls.addEventListener('change', requestRender);

	// ------------------------------------------------------------ pointing and clicking

	const raycaster = new Raycaster();
	const pointer = new Vector2();

	// What's under the pointer: a row on the laptop, a prop, or nothing.
	// Points the raycaster from the camera through the pointer.
	function aim(event) {
		const rect = canvas.getBoundingClientRect();
		pointer.set(((event.clientX - rect.left) / rect.width) * 2 - 1, -((event.clientY - rect.top) / rect.height) * 2 + 1);
		raycaster.setFromCamera(pointer, camera);
	}

	function pick(event) {
		aim(event);
		// The plectrum before the mug it's under, so its tip can be clicked.
		if (plectrum.visible && raycaster.intersectObject(plectrum).length) return { prop: 'plectrum' };
		const hit = raycaster.intersectObjects(hits)[0];
		return hit ? { prop: hit.object.userData.prop } : {};
	}

	// The prop whose name the label is showing, if any.
	let labelled = null;
	function showPicked(picked, event) {
		const name = picked.prop && labels[picked.prop];
		labelled = name ? picked.prop : null;
		canvas.style.cursor = name ? 'pointer' : 'grab';
		label.classList.toggle('shown', Boolean(name));
		if (name) {
			const rect = stage.getBoundingClientRect();
			label.textContent = name;
			label.style.transform = `translate(${event.clientX - rect.left + 14}px, ${event.clientY - rect.top + 14}px)`;
		}
	}

	let press = null;
	canvas.addEventListener('pointerdown', (event) => {
		press = { x: event.clientX, y: event.clientY };
		label.classList.remove('shown');
	});
	canvas.addEventListener('pointermove', (event) => {
		if (event.pointerType !== 'mouse' || event.buttons || saved) return;
		showPicked(pick(event), event);
		// Floating things can be grabbed.
		if (!gravityOn && raycaster.intersectObjects([...loose, ...blobs.keys()], false).length) canvas.style.cursor = 'grab';
	});
	canvas.addEventListener('pointerleave', () => label.classList.remove('shown'));
	canvas.addEventListener('pointerup', (event) => {
		if (!press || Math.hypot(event.clientX - press.x, event.clientY - press.y) > CLICK_SLOP) return;
		press = null;
		// Up close to something, clicks don't pick other props.
		if (saved) return;
		const picked = pick(event);
		if (picked.prop === 'gravity') throwLever();
		else if (picked.prop === 'plectrum') takePlectrum();
		else if (picked.prop) ui.activate(picked.prop);
	});

	// ------------------------------------------------------------ grabbing and throwing

	// With the gravity off, a press on a floating thing takes hold of it (the
	// camera stays put), dragging moves it about, and letting go throws it,
	// as fast as it was moving. A press that hardly moves is still a click.
	// With reduced motion, a thing stays where you let it go.
	const grabPlane = new Plane();
	const grabbed = new Vector3();
	const noVelocity = new Vector3();
	let held = null;

	// Capturing, so it's seen before the camera's controls, which never are.
	canvas.addEventListener(
		'pointerdown',
		(event) => {
			if (gravityOn || saved) return;
			aim(event);
			const hit = raycaster.intersectObjects([...loose, ...blobs.keys()], false)[0];
			if (!hit) return;
			event.stopImmediatePropagation();
			if (hit.object === notLose && leaking) return catchCase();
			press = { x: event.clientX, y: event.clientY };
			label.classList.remove('shown');
			hideHint();
			grabPlane.setFromNormalAndCoplanarPoint(camera.getWorldDirection(grabbed), hit.point);
			held = { thing: hit.object, offset: hit.object.position.clone().sub(hit.point), trail: [], moved: false };
			canvas.setPointerCapture(event.pointerId);
		},
		{ capture: true },
	);
	canvas.addEventListener('pointermove', (event) => {
		if (!held) return;
		const { thing } = held;
		if (!held.moved) {
			if (Math.hypot(event.clientX - press.x, event.clientY - press.y) <= CLICK_SLOP) return;
			held.moved = true;
			held.hover = moves.get(thing)?.hover ?? thing.position.clone();
			moves.set(thing, { held: true });
			canvas.style.cursor = 'grabbing';
		}
		aim(event);
		if (!raycaster.ray.intersectPlane(grabPlane, grabbed)) return;
		thing.position.copy(grabbed).add(held.offset);
		hitRoom(thing.position, noVelocity.set(0, 0, 0), radii.get(thing));
		const now = performance.now() / 1000;
		held.trail.push([now, thing.position.clone()]);
		while (held.trail.length > 2 && now - held.trail[0][0] > 0.1) held.trail.shift();
		requestRender();
	});
	function letGo(event) {
		if (!held) return;
		const { thing, moved, trail, hover } = held;
		held = null;
		canvas.style.cursor = 'grab';
		// Not moved: a click, which the handler above has dealt with.
		if (!moved) return;
		if (reduceMotion.matches) {
			moves.delete(thing);
			requestRender();
			return;
		}
		const now = performance.now() / 1000;
		const velocity = new Vector3();
		const first = trail[0];
		const last = trail.at(-1);
		// Thrown only if it was still moving when let go.
		if (event.type === 'pointerup' && trail.length > 1 && now - last[0] < 0.1 && last[0] > first[0]) {
			velocity.subVectors(last[1], first[1]).divideScalar(last[0] - first[0]).clampLength(0, THROW.fastest);
		}
		// A blob just goes where it's thrown, with no pull back.
		if (blobs.has(thing)) {
			moves.delete(thing);
			blobs.get(thing).velocity.copy(velocity);
			requestRender();
			return;
		}
		const spin = new Vector3(between(-1, 1), between(-1, 1), between(-1, 1)).setLength(Math.min(THROW.spin, 0.4 + velocity.length() * 1.5));
		moves.set(thing, { flying: true, at: now, velocity, spin, hover, radius: radii.get(thing) });
		requestRender();
	}
	canvas.addEventListener('pointerup', letGo);
	canvas.addEventListener('pointercancel', letGo);

	// ------------------------------------------------------------ flying to props

	// Flying also zooms back out to the plain lens on the way.
	function tween(toPosition, toTarget) {
		const fromPosition = camera.position.clone();
		const fromTarget = controls.target.clone();
		const fromZoom = camera.zoom;
		const fromLens = { ...lens };
		const unzoom = (eased) => {
			camera.zoom = fromZoom + (1 - fromZoom) * eased;
			lens.x = fromLens.x * (1 - eased);
			lens.y = fromLens.y * (1 - eased);
			applyView();
		};
		if (reduceMotion.matches) {
			camera.position.copy(toPosition);
			controls.target.copy(toTarget);
			camera.lookAt(toTarget);
			unzoom(1);
			render();
			return Promise.resolve();
		}
		return new Promise((resolve) => {
			const start = performance.now();
			function step(now) {
				const t = Math.min(1, (now - start) / (FLIGHT_SECONDS * 1000));
				const eased = t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;
				camera.position.lerpVectors(fromPosition, toPosition, eased);
				controls.target.lerpVectors(fromTarget, toTarget, eased);
				camera.lookAt(controls.target);
				unzoom(eased);
				render();
				if (t < 1) requestAnimationFrame(step);
				else resolve();
			}
			requestAnimationFrame(step);
		});
	}

	let saved = null;
	let flight = Promise.resolve();
	// Where a prop is now: its picking box may be floating along with it.
	const centre = (prop) => scene.getObjectByName(`hit-${prop}`).getWorldPosition(new Vector3());

	const api = {
		flyTo(prop) {
			const view = VIEWS[prop];
			if (!view || saved) return Promise.resolve(false);
			const target = view.screen ? screenCentre.clone() : centre(prop);
			// Square on to the laptop's screen, straight on for the window;
			// otherwise from wherever the camera is now.
			const direction = view.screen ? screenNormal.clone() : view.straight ? new Vector3(0, 0, 1) : camera.position.clone().sub(target).normalize();
			const card = view.fill && !view.screen && new Box3().setFromObject(scene.getObjectByName(`hit-${prop}`));
			const distance = view.screen
				? fitDistance(screenCentre, screenNormal, corners, view.fill)
				: card
					? fitDistance(target, direction, [card.min, card.max], view.fill)
					: view.distance;
			saved = { position: camera.position.clone(), target: controls.target.clone() };
			controls.enabled = false;
			label.classList.remove('shown');
			hideHint();
			stopZooming();
			canvas.style.cursor = view.look ? 'grab' : '';
			flight = flight
				.then(() => tween(target.clone().add(direction.multiplyScalar(distance)), target))
				.then(() => {
					if (view.zoom) startZooming(view.zoom);
					if (!view.look) return;
					setLimits(view.look);
					controls.enabled = true;
					controls.update();
					hint.textContent = matchMedia('(hover: none)').matches ? 'Pinch to zoom.' : 'Point and scroll to zoom.';
					hint.classList.add('shown');
					clearTimeout(hintTimer);
					hintTimer = setTimeout(hideHint, 4000);
				});
			return flight.then(() => true);
		},
		flyHome() {
			if (!saved) return Promise.resolve();
			stopZooming();
			const back = saved;
			saved = null;
			controls.enabled = false;
			flight = flight
				.then(() => tween(back.position, back.target))
				.then(() => {
					setLimits(LOOK);
					controls.enabled = true;
					controls.update();
					startZooming(LOOK.zoom);
				});
			return flight;
		},
		useLaptop,
		readCard,
		tapeCrack,
		squeeze,
		leaking: () => leaking,
		toggleGravity() {
			throwLever();
		},
		// The control panel's game (ui.js) lights its 3D buttons as it goes.
		panelLight(colour, on) {
			const button = panelButtons[colour];
			button.material.color.copy(on ? button.userData.lit : button.userData.dim);
			requestRender();
		},
		panelSynced() {
			panelLamp.material.color.copy(panelGreen);
			requestRender();
		},
		phoneChanged() {
			drawPhone();
			requestRender();
		},
	};

	// ------------------------------------------------------------ zooming

	// Scrolling, pinching or the + and - buttons zoom like a lens (the
	// camera's zoom), as far as the view allows (LOOK and VIEWS): far enough
	// to read the Morse card from the chair, or a hull number out of the
	// window. Scrolling and pinching zoom in towards the pointer or between
	// the fingers, so you can point at what you want a closer look at; the
	// buttons zoom on the middle. Looking around slows as you zoom in.
	const zoomButtons = stage.querySelector('.zoom');
	let zoomLimit = 0;
	function setZoom(zoom, at = null) {
		const before = camera.zoom;
		camera.zoom = Math.min(zoomLimit || 1, Math.max(1, zoom));
		const grown = camera.zoom / before;
		if (camera.zoom === 1) {
			lens.x = lens.y = 0;
		} else if (at) {
			// The point under the pointer stays under it: the frame zooms about
			// its own middle, so shift the view by how far that point moves.
			const rect = canvas.getBoundingClientRect();
			const x = frame.left + lens.x + (at.clientX - rect.left) - frame.fullWidth / 2;
			const y = frame.top + lens.y + (at.clientY - rect.top) - frame.fullHeight / 2;
			lens.x += x * (grown - 1);
			lens.y += y * (grown - 1);
		} else {
			lens.x *= grown;
			lens.y *= grown;
			lens.x += (frame.left + frame.width / 2 - frame.fullWidth / 2) * (grown - 1);
			lens.y += (frame.top + frame.height / 2 - frame.fullHeight / 2) * (grown - 1);
		}
		applyView();
		requestRender();
	}
	function startZooming(limit) {
		zoomLimit = limit;
		stage.dataset.zooming = '';
	}
	function stopZooming() {
		zoomLimit = 0;
		delete stage.dataset.zooming;
	}
	canvas.addEventListener(
		'wheel',
		(event) => {
			if (!zoomLimit) return;
			event.preventDefault();
			setZoom(camera.zoom * Math.exp(-event.deltaY * 0.0015), event);
		},
		{ passive: false },
	);
	for (const button of zoomButtons.querySelectorAll('[data-zoom]')) {
		button.addEventListener('click', () => setZoom(camera.zoom * (button.dataset.zoom === 'in' ? 1.5 : 1 / 1.5)));
	}
	// Two fingers apart or together.
	const touches = new Map();
	let pinch = null;
	const spread = () => {
		const [a, b] = [...touches.values()];
		return Math.hypot(a[0] - b[0], a[1] - b[1]);
	};
	canvas.addEventListener('pointerdown', (event) => {
		if (!zoomLimit) return;
		touches.set(event.pointerId, [event.clientX, event.clientY]);
		if (touches.size === 2) pinch = { spread: spread(), zoom: camera.zoom };
	});
	canvas.addEventListener('pointermove', (event) => {
		if (!touches.has(event.pointerId)) return;
		touches.set(event.pointerId, [event.clientX, event.clientY]);
		if (pinch && touches.size === 2) {
			const [a, b] = [...touches.values()];
			setZoom((pinch.zoom * spread()) / pinch.spread, { clientX: (a[0] + b[0]) / 2, clientY: (a[1] + b[1]) / 2 });
		}
	});
	for (const type of ['pointerup', 'pointercancel']) {
		canvas.addEventListener(type, (event) => {
			touches.delete(event.pointerId);
			if (touches.size < 2) pinch = null;
		});
	}

	// ------------------------------------------------------------ using the laptop

	// How far from a flat thing, square on, for it to fill that much of the
	// view, whatever the window's shape: measured with a copy of the camera.
	const probe = camera.clone();
	function fitDistance(centre, normal, points, fill) {
		// As the view will be on arrival, with the plain lens.
		probe.copy(camera);
		probe.zoom = 1;
		probe.setViewOffset(frame.fullWidth, frame.fullHeight, frame.left, frame.top, frame.width, frame.height);
		probe.updateProjectionMatrix();
		probe.position.copy(centre).add(normal);
		probe.lookAt(centre);
		probe.updateMatrixWorld();
		let reach = 0;
		for (const point of points) {
			const seen = point.clone().project(probe);
			reach = Math.max(reach, Math.abs(seen.x), Math.abs(seen.y));
		}
		return reach / fill;
	}

	// Up at the screen, the terminal takes the pointer and keyboard (see the
	// stage's [data-laptop] styles); Escape or Step back leaves.
	const back = stage.querySelector('.step-back');
	const laptopDialog = document.getElementById('laptop-dialog');
	const narrow = matchMedia('(max-width: 700px)');
	let usingLaptop = false;
	async function useLaptop() {
		// On a narrow screen the 3D screen is too small to read, so the terminal
		// opens in its dialog instead, and goes back on the screen when it closes.
		if (narrow.matches) {
			terminalAway = true;
			laptopDialog.append(os);
			os.inert = false;
			laptopDialog.showModal();
			laptop.focus();
			laptopDialog.addEventListener(
				'close',
				() => {
					terminalAway = false;
					os.inert = true;
					render();
				},
				{ once: true },
			);
			return;
		}
		if (usingLaptop || !(await api.flyTo('laptop'))) return;
		usingLaptop = true;
		stage.dataset.laptop = '';
		os.inert = false;
		laptop.focus();
	}
	function leaveLaptop() {
		if (!usingLaptop) return;
		usingLaptop = false;
		delete stage.dataset.laptop;
		os.inert = true;
		api.flyHome();
	}
	back.addEventListener('click', leaveLaptop);
	document.addEventListener('keydown', (event) => event.key === 'Escape' && leaveLaptop());

	// ------------------------------------------------------------ reading the Morse card

	// Up at the card, scrolling or pinching zooms in on it; Escape or Step
	// back leaves.
	let readingCard = false;
	async function readCard() {
		if (readingCard || !(await api.flyTo('morse'))) return;
		readingCard = true;
		stage.dataset.card = '';
	}
	function leaveCard() {
		if (!readingCard) return;
		readingCard = false;
		delete stage.dataset.card;
		api.flyHome();
	}
	back.addEventListener('click', leaveCard);
	document.addEventListener('keydown', (event) => event.key === 'Escape' && leaveCard());

	// ------------------------------------------------------------ start

	let hintTimer;
	function hideHint() {
		clearTimeout(hintTimer);
		hint.classList.remove('shown');
	}

	drawPhone();
	// The clock on the phone.
	setInterval(() => {
		drawPhone();
		requestRender();
	}, 20000);
	fit();
	new ResizeObserver(fit).observe(stage);
	blink();
	startMoving();
	startZooming(LOOK.zoom);
	canvas.style.cursor = 'grab';
	canvas.classList.add('ready');
	terminalRenderer.domElement.classList.add('ready');
	// Once the fade has finished, the HTML hotspots over the still step aside.
	canvas.addEventListener('transitionend', () => (stage.dataset.live = ''), { once: true });
	if (matchMedia('(hover: none)').matches) hint.textContent = 'Drag to look around, pinch to zoom. Tap things.';
	hint.classList.add('shown');
	hintTimer = setTimeout(hideHint, 6000);
	return api;
}
