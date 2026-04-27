"""
Stress Test - Simulates multiple concurrent Telnyx phone calls with AI-to-AI conversation.

This script runs N concurrent simulated calls using a mediator pattern:
- Each call connects to /ws/phone (Telnyx protocol)
- A "Customer Agent" (Gemini 2.0 Flash) generates natural responses
- Text-to-Speech converts customer text to audio
- The IVR App (Gemini 2.5 Flash Native Audio) receives real speech

This creates true AI-to-AI conversations that fully test the IVR pipeline.

Usage:
    python stress_test.py --calls 10 --host localhost --port 8000
"""

import argparse
import asyncio
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List
from datetime import datetime

from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent / ".env")

from mediator_simulator import MediatorCallSimulator, CallResult, generate_random_postal_code, generate_random_dimensions

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"stress_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class StressTestResults:
    """Aggregate results from stress test."""
    total_calls: int
    successful_calls: int
    failed_calls: int
    total_duration: float
    avg_duration: float
    min_duration: float
    max_duration: float
    total_audio_sent: int
    total_audio_received: int
    call_results: List[CallResult]


def print_banner(num_calls: int, batch_size: int = None) -> None:
    """Print stress test banner."""
    print("\n" + "=" * 80)
    if batch_size and batch_size < num_calls:
        num_batches = (num_calls + batch_size - 1) // batch_size
        print(f"STRESS TEST: {num_calls} Calls in {num_batches} Batches (batch size: {batch_size})")
    else:
        print(f"STRESS TEST: {num_calls} Concurrent Telnyx Phone Calls")
    print("=" * 80)
    print(f"Endpoint: /ws/phone (Telnyx WebSocket protocol)")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()


def print_call_start(call_num: int, total: int, simulator: MediatorCallSimulator) -> None:
    """Print call start info."""
    dims = simulator.dimensions
    print(f"  [Call {call_num}/{total}] {simulator.from_postal} -> {simulator.to_postal}, "
          f"{dims['length']}x{dims['width']}x{dims['height']}cm "
          f"(id: {simulator.call_control_id[:8]})")


def print_call_result(result: CallResult) -> None:
    """Print individual call result."""
    status = "OK" if result.success else "FAIL"
    print(f"  [{status}] Call {result.call_id}: "
          f"{result.duration_seconds:.2f}s, "
          f"{result.audio_chunks_sent} sent/{result.audio_chunks_received} recv"
          + (f" - ERROR: {result.error}" if result.error else ""))


def print_results(results: StressTestResults) -> None:
    """Print aggregate stress test results."""
    print("\n" + "=" * 80)
    print("STRESS TEST RESULTS")
    print("=" * 80)
    
    success_rate = (results.successful_calls / results.total_calls * 100) if results.total_calls > 0 else 0
    
    print(f"""
  Total Calls:        {results.total_calls}
  Successful:         {results.successful_calls} ({success_rate:.1f}%)
  Failed:             {results.failed_calls} ({100 - success_rate:.1f}%)
  
  Total Duration:     {results.total_duration:.2f} seconds
  Avg Call Time:      {results.avg_duration:.2f} seconds
  Min Call Time:      {results.min_duration:.2f} seconds
  Max Call Time:      {results.max_duration:.2f} seconds
  
  Audio Chunks Sent:      {results.total_audio_sent}
  Audio Chunks Received:  {results.total_audio_received}
""")
    
    # Print individual call summaries
    print("  Individual Call Results:")
    print("  " + "-" * 76)
    
    for result in results.call_results:
        status = "OK" if result.success else "FAIL"
        dims = result.dimensions
        print(f"    [{status}] {result.call_id}: "
              f"{result.from_postal} -> {result.to_postal}, "
              f"{dims['length']}x{dims['width']}x{dims['height']}cm, "
              f"{result.duration_seconds:.2f}s"
              + (f", {result.selected_service}" if result.selected_service else "")
              + (f" [{result.error}]" if result.error else ""))
    
    print("=" * 80)
    
    # Summary
    if results.failed_calls == 0:
        print("\nSUCCESS: All calls completed successfully!")
    else:
        print(f"\nWARNING: {results.failed_calls} call(s) failed. Check logs for details.")


async def run_single_call(
    call_num: int,
    total: int,
    host: str,
    port: int,
    delay: float,
) -> CallResult:
    """Run a single simulated Telnyx call with staggered start."""
    # Stagger call starts
    if delay > 0 and call_num > 1:
        await asyncio.sleep(delay * (call_num - 1))
    
    simulator = MediatorCallSimulator(
        host=host,
        port=port,
    )
    
    print_call_start(call_num, total, simulator)
    
    result = await simulator.run()
    
    print_call_result(result)
    
    return result


async def run_stress_test(
    num_calls: int = 10,
    host: str = "localhost",
    port: int = 8000,
    delay: float = 0.5,
    concurrent: bool = True,
    batch_size: int = None,
) -> StressTestResults:
    """
    Run the stress test with multiple concurrent Telnyx calls.
    
    Args:
        num_calls: Number of calls to simulate
        host: Server host
        port: Server port
        delay: Delay between starting calls (seconds)
        concurrent: Run calls concurrently (True) or sequentially (False)
        batch_size: If set, run calls in batches of this size (for rate limiting)
    
    Returns:
        StressTestResults with aggregate statistics
    """
    print_banner(num_calls, batch_size)
    
    print("Starting calls...\n")
    start_time = time.time()
    
    all_results: List[CallResult] = []
    
    # Determine if we're running in batch mode
    if batch_size and batch_size < num_calls and concurrent:
        # Batch mode: run calls in groups
        num_batches = (num_calls + batch_size - 1) // batch_size
        call_counter = 0
        
        for batch_num in range(num_batches):
            batch_start = batch_num * batch_size
            batch_end = min(batch_start + batch_size, num_calls)
            current_batch_size = batch_end - batch_start
            
            print(f"\n{'='*40}")
            print(f"BATCH {batch_num + 1}/{num_batches} ({current_batch_size} calls)")
            print(f"{'='*40}")
            
            # Create tasks for this batch
            tasks = [
                run_single_call(call_counter + i + 1, num_calls, host, port, delay)
                for i in range(current_batch_size)
            ]
            call_counter += current_batch_size
            
            # Run this batch concurrently
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for i, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    all_results.append(CallResult(
                        call_id=f"call-{batch_start + i + 1}",
                        success=False,
                        duration_seconds=0.0,
                        from_postal="N/A",
                        to_postal="N/A",
                        dimensions={"length": 0, "width": 0, "height": 0},
                        error=str(result),
                    ))
                else:
                    all_results.append(result)
            
            # Print batch summary
            batch_success = sum(1 for r in batch_results if isinstance(r, CallResult) and r.success)
            batch_failed = current_batch_size - batch_success
            print(f"\n  Batch {batch_num + 1} complete: {batch_success}/{current_batch_size} successful")
            
            # Small delay between batches to let resources settle
            if batch_num < num_batches - 1:
                print(f"  Waiting 2 seconds before next batch...")
                await asyncio.sleep(2)
        
        call_results = all_results
    
    elif concurrent:
        # Create all call tasks
        tasks = [
            run_single_call(i + 1, num_calls, host, port, delay)
            for i in range(num_calls)
        ]
        
        # Run all calls concurrently
        call_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle any exceptions
        processed_results: List[CallResult] = []
        for i, result in enumerate(call_results):
            if isinstance(result, Exception):
                # Convert exception to failed CallResult
                processed_results.append(CallResult(
                    call_id=f"call-{i+1}",
                    success=False,
                    duration_seconds=0.0,
                    from_postal="N/A",
                    to_postal="N/A",
                    dimensions={"length": 0, "width": 0, "height": 0},
                    error=str(result),
                ))
            else:
                processed_results.append(result)
        call_results = processed_results
    else:
        # Run calls sequentially
        call_results = []
        for i in range(num_calls):
            result = await run_single_call(i + 1, num_calls, host, port, 0)
            call_results.append(result)
            if delay > 0:
                await asyncio.sleep(delay)
    
    total_duration = time.time() - start_time
    
    # Calculate statistics
    successful = [r for r in call_results if r.success]
    failed = [r for r in call_results if not r.success]
    durations = [r.duration_seconds for r in call_results]
    
    results = StressTestResults(
        total_calls=num_calls,
        successful_calls=len(successful),
        failed_calls=len(failed),
        total_duration=total_duration,
        avg_duration=sum(durations) / len(durations) if durations else 0,
        min_duration=min(durations) if durations else 0,
        max_duration=max(durations) if durations else 0,
        total_audio_sent=sum(r.audio_chunks_sent for r in call_results),
        total_audio_received=sum(r.audio_chunks_received for r in call_results),
        call_results=call_results,
    )
    
    print_results(results)
    
    return results


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Stress test the SmartShip Voice Assistant with concurrent Telnyx calls"
    )
    parser.add_argument(
        "--calls", "-n",
        type=int,
        default=10,
        help="Number of concurrent calls to simulate (default: 10)"
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Server host (default: from .env or localhost)"
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=None,
        help="Server port (default: from .env or 8000)"
    )
    parser.add_argument(
        "--delay", "-d",
        type=float,
        default=0.5,
        help="Delay between starting calls in seconds (default: 0.5)"
    )
    parser.add_argument(
        "--sequential", "-s",
        action="store_true",
        help="Run calls sequentially instead of concurrently"
    )
    parser.add_argument(
        "--batch", "-b",
        type=int,
        default=None,
        help="Run calls in batches of this size (default: all concurrent). Use -b 2 to run 2 concurrent calls per batch."
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Get host/port from args or .env
    host = args.host or os.getenv("SERVER_HOST", "localhost")
    port = args.port or int(os.getenv("SERVER_PORT", "8000"))
    
    # Run the stress test
    try:
        results = asyncio.run(run_stress_test(
            num_calls=args.calls,
            host=host,
            port=port,
            delay=args.delay,
            concurrent=not args.sequential,
            batch_size=args.batch,
        ))
        
        # Exit with error code if any calls failed
        sys.exit(0 if results.failed_calls == 0 else 1)
        
    except KeyboardInterrupt:
        print("\n\n[!] Stress test interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Stress test failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
