extends CharacterBody3D
## One authoritative stalker. First slice deliberately uses basic perception and steering.

const ALERT_DISTANCE: float = 11.5
const ATTACK_DISTANCE: float = 1.65
const ATTACK_COOLDOWN: float = 1.6
const SPEED: float = 2.65

var attack_wait: float = 0.0
var patrol_phase: float = 0.0
var state: String = "PATROL"
var target_position: Vector3 = Vector3.ZERO
var visual: Node3D

func _ready() -> void:
	collision_layer = 4
	collision_mask = 1 | 2
	var shape := CollisionShape3D.new()
	var capsule := CapsuleShape3D.new()
	capsule.radius = 0.44
	capsule.height = 2.1
	shape.shape = capsule
	add_child(shape)

	visual = Node3D.new()
	add_child(visual)
	var torso := MeshInstance3D.new()
	var mesh := CapsuleMesh.new()
	mesh.height = 2.15
	mesh.radius = 0.39
	torso.mesh = mesh
	var skin := StandardMaterial3D.new()
	skin.albedo_color = Color(0.22, 0.09, 0.10)
	skin.roughness = 0.85
	skin.metallic = 0.08
	torso.material_override = skin
	visual.add_child(torso)

	var eye_material := StandardMaterial3D.new()
	eye_material.albedo_color = Color(0.5, 0.02, 0.015)
	eye_material.emission_enabled = true
	eye_material.emission = Color(0.95, 0.025, 0.015)
	eye_material.emission_energy_multiplier = 1.8

	for x_offset in [-0.16, 0.16]:
		var eye := MeshInstance3D.new()
		var orb := SphereMesh.new()
		orb.radius = 0.055
		orb.height = 0.11
		eye.mesh = orb
		eye.material_override = eye_material
		eye.position = Vector3(x_offset, 0.49, -0.37)
		visual.add_child(eye)

	for i in range(5):
		var spine := MeshInstance3D.new()
		var cone := CylinderMesh.new()
		cone.top_radius = 0.0
		cone.bottom_radius = 0.17
		cone.height = 0.4
		spine.mesh = cone
		spine.material_override = skin
		spine.position = Vector3(0.0, 0.72 - i * 0.34, 0.33)
		spine.rotation.x = 0.9
		visual.add_child(spine)
	target_position = global_position

func authoritative_step(delta: float, players: Dictionary) -> int:
	attack_wait = maxf(0.0, attack_wait - delta)
	patrol_phase += delta
	var victim_id: int = -1
	var nearest_distance: float = ALERT_DISTANCE

	for id in players.keys():
		var survivor: CharacterBody3D = players[id]
		var distance: float = global_position.distance_to(survivor.global_position)
		if distance < nearest_distance and _can_see(survivor):
			nearest_distance = distance
			victim_id = id

	var direction := Vector3.ZERO
	if victim_id != -1:
		state = "STALKING"
		var victim: CharacterBody3D = players[victim_id]
		direction = victim.global_position - global_position
		direction.y = 0.0
		if direction.length() > 0.01:
			direction = direction.normalized()
			rotation.y = atan2(-direction.x, -direction.z)
	else:
		state = "PATROL"
		var destination := Vector3(sin(patrol_phase * 0.28) * 2.2, 1.13, -3.5 + cos(patrol_phase * 0.28) * 2.0)
		direction = destination - global_position
		direction.y = 0.0
		if direction.length() > 0.7:
			direction = direction.normalized()
			rotation.y = atan2(-direction.x, -direction.z)
		else:
			direction = Vector3.ZERO

	velocity.x = direction.x * SPEED
	velocity.z = direction.z * SPEED
	velocity.y -= 24.0 * delta
	move_and_slide()
	visual.position.y = sin(patrol_phase * 6.0) * 0.04

	if victim_id != -1 and nearest_distance < ATTACK_DISTANCE and attack_wait <= 0.0:
		state = "STRIKING"
		attack_wait = ATTACK_COOLDOWN
		return victim_id
	return -1

func _can_see(target: CharacterBody3D) -> bool:
	var start := global_position + Vector3(0.0, 0.45, 0.0)
	var finish := target.global_position + Vector3(0.0, 0.35, 0.0)
	var query := PhysicsRayQueryParameters3D.create(start, finish)
	query.exclude = [get_rid()]
	query.collision_mask = 1 | 2
	var hit: Dictionary = get_world_3d().direct_space_state.intersect_ray(query)
	return hit.is_empty() or hit.get("collider") == target

func snapshot() -> Dictionary:
	return {
		"position": global_position,
		"yaw": rotation.y,
		"state": state
	}
