"""
Memory Monitoring Utilities

Provides lightweight memory profiling for the pipeline to detect and prevent OOM issues.
"""

import psutil
import os
from loguru import logger
from typing import Optional


def get_memory_mb() -> float:
    """
    Get current process memory usage in MB.

    Returns:
        Memory usage in MB (RSS - Resident Set Size)
    """
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 ** 2)


def log_memory(label: str, level: str = "info") -> float:
    """
    Log current memory usage with a descriptive label.

    Args:
        label: Description of current operation
        level: Log level (info, debug, warning)

    Returns:
        Current memory usage in MB
    """
    mem_mb = get_memory_mb()
    mem_gb = mem_mb / 1024

    log_func = getattr(logger, level, logger.info)
    log_func(f"[MEM] {label}: {mem_mb:,.0f} MB ({mem_gb:.2f} GB)")

    return mem_mb


def check_memory_threshold(operation: str, threshold_gb: float = 12.0) -> bool:
    """
    Check if memory usage is approaching threshold and warn.

    Args:
        operation: Description of operation being performed
        threshold_gb: Warning threshold in GB (default 12GB for 16GB laptops)

    Returns:
        True if under threshold, False if over threshold
    """
    mem_mb = get_memory_mb()
    mem_gb = mem_mb / 1024

    if mem_gb > threshold_gb:
        logger.warning(
            f"[MEM WARNING] {operation}: Memory usage {mem_gb:.2f} GB "
            f"exceeds threshold {threshold_gb:.0f} GB"
        )
        return False

    return True


class MemoryMonitor:
    """Context manager for monitoring memory during operations."""

    def __init__(self, operation_name: str, warn_threshold_gb: float = 12.0):
        """
        Initialize memory monitor.

        Args:
            operation_name: Name of operation being monitored
            warn_threshold_gb: Threshold for warnings (default 12GB)
        """
        self.operation_name = operation_name
        self.warn_threshold_gb = warn_threshold_gb
        self.start_mem_mb = None
        self.peak_mem_mb = None

    def __enter__(self):
        """Start monitoring."""
        self.start_mem_mb = get_memory_mb()
        logger.info(
            f"[MEM START] {self.operation_name}: "
            f"{self.start_mem_mb:,.0f} MB ({self.start_mem_mb/1024:.2f} GB)"
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """End monitoring and report."""
        end_mem_mb = get_memory_mb()
        delta_mb = end_mem_mb - self.start_mem_mb
        delta_sign = "+" if delta_mb >= 0 else ""

        logger.info(
            f"[MEM END] {self.operation_name}: "
            f"{end_mem_mb:,.0f} MB ({end_mem_mb/1024:.2f} GB), "
            f"delta: {delta_sign}{delta_mb:,.0f} MB ({delta_sign}{delta_mb/1024:.2f} GB)"
        )

        if end_mem_mb / 1024 > self.warn_threshold_gb:
            logger.warning(
                f"[MEM WARNING] {self.operation_name} exceeded threshold: "
                f"{end_mem_mb/1024:.2f} GB > {self.warn_threshold_gb:.0f} GB"
            )
