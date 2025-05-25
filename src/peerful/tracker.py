import asyncio
import json
from dataclasses import dataclass, asdict
from typing import Dict, Set, Optional, List
import logging
from asyncio import StreamReader, StreamWriter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class PeerInfo:
    """Information about a connected peer."""
    peer_id: str
    address: str
    port: int
    writer: StreamWriter

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'peer_id': self.peer_id,
            'address': self.address,
            'port': self.port
        }

class Tracker:
    def __init__(self, host: str = '127.0.0.1', port: int = 6881):
        self.host = host
        self.port = port
        self.swarms: Dict[str, Dict[str, PeerInfo]] = {}  # info_hash -> peer_id -> PeerInfo
        self._server = None

    async def start(self):
        """Start the tracker server."""
        self._server = await asyncio.start_server(
            self._handle_connection, self.host, self.port
        )
        
        addr = self._server.sockets[0].getsockname()
        logger.info(f'Tracker serving on {addr}')
        
        async with self._server:
            await self._server.serve_forever()

    async def _handle_connection(self, reader: StreamReader, writer: StreamWriter):
        """Handle incoming peer connections."""
        peer_address = writer.get_extra_info('peername')
        logger.info(f'New connection from {peer_address}')
        
        try:
            while True:
                # Read message length (4 bytes)
                length_bytes = await reader.read(4)
                if not length_bytes:
                    break
                
                length = int.from_bytes(length_bytes, 'big')
                if length > 16384:  # Max message size 16KB
                    raise ValueError("Message too large")
                
                # Read message
                data = await reader.read(length)
                if not data:
                    break
                
                # Parse and handle message
                message = json.loads(data.decode())
                await self._handle_message(message, writer, peer_address)
                
        except Exception as e:
            logger.error(f'Error handling connection: {e}')
        finally:
            self._remove_peer(writer)
            writer.close()
            await writer.wait_closed()
            logger.info(f'Connection closed for {peer_address}')

    async def _handle_message(self, message: dict, writer: StreamWriter, peer_address: tuple):
        """Handle incoming tracker messages."""
        try:
            message_type = message.get('type')
            if message_type == 'announce':
                await self._handle_announce(message, writer, peer_address)
            elif message_type == 'get_peers':
                await self._handle_get_peers(message, writer)
            else:
                logger.warning(f'Unknown message type: {message_type}')
        except Exception as e:
            logger.error(f'Error handling message: {e}')
            await self._send_error(writer, str(e))

    async def _handle_announce(self, message: dict, writer: StreamWriter, peer_address: tuple):
        """Handle peer announce message."""
        info_hash = message['info_hash']
        peer_id = message['peer_id']
        port = message['port']
        
        # Create peer info
        peer = PeerInfo(
            peer_id=peer_id,
            address=peer_address[0],
            port=port,
            writer=writer
        )
        
        # Add to swarm
        if info_hash not in self.swarms:
            self.swarms[info_hash] = {}
        self.swarms[info_hash][peer_id] = peer
        
        logger.info(f'Peer {peer_id} announced for {info_hash}')
        
        # Send peer list
        await self._send_peer_list(info_hash, writer, exclude_peer_id=peer_id)

    async def _handle_get_peers(self, message: dict, writer: StreamWriter):
        """Handle get peers request."""
        info_hash = message['info_hash']
        await self._send_peer_list(info_hash, writer)

    async def _send_peer_list(self, info_hash: str, writer: StreamWriter, exclude_peer_id: Optional[str] = None):
        """Send list of peers in a swarm."""
        peers = self.swarms.get(info_hash, {})
        peer_list = [
            p.to_dict() for p in peers.values()
            if not exclude_peer_id or p.peer_id != exclude_peer_id
        ]
        
        response = {
            'type': 'peer_list',
            'peers': peer_list
        }
        
        await self._send_message(writer, response)

    async def _send_error(self, writer: StreamWriter, error: str):
        """Send error message to peer."""
        response = {
            'type': 'error',
            'error': error
        }
        await self._send_message(writer, response)

    async def _send_message(self, writer: StreamWriter, message: dict):
        """Send message to peer."""
        try:
            data = json.dumps(message).encode()
            length = len(data).to_bytes(4, 'big')
            writer.write(length + data)
            await writer.drain()
        except Exception as e:
            logger.error(f'Error sending message: {e}')

    def _remove_peer(self, writer: StreamWriter):
        """Remove peer from all swarms."""
        for swarm in self.swarms.values():
            to_remove = None
            for peer in swarm.values():
                if peer.writer == writer:
                    to_remove = peer
                    break
            if to_remove:
                del swarm[to_remove.peer_id]

async def main():
    """Run the tracker server."""
    tracker = Tracker()
    await tracker.start()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info('Tracker stopped by user') 