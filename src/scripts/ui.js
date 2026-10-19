// Everything you can do in the cabin apart from the laptop (laptop.js): the
// hotspots, the dialogs, sound, the radio, the guitar (which needs the
// plectrum), the control panel's pattern game, and the light in the window,
// played as beeps. It works the same over the still and over the live scene;
// when the live scene is running (window.cabin), the camera flies to a prop
// before its dialog opens, and the gravity lever works (once it's enabled).

import { progress } from './progress.js';

const MUFFLED = 650;
// The tune the ship hears: the Ground Control lines of Space Oddity, as in
// the songbook in the guitar's panel. It only counts once the Major Tom
// message has come through Snake (laptop.js); before that, it's just a song.
const SONG = ['C', 'Em', 'C', 'Em'];
// The control panel: three rounds of this many flashes; each colour's tone.
const SYNC = { rounds: [4, 6, 8], on: 0.45, gap: 0.18, tones: { blue: 262, green: 330, red: 392, yellow: 523 } };
const CLEAR = 18000;
const STANDARD_TUNING = [82.41, 110.0, 146.83, 196.0, 246.94, 329.63];
const STRING_NAMES = ['E', 'A', 'D', 'G', 'B', 'e'];
// The G string has slipped flat; the song only counts once it's back in
// tune. Each turn of its peg is step cents; within close counts as in tune.
const TUNING = { string: 3, slipped: -50, step: 10, close: 5 };
// The call home at the end: seconds between its lines.
const CALL_LINE_SECONDS = 2.6;
// Frets per string, low E to high e; null means the string isn't played.
const CHORDS = {
	Open: [0, 0, 0, 0, 0, 0],
	Em: [0, 2, 2, 0, 0, 0],
	G: [3, 2, 0, 0, 0, 3],
	C: [null, 3, 2, 0, 1, 0],
	D: [null, null, 0, 2, 3, 2],
	Am: [null, 0, 2, 2, 1, 0],
};

export function initCabin(stage) {
	const toast = stage.querySelector('.toast');
	const soundButton = stage.querySelector('.sound');
	let toastTimer;

	// Up long enough to read: 3.5 seconds, or longer for a longer line.
	function say(text) {
		toast.textContent = text;
		toast.classList.add('shown');
		clearTimeout(toastTimer);
		toastTimer = setTimeout(() => toast.classList.remove('shown'), Math.max(3500, text.length * 70));
	}

	// ------------------------------------------------------------ sound

	// Built on the first click that needs sound, because browsers only allow
	// audio to start from a click or key press.
	let audio = null;

	function getAudio() {
		if (!audio) {
			const ctx = new AudioContext({ latencyHint: 'interactive' });
			const master = ctx.createGain();
			master.gain.value = 0;
			master.connect(ctx.destination);
			const filter = ctx.createBiquadFilter();
			filter.type = 'lowpass';
			filter.frequency.value = MUFFLED;
			const music = ctx.createGain();
			music.gain.value = 0.6;
			const volume = ctx.createGain();
			volume.gain.value = 0.6;
			filter.connect(music);
			music.connect(volume);
			volume.connect(master);
			const effects = ctx.createGain();
			effects.gain.value = 0.9;
			effects.connect(master);
			const ambience = ctx.createGain();
			ambience.gain.value = 0.12;
			ambience.connect(master);
			// Listens to the radio, for the waveform on the phone's screen.
			const analyser = ctx.createAnalyser();
			analyser.fftSize = 1024;
			music.connect(analyser);
			audio = { ctx, master, filter, music, volume, effects, ambience, analyser, on: false };
			Object.assign(audio, startHum(audio));
			setGenerator(gravityOn);
		}
		if (audio.ctx.state === 'suspended') audio.ctx.resume();
		return audio;
	}

	function setSound(on) {
		const { ctx, master } = getAudio();
		audio.on = on;
		// iOS mutes web audio when the ringer switch is off unless the page asks
		// to play like a media app; only ask once someone turns sound on.
		if (on && navigator.audioSession) navigator.audioSession.type = 'playback';
		master.gain.cancelScheduledValues(ctx.currentTime);
		master.gain.setTargetAtTime(on ? 1 : 0, ctx.currentTime, 0.08);
		soundButton.setAttribute('aria-pressed', String(on));
		soundButton.querySelector('.sound-label').textContent = on ? 'Sound on' : 'Sound off';
	}

	// Anything you play turns sound on: playing it is asking for sound.
	function withSound() {
		const sound = getAudio();
		if (!sound.on) setSound(true);
		return sound;
	}

	soundButton.addEventListener('click', () => setSound(!(audio && audio.on)));

	// ------------------------------------------------------------ dialogs and props

	// Resolves true if the camera actually moved, so it can come back afterwards.
	async function flyTo(prop) {
		return window.cabin ? window.cabin.flyTo(prop) : false;
	}

	// In the live scene these panels sit in a corner instead of blocking the
	// view, so you can keep looking around, watch the light in the window
	// while reading the Morse card, and see the phone's screen while the radio
	// plays. Escape still closes them.
	const SIDE_PANELS = new Set(['window', 'morse', 'phone', 'panel']);

	async function openDialog(prop, id) {
		const dialog = document.getElementById(id);
		if (dialog.open) return;
		const flew = await flyTo(prop);
		if (SIDE_PANELS.has(prop) && window.cabin) {
			dialog.show();
			const escape = (event) => event.key === 'Escape' && dialog.close();
			document.addEventListener('keydown', escape);
			dialog.addEventListener('close', () => document.removeEventListener('keydown', escape), { once: true });
		} else {
			dialog.showModal();
		}
		if (flew) dialog.addEventListener('close', () => window.cabin?.flyHome(), { once: true });
	}

	const mugLines = [
		'Sip. Still hot.',
		'Sip. Half gone.',
		'Sip. Going cold.',
		"Empty. The galley's closed until Tuesday.",
	];
	let sips = 0;
	let headphonesOn = false;

	const actions = {
		// A line of its own, from the hotspot's data-say.
		say(hotspot) {
			say(hotspot.dataset.say);
		},
		sip() {
			say(mugLines[sips % mugLines.length]);
			sips += 1;
		},
		plant() {
			say("A snake plant. It's thriving on neglect.");
		},
		// The DO NOT LOSE case stays jammed shut until there's no gravity.
		discs(hotspot) {
			say(gravityOn ? hotspot.dataset.say : hotspot.dataset.floating);
		},
		headphones() {
			setHeadphones(!headphonesOn);
			if (headphonesOn && !radio.playing) startRadio();
			say(headphonesOn ? 'Headphones on.' : 'Headphones back on the hook. The music leaks out, muffled.');
		},
	};

	// What each prop does comes from its hotspot in the page: a dialog to
	// open or an action to run. The gravity lever has no hotspot: only the
	// live scene can make things float.
	function activate(prop) {
		if (prop === 'gravity') return window.cabin?.toggleGravity();
		// In the live scene, the camera goes up to the laptop's own screen.
		if (prop === 'laptop' && window.cabin) return window.cabin.useLaptop();
		const hotspot = document.querySelector(`.hotspot[data-prop="${prop}"]`);
		if (!hotspot) return;
		const { dialog, action } = hotspot.dataset;
		if (dialog) openDialog(prop, dialog);
		else if (action) actions[action](hotspot);
	}

	// The hotspots over the still, the buttons for small screens, and the
	// keyboard menu. The live scene calls activate() itself.
	for (const element of document.querySelectorAll('[data-prop]')) {
		element.addEventListener('click', (event) => {
			event.preventDefault();
			activate(element.dataset.prop);
		});
	}

	// ------------------------------------------------------------ plucked strings

	// Karplus-Strong: a burst of noise fed back through a short delay and an
	// averaging filter sounds like a plucked string. Rendered once per pitch.
	const plucks = new Map();

	function pluckBuffer(ctx, frequency, brightness) {
		const key = `${frequency.toFixed(2)}:${brightness}`;
		if (plucks.has(key)) return plucks.get(key);
		const rate = ctx.sampleRate;
		const length = Math.floor(rate * 3);
		const buffer = ctx.createBuffer(1, length, rate);
		const data = buffer.getChannelData(0);
		// The averaging adds half a sample of delay; take it off the period.
		const period = Math.max(2, Math.round(rate / frequency - 0.5));
		let smooth = 0;
		for (let i = 0; i < period; i++) {
			smooth += (Math.random() * 2 - 1 - smooth) * brightness;
			data[i] = smooth;
		}
		for (let i = period; i < length; i++) {
			data[i] = 0.4985 * (data[i - period] + (i > period ? data[i - period - 1] : 0));
		}
		plucks.set(key, buffer);
		return buffer;
	}

	function pluck(frequency, { when = 0, gain = 0.5, brightness = 0.55, output } = {}) {
		const { ctx, effects } = audio;
		const source = ctx.createBufferSource();
		source.buffer = pluckBuffer(ctx, frequency, brightness);
		const level = ctx.createGain();
		level.gain.value = gain;
		source.connect(level);
		level.connect(output || effects);
		source.start(when || ctx.currentTime);
	}

	// ------------------------------------------------------------ cabin hum

	function startHum({ ctx, ambience }) {
		// Brown noise through a low-pass filter: the ship's air and engines.
		const seconds = 6;
		const buffer = ctx.createBuffer(1, ctx.sampleRate * seconds, ctx.sampleRate);
		const data = buffer.getChannelData(0);
		let last = 0;
		for (let i = 0; i < data.length; i++) {
			last = (last + 0.02 * (Math.random() * 2 - 1)) / 1.02;
			data[i] = last * 3.5;
		}
		const noise = ctx.createBufferSource();
		noise.buffer = buffer;
		noise.loop = true;
		const low = ctx.createBiquadFilter();
		low.type = 'lowpass';
		low.frequency.value = 160;
		noise.connect(low);
		low.connect(ambience);
		noise.start();
		const drone = ctx.createOscillator();
		drone.frequency.value = 55;
		const droneLevel = ctx.createGain();
		droneLevel.gain.value = 0.08;
		drone.connect(droneLevel);
		droneLevel.connect(ambience);
		drone.start();
		return { drone, droneLevel };
	}

	// ------------------------------------------------------------ gravity

	// The drone in the hum is the gravity generator: switched off, it winds
	// down and nearly fades; on, it winds back up.
	let gravityOn = true;
	const gravityButton = document.querySelector('.skip [data-prop="gravity"]');

	function setGenerator(on) {
		const { ctx, drone, droneLevel } = audio;
		const settle = on ? 0.3 : 0.9;
		drone.frequency.setTargetAtTime(on ? 55 : 36, ctx.currentTime, settle);
		droneLevel.gain.setTargetAtTime(on ? 0.08 : 0.015, ctx.currentTime, settle);
	}

	// A short burst of noise around a pitch: a latch, or something landing on the desk.
	function knock(when, pitch, gain) {
		const { ctx, effects } = audio;
		if (!audio.noise) {
			audio.noise = ctx.createBuffer(1, ctx.sampleRate * 0.05, ctx.sampleRate);
			const data = audio.noise.getChannelData(0);
			for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
		}
		const burst = ctx.createBufferSource();
		burst.buffer = audio.noise;
		const band = ctx.createBiquadFilter();
		band.type = 'bandpass';
		band.frequency.value = pitch;
		band.Q.value = 3;
		const level = ctx.createGain();
		level.gain.setValueAtTime(gain, when);
		level.gain.exponentialRampToValueAtTime(0.001, when + 0.05);
		burst.connect(band);
		band.connect(level);
		level.connect(effects);
		burst.start(when);
		burst.stop(when + 0.05);
	}

	// The lever thrown: a clunk, the generator, and a line to say so. landings
	// are the seconds until each falling thing hits the desk, for a clatter.
	function gravity(on, landings = []) {
		gravityOn = on;
		gravityButton?.setAttribute('aria-pressed', String(on));
		say(on ? 'Gravity on.' : 'Gravity off. Grab something and throw it.');
		if (!audio) return;
		setGenerator(on);
		if (!audio.on) return;
		const now = clunk();
		for (const seconds of landings) knock(now + seconds, 1200 + Math.random() * 2500, 0.6 + Math.random() * 0.8);
	}

	// The lever thrown while manual gravity control is locked out: a clunk,
	// and nothing else.
	function gravityRefused() {
		say('Nothing happens. The lamp by the lever blinks red.');
		if (audio?.on) clunk();
	}

	// A lever going over: a thump and a latch. Returns when it played.
	function clunk() {
		const now = audio.ctx.currentTime;
		const thump = audio.ctx.createOscillator();
		thump.frequency.setValueAtTime(150, now);
		thump.frequency.exponentialRampToValueAtTime(45, now + 0.15);
		const level = audio.ctx.createGain();
		level.gain.setValueAtTime(0.6, now);
		level.gain.exponentialRampToValueAtTime(0.001, now + 0.2);
		thump.connect(level);
		level.connect(audio.effects);
		thump.start(now);
		thump.stop(now + 0.21);
		knock(now, 2500, 1.2);
		return now;
	}

	// ------------------------------------------------------------ the radio

	const radioDialog = document.getElementById('radio-dialog');
	const playButton = radioDialog.querySelector('.play');
	const headphonesButton = radioDialog.querySelector('.headphones');
	const radio = { playing: false, timer: null, next: 0, bar: 0, bus: null };
	const midi = (note) => 440 * 2 ** ((note - 69) / 12);
	// Dmaj7, Bm7, Gmaj7, A add9: four bars, six seconds each.
	const PROGRESSION = [
		[50, 57, 61, 66],
		[47, 54, 57, 62],
		[43, 50, 54, 59],
		[45, 52, 59, 61],
	];
	const PENTATONIC = [62, 64, 66, 69, 71, 74, 76, 78, 81];
	const BAR = 6;

	function playChord(notes, when) {
		const { ctx } = audio;
		for (const note of notes) {
			for (const detune of [-6, 6]) {
				const osc = ctx.createOscillator();
				osc.type = 'triangle';
				osc.frequency.value = midi(note);
				osc.detune.value = detune;
				const level = ctx.createGain();
				level.gain.setValueAtTime(0, when);
				level.gain.linearRampToValueAtTime(0.035, when + 2);
				level.gain.setTargetAtTime(0, when + BAR - 0.5, 1.2);
				osc.connect(level);
				level.connect(radio.bus);
				osc.start(when);
				osc.stop(when + BAR + 5);
			}
		}
	}

	// Schedules a little ahead of time, so the music doesn't stutter when the
	// page is busy.
	function scheduleRadio() {
		const { ctx } = audio;
		while (radio.next < ctx.currentTime + 1.5) {
			const when = radio.next;
			playChord(PROGRESSION[radio.bar % PROGRESSION.length], when);
			for (let beat = 0; beat < 4; beat++) {
				if (Math.random() < 0.55) {
					const note = PENTATONIC[Math.floor(Math.random() * PENTATONIC.length)];
					pluck(midi(note), { when: when + beat * (BAR / 4) + Math.random() * 0.2, gain: 0.18, brightness: 0.4, output: radio.bus });
				}
			}
			radio.bar += 1;
			radio.next += BAR;
		}
	}

	function startRadio() {
		const { ctx, filter } = withSound();
		// Each run gets its own bus, so stopping can fade it out cleanly.
		radio.bus = ctx.createGain();
		const echo = ctx.createDelay();
		echo.delayTime.value = 0.375;
		const feedback = ctx.createGain();
		feedback.gain.value = 0.35;
		radio.bus.connect(filter);
		radio.bus.connect(echo);
		echo.connect(feedback);
		feedback.connect(echo);
		echo.connect(filter);
		radio.next = ctx.currentTime + 0.1;
		radio.bar = 0;
		radio.playing = true;
		radio.started = true;
		radio.since = performance.now();
		scheduleRadio();
		radio.timer = setInterval(scheduleRadio, 250);
		playButton.textContent = 'Pause';
		playButton.setAttribute('aria-pressed', 'true');
		window.cabin?.phoneChanged();
	}

	function stopRadio() {
		const { ctx } = audio;
		clearInterval(radio.timer);
		radio.bus.gain.setTargetAtTime(0, ctx.currentTime, 0.3);
		const bus = radio.bus;
		setTimeout(() => bus.disconnect(), 3000);
		radio.playing = false;
		playButton.textContent = 'Play';
		playButton.setAttribute('aria-pressed', 'false');
		window.cabin?.phoneChanged();
	}

	function setHeadphones(on) {
		const { ctx, filter, music } = getAudio();
		headphonesOn = on;
		filter.frequency.setTargetAtTime(on ? CLEAR : MUFFLED, ctx.currentTime, 0.15);
		music.gain.setTargetAtTime(on ? 1 : 0.6, ctx.currentTime, 0.15);
		headphonesButton.textContent = on ? 'Headphones on' : 'Headphones off';
		headphonesButton.setAttribute('aria-pressed', String(on));
		window.cabin?.phoneChanged();
	}

	// What the phone's screen shows: the track and where it's from (as the
	// radio panel names them), whether it's playing and since when, the
	// headphones, and the radio's sound right now, for the waveform.
	const track = radioDialog.querySelector('.now').textContent;
	const station = document.getElementById('radio-title').textContent;
	const wave = new Uint8Array(512);
	function nowPlaying() {
		if (radio.playing) audio.analyser.getByteTimeDomainData(wave);
		else wave.fill(128);
		return { track, station, started: Boolean(radio.started), playing: radio.playing, since: radio.since, headphones: headphonesOn, wave };
	}

	playButton.addEventListener('click', () => (radio.playing ? stopRadio() : startRadio()));
	headphonesButton.addEventListener('click', () => {
		withSound();
		setHeadphones(!headphonesOn);
	});
	radioDialog.querySelector('.volume input').addEventListener('input', (event) => {
		const { ctx, volume } = getAudio();
		volume.gain.setTargetAtTime(Number(event.target.value), ctx.currentTime, 0.05);
	});

	// ------------------------------------------------------------ the guitar

	const guitarDialog = document.getElementById('guitar-dialog');
	const strings = [...guitarDialog.querySelectorAll('.string')];
	let chordName = 'Open';
	let chord = CHORDS.Open;
	let dragging = false;
	// The chords strummed so far, for the song.
	const strummed = [];
	const tunerReading = guitarDialog.querySelector('.tuner-reading');
	let slipped = progress.has('tuned') ? 0 : TUNING.slipped;
	const centsOff = (index) => (index === TUNING.string ? slipped : 0);
	const inTune = () => Math.abs(slipped) < TUNING.close;

	function showTuning(index) {
		const off = centsOff(index);
		const { inTune: steady, flat, sharp } = tunerReading.dataset;
		tunerReading.textContent = `${STRING_NAMES[index]}: ${Math.abs(off) < TUNING.close ? steady : `${Math.abs(off)} ${off < 0 ? flat : sharp}`}`;
	}

	// Without the plectrum, a dead thud and a reminder.
	function needsPick() {
		if (progress.has('pick')) return false;
		const { ctx } = withSound();
		knock(ctx.currentTime, 180, 1.4);
		say('You need a pick. These strings would shred your fingers.');
		return true;
	}

	function pluckString(index, when) {
		const fret = chord[index];
		if (fret === null) return;
		if (when === undefined && needsPick()) return;
		withSound();
		pluck(STANDARD_TUNING[index] * 2 ** ((fret + centsOff(index) / 100) / 12), { when, gain: 0.55 });
		if (when === undefined) showTuning(index);
		const line = strings[index];
		line.classList.remove('ringing');
		void line.offsetWidth;
		line.classList.add('ringing');
	}

	function strum() {
		if (needsPick()) return;
		const { ctx } = withSound();
		strings.forEach((_, i) => pluckString(i, ctx.currentTime + i * 0.028));
		strummed.push(chordName);
		if (progress.has('snake') && !progress.has('song') && SONG.every((name, i) => strummed.at(i - SONG.length) === name)) {
			if (!inTune()) {
				setTimeout(() => say(guitarDialog.dataset.outOfTune), 1200);
				return;
			}
			progress.mark('song');
			setTimeout(() => say('New message on the laptop.'), 1800);
		}
	}

	for (const [index, string] of strings.entries()) {
		string.addEventListener('pointerdown', (event) => {
			dragging = true;
			string.releasePointerCapture?.(event.pointerId);
			pluckString(index);
		});
		string.addEventListener('pointerenter', () => dragging && pluckString(index));
		string.addEventListener('click', (event) => {
			// Keyboard activation has no pointerdown.
			if (event.detail === 0) pluckString(index);
		});
	}
	addEventListener('pointerup', () => (dragging = false));
	for (const button of guitarDialog.querySelectorAll('[data-chord]')) {
		button.addEventListener('click', () => {
			chordName = button.dataset.chord;
			chord = CHORDS[chordName];
			for (const other of guitarDialog.querySelectorAll('[data-chord]')) {
				other.setAttribute('aria-pressed', String(other === button));
			}
			strum();
		});
	}
	guitarDialog.querySelector('.strum').addEventListener('click', strum);
	for (const peg of guitarDialog.querySelectorAll('[data-peg]')) {
		peg.addEventListener('click', () => {
			slipped += Number(peg.dataset.peg) * TUNING.step;
			progress.mark('tuned', inTune());
			showTuning(TUNING.string);
			if (progress.has('pick')) pluckString(TUNING.string);
		});
	}
	guitarDialog.addEventListener('keydown', (event) => {
		if (event.key >= '1' && event.key <= '6') {
			pluckString(Number(event.key) - 1);
		} else if (event.key === ' ' && !event.target.closest('button')) {
			event.preventDefault();
			strum();
		}
	});

	// ------------------------------------------------------------ the control panel

	// Press Start and the panel flashes a pattern; play it back. Each round
	// adds two to the pattern; a mistake replays the round. After three, the
	// panel's in sync and the gravity fault clears. Every press and flash
	// lights the 3D buttons too.
	const panelDialog = document.getElementById('panel-dialog');
	const pads = Object.fromEntries([...panelDialog.querySelectorAll('[data-colour]')].map((pad) => [pad.dataset.colour, pad]));
	const syncStart = panelDialog.querySelector('.sync-start');
	const syncRound = panelDialog.querySelector('.sync-round');
	const syncStatus = panelDialog.querySelector('.sync-status');
	const sync = { pattern: [], round: 0, entered: 0, watching: false, timers: [] };
	const anyColour = () => Object.keys(pads)[Math.floor(Math.random() * 4)];

	function light(colour, seconds) {
		const pad = pads[colour];
		pad.classList.add('lit');
		window.cabin?.panelLight(colour, true);
		if (audio?.on) {
			const { ctx, effects } = audio;
			const tone = ctx.createOscillator();
			tone.type = 'square';
			tone.frequency.value = SYNC.tones[colour];
			const level = ctx.createGain();
			level.gain.setValueAtTime(0.08, ctx.currentTime);
			level.gain.setTargetAtTime(0, ctx.currentTime + seconds, 0.03);
			tone.connect(level);
			level.connect(effects);
			tone.start();
			tone.stop(ctx.currentTime + seconds + 0.2);
		}
		setTimeout(() => {
			pad.classList.remove('lit');
			window.cabin?.panelLight(colour, false);
		}, seconds * 1000);
	}

	function showSynced() {
		panelDialog.querySelector('.sync-state').textContent = 'In sync. Fault E-07 cleared.';
		syncStart.hidden = true;
		syncRound.textContent = '';
	}

	function playPattern() {
		sync.watching = true;
		sync.entered = 0;
		syncStatus.textContent = 'Watch.';
		syncRound.textContent = `Round ${sync.round + 1} of ${SYNC.rounds.length}`;
		const step = (SYNC.on + SYNC.gap) * 1000;
		sync.pattern.forEach((colour, i) => sync.timers.push(setTimeout(() => light(colour, SYNC.on), 700 + i * step)));
		sync.timers.push(
			setTimeout(() => {
				sync.watching = false;
				syncStatus.textContent = 'Your turn.';
			}, 700 + sync.pattern.length * step),
		);
	}

	function startSync() {
		withSound();
		sync.timers.forEach(clearTimeout);
		sync.round = 0;
		sync.pattern = Array.from({ length: SYNC.rounds[0] }, anyColour);
		playPattern();
	}

	syncStart.addEventListener('click', startSync);
	for (const [colour, pad] of Object.entries(pads)) {
		pad.addEventListener('click', () => {
			light(colour, 0.25);
			if (!sync.pattern.length || sync.watching || progress.has('panel')) return;
			if (colour !== sync.pattern[sync.entered]) {
				syncStatus.textContent = 'Not quite. Watch again.';
				sync.watching = true;
				sync.timers.push(setTimeout(playPattern, 900));
				return;
			}
			sync.entered += 1;
			if (sync.entered < sync.pattern.length) return;
			sync.round += 1;
			if (sync.round === SYNC.rounds.length) {
				progress.mark('panel');
				showSynced();
				syncStatus.textContent = 'The lamp turns green.';
				window.cabin?.panelSynced();
				return;
			}
			syncStatus.textContent = 'Good.';
			while (sync.pattern.length < SYNC.rounds[sync.round]) sync.pattern.push(anyColour());
			sync.watching = true;
			sync.timers.push(setTimeout(playPattern, 900));
		});
	}
	panelDialog.addEventListener('close', () => {
		sync.timers.forEach(clearTimeout);
		sync.pattern = [];
		if (!progress.has('panel')) {
			syncStatus.textContent = '';
			syncRound.textContent = '';
		}
	});
	if (progress.has('panel')) showSynced();

	// ------------------------------------------------------------ the light in the window

	const windowDialog = document.getElementById('window-dialog');

	// The same pattern as the light, as beeps: dots and dashes for anyone who
	// can't watch it blink.
	windowDialog.querySelector('.replay').addEventListener('click', (event) => {
		const { ctx, effects } = withSound();
		const steps = JSON.parse(event.currentTarget.dataset.signal);
		const unit = 0.12;
		let when = ctx.currentTime + 0.1;
		for (const [on, length] of steps) {
			if (on) {
				const tone = ctx.createOscillator();
				tone.frequency.value = 620;
				const level = ctx.createGain();
				level.gain.setValueAtTime(0, when);
				level.gain.linearRampToValueAtTime(0.25, when + 0.005);
				level.gain.setValueAtTime(0.25, when + length * unit - 0.005);
				level.gain.linearRampToValueAtTime(0, when + length * unit);
				tone.connect(level);
				level.connect(effects);
				tone.start(when);
				tone.stop(when + length * unit + 0.01);
			}
			when += length * unit;
		}
	});

	// ------------------------------------------------------------ calling home

	// Once the ship's safe, the phone can call home: the lines appear one by one.
	const call = radioDialog.querySelector('.call');
	const showCall = () => (call.hidden = !progress.has('saved'));
	showCall();
	progress.listen(showCall);
	call.querySelector('.call-home').addEventListener('click', (event) => {
		event.currentTarget.disabled = true;
		[...call.querySelectorAll('.call-lines p')].forEach((line, i) => {
			setTimeout(() => {
				line.hidden = false;
				if (!line.nextElementSibling) progress.mark('called');
			}, i * CALL_LINE_SECONDS * 1000);
		});
	});

	// Something thrown hitting a wall or the desk: louder the faster it was going.
	function bump(speed) {
		if (!audio?.on) return;
		knock(audio.ctx.currentTime, 700 + Math.random() * 2000, Math.min(1.4, 0.3 + speed * 0.4));
	}

	return { activate, gravity, gravityRefused, bump, nowPlaying, say };
}
