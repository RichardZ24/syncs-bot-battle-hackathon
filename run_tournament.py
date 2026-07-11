# RUN USING uv run python run_tournament.py
import subprocess
import json
import os

# --- CONFIGURATION ---
ITERATIONS = 200  # Change this number to run more or fewer matches

# The exact command you use to run the simulation
COMMAND = [
    "uv", "run", "simulation", "--headless",
    "1:bots/kevin_bot.py",
    "2:bots/richard_bot.py",
    "2:bots/default_bot.py",
    "1:bots/kevin_bot_og.py",
    "1:bots/kevin_bot_cld1.py",
    "1:bots/kevin_bot_cld2.py"
]

# Path to where the engine saves the results
RESULTS_PATH = ".agario/simulation/output/results.json"

# Map player IDs (0-7) to their respective bots based on the command order
BOT_MAP = {
    0: "kevin_bot.py",
    1: "richard_bot.py",
    2: "richard_bot.py",
    3: "default_bot.py",
    4: "default_bot.py",
    5: "kevin_bot_og.py",
    6: "kevin_bot_cld1.py",
    7: "kevin_bot_cld2.py"
}


def main():
    # Tracking dictionaries
    unique_bots = set(BOT_MAP.values())
    win_counts = {bot: 0 for bot in unique_bots}
    total_mass = {bot: 0.0 for bot in unique_bots}
    total_instances = {bot: 0 for bot in unique_bots}
    valid_games = 0

    print(f"Starting tournament: {ITERATIONS} matches...")

    for i in range(ITERATIONS):
        print(f"Running Match {i + 1}/{ITERATIONS}...", end="", flush=True)

        # This runs the game silently in the background
        subprocess.run(COMMAND, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)

        if not os.path.exists(RESULTS_PATH):
            print(" [Failed: results.json not found]")
            continue

        # Open and parse the results
        with open(RESULTS_PATH, "r") as f:
            try:
                results = json.load(f)

                # Check for a successful match
                if results.get("result_type") == "SUCCESS" and "ranking" in results:

                    # 1. Tally Wins
                    winner_id = results["ranking"][0]
                    winner_bot = BOT_MAP.get(
                        winner_id, f"Unknown (ID: {winner_id})")

                    if winner_bot in win_counts:
                        win_counts[winner_bot] += 1

                    # 2. Tally Final Masses
                    if "final_masses" in results:
                        for pid_str, mass in results["final_masses"].items():
                            try:
                                pid = int(pid_str)
                                bot_name = BOT_MAP.get(pid)
                                if bot_name:
                                    total_mass[bot_name] += float(mass)
                                    total_instances[bot_name] += 1
                            except ValueError:
                                pass  # Ignore invalid player IDs

                    valid_games += 1
                    print(f" [Winner: {winner_bot} (Player {winner_id})]")
                else:
                    print(" [Failed: Match cancelled or banned player]")
            except json.JSONDecodeError:
                print(" [Failed: Invalid JSON format]")

    # Print the final leaderboard
    print("\n" + "="*60)
    print("🏆 TOURNAMENT LEADERBOARD (Ranked by Avg Mass) 🏆")
    print("="*60)
    print(f"Total Valid Games: {valid_games}\n")

    if valid_games > 0:
        # Calculate averages and store in a list for sorting
        leaderboard_data = []
        for bot in unique_bots:
            avg_mass = total_mass[bot] / \
                total_instances[bot] if total_instances[bot] > 0 else 0.0
            wins = win_counts[bot]
            win_rate = (wins / valid_games) * 100
            leaderboard_data.append((bot, avg_mass, wins, win_rate))

        # Sort by Average Mass (Highest to Lowest)
        leaderboard_data.sort(key=lambda x: x[1], reverse=True)

        # Print table header
        print(f"{'Bot Name':<20} | {'Avg Mass':>10} | {'Wins':>6} | {'Win Rate':>8}")
        print("-" * 60)

        # Print rows
        for bot, avg_mass, wins, win_rate in leaderboard_data:
            print(f"{bot:<20} | {avg_mass:>10.2f} | {wins:>6} | {win_rate:>7.1f}%")
    else:
        print("No valid games completed.")


if __name__ == "__main__":
    main()
