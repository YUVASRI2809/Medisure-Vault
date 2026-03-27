"""
MediSure Vault - Blockchain Utility Functions

This module provides helper functions for blockchain operations.
"""

import hashlib
import json


def compute_hash(data):
    """
    Compute SHA-256 hash of arbitrary data.
    
    Args:
        data (str or dict): Data to hash
        
    Returns:
        str: Hexadecimal hash string
    """
    if isinstance(data, dict):
        data = json.dumps(data, sort_keys=True)
    
    return hashlib.sha256(data.encode()).hexdigest()


def verify_hash(data, expected_hash):
    """
    Verify that data matches expected hash.
    
    Args:
        data (str or dict): Data to verify
        expected_hash (str): Expected hash value
        
    Returns:
        bool: True if hash matches, False otherwise
    """
    actual_hash = compute_hash(data)
    return actual_hash == expected_hash
