# SlowBurn: formal model and results

> **NEEDS HUMAN REVIEW.** Every proof in this file was written by the coding agent and has a
> matching numerical check in `tests/test_theory.py`, `tests/test_retention_dp.py` and
> `tests/test_retention_policies.py` (`slowburn theory-check` writes the tightness report to
> `results/theory/`). The checks support the statements; they do not replace a proof review.
> Please check each proof before anything here goes into the paper.

## 1. Model

* **Time and snapshots.** Days are numbered t = 0, 1, 2, .... One snapshot is taken at the end of
  every day; the snapshot of day j is called *j*.
* **Attack.** The attack starts on day s (unknown) and first damages data during day s. Snapshot
  j is **clean iff j < s**.
* **Discovery.** The attack is discovered on day t_d = s + d, with delay d >= 0.
* **Retention.** A policy holds a set R_t of snapshot days after day t, with |R_t| <= K (the
  budget), t ∈ R_t (today's snapshot is always kept), and R_t ⊆ R_{t-1} ∪ {t} (deleted snapshots
  never come back: the policy is online).
* **Loss.** If R_{t_d} contains a clean snapshot, let j* = max{j ∈ R_{t_d} : j < s}. The clean
  work lost is g = s - 1 - j* days (0 when the snapshot of day s - 1 survived), and a whole-system
  restore to j* discards W = t_d - j* = g + d + 1 days. If no clean snapshot is held, the loss is
  a penalty P (asymmetric loss) or s (symmetric loss: as if a clean copy of day -1 existed).
* **Posterior.** Inference provides π_t(s) = P(start = s | evidence up to t) for s <= t, plus the
  mass of "not started". The retention decision uses it conditioned on "not discovered by t":
  π̃_t(s) ∝ π_t(s) · S_D(t - s), where S_D(k) = P(delay > k) is an *assumed* discovery-delay
  distribution (an input, swept and misspecified in the evaluation). This assumes the discovery
  time is independent of the evidence given s. The "not started" mass costs nothing.

## 2. Proposition 1 (fixed recent windows fail, whatever the detector)

**Proposition 1.** Keep-last-N holds R_t = {t - N + 1, ..., t} (once t >= N - 1). At discovery
t_d = s + d >= N - 1 it holds a clean snapshot if and only if d <= N - 2. Hence for every
d >= N - 1, and in particular every d >= N, keep-last-N retains **zero** clean snapshots,
for any detector and any evidence.

*Proof.* The oldest held snapshot at t_d is t_d - N + 1 = s + d - N + 1. A held snapshot is clean
iff it is < s, which holds for the oldest one iff d - N + 1 < 0, i.e. d <= N - 2. Keep-last-N
never reads the evidence, so no detector changes R_{t_d}. ∎

*Check.* `tests/test_retention_policies.py::test_proposition_1_*` (all N in {3,5,8}, d in
{0,2,5,8,12}) and every keep-last-N row of every retention experiment with d >= K - 1
(`tests/test_retention_experiment.py`, and the column `clean_snapshot_retained` in the results).

## 3. Theorem 2 (guarantee without a detector, and the horizon limit)

Detector-free retention cannot know s, so the best it can do is a schedule whose held ages are
spread geometrically. We prove a guarantee for the Tower-of-Hanoi (ToH) rotation, the classical
geometric schedule (prior practice; our prior-only policy is compared against it empirically),
and a lower bound that no policy can beat.

**ToH with K media.** Number days n = t + 1 >= 1 and let tz(n) be the number of trailing zero
bits of n. Day n goes to medium min(tz(n), K - 1); every medium keeps only its newest snapshot.
At "time" N the held days are L_k(N) = max{n <= N : tz(n) = k} for k <= K - 2, and
L_top(N) = max{n <= N : tz(n) >= K - 1}.

**Lemma A.** For every i in {0, ..., K - 1} with N >= 2^i, ToH holds
M_i(N) = max{n <= N : 2^i divides n}.

*Proof.* Let k = tz(M_i) >= i. If k <= K - 2, no n in (M_i, N] has tz(n) = k (such n would be
a multiple of 2^k, hence of 2^i, contradicting the maximality of M_i), so M_i = L_k(N). If
k >= K - 1, the same argument with "tz(n) >= K - 1" gives M_i = L_top(N). ∎

**Theorem 2(a) (achievability).** Let K >= 2 and let the attack start on day s and be
discovered after delay d. If d = 0 and s >= 1, ToH holds the snapshot of day s - 1 (g = 0, W = 1).
If 1 <= d <= 2^(K-2) - 1 and s >= 2d (enough history), ToH holds a clean snapshot at
discovery with clean work lost g <= 2d - 1 and whole-system work lost W = g + d + 1 <= 3d.

*Proof.* In 1-based numbering let S = s + 1 (first damaged day), N = t_d + 1, so d = N - S. A
held day n is clean iff n < S, and g = S - 1 - n for the newest clean held n. Let j = 0 if
d = 0, else j = ⌊log2 d⌋ + 1, so that d < 2^j <= 2d (for d >= 1) and, because
d <= 2^(K-2) - 1, j <= K - 2. The window I = [S, N] has d + 1 <= 2^j integers, so it contains
at most one multiple of 2^j.

* *Case 1: I contains no multiple of 2^j.* Then M_j(N) < S, it is held (Lemma A, j <= K - 1),
  and M_j(N) >= N - 2^j + 1. Hence g <= S - 1 - (N - 2^j + 1) = 2^j - d - 2 < 2^j - 1.
* *Case 2: I contains exactly one multiple m of 2^j.* Put n* = m - 2^j. Since m <= N and
  N - S = d < 2^j, n* < S, and since m >= S, n* >= S - 2^j, i.e. g <= 2^j - 1. It remains to
  show n* is held.
  - If 2^(j+1) divides m, then tz(n*) = j exactly; the next day with tz = j after n* is
    n* + 2^(j+1) = m + 2^j > N (because N - m <= d < 2^j), and m itself has tz > j. So
    n* = L_j(N), held because j <= K - 2.
  - Otherwise tz(m) = j and n* = m - 2^j is a multiple of 2^(j+1); the next multiple of 2^(j+1)
    is m + 2^j > N, so n* = M_(j+1)(N), held by Lemma A because j + 1 <= K - 1.

  In both sub-cases n* >= S - 2^j >= 1 needs S > 2^j, which s >= 2d guarantees (2^j <= 2d < S).

So g <= 2^j - 1 <= 2d - 1 for d >= 1, and W = g + d + 1 <= 3d. For d = 0, j = 0 and the same
argument gives g <= 0, i.e. g = 0 and W = 1. ∎

**Theorem 2(b) (horizon limit, any policy).** Fix a time t and a ratio c > 1. If a held set of
at most K snapshots (including today's) guarantees, for every delay d in {0, ..., D}, a clean
snapshot with whole-system work lost W <= c(d + 1), then

    K >= log_c( (c - 1)(D + 1) + c ).

This holds for any policy, online or not, with or without a detector that cannot rule out any
start in the window.

*Proof.* Describe the held snapshots by their ages a = t - j. Today's snapshot (age 0) is never
clean for d >= 0. For start s = t - d a held snapshot is clean iff a > d, and then W = a. So the
requirement is: for every d <= D there is a held age a with d < a <= c(d + 1). Let the useful
ages be a_1 < ... < a_m (m <= K - 1). Covering d = 0 needs a_1 <= c. If a_1..a_i cover all
d <= a_i - 1, then d = a_i needs an age in (a_i, c(a_i + 1)], so a_(i+1) <= c(a_i + 1) (an
optimal set uses the largest allowed next age). With b_i = a_i + c/(c - 1) this reads
b_(i+1) <= c b_i, and b_1 <= c + c/(c - 1) = c²/(c - 1), so b_m <= c^(m+1)/(c - 1). Covering
d = D needs a_m >= D + 1, i.e. b_m >= D + 1 + c/(c - 1). Combining,
c^(m+1) >= (c - 1)(D + 1) + c, so m >= log_c((c - 1)(D + 1) + c) - 1 and K >= m + 1. ∎

*Reading.* With ratio c = 3, Theorem 2(a) shows ToH covers delays up to D = 2^(K-2) - 1,
i.e. K = log2(D + 1) + 2 snapshots, while Theorem 2(b) says no policy can use fewer than
log3(2D + 5). ToH is therefore within a constant factor (log 3 / log 2 ≈ 1.58) of the minimum
budget, and **delays far beyond about c^K days cannot be recovered at bounded loss by any
policy with budget K**: this is the hard limit the paper must state.

*Scope.* The guarantee is proved for the ToH schedule. The prior-only DP (SlowBurn's DP without
evidence) carries **no proven worst-case guarantee**: it minimises expected loss under the
assumed prior and discovery distribution. Its behaviour is compared against ToH empirically, and
under a misspecified prior in the sensitivity sweep.

*Checks.* `tests/test_theory.py`: (a) ToH replayed for K in {4, 5, 6, 8} over 600 days, every
(s, d) satisfying the conditions, asserting a clean snapshot and W <= max(1, 3d), with the
observed worst ratio max W / (3d) reported (tightness); (b) the minimum number of useful ages
found by exhaustive search for small D and c in {2, 3, 4}, compared with the bound.

## 4. Theorem 3 (per-decision optimality of the DP)

**Theorem 3.** Fix a day t, the held set H (including today's snapshot t), a budget K, a
penalty P (or the symmetric loss) and π̃_t. Among all J ⊆ H with t ∈ J and |J| <= K,
`dp_select` returns a J that minimises the expected loss

    ℓ(J) = Σ_s π̃_t(s) L(s, J),

where L(s, J) = s - 1 - max{j ∈ J : j < s} if J holds a clean snapshot, else P (or s).
The algorithm runs in O(m² K) time for m = |H| candidates.

*Proof.* Sort J as j_1 < ... < j_k (j_k = t). For s <= j_1 no held snapshot is clean, so the
cost is P·Π(j_1) with Π(a) = Σ_{s<=a} π̃(s) (or Σ_{s<=a} π̃(s)·s for the symmetric loss). For
j_i < s <= j_(i+1) the newest clean held snapshot is j_i, costing C(j_i, j_(i+1)) with
C(a, b) = Σ_{a<s<=b} π̃(s)(s - 1 - a); and for s > j_k the cost is C(j_k, ∞). Starts after t
and "not started" have zero cost. Hence ℓ(J) = P·Π(j_1) + Σ_i C(j_i, j_(i+1)) + C(j_k, ∞): a
sum of terms that each depend on one element or on two consecutive elements of J. Let
f(i, n) be the minimum over n-element chains ending at the i-th candidate c_i of the cost up to
c_i. Then f(i, 1) = P·Π(c_i) and f(i, n) = min_{h<i} f(h, n - 1) + C(c_h, c_i), because the
cost of a chain is its prefix cost plus a term depending only on its last two elements
(optimal substructure). The answer is min_{n<=K} f(m, n) + C(c_m, ∞) with c_m = t, which also
enforces t ∈ J. Prefix sums make each C and Π O(1), giving O(m² K). ∎

*Scope, stated exactly.* (i) The optimality is **myopic, per decision**: given the snapshots
currently held and the stated discovery distribution, the DP picks the best subset for this
day. It does not plan for future deletions or snapshots, and the sequence of such decisions is
**not** claimed to be globally optimal over time. (ii) It is optimal for the model's loss (clean
work lost in whole-system terms, plus the penalty); the selective-restore stage and its
posterior quantile are separate and are evaluated, not optimised, here. (iii) The conditioning
on non-discovery uses the assumed delay distribution, which may be misspecified.

*Check.* `tests/test_retention_dp.py`: the DP's expected loss equals the exhaustive minimum on
120 random instances (random posteriors, candidate sets, budgets; penalty in {none, 5, 50}),
plus hand-computed losses and the directional checks (heavy penalty never keeps a newer oldest
snapshot; a certain start keeps day s - 1).
