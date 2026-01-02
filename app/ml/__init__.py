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
    "stop_training_scheduler"
]
