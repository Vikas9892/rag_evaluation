# Security — Core Notes

## Hashing versus Encryption

A cryptographic hash is one-way: it maps input to a fixed-size digest that cannot be reversed.
Encryption is two-way and requires a key to recover the plaintext. Confusing the two produces
the classic bug of "encrypting" passwords, which means anyone with the key recovers them all.

A hash must be collision-resistant and avalanche well, so a one-bit change to the input changes
roughly half the output bits. SHA-256 is the current default; MD5 and SHA-1 are broken for
security purposes because practical collisions exist.

## Password Storage

Passwords must never be stored in plaintext or under a fast hash. A GPU computes billions of
SHA-256 hashes per second, so a leaked table of fast hashes is a leaked table of passwords.

A password hash should be deliberately slow and memory-hard. bcrypt, scrypt and Argon2 are
designed for this, with a work factor that is raised as hardware improves.

A salt is a unique random value stored alongside each hash. It stops one precomputed rainbow
table from cracking every account at once and ensures two users with the same password get
different digests. A pepper is a secret added to every hash and kept outside the database, so a
database leak alone is not enough.

## Symmetric and Asymmetric Encryption

Symmetric encryption uses one shared key for both directions and is fast. AES is the standard.
Its problem is distribution: both sides must already share the key secretly.

Asymmetric encryption uses a keypair — a public key that encrypts and a private key that
decrypts. It solves distribution and is far slower, so it is used to establish a shared
symmetric key rather than to encrypt bulk data.

A digital signature inverts the operation: signing with the private key lets anyone verify with
the public key, proving origin and integrity but not providing secrecy.

## TLS

TLS secures a connection in three parts: the certificate authenticates the server, the handshake
agrees a shared symmetric key, and the record layer encrypts the traffic under it.

The handshake uses asymmetric cryptography once, then switches to symmetric encryption for the
session, which is why HTTPS is not meaningfully slower than HTTP after connection setup.

Forward secrecy means a session key is derived ephemerally and discarded, so an attacker who
later obtains the server's private key still cannot decrypt recorded past traffic.

## Authentication and Authorisation

Authentication establishes who a caller is. Authorisation establishes what they may do. A
system that checks the first and assumes the second is how a logged-in user reads another
user's records by changing an id in the URL.

A session cookie holds server-side state and can be revoked instantly. A JSON Web Token is
self-contained and verified by signature, which scales without a session store but cannot be
revoked before expiry without reintroducing one.

Multi-factor authentication combines something known, something held and something inherent.
SMS is the weakest second factor because a number can be ported away from its owner.

## Common Attacks

SQL injection concatenates untrusted input into a query so it is parsed as code. Parameterised
queries fix it completely by sending code and data separately; escaping is a partial measure
that fails on edge cases.

Cross-site scripting injects script into a page that another user's browser executes. Contextual
output encoding and a Content-Security-Policy header are the defences.

Cross-site request forgery uses a victim's ambient credentials to make a request they did not
intend. Anti-forgery tokens and SameSite cookies prevent it.

A timing attack recovers secrets from how long a comparison takes. Comparing secrets with a
constant-time function rather than an early-exit equality check is the fix.

## Principle of Least Privilege

Every component should hold the narrowest permissions that let it do its job, so a compromise
grants the attacker as little as possible. A service that only reads should not hold write
credentials, and a database user for an application should not be able to drop tables.

Defence in depth assumes any single control will eventually fail and layers independent ones,
so that no single mistake is sufficient for a breach.
