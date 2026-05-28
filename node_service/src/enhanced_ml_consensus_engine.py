'''Compatibility module for legacy imports

Provides the EnhancedMLConsensusEngine class under the expected module name
`enhanced_ml_consensus_engine`. This allows existing code that does:

    from enhanced_ml_consensus_engine import EnhancedMLConsensusEngine

to work without modification.
'''

from ml_consensus_engine import EnhancedMLConsensusEngine

__all__ = ["EnhancedMLConsensusEngine"]
