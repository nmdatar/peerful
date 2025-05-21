import asyncio
import os
from src.peerful.file_manager import FileManager
from src.peerful.tracker import Tracker

async def share_file(filepath: str):
    # Initialize file manager
    file_manager = FileManager(filepath)
    file_info = await file_manager.initialize_for_sharing()
    
    print(f"File initialized for sharing:")
    print(f"Info hash: {file_info.info_hash.hex()}")
    print(f"File size: {file_info.file_size} bytes")
    print(f"Number of pieces: {file_info.num_pieces}")
    print(f"First piece hash: {file_info.piece_hashes[0].hex()}")

async def main():
    # Create a test file if it doesn't exist
    test_file = "test_file.txt"
    if not os.path.exists(test_file):
        with open(test_file, "w") as f:
            f.write("This is a test file for PeerFul P2P sharing system.\n" * 1000)
    
    # Start tracker in the background
    tracker = Tracker()
    tracker_task = asyncio.create_task(tracker.start())
    
    # Give tracker a moment to start
    await asyncio.sleep(1)
    
    try:
        # Share the file
        await share_file(test_file)
        
        print("\nTracker is running. Press Ctrl+C to stop...")
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        tracker_task.cancel()
        try:
            await tracker_task
        except asyncio.CancelledError:
            pass

if __name__ == "__main__":
    asyncio.run(main()) 