// The rules of Snake, kept apart from drawing and keys so they can be
// checked on their own. The snake starts three long, moving right; it grows
// by one for each dot it eats, and dies by hitting the wall or biting itself.

export const DIRECTIONS = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] };
const OPPOSITE = { up: 'down', down: 'up', left: 'right', right: 'left' };

export function createSnake(columns, rows, random = Math.random) {
	const middle = Math.floor(rows / 2);
	const game = {
		columns,
		rows,
		random,
		body: [
			[4, middle],
			[3, middle],
			[2, middle],
		],
		heading: 'right',
		// Turns pressed faster than the snake moves wait their turn, two at most.
		turns: [],
		food: null,
		eaten: 0,
		// null while it's alive; then 'wall' or 'self'.
		death: null,
	};
	placeFood(game);
	return game;
}

function placeFood(game) {
	const taken = new Set(game.body.map(([x, y]) => `${x},${y}`));
	const free = [];
	for (let x = 0; x < game.columns; x++) {
		for (let y = 0; y < game.rows; y++) if (!taken.has(`${x},${y}`)) free.push([x, y]);
	}
	game.food = free[Math.floor(game.random() * free.length)];
}

export function turn(game, direction) {
	const last = game.turns.at(-1) ?? game.heading;
	if (direction !== last && direction !== OPPOSITE[last] && game.turns.length < 2) game.turns.push(direction);
}

export function step(game) {
	if (game.death) return;
	if (game.turns.length) game.heading = game.turns.shift();
	const [dx, dy] = DIRECTIONS[game.heading];
	const head = [game.body[0][0] + dx, game.body[0][1] + dy];
	if (head[0] < 0 || head[1] < 0 || head[0] >= game.columns || head[1] >= game.rows) {
		game.death = 'wall';
		return;
	}
	const eating = head[0] === game.food[0] && head[1] === game.food[1];
	// The tail moves on as the head moves, unless the snake is growing.
	const body = eating ? game.body : game.body.slice(0, -1);
	if (body.some(([x, y]) => x === head[0] && y === head[1])) {
		game.death = 'self';
		return;
	}
	game.body = [head, ...body];
	if (eating) {
		game.eaten += 1;
		placeFood(game);
	}
}
