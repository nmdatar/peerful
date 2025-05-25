import asyncio
import os
import sys
from pathlib import Path

from src.peerful.tracker import Tracker
from src.peerful.peer import Peer
from src.peerful.file_manager import FileInfo

async def create_test_file(filename: str, size_kb: int = 100):
    """Create a test file with specified size."""
    content = "This is test data for PeerFul P2P file sharing.\n" * (size_kb * 10)
    with open(filename, 'w') as f:
        f.write(content)
    print(f"Created test file: {filename} ({size_kb}KB)")

async def run_tracker():
    """Run the tracker server."""
    tracker = Tracker()
    print("Starting tracker...")
    await tracker.start()

async def run_seeder(filepath: str):
    """Run a peer that shares a file."""
    peer = Peer()
    print(f"Starting seeder for file: {filepath}")
    
    info_hash = await peer.share_file(filepath)
    print(f"File is being shared with info hash: {info_hash}")
    
    # Keep running to serve the file
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("Seeder stopping...")
        await peer.stop()
    
    return info_hash

async def run_downloader(info_hash: str, output_path: str, file_info: FileInfo):
    """Run a peer that downloads a file."""
    peer = Peer()
    print(f"Starting downloader for info hash: {info_hash}")
    
    try:
        await peer.download_file(info_hash, output_path, file_info)
        print(f"Download completed: {output_path}")
    except KeyboardInterrupt:
        print("Downloader stopping...")
    finally:
        await peer.stop()

async def demo_full_p2p():
    """Demonstrate full P2P functionality with tracker, seeder, and downloader."""
    # Create test file
    test_file = "original_file.txt"
    download_file = "downloaded_file.txt"
    
    await create_test_file(test_file, 50)  # 50KB file
    
    # Start tracker
    tracker_task = asyncio.create_task(run_tracker())
    await asyncio.sleep(1)  # Give tracker time to start
    
    # Start seeder
    seeder_peer = Peer()
    info_hash = await seeder_peer.share_file(test_file)
    
    # Give seeder time to announce
    await asyncio.sleep(2)
    
    # Create file info for downloader (in real scenario, this would come from a .torrent file)
    file_info = FileInfo(
        info_hash=bytes.fromhex(info_hash),
        piece_hashes=seeder_peer.file_manager.piece_hashes,
        file_size=seeder_peer.file_manager.file_size,
        num_pieces=len(seeder_peer.file_manager.pieces),
        name=Path(test_file).name
    )
    
    # Start downloader
    downloader_peer = Peer()
    download_task = asyncio.create_task(
        downloader_peer.download_file(info_hash, download_file, file_info)
    )
    
    # Wait for download to complete or timeout
    try:
        await asyncio.wait_for(download_task, timeout=30)
        
        # Verify files are identical
        with open(test_file, 'r') as f1, open(download_file, 'r') as f2:
            if f1.read() == f2.read():
                print("✅ SUCCESS: Downloaded file matches original!")
            else:
                print("❌ ERROR: Downloaded file doesn't match original!")
                
    except asyncio.TimeoutError:
        print("⏰ Download timed out")
    except Exception as e:
        print(f"❌ Error during download: {e}")
    
    # Cleanup
    await seeder_peer.stop()
    await downloader_peer.stop()
    tracker_task.cancel()
    
    # Clean up test files
    for file in [test_file, download_file]:
        if os.path.exists(file):
            os.remove(file)

async def main():
    """Main function to run different modes."""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python test_p2p.py demo     - Run full P2P demo")
        print("  python test_p2p.py tracker  - Run tracker only")
        print("  python test_p2p.py seed <file> - Run seeder for file")
        return
    
    mode = sys.argv[1]
    
    if mode == "demo":
        await demo_full_p2p()
    elif mode == "tracker":
        await run_tracker()
    elif mode == "seed" and len(sys.argv) > 2:
        filepath = sys.argv[2]
        if not os.path.exists(filepath):
            print(f"File not found: {filepath}")
            return
        await run_seeder(filepath)
    else:
        print("Invalid arguments")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped by user") 