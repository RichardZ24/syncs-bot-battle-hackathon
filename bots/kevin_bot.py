import math
from helper.game import Game
from lib.interface.events.moves.move_player import MovePlayer
from lib.interface.queries.query_move import QueryMovePlayer
from lib.models.penguin_model import DirectionModel

# Engine Constants
MAP_MAX = 60.0
EAT_RATIO = 1.2
SPLIT_RATIO = 2.4
SPLIT_JUMP = 8.88
MAX_BLOBS = 16


class BotMemory:
    def __init__(self):
        self.last_positions = {}
        self.velocities = {}
        self.last_dir = (1.0, 0.0)
        self.visit_history = []
        self.tick = 0
        self.my_last_pos = None


def calculate_move(query: QueryMovePlayer, memory: BotMemory) -> MovePlayer:
    if not query.you.alive or not query.you.blobs:
        return MovePlayer(
            player_id=query.you.player_id,
            direction=DirectionModel(x=1.0, y=0.0),
            split=False
        )

    my_largest = max(query.you.blobs, key=lambda b: b.radius)
    my_x, my_y = my_largest.pos
    my_r = my_largest.radius
    my_mass = my_r ** 2
    my_speed = max(0.25, 1.1 - 0.08 * my_r)
    my_blob_count = len(query.you.blobs)

    my_vx, my_vy = 0.0, 0.0
    if memory.my_last_pos:
        my_vx = my_x - memory.my_last_pos[0]
        my_vy = my_y - memory.my_last_pos[1]
    memory.my_last_pos = (my_x, my_y)

    memory.tick += 1
    if memory.tick % 5 == 0:
        memory.visit_history.append((my_x, my_y, memory.tick))
    memory.visit_history = [
        h for h in memory.visit_history if memory.tick - h[2] < 200]

    player_masses = {}
    current_blob_ids = set()

    for b in query.visible_blobs:
        if b.player_id == query.you.player_id:
            continue
        player_masses[b.player_id] = player_masses.get(
            b.player_id, 0.0) + (b.radius ** 2)

    enemy_data = []
    can_physically_split = my_blob_count < MAX_BLOBS and my_mass > 4.0

    for b in query.visible_blobs:
        if b.player_id == query.you.player_id:
            continue

        b_id = getattr(b, 'blob_id', id(b))
        current_blob_ids.add(b_id)

        dx = b.pos[0] - my_x
        dy = b.pos[1] - my_y
        dist = math.hypot(dx, dy)
        if dist < 0.01:
            continue

        vx, vy = 0.0, 0.0
        if b_id in memory.last_positions:
            lx, ly = memory.last_positions[b_id]
            vx = b.pos[0] - lx
            vy = b.pos[1] - ly
            if b_id in memory.velocities:
                ovx, ovy = memory.velocities[b_id]
                vx = vx * 0.5 + ovx * 0.5

        memory.last_positions[b_id] = b.pos
        memory.velocities[b_id] = (vx, vy)

        mass = b.radius ** 2
        cd = getattr(b, 'merge_cooldown', 0)

        frames_to_reach = dist / my_speed
        eff_mass = player_masses[b.player_id] if (
            cd <= frames_to_reach and player_masses[b.player_id] > mass) else mass

        is_prey = my_mass >= eff_mass * EAT_RATIO
        # Mechanical Split Awareness
        is_split_target = (my_mass >= eff_mass *
                           SPLIT_RATIO) and can_physically_split

        heading_to_wall = False
        if abs(vx) > 0.05 or abs(vy) > 0.05:
            tx = (MAP_MAX - b.pos[0]) / vx if vx > 0 else (
                b.pos[0] / -vx if vx < 0 else float('inf'))
            ty = (MAP_MAX - b.pos[1]) / vy if vy > 0 else (
                b.pos[1] / -vy if vy < 0 else float('inf'))
            if min(tx, ty) < 15.0:
                heading_to_wall = True

        enemy_wall_dist = min(b.pos[0], MAP_MAX -
                              b.pos[0], b.pos[1], MAP_MAX - b.pos[1])
        cornered = enemy_wall_dist < 8.0 or heading_to_wall

        closure_rate = (dx * (vx - my_vx) + dy * (vy - my_vy)) / dist

        # TACTICAL UPGRADE: The Kinematic Paradox Fix
        # Drop aggro if we are mathematically slower and out of range
        if is_prey and not cornered:
            if is_split_target:
                gap_to_split = dist - (my_r / 1.414 + SPLIT_JUMP + b.radius)
                if gap_to_split > 2.0 and closure_rate >= -0.05:
                    is_prey = False
                    is_split_target = False
            else:
                gap_to_eat = dist - (my_r + b.radius)
                if gap_to_eat > 1.0 and closure_rate >= -0.05:
                    is_prey = False

        enemy_data.append({
            'x': b.pos[0], 'y': b.pos[1],
            'vx': vx, 'vy': vy,
            'dist': dist,
            'dir_x': dx/dist,
            'dir_y': dy/dist,
            'is_threat': eff_mass >= my_mass * EAT_RATIO,
            'is_split_threat': eff_mass >= my_mass * SPLIT_RATIO,
            'is_prey': is_prey,
            'is_split_target': is_split_target,
            'cornered': cornered,
            'r': b.radius,
            'pid': b.player_id
        })

    memory.last_positions = {
        k: v for k, v in memory.last_positions.items() if k in current_blob_ids}
    memory.velocities = {
        k: v for k, v in memory.velocities.items() if k in current_blob_ids}

    NUM_RAYS = 32
    best_score = -float('inf')
    best_ray = memory.last_dir
    do_split = False

    for i in range(NUM_RAYS):
        angle = i * (2 * math.pi / NUM_RAYS)
        rx, ry = math.cos(angle), math.sin(angle)
        score = 0.0
        chase_food_mult = 1.0
        ray_prey_score = 0.0

        score += (rx * memory.last_dir[0] + ry * memory.last_dir[1]) * 15.0

        proj_x = my_x + rx * 12.0
        proj_y = my_y + ry * 12.0
        for hx, hy, htick in memory.visit_history:
            if math.hypot(proj_x - hx, proj_y - hy) < 10.0:
                age_ratio = 1.0 - ((memory.tick - htick) / 200.0)
                score -= 2.0 * max(0.0, age_ratio)

        for e in enemy_data:
            dot = rx * e['dir_x'] + ry * e['dir_y']
            if dot > 0.3:
                if e['is_threat']:
                    weight = 25000.0 if e['is_split_threat'] else 8000.0
                    score -= (weight * dot) / max(1.0, e['dist'] ** 2)
                elif e['is_prey']:
                    if e['cornered']:
                        add_score = (40000.0 * dot) / max(0.1, e['dist'])
                        score += add_score
                        ray_prey_score += add_score
                        chase_food_mult = max(chase_food_mult, 1.2)
                    else:
                        add_score = (3000.0 * dot) / max(1.0, e['dist'])
                        score += add_score
                        ray_prey_score += add_score
                        if dot > 0.85:
                            chase_food_mult = max(
                                chase_food_mult, 3.0 if not e['is_split_target'] else 1.5)
                else:
                    score -= (500.0 * dot) / max(1.0, e['dist'] ** 2)

        dist_x = (MAP_MAX - my_x) / rx if rx > 0 else (my_x / -
                                                       rx if rx < 0 else float('inf'))
        dist_y = (MAP_MAX - my_y) / ry if ry > 0 else (my_y / -
                                                       ry if ry < 0 else float('inf'))
        wall_dist = min(dist_x, dist_y)

        if wall_dist < 12.0:
            base_wall_penalty = 3000.0 / max(1.0, wall_dist ** 2)
            if ray_prey_score > base_wall_penalty * 0.8:
                score -= base_wall_penalty * 0.1
            else:
                score -= base_wall_penalty

        if my_r > 1.6 and query.visible_viruses:
            for v in query.visible_viruses:
                if my_mass > (v.radius ** 2) * EAT_RATIO:
                    vdx, vdy = v.pos[0] - my_x, v.pos[1] - my_y
                    along_dist = rx * vdx + ry * vdy
                    if 0 < along_dist < 30.0:
                        perp_dist = abs(rx * vdy - ry * vdx)
                        if perp_dist < (my_r + v.radius + 1.0):
                            score -= 500000.0 / max(0.1, along_dist ** 2)

        if query.visible_food:
            eat_radius = my_r + 0.15
            for f in query.visible_food:
                fdx, fdy = f.pos[0] - my_x, f.pos[1] - my_y
                along_dist = rx * fdx + ry * fdy
                if 0 < along_dist < 25.0:
                    perp_dist = abs(rx * fdy - ry * fdx)
                    if perp_dist < eat_radius:
                        accuracy_mult = 1.0 - (perp_dist / eat_radius)
                        score += (60.0 * (1.0 + 2.0 * accuracy_mult)
                                  * chase_food_mult) / (along_dist + 1.0)

        if score > best_score:
            best_score = score
            best_ray = (rx, ry)

    if can_physically_split:
        halved_mass = my_mass / 2.0
        halved_r = my_r / 1.414

        safe_to_split = True
        for e in enemy_data:
            if player_masses[e['pid']] >= halved_mass * EAT_RATIO and e['dist'] < 30.0:
                safe_to_split = False
                break

        if safe_to_split:
            for e in enemy_data:
                if e['is_split_target']:
                    ex_future = e['x'] + e['vx'] * 6.0
                    ey_future = e['y'] + e['vy'] * 6.0

                    landing_x = my_x + best_ray[0] * (halved_r + SPLIT_JUMP)
                    landing_y = my_y + best_ray[1] * (halved_r + SPLIT_JUMP)

                    if math.hypot(landing_x - ex_future, landing_y - ey_future) < (halved_r + e['r'] * 0.5):
                        virus_blocked = False
                        if query.visible_viruses:
                            for v in query.visible_viruses:
                                if halved_mass > (v.radius ** 2) * EAT_RATIO:
                                    vdx, vdy = v.pos[0] - my_x, v.pos[1] - my_y
                                    vdot = best_ray[0] * \
                                        vdx + best_ray[1] * vdy
                                    if 0 < vdot < (halved_r + SPLIT_JUMP + v.radius):
                                        perp = abs(
                                            best_ray[0] * vdy - best_ray[1] * vdx)
                                        if perp < (v.radius + halved_r + 0.5):
                                            virus_blocked = True
                                            break
                        if not virus_blocked:
                            do_split = True
                            break

    blend = 0.4
    smooth_x = best_ray[0] * (1.0 - blend) + memory.last_dir[0] * blend
    smooth_y = best_ray[1] * (1.0 - blend) + memory.last_dir[1] * blend

    mag = math.hypot(smooth_x, smooth_y)
    if mag > 0.0001:
        smooth_x /= mag
        smooth_y /= mag

    memory.last_dir = (smooth_x, smooth_y)

    return MovePlayer(
        player_id=query.you.player_id,
        direction=DirectionModel(x=smooth_x, y=smooth_y),
        split=do_split
    )


def main() -> None:
    game = Game()
    memory = BotMemory()
    while True:
        query = game.get_next_query()
        match query:
            case QueryMovePlayer():
                game.send_move(calculate_move(query, memory))
            case _:
                raise RuntimeError(f"Unsupported query type: {type(query)}")


if __name__ == "__main__":
    main()
