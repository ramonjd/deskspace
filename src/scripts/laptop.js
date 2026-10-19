// The laptop's registry terminal (src/components/Laptop.astro): logging in,
// the menu, messages, the registry, settings and Snake. Progress is saved,
// so once you're logged in you stay logged in.
//
// The password is what the light outside the window blinks. Only its SHA-256
// is kept here, so reading the page's code doesn't give it away.

import { progress } from './progress.js';
import { createSnake, step, turn } from './snake.js';

const PASSWORD_SHA256 = '2c50624bea38c570f59fb28e3fffd11330856e2cd512760acaff9eb82d3df8ca';
// Snake: a 30 by 18 grid, moving this many cells a second.
const SNAKE = { columns: 30, rows: 18, speed: 8 };
const KEYS = { ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right', w: 'up', s: 'down', a: 'left', d: 'right' };
// The backup's password is written inside the DO NOT LOSE disc case (ui.js).
const BACKUP_PASSWORD = 'flexbox';
// The flight code (Laptop.astro): the right number of pulses, give or take.
const FLIGHT = { pulses: 3949, tolerance: 0.01 };
// bezel.js's own styles, as the crew's page loads them: a locked panel shows
// its notice and hides its controls.
const BEZEL_CSS = `<style>
body { margin: 0; padding: 16px; font: 15px/1.4 ui-monospace, Menlo, monospace; color: #cfe9ec; background: transparent; }
.bezel { position: relative; min-height: 140px; padding: 20px; border: 2px solid #cfe9ec; }
.bezel-notice { display: none; }
.bezel[data-bezel-locked="true"] .bezel-notice { display: grid; place-items: center; position: absolute; inset: 0; margin: 0; padding: 16px; text-align: center; }
.bezel[data-bezel-locked="true"] .bezel-controls { visibility: hidden; }
button { font: inherit; color: #17323b; background: #cfe9ec; border: 0; padding: 12px 16px; cursor: pointer; }
</style>`;

async function sha256(text) {
	const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
	return [...new Uint8Array(bytes)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

// A goat in profile, facing left, as one-bit pixels: drawn small in shapes,
// every pixel then set fully on or off, and scaled up square.
function drawGoat(canvas, ink) {
	const small = document.createElement('canvas');
	small.width = 64;
	small.height = 40;
	const s = small.getContext('2d');
	s.fillStyle = '#fff';
	s.strokeStyle = '#fff';
	const blob = (x, y, rx, ry, turn = 0) => {
		s.beginPath();
		s.ellipse(x, y, rx, ry, turn, 0, Math.PI * 2);
		s.fill();
	};
	const shape = (points) => {
		s.beginPath();
		s.moveTo(...points[0]);
		for (const point of points.slice(1)) s.lineTo(...point);
		s.fill();
	};
	blob(38, 20, 15, 7.5);
	shape([[25, 15], [18, 7], [14, 10], [23, 22]]);
	blob(14, 10, 5.5, 3.4, -0.45);
	blob(8.5, 13.2, 3.4, 2.1, -0.55);
	shape([[8, 14.5], [11, 15], [8.5, 20.5]]);
	shape([[16, 8], [22.5, 9.5], [16.5, 10.5]]);
	s.lineWidth = 2.2;
	s.beginPath();
	s.arc(19.5, 9.5, 5.5, Math.PI * 1.12, Math.PI * 1.8);
	s.stroke();
	for (const x of [26, 30, 43, 47]) s.fillRect(x, 24, 2.6, 12);
	shape([[52, 16], [56, 10.5], [54, 17.5]]);
	s.clearRect(12, 8.6, 1.6, 1.6);
	const { data } = s.getImageData(0, 0, small.width, small.height);
	const c = canvas.getContext('2d');
	const cell = canvas.width / small.width;
	c.clearRect(0, 0, canvas.width, canvas.height);
	c.fillStyle = ink;
	for (let y = 0; y < small.height; y++) {
		for (let x = 0; x < small.width; x++) if (data[(y * small.width + x) * 4 + 3] > 128) c.fillRect(x * cell, y * cell, cell, cell);
	}
}

// The photos on PHOTOS 2011 (Laptop.astro), stand-ins until there are real
// ones: each is drawn small in greys, dithered to one-bit pixels in the
// terminal's ink and scaled up square, the way an old photo shows on it.
// Words in a picture (a banner, a slide) are cut out afterwards, sharp, so
// they read. Each scene returns those words, in the small picture's units.
const BAYER = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5];
const PHOTOS = {
	mum({ s, tone, blob, box, shade }) {
		shade(0.3, 0.18);
		box(0, 0, 96, 64);
		tone(1);
		box(62, 6, 26, 22);
		tone(0.2);
		box(74, 6, 1.5, 22);
		box(62, 16, 26, 1.5);
		tone(0.6);
		s.beginPath();
		s.moveTo(22, 64);
		s.quadraticCurveTo(24, 38, 40, 37);
		s.quadraticCurveTo(56, 38, 58, 64);
		s.fill();
		tone(0.08);
		for (const [x, y] of [[32, 20], [36, 16], [42, 15], [47, 18], [49, 24], [31, 27], [49, 30]]) blob(x, y, 5, 5);
		tone(0.95);
		blob(40, 26, 8, 9.5);
		tone(0.1);
		blob(37, 25, 1, 1.2);
		blob(43, 25, 1, 1.2);
		s.lineWidth = 1.2;
		s.beginPath();
		s.arc(40, 29, 3.5, 0.15 * Math.PI, 0.85 * Math.PI);
		s.stroke();
		tone(0.1);
		box(0, 50, 96, 14);
		tone(0.5);
		box(0, 50, 96, 1.5);
		tone(1);
		blob(72, 46, 8, 6);
		box(70, 38, 4, 3);
		s.lineWidth = 2;
		s.beginPath();
		s.moveTo(65, 45);
		s.lineTo(60, 40);
		s.stroke();
		s.beginPath();
		s.arc(80, 46, 3.5, -Math.PI / 2, Math.PI / 2);
		s.stroke();
	},
	barry({ s, tone, blob, box, shade }) {
		shade(0.32, 0.2);
		box(0, 0, 96, 64);
		tone(0.1);
		for (let x = 0; x < 96; x += 7) box(x, 30, 5, 34);
		tone(0.05);
		box(66, 30, 28, 22);
		tone(0.42);
		box(68, 32, 24, 18);
		tone(0.15);
		blob(76, 48, 5, 3);
		blob(86, 47, 4, 3);
		tone(0.55);
		s.beginPath();
		s.moveTo(14, 64);
		s.quadraticCurveTo(16, 34, 38, 33);
		s.quadraticCurveTo(60, 34, 62, 64);
		s.fill();
		tone(0.95);
		blob(38, 20, 9, 10.5);
		tone(0.12);
		s.beginPath();
		s.ellipse(38, 25, 9, 7, 0, 0, Math.PI);
		s.fill();
		tone(0.1);
		blob(35, 18, 1, 1.2);
		blob(41, 18, 1, 1.2);
		tone(1);
		blob(38, 12, 3, 1.5);
		// Gerald, round his shoulders.
		s.lineCap = 'round';
		tone(0.92);
		s.lineWidth = 6;
		s.beginPath();
		s.moveTo(12, 52);
		s.bezierCurveTo(18, 30, 30, 40, 38, 36);
		s.bezierCurveTo(48, 32, 58, 42, 66, 32);
		s.stroke();
		tone(0.1);
		s.lineWidth = 2;
		s.setLineDash([2, 3]);
		s.stroke();
		s.setLineDash([]);
		tone(0.92);
		blob(68, 30, 4, 3, -0.4);
		tone(0.05);
		s.lineWidth = 0.8;
		s.beginPath();
		s.moveTo(71, 28.5);
		s.lineTo(75, 27);
		s.stroke();
	},
	hackday({ s, tone, blob, box, shade }) {
		shade(0.5, 0.25);
		box(0, 0, 96, 64);
		tone(1);
		box(10, 3, 76, 12);
		tone(0.08);
		blob(30, 28, 9, 12);
		box(21, 28, 18, 14);
		tone(0.95);
		blob(30, 26, 6.5, 8);
		tone(0.1);
		blob(27.5, 25, 1, 1.2);
		blob(32.5, 25, 1, 1.2);
		tone(0.65);
		s.beginPath();
		s.moveTo(16, 64);
		s.quadraticCurveTo(18, 40, 30, 39);
		s.quadraticCurveTo(42, 40, 44, 64);
		s.fill();
		tone(0.45);
		s.beginPath();
		s.moveTo(52, 64);
		s.quadraticCurveTo(54, 40, 66, 39);
		s.quadraticCurveTo(78, 40, 80, 64);
		s.fill();
		tone(0.95);
		blob(66, 27, 7, 8.5);
		tone(0.08);
		s.beginPath();
		s.ellipse(66, 22, 7.5, 5, 0, Math.PI, 2 * Math.PI);
		s.fill();
		s.lineWidth = 1;
		for (const x of [63, 69]) {
			s.beginPath();
			s.arc(x, 27, 2.2, 0, Math.PI * 2);
			s.stroke();
		}
		tone(0.12);
		box(0, 55, 96, 9);
		tone(0.75);
		for (const x of [18, 54]) {
			s.beginPath();
			s.moveTo(x, 55);
			s.lineTo(x + 3, 46);
			s.lineTo(x + 21, 46);
			s.lineTo(x + 24, 55);
			s.fill();
		}
		tone(0.1);
		blob(30, 50.5, 1.8, 1.8);
		blob(66, 50.5, 1.8, 1.8);
		tone(0.9);
		box(82, 50, 14, 5);
		return [{ text: 'HACK DAY', x: 48, y: 9.5, size: 9 }];
	},
	launch({ s, tone, blob, box }) {
		tone(0.08);
		box(0, 0, 96, 64);
		tone(1);
		box(40, 4, 52, 32);
		const spot = s.createRadialGradient(18, 40, 2, 18, 40, 22);
		spot.addColorStop(0, 'rgb(150 150 150)');
		spot.addColorStop(1, 'rgb(20 20 20)');
		s.fillStyle = spot;
		box(0, 18, 38, 32);
		tone(0.3);
		box(0, 50, 96, 14);
		tone(0.45);
		box(0, 50, 96, 1.5);
		tone(0.7);
		s.beginPath();
		s.moveTo(11, 50);
		s.quadraticCurveTo(12, 35, 18, 34);
		s.quadraticCurveTo(24, 35, 25, 50);
		s.fill();
		tone(1);
		blob(18, 28, 4.5, 5.5);
		tone(0.05);
		s.beginPath();
		s.ellipse(18, 25.5, 5, 3.2, 0, Math.PI, 2 * Math.PI);
		s.fill();
		tone(0.15);
		s.beginPath();
		s.moveTo(20, 50);
		s.lineTo(22, 38);
		s.lineTo(32, 38);
		s.lineTo(34, 50);
		s.fill();
		tone(0.2);
		for (let x = 3; x < 96; x += 8) blob(x, 61, 3.5, 4);
		return [
			{ text: 'Every panel should', x: 66, y: 12, size: 4.2 },
			{ text: 'have a way back', x: 66, y: 20, size: 4.2 },
			{ text: 'to a person.', x: 66, y: 28, size: 4.2 },
		];
	},
};

function drawPhoto(canvas, ink) {
	const small = document.createElement('canvas');
	small.width = 96;
	small.height = 64;
	const s = small.getContext('2d');
	const grey = (value) => `rgb(${Math.round(value * 255)} ${Math.round(value * 255)} ${Math.round(value * 255)})`;
	const tone = (value) => (s.fillStyle = s.strokeStyle = grey(value));
	const blob = (x, y, rx, ry, turn = 0) => {
		s.beginPath();
		s.ellipse(x, y, rx, ry, turn, 0, Math.PI * 2);
		s.fill();
	};
	const box = (x, y, width, height) => s.fillRect(x, y, width, height);
	const shade = (top, bottom) => {
		const fade = s.createLinearGradient(0, 0, 0, small.height);
		fade.addColorStop(0, grey(top));
		fade.addColorStop(1, grey(bottom));
		s.fillStyle = fade;
	};
	const words = PHOTOS[canvas.dataset.photo]({ s, tone, blob, box, shade }) ?? [];
	const { data } = s.getImageData(0, 0, small.width, small.height);
	const c = canvas.getContext('2d');
	const cell = canvas.width / small.width;
	c.clearRect(0, 0, canvas.width, canvas.height);
	c.fillStyle = ink;
	for (let y = 0; y < small.height; y++) {
		for (let x = 0; x < small.width; x++) {
			if ((data[(y * small.width + x) * 4] / 255) * 16 > BAYER[(y % 4) * 4 + (x % 4)] + 0.5) c.fillRect(x * cell, y * cell, cell, cell);
		}
	}
	c.globalCompositeOperation = 'destination-out';
	c.textAlign = 'center';
	c.textBaseline = 'middle';
	for (const { text, x, y, size } of words) {
		c.font = `bold ${size * cell}px ui-monospace, Menlo, Consolas, monospace`;
		c.fillText(text, x * cell, y * cell);
	}
	c.globalCompositeOperation = 'source-over';
}

export function initLaptop(os) {
	const screens = Object.fromEntries([...os.querySelectorAll('[data-screen-name]')].map((section) => [section.dataset.screenName, section]));

	// Shows one screen, the messages with one of them open if asked. Moves the
	// keyboard there too, except when the page first loads.
	function show(name, { open = null, quiet = false } = {}) {
		for (const [key, section] of Object.entries(screens)) section.hidden = key !== name;
		os.dataset.screen = name;
		if (name === 'home') countUnread();
		if (name === 'messages') listMessages(open);
		if (name === 'photos') for (const photo of screens.photos.querySelectorAll('.os-photo')) drawPhoto(photo, ink);
		if (name !== 'snake') pause();
		if (!quiet) focus();
	}

	// The first thing to type in or press on the screen showing.
	function focus() {
		const section = screens[os.dataset.screen];
		const live = section.querySelector('[data-step]:not([hidden])') || section;
		const showing = [...live.querySelectorAll('textarea, input, canvas, .os-list button, .os-to-list, .os-menu button, .os-button')].find((element) => element.getClientRects().length);
		(showing || section).focus({ preventScroll: true });
	}

	for (const button of os.querySelectorAll('[data-go]')) button.addEventListener('click', () => show(button.dataset.go));
	// Menu items that appear once the player has got that far.
	const showMenu = () => {
		for (const button of screens.home.querySelectorAll('[data-after]')) button.hidden = !progress.has(button.dataset.after);
	};
	showMenu();
	progress.listen(showMenu);

	// ------------------------------------------------------------ the clock

	const clock = os.querySelector('.os-clock');
	const tick = () => (clock.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
	tick();
	setInterval(tick, 20000);

	// ------------------------------------------------------------ logging in

	const login = os.querySelector('.os-login');
	const loginStatus = screens.lock.querySelector('.os-status');
	login.addEventListener('submit', async (event) => {
		event.preventDefault();
		const typed = login.password.value.trim().toLowerCase();
		login.password.value = '';
		if ((await sha256(typed)) === PASSWORD_SHA256) {
			loginStatus.textContent = '';
			progress.mark('unlocked');
			show('home');
		} else {
			loginStatus.textContent = typed ? 'Incorrect password.' : '';
		}
	});

	// ------------------------------------------------------------ messages

	// An open message takes the list's place; the list is one press away.
	const list = screens.messages.querySelector('.os-list');
	const toList = screens.messages.querySelector('.os-to-list');
	toList.addEventListener('click', () => {
		listMessages(null);
		focus();
	});
	const articles = [...screens.messages.querySelectorAll('article')];
	const shown = () => articles.filter((article) => !article.dataset.after || progress.has(article.dataset.after));

	function listMessages(open) {
		if (open) progress.mark(`read-${open.dataset.id}`);
		list.replaceChildren(
			...shown().map((article) => {
				const unread = !progress.has(`read-${article.dataset.id}`);
				const item = document.createElement('li');
				const button = document.createElement('button');
				button.type = 'button';
				button.innerHTML = `<span>${unread ? '•' : ''}</span><span></span><span></span>`;
				button.children[1].textContent = article.querySelector('h3').textContent;
				button.children[2].textContent = article.querySelector('.os-subject').textContent;
				button.setAttribute('aria-label', `${unread ? 'Unread. ' : ''}${button.children[1].textContent}: ${button.children[2].textContent}`);
				button.addEventListener('click', () => {
					listMessages(article);
					focus();
				});
				item.append(button);
				return item;
			}),
		);
		for (const article of articles) article.hidden = article !== open;
		list.hidden = Boolean(open);
		toList.hidden = !open;
	}

	function countUnread() {
		const unread = shown().filter((article) => !progress.has(`read-${article.dataset.id}`)).length;
		screens.home.querySelector('.os-unread').textContent = unread ? `${unread} unread message${unread > 1 ? 's' : ''}.` : 'No new messages.';
		screens.home.querySelector('[data-go="messages"]').textContent = unread ? `Messages (${unread})` : 'Messages';
	}

	// ------------------------------------------------------------ the registry

	const check = os.querySelector('.os-check');
	const result = screens.registry.querySelector('.os-result');
	const records = Object.fromEntries([...screens.registry.querySelectorAll('tr[data-call]')].map((row) => [row.dataset.call, row]));
	const goat = screens.registry.querySelector('.os-goat');
	const recent = screens.registry.querySelector('.os-recent');
	check.addEventListener('submit', (event) => {
		event.preventDefault();
		const call = check.call.value.trim().toUpperCase();
		if (!call) return;
		goat.hidden = true;
		recent.hidden = false;
		if (!/^[A-Z]{4}$/.test(call)) {
			result.textContent = 'Call signs are four letters.';
			return;
		}
		// The ship that came past, once it has: its number is GOAT's letters.
		if (call === 'GOAT' && progress.has('song')) {
			result.textContent = screens.registry.querySelector('.os-passing').content.textContent.trim();
			drawGoat(goat, ink);
			goat.hidden = false;
			recent.hidden = true;
			progress.mark('goat');
			return;
		}
		const row = records[call];
		result.textContent = row
			? [...row.cells].map((cell, i) => `${screens.registry.querySelectorAll('th')[i].textContent}: ${cell.textContent}`).join(' · ')
			: `No record of ${call}.`;
	});

	// ------------------------------------------------------------ settings

	const settingsStatus = screens.settings.querySelector('.os-status');
	let resetArmed = false;
	// Manual gravity control: locked until the panel under the desk is in
	// sync, then ready to enable; enabled, the lever works.
	const gravityButton = screens.settings.querySelector('[data-setting="gravity"]');
	const gravityState = screens.settings.querySelector('.os-gravity-state');
	const showGravity = () => {
		const enabled = progress.has('gravity-enabled');
		gravityButton.textContent = enabled ? 'Enabled' : 'Enable';
		gravityButton.setAttribute('aria-pressed', String(enabled));
		if (enabled) gravityState.textContent = 'Enabled. The lever by your knees works.';
		else if (progress.has('panel')) gravityState.textContent = 'Fault cleared. Ready to enable.';
	};
	showGravity();
	progress.listen(showGravity);
	// Restoring the old backup brings back the administrator's portfolio.
	const restore = screens.settings.querySelector('.os-restore');
	const restoreLines = screens.settings.dataset;
	if (progress.has('restored')) screens.settings.querySelector('.os-restore-state').textContent = restoreLines.restored;
	restore.addEventListener('submit', (event) => {
		event.preventDefault();
		if (restore.password.value.trim().toLowerCase() !== BACKUP_PASSWORD) {
			settingsStatus.textContent = restoreLines.restoreWrong;
			return;
		}
		restore.hidden = true;
		progress.mark('restored');
		screens.settings.querySelector('.os-restore-state').textContent = restoreLines.restored;
		settingsStatus.textContent = restoreLines.restoreDone;
	});
	const alerts = screens.settings.querySelector('[data-setting="alerts"]');
	const showAlerts = () => {
		const on = !progress.has('alerts-off');
		alerts.textContent = on ? 'On' : 'Off';
		alerts.setAttribute('aria-pressed', String(on));
	};
	showAlerts();
	for (const button of screens.settings.querySelectorAll('[data-setting]')) {
		button.addEventListener('click', () => {
			const setting = button.dataset.setting;
			if (setting !== 'reset') resetArmed = false;
			if (setting === 'gravity') {
				if (!progress.has('panel')) settingsStatus.textContent = "Can't enable: re-sync the control panel first.";
				else if (!progress.has('gravity-enabled')) {
					progress.mark('gravity-enabled');
					settingsStatus.textContent = 'Manual gravity control enabled.';
				}
			}
			if (setting === 'restore') {
				if (progress.has('restored')) settingsStatus.textContent = restoreLines.restored;
				else {
					restore.hidden = false;
					restore.password.focus();
					settingsStatus.textContent = restoreLines.restoreAsk;
				}
			}
			if (setting === 'alerts') {
				progress.mark('alerts-off', !progress.has('alerts-off'));
				showAlerts();
				settingsStatus.textContent = '';
			}
			if (setting === 'lock') {
				settingsStatus.textContent = '';
				show('lock');
			}
			if (setting === 'reset') {
				if (!resetArmed) {
					resetArmed = true;
					settingsStatus.textContent = 'Press Reset again to forget everything.';
				} else {
					progress.reset();
					location.reload();
				}
			}
		});
	}

	// ------------------------------------------------------------ the ship link

	// The rescue, a step at a time: free the crew's manual controls (HTML),
	// fix the units in the flight code (JavaScript), then choose what to
	// jettison. Each step is saved, so the screen shows the one you're on.
	const steps = Object.fromEntries([...screens.link.querySelectorAll('[data-step]')].map((part) => [part.dataset.step, part]));
	const showStep = () => {
		const now = !progress.has('page') ? 'page' : !progress.has('units') ? 'units' : !progress.has('saved') ? 'choice' : 'done';
		for (const [name, part] of Object.entries(steps)) part.hidden = name !== now;
	};
	showStep();
	progress.listen(showStep);

	// The page runs in a preview with no scripts of its own. Pressing its
	// manual control button, once it can be reached, hands over the ship.
	const page = steps.page.querySelector('.os-code');
	const preview = steps.page.querySelector('.os-preview');
	const pageReply = steps.page.querySelector('.os-reply');
	let edited;
	page.addEventListener('input', () => {
		clearTimeout(edited);
		edited = setTimeout(() => (preview.srcdoc = BEZEL_CSS + page.value), 300);
	});
	// Each click that misses the button gives a plainer hint than the last.
	let pageMisses = 0;
	preview.addEventListener('load', () => {
		preview.contentDocument?.addEventListener('click', (event) => {
			const button = event.target.closest('button');
			if (button && /manual/i.test(button.textContent)) return progress.mark('page');
			const { notice, hintFirst, hintLast } = steps.page.dataset;
			pageMisses += 1;
			pageReply.textContent = pageMisses === 1 ? notice : pageMisses === 2 ? hintFirst : hintLast;
		});
	});
	preview.srcdoc = BEZEL_CSS + page.value;

	// The player's own flight code, run in their own browser. Every run that
	// doesn't work counts; from the second wrong number on, the AI's reply
	// becomes a hint, plainer the third time. Errors are always shown as is.
	const flight = steps.units.querySelector('.os-code');
	const unitsReply = steps.units.querySelector('.os-reply');
	const signOff = steps.units.querySelector('[data-sign]');
	let runMisses = 0;
	steps.units.querySelector('[data-run]').addEventListener('click', () => {
		const lines = steps.units.dataset;
		signOff.hidden = true;
		let pulses;
		try {
			pulses = new Function(`${flight.value}\nreturn pulsesNeeded();`)();
		} catch (error) {
			runMisses += 1;
			unitsReply.textContent = lines.error.replace('#', error.message);
			return;
		}
		if (!Number.isFinite(pulses)) {
			runMisses += 1;
			unitsReply.textContent = lines.nan;
			return;
		}
		const right = Math.abs(pulses - FLIGHT.pulses) <= FLIGHT.pulses * FLIGHT.tolerance;
		if (!right) runMisses += 1;
		const line = right ? lines.right : runMisses >= 3 ? lines.hintLast : runMisses === 2 ? lines.hintFirst : pulses > FLIGHT.pulses ? lines.high : lines.low;
		unitsReply.textContent = line.replace('#', pulses.toLocaleString('en'));
		signOff.hidden = !right;
	});
	signOff.addEventListener('click', () => progress.mark('units'));

	// Reset puts a step's code back as it came, if an edit has gone wrong.
	for (const reset of screens.link.querySelectorAll('[data-reset]')) {
		reset.addEventListener('click', () => {
			const part = reset.closest('[data-step]');
			const code = part.querySelector('.os-code');
			code.value = code.defaultValue;
			part.querySelector('.os-reply').textContent = '';
			signOff.hidden = true;
			if (part === steps.page) preview.srcdoc = BEZEL_CSS + page.value;
			code.focus();
		});
	}

	// What to jettison: only the racks are enough without risking anyone, and
	// the AI can't break the investors' order to keep them. The player can.
	const choiceReply = steps.choice.querySelector('.os-reply');
	const jettison = steps.choice.querySelector('.os-confirm');
	for (const option of steps.choice.querySelectorAll('.os-options button')) {
		option.addEventListener('click', () => {
			choiceReply.textContent = option.dataset.reply;
			jettison.hidden = !('racks' in option.dataset);
		});
	}
	jettison.addEventListener('click', () => progress.mark('saved'));

	// ------------------------------------------------------------ Snake

	const canvas = screens.snake.querySelector('canvas');
	const score = screens.snake.querySelector('.os-score');
	const snakeStatus = screens.snake.querySelector('.os-snake-status');
	const ink = getComputedStyle(os).getPropertyValue('--ink').trim() || '#cfe9ec';
	let game = null;
	let timer = null;

	function draw() {
		const c = canvas.getContext('2d');
		const cell = canvas.width / SNAKE.columns;
		c.clearRect(0, 0, canvas.width, canvas.height);
		if (!game) return;
		c.fillStyle = ink;
		const [fx, fy] = game.food;
		c.beginPath();
		c.arc((fx + 0.5) * cell, (fy + 0.5) * cell, cell * 0.3, 0, Math.PI * 2);
		c.fill();
		for (const [x, y] of game.body) c.fillRect(x * cell + 2, y * cell + 2, cell - 4, cell - 4);
		score.textContent = `Score ${game.eaten}`;
	}

	function pause() {
		clearInterval(timer);
		timer = null;
	}

	function start() {
		game = createSnake(SNAKE.columns, SNAKE.rows);
		snakeStatus.textContent = '';
		pause();
		timer = setInterval(advance, 1000 / SNAKE.speed);
		draw();
	}

	function advance() {
		step(game);
		draw();
		if (!game.death) return;
		pause();
		// Bitten three times, then dead: three dots eaten, then the snake bites itself.
		if (game.eaten === 3 && game.death === 'self') {
			progress.mark('snake');
			snakeStatus.textContent = 'Incoming message.';
			show('messages', { open: articles.find((article) => article.dataset.id === 'major-tom') });
			return;
		}
		snakeStatus.textContent = `Game over. Score ${game.eaten}. Space to play again.`;
	}

	function steer(direction) {
		if (!game || game.death || !timer) start();
		else turn(game, direction);
	}

	canvas.addEventListener('keydown', (event) => {
		const direction = KEYS[event.key] ?? KEYS[event.key.toLowerCase()];
		if (direction) steer(direction);
		else if (event.key === ' ' && (!game || game.death || !timer)) start();
		else return;
		event.preventDefault();
	});
	canvas.addEventListener('click', () => (!game || game.death || !timer) && start());
	for (const button of screens.snake.querySelectorAll('[data-turn]')) {
		button.addEventListener('click', () => {
			steer(button.dataset.turn);
			canvas.focus({ preventScroll: true });
		});
	}
	// Swipes on touch screens.
	let swipe = null;
	canvas.addEventListener('pointerdown', (event) => (swipe = { x: event.clientX, y: event.clientY }));
	canvas.addEventListener('pointerup', (event) => {
		if (!swipe) return;
		const dx = event.clientX - swipe.x;
		const dy = event.clientY - swipe.y;
		swipe = null;
		if (Math.hypot(dx, dy) < 20) return;
		steer(Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? 'right' : 'left') : dy > 0 ? 'down' : 'up');
	});
	draw();

	show(progress.has('unlocked') ? 'home' : 'lock', { quiet: true });
	return { focus };
}
