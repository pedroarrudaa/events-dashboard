#!/usr/bin/env python3
"""
Performance Benchmark Script for Events Dashboard Optimization

This script demonstrates the performance improvements achieved by the optimization:
- Before: N+1 query problem with separate API calls for event actions
- After: Single optimized SQL query with JOINs

Usage:
    python performance_benchmark.py
"""

import asyncio
import time
import statistics
import requests
from typing import List, Dict, Any
from database_utils import (
    get_db_session, 
    get_events_from_db, 
    get_event_action,
    get_events_with_actions_optimized
)

class PerformanceBenchmark:
    """
    Performance benchmark class to measure and compare optimization results.
    """
    
    def __init__(self, api_base_url: str = "http://localhost:8000"):
        self.api_base_url = api_base_url
        self.results = {}
    
    def benchmark_old_approach(self, limit: int = 100) -> Dict[str, Any]:
        """
        Benchmark the old N+1 query approach.
        
        This simulates the original implementation:
        1. Fetch hackathons from database
        2. Fetch conferences from database  
        3. For each event, make separate query for actions
        """
        print("🔍 Benchmarking OLD approach (N+1 queries)...")
        
        start_time = time.time()
        
        # Step 1: Fetch hackathons and conferences separately
        hackathons = get_events_from_db('hackathons', limit // 2)
        conferences = get_events_from_db('conferences', limit // 2)
        
        events = []
        
        # Step 2: Process hackathons
        for hackathon in hackathons:
            hackathon['type'] = 'hackathon'
            events.append(hackathon)
        
        # Step 3: Process conferences
        for conference in conferences:
            conference['type'] = 'conference'
            events.append(conference)
        
        db_query_time = time.time() - start_time
        
        # Step 4: Fetch actions for each event (N+1 problem)
        action_start_time = time.time()
        for event in events:
            if event.get('id'):
                action = get_event_action(str(event['id']))
                if action:
                    event['last_action'] = action['action']
                    event['action_time'] = action['timestamp']
        
        action_query_time = time.time() - action_start_time
        total_time = time.time() - start_time
        
        result = {
            'approach': 'old_n_plus_1',
            'total_time': total_time,
            'db_query_time': db_query_time,
            'action_query_time': action_query_time,
            'events_count': len(events),
            'queries_count': 2 + len(events),  # 2 main queries + 1 per event
            'avg_time_per_event': total_time / len(events) if events else 0
        }
        
        print(f"   📊 Old approach: {total_time:.3f}s total, {len(events)} events, {result['queries_count']} queries")
        return result
    
    def benchmark_optimized_approach(self, limit: int = 100) -> Dict[str, Any]:
        """
        Benchmark the new optimized single-query approach.
        """
        print("⚡ Benchmarking OPTIMIZED approach (Single JOIN query)...")
        
        start_time = time.time()
        
        # Single optimized query with JOINs
        events = get_events_with_actions_optimized(limit=limit)
        
        total_time = time.time() - start_time
        
        result = {
            'approach': 'optimized_join',
            'total_time': total_time,
            'db_query_time': total_time,  # All in one query
            'action_query_time': 0,  # Included in main query
            'events_count': len(events),
            'queries_count': 1,  # Single query
            'avg_time_per_event': total_time / len(events) if events else 0
        }
        
        print(f"   📊 Optimized: {total_time:.3f}s total, {len(events)} events, {result['queries_count']} query")
        return result
    
    async def benchmark_api_endpoints(self, iterations: int = 5) -> Dict[str, Any]:
        """
        Benchmark the actual API endpoints.
        """
        print("🌐 Benchmarking API endpoints...")
        
        old_times = []
        new_times = []
        
        for i in range(iterations):
            print(f"   Iteration {i+1}/{iterations}")
            
            # Test new optimized endpoint
            start_time = time.time()
            try:
                response = requests.get(f"{self.api_base_url}/events", timeout=30)
                if response.status_code == 200:
                    new_time = time.time() - start_time
                    new_times.append(new_time)
                    
                    # Check for performance headers
                    process_time = response.headers.get('X-Process-Time')
                    if process_time:
                        print(f"      API process time: {float(process_time)*1000:.0f}ms")
                else:
                    print(f"      API error: {response.status_code}")
            except Exception as e:
                print(f"      API error: {e}")
        
        api_results = {
            'new_endpoint_times': new_times,
            'new_avg_time': statistics.mean(new_times) if new_times else 0,
            'new_min_time': min(new_times) if new_times else 0,
            'new_max_time': max(new_times) if new_times else 0,
            'iterations': len(new_times)
        }
        
        print(f"   📊 API Average: {api_results['new_avg_time']:.3f}s")
        return api_results
    
    def run_comprehensive_benchmark(self, iterations: int = 3) -> Dict[str, Any]:
        """
        Run comprehensive performance benchmark comparing old vs optimized approaches.
        """
        print("\n" + "="*70)
        print("🚀 EVENTS DASHBOARD PERFORMANCE BENCHMARK")
        print("="*70)
        
        results = {
            'database_benchmarks': [],
            'api_benchmarks': {},
            'summary': {}
        }
        
        # Run database benchmarks multiple times for accuracy
        print(f"\n📊 Running database benchmarks ({iterations} iterations)...")
        
        old_times = []
        new_times = []
        old_query_counts = []
        new_query_counts = []
        
        for i in range(iterations):
            print(f"\nIteration {i+1}/{iterations}")
            
            # Benchmark old approach
            old_result = self.benchmark_old_approach(limit=100)
            old_times.append(old_result['total_time'])
            old_query_counts.append(old_result['queries_count'])
            
            # Benchmark optimized approach
            new_result = self.benchmark_optimized_approach(limit=100)
            new_times.append(new_result['total_time'])
            new_query_counts.append(new_result['queries_count'])
            
            results['database_benchmarks'].append({
                'iteration': i+1,
                'old': old_result,
                'new': new_result,
                'improvement_ratio': old_result['total_time'] / new_result['total_time'] if new_result['total_time'] > 0 else 0
            })
        
        # Calculate averages
        old_avg = statistics.mean(old_times)
        new_avg = statistics.mean(new_times)
        improvement_ratio = old_avg / new_avg if new_avg > 0 else 0
        improvement_percentage = ((old_avg - new_avg) / old_avg * 100) if old_avg > 0 else 0
        
        # API benchmarks
        api_results = asyncio.run(self.benchmark_api_endpoints(iterations=3))
        results['api_benchmarks'] = api_results
        
        # Summary
        results['summary'] = {
            'old_approach_avg_time': old_avg,
            'new_approach_avg_time': new_avg,
            'improvement_ratio': improvement_ratio,
            'improvement_percentage': improvement_percentage,
            'old_avg_queries': statistics.mean(old_query_counts),
            'new_avg_queries': statistics.mean(new_query_counts),
            'query_reduction_percentage': ((statistics.mean(old_query_counts) - statistics.mean(new_query_counts)) / statistics.mean(old_query_counts) * 100)
        }
        
        self.print_results(results)
        return results
    
    def print_results(self, results: Dict[str, Any]):
        """
        Print formatted benchmark results.
        """
        summary = results['summary']
        
        print("\n" + "="*70)
        print("📈 PERFORMANCE OPTIMIZATION RESULTS")
        print("="*70)
        
        print(f"\n🔍 DATABASE QUERY PERFORMANCE:")
        print(f"   Old Approach (N+1):     {summary['old_approach_avg_time']:.3f}s avg")
        print(f"   New Approach (JOIN):    {summary['new_approach_avg_time']:.3f}s avg")
        print(f"   Improvement Ratio:      {summary['improvement_ratio']:.1f}x faster")
        print(f"   Improvement Percentage: {summary['improvement_percentage']:.1f}% faster")
        
        print(f"\n🗃️ QUERY EFFICIENCY:")
        print(f"   Old Query Count:        {summary['old_avg_queries']:.0f} queries avg")
        print(f"   New Query Count:        {summary['new_avg_queries']:.0f} query avg") 
        print(f"   Query Reduction:        {summary['query_reduction_percentage']:.1f}% fewer queries")
        
        api_results = results['api_benchmarks']
        if api_results['new_avg_time'] > 0:
            print(f"\n🌐 API ENDPOINT PERFORMANCE:")
            print(f"   Optimized API Response: {api_results['new_avg_time']:.3f}s avg")
            print(f"   Min Response Time:      {api_results['new_min_time']:.3f}s")
            print(f"   Max Response Time:      {api_results['new_max_time']:.3f}s")
        
        print(f"\n✅ OPTIMIZATION SUMMARY:")
        print(f"   • Eliminated N+1 query problem with SQL JOINs")
        print(f"   • Reduced database queries by {summary['query_reduction_percentage']:.0f}%")
        print(f"   • Improved response time by {summary['improvement_percentage']:.0f}%")
        print(f"   • Added database indexes for optimal performance")
        print(f"   • Implemented React performance optimizations")
        print(f"   • Added HTTP caching headers")
        
        print("\n" + "="*70)
        print("🎉 PERFORMANCE OPTIMIZATION COMPLETE!")
        print("="*70)

if __name__ == "__main__":
    """
    Run performance benchmark when script is executed directly.
    """
    try:
        benchmark = PerformanceBenchmark()
        benchmark.run_comprehensive_benchmark(iterations=3)
    except Exception as e:
        print(f"❌ Benchmark failed: {e}")
        print("Make sure the database is running and accessible.") 