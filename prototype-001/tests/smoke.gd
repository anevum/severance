extends SceneTree
## CI smoke: parse/load the actual scene, exercise rules, creature, evidence, and solo.

const RULES = preload("res://scripts/rules.gd")
const MAIN_SCENE = preload("res://scenes/main.tscn")
var failures: Array[String] = []

func _initialize() -> void:
	call_deferred("_run")

func _expect(condition: bool, label: String) -> void:
	if condition:
		print("SEVERANCE_TEST_PASS " + label)
	else:
		failures.append(label)
		push_error("SEVERANCE_TEST_FAIL " + label)

func _run() -> void:
	_expect(RULES.normalized_axes(4.0, 4.0).length() <= 1.0001, "movement normalization")
	_expect(RULES.normalized_axes(0.0, -1.0) == Vector2(0.0, -1.0), "forward direction")
	_expect(RULES.valid_endpoint("ws://127.0.0.1:8910"), "local websocket")
	_expect(RULES.valid_endpoint("wss://game.example.test/connect"), "secure websocket")
	_expect(not RULES.valid_endpoint("https://example.test"), "reject non websocket")
	_expect(RULES.spawn_point(0) != RULES.spawn_point(1), "distinct spawn slots")

	var game: Node3D = MAIN_SCENE.instantiate()
	root.add_child(game)
	await process_frame
	_expect(game.world != null, "world constructed")
	_expect(game.creature != null, "creature constructed")
	_expect(game.world.remaining_samples() == 3, "three evidence cases")
	_expect(game.mode == "menu", "no automatic public session")

	game._start_solo()
	await process_frame
	_expect(game.mode == "solo", "offline test mode")
	_expect(absf(game.local_yaw - PI) < 0.01, "survivor starts facing the traversable compound exit")
	_expect(game.players.has(1), "solo survivor spawned")

	if game.players.has(1):
		var survivor: CharacterBody3D = game.players[1]
		_expect(survivor.health == 100, "survivor initial health")
		survivor.global_position = Vector3(1.0, 1.03, -12.0)
		game._try_collect(1)
		_expect(game.world.remaining_samples() == 2, "server-rule collection radius")
		game._try_collect(1)
		_expect(game.world.remaining_samples() == 2, "evidence cannot be duplicated")
		game._damage_player(1, 200)
		_expect(survivor.health == 100, "fatal damage causes a controlled respawn")
		_expect(survivor.global_position.distance_to(RULES.spawn_point(1)) < 0.01, "respawn point validated")

	game.queue_free()
	if failures.is_empty():
		print("SEVERANCE_SMOKE_PASS")
		quit(0)
	else:
		print("SEVERANCE_SMOKE_FAIL count=%s" % failures.size())
		quit(1)
