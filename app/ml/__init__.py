"""
ML Auto-Learning Module for Voice Agent

This module provides automatic learning and training capabilities:
- Conversation data pipeline with embeddings
- Feedback loop for learning from call outcomes
- Dynamic prompt optimization
- Intent classifier training
- Lead scoring ML model
- A/B testing framework
- Nightly/Weekly training scheduler

THREE-BRAIN ARCHITECTURE (Vertex AI Powered):
- Brain #1: Sub-Agent Brain - Powers 13 specialized development sub-agents
- Brain #2: Voice Agent Brain - Handles real-time voice calls with lead generation
- Brain #3: Production Brain - Ensures operational excellence and growth

The system learns from every call and continuously improves the voice agent.
"""

from app.ml.data_pipeline import ConversationDataPipeline, ConversationRecord
from app.ml.feedback_loop import FeedbackLoop, CallOutcome, ResponsePattern
from app.ml.auto_trainer import AutoTrainer, TrainingJob
from app.ml.brain_optimizer import BrainOptimizer, OptimizedPrompt
from app.ml.vector_store import VectorStore, SimilarConversation
from app.ml.training_scheduler import (
    MLTrainingScheduler,
    TrainingScheduleConfig,
    TrainingReport,
    get_training_scheduler,
    stop_training_scheduler
)

# Three-Brain Architecture
from app.ml.agent_brain import AgentBrain, AgentRole, get_agent_brain
from app.ml.voice_agent_brain import VoiceAgentBrain, CallIntent, LeadTemperature, get_voice_agent_brain
from app.ml.production_brain import ProductionBrain, HealthStatus, OptimizationType, get_production_brain
from app.ml.brain_orchestrator import BrainOrchestrator, BrainType, get_brain_orchestrator
from app.ml.codebase_indexer import CodebaseIndexer, get_codebase_indexer

# Brain Auto-Trainer (Billionaire Mode)
from app.ml.brain_auto_trainer import (
    BrainAutoTrainer,
    get_brain_auto_trainer,
    train_brain_now,
    train_all_now,
    record_brain_action,
    SkillCategory,
    BILLIONAIRE_MINDSET,
    BILLIONAIRE_SKILLS,
)

# Vertex AI Continuous Trainer (Production-Ready)
from app.ml.vertex_continuous_trainer import (
    VertexContinuousTrainer,
    VertexTrainingConfig,
    TrainingMetrics,
    TrainingPhase,
    TrainingPriority,
    get_vertex_continuous_trainer,
    start_continuous_training,
    stop_continuous_training,
    train_all_now as vertex_train_all_now,
    get_training_status as vertex_get_training_status,
    record_brain_behavior,
    BILLIONAIRE_TRAINING_PRINCIPLES,
)

__all__ = [
    # Data Pipeline
    "ConversationDataPipeline",
    "ConversationRecord",
    
    # Feedback Loop
    "FeedbackLoop",
    "CallOutcome",
    "ResponsePattern",
    
    # Auto Trainer
    "AutoTrainer",
    "TrainingJob",
    
    # Brain Optimizer
    "BrainOptimizer",
    "OptimizedPrompt",
    
    # Vector Store
    "VectorStore",
    "SimilarConversation",
    
    # Training Scheduler
    "MLTrainingScheduler",
    "TrainingScheduleConfig",
    "TrainingReport",
    "get_training_scheduler",
    "stop_training_scheduler",
    
    # Three-Brain Architecture
    "AgentBrain",
    "AgentRole",
    "get_agent_brain",
    "VoiceAgentBrain",
    "CallIntent",
    "LeadTemperature",
    "get_voice_agent_brain",
    "ProductionBrain",
    "HealthStatus",
    "OptimizationType",
    "get_production_brain",
    "BrainOrchestrator",
    "BrainType",
    "get_brain_orchestrator",
    "CodebaseIndexer",
    "get_codebase_indexer",
    
    # Brain Auto-Trainer (Billionaire Mode)
    "BrainAutoTrainer",
    "get_brain_auto_trainer",
    "train_brain_now",
    "train_all_now",
    "record_brain_action",
    "SkillCategory",
    "BILLIONAIRE_MINDSET",
    "BILLIONAIRE_SKILLS",
    
    # Vertex AI Continuous Trainer (Production-Ready)
    "VertexContinuousTrainer",
    "VertexTrainingConfig",
    "TrainingMetrics",
    "TrainingPhase",
    "TrainingPriority",
    "get_vertex_continuous_trainer",
    "start_continuous_training",
    "stop_continuous_training",
    "vertex_train_all_now",
    "vertex_get_training_status",
    "record_brain_behavior",
    "BILLIONAIRE_TRAINING_PRINCIPLES",
]
