# 9231 AS Level Further Mathematics Practice Paper Generation Prompt

You are generating a CAIE 9231 AS Level Further Mathematics practice paper from extracted and segmented past-paper data.

## Syllabus Reference
- 2026–2027 syllabus (Version 1, September 2023)
- Paper 1 + Paper 4 (Further Pure 1 + Further Probability & Statistics)

## AS Level Paper Structure
| Paper | Title                           | Duration    | Marks | Questions      | Weight (AS) |
|-------|---------------------------------|-------------|-------|----------------|-------------|
| P1    | Further Pure Mathematics 1      | 2 hours     | 75    | 6–8 compulsory | 60%         |
| P4    | Further Probability & Statistics| 1 hr 30 min | 50    | 5–7 compulsory | 40%         |

Note: P3 and P4 are alternatives — candidates take P1 with either P3 or P4.
P2 (Further Pure Mathematics 2) is A Level only.

## Prior Knowledge Required
- P1: 9709 Papers 1 and 3 (Pure Mathematics 1 & 3)
- P4: 9709 Papers 1, 3, 5, and 6 (Pure 1, Pure 3, P&S 1, P&S 2)

## Content Per Paper

### Paper 1 — Further Pure Mathematics 1 (75 marks)
Topics:
- 1.1 Roots of polynomial equations: Vieta's formulas for degree 2, 3, 4; substitutions to find related equations; symmetric functions of roots
- 1.2 Rational functions and graphs: sketch rational functions (numerator/denominator degree ≤ 2), oblique asymptotes, set of values taken (discriminant); relationships between y = f(x), y² = f(x), y = 1/f(x), y = |f(x)|, y = f(|x|)
- 1.3 Summation of series: standard results Σr, Σr², Σr³; method of differences (may require partial fractions); convergence and sum to infinity
- 1.4 Matrices: operations up to 3×3; singular/non-singular; determinants and inverses of 2×2 and 3×3; (AB)⁻¹ = B⁻¹A⁻¹; 2×2 matrices as geometric transformations (rotation, reflection, enlargement, stretch, shear); area scale factor = |det M|; invariant points and invariant lines
- 1.5 Polar coordinates: convert between Cartesian and polar; sketch polar curves (r ≥ 0); area of sector A = ½∫r² dθ
- 1.6 Vectors (3D): plane equations (ax + by + cz = d, r·n = p, r = a + λb + μc); vector product in component form; lines and planes (intersection, parallel, perpendicular foot, angles between); line of intersection of two planes; shortest distance between skew lines; common perpendicular
- 1.7 Proof by induction: summation, divisibility, matrix powers, sequences; conjecture and prove

### Paper 4 — Further Probability & Statistics (50 marks)
Topics (assumes 9709 P5 and P6 content):
- 4.1 Continuous random variables: piecewise PDFs; E[g(X)] = ∫ g(x) f(x) dx; PDF ↔ CDF; percentiles; CDF of related variables (e.g. Y = X³)
- 4.2 Inference using normal and t-distributions: t-test for population mean (small sample, unknown variance); pooled variance estimate from two samples (raw or summarised data); two-sample t-test, paired t-test, normal distribution test; select appropriate test for given situation
- 4.3 χ²-tests: fit theoretical distribution to data; goodness-of-fit test (combine classes so expected ≥ 5; correct df); contingency table independence test (combine rows/columns as needed; Yates' correction NOT required)
- 4.4 Non-parametric tests: when to use (non-normal populations); sign test (single-sample and paired); Wilcoxon signed-rank test (single-sample and matched-pairs, symmetric distributions only); Wilcoxon rank-sum test; normal approximations where appropriate; no tied ranks or observations equal to median under test
- 4.5 Probability generating functions: G(t) = E(tˣ); E(X) = G'(1); Var(X) = G''(1) + G'(1) − [G'(1)]²; PGFs for discrete uniform, binomial, geometric, Poisson; PGF of sum of independent variables = product of PGFs

## Representative Examples

### Paper 1
- Example 1 (1.1): The roots of x³ − 5x² + 3x + k = 0 are α, β, γ. Find α²β² + β²γ² + γ²α² in terms of k. [5]
- Example 2 (1.2): Sketch y = (2x² + 1)/(x − 1), showing asymptotes and turning points. Find the set of values not taken by y. [6]
- Example 3 (1.3): Use the method of differences to find Σᵣ₌₁ⁿ 1/[r(r+2)] and hence find the sum to infinity. [6]
- Example 4 (1.4): Find the eigenvalues and eigenvectors of [[3, 1], [1, 3]]. Hence write M = QDQ⁻¹. [7]
- Example 5 (1.4): Find all invariant lines through the origin for the transformation represented by [[2, 1], [4, 3]]. [4]
- Example 6 (1.5): The curve C has polar equation r = a(1 + cos θ). Sketch C and find the area enclosed. [6]
- Example 7 (1.6): Planes Π₁: 2x − y + 3z = 5 and Π₂: x + 2y − z = 3 intersect in line l. Find the equation of l and the angle between the planes. [7]
- Example 8 (1.6): Find the shortest distance between lines r = (1, 0, 2) + s(1, 1, 0) and r = (0, 2, 1) + t(2, 0, 1). [5]
- Example 9 (1.7): Prove by induction that 3²ⁿ − 1 is divisible by 8 for all positive integers n. [5]
- Example 10 (1.7): Given u₁ = 1, uₙ₊₁ = 3uₙ + 2, conjecture a formula for uₙ and prove it by induction. [6]

### Paper 4
- Example 1 (4.1): f(x) = kx(2 − x) for 0 ≤ x ≤ 2, 0 otherwise. Find k, E(X), Var(X), and the median. [7]
- Example 2 (4.1): The CDF of X is F(x) = x³/8 for 0 ≤ x ≤ 2. Find the CDF of Y = X² and hence its PDF. [5]
- Example 3 (4.2): A sample of 10 has mean 68.4 and variance 42.3. Test at 5% whether population mean = 72. [5]
- Example 4 (4.2): Two independent samples: n₁ = 8, x̄₁ = 15.2, s₁² = 4.1; n₂ = 10, x̄₂ = 13.5, s₂² = 5.3. Test at 5% whether population means differ (assume equal variances). [7]
- Example 5 (4.3): In 120 rolls of a die, outcomes are recorded. Test at 5% whether the die is fair using a χ²-test. [6]
- Example 6 (4.3): A 3×2 contingency table records preferences by gender. Test for independence at 5%, combining cells as necessary. [7]
- Example 7 (4.4): Use the Wilcoxon signed-rank test on 9 observations to test whether the population median = 15, at 5% significance. [5]
- Example 8 (4.4): Use the Wilcoxon rank-sum test on samples of size 6 and 7 to test for identical populations at 5% (two-tailed). [5]
- Example 9 (4.5): X ~ B(3, ½). Find the PGF of X. Hence verify E(X) = 1.5 and find Var(X). [5]
- Example 10 (4.5): X ~ Geom(p) and Y ~ Geom(p) are independent. Using PGFs, show X + Y has a negative binomial distribution. [5]

## Mark Scheme Notes
- Induction proofs must state: base case, inductive hypothesis, inductive step, conclusion
- All hypothesis tests must state H₀ and H₁, test statistic, critical value, and conclusion in context
- Pooled variance estimate must be shown clearly; degrees of freedom must be stated explicitly
- Sketches must show asymptotes, key intersections, and general shape — no detailed plotting required
- 3 s.f. for non-exact answers; 1 d.p. for angles in degrees unless specified

## Output Requirements
- Produce one full draft practice paper for the chosen route:(P1+P4)
- P1 = 75 marks (6–8 questions); P4 = 50 marks (5–7 questions)
- Provide mark allocation per question and sub-question
- P1: cover at least 5 of the 7 topics
- P4: cover all 5 topics, weight toward 4.1, 4.2, 4.3
- Vary command words: prove, show that, find, sketch, deduce, state, verify, calculate, interpret
- Questions may draw on assumed prior knowledge from 9709
- Do not copy any past question verbatim
- Align difficulty to genuine CAIE 9231 AS Level standard

<!-- AUTO-DATA-START -->
## Data-Driven Addendum (Auto-Generated)

Use this block as additional evidence from extracted data. Keep all subject-specific syllabus constraints from the handcrafted prompt above.

### Blueprint Scaffold Snapshot
- P1: target 2 questions, 75 total marks
- P4: target 2 questions, 50 total marks

### Representative Examples From Extracted Data
- Representative examples are currently mock placeholders. Add real PDFs and rerun extraction to populate subject-authentic examples.
<!-- AUTO-DATA-END -->
