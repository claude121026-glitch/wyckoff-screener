import sys, numpy as np, pandas as pd
g = pd.read_csv(sys.argv[1]); pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
keys = ["setups", "range_len", "quiet", "sos_rv", "direct", "ctx", "mkt", "rmult", "hold"]
print(f"combos: {len(g)}")
# ---- PRE-DECLARED selection: train on U1 2016-2021 only ----
elig = g[g.U1_train_n >= 80].copy()
top = elig.sort_values("U1_train_R", ascending=False).head(20)
cols = keys + ["U1_train_n", "U1_train_R", "U1_val_n", "U1_val_R", "U1_test_n", "U1_test_R", "U2_train_R", "U2_val_R", "U2_test_n", "U2_test_R"]
print("\n=== Top 20 by TRAIN (U1, 2016-2021) and how they did on unseen data ===")
print(top[cols].round(3).to_string(index=False))
print("\nTop-20 averages:", top[["U1_train_R", "U1_val_R", "U1_test_R", "U2_train_R", "U2_val_R", "U2_test_R"]].mean().round(3).to_dict())
# ---- does in-sample rank predict out-of-sample? ----
sp = lambda a, b: elig[a].rank().corr(elig[b].rank())
print(f"\nRank correlation across {len(elig)} combos: train->val {sp('U1_train_R','U1_val_R'):+.2f} | train->test {sp('U1_train_R','U1_test_R'):+.2f}"
      f" | U1 train -> U2 train {sp('U1_train_R','U2_train_R'):+.2f} | U1 train -> U2 test {sp('U1_train_R','U2_test_R'):+.2f}")
# ---- by setup family, distribution of out-of-sample results ----
print("\n=== Median avg R across all combos, by setup group ===")
print(elig.groupby("setups")[["U1_train_R", "U1_val_R", "U1_test_R", "U2_train_R", "U2_val_R", "U2_test_R"]].median().round(3).to_string())
print("\nShare of combos with positive TEST avg R:  U1 %.0f%%  U2 %.0f%%" % (100*(elig.U1_test_R > 0).mean(), 100*(elig.U2_test_R > 0).mean()))
# ---- pre-declared robustness screen: positive everywhere ----
per = ["U1_train", "U1_val", "U1_test", "U2_train", "U2_val", "U2_test"]
rob = g[np.all([(g[f"{p}_n"] >= 25) & (g[f"{p}_R"] > 0.05) for p in per], axis=0)]
print(f"\n=== Combos with avg R > +0.05 in ALL six period x universe slices (>=25 trades each): {len(rob)} of {len(g)} ===")
if len(rob):
    rob = rob.assign(worst=rob[[f"{p}_R" for p in per]].min(axis=1)).sort_values("worst", ascending=False)
    print(rob[keys + [f"{p}_R" for p in per] + [f"{p}_n" for p in ("U1_test", "U2_test")] + ["worst"]].head(15).round(3).to_string(index=False))
# ---- hindsight view (for contrast only) ----
h = g[(g.U1_test_n >= 30)].sort_values("U1_test_R", ascending=False).head(5)
print("\n=== HINDSIGHT ONLY: best 5 on the recent TEST period (U1) and their earlier record ===")
print(h[keys + ["U1_test_n", "U1_test_R", "U1_train_R", "U1_val_R", "U2_test_R"]].round(3).to_string(index=False))
