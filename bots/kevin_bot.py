import math
from helper.game import Game
from lib.interface.events.moves.move_player import MovePlayer
from lib.interface.queries.query_move import QueryMovePlayer
from lib.models.penguin_model import DirectionModel


def choose_move(game: Game) -> tuple[float, float, bool]:
    my_blobs = game.state.me.blobs
    if not my_blobs:
        return (1.0, 0.0, False)

    largest_blob = max(my_blobs.values(), key=lambda b: b.radius)
    my_x, my_y = largest_blob.pos
    my_r = largest_blob.radius
    my_mass = my_r ** 2
    arena_size = getattr(game.state, 'arena_size', 60.0)
    center_x, center_y = arena_size / 2.0, arena_size / 2.0

    threats = []
    prey = []
    neutrals = []
    all_enemies = []

    for enemy in game.state.visible_blobs:
        if enemy.player_id == game.state.me.player_id:
            continue

        dist = math.hypot(enemy.pos[0] - my_x, enemy.pos[1] - my_y)
        if dist == 0:
            continue

        all_enemies.append(enemy)
        enemy_mass = enemy.radius ** 2

        if enemy_mass > 1.2 * my_mass:
            threats.append((enemy, dist))
        elif my_mass > 1.2 * enemy_mass:
            prey.append((enemy, dist))
        else:
            neutrals.append((enemy, dist))

    safe_food = []
    if game.state.visible_food:
        for food in game.state.visible_food:
            my_dist_sq = (food.pos[0] - my_x) ** 2 + (food.pos[1] - my_y) ** 2
            is_contested = False
            for enemy in all_enemies:
                enemy_dist_sq = (
                    food.pos[0] - enemy.pos[0]) ** 2 + (food.pos[1] - enemy.pos[1]) ** 2
                if enemy_dist_sq < my_dist_sq:
                    is_contested = True
                    break

            if not is_contested:
                if 4.0 < food.pos[0] < arena_size - 4.0 and 4.0 < food.pos[1] < arena_size - 4.0:
                    safe_food.append((food, math.sqrt(my_dist_sq)))

    best_food_cluster = None
    best_cluster_score = -1.0

    if safe_food:
        for f, d in safe_food:
            neighbors = sum(1 for other_f, _ in safe_food if math.hypot(
                f.pos[0] - other_f.pos[0], f.pos[1] - other_f.pos[1]) < 6.0)

            f_dist_center = math.hypot(
                f.pos[0] - center_x, f.pos[1] - center_y)
            edge_penalty = 1.0 + (f_dist_center / (arena_size / 2.0))

            score = (neighbors + 1) / (d * edge_penalty + 0.1)
            if score > best_cluster_score:
                best_cluster_score = score
                best_food_cluster = f

    dx, dy, do_split = 0.0, 0.0, False
    action_chosen = False

    active_threats = [t for t in threats if t[1] < (t[0].radius * 4.0 + my_r)]
    if active_threats and not action_chosen:
        closest_threat, threat_dist = min(active_threats, key=lambda t: t[1])
        threat_mass = closest_threat.radius ** 2

        safe_virus = None
        if game.state.visible_viruses:
            valid_viruses = [
                v for v in game.state.visible_viruses if threat_mass > 1.2 * (v.radius ** 2)]
            if valid_viruses:
                safe_virus = min(valid_viruses, key=lambda v: math.hypot(
                    v.pos[0] - my_x, v.pos[1] - my_y))

        if safe_virus:
            vx, vy = safe_virus.pos
            tx, ty = closest_threat.pos
            tv_dist = math.hypot(vx - tx, vy - ty)

            if tv_dist > 0:
                dir_x = (vx - tx) / tv_dist
                dir_y = (vy - ty) / tv_dist
                shadow_x = vx + dir_x * (safe_virus.radius + my_r)
                shadow_y = vy + dir_y * (safe_virus.radius + my_r)
                sdx = shadow_x - my_x
                sdy = shadow_y - my_y
                s_dist = math.hypot(sdx, sdy)

                if s_dist > 0:
                    dx, dy = (sdx / s_dist) * 15.0, (sdy / s_dist) * 15.0
                    action_chosen = True

        if not action_chosen:
            tdx = my_x - closest_threat.pos[0]
            tdy = my_y - closest_threat.pos[1]
            dx += (tdx / threat_dist) * 10.0
            dx -= (tdy / threat_dist) * 5.0
            dy += (tdx / threat_dist) * 5.0
            action_chosen = True

    if not action_chosen:
        active_prey = [p for p in prey if p[1] < max(25.0, my_r * 4.0)]
        if active_prey:
            active_prey.sort(key=lambda p: p[1])
            for closest_prey, dist in active_prey:
                if dist > 12.0 and best_food_cluster:
                    if math.hypot(best_food_cluster.pos[0] - my_x, best_food_cluster.pos[1] - my_y) < 5.0:
                        continue

                path_blocked = False
                if game.state.visible_viruses:
                    for virus in game.state.visible_viruses:
                        if my_mass > 1.2 * (virus.radius ** 2):
                            ABx = closest_prey.pos[0] - my_x
                            ABy = closest_prey.pos[1] - my_y
                            ACx = virus.pos[0] - my_x
                            ACy = virus.pos[1] - my_y

                            dot_AB = ABx**2 + ABy**2
                            if dot_AB == 0:
                                continue

                            t = max(0.0, min(1.0, (ACx*ABx + ACy*ABy) / dot_AB))
                            closest_x = my_x + t * ABx
                            closest_y = my_y + t * ABy
                            dist_to_virus = math.hypot(
                                closest_x - virus.pos[0], closest_y - virus.pos[1])

                            if dist_to_virus < (virus.radius + my_r + 1.0):
                                path_blocked = True
                                break

                if path_blocked:
                    continue

                px, py = closest_prey.pos
                wall_dists = {'left': px, 'right': arena_size -
                              px, 'top': py, 'bottom': arena_size - py}
                nearest_wall = min(wall_dists, key=wall_dists.get)

                target_x, target_y = px, py
                offset = closest_prey.radius * 2.0
                if nearest_wall == 'left':
                    target_x -= offset
                elif nearest_wall == 'right':
                    target_x += offset
                elif nearest_wall == 'top':
                    target_y -= offset
                elif nearest_wall == 'bottom':
                    target_y += offset

                dx = target_x - my_x
                dy = target_y - my_y

                enemy_mass = closest_prey.radius ** 2
                if my_mass > 2.4 * enemy_mass and my_r > 3.0:
                    if my_r < dist < 4.0 * my_r:
                        do_split = True

                action_chosen = True
                break

    if not action_chosen:
        base_dx, base_dy = 0.0, 0.0

        close_neutrals = [n for n in neutrals if n[1] < 15.0]
        for enemy, dist in close_neutrals:
            if dist > 0:
                ndx = my_x - enemy.pos[0]
                ndy = my_y - enemy.pos[1]
                base_dx += (ndx / dist) * 5.0
                base_dy += (ndy / dist) * 5.0
                base_dx -= (ndy / dist) * 3.0
                base_dy += (ndx / dist) * 3.0

        if best_food_cluster:
            fdx = best_food_cluster.pos[0] - my_x
            fdy = best_food_cluster.pos[1] - my_y
            f_dist = math.hypot(fdx, fdy)
            if f_dist > 0:
                base_dx += (fdx / f_dist) * 10.0
                base_dy += (fdy / f_dist) * 10.0

                if my_r > 4.0 and len(my_blobs) < 3:
                    do_split = True
        else:
            cdx, cdy = center_x - my_x, center_y - my_y
            c_dist = math.hypot(cdx, cdy)
            if c_dist > 0:
                base_dx += (cdx / c_dist) * 3.0
                base_dy += (cdy / c_dist) * 3.0

        dx, dy = base_dx, base_dy

    margin = 8.0
    if my_x < margin:
        dx += (margin - my_x) * 20.0
    elif my_x > arena_size - margin:
        dx -= (my_x - (arena_size - margin)) * 20.0
    if my_y < margin:
        dy += (margin - my_y) * 20.0
    elif my_y > arena_size - margin:
        dy -= (my_y - (arena_size - margin)) * 20.0

    return (dx, dy, do_split)


def main() -> None:
    game = Game()

    while True:
        query = game.get_next_query()
        match query:
            case QueryMovePlayer():
                dx, dy, split = choose_move(game)
                game.send_move(
                    MovePlayer(
                        player_id=game.state.me.player_id,
                        direction=DirectionModel(x=dx, y=dy),
                        split=split
                    )
                )
            case _:
                raise RuntimeError(f"Unsupported query type: {type(query)}")


if __name__ == "__main__":
    main()
