extends CharacterBody3D
## Server-authoritative capsule movement. The locally owned camera is presentation only.

const RULES = preload("res://scripts/rules.gd")

var peer_id: int = 0
var health: int = 100
var move_axes: Vector2 = Vector2.ZERO
var desired_yaw: float = 0.0
var sprinting: bool = false
var locally_controlled: bool = false
var camera: Camera3D
var body_visual: Node3D
var flashlight: SpotLight3D
var remote_target: Vector3 = Vector3.ZERO

func _ready() -> void:
	collision_layer = 2
	collision_mask = 1 | 2 | 4

	var shape := CollisionShape3D.new()
	var capsule := CapsuleShape3D.new()
	capsule.radius = 0.34
	capsule.height = 1.8
	shape.shape = capsule
	add_child(shape)

	body_visual = Node3D.new()
	body_visual.name = "VisibleSuit"
	add_child(body_visual)

	var suit := MeshInstance3D.new()
	var suit_mesh := CapsuleMesh.new()
	suit_mesh.radius = 0.31
	suit_mesh.height = 1.65
	suit.mesh = suit_mesh
	var suit_material := StandardMaterial3D.new()
	suit_material.albedo_color = Color(0.13, 0.18, 0.21, 1.0)
	suit_material.metallic = 0.35
	suit_material.roughness = 0.65
	suit.material_override = suit_material
	body_visual.add_child(suit)

	var visor := MeshInstance3D.new()
	var visor_mesh := SphereMesh.new()
	visor_mesh.radius = 0.28
	visor_mesh.height = 0.32
	visor.mesh = visor_mesh
	visor.position = Vector3(0.0, 0.53, -0.1)
	var visor_material := StandardMaterial3D.new()
	visor_material.albedo_color = Color(0.035, 0.08, 0.09)
	visor_material.metallic = 0.7
	visor_material.roughness = 0.2
	visor_material.emission_enabled = true
	visor_material.emission = Color(0.015, 0.05, 0.06)
	visor.material_override = visor_material
	body_visual.add_child(visor)

	camera = Camera3D.new()
	camera.name = "Eyes"
	camera.position = Vector3(0.0, 0.55, 0.0)
	camera.fov = 76.0
	camera.near = 0.08
	camera.current = false
	add_child(camera)

	flashlight = SpotLight3D.new()
	flashlight.name = "Torch"
	flashlight.position = Vector3(0.19, -0.10, -0.10)
	flashlight.light_color = Color(0.80, 0.92, 1.0)
	flashlight.light_energy = 2.1
	flashlight.spot_range = 21.0
	flashlight.spot_angle = 32.0
	flashlight.shadow_enabled = true
	flashlight.visible = false
	camera.add_child(flashlight)

	remote_target = global_position
	set_locally_controlled(locally_controlled)

func set_locally_controlled(value: bool) -> void:
	locally_controlled = value
	if camera != null:
		camera.current = value
		body_visual.visible = not value
		flashlight.visible = value

func set_local_pitch(pitch: float) -> void:
	if camera != null:
		camera.rotation.x = clampf(pitch, -1.4, 1.4)

func toggle_flashlight() -> void:
	if locally_controlled and flashlight != null:
		flashlight.visible = not flashlight.visible

func accept_intent(axes: Vector2, new_yaw: float, run: bool) -> void:
	move_axes = axes
	desired_yaw = new_yaw
	sprinting = run

func authoritative_step(delta: float) -> void:
	rotation.y = desired_yaw
	var direction: Vector3 = Vector3(move_axes.x, 0.0, move_axes.y).rotated(Vector3.UP, desired_yaw)
	var speed: float = RULES.RUN_SPEED if sprinting else RULES.WALK_SPEED
	velocity.x = direction.x * speed
	velocity.z = direction.z * speed
	velocity.y -= 24.0 * delta
	move_and_slide()

func take_damage(points: int) -> bool:
	health = maxi(0, health - maxi(points, 0))
	return health <= 0

func respawn(at_position: Vector3) -> void:
	health = 100
	velocity = Vector3.ZERO
	global_position = at_position
	remote_target = at_position

func snapshot() -> Dictionary:
	return {
		"id": peer_id,
		"position": global_position,
		"yaw": rotation.y,
		"health": health
	}
