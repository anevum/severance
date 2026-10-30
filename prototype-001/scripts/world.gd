extends Node3D
## Original modular graybox compound; geometry is generated, not remotely downloaded.
## Only the dedicated server / offline test may load or write durable state.

const SAVE_PATH: String = "user://severance-prototype-001-world.json"
const SAMPLE_POINTS := {
	"LAB-01": Vector3(1.0, 0.65, -12.0),
	"YARD-02": Vector3(7.3, 0.65, 8.0),
	"PERIMETER-03": Vector3(-8.0, 0.65, 16.0)
}

var recovered: Dictionary = {}
var sample_nodes: Dictionary = {}
var concrete: StandardMaterial3D
var metal: StandardMaterial3D
var dark_metal: StandardMaterial3D
var rust: StandardMaterial3D

func _ready() -> void:
	concrete = _material(Color(0.20, 0.23, 0.24), 0.08, 0.90)
	metal = _material(Color(0.25, 0.30, 0.31), 0.72, 0.38)
	dark_metal = _material(Color(0.095, 0.12, 0.14), 0.62, 0.60)
	rust = _material(Color(0.33, 0.10, 0.08), 0.35, 0.88)
	_make_environment()
	_make_architecture()
	_make_props()
	_make_samples()

func _material(color: Color, metallic_value: float, roughness_value: float) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.metallic = metallic_value
	material.roughness = roughness_value
	return material

func _box(name_text: String, at: Vector3, size: Vector3, material: Material, collides: bool = true) -> Node3D:
	var holder: Node3D = StaticBody3D.new() if collides else Node3D.new()
	holder.name = name_text
	holder.position = at
	add_child(holder)
	if collides:
		(holder as StaticBody3D).collision_layer = 1
		(holder as StaticBody3D).collision_mask = 0
		var collider := CollisionShape3D.new()
		var shape := BoxShape3D.new()
		shape.size = size
		collider.shape = shape
		holder.add_child(collider)
	var visual := MeshInstance3D.new()
	var cube := BoxMesh.new()
	cube.size = size
	visual.mesh = cube
	visual.material_override = material
	holder.add_child(visual)
	return holder

func _make_environment() -> void:
	var world_env := WorldEnvironment.new()
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.012, 0.022, 0.030)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.18, 0.29, 0.33)
	env.ambient_light_energy = 0.54
	world_env.environment = env
	add_child(world_env)

	var moon := DirectionalLight3D.new()
	moon.name = "ColdMoon"
	moon.rotation_degrees = Vector3(-52, -32, 0)
	moon.light_color = Color(0.40, 0.61, 0.72)
	moon.light_energy = 0.22
	moon.shadow_enabled = false
	add_child(moon)

	_omni("EntranceSodium", Vector3(0, 3.6, -21), Color(0.70, 0.82, 0.85), 0.95, 11.0)
	_omni("LabEmergency", Vector3(0, 3.4, -9.0), Color(1.00, 0.10, 0.09), 1.65, 10.0)
	_omni("LabOverheadA", Vector3(0, 4.6, -25.0), Color(0.66, 0.86, 0.94), 1.15, 8.0)
	_omni("LabOverheadB", Vector3(0, 4.6, -17.2), Color(0.66, 0.86, 0.94), 0.90, 8.0)
	_omni("LabOverheadC", Vector3(0, 4.6, -13.0), Color(0.76, 0.90, 0.96), 0.85, 8.0)
	_omni("ExitEmergency", Vector3(0, 3.2, -1.7), Color(0.80, 0.09, 0.09), 1.25, 9.0)
	_omni("YardFloodlight", Vector3(7, 5, 7), Color(0.67, 0.83, 0.87), 1.3, 14.0)
	_omni("FenceFloodlight", Vector3(-10, 5, 15), Color(0.61, 0.79, 0.83), 0.95, 12.0)

func _omni(name_text: String, at: Vector3, color: Color, energy: float, radius: float) -> void:
	var lamp := OmniLight3D.new()
	lamp.name = name_text
	lamp.position = at
	lamp.light_color = color
	lamp.light_energy = energy
	lamp.omni_range = radius
	lamp.shadow_enabled = false
	add_child(lamp)

func _make_architecture() -> void:
	_box("GroundSlab", Vector3(0, -0.33, -3), Vector3(30, 0.65, 54), concrete)
	_box("NorthFence", Vector3(0, 1.8, 23.6), Vector3(30, 3.6, 0.5), dark_metal)
	_box("WestFence", Vector3(-14.7, 1.8, -3), Vector3(0.5, 3.6, 54), dark_metal)
	_box("EastFence", Vector3(14.7, 1.8, -3), Vector3(0.5, 3.6, 54), dark_metal)
	_box("RearLabWall", Vector3(0, 2.7, -29.5), Vector3(11.2, 5.4, 0.5), concrete)
	_box("LabWestWall", Vector3(-5.4, 2.7, -16.3), Vector3(0.55, 5.4, 26.5), concrete)
	_box("LabEastWall", Vector3(5.4, 2.7, -16.3), Vector3(0.55, 5.4, 26.5), concrete)
	_box("LabCeiling", Vector3(0, 5.43, -16.3), Vector3(11.2, 0.45, 26.5), dark_metal)
	_box("ExitWallWest", Vector3(-3.7, 2.7, -3.0), Vector3(3.5, 5.4, 0.5), metal)
	_box("ExitWallEast", Vector3(3.7, 2.7, -3.0), Vector3(3.5, 5.4, 0.5), metal)
	_box("ExitLintel", Vector3(0, 4.25, -3.0), Vector3(4.1, 2.3, 0.5), metal)
	_box("FloorTreadWest", Vector3(-3.1, 0.015, -13), Vector3(0.25, 0.03, 23), rust, false)
	_box("FloorTreadEast", Vector3(3.1, 0.015, -13), Vector3(0.25, 0.03, 23), rust, false)
	for i in range(6):
		var z: float = -27.0 + float(i) * 4.0
		_box("CeilingRib_%s" % i, Vector3(0, 5.02, z), Vector3(10.8, 0.38, 0.50), metal)
		_box("LeftPipe_%s" % i, Vector3(-4.7, 3.4, z), Vector3(0.25, 0.25, 3.5), dark_metal, false)
		_box("RightPipe_%s" % i, Vector3(4.7, 3.4, z), Vector3(0.25, 0.25, 3.5), dark_metal, false)
	for x in [-12.5, 12.5]:
		for z in [0.0, 10.0, 20.0]:
			_box("YardPillar_%s_%s" % [x, z], Vector3(x, 2.4, z), Vector3(0.7, 4.8, 0.7), concrete)

func _make_props() -> void:
	# Emissive tube fixtures make the starting corridor legible in WebGL 2
	# without requiring GPU-heavy real-time shadows.
	var lamp_material := _material(Color(0.41, 0.70, 0.79), 0.20, 0.17)
	lamp_material.emission_enabled = true
	lamp_material.emission = Color(0.28, 0.55, 0.65)
	lamp_material.emission_energy_multiplier = 2.4
	for i in range(5):
		var fixture_z: float = -25.0 + float(i) * 5.0
		_box("SuspendedLuminaire_%s" % i, Vector3(0, 4.70, fixture_z), Vector3(1.80, 0.09, 0.20), lamp_material, false)
	var warning_material := _material(Color(0.64, 0.08, 0.065), 0.25, 0.20)
	warning_material.emission_enabled = true
	warning_material.emission = Color(0.85, 0.065, 0.045)
	warning_material.emission_energy_multiplier = 2.0
	_box("ExitWarningBar", Vector3(0, 3.15, -3.32), Vector3(3.1, 0.16, 0.10), warning_material, false)

	for index in range(5):
		var z: float = -25.0 + float(index) * 4.5
		var side: float = -3.6 if index % 2 == 0 else 3.6
		_box("IndustrialRack_%s" % index, Vector3(side, 0.85, z), Vector3(1.35, 1.7, 1.4), dark_metal)
		_box("RackTrim_%s" % index, Vector3(side, 1.74, z), Vector3(1.45, 0.09, 1.48), rust, false)
	for index in range(10):
		var x: float = -11.3 + float(index % 5) * 5.2
		var z: float = 5.0 + float(index / 5) * 9.4
		if x > -4.0 and x < 4.0 and z < 10.0:
			continue
		_box("SupplyCrate_%s" % index, Vector3(x, 0.60, z), Vector3(1.3, 1.2, 1.4), metal)
		_box("CrateStripe_%s" % index, Vector3(x, 1.25, z), Vector3(1.34, 0.09, 1.44), rust, false)
	_box("GeneratorHousing", Vector3(9.5, 1.1, -1.8), Vector3(2.5, 2.2, 1.7), dark_metal)
	_box("GeneratorCore", Vector3(9.5, 1.3, -2.68), Vector3(1.4, 0.40, 0.08), rust, false)
	_box("CommsAntenna", Vector3(-11.5, 3.0, 5.0), Vector3(0.32, 6.0, 0.32), dark_metal)
	_box("CommsCrossbeam", Vector3(-11.5, 5.5, 5.0), Vector3(2.0, 0.22, 0.22), metal, false)

func _make_samples() -> void:
	var glowing := StandardMaterial3D.new()
	glowing.albedo_color = Color(0.38, 0.67, 0.72)
	glowing.metallic = 0.8
	glowing.roughness = 0.15
	glowing.emission_enabled = true
	glowing.emission = Color(0.04, 0.36, 0.47)
	glowing.emission_energy_multiplier = 1.3
	for identifier in SAMPLE_POINTS.keys():
		var marker := Node3D.new()
		marker.name = "Evidence_%s" % identifier
		marker.position = SAMPLE_POINTS[identifier]
		add_child(marker)
		var case := MeshInstance3D.new()
		var cube := BoxMesh.new()
		cube.size = Vector3(0.42, 0.27, 0.28)
		case.mesh = cube
		case.material_override = glowing
		marker.add_child(case)
		var lamp := OmniLight3D.new()
		lamp.omni_range = 2.5
		lamp.light_color = Color(0.11, 0.67, 0.74)
		lamp.light_energy = 0.8
		marker.add_child(lamp)
		sample_nodes[identifier] = marker

func collect_nearest(at: Vector3, max_distance: float) -> String:
	var closest: String = ""
	var nearest: float = max_distance
	for identifier in SAMPLE_POINTS.keys():
		if recovered.has(identifier):
			continue
		var distance: float = at.distance_to(SAMPLE_POINTS[identifier])
		if distance < nearest:
			closest = identifier
			nearest = distance
	if closest.is_empty():
		return ""
	recovered[closest] = true
	_refresh_markers()
	return closest

func set_recovered_ids(ids: Array) -> void:
	recovered.clear()
	for item in ids:
		var identifier: String = str(item)
		if SAMPLE_POINTS.has(identifier):
			recovered[identifier] = true
	_refresh_markers()

func recovered_ids() -> Array:
	var output: Array = recovered.keys()
	output.sort()
	return output

func remaining_samples() -> int:
	return SAMPLE_POINTS.size() - recovered.size()

func _refresh_markers() -> void:
	for identifier in sample_nodes.keys():
		var marker: Node3D = sample_nodes[identifier]
		marker.visible = not recovered.has(identifier)

func load_server_state() -> void:
	if not FileAccess.file_exists(SAVE_PATH):
		return
	var file := FileAccess.open(SAVE_PATH, FileAccess.READ)
	if file == null:
		return
	var contents := file.get_as_text()
	if contents.length() > 8192:
		return
	var parsed: Variant = JSON.parse_string(contents)
	if typeof(parsed) == TYPE_DICTIONARY and parsed.get("version", 0) == 1 and parsed.get("recovered", null) is Array:
		set_recovered_ids(parsed["recovered"])

func save_server_state() -> bool:
	var file := FileAccess.open(SAVE_PATH, FileAccess.WRITE)
	if file == null:
		return false
	var record: Dictionary = {"version": 1, "recovered": recovered_ids()}
	file.store_string(JSON.stringify(record))
	file.flush()
	return true
