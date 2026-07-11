import math
from helper.game import Game
from lib.interface.events.moves.move_player import MovePlayer
from lib.interface.queries.query_move import QueryMovePlayer
from lib.models.penguin_model import DirectionModel
from lib.config.arena import ARENA_SIZE, MAX_ROUNDS, VIRUS_SIZE
from lib.config.player import (
    EAT_SIZE_RATIO,
    BASE_PLAYER_SPEED,
    PLAYER_SPEED_RADIUS_FACTOR,
    MIN_PLAYER_SPEED,
    SPLIT_EJECT_SPEED,
    SPLIT_EJECT_DRAG,
)

# kevin_bot_v9.0 - Optimized for Average Final Mass & Anti-AI Tactics

MAP_MAX = ARENA_SIZE
EAT_RATIO = EAT_SIZE_RATIO
SPLIT_RATIO = 2.4
SPLIT_JUMP = SPLIT_EJECT_SPEED / (1.0 - SPLIT_EJECT_DRAG)
MAX_BLOBS = 16
FARM_MIN_MASS = 5.0
VIRUS_CONSUME_MASS = (VIRUS_SIZE ** 2) * EAT_SIZE_RATIO


def blob_speed(radius):
    return max(MIN_PLAYER_SPEED, BASE_PLAYER_SPEED / (1.0 + radius * PLAYER_SPEED_RADIUS_FACTOR))


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
    my_speed = blob_speed(my_r)
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
    can_physically_split = my_blob_count < MAX_BLOBS and my_mass > 10.0

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
        cornered = enemy_wall_dist < 10.0 or heading_to_wall
        closure_rate = (dx * (vx - my_vx) + dy * (vy - my_vy)) / dist

        if is_prey and not cornered:
            if is_split_target:
                halved_r = math.sqrt(my_mass / 2.0)
                gap_to_split = dist - (halved_r + SPLIT_JUMP)
                if gap_to_split > 2.0 and closure_rate >= -0.05:
                    is_prey = False
                    is_split_target = False
            else:
                gap_to_eat = dist - my_r
                if gap_to_eat > 1.0 and closure_rate >= -0.05:
                    is_prey = False

        target_dir_x, target_dir_y = dx / dist, dy / dist
        if is_prey and cornered:
            mag_v = math.hypot(vx, vy)
            norm_vx, norm_vy = (
                vx / mag_v, vy / mag_v) if mag_v > 0.01 else (0.0, 0.0)

            target_dir_x = (target_dir_x * 0.7) + (norm_vx * 0.3)
            target_dir_y = (target_dir_y * 0.7) + (norm_vy * 0.3)
            mag = math.hypot(target_dir_x, target_dir_y)
            if mag > 0.001:
                target_dir_x /= mag
                target_dir_y /= mag

        enemy_data.append({
            'x': b.pos[0], 'y': b.pos[1],
            'vx': vx, 'vy': vy,
            'dist': dist,
            'dir_x': target_dir_x,
            'dir_y': target_dir_y,
            'raw_dx': dx / dist,
            'raw_dy': dy / dist,
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

    # Only farm viruses if strictly no enemies are around to eat the fragments
    farm_viruses = (
        len(enemy_data) == 0
        and my_mass >= FARM_MIN_MASS
        and my_mass > VIRUS_CONSUME_MASS
    )

    NUM_RAYS = 64
    best_score = -float('inf')
    best_ray = memory.last_dir
    do_split = False

    mass_aggression_multiplier = 1.0 + (my_mass / 200.0)

    rounds_left = MAX_ROUNDS - query.round
    endgame_caution = 1.0
    if rounds_left < 200:
        endgame_caution = 1.0 + (200 - max(0, rounds_left)) / 200.0 * 2.0
        try:
            if list(query.rankings).index(query.you.player_id) <= 1:
                endgame_caution *= 1.5
        except (ValueError, AttributeError):
            pass

    for i in range(NUM_RAYS):
        angle = i * (2 * math.pi / NUM_RAYS)
        rx, ry = math.cos(angle), math.sin(angle)
        score = 0.0
        chase_food_mult = 1.0 * mass_aggression_multiplier
        ray_prey_score = 0.0

        score += (rx * memory.last_dir[0] + ry * memory.last_dir[1]) * 15.0

        # Memory exploration penalty
        proj_x = my_x + rx * 12.0
        proj_y = my_y + ry * 12.0
        for hx, hy, htick in memory.visit_history:
            if math.hypot(proj_x - hx, proj_y - hy) < 10.0:
                age_ratio = 1.0 - ((memory.tick - htick) / 200.0)
                score -= 2.0 * max(0.0, age_ratio)

        for e in enemy_data:
            dot = rx * e['dir_x'] + ry * e['dir_y']
            raw_dot = rx * e['raw_dx'] + ry * e['raw_dy']

            # Anti-AI Virus Shielding: Reward rays that align a virus between us and a threat
            if e['is_threat'] and raw_dot < -0.3 and query.visible_viruses:
                for v in query.visible_viruses:
                    vdx, vdy = v.pos[0] - my_x, v.pos[1] - my_y
                    dist_to_v = math.hypot(vdx, vdy)
                    if dist_to_v < e['dist']:
                        edx, edy = e['x'] - my_x, e['y'] - my_y
                        dot_v_e = (vdx * edx + vdy * edy) / \
                            (dist_to_v * e['dist'])
                        if dot_v_e > 0.9:
                            ray_v_dot = rx * vdx + ry * vdy
                            if ray_v_dot > 0:
                                score += 3000.0 / max(1.0, dist_to_v)

            if raw_dot > 0.3:
                if e['is_threat']:
                    weight = (30000.0 if e['is_split_threat']
                              else 15000.0) * endgame_caution
                    score -= (weight * raw_dot) / max(1.0, e['dist'] ** 2)

                    if e['is_split_threat']:
                        # Smoother gradient compared to cld1's hard drop-off
                        lunge_reach = e['r'] * 2.0 + SPLIT_JUMP + 2.0
                        if e['dist'] < lunge_reach:
                            score -= (15000.0 * raw_dot *
                                      endgame_caution) / max(1.0, e['dist'])

                elif e['is_prey']:
                    if e['cornered']:
                        add_score = (
                            50000.0 * dot * mass_aggression_multiplier) / max(0.1, e['dist'])
                        score += add_score
                        ray_prey_score += add_score
                        chase_food_mult = max(
                            chase_food_mult, 1.5 * mass_aggression_multiplier)
                    else:
                        add_score = (
                            4000.0 * dot * mass_aggression_multiplier) / max(1.0, e['dist'])
                        score += add_score
                        ray_prey_score += add_score
                        if dot > 0.85:
                            chase_food_mult = max(
                                chase_food_mult, 4.0 if not e['is_split_target'] else 2.0)
                else:
                    score -= (500.0 * raw_dot) / max(1.0, e['dist'] ** 2)

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

        # Engine rule fix: Only pop if virus CENTER is inside blob radius
        if my_mass > VIRUS_CONSUME_MASS and query.visible_viruses:
            for v in query.visible_viruses:
                vdx, vdy = v.pos[0] - my_x, v.pos[1] - my_y
                along_dist = rx * vdx + ry * vdy
                if 0 < along_dist < 30.0:
                    perp_dist = abs(rx * vdy - ry * vdx)
                    if perp_dist < my_r + 0.1:
                        if my_blob_count == MAX_BLOBS or farm_viruses:
                            score += 8000.0 / max(0.1, along_dist ** 2)
                        else:
                            score -= 50000.0 / max(0.1, along_dist)

        if query.visible_food:
            eat_radius = my_r + 0.15
            for f in query.visible_food:
                fdx, fdy = f.pos[0] - my_x, f.pos[1] - my_y
                along_dist = rx * fdx + ry * fdy
                if 0 < along_dist < 25.0:
                    perp_dist = abs(rx * fdy - ry * fdx)
                    if perp_dist < eat_radius:
                        accuracy_mult = 1.0 - (perp_dist / eat_radius)
                        score += (75.0 * (1.0 + 2.0 * accuracy_mult)
                                  * chase_food_mult) / (along_dist + 1.0)

        if score > best_score:
            best_score = score
            best_ray = (rx, ry)

    if can_physically_split:
        halved_mass = my_mass / 2.0
        halved_r = math.sqrt(halved_mass)

        safe_to_split = True
        for e in enemy_data:
            # Tighter restriction on 3rd party interference - only check closer radii
            if player_masses.get(e['pid'], e['r'] ** 2) >= halved_mass * EAT_RATIO and e['dist'] < (20.0 + halved_r):
                safe_to_split = False
                break

        if safe_to_split:
            for e in enemy_data:
                if e['is_split_target']:
                    # Replaced complex 8-tick sim with robust landing-zone center overlap
                    ex_future = e['x'] + e['vx'] * 5.0
                    ey_future = e['y'] + e['vy'] * 5.0

                    landing_x = my_x + best_ray[0] * \
                        (halved_r + SPLIT_JUMP * 0.9)
                    landing_y = my_y + best_ray[1] * \
                        (halved_r + SPLIT_JUMP * 0.9)

                    # To eat, target center must be inside our new radius
                    if math.hypot(landing_x - ex_future, landing_y - ey_future) < halved_r:
                        virus_blocked = False
                        if query.visible_viruses:
                            for v in query.visible_viruses:
                                if halved_mass > VIRUS_CONSUME_MASS:
                                    vdx, vdy = v.pos[0] - my_x, v.pos[1] - my_y
                                    vdot = best_ray[0] * \
                                        vdx + best_ray[1] * vdy
                                    if 0 < vdot < (halved_r + SPLIT_JUMP + v.radius):
                                        perp = abs(
                                            best_ray[0] * vdy - best_ray[1] * vdx)
                                        if perp < (halved_r + 0.1):
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

    # Clamp logic: ensure inertia doesn't drag us into viruses or threats at the last second
    if my_blob_count < MAX_BLOBS and not farm_viruses and my_mass > VIRUS_CONSUME_MASS and query.visible_viruses:
        for v in query.visible_viruses:
            vdx, vdy = v.pos[0] - my_x, v.pos[1] - my_y
            along = smooth_x * vdx + smooth_y * vdy
            perp = abs(smooth_x * vdy - smooth_y * vdx)
            if 0 < along < (my_r + v.radius + 1.0) and perp < (my_r + 0.1):
                smooth_x, smooth_y = best_ray[0], best_ray[1]
                break

    for e in enemy_data:
        if e['is_threat']:
            edx, edy = e['x'] - my_x, e['y'] - my_y
            along = smooth_x * edx + smooth_y * edy
            perp = abs(smooth_x * edy - smooth_y * edx)
            if 0 < along < (my_r + e['r'] + 2.0) and perp < (my_r + e['r'] - 0.2):
                smooth_x, smooth_y = best_ray[0], best_ray[1]
                break

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
