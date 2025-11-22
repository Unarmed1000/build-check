#!/usr/bin/env python3
"""Utilities for persistent file-based caching of parsed data."""

import os
import pickle
import logging
import time
from typing import Any, Optional
from dataclasses import dataclass

from lib.color_utils import print_info

logger = logging.getLogger(__name__)


@dataclass
class CacheMetadata:
    """Metadata for cache validation.
    
    Attributes:
        filtered_db_mtime: Modification time of filtered compile_commands.json
        filtered_db_size: Size of filtered compile_commands.json in bytes
        build_ninja_mtime: Modification time of build.ninja (if exists)
        cache_timestamp: Timestamp when cache was created
    """
    filtered_db_mtime: float
    filtered_db_size: int
    build_ninja_mtime: Optional[float]
    cache_timestamp: float


@dataclass
class CachedData:
    """Container for cached data with metadata.
    
    Attributes:
        metadata: Cache validation metadata
        data: The actual cached data
    """
    metadata: CacheMetadata
    data: Any


def get_cache_path(build_dir: str, cache_filename: str) -> str:
    """Get the path to a cache file in the build directory.
    
    Args:
        build_dir: Path to the build directory
        cache_filename: Name of the cache file
        
    Returns:
        Full path to the cache file
    """
    from lib.constants import CACHE_DIR
    cache_dir = os.path.join(build_dir, CACHE_DIR)
    return os.path.join(cache_dir, cache_filename)


def ensure_cache_dir(build_dir: str) -> str:
    """Ensure the cache directory exists in the build directory.
    
    Args:
        build_dir: Path to the build directory
        
    Returns:
        Path to the cache directory
    """
    from lib.constants import CACHE_DIR
    cache_dir = os.path.join(build_dir, CACHE_DIR)
    
    if not os.path.exists(cache_dir):
        try:
            os.makedirs(cache_dir, exist_ok=True)
            logger.debug(f"Created cache directory: {cache_dir}")
        except OSError as e:
            logger.warning(f"Failed to create cache directory {cache_dir}: {e}")
    
    return cache_dir


def is_cache_valid(
    metadata: CacheMetadata,
    filtered_db_path: str,
    build_ninja_path: Optional[str] = None,
    max_age_hours: Optional[float] = None
) -> bool:
    """Check if cached data is still valid.
    
    Args:
        metadata: Cache metadata to validate
        filtered_db_path: Path to filtered compile_commands.json
        build_ninja_path: Optional path to build.ninja for additional validation
        max_age_hours: Maximum cache age in hours (None = no age limit)
        
    Returns:
        True if cache is valid, False otherwise
    """
    # Check if filtered DB exists and matches metadata
    if not os.path.exists(filtered_db_path):
        logger.debug(f"Cache invalid: filtered DB {filtered_db_path} does not exist")
        return False
    
    filtered_stat = os.stat(filtered_db_path)
    if filtered_stat.st_mtime != metadata.filtered_db_mtime:
        logger.debug(f"Cache invalid: filtered DB mtime changed")
        print_info("🔄 Cache invalidated: build configuration changed")
        return False
    
    if filtered_stat.st_size != metadata.filtered_db_size:
        logger.debug(f"Cache invalid: filtered DB size changed")
        print_info("🔄 Cache invalidated: build configuration changed")
        return False
    
    # Check build.ninja if provided
    if build_ninja_path and os.path.exists(build_ninja_path):
        build_ninja_mtime = os.path.getmtime(build_ninja_path)
        if metadata.build_ninja_mtime is None or build_ninja_mtime != metadata.build_ninja_mtime:
            logger.debug(f"Cache invalid: build.ninja mtime changed")
            print_info("🔄 Cache invalidated: build.ninja changed")
            return False
    
    # Check cache age if limit is specified
    if max_age_hours is not None:
        age_seconds = time.time() - metadata.cache_timestamp
        age_hours = age_seconds / 3600
        if age_hours > max_age_hours:
            logger.debug(f"Cache invalid: age {age_hours:.1f}h exceeds limit {max_age_hours}h")
            print_info(f"🔄 Cache invalidated: too old ({age_hours:.1f}h > {max_age_hours}h limit)")
            return False
    
    return True


def save_cache(
    cache_path: str,
    data: Any,
    filtered_db_path: str,
    build_ninja_path: Optional[str] = None
) -> bool:
    """Save data to cache with metadata.
    
    Uses atomic write (temp file + rename) to prevent corruption.
    
    Args:
        cache_path: Path to the cache file
        data: Data to cache
        filtered_db_path: Path to filtered compile_commands.json
        build_ninja_path: Optional path to build.ninja for validation
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Gather metadata
        filtered_stat = os.stat(filtered_db_path)
        build_ninja_mtime = None
        if build_ninja_path and os.path.exists(build_ninja_path):
            build_ninja_mtime = os.path.getmtime(build_ninja_path)
        
        metadata = CacheMetadata(
            filtered_db_mtime=filtered_stat.st_mtime,
            filtered_db_size=filtered_stat.st_size,
            build_ninja_mtime=build_ninja_mtime,
            cache_timestamp=time.time()
        )
        
        cached_data = CachedData(metadata=metadata, data=data)
        
        # Write to temp file first (atomic operation)
        temp_path = cache_path + '.tmp'
        with open(temp_path, 'wb') as f:
            pickle.dump(cached_data, f, protocol=pickle.HIGHEST_PROTOCOL)
        
        # Atomic rename
        os.replace(temp_path, cache_path)
        
        logger.debug(f"Saved cache: {cache_path}")
        return True
        
    except (OSError, IOError, pickle.PicklingError) as e:
        logger.warning(f"Failed to save cache {cache_path}: {e}")
        # Clean up temp file if it exists
        temp_path = cache_path + '.tmp'
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        return False


def load_cache(
    cache_path: str,
    filtered_db_path: str,
    build_ninja_path: Optional[str] = None,
    max_age_hours: Optional[float] = None
) -> Optional[Any]:
    """Load data from cache if valid.
    
    Args:
        cache_path: Path to the cache file
        filtered_db_path: Path to filtered compile_commands.json for validation
        build_ninja_path: Optional path to build.ninja for validation
        max_age_hours: Maximum cache age in hours (None = no age limit)
        
    Returns:
        Cached data if valid, None otherwise
    """
    if not os.path.exists(cache_path):
        logger.debug(f"Cache miss: {cache_path} does not exist")
        return None
    
    try:
        with open(cache_path, 'rb') as f:
            cached_data: CachedData = pickle.load(f)
        
        # Validate cache
        if not is_cache_valid(cached_data.metadata, filtered_db_path, build_ninja_path, max_age_hours):
            logger.debug(f"Cache invalid: {cache_path}")
            return None
        
        logger.debug(f"Cache hit: {cache_path}")
        return cached_data.data
        
    except (OSError, IOError, pickle.UnpicklingError, AttributeError, EOFError) as e:
        logger.warning(f"Failed to load cache {cache_path}: {e}, falling back to regeneration")
        # Try to remove corrupted cache
        try:
            os.remove(cache_path)
            logger.debug(f"Removed corrupted cache: {cache_path}")
        except OSError:
            pass
        return None


def cleanup_old_caches(build_dir: str, max_age_hours: float) -> int:
    """Clean up cache files older than the specified age.
    
    Args:
        build_dir: Path to the build directory
        max_age_hours: Maximum cache age in hours
        
    Returns:
        Number of cache files removed
    """
    from lib.constants import CACHE_DIR
    cache_dir = os.path.join(build_dir, CACHE_DIR)
    
    if not os.path.exists(cache_dir):
        return 0
    
    removed_count = 0
    current_time = time.time()
    max_age_seconds = max_age_hours * 3600
    
    try:
        for filename in os.listdir(cache_dir):
            if not filename.endswith('.pickle'):
                continue
            
            filepath = os.path.join(cache_dir, filename)
            try:
                file_stat = os.stat(filepath)
                age_seconds = current_time - file_stat.st_mtime
                
                if age_seconds > max_age_seconds:
                    os.remove(filepath)
                    removed_count += 1
                    logger.debug(f"Removed old cache: {filepath} (age: {age_seconds/3600:.1f}h)")
            except OSError as e:
                logger.warning(f"Failed to process cache file {filepath}: {e}")
                continue
    
    except OSError as e:
        logger.warning(f"Failed to list cache directory {cache_dir}: {e}")
    
    if removed_count > 0:
        logger.info(f"Cleaned up {removed_count} old cache file(s)")
    
    return removed_count
