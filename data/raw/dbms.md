# DBMS — Core Concepts

## ACID Properties

| Property    | Meaning                                               |
|-------------|-------------------------------------------------------|
| Atomicity   | All or nothing — transaction fully commits or rolls back |
| Consistency | DB moves from one valid state to another              |
| Isolation   | Concurrent transactions don't interfere               |
| Durability  | Committed data survives crashes                       |

## Indexing

A B-Tree index allows O(log n) lookups. Used by most RDBMS by default.
A Hash index allows O(1) equality lookups but cannot do range queries.

## Normalisation

- 1NF: Atomic values, no repeating groups.
- 2NF: 1NF + no partial dependencies on composite key.
- 3NF: 2NF + no transitive dependencies.
- BCNF: Every determinant is a candidate key.

## Transactions

```sql
BEGIN;
UPDATE accounts SET balance = balance - 100 WHERE id = 1;
UPDATE accounts SET balance = balance + 100 WHERE id = 2;
COMMIT;
```

## CAP Theorem

A distributed system can guarantee at most 2 of:
- **Consistency** — every read receives the latest write
- **Availability** — every request receives a response
- **Partition Tolerance** — system works despite network splits
