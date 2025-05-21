import os
import asyncio
import aiofiles
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from pathlib import Path

from .protocol import PIECE_SIZE, calculate_piece_hash, calculate_info_hash

@dataclass
class FileInfo:
    """File information and metadata."""
    info_hash: bytes
    piece_hashes: List[bytes]
    file_size: int
    num_pieces: int
    name: str

class FileManager:
    def __init__(self, filepath: str):
        self.filepath = Path(filepath)
        self.pieces: List[Optional[bytes]] = []
        self.piece_hashes: List[bytes] = []
        self.bitfield: List[bool] = []
        self.file_size: int = 0
        self._file_handle = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._file_handle:
            await self._file_handle.close()

    async def initialize_for_sharing(self) -> FileInfo:
        """Initialize a file for sharing."""
        try:
            self.file_size = os.path.getsize(self.filepath)
            self.num_pieces = (self.file_size + PIECE_SIZE - 1) // PIECE_SIZE

            async with aiofiles.open(self.filepath, 'rb') as f:
                for i in range(self.num_pieces):
                    position = i * PIECE_SIZE
                    length = min(PIECE_SIZE, self.file_size - position)
                    
                    # Seek and read the piece
                    await f.seek(position)
                    piece_data = await f.read(length)
                    
                    # Store piece and calculate hash
                    self.pieces.append(piece_data)
                    piece_hash = calculate_piece_hash(piece_data)
                    self.piece_hashes.append(piece_hash)
                    self.bitfield.append(True)

            # Generate info hash
            info = {
                'piece_length': PIECE_SIZE,
                'pieces': [h.hex() for h in self.piece_hashes],
                'length': self.file_size,
                'name': self.filepath.name
            }
            info_hash = calculate_info_hash(info)

            return FileInfo(
                info_hash=info_hash,
                piece_hashes=self.piece_hashes,
                file_size=self.file_size,
                num_pieces=self.num_pieces,
                name=self.filepath.name
            )

        except Exception as e:
            raise RuntimeError(f"Failed to initialize file: {e}")

    async def initialize_for_download(self, file_info: FileInfo) -> None:
        """Initialize for downloading a file."""
        self.file_size = file_info.file_size
        self.piece_hashes = file_info.piece_hashes
        self.pieces = [None] * file_info.num_pieces
        self.bitfield = [False] * file_info.num_pieces

        # Create empty file of correct size
        try:
            async with aiofiles.open(self.filepath, 'wb') as f:
                await f.truncate(self.file_size)
        except Exception as e:
            raise RuntimeError(f"Failed to initialize download file: {e}")

    def get_piece(self, index: int) -> Optional[bytes]:
        """Get a specific piece."""
        if 0 <= index < len(self.pieces):
            return self.pieces[index]
        return None

    async def save_piece(self, index: int, piece_data: bytes) -> bool:
        """Save a received piece."""
        if index >= len(self.piece_hashes):
            return False

        # Verify piece hash
        piece_hash = calculate_piece_hash(piece_data)
        if piece_hash != self.piece_hashes[index]:
            raise ValueError("Piece hash verification failed")

        # Save piece in memory
        self.pieces[index] = piece_data
        self.bitfield[index] = True

        # Write to file
        try:
            position = index * PIECE_SIZE
            async with aiofiles.open(self.filepath, 'r+b') as f:
                await f.seek(position)
                await f.write(piece_data)
                await f.flush()
                os.fsync(f.fileno())  # Force sync to disk
        except Exception as e:
            self.pieces[index] = None
            self.bitfield[index] = False
            raise RuntimeError(f"Failed to save piece: {e}")

        return True

    def is_complete(self) -> bool:
        """Check if download is complete."""
        return all(self.bitfield)

    def get_missing_pieces(self) -> List[int]:
        """Get indices of missing pieces."""
        return [i for i, have in enumerate(self.bitfield) if not have]

    def get_progress(self) -> float:
        """Get download progress as percentage."""
        if not self.bitfield:
            return 0.0
        return sum(self.bitfield) / len(self.bitfield) * 100 