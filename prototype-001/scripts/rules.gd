extends RefCounted
## Shared, deterministic validation. Networking is always untrusted.

const MAX_PLAYERS: int = 4
const PORT: int = 8910
const WALK_SPEED: float = 4.1
const RUN_SPEED: float = 6.4
const INTERACT_RADIUS: float = 2.4
const MAX_SAMPLE_COUNT: int = 3
const INPUT_INTERVAL_SECONDS: float = 0.05
const SNAPSHOT_INTERVAL_SECONDS: float = 0.075

static func normalized_axes(x: float, y: float) -> Vector2:
	if is_nan(x) or is_inf(x) or is_nan(y) or is_inf(y):
		return Vector2.ZERO
	return Vector2(clampf(x, -1.0, 1.0), clampf(y, -1.0, 1.0)).limit_length(1.0)

static func sanitized_yaw(value: float) -> float:
	if is_nan(value) or is_inf(value):
		return 0.0
	return wrapf(value, -PI, PI)

static func valid_endpoint(url: String) -> bool:
	var lower: String = url.to_lower().strip_edges()
	return (lower.begins_with("ws://") or lower.begins_with("wss://")) and lower.length() < 256

static func spawn_point(index: int) -> Vector3:
	return Vector3(-1.5 + float(posmod(index, MAX_PLAYERS)), 1.03, -24.0)
