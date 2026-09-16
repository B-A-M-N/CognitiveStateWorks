# Platform support

The beta StateWork control plane is POSIX-oriented and tested on Linux. Its
packet authority uses POSIX advisory locks, SQLite/WAL-compatible deployment
assumptions, and atomic rename semantics. Windows is unsupported until those
contracts are replaced and tested.
