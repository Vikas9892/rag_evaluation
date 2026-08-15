# Data Structures — Core Notes

## Arrays and Dynamic Arrays

A static array stores elements contiguously, giving O(1) random access by index because the
address of element i is a single multiplication away from the base pointer. Insertion in the
middle is O(n) because every later element must shift.

A dynamic array (vector, ArrayList) grows by allocating a larger buffer and copying. Growth is
usually geometric — doubling — which makes append O(1) amortised: n appends cost O(n) copying
in total, spread across the appends.

## Linked Lists

A singly linked list stores each element in a node holding a value and a pointer to the next
node. Insertion and deletion at a known position are O(1) because only pointers change, but
access by index is O(n) because the list must be walked.

A doubly linked list adds a previous pointer, allowing backward traversal and O(1) deletion
given only a node reference. The cost is one extra pointer per node and more bookkeeping on
every update.

Linked lists lose to arrays in practice far more often than the asymptotics suggest, because
each node is a separate allocation and traversal defeats the CPU cache.

## Stacks and Queues

A stack is last-in-first-out. Push and pop are O(1). Stacks back function call frames,
expression evaluation, and depth-first traversal.

A queue is first-in-first-out. Enqueue and dequeue are O(1) when implemented over a circular
buffer or a linked list. Queues back breadth-first traversal and producer-consumer pipelines.

A deque allows insertion and removal at both ends in O(1) and generalises both.

## Hash Tables

A hash table maps keys to buckets using a hash function, giving O(1) average lookup, insertion
and deletion. Worst case degrades to O(n) when many keys collide into one bucket.

Collisions are resolved by chaining — each bucket holds a list — or by open addressing, where
a probe sequence finds the next free slot. Open addressing is more cache-friendly but suffers
from clustering and cannot delete without tombstones.

The load factor is the ratio of entries to buckets. Exceeding it triggers a resize and a full
rehash, which is why a single insertion can occasionally cost O(n).

## Binary Search Trees

A binary search tree keeps every left subtree smaller than its node and every right subtree
larger, so search, insertion and deletion are O(log n) on a balanced tree and O(n) on a
degenerate one that has become a linked list.

Self-balancing variants keep the height logarithmic. An AVL tree rebalances aggressively with
rotations and keeps height closer to optimal, favouring lookup-heavy workloads. A red-black
tree rebalances more loosely, doing fewer rotations per update, which favours write-heavy
workloads.

## Heaps and Priority Queues

A binary heap is a complete binary tree stored in an array, where every parent compares
favourably to its children. In a min-heap the smallest element is at the root.

Peek is O(1), insertion and extraction are O(log n) because an element sifts up or down one
level at a time. Building a heap from n elements is O(n), not O(n log n), because most nodes
are near the leaves and sift down only a little.

## Tries

A trie stores strings by character along tree edges, so lookup costs O(m) in the length of the
key rather than O(log n) in the number of keys. Every node on a path shares a common prefix,
which is what makes prefix search and autocomplete natural.

The cost is memory: a naive trie allocates a child array per node regardless of how few
children exist.

## Graphs

A graph is a set of vertices and edges. An adjacency list stores each vertex's neighbours and
uses O(V + E) space, which suits sparse graphs. An adjacency matrix stores a V by V grid,
using O(V squared) space but answering "is there an edge" in O(1), which suits dense graphs.

Graphs may be directed or undirected, and weighted or unweighted. A directed acyclic graph has
no cycles and can be topologically ordered, which is what makes build systems and task
schedulers expressible as graphs.
