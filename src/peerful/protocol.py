import enum
import json
import hashlib
import os
from dataclasses import dataclass
from typing import Optional, Dict, Any

PIECE_SIZE = 16384  # 16KB chunks
PROTOCOL_ID = b'PF_P2P_1.0'

class MessageType(enum.IntEnum):
    HANDSHAKE = 0
    KEEPALIVE = 1
    CHOKE = 2
    UNCHOKE = 3
    INTERESTED = 4
    NOT_INTERESTED = 5
    HAVE = 6
    REQUEST = 7
    PIECE = 8
    CANCEL = 9

@dataclass
class Message:
    type: MessageType
    payload: Optional[bytes] = None

    def serialize(self) -> bytes:
        """Serialize the message to bytes."""
        if self.type == MessageType.HANDSHAKE:
            return self.payload if self.payload else b''
        
        length = len(self.payload) + 1 if self.payload else 1
        message = length.to_bytes(4, 'big')
        message += bytes([self.type])
        
        if self.payload:
            message += self.payload
            
        return message

    @classmethod
    def deserialize(cls, data: bytes) -> tuple['Message', int]:
        """Deserialize bytes into a Message object."""
        if len(data) < 4:
            return None, 0
            
        length = int.from_bytes(data[:4], 'big')
        if len(data) < length + 4:
            return None, 0
            
        msg_type = MessageType(data[4])
        payload = data[5:length+4] if length > 1 else None
        
        return cls(type=msg_type, payload=payload), length + 4

def create_handshake(info_hash: bytes, peer_id: bytes) -> Message:
    """Create a handshake message."""
    payload = (
        PROTOCOL_ID +
        info_hash +
        peer_id
    )
    return Message(MessageType.HANDSHAKE, payload)

def generate_peer_id() -> bytes:
    """Generate a unique peer ID."""
    random_suffix = os.urandom(12)
    return b'-PF0001-' + random_suffix

def calculate_piece_hash(data: bytes) -> bytes:
    """Calculate SHA1 hash of a piece."""
    return hashlib.sha1(data).digest()

def calculate_info_hash(info: Dict[str, Any]) -> bytes:
    """Calculate info hash from metadata."""
    info_encoded = json.dumps(info, sort_keys=True).encode()
    return hashlib.sha1(info_encoded).digest() 