import math
from helper.game import Game
from lib.interface.events.moves.move_player import MovePlayer
from lib.interface.queries.query_move import QueryMovePlayer
from lib.models.penguin_model import DirectionModel

MAP_MAX = 60.0
EAT_RATIO = 1.2
SPLIT_RATIO = 1.697056
MAX_BLOBS = 16
SPLIT_REACH = 15.0


class BotProfile:
    def __init__(self):
        self.last_pos = None
        self.dumb_moves = 0
        self.smart_moves = 0
        self.risk_score = 1.0


def calculate_move(query: QueryMovePlayer, profiles: dict) -> MovePlayer:
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

    vec_x, vec_y = 0.0, 0.0
    do_split = False

    wall_padding = 0.1
    dist_left = max(my_x, wall_padding)
    dist_right = max(MAP_MAX - my_x, wall_padding)
    dist_bottom = max(my_y, wall_padding)
    dist_top = max(MAP_MAX - my_y, wall_padding)

    vec_x += (35.0 / (dist_left ** 2)) - (35.0 / (dist_right ** 2))
    vec_y += (35.0 / (dist_bottom ** 2)) - (35.0 / (dist_top ** 2))

    for enemy in query.visible_blobs:
        if enemy.player_id == query.you.player_id:
            continue

        enemy_id = (enemy.player_id, getattr(enemy, 'blob_id', 0))
        if enemy_id not in profiles:
            profiles[enemy_id] = BotProfile()

        prof = profiles[enemy_id]
        enemy_mass = enemy.radius ** 2

        if prof.last_pos:
            move_dx = enemy.pos[0] - prof.last_pos[0]
            move_dy = enemy.pos[1] - prof.last_pos[1]
            if move_dx != 0 or move_dy != 0:
                rel_dx = my_x - prof.last_pos[0]
                rel_dy = my_y - prof.last_pos[1]
                dot_prod = (move_dx * rel_dx + move_dy * rel_dy)

                if my_mass > enemy_mass * EAT_RATIO:
                    if dot_prod > 0:
                        prof.dumb_moves += 1
                    else:
                        prof.smart_moves += 1
                elif enemy_mass > my_mass * EAT_RATIO:
                    if dot_prod > 0:
                        prof.smart_moves += 1

        total_evals = prof.dumb_moves + prof.smart_moves
        if total_evals > 5:
            prof.risk_score = max(
                0.4, min(2.5, (prof.smart_moves + 1) / (prof.dumb_moves + 1)))

        prof.last_pos = enemy.pos

        dx = enemy.pos[0] - my_x
        dy = enemy.pos[1] - my_y
        dist_sq = dx*dx + dy*dy
        if dist_sq < 0.0001:
            continue

        dist = math.sqrt(dist_sq)
        dir_x, dir_y = dx / dist, dy / dist
        enemy_speed = max(0.25, 1.1 - 0.08 * enemy.radius)

        if enemy.radius >= my_r * EAT_RATIO:
            force = 0.0
            base_flee = -800.0 if (enemy.radius >= my_r * SPLIT_RATIO and dist <
                                   (SPLIT_REACH + enemy.radius)) else -150.0
            if enemy.radius < my_r * SPLIT_RATIO:
                base_flee = -300.0

            force = (base_flee * prof.risk_score) / dist_sq

            vec_x += dir_x * force
            vec_y += dir_y * force

            tangent_x, tangent_y = -dir_y, dir_x
            if (tangent_x > 0 and dist_right < dist_left) or (tangent_x < 0 and dist_left < dist_right):
                tangent_x = -tangent_x
            if (tangent_y > 0 and dist_top < dist_bottom) or (tangent_y < 0 and dist_bottom < dist_top):
                tangent_y = -tangent_y

            slide_force = abs(force) * 0.6 * prof.risk_score
            vec_x += tangent_x * slide_force
            vec_y += tangent_y * slide_force

        elif my_r >= enemy.radius * EAT_RATIO:
            can_split_kill = (my_r >= enemy.radius * SPLIT_RATIO)
            is_faster = enemy_speed >= my_speed
            wall_dist_x = min(enemy.pos[0], MAP_MAX - enemy.pos[0])
            wall_dist_y = min(enemy.pos[1], MAP_MAX - enemy.pos[1])
            is_cornered = wall_dist_x < 8.0 or wall_dist_y < 8.0

            if can_split_kill:
                force = (200.0 / prof.risk_score) / dist
                vec_x += dir_x * force
                vec_y += dir_y * force

                if dist < SPLIT_REACH + enemy.radius and len(query.you.blobs) < MAX_BLOBS and my_mass > 4.0:
                    do_split = True

            elif not is_faster or is_cornered or prof.risk_score < 0.7:
                force = (120.0 / prof.risk_score) / dist
                vec_x += dir_x * force
                vec_y += dir_y * force

        else:
            force = (-20.0 * prof.risk_score) / dist_sq
            vec_x += dir_x * force
            vec_y += dir_y * force
            vec_x -= dir_y * (abs(force) * 0.8)
            vec_y += dir_x * (abs(force) * 0.8)

    if query.visible_viruses and my_r > 1.64:
        for virus in query.visible_viruses:
            if my_mass > 1.2 * (virus.radius ** 2):
                dx = virus.pos[0] - my_x
                dy = virus.pos[1] - my_y
                dist_sq = dx*dx + dy*dy
                if 0.0001 < dist_sq < 150.0:
                    dist = math.sqrt(dist_sq)
                    force = -200.0 / dist_sq
                    vec_x += (dx / dist) * force
                    vec_y += (dy / dist) * force
                    vec_x -= (dy / dist) * abs(force)
                    vec_y += (dx / dist) * abs(force)

    if query.visible_food:
        for food in query.visible_food:
            dx = food.pos[0] - my_x
            dy = food.pos[1] - my_y
            dist_sq = dx*dx + dy*dy
            if dist_sq > 0.0001:
                force = 15.0 / dist_sq
                vec_x += (dx / math.sqrt(dist_sq)) * force
                vec_y += (dy / math.sqrt(dist_sq)) * force

    mag = math.sqrt(vec_x**2 + vec_y**2)
    if mag < 0.0001:
        norm_x, norm_y = 1.0, 0.0
    else:
        norm_x = vec_x / mag
        norm_y = vec_y / mag

    return MovePlayer(
        player_id=query.you.player_id,
        direction=DirectionModel(x=norm_x, y=norm_y),
        split=do_split
    )


def main() -> None:
    game = Game()
    profiles = {}
    while True:
        query = game.get_next_query()
        match query:
            case QueryMovePlayer():
                game.send_move(calculate_move(query, profiles))
            case _:
                raise RuntimeError(f"Unsupported query type: {type(query)}")


if __name__ == "__main__":
    main()
