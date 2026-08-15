# Algorithms and Complexity — Core Notes

## Asymptotic Notation

Big-O describes an upper bound on growth: an O(n log n) algorithm never grows faster than
n log n up to a constant factor, for large enough input. Big-Omega describes a lower bound and
Big-Theta describes a tight bound where the two coincide.

Asymptotics deliberately discard constants and lower-order terms, which is why an O(n squared)
algorithm can beat an O(n log n) one on small inputs. Insertion sort is faster than merge sort
below roughly a few dozen elements, and real sorting implementations switch to it there.

## Sorting

Merge sort divides the array, sorts each half and merges, running in O(n log n) in every case.
It is stable — equal elements keep their relative order — but needs O(n) auxiliary space.

Quicksort partitions around a pivot and recurses. It averages O(n log n) with excellent cache
behaviour and sorts in place, but degrades to O(n squared) when the pivot is consistently poor.
Randomised or median-of-three pivots make that case vanishingly unlikely.

Heapsort runs in O(n log n) in the worst case and sorts in place, but is not stable and has
worse locality than quicksort.

No comparison sort can beat O(n log n) in the worst case: there are n factorial possible
orderings and each comparison distinguishes at most two branches, so the decision tree has
height at least log(n!), which is Theta(n log n).

Counting sort and radix sort break that bound by not comparing — they exploit the structure of
the keys — and run in O(n + k) and O(d(n + k)) respectively.

## Searching

Binary search finds a value in a sorted array in O(log n) by halving the search interval. It
requires random access, which is why it works on arrays and not on linked lists.

The classic bug is computing the midpoint as (low + high) / 2, which overflows on large
indices. Writing it as low + (high - low) / 2 avoids the overflow.

## Graph Traversal

Breadth-first search explores a graph level by level using a queue, and on an unweighted graph
it finds the shortest path in edges. It runs in O(V + E).

Depth-first search follows a path to exhaustion before backtracking, using a stack or
recursion, also in O(V + E). It underlies cycle detection, topological sorting and connected
component labelling.

## Shortest Paths

Dijkstra's algorithm finds shortest paths from a source in a graph with non-negative edge
weights, running in O((V + E) log V) with a binary heap. It fails with negative weights because
it finalises a vertex the first time it is reached and never revisits that decision.

Bellman-Ford handles negative weights in O(V times E) by relaxing every edge V-1 times, and it
detects a negative cycle when a further relaxation still improves a distance.

A-star extends Dijkstra with a heuristic estimate of the remaining distance. It finds an
optimal path when the heuristic never overestimates.

## Dynamic Programming

Dynamic programming solves problems with overlapping subproblems and optimal substructure by
solving each subproblem once and reusing the answer.

Memoisation is top-down: recurse naturally and cache results. Tabulation is bottom-up: fill a
table in dependency order, which avoids recursion depth limits and often improves locality.

Naive Fibonacci is exponential because it recomputes the same values repeatedly; memoised it is
linear. The knapsack problem, edit distance and longest common subsequence are the standard
worked examples.

## Greedy Algorithms

A greedy algorithm takes the locally best option at each step and never reconsiders. It is
correct only when the problem has the greedy-choice property, meaning a locally optimal choice
is part of some global optimum.

Interval scheduling by earliest finish time is greedy and optimal. The 0/1 knapsack is not:
taking the best value-per-weight item first can leave capacity that no remaining item fits,
which is why it needs dynamic programming.

## Amortised Analysis

Amortised analysis averages the cost of an operation across a sequence rather than looking at
the worst single case. A dynamic array's append is O(n) when it resizes but O(1) amortised,
because a resize doubling the capacity pays for the n appends that follow it.

This is different from average-case analysis, which averages over random inputs. Amortised
bounds hold for every sequence, including adversarial ones.
