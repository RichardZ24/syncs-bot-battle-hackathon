import math
from helper.game import Game
from lib.interface.events.moves.move_player import MovePlayer
from lib.interface.queries.query_move import QueryMovePlayer
from lib.models.penguin_model import DirectionModel

# Engine Constants
MAP_MAX = 60.0
EAT_RATIO = 1.2
SPLIT_RATIO = 1.697  # sqrt(2) * 1.2
MAX_BLOBS = 16
SPLIT_MIN_MASS = 2.0
SPLIT_REACH = 12.0


def calculate_move(query: QueryMovePlayer) -> MovePlayer:
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

    # 1. Wall Boundaries (Repulsion)
    wall_padding = 0.5
    dist_x_0 = max(my_x, wall_padding)
    dist_x_60 = max(MAP_MAX - my_x, wall_padding)
    dist_y_0 = max(my_y, wall_padding)
    dist_y_60 = max(MAP_MAX - my_y, wall_padding)

    vec_x += (20.0 / (dist_x_0 ** 2)) - (20.0 / (dist_x_60 ** 2))
    vec_y += (20.0 / (dist_y_0 ** 2)) - (20.0 / (dist_y_60 ** 2))

    # 2. Enemy Blobs
    for enemy in query.visible_blobs:
        if enemy.player_id == query.you.player_id:
            continue
        
        dx = enemy.pos[0] - my_x
        dy = enemy.pos[1] - my_y
        dist_sq = dx*dx + dy*dy
        
        if dist_sq < 0.0001: 
            continue
            
        dist = math.sqrt(dist_sq)
        dir_x, dir_y = dx / dist, dy / dist
        enemy_speed = max(0.25, 1.1 - 0.08 * enemy.radius)

        # --- DEFENSE ---
        # Extreme Danger: Enemy can split-kill us
        if enemy.radius >= my_r * SPLIT_RATIO:
            # Panic evasion if they are within split reach + their own radius
            if dist < (SPLIT_REACH + enemy.radius):
                force = -500.0 / dist_sq 
            else:
                force = -50.0 / dist_sq
            vec_x += dir_x * force
            vec_y += dir_y * force
            
        # Normal Danger: Enemy can eat us normally
        elif enemy.radius >= my_r / EAT_RATIO:
            force = -150.0 / dist_sq
            vec_x += dir_x * force
            vec_y += dir_y * force
            
        # --- OFFENSE ---
        # We can eat them
        elif my_r >= enemy.radius * EAT_RATIO:
            can_split_kill = (my_r >= enemy.radius * SPLIT_RATIO) and (my_mass >= SPLIT_MIN_MASS)
            is_faster = enemy_speed >= my_speed
            
            # Check if they are cornered
            wall_dist_x = min(enemy.pos[0], MAP_MAX - enemy.pos[0])
            wall_dist_y = min(enemy.pos[1], MAP_MAX - enemy.pos[1])
            is_cornered = wall_dist_x < 10.0 or wall_dist_y < 10.0

            if can_split_kill:
                force = 100.0 / dist
                vec_x += dir_x * force
                vec_y += dir_y * force
                
                # Execute Split
                if dist < SPLIT_REACH and len(query.you.blobs) < MAX_BLOBS and not do_split:
                    do_split = True
                    
            elif not is_faster or is_cornered:
                # Catchable naturally or cornered
                force = 60.0 / dist
                vec_x += dir_x * force
                vec_y += dir_y * force
                
            else:
                # CHASE FATIGUE: Ditch them. They are faster, not cornered, and we can't split.
                # Do not add to vec_x / vec_y. Bot will default to farming food.
                pass

    # 3. Viruses
    if my_r > 1.5:
        for virus in query.visible_viruses:
            dx = virus.pos[0] - my_x
            dy = virus.pos[1] - my_y
            dist_sq = dx*dx + dy*dy
            
            if 0.0001 < dist_sq < 100.0:
                dist = math.sqrt(dist_sq)
                force = -80.0 / dist_sq
                vec_x += (dx / dist) * force
                vec_y += (dy / dist) * force

    # 4. Food
    for food in query.visible_food:
        dx = food.pos[0] - my_x
        dy = food.pos[1] - my_y
        dist_sq = dx*dx + dy*dy
        
        if dist_sq > 0.0001:
            force = 5.0 / dist_sq
            vec_x += (dx / math.sqrt(dist_sq)) * force
            vec_y += (dy / math.sqrt(dist_sq)) * force

    # 5. Normalization
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

    while True:
        query = game.get_next_query()
        match query:
            case QueryMovePlayer():
                move_action = calculate_move(query)
                game.send_move(move_action)
            case _:
                raise RuntimeError(f"Unsupported query type: {type(query)}")


if __name__ == "__main__":
    main()