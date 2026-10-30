extends Node3D
## ANEVUM / SEVERANCE Prototype 001.
## One scene shared by the offline client, WebSocket client and headless server.
## Production website/authentication/payment boundaries remain untouched.

const RULES = preload("res://scripts/rules.gd")
const WORLD = preload("res://scripts/world.gd")
const SURVIVOR = preload("res://scripts/survivor.gd")
const CREATURE = preload("res://scripts/creature.gd")

var world: Node3D
var survivor_root: Node3D
var creature: CharacterBody3D
var players: Dictionary = {}
var mode: String = "menu" # menu | solo | client | server
var local_peer_id: int = 0
var local_yaw: float = 0.0
var local_pitch: float = 0.0
var send_elapsed: float = 0.0
var snapshot_elapsed: float = 0.0
var visual_status_elapsed: float = 0.0
var debug_probe: bool = false
var probe_snapshots: int = 0
var session_events: Array[String] = []
var gui_layer: CanvasLayer
var menu_panel: PanelContainer
var endpoint_field: LineEdit
var menu_message: Label
var hud_root: Control
var hud_status: Label
var hud_objective: Label
var hud_net: Label
var last_server_input_ms: Dictionary = {}
var server_port: int = RULES.PORT
var server_bind: String = "127.0.0.1"

func _set_web_probe_phase(phase: String) -> void:
	# Read-only test signal for the isolated browser build; not a public game API.
	if OS.has_feature("web"):
		JavaScriptBridge.eval("window.__severancePrototypePhase = " + JSON.stringify(phase) + ";", true)

func _ready() -> void:
	_register_actions()

	world = WORLD.new()
	world.name = "Compound"
	add_child(world)

	survivor_root = Node3D.new()
	survivor_root.name = "Survivors"
	add_child(survivor_root)

	creature = CREATURE.new()
	creature.name = "PrototypeStalker"
	creature.position = Vector3(0.0, 1.13, -3.5)
	add_child(creature)

	multiplayer.peer_connected.connect(_on_peer_joined)
	multiplayer.peer_disconnected.connect(_on_peer_left)
	multiplayer.connected_to_server.connect(_on_connected)
	multiplayer.connection_failed.connect(_on_connection_failed)
	multiplayer.server_disconnected.connect(_on_server_disconnected)

	if DisplayServer.get_name() != "headless":
		_build_interface()
		_set_web_probe_phase("menu")

	var args: PackedStringArray = OS.get_cmdline_user_args()
	for argument in args:
		if argument.begins_with("--port="):
			server_port = clampi(int(argument.trim_prefix("--port=")), 1024, 65535)
		elif argument.begins_with("--bind="):
			server_bind = argument.trim_prefix("--bind=")

	if "--server" in args:
		_start_dedicated_server()
	elif "--probe-client" in args:
		debug_probe = true
		var url: String = "ws://127.0.0.1:%s" % server_port
		for argument in args:
			if argument.begins_with("--endpoint="):
				url = argument.trim_prefix("--endpoint=")
		_connect_to_server(url)
	elif "--solo" in args:
		_start_solo()

func _register_actions() -> void:
	_add_key("move_forward", KEY_W)
	_add_key("move_backward", KEY_S)
	_add_key("move_left", KEY_A)
	_add_key("move_right", KEY_D)
	_add_key("sprint", KEY_SHIFT)
	_add_key("interact", KEY_E)
	_add_key("torch", KEY_F)
	_add_key("release_mouse", KEY_ESCAPE)

func _add_key(action: String, physical_code: Key) -> void:
	if not InputMap.has_action(action):
		InputMap.add_action(action)
	var key := InputEventKey.new()
	key.physical_keycode = physical_code
	if not InputMap.action_has_event(action, key):
		InputMap.action_add_event(action, key)

func _start_solo() -> void:
	if mode != "menu":
		return
	mode = "solo"
	local_yaw = PI # Face toward the exit, not the compound rear wall.
	local_peer_id = 1
	_spawn_survivor(local_peer_id)
	_enter_game()
	_set_web_probe_phase("solo")
	_note("LOCAL PROTOTYPE — NO ONLINE SERVER")

func _start_dedicated_server() -> void:
	if mode != "menu":
		return
	var peer := WebSocketMultiplayerPeer.new()
	var error: Error = peer.create_server(server_port, server_bind)
	if error != OK:
		push_error("SEVERANCE_SERVER_ERROR %s" % error_string(error))
		if "--server" in OS.get_cmdline_user_args():
			get_tree().quit(2)
		return
	multiplayer.multiplayer_peer = peer
	mode = "server"
	world.load_server_state()
	print("SEVERANCE_SERVER_READY ws://%s:%s" % [server_bind, server_port])

func _on_join_pressed() -> void:
	if endpoint_field == null:
		return
	_connect_to_server(endpoint_field.text)

func _connect_to_server(raw_url: String) -> void:
	if mode != "menu":
		return
	var url: String = raw_url.strip_edges()
	if not RULES.valid_endpoint(url):
		_show_error("Enter a ws:// or wss:// WebSocket address.")
		if debug_probe:
			get_tree().quit(3)
		return
	if OS.has_feature("web") and url.begins_with("ws://") and JavaScriptBridge.eval("location.protocol") == "https:":
		_show_error("HTTPS browser pages require a secure wss:// endpoint.")
		if debug_probe:
			get_tree().quit(3)
		return
	var peer := WebSocketMultiplayerPeer.new()
	var error: Error = peer.create_client(url)
	if error != OK:
		_show_error("Connection refused before handshake: %s" % error_string(error))
		if debug_probe:
			get_tree().quit(3)
		return
	mode = "connecting"
	multiplayer.multiplayer_peer = peer
	_show_error("Connecting to %s ..." % url)

func _on_connected() -> void:
	if mode != "connecting":
		return
	local_peer_id = multiplayer.get_unique_id()
	local_yaw = PI # Correct forward-facing view for the network client.
	mode = "client"
	_enter_game()
	_set_web_probe_phase("client")
	_note("Connected to isolated test server. No player accounts enabled.")
	print("SEVERANCE_CLIENT_CONNECTED %s" % local_peer_id)

func _on_connection_failed() -> void:
	_return_to_menu("Could not connect. Check server and WebSocket URL.")
	if debug_probe:
		get_tree().quit(4)

func _on_server_disconnected() -> void:
	_return_to_menu("Server disconnected. World state is not locally authoritative.")
	if debug_probe:
		get_tree().quit(5)

func _return_to_menu(reason: String) -> void:
	mode = "menu"
	_set_web_probe_phase("menu")
	local_peer_id = 0
	for id in players.keys():
		var survivor: Node = players[id]
		survivor.queue_free()
	players.clear()
	multiplayer.multiplayer_peer = OfflineMultiplayerPeer.new()
	if DisplayServer.get_name() != "headless":
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	if menu_panel != null:
		menu_panel.visible = true
	if hud_root != null:
		hud_root.visible = false
	_show_error(reason)

func _on_peer_joined(id: int) -> void:
	if mode != "server":
		return
	if players.size() >= RULES.MAX_PLAYERS:
		multiplayer.multiplayer_peer.disconnect_peer(id)
		return
	_spawn_survivor(id)
	_note("TEST SURVIVOR %s CONNECTED" % id)
	_send_snapshot()

func _on_peer_left(id: int) -> void:
	if mode != "server":
		return
	if players.has(id):
		var avatar: Node = players[id]
		players.erase(id)
		avatar.queue_free()
		last_server_input_ms.erase(id)
		_note("TEST SURVIVOR %s DISCONNECTED" % id)

func _spawn_survivor(id: int) -> CharacterBody3D:
	if players.has(id):
		return players[id]
	var avatar: CharacterBody3D = SURVIVOR.new()
	avatar.peer_id = id
	avatar.name = "Survivor_%s" % id
	avatar.position = RULES.spawn_point(players.size())
	survivor_root.add_child(avatar)
	players[id] = avatar
	avatar.remote_target = avatar.global_position
	if id == local_peer_id:
		avatar.set_locally_controlled(true)
		avatar.rotation.y = local_yaw
		avatar.set_local_pitch(local_pitch)
	return avatar

func _enter_game() -> void:
	if menu_panel != null:
		menu_panel.visible = false
	if hud_root != null:
		hud_root.visible = true
	if DisplayServer.get_name() != "headless":
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED

func _physics_process(delta: float) -> void:
	if mode == "server" or mode == "solo":
		if mode == "solo":
			_read_local_input()
		for id in players.keys():
			var avatar: CharacterBody3D = players[id]
			avatar.authoritative_step(delta)
		var attacked_peer: int = creature.authoritative_step(delta, players)
		if attacked_peer > 0 and players.has(attacked_peer):
			_damage_player(attacked_peer, 34)
		if mode == "server":
			snapshot_elapsed += delta
			if snapshot_elapsed >= RULES.SNAPSHOT_INTERVAL_SECONDS:
				snapshot_elapsed = 0.0
				_send_snapshot()
	elif mode == "client":
		send_elapsed += delta
		if send_elapsed >= RULES.INPUT_INTERVAL_SECONDS:
			send_elapsed = 0.0
			_send_local_intent()

	if (mode == "client" or mode == "solo") and Input.is_action_just_pressed("interact"):
		if mode == "solo":
			_try_collect(local_peer_id)
		else:
			request_collect.rpc_id(1)
	if (mode == "client" or mode == "solo") and Input.is_action_just_pressed("torch"):
		if players.has(local_peer_id):
			players[local_peer_id].toggle_flashlight()

func _read_local_input() -> void:
	if not players.has(local_peer_id):
		return
	var axes: Vector2 = Input.get_vector("move_left", "move_right", "move_forward", "move_backward")
	players[local_peer_id].accept_intent(axes, local_yaw, Input.is_action_pressed("sprint"))

func _send_local_intent() -> void:
	var axes: Vector2 = Input.get_vector("move_left", "move_right", "move_forward", "move_backward")
	send_intent.rpc_id(1, axes.x, axes.y, local_yaw, Input.is_action_pressed("sprint"))

@rpc("any_peer", "call_remote", "unreliable_ordered")
func send_intent(x: float, y: float, yaw: float, running: bool) -> void:
	if mode != "server" or not multiplayer.is_server():
		return
	var sender: int = multiplayer.get_remote_sender_id()
	if not players.has(sender):
		return
	var now: int = Time.get_ticks_msec()
	if now - int(last_server_input_ms.get(sender, -1000)) < 15:
		return
	last_server_input_ms[sender] = now
	players[sender].accept_intent(RULES.normalized_axes(x, y), RULES.sanitized_yaw(yaw), running)

@rpc("any_peer", "call_remote", "reliable")
func request_collect() -> void:
	if mode != "server" or not multiplayer.is_server():
		return
	_try_collect(multiplayer.get_remote_sender_id())

func _try_collect(sender: int) -> void:
	if not players.has(sender):
		return
	var avatar: CharacterBody3D = players[sender]
	var identifier: String = world.collect_nearest(avatar.global_position, RULES.INTERACT_RADIUS)
	if identifier.is_empty():
		return
	_note("EVIDENCE SECURED: %s" % identifier)
	if mode == "server":
		if not world.save_server_state():
			push_warning("Prototype world could not be persisted to server disk.")
		_send_snapshot()

func _damage_player(id: int, points: int) -> void:
	if not players.has(id):
		return
	var avatar: CharacterBody3D = players[id]
	if avatar.take_damage(points):
		avatar.respawn(RULES.spawn_point(int(id) % RULES.MAX_PLAYERS))
		_note("SURVIVOR %s REDEPLOYED — DEATH / RETURN TEST" % id)

func _send_snapshot() -> void:
	if mode != "server" or players.is_empty():
		return
	var records: Array = []
	for id in players.keys():
		records.append(players[id].snapshot())
	receive_snapshot.rpc(records, creature.snapshot(), world.recovered_ids())

@rpc("authority", "call_remote", "unreliable_ordered")
func receive_snapshot(records: Array, creature_record: Dictionary, recovered_ids: Array) -> void:
	if mode != "client":
		return
	var live_ids: Dictionary = {}
	for record in records:
		if not record is Dictionary:
			continue
		var id: int = int(record.get("id", 0))
		if id <= 0 or id in live_ids:
			continue
		live_ids[id] = true
		var avatar: CharacterBody3D = _spawn_survivor(id)
		var target: Variant = record.get("position", Vector3.ZERO)
		if target is Vector3:
			if avatar.remote_target == Vector3.ZERO or avatar.global_position.distance_to(target) > 20.0:
				avatar.global_position = target
			avatar.remote_target = target
		avatar.health = clampi(int(record.get("health", 100)), 0, 100)
		if id != local_peer_id:
			avatar.rotation.y = float(record.get("yaw", 0.0))
	for id in players.keys():
		if not live_ids.has(id):
			var old_avatar: Node = players[id]
			players.erase(id)
			old_avatar.queue_free()

	var creature_position: Variant = creature_record.get("position", Vector3.ZERO)
	if creature_position is Vector3:
		creature.target_position = creature_position
	creature.state = str(creature_record.get("state", "PATROL"))
	world.set_recovered_ids(recovered_ids)
	probe_snapshots += 1
	if debug_probe and probe_snapshots >= 4 and players.has(local_peer_id):
		print("SEVERANCE_PROBE_PASS player=%s packets=%s world_samples=%s" % [local_peer_id, probe_snapshots, world.remaining_samples()])
		get_tree().quit(0)

func _process(delta: float) -> void:
	if mode == "client":
		for id in players.keys():
			var avatar: CharacterBody3D = players[id]
			avatar.global_position = avatar.global_position.lerp(avatar.remote_target, minf(1.0, delta * 13.0))
		creature.global_position = creature.global_position.lerp(creature.target_position, minf(1.0, delta * 11.0))
	visual_status_elapsed += delta
	if visual_status_elapsed > 0.20:
		visual_status_elapsed = 0.0
		_refresh_hud()

func _unhandled_input(event: InputEvent) -> void:
	if mode != "solo" and mode != "client":
		return
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		local_yaw = RULES.sanitized_yaw(local_yaw - event.relative.x * 0.00235)
		local_pitch = clampf(local_pitch - event.relative.y * 0.00235, -1.36, 1.36)
		if players.has(local_peer_id):
			var avatar: CharacterBody3D = players[local_peer_id]
			avatar.rotation.y = local_yaw
			avatar.set_local_pitch(local_pitch)
	elif event.is_action_pressed("release_mouse"):
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	elif event is InputEventMouseButton and event.pressed and Input.mouse_mode == Input.MOUSE_MODE_VISIBLE:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED

func _note(message: String) -> void:
	session_events.append(message)
	if session_events.size() > 6:
		session_events.pop_front()
	print("SEVERANCE_EVENT %s" % message)

func _show_error(message: String) -> void:
	if menu_message != null:
		menu_message.text = message
	if DisplayServer.get_name() == "headless":
		print("SEVERANCE_CONNECTION %s" % message)

func _refresh_hud() -> void:
	if hud_root == null or not hud_root.visible:
		return
	var health: int = 100
	if players.has(local_peer_id):
		health = players[local_peer_id].health
	hud_status.text = "SEVERANCE / COMPOUND 001     HEALTH %03d" % health
	hud_objective.text = "RECOVER 3 DATA CASES  [E]     %s / 3 RECOVERED\nSTALKER: %s\nWASD MOVE   SHIFT RUN   F LIGHT   ESC CURSOR" % [RULES.MAX_SAMPLE_COUNT - world.remaining_samples(), creature.state]
	hud_net.text = ("LOCAL / SOLO" if mode == "solo" else "NETWORK TEST / %s" % local_peer_id)
	if not session_events.is_empty():
		hud_net.text += "\n" + session_events[-1]

func _build_interface() -> void:
	gui_layer = CanvasLayer.new()
	gui_layer.name = "Interface"
	gui_layer.layer = 4
	add_child(gui_layer)
	var screen := Control.new()
	screen.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	screen.mouse_filter = Control.MOUSE_FILTER_IGNORE
	gui_layer.add_child(screen)

	hud_root = Control.new()
	hud_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	hud_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	screen.add_child(hud_root)

	hud_status = Label.new()
	hud_status.position = Vector2(24, 20)
	hud_status.add_theme_font_size_override("font_size", 19)
	hud_status.modulate = Color(0.79, 0.90, 0.91)
	hud_root.add_child(hud_status)

	hud_objective = Label.new()
	hud_objective.anchor_top = 1.0
	hud_objective.anchor_bottom = 1.0
	hud_objective.offset_left = 24
	hud_objective.offset_top = -108
	hud_objective.offset_bottom = -16
	hud_objective.add_theme_font_size_override("font_size", 15)
	hud_objective.modulate = Color(0.78, 0.88, 0.90)
	hud_root.add_child(hud_objective)

	var crosshair := Label.new()
	crosshair.text = "+"
	crosshair.anchor_left = 0.5
	crosshair.anchor_right = 0.5
	crosshair.anchor_top = 0.5
	crosshair.anchor_bottom = 0.5
	crosshair.offset_left = -7
	crosshair.offset_top = -16
	crosshair.add_theme_font_size_override("font_size", 28)
	crosshair.modulate = Color(0.89, 0.30, 0.26, 0.85)
	hud_root.add_child(crosshair)

	hud_net = Label.new()
	hud_net.anchor_left = 1.0
	hud_net.anchor_right = 1.0
	hud_net.offset_left = -380
	hud_net.offset_right = -24
	hud_net.offset_top = 24
	hud_net.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	hud_net.modulate = Color(0.70, 0.77, 0.79)
	hud_root.add_child(hud_net)
	hud_root.visible = false

	menu_panel = PanelContainer.new()
	menu_panel.name = "SeveranceTitle"
	menu_panel.anchor_left = 0.5
	menu_panel.anchor_top = 0.5
	menu_panel.anchor_right = 0.5
	menu_panel.anchor_bottom = 0.5
	menu_panel.offset_left = -245
	menu_panel.offset_top = -200
	menu_panel.offset_right = 245
	menu_panel.offset_bottom = 200
	var panel_style := StyleBoxFlat.new()
	panel_style.bg_color = Color(0.022, 0.030, 0.041, 0.97)
	panel_style.border_color = Color(0.42, 0.11, 0.11)
	panel_style.set_border_width_all(2)
	panel_style.set_corner_radius_all(9)
	menu_panel.add_theme_stylebox_override("panel", panel_style)
	screen.add_child(menu_panel)

	var padding := MarginContainer.new()
	for margin_name in ["margin_left", "margin_right", "margin_top", "margin_bottom"]:
		padding.add_theme_constant_override(margin_name, 25)
	menu_panel.add_child(padding)
	var stack := VBoxContainer.new()
	stack.add_theme_constant_override("separation", 14)
	padding.add_child(stack)

	var label := Label.new()
	label.text = "T R A N S C O S M I C"
	label.add_theme_font_size_override("font_size", 17)
	label.modulate = Color(0.65, 0.77, 0.80)
	stack.add_child(label)

	var title := Label.new()
	title.text = "S E V E R A N C E"
	title.add_theme_font_size_override("font_size", 31)
	title.modulate = Color(0.93, 0.87, 0.82)
	stack.add_child(title)

	var details := Label.new()
	details.text = "PROTOTYPE 001 / QUARANTINED COMPOUND\nDeveloper test: 3 data cases, 1 stalker, server-controlled survival.\nThis is not a public beta."
	details.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	details.modulate = Color(0.70, 0.76, 0.77)
	stack.add_child(details)

	var solo_button := Button.new()
	solo_button.text = "SOLO TEST / START"
	solo_button.custom_minimum_size.y = 43.0
	solo_button.pressed.connect(_start_solo)
	stack.add_child(solo_button)

	endpoint_field = LineEdit.new()
	endpoint_field.text = "ws://127.0.0.1:%s" % RULES.PORT
	endpoint_field.placeholder_text = "wss://your-secure-test-server.example"
	stack.add_child(endpoint_field)

	var join_button := Button.new()
	join_button.text = "CONNECT TO PRIVATE TEST SERVER"
	join_button.custom_minimum_size.y = 43.0
	join_button.pressed.connect(_on_join_pressed)
	stack.add_child(join_button)

	menu_message = Label.new()
	menu_message.text = "WASD MOVE  /  MOUSE LOOK  /  E COLLECT  /  F FLASHLIGHT"
	menu_message.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	menu_message.modulate = Color(0.70, 0.70, 0.75)
	stack.add_child(menu_message)
