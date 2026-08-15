# Distributed Systems — Core Notes

## Why Distribution Is Hard

A distributed system is one where a machine you have never heard of can fail and stop your work.
The difficulty is not concurrency but partial failure: a request that times out may have been
lost, may be queued, or may have already succeeded with the reply lost on the way back.

The network is not reliable, latency is not zero, bandwidth is not infinite and the topology
changes. Designs that assume otherwise fail in production rather than in testing.

## Replication

Replication keeps copies of data on several nodes for durability and read throughput.

Single-leader replication routes every write to one node which ships a log to followers. It
gives a simple consistency story and makes the leader a bottleneck and a failover problem.

Multi-leader replication accepts writes anywhere and must resolve conflicting concurrent edits,
usually with last-write-wins, version vectors, or application-specific merge rules.

Leaderless replication writes to several replicas at once and reads from several, using quorums
to overlap. With N replicas, W writes and R reads, choosing W plus R greater than N guarantees
a read sees the latest write.

## Consensus

Consensus is agreement on a single value among nodes that may crash. Raft and Paxos both solve
it; Raft is structured around an explicit leader election and an append-only log because it was
designed to be understandable.

A consensus round needs a majority quorum, which is why clusters are sized at odd numbers: five
nodes tolerate two failures, and adding a sixth tolerates no more while adding a vote to
collect.

The FLP result proves no deterministic algorithm can guarantee consensus in an asynchronous
network with even one faulty process. Practical systems sidestep it with timeouts, accepting
that a slow node is indistinguishable from a dead one.

## Sharding

Sharding splits data across nodes so each holds a subset, allowing writes to scale beyond one
machine.

Range sharding keeps keys ordered, which makes range scans cheap but creates hotspots when
traffic concentrates — sharding by timestamp sends every new write to the same shard.

Hash sharding distributes evenly and destroys range locality. Consistent hashing places nodes
and keys on a ring so that adding or removing a node moves only the keys in one arc, rather
than remapping everything as a plain modulo would.

## Load Balancing

A load balancer spreads requests across instances. Round robin is simple and ignores load;
least-connections favours instances that are keeping up; consistent hashing routes the same
client to the same instance, which matters when that instance holds a warm cache.

Health checks decide which instances receive traffic. A check that is too shallow keeps a
broken instance in rotation; one that is too deep takes healthy instances out because a
downstream dependency is slow.

## Caching

A cache trades staleness for latency. Cache-aside has the application read the cache, fall
through to the database on a miss and populate the cache. Write-through updates both on every
write, keeping them consistent at the cost of write latency.

Cache invalidation is hard because the correct moment to evict depends on knowledge the cache
does not have. A time-to-live is the pragmatic answer: it bounds staleness without requiring
the cache to understand the data.

A cache stampede occurs when a popular key expires and every request misses at once, all
hitting the database together. Request coalescing or a randomised jitter on expiry prevents it.

## Message Queues

A queue decouples producers from consumers, absorbs bursts, and lets the two scale
independently. It converts a synchronous dependency into an asynchronous one, which removes a
failure mode and adds the problem of knowing whether work was done.

Delivery guarantees are at-most-once, at-least-once, or exactly-once. At-least-once is what
most systems actually provide, which is why consumers should be idempotent — processing the
same message twice must be harmless.

A dead-letter queue collects messages that repeatedly fail, so one poison message cannot block
a partition forever.

## Idempotency

An idempotent operation has the same effect applied once or many times. Setting a value is
idempotent; incrementing one is not.

Idempotency is what makes retries safe, and retries are what make an unreliable network
tolerable. The usual implementation is an idempotency key: the client sends a unique
identifier, and the server records it so a repeat is recognised and ignored.
