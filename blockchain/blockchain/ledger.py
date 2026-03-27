"""
MediSure Vault - Blockchain Ledger Module

This module implements a custom private blockchain for immutable audit logging
of prescription state transitions and critical system events.
"""

from database import db
from models import Block
from datetime import datetime
from config import Config
import hashlib
import json


class Blockchain:
    """
    Custom private blockchain implementation for prescription audit trail.
    Each block contains event data and is cryptographically linked to the previous block.
    """
    
    def __init__(self):
        """Initialize blockchain and ensure genesis block exists."""
        self.difficulty = Config.BLOCKCHAIN_DIFFICULTY
        
        # Check if genesis block exists, create if not
        genesis = Block.query.filter_by(index=0).first()
        if not genesis:
            self._create_genesis_block()
    
    def _create_genesis_block(self):
        """
        Create the genesis block (first block in the chain).
        Genesis block has index 0 and previous_hash of '0'.
        """
        genesis_data = {
            'type': 'GENESIS',
            'message': Config.GENESIS_BLOCK_DATA,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        genesis = Block(
            index=0,
            timestamp=datetime.utcnow(),
            data=json.dumps(genesis_data),
            previous_hash='0' * 64,
            nonce=0
        )
        
        # Mine the genesis block
        genesis.hash = self._mine_block(genesis)
        
        db.session.add(genesis)
        db.session.commit()
        
        return genesis
    
    def get_latest_block(self):
        """
        Get the most recent block in the chain.
        
        Returns:
            Block: Latest block object
        """
        return Block.query.order_by(Block.index.desc()).first()
    
    def add_block(self, event_type, data, prescription_id=None, user_id=None):
        """
        Add a new block to the blockchain with event data.
        
        Args:
            event_type (str): Type of event being recorded
            data (dict): Event data to store in the block
            prescription_id (int): Optional prescription ID related to event
            user_id (int): Optional user ID who triggered the event
            
        Returns:
            Block: Newly created block object
        """
        latest_block = self.get_latest_block()
        
        # Prepare block data
        block_data = {
            'event_type': event_type,
            'prescription_id': prescription_id,
            'user_id': user_id,
            'timestamp': datetime.utcnow().isoformat(),
            'data': data
        }
        
        # Create new block
        new_block = Block(
            index=latest_block.index + 1,
            timestamp=datetime.utcnow(),
            data=json.dumps(block_data),
            previous_hash=latest_block.hash,
            nonce=0
        )
        
        # Mine the block (proof of work)
        new_block.hash = self._mine_block(new_block)
        
        # Save to database
        db.session.add(new_block)
        db.session.commit()
        
        return new_block
    
    def _mine_block(self, block):
        """
        Perform proof-of-work mining on a block.
        Finds a nonce such that the block hash has the required number of leading zeros.
        
        Args:
            block (Block): Block to mine
            
        Returns:
            str: Valid hash meeting difficulty requirement
        """
        target = '0' * self.difficulty
        
        while True:
            hash_result = block.compute_hash()
            
            if hash_result.startswith(target):
                return hash_result
            
            block.nonce += 1
    
    def is_chain_valid(self):
        """
        Validate the entire blockchain integrity.
        Checks:
        1. Each block's hash is correct
        2. Each block's previous_hash matches the previous block's hash
        3. Genesis block is valid
        
        Returns:
            bool: True if chain is valid, False if tampered
        """
        blocks = Block.query.order_by(Block.index.asc()).all()
        
        if not blocks:
            return False
        
        # Validate genesis block
        genesis = blocks[0]
        if genesis.index != 0:
            return False
        if genesis.previous_hash != '0' * 64:
            return False
        if genesis.hash != genesis.compute_hash():
            return False
        
        # Validate chain links
        for i in range(1, len(blocks)):
            current_block = blocks[i]
            previous_block = blocks[i - 1]
            
            # Check if current block's hash is correct
            if current_block.hash != current_block.compute_hash():
                return False
            
            # Check if current block's previous_hash matches previous block's hash
            if current_block.previous_hash != previous_block.hash:
                return False
            
            # Check if hash meets difficulty requirement
            if not current_block.hash.startswith('0' * self.difficulty):
                return False
        
        return True
    
    def get_chain(self):
        """
        Get the entire blockchain as a list of blocks.
        
        Returns:
            list: List of Block objects ordered by index
        """
        return Block.query.order_by(Block.index.asc()).all()
    
    def get_blocks_by_prescription(self, prescription_id):
        """
        Get all blocks related to a specific prescription.
        
        Args:
            prescription_id (int): Prescription ID to search for
            
        Returns:
            list: List of Block objects containing prescription events
        """
        blocks = []
        all_blocks = self.get_chain()
        
        for block in all_blocks:
            try:
                block_data = json.loads(block.data)
                if block_data.get('prescription_id') == prescription_id:
                    blocks.append(block)
            except json.JSONDecodeError:
                continue
        
        return blocks
    
    def get_blocks_by_user(self, user_id):
        """
        Get all blocks related to a specific user.
        
        Args:
            user_id (int): User ID to search for
            
        Returns:
            list: List of Block objects containing user events
        """
        blocks = []
        all_blocks = self.get_chain()
        
        for block in all_blocks:
            try:
                block_data = json.loads(block.data)
                if block_data.get('user_id') == user_id:
                    blocks.append(block)
            except json.JSONDecodeError:
                continue
        
        return blocks
    
    def verify_prescription_history(self, prescription_id):
        """
        Verify the complete blockchain history for a prescription.
        Reconstructs state transitions from blockchain to detect tampering.
        
        Args:
            prescription_id (int): Prescription ID to verify
            
        Returns:
            dict: Verification result with status and state history
        """
        blocks = self.get_blocks_by_prescription(prescription_id)
        
        if not blocks:
            return {
                'verified': False,
                'message': 'No blockchain records found for this prescription'
            }
        
        # Extract state transitions from blocks
        state_history = []
        for block in blocks:
            try:
                block_data = json.loads(block.data)
                event_type = block_data.get('event_type')
                
                if event_type in ['PRESCRIPTION_CREATED', 'PRESCRIPTION_SHARED', 
                                 'PRESCRIPTION_DISPENSED', 'PRESCRIPTION_LOCKED']:
                    state_history.append({
                        'timestamp': block_data.get('timestamp'),
                        'event': event_type,
                        'block_index': block.index,
                        'block_hash': block.hash
                    })
            except json.JSONDecodeError:
                continue
        
        return {
            'verified': True,
            'prescription_id': prescription_id,
            'state_history': state_history,
            'total_blocks': len(blocks)
        }
    
    def detect_tampering(self, prescription_id):
        """
        Detect any tampering attempts on a prescription by comparing
        blockchain records with current database state.
        
        Args:
            prescription_id (int): Prescription ID to check
            
        Returns:
            dict: Tampering detection result
        """
        from models import Prescription
        
        prescription = Prescription.query.get(prescription_id)
        if not prescription:
            return {
                'tampered': False,
                'message': 'Prescription not found'
            }
        
        # Get blockchain history
        blocks = self.get_blocks_by_prescription(prescription_id)
        
        if not blocks:
            return {
                'tampered': True,
                'message': 'No blockchain records found - possible tampering',
                'severity': 'CRITICAL'
            }
        
        # Verify each state transition is recorded
        expected_events = []
        if prescription.created_at:
            expected_events.append('PRESCRIPTION_CREATED')
        if prescription.shared_at:
            expected_events.append('PRESCRIPTION_SHARED')
        if prescription.dispensed_at:
            expected_events.append('PRESCRIPTION_DISPENSED')
        if prescription.locked_at:
            expected_events.append('PRESCRIPTION_LOCKED')
        
        # Extract recorded events from blockchain
        recorded_events = []
        for block in blocks:
            try:
                block_data = json.loads(block.data)
                event_type = block_data.get('event_type')
                if event_type:
                    recorded_events.append(event_type)
            except json.JSONDecodeError:
                continue
        
        # Check for missing events
        missing_events = [e for e in expected_events if e not in recorded_events]
        
        if missing_events:
            return {
                'tampered': True,
                'message': 'Missing blockchain records for state transitions',
                'missing_events': missing_events,
                'severity': 'HIGH'
            }
        
        return {
            'tampered': False,
            'message': 'Blockchain records match prescription state',
            'severity': 'NONE'
        }
    
    def get_blockchain_stats(self):
        """
        Get statistics about the blockchain.
        
        Returns:
            dict: Blockchain statistics
        """
        total_blocks = Block.query.count()
        genesis = Block.query.filter_by(index=0).first()
        latest = self.get_latest_block()
        
        # Count events by type
        event_counts = {}
        all_blocks = self.get_chain()
        
        for block in all_blocks:
            try:
                block_data = json.loads(block.data)
                event_type = block_data.get('event_type', 'UNKNOWN')
                event_counts[event_type] = event_counts.get(event_type, 0) + 1
            except json.JSONDecodeError:
                continue
        
        return {
            'total_blocks': total_blocks,
            'chain_height': latest.index if latest else 0,
            'genesis_timestamp': genesis.timestamp.isoformat() if genesis else None,
            'latest_timestamp': latest.timestamp.isoformat() if latest else None,
            'is_valid': self.is_chain_valid(),
            'difficulty': self.difficulty,
            'event_counts': event_counts
        }


def record_prescription_event(event_type, prescription_id, user_id, details):
    """
    Convenience function to record prescription events to blockchain.
    
    Args:
        event_type (str): Type of event (PRESCRIPTION_CREATED, etc.)
        prescription_id (int): Prescription ID
        user_id (int): User ID who triggered the event
        details (dict): Additional event details
        
    Returns:
        Block: Created block object
    """
    blockchain = Blockchain()
    
    return blockchain.add_block(
        event_type=event_type,
        data=details,
        prescription_id=prescription_id,
        user_id=user_id
    )


def record_token_event(event_type, prescription_id, patient_id, token_id, details):
    """
    Convenience function to record access token events to blockchain.
    
    Args:
        event_type (str): Type of event (TOKEN_GENERATED, TOKEN_USED, etc.)
        prescription_id (int): Prescription ID
        patient_id (int): Patient ID who owns the token
        token_id (int): Access token ID
        details (dict): Additional event details
        
    Returns:
        Block: Created block object
    """
    blockchain = Blockchain()
    
    event_data = {
        'token_id': token_id,
        **details
    }
    
    return blockchain.add_block(
        event_type=event_type,
        data=event_data,
        prescription_id=prescription_id,
        user_id=patient_id
    )


def record_emergency_access(prescription_id, admin_id, justification, details):
    """
    Convenience function to record emergency access override to blockchain.
    
    Args:
        prescription_id (int): Prescription ID accessed
        admin_id (int): Admin user ID who performed override
        justification (str): Justification for emergency access
        details (dict): Additional event details
        
    Returns:
        Block: Created block object
    """
    blockchain = Blockchain()
    
    event_data = {
        'justification': justification,
        'is_emergency': True,
        **details
    }
    
    return blockchain.add_block(
        event_type='EMERGENCY_ACCESS',
        data=event_data,
        prescription_id=prescription_id,
        user_id=admin_id
    )


def verify_chain_integrity():
    """
    Verify the entire blockchain integrity.
    
    Returns:
        dict: Verification result with details
    """
    blockchain = Blockchain()
    is_valid = blockchain.is_chain_valid()
    
    return {
        'valid': is_valid,
        'message': 'Blockchain is intact' if is_valid else 'Blockchain has been tampered with',
        'timestamp': datetime.utcnow().isoformat(),
        'stats': blockchain.get_blockchain_stats()
    }
