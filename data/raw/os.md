# Operating Systems — Quick Notes

## Process Management

A **process** is a program in execution. The OS manages processes through the Process Control Block (PCB),
which stores the PID, state, program counter, registers, and memory limits.

### States
- New → Ready → Running → Waiting → Terminated

## Memory Management

Virtual memory allows each process to behave as if it has exclusive access to main memory.
Paging divides virtual memory into fixed-size pages mapped to physical frames.

### Page Replacement Algorithms
- FIFO
- LRU (Least Recently Used)
- Optimal (Belady's)

## File Systems

The file system organises data on storage. Common structures:
- FAT32, NTFS, ext4
- Inodes store metadata; directory entries map names to inodes.

## Synchronisation

Race conditions occur when multiple threads access shared data concurrently.
Solutions: mutexes, semaphores, monitors, spinlocks.

### Classic Problems
- Producer-Consumer
- Readers-Writers
- Dining Philosophers
