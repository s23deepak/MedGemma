#!/usr/bin/env python3
"""
Load testing script for MedGemma production validation.
Tests concurrent throughput, latency, and circuit breaker behavior.
"""

import asyncio
import time
import statistics
from typing import List, Tuple
import sys
from pathlib import Path

import httpx


class LoadTester:
    """Load testing utility for MedGemma."""

    def __init__(self, base_url: str = "http://localhost:8000", timeout: int = 30):
        self.base_url = base_url
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)

    async def test_endpoint(
        self, method: str, path: str, concurrent_users: int, requests_per_user: int = 5
    ) -> dict:
        """Test an endpoint with concurrent load."""
        url = f"{self.base_url}{path}"
        latencies: List[float] = []
        errors = 0
        successes = 0

        print(f"\n📊 Testing {method} {path}")
        print(f"   Concurrent users: {concurrent_users}, Requests per user: {requests_per_user}")

        async def make_request():
            nonlocal errors, successes, latencies
            try:
                start = time.time()
                response = await self.client.request(method, url)
                latency = time.time() - start
                latencies.append(latency)

                if response.status_code == 200:
                    successes += 1
                else:
                    errors += 1
                    print(f"   ⚠️  Status {response.status_code}", end="")
            except Exception as e:
                errors += 1
                print(f"\n   ❌ Error: {str(e)[:50]}", end="")

        # Run concurrent requests
        tasks = []
        for _ in range(concurrent_users):
            for _ in range(requests_per_user):
                tasks.append(make_request())

        start_time = time.time()
        await asyncio.gather(*tasks)
        total_time = time.time() - start_time

        total_requests = len(tasks)
        throughput = total_requests / total_time if total_time > 0 else 0

        results = {
            "endpoint": path,
            "concurrent_users": concurrent_users,
            "total_requests": total_requests,
            "successes": successes,
            "errors": errors,
            "error_rate": (errors / total_requests * 100) if total_requests > 0 else 0,
            "total_time_seconds": total_time,
            "throughput_rps": throughput,
            "latency_min_ms": min(latencies) * 1000 if latencies else 0,
            "latency_max_ms": max(latencies) * 1000 if latencies else 0,
            "latency_mean_ms": statistics.mean(latencies) * 1000 if latencies else 0,
            "latency_p50_ms": statistics.median(latencies) * 1000 if latencies else 0,
            "latency_p95_ms": (
                sorted(latencies)[int(len(latencies) * 0.95)] * 1000 if latencies else 0
            ),
            "latency_p99_ms": (
                sorted(latencies)[int(len(latencies) * 0.99)] * 1000 if latencies else 0
            ),
        }

        return results

    async def test_health(self) -> bool:
        """Test health endpoint."""
        try:
            response = await self.client.get(f"{self.base_url}/api/health")
            return response.status_code == 200
        except Exception as e:
            print(f"❌ Health check failed: {e}")
            return False

    async def get_status(self) -> dict:
        """Get system status."""
        try:
            response = await self.client.get(f"{self.base_url}/api/status")
            return response.json()
        except Exception as e:
            print(f"⚠️  Could not get status: {e}")
            return {}

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

    def print_results(self, results: dict):
        """Pretty print test results."""
        print(f"\n✅ Results for {results['endpoint']}:")
        print(f"   Total requests: {results['total_requests']}")
        print(f"   Successes: {results['successes']} ({100 - results['error_rate']:.1f}%)")
        print(f"   Errors: {results['errors']} ({results['error_rate']:.1f}%)")
        print(f"   Duration: {results['total_time_seconds']:.2f}s")
        print(f"   Throughput: {results['throughput_rps']:.1f} req/s")
        print(f"   Latency:")
        print(f"     - Min: {results['latency_min_ms']:.1f}ms")
        print(f"     - Mean: {results['latency_mean_ms']:.1f}ms")
        print(f"     - P50: {results['latency_p50_ms']:.1f}ms")
        print(f"     - P95: {results['latency_p95_ms']:.1f}ms")
        print(f"     - P99: {results['latency_p99_ms']:.1f}ms")
        print(f"     - Max: {results['latency_max_ms']:.1f}ms")


async def main():
    """Run comprehensive load tests."""
    tester = LoadTester()

    print("\n🚀 MedGemma Production Load Testing")
    print("=" * 50)

    # Health check
    print("\n🔍 Health check...")
    if not await tester.test_health():
        print("❌ Server not responding. Is it running on http://localhost:8000?")
        await tester.close()
        return

    print("✅ Server is healthy")

    # Get initial status
    print("\n📊 Initial system status:")
    status = await tester.get_status()
    if status:
        print(f"   Active sessions: {status.get('active_sessions', 'N/A')}")
        print(f"   Circuit breakers: {status.get('circuit_breakers', {})}")

    # Test configurations
    tests = [
        ("GET", "/api/patients", 5, 10),      # Light load
        ("GET", "/api/patients", 20, 5),      # Medium load
        ("GET", "/api/patients", 50, 3),      # Heavy load
    ]

    all_results = []

    for method, endpoint, concurrent_users, requests_per_user in tests:
        result = await tester.test_endpoint(
            method, endpoint, concurrent_users, requests_per_user
        )
        all_results.append(result)
        tester.print_results(result)
        await asyncio.sleep(2)  # Cool down between tests

    # Final status
    print("\n📊 Final system status:")
    status = await tester.get_status()
    if status:
        print(f"   Active sessions: {status.get('active_sessions', 'N/A')}")
        print(f"   Circuit breakers: {status.get('circuit_breakers', {})}")

    # Summary
    print("\n" + "=" * 50)
    print("📈 Summary")
    print("=" * 50)

    total_requests = sum(r["total_requests"] for r in all_results)
    total_successes = sum(r["successes"] for r in all_results)
    total_errors = sum(r["errors"] for r in all_results)
    total_time = max(r["total_time_seconds"] for r in all_results)

    print(f"\nTotal requests: {total_requests}")
    print(f"Total successes: {total_successes} ({total_successes/total_requests*100:.1f}%)")
    print(f"Total errors: {total_errors} ({total_errors/total_requests*100:.1f}%)")
    print(f"Total time: {total_time:.2f}s")
    print(f"Overall throughput: {total_requests/total_time:.1f} req/s")

    # Recommendations
    print("\n💡 Recommendations:")
    avg_error_rate = sum(r["error_rate"] for r in all_results) / len(all_results)
    if avg_error_rate > 5:
        print(f"   ⚠️  Error rate is {avg_error_rate:.1f}% - consider increasing workers")
    else:
        print(f"   ✅ Error rate is acceptable ({avg_error_rate:.1f}%)")

    avg_p95_latency = statistics.mean(r["latency_p95_ms"] for r in all_results)
    if avg_p95_latency > 1000:
        print(f"   ⚠️  P95 latency is {avg_p95_latency:.0f}ms - check circuit breakers")
    else:
        print(f"   ✅ P95 latency is good ({avg_p95_latency:.0f}ms)")

    # Check circuit breaker status
    print("\n🔌 Circuit Breaker Status:")
    status = await tester.get_status()
    if status and "circuit_breakers" in status:
        for name, state in status["circuit_breakers"].items():
            icon = "✅" if state == "closed" else "⚠️ "
            print(f"   {icon} {name}: {state}")

    await tester.close()


if __name__ == "__main__":
    print("Starting load tests in 2 seconds...")
    print("(Press Ctrl+C to cancel)")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n❌ Tests cancelled by user")
        sys.exit(1)
