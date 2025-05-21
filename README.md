# PeerFul - Simple P2P File Sharing

A simplified peer-to-peer file sharing system in Python. Purpose is to learn how more scalable architectures work as compared to more centralized methods of information transfer.

- Peer discovery and management
- File chunking and piece exchange
- Distributed file sharing
- Basic wire protocol

## Requirements

- Python 3.8+
- Dependencies listed in `requirements.txt`

## Installation

```bash
# Create a virtual environment (recommended)
python -m venv peerful
source peerful/bin/activate  # On Windows: peerful\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Components

1. **Peer**: Represents a node in the P2P network
2. **Tracker**: Simple tracker server for peer discovery
3. **FileManager**: Handles file chunking and piece management
4. **Protocol**: Basic wire protocol for peer communication

## Usage

Start the tracker:
```bash
python -m peerful.tracker
```

Share a file:
```bash
python -m peerful.peer share <filepath>
```

Download a file:
```bash
python -m peerful.peer download <info_hash> <output_path>
```

## Architecture

The system uses a simplified version of the BitTorrent protocol:

1. Files are split into fixed-size pieces
2. Each piece is hashed for integrity
3. Peers connect to tracker to discover other peers
4. Peers exchange pieces directly with each other
5. Files are verified using piece hashes

## Network Protocol

Basic message types:
- HANDSHAKE: Initial peer connection
- REQUEST: Request a specific piece
- PIECE: Send a piece of the file
- HAVE: Announce available pieces

## Learning Objectives

This implementation helps understand:
- How P2P networks work
- Basic distributed systems concepts
- Network protocols and peer communication
- File chunking and verification
- Asynchronous I/O in Python