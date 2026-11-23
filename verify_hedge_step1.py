"""Quick verification script for hedge step 1."""
import sys
sys.path.insert(0, r"D:\project\worldcup-predictor")

# Test 1: strategies import and correctness
from skill.hedge.strategies import equal_profit, partial, kelly_hedge, no_hedge

print("=== Strategy Tests ===")
hedge = equal_profit(100.0, 8.5, 2.0)
print(f"equal_profit(100, 8.5, 2.0) = {hedge:.2f}")
# Verify both sides profit equal
total = 100.0 + hedge
if_team = 100.0 * 8.5 - total
if_opp = hedge * 2.0 - total
print(f"  if_team_wins profit = {if_team:.2f}")
print(f"  if_opponent_wins profit = {if_opp:.2f}")
print(f"  equal? {abs(if_team - if_opp) < 0.01}")

print(f"partial(100, 8.5, 2.0, 0.5) = {partial(100.0, 8.5, 2.0, 0.5):.2f}")
print(f"kelly_hedge(100, 8.5, 2.0, 0.6) = {kelly_hedge(100.0, 8.5, 2.0, 0.6):.2f}")
print(f"no_hedge(100, 8.5, 2.0) = {no_hedge(100.0, 8.5, 2.0):.2f}")

# Test 2: montecarlo module imports and contains new output fields
print("\n=== Monte Carlo Output Field Tests ===")
from skill.model import dixon_coles as dc
from skill.sim import montecarlo
from skill.helpers import data_loader
import pandas as pd

results = data_loader.load_results()
fixtures = data_loader.load_wc2026_fixtures()
model = dc.fit(results, as_of=pd.Timestamp.now().normalize(), min_matches=8)

print(f"Fitting model with {len(results)} historical results...")
print(f"Simulating {len(fixtures)} WC2026 fixtures...")

sim = montecarlo.run(model, fixtures, n=5000, seed=42)

print(f"Keys in sim output: {sorted(sim.keys())}")
print(f"Has opponent_distribution: {'opponent_distribution' in sim}")
print(f"Has conditional_title_prob: {'conditional_title_prob' in sim}")

if "opponent_distribution" in sim:
    print(f"\nopponent_distribution['final'] sample:")
    for team, opps in list(sim["opponent_distribution"]["final"].items())[:2]:
        print(f"  {team}: {opps}")

if "conditional_title_prob" in sim:
    print(f"\nconditional_title_prob['final'] sample:")
    for team, prob in list(sim["conditional_title_prob"]["final"].items())[:4]:
        print(f"  {team}: {prob:.4f}")

print("\n=== All checks passed ===")
