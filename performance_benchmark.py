#!/usr/bin/env python3
"""
Performance Benchmark for Events Dashboard API
Measures the impact of database query optimization.
"""

import time
import requests
import statistics
from typing import List, Dict
from datetime import datetime

class APIPerformanceBenchmark:
    """Benchmark the /events API endpoint performance."""
    
    def __init__(self, base_url: str = "http://localhost:5000"):
        self.base_url = base_url
        self.endpoints = {
            "all_events": "/events",
            "hackathons_only": "/events?type_filter=hackathon",
            "conferences_only": "/events?type_filter=conference", 
            "location_filter": "/events?location_filter=San Francisco",
            "status_filter": "/events?status_filter=enriched",
            "limited_results": "/events?limit=10",
            "paginated": "/events?limit=20&offset=10"
        }
    
    def measure_endpoint_performance(self, endpoint: str, iterations: int = 5) -> Dict[str, float]:
        """
        Measure endpoint performance over multiple iterations.
        
        Args:
            endpoint: API endpoint path
            iterations: Number of test iterations
            
        Returns:
            Performance statistics dictionary
        """
        response_times = []
        
        for i in range(iterations):
            start_time = time.time()
            
            try:
                response = requests.get(f"{self.base_url}{endpoint}", timeout=30)
                response.raise_for_status()
                
                end_time = time.time()
                response_time = (end_time - start_time) * 1000  # Convert to milliseconds
                response_times.append(response_time)
                
                # Log response info
                data = response.json()
                event_count = len(data) if isinstance(data, list) else 0
                print(f"  Iteration {i+1}: {response_time:.1f}ms ({event_count} events)")
                
                # Small delay between requests
                if i < iterations - 1:
                    time.sleep(0.5)
                    
            except Exception as e:
                print(f"  Iteration {i+1}: FAILED - {e}")
                continue
        
        if not response_times:
            return {"error": "All requests failed"}
        
        return {
            "min_ms": min(response_times),
            "max_ms": max(response_times),
            "avg_ms": statistics.mean(response_times),
            "median_ms": statistics.median(response_times),
            "std_dev_ms": statistics.stdev(response_times) if len(response_times) > 1 else 0,
            "sample_size": len(response_times)
        }
    
    def run_comprehensive_benchmark(self) -> Dict[str, Dict[str, float]]:
        """Run performance tests on all endpoints."""
        print("=" * 60)
        print("🚀 EVENTS DASHBOARD API PERFORMANCE BENCHMARK")
        print("=" * 60)
        print(f"Target: {self.base_url}")
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        results = {}
        
        for name, endpoint in self.endpoints.items():
            print(f"📊 Testing {name}: {endpoint}")
            
            # Check if API is responsive
            try:
                health_check = requests.get(f"{self.base_url}/health", timeout=10)
                if health_check.status_code != 200:
                    print(f"  ❌ API health check failed: {health_check.status_code}")
                    continue
            except Exception as e:
                print(f"  ❌ API not accessible: {e}")
                continue
            
            # Run performance test
            stats = self.measure_endpoint_performance(endpoint)
            results[name] = stats
            
            if "error" in stats:
                print(f"  ❌ {stats['error']}")
            else:
                print(f"  ✅ Average: {stats['avg_ms']:.1f}ms | Min: {stats['min_ms']:.1f}ms | Max: {stats['max_ms']:.1f}ms")
            
            print()
        
        return results
    
    def generate_performance_report(self, results: Dict[str, Dict[str, float]]) -> str:
        """Generate a detailed performance report."""
        report = []
        report.append("📈 PERFORMANCE BENCHMARK RESULTS")
        report.append("=" * 50)
        report.append("")
        
        # Summary table
        report.append("| Endpoint | Avg (ms) | Min (ms) | Max (ms) | Std Dev |")
        report.append("|----------|----------|----------|----------|---------|")
        
        for name, stats in results.items():
            if "error" in stats:
                report.append(f"| {name:<20} | ERROR | ERROR | ERROR | ERROR |")
            else:
                report.append(f"| {name:<20} | {stats['avg_ms']:>8.1f} | {stats['min_ms']:>8.1f} | {stats['max_ms']:>8.1f} | {stats['std_dev_ms']:>7.1f} |")
        
        report.append("")
        
        # Performance analysis
        successful_tests = [stats for stats in results.values() if "error" not in stats]
        if successful_tests:
            avg_times = [stats['avg_ms'] for stats in successful_tests]
            overall_avg = statistics.mean(avg_times)
            
            report.append("🎯 PERFORMANCE ANALYSIS")
            report.append(f"Overall average response time: {overall_avg:.1f}ms")
            
            # Performance categorization
            if overall_avg < 100:
                report.append("✅ EXCELLENT performance (< 100ms)")
            elif overall_avg < 300:
                report.append("✅ GOOD performance (< 300ms)")
            elif overall_avg < 500:
                report.append("⚠️  ACCEPTABLE performance (< 500ms)")
            else:
                report.append("❌ POOR performance (> 500ms) - optimization recommended")
        
        report.append("")
        report.append("🔧 OPTIMIZATION IMPACT")
        report.append("Target: 60-70% improvement with single-query optimization")
        report.append("Expected: 200-500ms → 60-120ms response times")
        
        return "\n".join(report)

def main():
    """Run the performance benchmark."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Benchmark Events Dashboard API performance")
    parser.add_argument("--url", default="http://localhost:5000", 
                       help="Base URL for the API (default: http://localhost:5000)")
    parser.add_argument("--iterations", type=int, default=5,
                       help="Number of test iterations per endpoint (default: 5)")
    
    args = parser.parse_args()
    
    # Run benchmark
    benchmark = APIPerformanceBenchmark(args.url)
    results = benchmark.run_comprehensive_benchmark()
    
    # Generate and display report
    report = benchmark.generate_performance_report(results)
    print(report)
    
    # Save results to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"performance_results_{timestamp}.txt"
    with open(filename, 'w') as f:
        f.write(report)
    
    print(f"\n📁 Results saved to: {filename}")

if __name__ == "__main__":
    main() 