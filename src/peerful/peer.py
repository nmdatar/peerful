import asyncio
import json
import logging
import random
from typing import Dict, Set, Optional, List, Tuple
from asyncio import StreamReader, StreamWriter
from dataclasses import dataclass

from .protocol import (
    Message, MessageType, generate_peer_id, create_handshake,
    PROTOCOL_ID, PIECE_SIZE
)
from .file_manager import FileManager, FileInfo

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class PeerConnection:
    """Represents a connection to another peer."""
    peer_id: str
    reader: StreamReader
    writer: StreamWriter
    bitfield: List[bool]
    choked: bool = True
    interested: bool = False

class Peer:
    def __init__(self, tracker_host: str = '127.0.0.1', tracker_port: int = 6881):
        self.peer_id = generate_peer_id().hex()
        self.tracker_host = tracker_host
        self.tracker_port = tracker_port
        self.port = random.randint(6882, 7000)  # Random port for peer connections
        
        self.file_manager: Optional[FileManager] = None
        self.info_hash: Optional[str] = None
        self.connections: Dict[str, PeerConnection] = {}
        self.pending_requests: Set[int] = set()
        
        self._server = None
        self._tracker_connection = None
        self._running = False

    async def start_server(self):
        """Start the peer server to accept incoming connections."""
        self._server = await asyncio.start_server(
            self._handle_peer_connection, '127.0.0.1', self.port
        )
        logger.info(f'Peer {self.peer_id} listening on port {self.port}')

    async def share_file(self, filepath: str) -> str:
        """Share a file and return its info hash."""
        self.file_manager = FileManager(filepath)
        file_info = await self.file_manager.initialize_for_sharing()
        self.info_hash = file_info.info_hash.hex()
        
        logger.info(f'Sharing file: {filepath}')
        logger.info(f'Info hash: {self.info_hash}')
        logger.info(f'File size: {file_info.file_size} bytes')
        logger.info(f'Pieces: {file_info.num_pieces}')
        
        # Start server and announce to tracker
        await self.start_server()
        await self._announce_to_tracker()
        
        return self.info_hash

    async def download_file(self, info_hash: str, output_path: str, file_info: FileInfo):
        """Download a file from peers."""
        self.info_hash = info_hash
        self.file_manager = FileManager(output_path)
        await self.file_manager.initialize_for_download(file_info)
        
        logger.info(f'Starting download: {output_path}')
        logger.info(f'Info hash: {info_hash}')
        
        # Start server and get peers from tracker
        await self.start_server()
        await self._get_peers_from_tracker()
        
        # Start download process
        self._running = True
        await self._download_loop()

    async def _announce_to_tracker(self):
        """Announce this peer to the tracker."""
        try:
            reader, writer = await asyncio.open_connection(
                self.tracker_host, self.tracker_port
            )
            self._tracker_connection = writer
            
            message = {
                'type': 'announce',
                'info_hash': self.info_hash,
                'peer_id': self.peer_id,
                'port': self.port
            }
            
            await self._send_tracker_message(writer, message)
            
            # Listen for peer list
            asyncio.create_task(self._handle_tracker_messages(reader, writer))
            
        except Exception as e:
            logger.error(f'Failed to connect to tracker: {e}')

    async def _get_peers_from_tracker(self):
        """Request peer list from tracker."""
        try:
            reader, writer = await asyncio.open_connection(
                self.tracker_host, self.tracker_port
            )
            self._tracker_connection = writer
            
            message = {
                'type': 'get_peers',
                'info_hash': self.info_hash,
                'peer_id': self.peer_id,
                'port': self.port
            }
            
            await self._send_tracker_message(writer, message)
            
            # Listen for peer list
            asyncio.create_task(self._handle_tracker_messages(reader, writer))
            
        except Exception as e:
            logger.error(f'Failed to connect to tracker: {e}')

    async def _send_tracker_message(self, writer: StreamWriter, message: dict):
        """Send message to tracker."""
        data = json.dumps(message).encode()
        length = len(data).to_bytes(4, 'big')
        writer.write(length + data)
        await writer.drain()

    async def _handle_tracker_messages(self, reader: StreamReader, writer: StreamWriter):
        """Handle messages from tracker."""
        try:
            while True:
                # Read message length
                length_bytes = await reader.read(4)
                if not length_bytes:
                    break
                
                length = int.from_bytes(length_bytes, 'big')
                data = await reader.read(length)
                
                message = json.loads(data.decode())
                if message['type'] == 'peer_list':
                    await self._handle_peer_list(message['peers'])
                    
        except Exception as e:
            logger.error(f'Error handling tracker messages: {e}')

    async def _handle_peer_list(self, peers: List[dict]):
        """Handle peer list from tracker."""
        logger.info(f'Received {len(peers)} peers from tracker')
        
        for peer_info in peers:
            if peer_info['peer_id'] != self.peer_id:
                asyncio.create_task(self._connect_to_peer(peer_info))

    async def _connect_to_peer(self, peer_info: dict):
        """Connect to a peer."""
        try:
            reader, writer = await asyncio.open_connection(
                peer_info['address'], peer_info['port']
            )
            
            # Send handshake
            handshake = create_handshake(
                bytes.fromhex(self.info_hash),
                bytes.fromhex(self.peer_id)  # Convert hex string back to bytes
            )
            writer.write(handshake.serialize())
            await writer.drain()
            
            # Create connection object
            connection = PeerConnection(
                peer_id=peer_info['peer_id'],
                reader=reader,
                writer=writer,
                bitfield=[False] * len(self.file_manager.piece_hashes)
            )
            
            self.connections[peer_info['peer_id']] = connection
            logger.info(f'Connected to peer {peer_info["peer_id"]}')
            
            # Send unchoke message immediately
            unchoke_message = Message(MessageType.UNCHOKE)
            writer.write(unchoke_message.serialize())
            await writer.drain()
            
            # If we're a seeder, send bitfield showing we have all pieces
            if self.file_manager and all(self.file_manager.bitfield):
                for i, have in enumerate(self.file_manager.bitfield):
                    if have:
                        have_payload = i.to_bytes(4, 'big')
                        have_message = Message(MessageType.HAVE, have_payload)
                        writer.write(have_message.serialize())
                        await writer.drain()
            
            # Handle messages from this peer
            asyncio.create_task(self._handle_peer_messages(connection))
            
        except Exception as e:
            logger.error(f'Failed to connect to peer {peer_info["peer_id"]}: {e}')

    async def _handle_peer_connection(self, reader: StreamReader, writer: StreamWriter):
        """Handle incoming peer connection."""
        peer_address = writer.get_extra_info('peername')
        logger.info(f'Incoming connection from {peer_address}')
        
        try:
            # Read handshake
            handshake_data = await reader.read(len(PROTOCOL_ID) + 40)
            # TODO: Parse and validate handshake
            
            # For now, create a basic connection
            connection = PeerConnection(
                peer_id=f"incoming_{peer_address[1]}",
                reader=reader,
                writer=writer,
                bitfield=[False] * len(self.file_manager.piece_hashes) if self.file_manager else []
            )
            
            self.connections[connection.peer_id] = connection
            
            # Send unchoke message immediately
            unchoke_message = Message(MessageType.UNCHOKE)
            writer.write(unchoke_message.serialize())
            await writer.drain()
            
            # If we're a seeder, send bitfield showing we have all pieces
            if self.file_manager and all(self.file_manager.bitfield):
                for i, have in enumerate(self.file_manager.bitfield):
                    if have:
                        have_payload = i.to_bytes(4, 'big')
                        have_message = Message(MessageType.HAVE, have_payload)
                        writer.write(have_message.serialize())
                        await writer.drain()
            
            await self._handle_peer_messages(connection)
            
        except Exception as e:
            logger.error(f'Error handling incoming connection: {e}')
            writer.close()

    async def _handle_peer_messages(self, connection: PeerConnection):
        """Handle messages from a peer."""
        buffer = b''
        
        try:
            while True:
                data = await connection.reader.read(4096)
                if not data:
                    break
                
                buffer += data
                
                # Parse messages from buffer
                while len(buffer) >= 4:
                    message, consumed = Message.deserialize(buffer)
                    if not message:
                        break
                    
                    buffer = buffer[consumed:]
                    await self._process_peer_message(connection, message)
                    
        except Exception as e:
            logger.error(f'Error handling peer messages: {e}')
        finally:
            self._remove_connection(connection.peer_id)

    async def _process_peer_message(self, connection: PeerConnection, message: Message):
        """Process a message from a peer."""
        if message.type == MessageType.UNCHOKE:
            connection.choked = False
            logger.info(f'Peer {connection.peer_id} unchoked us')
            
        elif message.type == MessageType.HAVE:
            piece_index = int.from_bytes(message.payload[:4], 'big')
            connection.bitfield[piece_index] = True
            logger.info(f'Peer {connection.peer_id} has piece {piece_index}')
            
        elif message.type == MessageType.REQUEST:
            await self._handle_piece_request(connection, message.payload)
            
        elif message.type == MessageType.PIECE:
            await self._handle_piece_received(connection, message.payload)

    async def _handle_piece_request(self, connection: PeerConnection, payload: bytes):
        """Handle piece request from peer."""
        piece_index = int.from_bytes(payload[:4], 'big')
        
        if self.file_manager:
            piece_data = self.file_manager.get_piece(piece_index)
            if piece_data:
                # Send piece
                piece_payload = piece_index.to_bytes(4, 'big') + piece_data
                piece_message = Message(MessageType.PIECE, piece_payload)
                connection.writer.write(piece_message.serialize())
                await connection.writer.drain()
                logger.info(f'Sent piece {piece_index} to {connection.peer_id}')

    async def _handle_piece_received(self, connection: PeerConnection, payload: bytes):
        """Handle received piece from peer."""
        piece_index = int.from_bytes(payload[:4], 'big')
        piece_data = payload[4:]
        
        try:
            await self.file_manager.save_piece(piece_index, piece_data)
            self.pending_requests.discard(piece_index)
            
            logger.info(f'Received piece {piece_index} from {connection.peer_id}')
            logger.info(f'Progress: {self.file_manager.get_progress():.1f}%')
            
            if self.file_manager.is_complete():
                logger.info('Download complete!')
                self._running = False
                
        except Exception as e:
            logger.error(f'Failed to save piece {piece_index}: {e}')

    async def _download_loop(self):
        """Main download loop."""
        while self._running and not self.file_manager.is_complete():
            await self._request_pieces()
            await asyncio.sleep(1)  # Check every second

    async def _request_pieces(self):
        """Request missing pieces from peers."""
        missing_pieces = self.file_manager.get_missing_pieces()
        
        for piece_index in missing_pieces:
            if piece_index in self.pending_requests:
                continue
                
            # Find a peer that has this piece
            for connection in self.connections.values():
                if (not connection.choked and 
                    piece_index < len(connection.bitfield) and 
                    connection.bitfield[piece_index]):
                    
                    # Request the piece
                    request_payload = piece_index.to_bytes(4, 'big')
                    request_message = Message(MessageType.REQUEST, request_payload)
                    connection.writer.write(request_message.serialize())
                    await connection.writer.drain()
                    
                    self.pending_requests.add(piece_index)
                    logger.info(f'Requested piece {piece_index} from {connection.peer_id}')
                    break

    def _remove_connection(self, peer_id: str):
        """Remove a peer connection."""
        if peer_id in self.connections:
            connection = self.connections[peer_id]
            connection.writer.close()
            del self.connections[peer_id]
            logger.info(f'Removed connection to {peer_id}')

    async def stop(self):
        """Stop the peer."""
        self._running = False
        
        # Close all connections
        for connection in self.connections.values():
            connection.writer.close()
        self.connections.clear()
        
        # Close tracker connection
        if self._tracker_connection:
            self._tracker_connection.close()
            
        # Close server
        if self._server:
            self._server.close()
            await self._server.wait_closed() 